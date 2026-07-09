import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
TEXT_TO_SQL_ROOT = ROOT_DIR.parent
SCRIPT_DIR = ROOT_DIR / "script"
DEFAULT_EVIDENCE_DIR = TEXT_TO_SQL_ROOT / "graph_decoration" / "semantic_evidence"
DEFAULT_EXTRACTION_DIR = ROOT_DIR / "extraction_input"


def run_command(command: list[str]) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT_DIR)


def list_keywords(input_dir: Path) -> list[str]:
    return sorted(path.stem for path in input_dir.glob("*.json"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full local pipeline in sequence: build extraction input, then run extraction and schema induction."
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="Run the extraction phase only for one database name. If omitted with --all, runs for all generated inputs.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run extraction and schema induction for all JSON files in extraction_input.",
    )
    parser.add_argument(
        "--model",
        default="Qwen2.5-Coder-7B-Instruct",
        help="Logical model name used to label the run output.",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Local model path forwarded to graph_decoration/script/_0_generator.py.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.keyword and not args.all:
        raise ValueError("Pass --keyword <db_name> or use --all.")

    build_command = [
        sys.executable,
        str(SCRIPT_DIR / "build_extraction_json.py"),
        "--input-dir",
        str(DEFAULT_EVIDENCE_DIR),
        "--output-dir",
        str(DEFAULT_EXTRACTION_DIR),
    ]
    run_command(build_command)

    keywords = [args.keyword] if args.keyword else list_keywords(DEFAULT_EXTRACTION_DIR)
    if not keywords:
        raise FileNotFoundError("No extraction_input JSON files were found after preparation.")

    for keyword in keywords:
        extraction_command = [
            sys.executable,
            str(SCRIPT_DIR / "run_schema_induction.py"),
            "--keyword",
            keyword,
            "--model",
            args.model,
        ]
        if args.model_path:
            extraction_command.extend(["--model-path", args.model_path])

        run_command(extraction_command)


if __name__ == "__main__":
    main()
