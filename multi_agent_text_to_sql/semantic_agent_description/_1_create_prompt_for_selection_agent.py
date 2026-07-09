from __future__ import annotations

import json
from pathlib import Path
from tqdm import tqdm
from _0_semantic_templete import get_entities_by_database, concept_appears_as_semantic_meaning

'''
Questo script elabora il dataset originale per creare un nuovo file JSON in cui ogni voce contiene:
- question_id: l'identificatore univoco della domanda
- db_id: l'identificatore del database associato alla domanda
- prompt: un prompt generato che istruisce un agente di analisi semantica a selezionare i concetti semantici rilevanti.
'''

INPUT_PATH = "path/to/dataset.json" 

GRAPH_FILE_PATH = Path(__file__).resolve().parent / "grafo.ttl"

OUTPUT_PROMPTS_BY_ID_PATH = Path(__file__).resolve().parent / "_1_generated_semantic_selection_prompts_by_id.json"

DEFAULT_AVAILABLE_SEMANTIC_CONCEPTS = [
    "identifier",
    "foreign_identifier",
    "person_name",
    "person_first_name",
    "person_last_name",
    "organization_name",
    "school_name",
    "team_name",
    "event_name",
    "title",
    "description_text",
    "category",
    "status",
    "gender",
    "nationality",
    "country_name",
    "state_name",
    "city_name",
    "postal_code",
    "address",
    "email_address",
    "phone_number",
    "url",
    "date",
    "year",
    "month",
    "timestamp",
    "age",
    "quantity",
    "count",
    "percentage",
    "score",
    "rating",
    "rank",
    "duration",
    "monetary_amount",
    "latitude",
    "longitude",
    "boolean_flag",
    "code",
    "type_label",
    "unknown",
]

GENERAL_SEMANTIC_SELECTOR_PROMPT = """
You are a strict semantic concept selector for Text-to-SQL.

Return exactly one JSON object and nothing else.
The JSON must contain exactly one field: "concepts_to_use".
"concepts_to_use" must be a list of at most 8 strings.

Rules:
- Use only exact names from available_semantic_concepts.
- Select the most useful concepts for the query.
- Do not invent, rename, explain, or repeat concepts.
- If nothing fits, return an empty list.

Input question:
{question}

Available concepts:
{available_semantic_concepts}

Example:
{{
    "concepts_to_use": ["school_name", "state_name", "identifier", "county_name"]
}}

""".strip()


def load_agent_inputs(input_path: Path = INPUT_PATH) -> list[dict[str, str]]:
    """
    Carica le richieste dal dataset e restituisce solo i campi necessari all'agente:
    - _id
    - question
    - db-id
    """
    with input_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError("Il file input deve contenere una lista di elementi JSON.")

    requests: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        request_id = item.get("_id")
        question = item.get("question")
        db_id = item.get("db_id") or item.get("db-id")
        if not request_id or not question or not db_id:
            continue

        requests.append(
            {
                "_id": str(request_id),
                "question": str(question),
                "db-id": str(db_id),
            }
        )

    return requests


def build_semantic_concept_selection_prompt(
    question: str,
    db_id: str,
    available_semantic_concepts: list[str],
) -> str:
    """
    Costruisce il prompt per la singola chiamata al modello che seleziona
    i concetti semantici necessari a rispondere alla question.
    """
    cleaned_concepts = sorted(
        {str(concept).strip() for concept in available_semantic_concepts if str(concept).strip()}
    )
    available_block = json.dumps(cleaned_concepts, ensure_ascii=False)

    return GENERAL_SEMANTIC_SELECTOR_PROMPT.format(
        question=question,
        available_semantic_concepts=available_block,
    )


# Global cache for entities to avoid reloading the same database multiple times
_ENTITIES_CACHE: dict[str, list[str]] = {}

def available_concepts_from_graph(database_name: str, graph_file: Path = GRAPH_FILE_PATH) -> list[str]:
    """Load available concepts for one database using cached results."""
    if database_name not in _ENTITIES_CACHE:
        all_for_db = get_entities_by_database(ttl_file_path=graph_file, db_name=database_name)
        
        # Filtra subito prendendo solo quelli che appaiono come semantic meaning
        only_appearing_as_semantic_meaning = [
            row for row in all_for_db 
            if concept_appears_as_semantic_meaning(graph_file, database_name, row.get("label", ""))
        ]
        
        concept_names: list[str] = []
        seen: set[str] = set()

        for row in only_appearing_as_semantic_meaning:
            concept_name = row.get("label")
            if concept_name and concept_name not in seen:
                concept_names.append(concept_name)
                seen.add(concept_name)
                
        _ENTITIES_CACHE[database_name] = concept_names
    
    return _ENTITIES_CACHE[database_name]


def preload_all_databases_concepts(inputs: list[dict[str, str]], graph_file: Path = GRAPH_FILE_PATH) -> None:
    """Riempie la cache per tutti i database unici prima di generare i prompt."""
    unique_db_ids = {item["db-id"] for item in inputs}
    print("Pre-caricamento dei concetti semantici per i database...")
    for db_id in tqdm(unique_db_ids, desc="Caching DB concepts", unit="db"):
        # Chiamare la funzione la popolerà e la memorizzerà nella cache globale
        available_concepts_from_graph(db_id, graph_file)


def generate_prompts_by_id(
    inputs: list[dict[str, str]],
    available_semantic_concepts_default: list[str] | None = None,
) -> list[dict[str, str]]:
    """Genera una lista di record con question_id, db_id e prompt semantico usando la cache."""
    prompt_records: list[dict[str, str]] = []
    
    # Pre-riscalda la cache per tutti i database
    preload_all_databases_concepts(inputs)
    
    for item in tqdm(inputs, desc="Generating prompts", unit="prompt"):
        request_id = item["_id"]
        db_id = item["db-id"]
        
        # Visto che la cache è già piena, questa operazione sarà istantanea
        available_semantic_concepts_for_db = available_concepts_from_graph(db_id)
        
        if available_semantic_concepts_for_db:
            concepts = available_semantic_concepts_for_db
        else:
            print(f"⚠️ Nessun semantic concept trovato nel grafo per db_id '{db_id}'. Usando concetti di default.")
            concepts = available_semantic_concepts_default or DEFAULT_AVAILABLE_SEMANTIC_CONCEPTS
            
        prompt_text = build_semantic_concept_selection_prompt(
            question=item["question"],
            db_id=item["db-id"],
            available_semantic_concepts=concepts,
        )
        prompt_records.append(
            {
                "question_id": request_id,
                "db_id": item["db-id"],
                "prompt": prompt_text,
                "available_semantic_concepts": concepts,
            }
        )
    return prompt_records


def save_prompts_by_id(output_path: Path, prompts_by_id: list[dict[str, str]]) -> None:
    """Salva su file JSON la lista di record prompt."""
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(prompts_by_id, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    inputs = load_agent_inputs()
    print(f"Totale richieste valide: {len(inputs)}")
    print("Prime 3 richieste:")
    for row in inputs[:3]:
        print(row)

    prompts_by_id = generate_prompts_by_id(inputs, DEFAULT_AVAILABLE_SEMANTIC_CONCEPTS)
    save_prompts_by_id(OUTPUT_PROMPTS_BY_ID_PATH, prompts_by_id)
    print(f"\nFile JSON salvato: {OUTPUT_PROMPTS_BY_ID_PATH}")

    if prompts_by_id:
        first_item = prompts_by_id[0]
        print(f"\n--- Prompt esempio (id={first_item['question_id']}) ---\n")
        print(first_item["prompt"])