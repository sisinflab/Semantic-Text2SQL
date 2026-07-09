from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rdflib import Graph
from _0_semantic_templete import get_entities_by_concept, get_columns_by_semantic_concept

'''
this script takes the output of the vLLM agent (with the identified semantic concepts) and enriches it with the columns associated to each concept,
by querying the SPARQL endpoint.
'''

INPUT_DATASET_PATH = Path("_2.2_vllm_semantic_agent_outputs_Qwen3.5-9B_20260628_112918.json")
OUTPUT_DATASET_PATH = Path(__file__).resolve().parent / "_3_dataset_with_semantic_info.json"
GRAPH_FILE_PATH = Path(__file__).resolve().parent / "grafo.ttl"

_GRAPH_CACHE: Graph | None = None
_CONCEPT_COLUMNS_CACHE: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
_CONCEPT_ERRORS_CACHE: dict[tuple[str, str], str] = {}


def _get_graph(graph_file: Path = GRAPH_FILE_PATH) -> Graph:
	global _GRAPH_CACHE
	if _GRAPH_CACHE is None:
		if not graph_file.exists():
			raise FileNotFoundError(f"Graph file not found: {graph_file}")
		graph = Graph()
		graph.parse(str(graph_file), format="turtle")
		_GRAPH_CACHE = graph
	return _GRAPH_CACHE


def _print_progress(current: int, total: int, width: int = 30) -> None:
	if total <= 0:
		return
	filled = int(width * current / total)
	bar = "#" * filled + "-" * (width - filled)
	percent = int((current / total) * 100)
	sys.stdout.write(f"\rProgress: [{bar}] {current}/{total} ({percent}%)")
	sys.stdout.flush()
	if current == total:
		sys.stdout.write("\n")
		sys.stdout.flush()


def _get_columns_for_concept(db_id: str, concept: str) -> list[tuple[str, str, str]]:
	cache_key = (db_id, concept)
	if cache_key in _CONCEPT_COLUMNS_CACHE:
		return _CONCEPT_COLUMNS_CACHE[cache_key]
	if cache_key in _CONCEPT_ERRORS_CACHE:
		raise RuntimeError(_CONCEPT_ERRORS_CACHE[cache_key])

	try:
		rows = get_columns_by_semantic_concept(GRAPH_FILE_PATH, db_id, concept)

		columns = [
			(row["table"], row["name"], row.get("semantic_comment") or "")
			for row in rows
		]
		# if cache_key == ('thrombosis_prediction', 'date'):
		# 	print(f"Debug SPARQL",rows)
		# 	# For debugging, we can choose to return an empty list or the actual columns
		# 	# return []  # Uncomment to return empty list for this specific case
		_CONCEPT_COLUMNS_CACHE[cache_key] = columns
		return columns
	except Exception as exc:
		err_msg = str(exc)
		_CONCEPT_ERRORS_CACHE[cache_key] = err_msg
		raise RuntimeError(err_msg)





def _load_entries(input_path: Path) -> list[dict[str, Any]]:
	with input_path.open("r", encoding="utf-8") as f:
		payload = json.load(f)

	if isinstance(payload, dict) and isinstance(payload.get("results"), list):
		return [item for item in payload["results"] if isinstance(item, dict)]

	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, dict)]

	raise ValueError("Formato input non valido: atteso list[...] o {'results': [...]}.")


def _extract_semantic_concepts(entry: dict[str, Any]) -> list[str]:
	def _normalize_list(value: Any) -> list[str]:
		if not isinstance(value, list):
			return []
		cleaned: list[str] = []
		seen: set[str] = set()
		for item in value:
			concept = str(item).strip()
			if concept and concept not in seen:
				cleaned.append(concept)
				seen.add(concept)
		return cleaned

	cleaned = entry.get("cleaned_response_json")
	if isinstance(cleaned, dict):
		concepts = _normalize_list(cleaned.get("concepts_to_use"))
		if concepts:
			return concepts

	return []


