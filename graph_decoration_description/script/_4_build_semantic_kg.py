import argparse
import json
from pathlib import Path
from urllib.parse import quote


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

DEFAULT_AUTOKG_OUTPUT_DIR = SCRIPT_DIR / "auto_kg_output"
DEFAULT_GRAPH_OUTPUT_DIR = SCRIPT_DIR / "generated_graphs"
DEFAULT_DESCRIPTIONS_DIR = PROJECT_DIR / "descriptions"
DEFAULT_CONCEPT_COMMENTS_DIR = PROJECT_DIR / "concept_comments"
RESOURCE_BASE = "http://example.org/resource"
SCHEMA_BASE = "http://example.org/schema#"


PREFIXES = f"""@prefix ex: <{SCHEMA_BASE}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

"""


def q(value: str) -> str:
    return quote(value, safe="")


def esc_lit(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def central_uri(db_name: str) -> str:
    return f"<{RESOURCE_BASE}/db/{q(db_name)}>"


def entity_uri(db_name: str, value: str) -> str:
    return f"<{RESOURCE_BASE}/entity/{q(db_name)}/{q(value)}>"


def relation_uri(db_name: str, value: str) -> str:
    return f"<{RESOURCE_BASE}/relation/{q(db_name)}/{q(value)}>"


def triple_uri(db_name: str, index: int) -> str:
    return f"<{RESOURCE_BASE}/triple/{q(db_name)}/t{index}>"


def concept_uri(db_name: str, value: str) -> str:
    return f"<{RESOURCE_BASE}/concept/{q(db_name)}/{q(value)}>"


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

    print(f"[load] Reading triples from: {extraction_path}")

    with extraction_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            row = json.loads(line)
            db_name = db_name or row.get("id")
            triple_dicts = row.get("triple_extraction_dict", [])

            for triple in triple_dicts:
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

    print(f"[load] Loaded {len(triples)} unique triples for DB: {db_name}")

    return db_name, triples


def resolve_description_file(descriptions_dir: Path, db_name: str) -> Path | None:
    candidates = [
        descriptions_dir / f"{db_name}.txt",
        descriptions_dir / f"{db_name}.semantic_evidence.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_database_description(descriptions_dir: Path, db_name: str) -> str | None:
    description_path = resolve_description_file(descriptions_dir, db_name)
    if description_path is None:
        print(f"[desc] No description file found for DB: {db_name} in {descriptions_dir}")
        return None
    text = description_path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[desc] Description file is empty: {description_path}")
        return None

    print(f"[desc] Loaded description for DB: {db_name} from {description_path}")
    return text or None


def load_concept_comments(concept_comments_dir: Path, db_name: str) -> list[dict]:
    comment_path = concept_comments_dir / f"{db_name}.concept_comments.json"
    if not comment_path.exists():
        print(f"[concept] No concept comments file found for DB: {db_name} in {concept_comments_dir}")
        return []

    try:
        payload = json.loads(comment_path.read_text(encoding="utf-8"))
    except Exception:
        print(f"[concept] Failed to parse concept comments JSON: {comment_path}")
        return []

    concepts = payload.get("concepts", [])
    if not isinstance(concepts, list):
        print(f"[concept] 'concepts' field is not a list in: {comment_path}")
        return []

    normalized: list[dict] = []
    for item in concepts:
        if not isinstance(item, dict):
            continue
        concept = str(item.get("concept", "")).strip()
        comment = str(item.get("comment", "")).strip()
        if concept and comment:
            normalized.append({"concept": concept, "comment": comment})

    print(f"[concept] Loaded {len(normalized)} concept comments from {comment_path}")

    return normalized


def build_turtle(
    db_name: str,
    triples: list[tuple[str, str, str]],
    db_description: str | None = None,
    concept_comments: list[dict] | None = None,
) -> str:
    lines: list[str] = [PREFIXES.rstrip(), ""]

    print(f"[ttl] Building Turtle for DB: {db_name}")
    print(f"[ttl] Triples: {len(triples)} | Description present: {bool(db_description)} | Concept comments: {len(concept_comments or [])}")

    db_ref = central_uri(db_name)
    lines.append(f"{db_ref} a ex:DatabaseGraph .")
    lines.append(f'{db_ref} rdfs:label "{esc_lit(db_name)}" .')
    if db_description:
        lines.append(f'{db_ref} rdfs:comment "{esc_lit(db_description)}" .')

    entity_labels: dict[str, str] = {}
    relation_labels: dict[str, str] = {}

    # Build a map of concept labels to their comments for direct attachment to entities
    concept_comments_map: dict[str, str] = {}
    for concept in concept_comments or []:
        concept_value = concept.get("concept", "")
        comment_value = concept.get("comment", "")
        if concept_value and comment_value:
            concept_comments_map[concept_value] = comment_value

    for index, (subject, relation, obj) in enumerate(triples, start=1):
        triple_ref = triple_uri(db_name, index)
        subject_ref = entity_uri(db_name, subject)
        relation_ref = relation_uri(db_name, relation)
        object_ref = entity_uri(db_name, obj)

        entity_labels[subject_ref] = subject
        entity_labels[object_ref] = obj
        relation_labels[relation_ref] = relation

        lines.append(f"{db_ref} ex:hasT {triple_ref} .")
        lines.append(f"{triple_ref} a rdf:Statement .")
        lines.append(f"{triple_ref} rdf:subject {subject_ref} .")
        lines.append(f"{triple_ref} rdf:predicate {relation_ref} .")
        lines.append(f"{triple_ref} rdf:object {object_ref} .")
        lines.append(f"{subject_ref} {relation_ref} {object_ref} .")

    # Add entity definitions with optional comments from concept_comments_map
    for entity_ref, label in sorted(entity_labels.items()):
        lines.append(f'{entity_ref} a ex:Entity .')
        lines.append(f'{entity_ref} rdfs:label "{esc_lit(label)}" .')
        lines.append(f'{entity_ref} ex:databaseName "{esc_lit(db_name)}" .')
        lines.append(f'{entity_ref} ex:belongsToDatabase {db_ref} .')
        if label in concept_comments_map:
            lines.append(f'{entity_ref} rdfs:comment "{esc_lit(concept_comments_map[label])}" .')

    for relation_ref, label in sorted(relation_labels.items()):
        lines.append(f'{relation_ref} a ex:Relation .')
        lines.append(f'{relation_ref} rdfs:label "{esc_lit(label)}" .')

    return "\n".join(lines) + "\n"


def write_graphs(
    input_dir: Path,
    output_dir: Path,
    descriptions_dir: Path | None = None,
    concept_comments_dir: Path | None = None,
    target_db: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[main] Input dir: {input_dir}")
    print(f"[main] Output dir: {output_dir}")
    extraction_files = find_latest_extraction_files(input_dir, target_db=target_db)

    descriptions_dir = descriptions_dir or DEFAULT_DESCRIPTIONS_DIR
    concept_comments_dir = concept_comments_dir or DEFAULT_CONCEPT_COMMENTS_DIR

    print(f"[main] Descriptions dir: {descriptions_dir}")
    print(f"[main] Concept comments dir: {concept_comments_dir}")
    print(f"[main] Databases to process: {len(extraction_files)}")

    written_files: list[Path] = []
    for _, extraction_path in sorted(extraction_files.items()):
        db_name, triples = load_triples_from_extraction(extraction_path)
        db_description = load_database_description(descriptions_dir, db_name)
        comments = load_concept_comments(concept_comments_dir, db_name)
        print(f"[main] DB {db_name}: description={'yes' if db_description else 'no'}, concept_comments={len(comments)}")
        turtle = build_turtle(
            db_name,
            triples,
            db_description=db_description,
            concept_comments=comments,
        )
        output_path = output_dir / f"{db_name}.ttl"
        output_path.write_text(turtle, encoding="utf-8")
        written_files.append(output_path)
        print(
            f"[graph] Wrote {output_path.name} from {extraction_path.name} with {len(triples)} triples."
        )

    # Create a simple concatenated TTL (prefixes once + bodies)
    try:
        combined_ttl = output_dir / "grafo.ttl"
        combined_lines = [PREFIXES.rstrip(), ""]
        for path in written_files:
            content = path.read_text(encoding="utf-8")
            if content.startswith(PREFIXES):
                content = content[len(PREFIXES):].lstrip()
            combined_lines.append(content)
        combined_ttl.write_text("\n".join(combined_lines), encoding="utf-8")
        print(f"[graph] Wrote concatenated TTL: {combined_ttl}")
    except Exception as e:
        print(f"[graph] Failed to write concatenated TTL: {e}")

    return written_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one Turtle graph per DB from AutoKG extracted triples."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_AUTOKG_OUTPUT_DIR,
        help="Root directory containing AutoKG outputs from _3_call_auto_kg.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_GRAPH_OUTPUT_DIR,
        help="Directory where per-DB Turtle graphs will be written.",
    )
    parser.add_argument(
        "--descriptions-dir",
        type=Path,
        default=DEFAULT_DESCRIPTIONS_DIR,
        help="Directory containing semantic DB descriptions.",
    )
    parser.add_argument(
        "--concept-comments-dir",
        type=Path,
        default=DEFAULT_CONCEPT_COMMENTS_DIR,
        help="Directory containing concept comment JSON files.",
    )
    parser.add_argument(
        "--db-name",
        default=None,
        help="Build the graph only for one DB.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_graphs(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        descriptions_dir=args.descriptions_dir,
        concept_comments_dir=args.concept_comments_dir,
        target_db=args.db_name,
    )


if __name__ == "__main__":
    main()
