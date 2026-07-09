from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DATASET_PATH = "path/to/dataset.json" 
REFERENCE_DATASET_PATH = BASE_DIR / "_3_dataset_with_semantic_info.json"
OUTPUT_DATASET_PATH = BASE_DIR / "_4_source_dataset_with_columns_by_semantic_concept.json"

SOURCE_ID_FIELD = "_id"
REFERENCE_ID_FIELD = "question_id"
REFERENCE_VALUE_FIELD = "columns_by_semantic_concept"
OUTPUT_FIELD = "columns_by_semantic_concept"


'''
This script takes the original dataset (with the questions and their IDs) and adds to each question the columns associated to the semantic concepts identified by the vLLM agent, 
by matching the question IDs with those in the reference dataset (the output of the previous script).
'''

def _load_json_list(path: Path) -> list[dict[str, Any]]:
	with path.open("r", encoding="utf-8") as f:
		payload = json.load(f)

	if not isinstance(payload, list):
		raise ValueError(f"Il file {path} deve contenere una lista JSON.")

	items = [item for item in payload if isinstance(item, dict)]
	if len(items) != len(payload):
		raise ValueError(f"Il file {path} contiene elementi non-oggetto.")

	return items


def _build_lookup(
	reference_rows: list[dict[str, Any]],
	reference_id_field: str,
	reference_value_field: str,
) -> dict[str, Any]:
	lookup: dict[str, Any] = {}
	for row in reference_rows:
		if reference_id_field not in row:
			continue
		key = str(row[reference_id_field]).strip()
		if not key:
			continue
		lookup[key] = row.get(reference_value_field)
	return lookup


def _normalize_path(path_value: str | Path) -> Path:
	path = path_value if isinstance(path_value, Path) else Path(path_value)
	if path.is_absolute():
		return path
	return (BASE_DIR / path).resolve()


def add_field_by_id_match(
	source_path: str | Path,
	reference_path: str | Path,
	output_path: str | Path,
	source_id_field: str,
	reference_id_field: str,
	reference_value_field: str,
	output_field: str,
) -> None:
	source_path = _normalize_path(source_path)
	reference_path = _normalize_path(reference_path)
	output_path = _normalize_path(output_path)

	source_rows = _load_json_list(source_path)
	reference_rows = _load_json_list(reference_path)
	lookup = _build_lookup(reference_rows, reference_id_field, reference_value_field)

	matched = 0
	missing = 0
	missing_id=set()
	result: list[dict[str, Any]] = []

	for row in source_rows:
		new_row = dict(row)
		row_id = str(row.get(source_id_field, "")).strip()
		# If we have a match, use it; otherwise set an empty mapping so the
		# output always contains the expected field (no KeyError later).
		if row_id and row_id in lookup and lookup.get(row_id) is not None:
			new_row[output_field] = lookup[row_id]
			matched += 1
		else:
			new_row[output_field] = {}
			missing += 1
			missing_id.add(row_id)
		result.append(new_row)

	with output_path.open("w", encoding="utf-8") as f:
		json.dump(result, f, ensure_ascii=False, indent=2)

	print(f"Source rows: {len(source_rows)}")
	print(f"Reference rows: {len(reference_rows)}")
	print(f"Matched on '{source_id_field}' -> '{reference_id_field}': {matched}")
	print(f"Missing matches: {missing}")
	print(f"Missing IDs: {missing_id}")
	print(f"Saved copy: {output_path}")

	


if __name__ == "__main__":
	add_field_by_id_match(
		source_path=SOURCE_DATASET_PATH,
		reference_path=REFERENCE_DATASET_PATH,
		output_path=OUTPUT_DATASET_PATH,
		source_id_field=SOURCE_ID_FIELD,
		reference_id_field=REFERENCE_ID_FIELD,
		reference_value_field=REFERENCE_VALUE_FIELD,
		output_field=OUTPUT_FIELD,
	)
