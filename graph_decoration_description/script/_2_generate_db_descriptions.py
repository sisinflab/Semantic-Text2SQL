import argparse
import json
import os
import time
from pathlib import Path
from _0_generator import query_qwen

"""
Generates detailed English DB descriptions using JSON semantic evidence files
and a specific system prompt template.
"""

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DESCRIPTIONS_DIR = PROJECT_DIR / "descriptions"

DEFAULT_SETTINGS = {
    "evidence_dir": PROJECT_DIR / "semantic_evidence", 
    # Percorso aggiornato come richiesto
    "template_path": PROJECT_DIR / "prompts" / "system_prompts" / "gen_description_prompt.txt",
}

def load_external_template() -> str:
    """Loads the prompt text from the specialized system_prompts folder."""
    path = DEFAULT_SETTINGS["template_path"]
    if not path.exists():
        raise FileNotFoundError(f"System prompt template NOT FOUND at: {path}")
    return path.read_text(encoding="utf-8")

def collect_semantic_context(db_name: str) -> str:
    """
    Parses the semantic evidence JSON to build a rich context for the LLM.
    Includes types, keys, and sample values.
    """
    evidence_file = DEFAULT_SETTINGS["evidence_dir"] / f"{db_name}.json"
    
    if not evidence_file.exists():
        print(f"    [!] Warning: Evidence file missing for {db_name}")
        return "No semantic evidence available."

    try:
        with open(evidence_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        sections = []
        for table in data.get("tables", []):
            t_name = table.get("table_name", "Unknown")
            t_rows = table.get("row_count", 0)
            lines = [f"### TABLE: {t_name} | Rows: {t_rows}"]
            
            for col in table.get("columns", []):
                c_name = col.get("column_name", "Unknown")
                c_type = col.get("sqlite_declared_type", "DATA")
                
                # Metadata extraction
                meta = col.get("metadata", {})
                desc = meta.get("description") or "N/A"
                
                # Structural Info (PK/FK)
                pk = "[PRIMARY KEY]" if col.get("is_primary_key") else ""
                fk_info = ""
                if col.get("is_foreign_key"):
                    target = col.get("foreign_key_target", {})
                    fk_info = f"[FOREIGN KEY references {target.get('references_table')}({target.get('references_column')})]"
                
                # Value Evidence (Samples)
                v_evid = col.get("value_evidence", {})
                samples = v_evid.get("sample_values", [])
                sample_str = f" | Samples: {samples[:4]}" if samples else ""

                lines.append(f"- {c_name} ({c_type}) {pk}{fk_info}: {desc}{sample_str}")
            
            sections.append("\n".join(lines))
        
        return "\n\n".join(sections)

    except Exception as e:
        print(f"    [!] Error parsing JSON for {db_name}: {e}")
        return "Error extracting data from JSON."

def process_database(db_name: str, template: str, current: int, total: int, model_path: str | None = None) -> bool:
    print(f"\n>>> [{current}/{total}] DB: {db_name}")
    start_time = time.time()
    
    try:
        # 1. Estrazione dati dal JSON
        print(f"    [step 1/4] Reading semantic evidence...")
        schema_context = collect_semantic_context(db_name)
        
        # 2. Popolamento Prompt
        print(f"    [step 2/4] Formatting prompt with system template...")
        final_prompt = template.replace("{{db_name}}", db_name)
        final_prompt = final_prompt.replace("{{schema_context}}", schema_context)
        
        # 3. Query Modello
        print(f"    [step 3/4] Sending to LLM (waiting)...")
        q_start = time.time()
        query_kwargs = {"prompt": final_prompt, "max_new_tokens": 8192, "temperature": 0.2}
        if model_path:
            query_kwargs["model_path"] = model_path

        response = query_qwen(**query_kwargs)

        print(f"    [info] LLM response time: {time.time() - q_start:.2f}s")

        # 4. Salvataggio
        if response:
            OUTPUT_DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
            out_file = OUTPUT_DESCRIPTIONS_DIR / f"{db_name}.txt"
            out_file.write_text(response.strip(), encoding="utf-8")
            print(f"    [step 4/4] Description saved to {out_file.name}")
            print(f"DONE: Total time {time.time() - start_time:.2f}s")
            return True
        
        print(f"    [!] Failed: Empty response from model.")
        return False
        
    except Exception as exc:
        print(f"    [CRITICAL] Error processing {db_name}: {exc}")
        return False

def main() -> None:
    parser = argparse.ArgumentParser(description="JSON-based DB Description Generator")
    parser.add_argument("--model-path", type=str, default=None)
    args = parser.parse_args()

    print("--- STARTING WORKFLOW (Semantic Evidence Mode) ---")
    
    try:
        prompt_template = load_external_template()
        print(f"[main] System prompt template loaded.")
    except Exception as e:
        print(f"[main] ABORTED: {e}")
        return

    evidence_dir = DEFAULT_SETTINGS["evidence_dir"]
    if not evidence_dir.exists():
        print(f"[main] ABORTED: Evidence directory not found at {evidence_dir}")
        return

    # Trova tutti i file JSON (escluso il manifest)
    json_files = sorted(f for f in evidence_dir.glob("*.json") if f.stem.lower() != "manifest")
    db_names = [f.stem for f in json_files]
    
    print(f"[main] Found {len(db_names)} databases to describe.")

    for index, db_name in enumerate(db_names, start=1):
        process_database(db_name, prompt_template, index, len(db_names), model_path=args.model_path)

    print("\n--- WORKFLOW FINISHED ---")

if __name__ == "__main__":
    main()