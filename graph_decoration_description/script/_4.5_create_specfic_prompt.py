"""Build per-database prompt files from the base template, graph concepts, and semantic evidence."""

import argparse
import json
from pathlib import Path

from rdflib import Graph


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

DEFAULT_TEMPLATE_PATH = PROJECT_DIR / "prompts" / "system_prompts" / "templete_promt.txt"
DEFAULT_GRAPH_PATH = SCRIPT_DIR / "generated_graphs" / "grafo.ttl"
DEFAULT_MANIFEST_PATH = PROJECT_DIR / "semantic_evidence" / "manifest.json"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "prompts"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_manifest_entry_path(manifest_path: Path, raw_path: str | Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def get_concepts_by_database(graph_file: str | Path, database_name: str) -> list[dict]:
    """Return the entities linked to a database in the RDF graph."""

    graph = Graph()
    graph.parse(str(graph_file), format="turtle")

    sparql_query = f"""
    PREFIX ex: <http://example.org/schema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?entity ?label ?comment
    WHERE {{
        ?entity a ex:Entity .
        ?entity rdfs:label ?label .
        OPTIONAL {{ ?entity rdfs:comment ?comment . }}
        FILTER(STRSTARTS(STR(?entity), "http://example.org/resource/entity/{database_name}"))
    }}
    ORDER BY ?label
    """

    results: list[dict] = []
    for row in graph.query(sparql_query):
        results.append(
            {
                "semantic_concept_id": str(row[0]),
                "label": str(row[1]),
                "comment": str(row[2]) if row[2] else None,
            }
        )

    return results


def format_concepts_block(concepts: list[dict], database_name: str, graph_path: Path) -> str:
    if not concepts:
        return (
            f"No semantic concepts were found in {graph_path.name} for database {database_name}.\n"
            "Keep the inventory empty and rely only on the evidence below."
        )

    lines = [
        f"Semantic concepts extracted from {graph_path.name} for database {database_name}:",
    ]
    for index, concept in enumerate(concepts, start=1):
        lines.append(f"{index}. {concept['label']}")
        lines.append(f"   description: {concept['comment'] or 'No description available.'}")

    return "\n".join(lines)


def insert_block(template: str, marker: str, block: str) -> str:
    if marker not in template:
        raise ValueError(f"Template marker not found: {marker}")
    before, after = template.split(marker, 1)
    return before + marker + "\n\n" + block + "\n\n" + after.lstrip()


def build_prompt(template: str, concepts_block: str, evidence_block: str) -> str:
    prompt = insert_block(
        template,
        "CANONICAL CONCEPT INVENTORY:",
        concepts_block,
    )
    return prompt.strip() + "\n"


def iter_manifest_entries(manifest_path: Path):
    manifest = load_json(manifest_path)
    for entry in manifest:
        yield entry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one prompt txt file per database by combining the base template, graph concepts, and semantic evidence."
    )
    parser.add_argument("--template-path", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--graph-file", type=Path, default=DEFAULT_GRAPH_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not args.template_path.exists():
        raise FileNotFoundError(f"Template not found: {args.template_path}")
    if not args.graph_file.exists():
        raise FileNotFoundError(f"Graph file not found: {args.graph_file}")
    if not args.manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {args.manifest}")

    template = args.template_path.read_text(encoding="utf-8").strip()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []
    for entry in iter_manifest_entries(args.manifest):
        database_name = entry["database_name"]
        concepts = get_concepts_by_database(args.graph_file, database_name)

        concepts_block = format_concepts_block(concepts, database_name, args.graph_file)
        final_prompt = build_prompt(template, concepts_block, "")

        output_path = args.output_dir / f"{database_name}.txt"
        output_path.write_text(final_prompt, encoding="utf-8")
        written_files.append(output_path)
        print(f"Wrote {output_path}")

    print(f"Generated {len(written_files)} prompt files in {args.output_dir}")


if __name__ == "__main__":
    main()
