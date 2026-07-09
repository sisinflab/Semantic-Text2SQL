import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
'''
This script provides utility functions to format prompts for a local Qwen2.5-Coder-7B-Instruct model using vLLM.
'''

def format_user_content_first_generator(schema_linking, question):
    return f"""Task Overview:
    You are a data science expert. Below, you are provided with examples, a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

    Database Engine:
    SQLite

    Database Schema:
    {schema_linking}

    This schema describes the database's structure, including tables, columns, primary keys, foreign keys, and any relevant relationships or constraints.

    Question:sssssssssssss
    {question}

    Instructions:
    - Make sure you only output the information that is asked in the question. If the question asks for a specific column, make sure to only include that column in the SELECT clause, nothing more.
    - The generated query should return all of the information asked in the question without any missing or extra information.
    - Before generating the final SQL query, please think through the steps of how to write the query.

    Take a deep breath and think step by step to find the correct SQL query."""

def format_fix_prompt(generated_sql_query, error_message, database_ddl):
    template_path = PROJECT_DIR / "fix_prompt.txt"
    fix_prompt_template = template_path.read_text(encoding="utf-8")
    return fix_prompt_template.format(
        sql_query=generated_sql_query,
        error_message=error_message,
        database_ddl=database_ddl or "",
    )


def format_semantic_prompt(column_evidence,db_name):
    template_path = SCRIPT_DIR / "../" / "prompts" / f"{db_name}.txt"
    semantic_prompt_template = template_path.read_text(encoding="utf-8").strip()
    evidence_payload = json.dumps(column_evidence, ensure_ascii=True, indent=2)
    return (
        f"{semantic_prompt_template}\n\n"
        "COLUMN EVIDENCE JSON:\n"
        f"{evidence_payload}\n"
    )

def format_generic_semantic_prompt(column_evidence):
    template_path = SCRIPT_DIR / "../" / "prompts" / f"generic_prompt.txt"
    semantic_prompt_template = template_path.read_text(encoding="utf-8").strip()
    evidence_payload = json.dumps(column_evidence, ensure_ascii=True, indent=2)
    return (
        f"{semantic_prompt_template}\n\n"
        "COLUMN EVIDENCE JSON:\n"
        f"{evidence_payload}\n"
    )