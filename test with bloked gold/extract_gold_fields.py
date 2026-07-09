"""Extract question id, question text, gold_result, and gold_error from an evaluation JSON.

The source file is expected to be a JSON array of objects like the one in
gold/evaluation_results_sql_speedlamatype.json.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_INPUT = "base.json"
DEFAULT_OUTPUT = "gold_only.json"


def extract_gold_fields(input_path: Path) -> list[dict[str, object]]:
    with input_path.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)

    if not isinstance(rows, list):
        raise ValueError("The input JSON must be a list of records.")

    extracted: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        extracted.append(
            {
                "question_id": row.get("question_id"),
                "question": row.get("question"),
                "gold_result": row.get("gold_result"),
                "gold_error": row.get("gold_error"),
            }
        )

    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract question_id, question, gold_result, and gold_error from an evaluation JSON file."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the source JSON file")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the output JSON file",
    )
    args = parser.parse_args()

    extracted = extract_gold_fields(args.input)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(extracted, handle, ensure_ascii=False, indent=2)

    print(f"Wrote {len(extracted)} records to {args.output}")


if __name__ == "__main__":
    main()