def _extract_concept_descriptions(entry: dict[str, Any]) -> dict[str, str]:
	def _normalize_text(value: Any) -> str:
		return str(value).strip()

	def _normalize_key(value: Any) -> str:
		return str(value).strip()

	descriptions: dict[str, str] = {}
	concept_descriptions = entry.get("concept_descriptions")
	if isinstance(concept_descriptions, list):
		for item in concept_descriptions:
			if not isinstance(item, dict):
				continue
			concept = _normalize_key(item.get("concept"))
			description = _normalize_text(item.get("description"))
			if concept and description:
				descriptions[concept] = description

	cleaned = entry.get("cleaned_response_json")
	if isinstance(cleaned, dict):
		fallback_descriptions = cleaned.get("concept_descriptions")
		if isinstance(fallback_descriptions, list):
			for item in fallback_descriptions:
				if not isinstance(item, dict):
					continue
				concept = _normalize_key(item.get("concept"))
				description = _normalize_text(item.get("description"))
				if concept and description and concept not in descriptions:
					descriptions[concept] = description

	return descriptions


def _format_columns_by_semantic_concept(
	concepts_to_use: list[str],
	columns_by_concept: dict[str, list[tuple[str, str, str]]],
	errors_by_concept: dict[str, str],
	concept_descriptions: dict[str, str],
) -> str:
	blocks: list[str] = []
	for concept in concepts_to_use:
		error = errors_by_concept.get(concept)
		if error:
			blocks.append(f"{concept}\n[ERROR] {error}")
			continue

		rows = columns_by_concept.get(concept, [])
		formatted_columns: list[str] = []
		seen_columns: set[str] = set()
		semantic_comment = ""
		for row in rows:
			table_name, column_name = row[0], row[1]
			comment = row[2] if len(row) > 2 else ""
			column_ref = f"{table_name}.{column_name}"
			if column_ref not in seen_columns:
				formatted_columns.append(column_ref)
				seen_columns.add(column_ref)
			if not semantic_comment and comment:
				semantic_comment = comment

		description = concept_descriptions.get(concept, semantic_comment) or "-"
		columns = ", ".join(formatted_columns) if formatted_columns else "-"
		blocks.append(f"{concept}\n{description}\n'Colums:'{columns}")

	return "\n\n".join(blocks)


def build_dataset_with_semantic_info(input_path: Path, output_path: Path) -> None:
	entries = _load_entries(input_path)
	enriched: list[dict[str, Any]] = []
	total_entries = len(entries)

	for idx, entry in enumerate(entries, start=1):
		question_id = entry.get("question_id")
		db_id = str(entry.get("db_id", "")).strip()
		concepts_to_use = _extract_semantic_concepts(entry)
		concept_descriptions = _extract_concept_descriptions(entry)

		sparql_columns_by_concept: dict[str, list[tuple[str, str, str]]] = {}
		sparql_errors_by_concept: dict[str, str] = {}

		for concept in concepts_to_use:
			try:
				sparql_columns_by_concept[concept] = _get_columns_for_concept(db_id, concept)
			except Exception as exc:
				sparql_errors_by_concept[concept] = str(exc)

		if question_id == "1167":
			print(f"Debug question_id={question_id}, db_id={db_id}")
			print(f"Concepts to use: {concepts_to_use}")
			print(f"Concept descriptions: {concept_descriptions}")
			print(f"SPARQL columns by concept: {sparql_columns_by_concept}")
			print(f"SPARQL errors by concept: {sparql_errors_by_concept}")

			# For debugging, we can choose to skip saving this entry or include the error info
			# continue  # Uncomment to skip saving this entry
		enriched_entry = {
			k: v
			for k, v in entry.items()
			if k not in {"response", "response_json", "cleaned_response_json"}
		}
		enriched_entry["concepts_to_use"] = concepts_to_use
		enriched_entry["columns_by_semantic_concept"] = _format_columns_by_semantic_concept(
			concepts_to_use,
			sparql_columns_by_concept,
			sparql_errors_by_concept,
			concept_descriptions,
		)
		enriched.append(enriched_entry)
		_print_progress(idx, total_entries)

	with output_path.open("w", encoding="utf-8") as f:
		json.dump(enriched, f, ensure_ascii=False, indent=2)

	print(f"Input entries: {len(entries)}")
	print(f"Output entries: {len(enriched)}")
	print(f"Cache hits (columns): {len(_CONCEPT_COLUMNS_CACHE)} unique (db_id, concept)")
	print(f"Cache errors: {len(_CONCEPT_ERRORS_CACHE)} unique (db_id, concept)")
	print(f"Saved: {output_path}")



if __name__ == "__main__":
	build_dataset_with_semantic_info(INPUT_DATASET_PATH, OUTPUT_DATASET_PATH)

