from __future__ import annotations

import json
from pathlib import Path
from tqdm import tqdm
from _0_semantic_templete import get_entities_by_database

'''
THis script processes the original dataset to create a new JSON file where each entry contains:
- question_id: the unique identifier of the question
- db_id: the database identifier associated with the question
- prompt: a generated prompt that instructs a semantic analysis agent to select relevant semantic concepts from

This result is used from the agent that will analyze the question and select the relevant semantic concepts to be used in the subsequent SQL generation step.
'''

INPUT_PATH = "path/to/dataset.json" 

GRAPH_FILE_PATH = Path("grafo.ttl")

# Input da step precedente (output di _2_run_agent_prompts.py)
PREVIOUS_AGENT_OUTPUT_PATH = Path("_2_vllm_semantic_agent_selection_outputs_Qwen3.5-9B_batch_0_None_20260628_110557.json")

OUTPUT_PROMPTS_BY_ID_PATH = Path(__file__).resolve().parent / "_2.1_generated_semantic_prompts_by_id.json"

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
You are a Text-to-SQL semantic analysis agent.

Task:
Analyze the user question (natural language) and select only the semantic concepts that are necessary to answer it.

Important constraints:
1. You do NOT need to generate SQL.
2. You must choose concepts only from the provided available_semantic_concepts.
3. Do not invent new concepts.
4. The output MUST be valid JSON.
5. Output ONLY one JSON object and nothing else.
6. Output must contain ONLY this field: "concepts_to_use".
7. "concepts_to_use" must be a list of strings.
8. Every string in "concepts_to_use" must exactly match one element in available_semantic_concepts.
9. If no concept is clearly required, return an empty list.

Return format (strict JSON, no extra text):
The JSON below is ONLY an example of the required structure.
Do NOT copy the same values blindly; infer concepts from the input question.
{{
	"concepts_to_use": ["person_name", "address"]
}}

Inputs:
- db_id: {db_id}
- question: {question}
- available_semantic_concepts: {available_semantic_concepts}
- concept_descriptions: {concept_descriptions}
""".strip()

_AVAILABLE_CONCEPTS_CACHE: dict[str, list[str]] = {}
def available_concepts_from_graph(database_name: str) -> list[str]:
	if database_name in _AVAILABLE_CONCEPTS_CACHE:
		return list(_AVAILABLE_CONCEPTS_CACHE[database_name])

	if not GRAPH_FILE_PATH.exists():
		_AVAILABLE_CONCEPTS_CACHE[database_name] = []
		return []

	rows = get_entities_by_database(ttl_file_path=GRAPH_FILE_PATH, db_name=database_name)
	concepts: list[str] = []
	seen: set[str] = set()

	for row in rows:
		concept = _concept_name_from_id(row.get("label", ""))
		if concept and concept not in seen:
			concepts.append(concept)
			seen.add(concept)

	_AVAILABLE_CONCEPTS_CACHE[database_name] = concepts
	return list(concepts)

# def get_concepts_by_database(graph_file: str | Path, database_name: str) -> list[dict]:
# 	"""Return all entities linked to a database in the RDF graph."""

# 	graph = Graph()
# 	graph.parse(str(graph_file), format="turtle")

# 	sparql_query = f"""
# 	PREFIX ex: <http://example.org/>
# 	PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# 	SELECT ?entity ?label ?comment
# 	WHERE {{
# 		?entity a ex:Entity .
# 		FILTER(STRSTARTS(STR(?entity), "http://example.org/resource/entity/{database_name}/"))
# 		?entity rdfs:label ?label .
# 		OPTIONAL {{ ?entity rdfs:comment ?comment . }}
# 	}}
# 	ORDER BY ?label
# 	"""

# 	results: list[dict] = []
# 	for row in graph.query(sparql_query):
# 		results.append(
# 			{
# 				"entity_id": str(row[0]),
# 				"label": str(row[1]),
# 				"comment": str(row[2]) if row[2] else None,
# 			}
# 		)

