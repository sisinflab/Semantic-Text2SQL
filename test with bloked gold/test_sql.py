import os
import sqlite3
import datetime
import ast
import json
import re
import html
from pathlib import Path
from difflib import SequenceMatcher
import multiprocessing

def extract_previus_project(text: str) -> str:
    # Ensure the query ends with a semicolon if not already present
    text_pred = text.rstrip()
    if not text_pred.endswith(';'):
        text_pred += ';'


    sql_pattern = re.compile(r'```(?:sql|sqlite)\s*(.*?)\s*```', re.DOTALL)

    matches = sql_pattern.findall(text_pred)
    if matches:
        sql_query = matches[-1].strip()

        if sql_query.startswith('ite '):
            sql_query = sql_query[4:]  # Remove the "ite " prefix

        #sql_query = safe_sql(sql_query)


        extracted_sql = sql_query
    else:
        sql_pattern = re.compile(r'```(?!\s*\w+\s*\n)(.*?)```', re.DOTALL)
        matches2 = sql_pattern.findall(text_pred)
        if matches2:
            sql_query = matches2[-1].strip()

            if sql_query.startswith('ite '):
                sql_query = sql_query[4:]  # Remove the "ite " prefix

            extracted_sql = sql_query

        else:
            extracted_sql = ""

    return extracted_sql

