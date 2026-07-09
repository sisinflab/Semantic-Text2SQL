#This script generates SQL queries using a vLLM model.

import torch
import sqlite3
import os
import json
import datetime
from difflib import SequenceMatcher
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
import sys
import re
import html

'''
This script generates SQL queries using a vLLM model.
'''

# Recuperiamo i percorsi base dalle variabili d'ambiente
SCRATCH = os.getenv('CINECA_SCRATCH', './')
HOME = os.getenv('HOME', './')


#usiamo momentaneamente scratch come work
# WORK = os.getenv('WORK') 
WORK=SCRATCH


# Impostiamo la cache di Hugging Face in scratch per non finire lo spazio in Home
os.environ["HF_HOME"] = os.path.join(SCRATCH, ".cache/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1" # Forza modalità offline per i nodi di calcolo

CHECKPOINT_INTERVAL = 100
TEST_SIZE = None
SCHEMA_CACHE = {}



MAX_MODEL_LEN = 4096
MAX_GEN_TOKENS = 250
PROMPT_TOKEN_BUFFER = 32
MAX_PROMPT_TOKENS = MAX_MODEL_LEN - MAX_GEN_TOKENS - PROMPT_TOKEN_BUFFER

def quote_ident(name: str) -> str:
    return f'"{name.replace("\"", "\"\"")}"'

def safe_tokenizer_load(model_path: str):
    try:
        return AutoTokenizer.from_pretrained(model_path, trust_remote_code=True, fix_mistral_regex=True)
    except TypeError:
        return AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

def build_prompt_text(system_message: str, schema: str, question: str, tokenizer, max_prompt_tokens: int) -> str:
    def make(schema_text: str) -> str:
        schema_str = "Database Schema:\n" + schema_text
        user_message = f"""{schema_str}

                Question: {question}

                Generate the SQL query (use exact column and table names):"""
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    def token_len(text: str) -> int:
        return len(tokenizer(text, add_special_tokens=False).input_ids)

    lines = schema.splitlines()
    prompt = make("\n".join(lines))
    if token_len(prompt) <= max_prompt_tokens:
        return prompt

    lines = [ln for ln in lines if not ln.startswith("-- ")]
    prompt = make("\n".join(lines))
    if token_len(prompt) <= max_prompt_tokens:
        return prompt

    while lines:
        lines = lines[:-1]
        prompt = make("\n".join(lines))
        if token_len(prompt) <= max_prompt_tokens:
            return prompt

    return make("")


global total_skipped_error_columns
global total_skipped_text_columns
global total_skipped_tables
total_skipped_tables = 0
total_skipped_text_columns = 0
total_skipped_error_columns = 0




def save_checkpoint(results, exact_matches, execution_matches, total_valid_predictions, total_similarity, current_index):
    checkpoint_data = {
        "results": results,
        "exact_matches": exact_matches,
        "execution_matches": execution_matches,
        "total_valid_predictions": total_valid_predictions,
        "total_similarity": total_similarity,
        "current_index": current_index
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def compute_gpu_memory_utilization_from_free(target_free_ratio: float = 0.7) -> float:
    """use 70% of the GPU memory minus the minimum free memory ratio specified"""
    if not torch.cuda.is_available():
        return 0.9
    ratios = []
    for i in range(torch.cuda.device_count()):
        try:
            free_b, total_b = torch.cuda.mem_get_info(i)
            if total_b > 0:
                ratios.append(float(free_b) / float(total_b))
        except Exception:
            ratios.append(0.5)
    if not ratios:
        return 0.7
    util = max(0.1, min(0.9, min(ratios) * float(target_free_ratio)))
    return util

def extract_sql_query(text: str) -> str:
    raw = text.strip()

    # Priority: corrected_plan > final_sql > initial_plan
    for tag in ("corrected_plan", "final_sql", "initial_plan"):
        m = re.search(rf'<{tag}>\s*(.*?)\s*</{tag}>', raw, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
            break
    else:
        # Blocks ```sql ... ```
        m = re.search(r'```sql\s*(.*?)\s*```', raw, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            # Remove HTML tags and take the first SELECT
            raw_no_tags = re.sub(r'<[^>]+>', ' ', raw)
            m = re.search(r'(SELECT\s+.*?)(;|$)', raw_no_tags, re.IGNORECASE | re.DOTALL)
            raw = m.group(1) if m else raw_no_tags

    # Cleaning
    sql = re.sub(r'<[^>]+>', ' ', raw)
    sql = html.unescape(sql)
    sql = sql.replace('\n', ' ')
    sql = re.sub(r'\s+', ' ', sql)
    sql = re.sub(r'\s+([,;])', r'\1', sql)
    return sql.strip()

def get_schema(db_id):

    #db_path = f"../data/original/train_databases/{db_id}/{db_id}.sqlite"
    db_path = os.path.join(SCRATCH, f"data/original/dev_databases/{db_id}/{db_id}.sqlite")
    if not os.path.exists(db_path):
        return "", {'skipped_tables': 0, 'skipped_text_columns': 0, 'skipped_error_columns': 0}
    
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:  # ✅ chiusura automatica
            cursor = conn.cursor()
            output = []
            skipped_tables = skipped_text_columns = skipped_error_columns = 0

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                cursor.execute("SELECT sql FROM sqlite_master WHERE name=?;", (table_name,))
                create_result = cursor.fetchone()
                if not create_result:
                    skipped_tables += 1
                    continue

                create_sql = create_result[0]
                compact_sql = ' '.join(create_sql.split())
                output.append(f"{compact_sql};")
                
                cursor.execute(f"PRAGMA table_info({quote_ident(table_name)});")
                columns = cursor.fetchall()
                
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    if col_type == 'TEXT' and col_name in ['overview', 'homepage', 'tagline']:
                        skipped_text_columns += 1
                        continue
                    try:
                        query = f"SELECT DISTINCT `{col_name}` FROM `{quote_ident(table_name)}` WHERE `{col_name}` IS NOT NULL LIMIT 2"
                        cursor.execute(query)
                        examples = [str(ex[0])[:50] for ex in cursor.fetchall()]
                        if examples:
                            output.append(f"-- {table_name}.{col_name}: {examples}")
                    except Exception:
                        skipped_error_columns += 1
                        continue

            stats = {
                'skipped_tables': skipped_tables,
                'skipped_text_columns': skipped_text_columns,
                'skipped_error_columns': skipped_error_columns
            }
            return '\n'.join(output), stats
    except Exception as e:
        print(f"⚠️ Error accessing database {db_id}: {e}")
        return "", {'skipped_tables': 0, 'skipped_text_columns': 0, 'skipped_error_columns': 0}


import csv
def get_schema_from_csv(db_id):
    all=False
    csvs_folder = f"data/original/dev_databases/{db_id}/database_description"
    csvs_folder = os.path.join(SCRATCH, csvs_folder)
    if not os.path.exists(csvs_folder):
        return ""

    output = []
    failed_csvs = []
    tables_names = []
    for csv_file in sorted(os.listdir(csvs_folder)):
        print(csv_file)
        if not csv_file.endswith(".csv"):
            continue
        table_name = csv_file.replace(".csv", "")
        csv_path = os.path.join(csvs_folder, csv_file)
        columns = []
        try:
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        col_name = (
                                row.get("original_column_name")
                                or row.get("name")
                                or row.get("\ufefforiginal_column_name")
                                or row.get("column_name")
                            )
                        col_type = row.get("data_format") or row.get("type") or row.get("column_type")
                        if col_type:
                            col_type = col_type.strip()
                        if col_name:
                            columns.append(f'"{col_name}" {col_type if col_type else "text"}')
            except Exception as e:
                print(f"Error processing {csv_path.split('/')[-1]} with utf-8-sig: {e}. Trying utf-8...")
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            col_name = (
                                    row.get("original_column_name")
                                    or row.get("name")
                                    or row.get("\ufefforiginal_column_name")
                                    or row.get("column_name")
                                )
                            col_type = row.get("data_format") or row.get("type") or row.get("column_type")
                            if col_type:
                                col_type = col_type.strip()
                            if col_name:
                                columns.append(f'"{col_name}" {col_type if col_type else "text"}')
                except Exception as e2:
                    print(f"Error processing {csv_path.split('/')[-1]} with utf-8: {e2}. Trying latin1...")
                    try:
                        with open(csv_path, "r", encoding="latin1") as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                col_name = (
                                        row.get("original_column_name")
                                        or row.get("name")
                                        or row.get("\ufefforiginal_column_name")
                                        or row.get("column_name")
                                    )
                                col_type = row.get("data_format") or row.get("type") or row.get("column_type")
                                if col_type:
                                    col_type = col_type.strip()
                                if col_name:
                                    columns.append(f'"{col_name}" {col_type if col_type else "text"}')
                    except Exception as e3:
                        print(f"Error processing {csv_path.split('/')[-1]} with latin1: {e3}.")
                        failed_csvs.append(csv_file)
            if columns:
                print(f"Processed {csv_path.split('/')[-1]} with {len(columns)} columns.")
                create_sql = f'CREATE TABLE "{table_name}" (\n  {", ".join(columns)}\n);'
                #print(create_sql)
                output.append(create_sql)
                tables_names.append(table_name)
            else:
                failed_csvs.append(csv_file)
        except Exception as e:
            print(f"Error processing {csv_path.split('/')[-1]}, skipping. Exception: {e}")
            failed_csvs.append(csv_file)
            continue
    
    #output.append(f"Nomi tabelle: {', '.join(tables_names)}")

    if failed_csvs:
        print("\nCSV non processati (errori):")
        for f in failed_csvs:
            print(f"  - {f}")
    else:        
        print("\nTutti i CSV sono stati processati con successo.")
        all=True
    return '\n'.join(output), tables_names



def results_match(pred_result, gold_result):
    """Check if the results of the two queries are identical"""
    if pred_result is None or gold_result is None:
        return False
    
    pred_normalized = set(str(r).lower().strip() for r in pred_result)
    gold_normalized = set(str(r).lower().strip() for r in gold_result)
    
    return pred_normalized == gold_normalized

def similarity_ratio(pred, gold):
    """Calculate similarity between predicted and gold queries using SequenceMatcher"""
    return SequenceMatcher(None, pred.lower(), gold.lower()).ratio()

def exact_match(pred, gold):
    """Check exact match (normalizing spaces)"""
    pred_norm = " ".join(pred.split()).lower()
    gold_norm = " ".join(gold.split()).lower()
    return 1.0 if pred_norm == gold_norm else 0.0




def format_user_content_with_evidence_and_semantic_info(schema_linking, question,evidence,semantic_info):
    return f"""Task Overview:
    You are a data science expert. Below, you are provided with examples, a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

    Database Engine:
    SQLite

    Question:
    {question}

    Evidence:
    {evidence}

    

    Database Schema:
    {schema_linking}

    This schema describes the database's structure, including tables, columns, primary keys, foreign keys, and any relevant relationships or constraints.

    Semantic Information about columns:
    {semantic_info}

    How to read semantic information:
    - Format: semantic_concept: table.column, table.column, ...
        - Example:
            person_name: comments.UserDisplayName, postHistory.UserDisplayName, posts.OwnerDisplayName, posts.LastEditorDisplayName, users.DisplayName
            title: posts.Title
    - Each semantic concept groups columns that can represent the same meaning.
    - Use these mappings to identify the most relevant tables and columns for the question.
    - Prefer mapped columns when they match the requested concept.
    - Do not invent columns: use only columns present in the schema.
    - If multiple mapped columns are possible, choose the one that best fits question constraints and joins.
    
    Question:
    {question}

    Evidence:
    {evidence}

    Instructions:
    - Make sure you only output the information that is asked in the question. If the question asks for a specific column, make sure to only include that column in the SELECT clause, nothing more.
    - The generated query should return all of the information asked in the question without any missing or extra information.
    - Use semantic mappings to resolve ambiguous terms in the question (for example synonyms or high-level concepts).
    - Use proper joins based on schema relations when mapped columns belong to different tables.
    - Before generating the final SQL query, please think through the steps of how to write the query.

    Take a deep breath and think step by step to find the correct SQL query."""

def generate_sql_batch(llm, tokenizer, sampling_params, questions, db_names, schema_linking_list,ids,evidence_list, semantic_info_list):
    """Generate SQL for multiple questions in batch"""
    global total_skipped_error_columns
    global total_skipped_text_columns
    global total_skipped_tables
    
    prompts = []
    # system_message = open("../finetuning/system_prompt.txt", "r", encoding="utf-8").read()

    system_prompt_path = "system_prompt.txt"
    
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_message = f.read()

    for question, db_name, schema_linking,id,evidence, semantic_info in zip(questions, db_names, schema_linking_list,ids,evidence_list, semantic_info_list):

        # db_path = os.path.join(SCRATCH, f"data/original/dev_databases/{db_name}/{db_name}.sqlite")
        # # schema = {}
        # schema = ""
        # if os.path.exists(db_path):
        #     if db_name not in SCHEMA_CACHE:
        #         SCHEMA_CACHE[db_name],tables_names = get_schema_from_csv(db_name)
        #     schema = SCHEMA_CACHE[db_name]
    
        # schema_str = "Database Schema:\n" + schema

        # user_message = format_user_content(schema_linking, question)
        user_message= format_user_content_with_evidence_and_semantic_info(schema_linking, question,evidence, semantic_info)
        

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompts.append((text,id))
    
    
    # Generate in batch
    prompt_texts = [p[0] for p in prompts]
    outputs = llm.generate(prompt_texts, sampling_params)
    
    # Extract SQL from outputs, associando ogni risposta al suo id
    sqls = []
    for out, (_, id) in zip(outputs, prompts):
        result = out.outputs[0].text
        sql = result.split("assistant\n")[-1].strip() if "assistant" in result else result
        sqls.append({"id": id, "sql": sql})
    return sqls


if __name__ == '__main__':

    model_path = os.getenv('MODEL_PATH')
    
    if not model_path:
        print("ERRORE: Variabile d'ambiente MODEL_PATH obbligatoria mancante!")
        sys.exit(1)


        # Estrai il nome del modello dal path per checkpoint unico
    model_name = os.path.basename(model_path)
    CHECKPOINT_FILE = os.path.join(WORK, f"checkpoint_{model_name}.json")

    print(f"Checkpoint file: {CHECKPOINT_FILE}")
    print(f"Loading model and tokenizer from: {model_path}")
    

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    gpu_util = compute_gpu_memory_utilization_from_free(0.7)

    llm = LLM(
        model=model_path,
        tensor_parallel_size=4,
        dtype="bfloat16",
        gpu_memory_utilization=gpu_util,
        trust_remote_code=True
    )

    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=8192,
    )

    print("Model loaded successfully!")


    # ### LEONARDO  ### Caricamento dataset da Scratch
    #dataset_path = os.path.join(SCRATCH, "data/original/dev_filtered.json")

    dataset_path = os.path.join(HOME, "multi_agent_ttsql/semantic_agent_description/_4_source_dataset_with_columns_by_semantic_concept.json")

    with open(dataset_path, "r", encoding="utf-8") as f:
        if TEST_SIZE is not None:
            test_data = json.load(f)[:TEST_SIZE]
        else:
            test_data = json.load(f)
   
    total= len(test_data)

    # Evaluation
    print("\n" + "="*70)
    print("EXECUTION-BASED EVALUATION (vLLM)")
    print("="*70)



    # Load checkpoint if available
    checkpoint = load_checkpoint()

    if checkpoint:
        print(f"Resuming from checkpoint at example index {checkpoint['current_index']}")
        results = checkpoint["results"]
        exact_matches = checkpoint["exact_matches"]
        execution_matches = checkpoint["execution_matches"]
        total_valid_predictions = checkpoint["total_valid_predictions"]
        total_similarity = checkpoint["total_similarity"]
        start_index = checkpoint["current_index"]
    else:
        print("No checkpoint found, starting fresh evaluation.")
        results = []
        exact_matches = 0
        execution_matches = 0
        total_valid_predictions = 0
        total_similarity = 0
        start_index = 0

    start = datetime.datetime.now()

    # Prepare batch
    questions = [ex["question"] for ex in test_data]
    db_names = [ex["db_id"] for ex in test_data]
    schema_linking = [ex['schema_linking'] for ex in test_data]
    evidence_list = [ex['evidence'] for ex in test_data]
    ids = [ex['_id'] for ex in test_data]
    semantic_info_list = [ex['columns_by_semantic_concept'] for ex in test_data]

    # Generate all predictions in batch
    print("Generating SQL queries in batch...")
    start= datetime.datetime.now()
    pred_sqls = generate_sql_batch(llm, tokenizer, sampling_params, questions, db_names, schema_linking, ids, evidence_list, semantic_info_list)
    end= datetime.datetime.now()
    print("SQL generation completed.")
    print(f"Total skipped tables: {total_skipped_tables}")
    print(f"Total skipped TEXT columns: {total_skipped_text_columns}")
    print(f"Total skipped error columns: {total_skipped_error_columns}")
    print(f"Tempo totale generazione: {(end - start).total_seconds():.2f} secondi")
    print(f"Tempo medio di esecuzione:'{(((end - start).total_seconds()) / len(pred_sqls)):.2f} secondi per prompt")


    OUTPUT_FILENAME= '_5_vllm_pred_sqls' +  model_name + '.json'
    #save pred_sqls to a json file
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(pred_sqls, f, indent=2, ensure_ascii=False)


    print(SCHEMA_CACHE)

