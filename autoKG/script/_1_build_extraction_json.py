import argparse
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
TEXT_TO_SQL_ROOT = ROOT_DIR.parent
DEFAULT_INPUT_DIR = TEXT_TO_SQL_ROOT / "graph_decoration" / "semantic_evidence"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "extraction_input"


def build_records(evidence_path: Path) -> list[dict]:
    with evidence_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    database_name = payload["database_name"]
    records = []

    for table in payload.get("tables", []):
        for column in table.get("columns", []):
            description = column.get("metadata", {}).get("description")
            if not description:
                continue

            records.append(
                {
                    "id": database_name,
                    "text": description,
                    "metadata": {"lang": "en"},
                }
            )

    return records


def convert_directory(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_files = sorted(input_dir.glob("*.semantic_evidence.json"))
    if not evidence_files:
        raise FileNotFoundError(
            f"No semantic evidence files found in '{input_dir}'."
        )

    for evidence_file in evidence_files:
        records = build_records(evidence_file)
        database_name = evidence_file.name.replace(".semantic_evidence.json", "")
        output_path = output_dir / f"{database_name}.json"

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2, ensure_ascii=False)

        print(
            f"Wrote {len(records)} records from '{evidence_file.name}' "
            f"to '{output_path.name}'"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert semantic evidence JSON files into extraction input JSON files."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing *.semantic_evidence.json files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where extraction-ready JSON files will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    convert_directory(input_dir, output_dir)


if __name__ == "__main__":
    main()
