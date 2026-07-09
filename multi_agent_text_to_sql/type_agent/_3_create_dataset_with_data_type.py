from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _0_templete_sparql import query_columns_by_type_sparql


INPUT_DATASET_PATH = Path(__file__).resolve().parent / "_2_vllm_type_selection_agent_outputs.json"
OUTPUT_DATASET_PATH = Path(__file__).resolve().parent / "_3_dataset_with_sparql_types.json"


def _load_entries(input_path: Path) -> list[dict[str, Any]]:
	with input_path.open("r", encoding="utf-8") as f:
		payload = json.load(f)

	if isinstance(payload, dict) and isinstance(payload.get("results"), list):
		return [item for item in payload["results"] if isinstance(item, dict)]

	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, dict)]

	raise ValueError("Formato input non valido: atteso list[...] o {'results': [...]}.")


def _extract_types(entry: dict[str, Any]) -> list[str]:
	cleaned = entry.get("cleaned_response_json")
	if isinstance(cleaned, dict) and isinstance(cleaned.get("types_to_use"), list):
		return [str(t).upper().strip() for t in cleaned["types_to_use"] if str(t).strip()]

	raw = entry.get("response_json")
	if isinstance(raw, dict) and isinstance(raw.get("types_to_use"), list):
		return [str(t).upper().strip() for t in raw["types_to_use"] if str(t).strip()]

	return []


def _format_columns_by_type(
	types_to_use: list[str],
	columns_by_type: dict[str, list[tuple[str, str, str]]],
	errors_by_type: dict[str, str],
) -> str:
	lines: list[str] = []
	for data_type in types_to_use:
		error = errors_by_type.get(data_type)
		if error:
			lines.append(f"{data_type}: [ERROR] {error}")
			continue

		rows = columns_by_type.get(data_type, [])
		if not rows:
			lines.append(f"{data_type}: -")
			continue

		columns = ", ".join(f"{table_name}.{column_name}" for table_name, column_name, _ in rows)
		lines.append(f"{data_type}: {columns}")

	return "\n".join(lines)


def build_dataset_with_sparql_types(input_path: Path, output_path: Path) -> None:
	entries = _load_entries(input_path)
	enriched: list[dict[str, Any]] = []

	for entry in entries:
		db_id = str(entry.get("db_id", "")).strip()
		types_to_use = _extract_types(entry)

		sparql_columns_by_type: dict[str, list[tuple[str, str, str]]] = {}
		sparql_errors_by_type: dict[str, str] = {}

		for data_type in types_to_use:
			try:
				rows = query_columns_by_type_sparql(db_id, data_type)
				sparql_columns_by_type[data_type] = rows
			except Exception as exc:
				sparql_errors_by_type[data_type] = str(exc)

		enriched_entry = {
			k: v
			for k, v in entry.items()
			if k not in {"response", "response_json", "cleaned_response_json"}
		}
		enriched_entry["types_to_use"] = types_to_use
		enriched_entry["columns_by_type"] = _format_columns_by_type(
			types_to_use,
			sparql_columns_by_type,
			sparql_errors_by_type,
		)
		enriched.append(enriched_entry)

	with output_path.open("w", encoding="utf-8") as f:
		json.dump(enriched, f, ensure_ascii=False, indent=2)

	print(f"Input entries: {len(entries)}")
	print(f"Output entries: {len(enriched)}")
	print(f"Saved: {output_path}")


if __name__ == "__main__":
	build_dataset_with_sparql_types(INPUT_DATASET_PATH, OUTPUT_DATASET_PATH)
 