# 	return results


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
	concept_descriptions: list[dict[str, str]] | None = None,
) -> str:
	"""
	Costruisce il prompt per la singola chiamata al modello che seleziona
	i concetti semantici necessari a rispondere alla question.
	"""
	cleaned_concepts = sorted(
		{str(concept).strip() for concept in available_semantic_concepts if str(concept).strip()}
	)
	description_map = {
		str(item.get("concept", "")).strip(): str(item.get("description", "")).strip()
		for item in (concept_descriptions or [])
	}
	descriptions_payload = [
		{
			"concept": concept,
			"description": description_map.get(concept, "No description available."),
		}
		for concept in cleaned_concepts
	]
	return GENERAL_SEMANTIC_SELECTOR_PROMPT.format(
		db_id=db_id,
		question=question,
		available_semantic_concepts=", ".join(cleaned_concepts),
		concept_descriptions=json.dumps(descriptions_payload, ensure_ascii=False),
	)


def _concept_name_from_id(entity_id: str) -> str:
	"""Extract canonical entity name from a URI-like entity_id."""
	value = str(entity_id or "").strip()
	if not value:
		return ""
	return value.rsplit("/", 1)[-1].strip()


# Global cache for entities to avoid reloading the same database multiple times
_ENTITIES_CACHE: dict[str, list[dict]] = {}

# Cache per concetti selezionati dal precedente agent
_PREVIOUS_SELECTED_CONCEPTS_CACHE: dict[str, list[str]] = {}


def load_previous_agent_output(input_file: Path | str = PREVIOUS_AGENT_OUTPUT_PATH) -> dict[str, list[str]]:
	"""
	Carica i risultati dall'output del precedente agent e estrae i concetti selezionati.
	Ritorna un dizionario: {question_id: [list di concetti selezionati]}
	`input_file` può essere il nome del file (nella stessa cartella dello script)
	o un percorso; in caso di solo nome cerchiamo nella cartella dello script.
	"""

	# Accept either a Path or a filename string. Always look in the script folder.
	input_path = Path(input_file) if not isinstance(input_file, Path) else input_file
	script_dir = Path(__file__).resolve().parent
	file_path = script_dir / input_path.name
	print(f"🔍 Carico file precedente: '{file_path}'")
	if not file_path.exists():
		print(f"⚠️  File '{file_path}' non trovato.")
		return {}

	try:
		with file_path.open("r", encoding="utf-8") as f:
			payload = json.load(f)
	except Exception as e:
		print(f"⚠️  Errore nel caricamento del file precedente '{file_path}': {e}")
		return {}
	
	results = payload.get("results", [])
	selected_concepts: dict[str, list[str]] = {}
	print(f"Caricato output precedente da '{input_file}' con {len(results)} risultati")
	
	for item in results:
		question_id = item.get("question_id")
		cleaned_response = item.get("cleaned_response_json", {})
		concepts_list = cleaned_response.get("concepts_to_use", [])
		
		if question_id is not None:
			selected_concepts[str(question_id)] = [str(c).strip() for c in concepts_list]
	
	return selected_concepts


def available_concept_descriptions_from_graph(
	database_name: str,
	graph_file: Path = GRAPH_FILE_PATH,
) -> list[dict[str, str]]:
	"""Load concept names plus descriptions from cached graph results."""
	# Use cache to avoid reloading entities for the same database
	if database_name not in _ENTITIES_CACHE:
		_ENTITIES_CACHE[database_name] = get_entities_by_database(ttl_file_path=graph_file, db_name=database_name)
	
	concept_rows = _ENTITIES_CACHE[database_name]
	concept_descriptions: list[dict[str, str]] = []
	seen: set[str] = set()

	for row in concept_rows:
		concept_name = str(row.get("label")).strip()
		if not concept_name or concept_name in seen:
			continue
		concept_descriptions.append(
			{
				"concept": concept_name,
				"description": str(row.get("comment") or "No description available."),
			}
		)
		seen.add(concept_name)

	return concept_descriptions