def extract_sql_query_simple(text: str) -> str:
    """Estrae la query tra i tag <final_sql> oppure da <final_sql> alla fine."""
    m = re.search(r'<final_sql>\s*(.*?)\s*</final_sql>', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    m2 = re.search(r'<final_sql>\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if m2:
        return m2.group(1).strip()
    
    n= re.search(r'```sql\s*(.*?)\s*```', text, re.IGNORECASE | re.DOTALL)
    if n:
        return n.group(1).strip()
    
    return text.strip()

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


#ignora la differenza sul punto e virgola finale 
def exact_match(pred, gold):
    """Check exact match (normalizing spaces)"""
    pred_norm = " ".join(pred.split()).lower().rstrip(" ;")
    gold_norm = " ".join(gold.split()).lower().rstrip(" ;")
    return 1.0 if pred_norm == gold_norm else 0.0

def worker(conn_pipe, db_path, sql):
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            conn_pipe.send((result, None))
    except Exception as e:
        conn_pipe.send((None, str(e)))
    finally:
        conn_pipe.close()

def run_query_with_timeout(db_path, sql, timeout=20):
    parent_conn, child_conn = multiprocessing.Pipe()
    p = multiprocessing.Process(target=worker, args=(child_conn, db_path, sql))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join()
        return None, "Timeout"
    if parent_conn.poll():
        result, error = parent_conn.recv()
        return result, error
    return None, "Unknown error"


def load_gold_results(gold_results_path: Path) -> dict[str, dict[str, object]]:
    with gold_results_path.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)

    if not isinstance(rows, list):
        raise ValueError("The gold results file must contain a JSON list.")

    gold_by_id: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue

        question_id = row.get("question_id")
        if question_id is None:
            continue

        gold_result = row.get("gold_result")
        if isinstance(gold_result, str):
            try:
                gold_result = ast.literal_eval(gold_result)
            except (ValueError, SyntaxError):
                pass

        row = dict(row)
        row["gold_result"] = gold_result

        gold_by_id[str(question_id)] = row

    return gold_by_id

if __name__ == "__main__":
    multiprocessing.freeze_support()


    start=datetime.datetime.now()
    dataset_path = "path/to/dataset.json" 
    
    TEST_SIZE= None  # Set to a smaller number for quick testing, e.g., 10

    with open(dataset_path, "r", encoding="utf-8") as f:
            if TEST_SIZE is not None:
                test_data = json.load(f)[:TEST_SIZE]
            else:                
                test_data = json.load(f)

    gold_results_path = Path(__file__).with_name("gold_only.json")
    gold_results_by_id = load_gold_results(gold_results_path)

    FILE_TO_PROCESS="base.json"

    with open(FILE_TO_PROCESS, "r", encoding="utf-8") as f:
        if TEST_SIZE is not None:
            id_and_pred_sql = json.load(f)[:TEST_SIZE]
        else:
            id_and_pred_sql = json.load(f)

    # ===========================
    # indicizzazione per ID
    # ===========================

    predictions_by_id = {}
    duplicate_prediction_ids = []

    for row in id_and_pred_sql:
        pred_id = str(row["id"])

        if pred_id in predictions_by_id:
            duplicate_prediction_ids.append(pred_id)

        predictions_by_id[pred_id] = row

    dataset_ids = {str(x["_id"]) for x in test_data}
    prediction_ids = set(predictions_by_id.keys())

    extra_prediction_ids = sorted(prediction_ids - dataset_ids)
    missing_prediction_ids = []

    print(f"Dataset examples: {len(dataset_ids)}")
    print(f"Prediction examples: {len(prediction_ids)}")
    print(f"Extra predictions: {len(extra_prediction_ids)}")
    print(f"Duplicate prediction IDs: {len(duplicate_prediction_ids)}")

    total = len(dataset_ids)
    matched_ids = 0
    results = []
    exact_matches = 0
    execution_matches = 0
    total_valid_predictions = 0
    total_similarity = 0
    total_timeouts_gold = 0
    total_timeouts_pred = 0
    total_gold_errors = 0
    total_pred_errors = 0
    empty_pred_sql_count = 0
    empty_responses = []

    total_id_not_matching = 0

    gold_errors_list = []
    # Dizionario per classificare errori pred_sql
    pred_error_types = {}

    pred_good_result=[]
    #     # Evaluate each prediction
    for i, example in enumerate(test_data):

        gold_id = str(example["_id"])

        pred_obj = predictions_by_id.get(gold_id)

        if pred_obj is None:
            print(f"\n⚠️ Missing prediction for ID {gold_id}")

            missing_prediction_ids.append(gold_id)

            results.append({
                "question": example["question"],
                "gold_sql": example["target"],
                "pred_sql": None,
                "exact_match": 0.0,
                "similarity": 0.0,
                "execution_match": 0,
                "gold_error": None,
                "pred_error": "Missing prediction",
                "gold_result": None,
                "pred_result": None,
                "question_id": gold_id,
            })

            continue

        matched_ids += 1

        print(f"\nEvaluating example {matched_ids}/{total}")

        start_i = datetime.datetime.now()

        og_pred = pred_obj["sql"]
        

        question = example["question"]
        gold_sql = example["target"]
        db_id = example["db_id"]

        print(f'Gold SQL:\n{gold_sql}')
        print(f"Database ID: {db_id}")

        extract_start = datetime.datetime.now()

        pred_sql = extract_sql_query_simple(og_pred)

        print(f"Predicted SQL:\n{pred_sql}")

        extract_end = datetime.datetime.now()

        print(
            f"  ⏱️ extract_sql_query: "
            f"{(extract_end - extract_start).total_seconds():.3f}s"
        )

        if not pred_sql.strip():
            empty_pred_sql_count += 1
            empty_responses.append(og_pred)

        metrics_start = datetime.datetime.now()

        em = exact_match(pred_sql, gold_sql)
        sim = similarity_ratio(pred_sql, gold_sql)

        metrics_end = datetime.datetime.now()

        print(
            f"  ⏱️ string_metrics: "
            f"{(metrics_end - metrics_start).total_seconds():.3f}s"
        )

        exact_matches += em
        total_similarity += sim

        execution_match = 0
        pred_error = None
        gold_error = None
        pred_result = None
        gold_result = None

        db_path = (
            f"../data/original/dev_databases/"
            f"{db_id}/{db_id}.sqlite"
        )

        question_id = gold_id

        gold_record = gold_results_by_id.get(question_id)

        if gold_record is None:

            gold_error = "Missing gold record"

            total_gold_errors += 1
            gold_errors_list.append(question_id)

            print(
                f"  ❌ gold record not found "
                f"for question_id {question_id}"
            )

        else:

            gold_result = gold_record.get("gold_result")
            gold_error = gold_record.get("gold_error")

            if gold_error:

                print(
                    f"  ❌ gold record reports error: "
                    f"{gold_error}"
                )

                gold_errors_list.append(question_id)

                total_gold_errors += 1

                if str(gold_error).lower() == "timeout":
                    total_timeouts_gold += 1

            else:

                print(
                    f"  ✅ gold record loaded "
                    f"(result available: {gold_result is not None})"
                )

        try:

            pred_start = datetime.datetime.now()

            pred_result, pred_error = run_query_with_timeout(
                db_path,
                pred_sql,
                timeout=20,
            )

            pred_end = datetime.datetime.now()

            print(
                f"  ⏱️ pred_sql execution: "
                f"{(pred_end - pred_start).total_seconds():.3f}s "
                f"rows: {len(pred_result) if pred_result else 'N/A'}"
            )

            if pred_error:

                print(
                    f"  ❌ pred_sql FAILED or TIMEOUT: "
                    f"{pred_error}"
                )

                if pred_error == "Timeout":
                    total_timeouts_pred += 1

                total_pred_errors += 1

                if "no such table" in pred_error.lower():
                    err_key = "no such table"
                elif "syntax error" in pred_error.lower():
                    err_key = "syntax error"
                elif "timeout" in pred_error.lower():
                    err_key = "timeout"
                elif "unrecognized token" in pred_error.lower():
                    err_key = "unrecognized token"
                elif "no such column" in pred_error.lower():
                    err_key = "no such column"
                else:
                    err_key = "other"

                pred_error_types[err_key] = (
                    pred_error_types.get(err_key, 0) + 1
                )

            else:

                print(
                    f"  ✅ pred_sql OK "
                    f"(rows: {len(pred_result)})"
                )

                if gold_error is None:

                    total_valid_predictions += 1

                    if results_match(pred_result, gold_result):

                        execution_match = 1
                        execution_matches += 1

                        print("  ✅ Results MATCH!")

                    else:

                        print("  ⚠️ Results DIFFER")

        except FileNotFoundError:
            pred_error = "DB not found"

        except sqlite3.OperationalError as e:
            pred_error = f"DB error: {str(e)}"

        except Exception as e:
            pred_error = str(e)

        results.append({
            "question": question,
            "gold_sql": gold_sql,
            "pred_sql": pred_sql,
            "exact_match": em,
            "similarity": sim,
            "execution_match": execution_match,
            "gold_error": gold_error,
            "pred_error": pred_error,
            "gold_result": str(gold_result) if gold_result else None,
            "pred_result": str(pred_result) if pred_result else None,
            "question_id": question_id,
        })

    OUTPUT_RESULTS_NAME = "evaluation_results_sql_speed"+ FILE_TO_PROCESS +".json"
    with open(OUTPUT_RESULTS_NAME, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    print("\n\n=== FINAL EVALUATION RESULTS ===")
    print(f"Total examples: {total}")
    print(f"Exact Match: {exact_matches}/{total} = {exact_matches/total:.3f}")
    print(f"Average Similarity: {total_similarity/total:.3f}")
    print(f"Total Gold Timeouts: {total_timeouts_gold}")
    print(f"Total Predicted Timeouts: {total_timeouts_pred}")
    print(f"Total Gold Errors: {total_gold_errors}")
    print(f"Gold Errors Question IDs: {gold_errors_list}")
    print(f"Total Predicted Errors: {total_pred_errors}")
    print(f"Empty Predicted SQL : {empty_pred_sql_count}")
    #print (f"IDs with Empty Predicted SQL: {empty_responses}")

    with open("empty_pred_sqls.json", "w", encoding="utf-8") as f:
        json.dump(empty_responses, f, indent=2, ensure_ascii=False)

    print("\nPredicted SQL Error Types:")
    for err_type, count in pred_error_types.items():
        print(f"  {err_type}: {count} / {total_pred_errors}")
    if total_valid_predictions > 0:
        print(f"Execution Match (valid predictions): {execution_matches}/{total_valid_predictions} = {execution_matches/total_valid_predictions:.3f}")
    else:
        print("Execution Match (valid predictions): No valid predictions to evaluate.")

    print(f"Total execution match accuracy: {execution_matches}/{total} = {execution_matches/total:.3f}")

    print(f"Total ID mismatches between gold and pred: {total_id_not_matching}")
    print("\n=== ID MATCH REPORT ===")

    print(f"Dataset IDs: {len(dataset_ids)}")
    print(f"Prediction IDs: {len(prediction_ids)}")

    print(f"Matched IDs: {matched_ids}")

    print(
        f"Missing predictions: "
        f"{len(missing_prediction_ids)}"
    )

    print(
        f"Extra predictions: "
        f"{len(extra_prediction_ids)}"
    )

    print(
        f"Duplicate prediction IDs: "
        f"{len(duplicate_prediction_ids)}"
    )

    coverage = matched_ids / len(dataset_ids)

    print(f"Coverage: {coverage:.3f}")

    with open(
        "id_matching_report.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "dataset_ids": len(dataset_ids),
                "prediction_ids": len(prediction_ids),
                "matched_ids": matched_ids,
                "coverage": coverage,
                "missing_prediction_ids": missing_prediction_ids,
                "extra_prediction_ids": extra_prediction_ids,
                "duplicate_prediction_ids": duplicate_prediction_ids,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    end=datetime.datetime.now()
    print(f"Total evaluation time: {(end - start).total_seconds():.3f}s")
    print(f"total time in minutes: {(end - start).total_seconds()/60:.3f}min")