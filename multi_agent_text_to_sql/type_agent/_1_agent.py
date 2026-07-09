from __future__ import annotations

import json
from pathlib import Path


INPUT_PATH = "path/to/dataset.json" 


OUTPUT_PROMPTS_BY_ID_PATH = Path(__file__).resolve().parent / "_1_generated_prompts_by_id.json"

DEFAULT_AVAILABLE_DATA_TYPES = ["INTEGER", "REAL", "TEXT", "DATE", "DATETIME"]


GENERAL_TYPE_SELECTOR_PROMPT = """
You are a Text-to-SQL analysis agent.

Task:
Analyze the user question (natural language) and select only the database data types that are necessary to answer it.

Important constraints:
1. You do NOT need to generate SQL.
2. You must choose types only from the provided available data types.
3. Do not invent new data types.
4. The output MUST be valid JSON.
5. Output ONLY one JSON object and nothing else.
6. Output must contain ONLY this field: "types_to_use".
7. "types_to_use" must be a list of strings.
8. Every string in "types_to_use" must exactly match one element in available_data_types.
9. If no type is clearly required, return an empty list.

Return format (strict JSON, no extra text):
The JSON below is ONLY an example of the required structure.
Do NOT copy the same values blindly; infer types from the input question.
{{
	"types_to_use": ["TEXT", "INTEGER"]
}}

Inputs:
- db_id: {db_id}
- question: {question}
- available_data_types: {available_data_types}
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


def build_datatype_selection_prompt(
	question: str,
	db_id: str,
	available_data_types: list[str],
) -> str:
	"""
	Costruisce il prompt per la singola chiamata al modello che seleziona
	i datatype necessari a rispondere alla question.
	"""
	sorted_types = sorted({str(t).upper().strip() for t in available_data_types if str(t).strip()})
	return GENERAL_TYPE_SELECTOR_PROMPT.format(
		db_id=db_id,
		question=question,
		available_data_types=", ".join(sorted_types),
	)


def generate_prompts_by_id(
	inputs: list[dict[str, str]],
	available_data_types: list[str] | None = None,
) -> list[dict[str, str]]:
	"""Genera una lista di record con question_id, db_id e prompt."""
	types = available_data_types or DEFAULT_AVAILABLE_DATA_TYPES
	prompt_records: list[dict[str, str]] = []
	for item in inputs:
		request_id = item["_id"]
		prompt_text = build_datatype_selection_prompt(
			question=item["question"],
			db_id=item["db-id"],
			available_data_types=types,
		)
		prompt_records.append(
			{
				"question_id": request_id,
				"db_id": item["db-id"],
				"prompt": prompt_text,
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

	prompts_by_id = generate_prompts_by_id(inputs, DEFAULT_AVAILABLE_DATA_TYPES)
	save_prompts_by_id(OUTPUT_PROMPTS_BY_ID_PATH, prompts_by_id)
	print(f"\nFile JSON salvato: {OUTPUT_PROMPTS_BY_ID_PATH}")

	if prompts_by_id:
		first_item = prompts_by_id[0]
		print(f"\n--- Prompt esempio (id={first_item['question_id']}) ---\n")
		print(first_item["prompt"])
