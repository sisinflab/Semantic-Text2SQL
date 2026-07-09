#This script generates SQL queries using a vLLM model and evaluates them against a test dataset.

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


SCRATCH = os.getenv('SCRATCH', os.getenv('CINECA_SCRATCH', './'))
HOME = os.getenv('HOME', './')

#usiamo momentaneamente scratch come work
# WORK = os.getenv('WORK') 
WORK=SCRATCH


# Impostiamo la cache di Hugging Face in scratch per non finire lo spazio in Home
os.environ["HF_HOME"] = os.path.join(SCRATCH, ".cache/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1" # Forza modalità offline per i nodi di calcolo

TEST_SIZE = None  # Usa None per tutto il dataset, o un numero per limitare
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
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)

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
import csv
total_skipped_tables = 0
total_skipped_text_columns = 0
total_skipped_error_columns = 0


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

def format_user_content(schema_linking, question):
    return f"""Task Overview:
    You are a data science expert. Below, you are provided with examples, a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

    Database Engine:
    SQLite

    Database Schema:
    {schema_linking}

    This schema describes the database's structure, including tables, columns, primary keys, foreign keys, and any relevant relationships or constraints.

    Question:
    {question}

    Instructions:
    - Make sure you only output the information that is asked in the question. If the question asks for a specific column, make sure to only include that column in the SELECT clause, nothing more.
    - The generated query should return all of the information asked in the question without any missing or extra information.
    - Before generating the final SQL query, please think through the steps of how to write the query.

    Take a deep breath and think step by step to find the correct SQL query."""

def format_user_content_with_evidence(schema_linking, question,evidence):
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

    Question:
    {question}

    Evidence:
    {evidence}

    Instructions:
    - Make sure you only output the information that is asked in the question. If the question asks for a specific column, make sure to only include that column in the SELECT clause, nothing more.
    - The generated query should return all of the information asked in the question without any missing or extra information.
    - Before generating the final SQL query, please think through the steps of how to write the query.

    Take a deep breath and think step by step to find the correct SQL query."""

def generate_sql_batch(llm, tokenizer, sampling_params, questions, db_names, schema_linking_list,ids,evidence_list):
    """Generate SQL for multiple questions in batch"""
    global total_skipped_error_columns
    global total_skipped_text_columns
    global total_skipped_tables
    
    prompts = []

    system_prompt_path ="system_prompt.txt"  
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_message = f.read()

    for question, db_name, schema_linking,id,evidence in zip(questions, db_names, schema_linking_list,ids,evidence_list):


        user_message= format_user_content_with_evidence(schema_linking, question, evidence)
        

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

    model_name = os.path.basename(model_path)



    print(f"Loading model and tokenizer from: {model_path}")
    

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    gpu_util = compute_gpu_memory_utilization_from_free(0.7)

    llm = LLM(
        model=model_path,
        tensor_parallel_size=4,
        dtype="bfloat16",
        gpu_memory_utilization=gpu_util,
        max_model_len=4096, 
        trust_remote_code=True
    )

    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=8192,
    )

    print("Model loaded successfully!")



    dataset_path = "path/to/dataset.json"  

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

    # Generate all predictions in batch
    print("Generating SQL queries in batch...")
    pred_sqls = generate_sql_batch(llm, tokenizer, sampling_params, questions, db_names, schema_linking,ids, evidence_list)

    print("SQL generation completed.")
    print(f"Total skipped tables: {total_skipped_tables}")
    print(f"Total skipped TEXT columns: {total_skipped_text_columns}")
    print(f"Total skipped error columns: {total_skipped_error_columns}")


    OUTPUT_FILENAME= 'vllm_pred_sqls' +  model_name + '.json'
    #save pred_sqls to a json file
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(pred_sqls, f, indent=2, ensure_ascii=False)


