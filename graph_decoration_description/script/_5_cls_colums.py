"""Classify database columns using the per-database prompt files and semantic evidence."""

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from _0_build_prompts import format_semantic_prompt
from _0_generator import query_qwen_batch


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

DEFAULT_EVIDENCE_MANIFEST_PATH = PROJECT_DIR / "semantic_evidence" / "manifest.json"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "semantic_annotations_cls.json"

# Fixed filters: set to None to disable each filter.
FIXED_DATABASE_FILTER = None
FIXED_TABLE_FILTER = None
FIXED_COLUMN_FILTER = None
FIXED_LIMIT = None
FIXED_MAX_NEW_TOKENS = 1024
FIXED_TEMPERATURE = 0.0
# Set to None to run everything in a single batch at the end.
FIXED_BATCH_SIZE = None


def load_json(path: Path):
	return json.loads(path.read_text(encoding="utf-8"))


def resolve_manifest_entry_path(manifest_path: Path, raw_path: str | Path) -> Path:
	candidate = Path(raw_path)
	if candidate.is_absolute():
		return candidate
	return (manifest_path.parent / candidate).resolve()


def compact_column_evidence(column: dict) -> dict:
	value_evidence = column.get("value_evidence", {})
	metadata = column.get("metadata", {})

	return {
		"database_name": column["database_name"],
		"table_name": column["table_name"],
		"column_name": column["column_name"],
		"sqlite_declared_type": column.get("sqlite_declared_type"),
		"is_primary_key": column.get("is_primary_key"),
		"is_not_null": column.get("is_not_null"),
		"is_foreign_key": column.get("is_foreign_key"),
		"foreign_key_target": column.get("foreign_key_target"),
		"metadata": {
			"description": metadata.get("description"),
			"synonym": metadata.get("synonym"),
			"value_description": metadata.get("value_description"),
		},
		"sample_values": value_evidence.get("sample_values", [])[:5],
	}


def iter_columns_from_manifest(
	manifest_path: Path,
	database_filter: str | None = None,
	table_filter: str | None = None,
	column_filter: str | None = None,
) -> Iterable[dict]:
	manifest_path = manifest_path.resolve()
	manifest = load_json(manifest_path)

	for entry in manifest:
		database_name = entry["database_name"]
		if database_filter and database_name != database_filter:
			continue

		evidence_path = resolve_manifest_entry_path(manifest_path, entry["evidence_path"])
		evidence = load_json(evidence_path)
		for table in evidence.get("tables", []):
			table_name = table["table_name"]
			if table_filter and table_name != table_filter:
				continue

			for column in table.get("columns", []):
				if column_filter and column["column_name"] != column_filter:
					continue
				yield compact_column_evidence(column)


def extract_json_object(raw_response: str) -> dict:
	text = (raw_response or "").strip()
	if not text:
		raise ValueError("Empty model response")

	try:
		parsed = json.loads(text)
		if isinstance(parsed, dict):
			return parsed
		if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
			return parsed[0]
	except json.JSONDecodeError:
		pass

	fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
	for block in fenced_blocks:
		try:
			parsed = json.loads(block)
			if isinstance(parsed, dict):
				return parsed
			if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
				return parsed[0]
		except json.JSONDecodeError:
			continue

	object_start = text.find("{")
	object_end = text.rfind("}")
	if object_start != -1 and object_end != -1 and object_end > object_start:
		candidate = text[object_start:object_end + 1]
		parsed = json.loads(candidate)
		if isinstance(parsed, dict):
			return parsed
		if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
			return parsed[0]

	array_start = text.find("[")
	array_end = text.rfind("]")
	if array_start != -1 and array_end != -1 and array_end > array_start:
		candidate = text[array_start:array_end + 1]
		parsed = json.loads(candidate)
		if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
			return parsed[0]

	raise ValueError("Model response does not contain a parseable JSON object")


def normalize_annotation(annotation: dict, column_evidence: dict) -> dict:
	return {
		"database_name": annotation.get("database_name") or column_evidence["database_name"],
		"table_name": annotation.get("table_name") or column_evidence["table_name"],
		"column_name": annotation.get("column_name") or column_evidence["column_name"],
		"semantic_concept_id": annotation.get("semantic_concept_id"),
	}


def write_json(path: Path, records: list[dict]) -> None:
	path.write_text(json.dumps(records, ensure_ascii=True, indent=2), encoding="utf-8")


def process_batch(
	batch_columns: list[dict],
	batch_prompts: list[str],
	model_path: str | None,
) -> list[dict]:
	query_kwargs = {
		"prompts": batch_prompts,
		"max_new_tokens": FIXED_MAX_NEW_TOKENS,
		"temperature": FIXED_TEMPERATURE,
	}
	if model_path:
		query_kwargs["model_path"] = model_path

	raw_responses = query_qwen_batch(**query_kwargs)

	print(f"raw_responses: {raw_responses}")

	batch_annotations: list[dict] = []
	for column_evidence, raw_response in zip(batch_columns, raw_responses):
		try:
			annotation = extract_json_object(raw_response)
		except (ValueError, json.JSONDecodeError, TypeError) as exc:
			annotation = {}
			column_key = (
				f"{column_evidence['database_name']}."
				f"{column_evidence['table_name']}."
				f"{column_evidence['column_name']}"
			)
			raw_preview = (raw_response or "").strip().replace("\n", " ")
			if len(raw_preview) > 200:
				raw_preview = raw_preview[:200] + "..."
			print(
				f"Warning: could not parse annotation for {column_key}: {exc}. "
				f"Raw response preview: {raw_preview}"
			)
		batch_annotations.append(normalize_annotation(annotation, column_evidence))
	return batch_annotations


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Iterate over column evidence, build semantic prompts from per-database prompt files, query Qwen, and save semantic annotations."
	)
	parser.add_argument(
		"--manifest",
		type=Path,
		default=DEFAULT_EVIDENCE_MANIFEST_PATH,
		help="Path to the semantic evidence manifest",
	)
	parser.add_argument("--model-path", type=str, default=None)
	args = parser.parse_args()

	output_path = Path(DEFAULT_OUTPUT_PATH)
	output_path.parent.mkdir(parents=True, exist_ok=True)

	annotation_records: list[dict] = []
	batch_columns: list[dict] = []
	batch_prompts: list[str] = []

	processed_count = 0
	for column_evidence in iter_columns_from_manifest(
		manifest_path=args.manifest,
		database_filter=FIXED_DATABASE_FILTER,
		table_filter=FIXED_TABLE_FILTER,
		column_filter=FIXED_COLUMN_FILTER,
	):
		if FIXED_LIMIT is not None and processed_count >= FIXED_LIMIT:
			break

		prompt = format_semantic_prompt(column_evidence, column_evidence["database_name"])

		batch_columns.append(column_evidence)
		batch_prompts.append(prompt)

		if FIXED_BATCH_SIZE is not None and len(batch_prompts) >= FIXED_BATCH_SIZE:
			annotation_records.extend(
				process_batch(
					batch_columns=batch_columns,
					batch_prompts=batch_prompts,
					model_path=args.model_path,
				)
			)
			batch_columns = []
			batch_prompts = []

		processed_count += 1

	if batch_prompts:
		annotation_records.extend(
			process_batch(
				batch_columns=batch_columns,
				batch_prompts=batch_prompts,
				model_path=args.model_path,
			)
		)

	write_json(output_path, annotation_records)
	print(f"Saved {len(annotation_records)} semantic annotations to: {output_path}")


if __name__ == "__main__":
	main()