def generate_prompts_by_id(
	inputs: list[dict[str, str]],
	available_semantic_concepts_default: list[str] | None = None,
	previous_selected_concepts: dict[str, list[str]] | None = None,
	) -> tuple[list[dict[str, str]], int]:
	"""
	Genera una lista di record con question_id, db_id e prompt semantico.
	Se previous_selected_concepts è fornito, filtra i concetti disponibili
	solo su quelli precedentemente selezionati dal modello.
	"""
	prompt_records: list[dict[str, str]] = []
	ignored_questions = 0
	ignore_ids: set[str] = set()
	previous_concepts = previous_selected_concepts or {}
	print(f"Concetti selezionati in precedenza per {len(previous_concepts)} domande")
	
	for item in tqdm(inputs, desc="Generating prompts", unit="prompt"):
		request_id = item["_id"]
		db_id = item["db-id"]

		if request_id in previous_concepts and not previous_concepts[request_id]:
			ignored_questions += 1
			#print(f"  ℹ️  Question {request_id}: ignorata perché il concept to use precedente è vuoto")
			ignore_ids.add(request_id)
			continue

		available_semantic_concepts_for_db = available_concepts_from_graph(db_id)
		concept_descriptions_for_db = available_concept_descriptions_from_graph(db_id)
		
		if available_semantic_concepts_for_db:
			concepts = available_semantic_concepts_for_db
		else:
			print(f"⚠️  Nessun semantic concept trovato nel grafo per db_id '{db_id}'. Usando concetti di default.")
			concepts = available_semantic_concepts_default or DEFAULT_AVAILABLE_SEMANTIC_CONCEPTS
		
		# Filtra i concetti basandosi su quelli precedentemente selezionati
		if request_id in previous_concepts and previous_concepts[request_id]:
			previously_selected = set(previous_concepts[request_id])
			concepts = [c for c in concepts if c in previously_selected]
			if concepts:
				#print(f"  ℹ️  Question {request_id}: filtrati {len(previous_concepts[request_id])} concetti dal precedente step")
				pass
			else:
				# Se il filtro toglie tutti i concetti, usa quelli precedentemente selezionati
				concepts = list(previous_concepts[request_id])
				#print(f"  ℹ️  Question {request_id}: usa {len(concepts)} concetti dal precedente step (nessuna corrispondenza nel grafo)")
		
		if not concept_descriptions_for_db:
			concept_descriptions_for_db = [
				{"concept": concept, "description": "No description available."} for concept in concepts
			]
		else:
			# Filtra le descrizioni solo per i concetti mantenuti
			concept_names = {c for c in concepts}
			concept_descriptions_for_db = [
				d for d in concept_descriptions_for_db 
				if d.get("concept", "") in concept_names
			]

		if not concepts:
			ignored_questions += 1
			ignore_ids.add(request_id)
			#print(f"  ℹ️  Question {request_id}: ignorata perché non ci sono concept to use")
			continue
		
		prompt_text = build_semantic_concept_selection_prompt(
			question=item["question"],
			db_id=item["db-id"],
			available_semantic_concepts=concepts,
			concept_descriptions=concept_descriptions_for_db,
		)
		prompt_records.append(
			{
				"question_id": request_id,
				"db_id": item["db-id"],
				"prompt": prompt_text,
				"available_concepts": concepts,
			}
		)
	return prompt_records, ignored_questions, ignore_ids


def save_prompts_by_id(output_path: Path, prompts_by_id: list[dict[str, str]]) -> None:
	"""Salva su file JSON la lista di record prompt."""
	with output_path.open("w", encoding="utf-8") as f:
		json.dump(prompts_by_id, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
	# Carica i risultati dal precedente step (se disponibili)
	previous_selected = load_previous_agent_output()
	if previous_selected:
		print(f"✓ Caricati risultati precedenti con {len(previous_selected)} domande elaborate")
	else:
		print("ℹ️  Nessun risultato precedente trovato. Userò tutti i concetti disponibili.")
	
	inputs = load_agent_inputs()
	print(f"Totale richieste valide: {len(inputs)}")


	prompts_by_id, ignored_questions, ignore_ids = generate_prompts_by_id(inputs, DEFAULT_AVAILABLE_SEMANTIC_CONCEPTS, previous_selected)
	save_prompts_by_id(OUTPUT_PROMPTS_BY_ID_PATH, prompts_by_id)
	print(f"\nFile JSON salvato: {OUTPUT_PROMPTS_BY_ID_PATH}")
	#le domande ignorate sono quelle il cui campo cleaned_response_json del precedente step aveva "concepts_to_use" vuoto, oppure quelle per cui non sono stati trovati concetti disponibili (né nel grafo né nei default)
	print(f"Domande ignorate : {ignored_questions}")
	print(f"ID domande ignorate: {ignore_ids}")
