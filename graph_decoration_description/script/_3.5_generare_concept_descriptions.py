import argparse
import json
import time
from pathlib import Path

from _0_generator import query_qwen_batch

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_AUTOKG_OUTPUT_DIR = SCRIPT_DIR / "auto_kg_output"
DEFAULT_DESCRIPTIONS_DIR = PROJECT_DIR / "descriptions"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "concept_comments"


def find_latest_extraction_files(input_dir: Path, target_db: str | None = None) -> dict[str, Path]:
    latest_files: dict[str, Path] = {}

    for path in input_dir.rglob("*.json"):
        if path.parent.name != "kg_extraction":
            continue

        db_name = path.parent.parent.name
        if target_db and db_name != target_db:
            continue

        current = latest_files.get(db_name)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            latest_files[db_name] = path

    if not latest_files:
        raise FileNotFoundError(
            f"No AutoKG kg_extraction JSON files found in '{input_dir}'."
        )

    return latest_files


def load_triples_from_extraction(extraction_path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    triples: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    db_name: str | None = None

    with extraction_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            row = json.loads(line)
            db_name = db_name or row.get("id")
            for triple in row.get("triple_extraction_dict", []):
                subject = str(triple.get("subject", "")).strip()
                relation = str(triple.get("relation", "")).strip()
                obj = str(triple.get("object", "")).strip()
                if not subject or not relation or not obj:
                    continue

                triple_tuple = (subject, relation, obj)
                if triple_tuple in seen:
                    continue
                seen.add(triple_tuple)
                triples.append(triple_tuple)

    if not db_name:
        raise ValueError(f"Unable to infer db id from extraction file: {extraction_path}")

    return db_name, triples


def resolve_description_file(descriptions_dir: Path, db_name: str) -> Path:
    candidates = [
        descriptions_dir / f"{db_name}.txt",
        descriptions_dir / f"{db_name}.semantic_evidence.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No description file found for '{db_name}' in '{descriptions_dir}'."
    )


def collect_concept_support(
    triples: list[tuple[str, str, str]],
    max_support_triples: int,
) -> dict[str, list[tuple[str, str, str]]]:
    support: dict[str, list[tuple[str, str, str]]] = {}

    for subject, relation, obj in triples:
        for concept in (subject, obj):
            support.setdefault(concept, [])
            if len(support[concept]) < max_support_triples:
                support[concept].append((subject, relation, obj))

    return dict(sorted(support.items(), key=lambda item: item[0].lower()))


def build_comment_prompt(
    db_name: str,
    db_description: str,
    concept: str,
    support_triples: list[tuple[str, str, str]],
) -> str:
    triple_lines = "\n".join(
        f"- ({subject}, {relation}, {obj})"
        for subject, relation, obj in support_triples
    )

    return f"""You are generating a concise semantic comment for a concept that will be stored in a knowledge graph.

Database:
{db_name}

Database description:
{db_description}

Target concept:
{concept}

Supporting triples:
{triple_lines}

Task:
- Write a short English comment describing the meaning of the target concept in the context of this database.
- Use the database description and the supporting triples as grounding evidence.
- Prefer a reusable semantic explanation, not a row-level description.
- If the concept is ambiguous, resolve it using only the provided context.

Constraints:
- Output plain text only.
- No markdown.
- No bullet points.
- Keep it between 1 and 3 sentences.
"""


def generate_concept_comments(
    db_name: str,
    db_description: str,
    concept_support: dict[str, list[tuple[str, str, str]]],
    model_path: str | None,
    max_new_tokens: int,
    temperature: float,
) -> list[dict]:
    concept_items = list(concept_support.items())
    records: list[dict] = []
    
    if not concept_items:
        return records

    # Genera tutti i prompt in anticipo
    prompts = []
    for concept, support_triples in concept_items:
        prompt = build_comment_prompt(
            db_name=db_name,
            db_description=db_description,
            concept=concept,
            support_triples=support_triples,
        )
        prompts.append(prompt)

    # Preparazione dei parametri per il batch
    query_kwargs = {
        "prompts": prompts,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
    }
    if model_path:
        query_kwargs["model_path"] = model_path

    # Chiamata unica batch
    print(f"    [info] Invio di {len(prompts)} prompt in batch al modello...")
    q_start = time.time()
    responses = query_qwen_batch(**query_kwargs)
    print(f"    [info] LLM batch response time: {time.time() - q_start:.2f}s")

    # Mappatura delle risposte indietro ai concetti
    for (concept, support_triples), response in zip(concept_items, responses):
        # Pulizia della risposta per rimuovere l'eventuale tag <think>
        raw_response = (response or "").strip()
        if "</think>" in raw_response:
            clean_response = raw_response.split("</think>", 1)[1].strip()
        else:
            clean_response = raw_response

        records.append(
            {
                "concept": concept,
                "comment": clean_response,
                "supporting_triples": [
                    {
                        "subject": subject,
                        "relation": relation,
                        "object": obj,
                    }
                    for subject, relation, obj in support_triples
                ],
            }
        )

    return records


def process_database(
    extraction_path: Path,
    descriptions_dir: Path,
    output_dir: Path,
    model_path: str | None,
    max_support_triples: int,
    max_new_tokens: int,
    temperature: float,
) -> Path:
    print(f"\n>>> Generating concept comments for DB: {extraction_path.parent.parent.name}")
    start_time = time.time()
    db_name, triples = load_triples_from_extraction(extraction_path)
    description_path = resolve_description_file(descriptions_dir, db_name)
    db_description = description_path.read_text(encoding="utf-8").strip()
    concept_support = collect_concept_support(
        triples=triples,
        max_support_triples=max_support_triples,
    )

    concept_records = generate_concept_comments(
        db_name=db_name,
        db_description=db_description,
        concept_support=concept_support,
        model_path=model_path,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{db_name}.concept_comments.json"
    payload = {
        "database_name": db_name,
        "source_description_file": str(description_path),
        "source_extraction_file": str(extraction_path),
        "concept_count": len(concept_records),
        "concepts": concept_records,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[comments] Wrote {output_path.name} with {len(concept_records)} concept comments."
    )
    print(f"[done] Total time: {time.time() - start_time:.2f}s")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate concept comments from AutoKG triples and DB descriptions."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_AUTOKG_OUTPUT_DIR,
        help="Root directory containing AutoKG outputs from _3_call_auto_kg.py",
    )
    parser.add_argument(
        "--descriptions-dir",
        type=Path,
        default=DEFAULT_DESCRIPTIONS_DIR,
        help="Directory containing DB descriptions from _2_generate_db_descriptions.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where generated concept comments will be written.",
    )
    parser.add_argument(
        "--db-name",
        default=None,
        help="Generate comments only for one DB.",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Optional local model path forwarded to _0_generator.",
    )
    parser.add_argument(
        "--max-support-triples",
        type=int,
        default=4,
        help="Maximum number of supporting triples kept per concept.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=8192,
        help="Maximum generation length for each concept comment.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature for comment generation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extraction_files = find_latest_extraction_files(args.input_dir, target_db=args.db_name)

    for _, extraction_path in sorted(extraction_files.items()):
        process_database(
            extraction_path=extraction_path,
            descriptions_dir=args.descriptions_dir,
            output_dir=args.output_dir,
            model_path=args.model_path,
            max_support_triples=args.max_support_triples,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
        )


if __name__ == "__main__":
    main()