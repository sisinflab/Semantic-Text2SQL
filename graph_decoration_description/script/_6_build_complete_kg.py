"""Build decorated graphs by enriching RDF schemas with semantic annotations and generated descriptions."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

DEFAULT_RDF_SCHEMA_DIR = PROJECT_DIR / "rdf_schema"
DEFAULT_GENERATED_GRAPHS_DIR = SCRIPT_DIR / "generated_graphs"
DEFAULT_ANNOTATIONS_PATH = SCRIPT_DIR / "semantic_annotations_cls.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "decorated_graphs"

SCHEMA = Namespace("http://example.org/schema#")
RESOURCE_BASE = "http://example.org/resource"
GRAPH_BASE = "http://example.org/graph/generated"


def q(value: str) -> str:
    return quote(value, safe="")


def database_uri(database_name: str) -> URIRef:
    return URIRef(f"{RESOURCE_BASE}/db/{q(database_name)}")


def column_uri(database_name: str, table_name: str, column_name: str) -> URIRef:
    return URIRef(f"{RESOURCE_BASE}/column/{q(database_name)}/{q(table_name)}__{q(column_name)}")


def generated_description_uri(database_name: str) -> URIRef:
    return URIRef(f"{RESOURCE_BASE}/generated-description/{q(database_name)}")


def generated_graph_uri(database_name: str) -> URIRef:
    return URIRef(f"{GRAPH_BASE}/{q(database_name)}")


def load_annotations_by_database(path: Path) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)

    for row in payload:
        database_name = str(row.get("database_name", "")).strip()
        table_name = str(row.get("table_name", "")).strip()
        column_name = str(row.get("column_name", "")).strip()
        concept_id = str(row.get("semantic_concept_id", "")).strip()

        if not database_name or not table_name or not column_name:
            continue

        grouped[database_name].append(
            {
                "table_name": table_name,
                "column_name": column_name,
                "semantic_concept_id": concept_id,
            }
        )

    return grouped


def build_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    bind_prefixes(graph)
    return graph


def bind_prefixes(graph: Graph) -> None:
    graph.bind("ex", SCHEMA)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)


def _find_entity_by_label(graph: Graph, label: str, database_name: str | None = None) -> URIRef | None:
    """Find an entity in the graph by its rdfs:label, optionally filtered by database name."""
    normalized_label = str(label).strip().lower()
    
    for subject in graph.subjects(RDFS.label, None):
        subject_label = str(graph.value(subject, RDFS.label, None)).strip().lower()
        if subject_label == normalized_label:
            # If database_name is provided, check if the entity URI contains it
            if database_name:
                subject_str = str(subject)
                if f"/entity/{database_name}/" not in subject_str:
                    continue
            return subject
    
    return None


def add_semantic_annotations(graph: Graph, database_name: str, annotations: list[dict]) -> tuple[int, int]:
    added = 0
    missing_columns = 0

    for annotation in annotations:
        concept_id = annotation["semantic_concept_id"]
        if not concept_id or concept_id.lower() == "unknown":
            continue

        subject = column_uri(database_name, annotation["table_name"], annotation["column_name"])
        if (subject, None, None) not in graph:
            missing_columns += 1
            continue

        # Try to find the entity by label in the graph
        entity_uri = _find_entity_by_label(graph, concept_id, database_name)
        
        if entity_uri:
            # Link to the actual entity
            obj = entity_uri
        else:
            # Fallback to 'unknown' if entity not found
            obj = Literal("unknown")

        triple = (subject, SCHEMA.semantic_meaning, obj)
        if triple not in graph:
            graph.add(triple)
            added += 1

    return added, missing_columns


def add_generated_description_link(graph: Graph, database_name: str, generated_graph_path: Path | None) -> bool:
    if generated_graph_path is None or not generated_graph_path.exists():
        return False

    db_node = database_uri(database_name)
    description_node = generated_description_uri(database_name)
    graph_node = generated_graph_uri(database_name)

    if (db_node, None, None) not in graph:
        return False

    graph.add((db_node, SCHEMA.generated_description, description_node))
    graph.add((description_node, RDF.type, SCHEMA.GeneratedDescriptionGraph))
    graph.add((description_node, RDFS.label, Literal(f"{database_name} generated description graph")))
    graph.add((description_node, SCHEMA.describesDatabase, db_node))
    graph.add((description_node, SCHEMA.graphIRI, graph_node))
    return True


def merge_generated_graph(graph: Graph, generated_graph_path: Path | None) -> bool:
    if generated_graph_path is None or not generated_graph_path.exists():
        return False

    generated_graph = build_graph(generated_graph_path)
    for triple in generated_graph:
        graph.add(triple)
    return True


def serialize_graph(graph: Graph, output_path: Path) -> None:
    bind_prefixes(graph)
    output_path.write_text(graph.serialize(format="turtle"), encoding="utf-8")


def decorate_single_graph(
    schema_graph_path: Path,
    generated_graph_path: Path | None,
    annotations_by_database: dict[str, list[dict]],
    output_dir: Path,
) -> dict:
    database_name = schema_graph_path.stem
    graph = build_graph(schema_graph_path)

    # Merge generated graph first so entities are available for semantic annotation linking
    generated_merged = merge_generated_graph(graph, generated_graph_path)
    
    # Now add semantic annotations (entities are now in the graph)
    semantic_added, missing_columns = add_semantic_annotations(
        graph,
        database_name=database_name,
        annotations=annotations_by_database.get(database_name, []),
    )
    
    generated_linked = add_generated_description_link(graph, database_name, generated_graph_path)

    output_path = output_dir / schema_graph_path.name
    serialize_graph(graph, output_path)

    return {
        "database_name": database_name,
        "output_path": output_path,
        "semantic_added": semantic_added,
        "missing_columns": missing_columns,
        "generated_merged": generated_merged,
        "generated_linked": generated_linked,
    }


def decorate_aggregate_graph(
    aggregate_schema_path: Path,
    schema_dir: Path,
    generated_dir: Path,
    annotations_by_database: dict[str, list[dict]],
    output_dir: Path,
) -> dict:
    graph = build_graph(aggregate_schema_path)
    total_semantic_added = 0
    total_missing_columns = 0
    linked_count = 0
    merged_count = 0

    schema_files = sorted(
        path for path in schema_dir.glob("*.ttl") if path.name != aggregate_schema_path.name
    )

    for schema_graph_path in schema_files:
        database_name = schema_graph_path.stem
        
        # Merge generated graph first so entities are available
        generated_graph_path = generated_dir / f"{database_name}.ttl"
        if merge_generated_graph(graph, generated_graph_path):
            merged_count += 1
        
        # Now add semantic annotations (entities are now in the graph)
        semantic_added, missing_columns = add_semantic_annotations(
            graph,
            database_name=database_name,
            annotations=annotations_by_database.get(database_name, []),
        )
        total_semantic_added += semantic_added
        total_missing_columns += missing_columns
        if add_generated_description_link(graph, database_name, generated_graph_path):
            linked_count += 1

    output_path = output_dir / aggregate_schema_path.name
    serialize_graph(graph, output_path)

    return {
        "database_name": aggregate_schema_path.stem,
        "output_path": output_path,
        "semantic_added": total_semantic_added,
        "missing_columns": total_missing_columns,
        "generated_merged": merged_count,
        "generated_linked": linked_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decorate RDF schema graphs with semantic annotations and generated graph descriptions."
    )
    parser.add_argument(
        "--rdf-schema-dir",
        type=Path,
        default=DEFAULT_RDF_SCHEMA_DIR,
        help="Directory containing the base RDF schema graphs.",
    )
    parser.add_argument(
        "--generated-graphs-dir",
        type=Path,
        default=DEFAULT_GENERATED_GRAPHS_DIR,
        help="Directory containing the LLM-generated graphs.",
    )
    parser.add_argument(
        "--annotations-path",
        type=Path,
        default=DEFAULT_ANNOTATIONS_PATH,
        help="Path to semantic_annotations_cls.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the decorated graphs will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rdf_schema_dir = args.rdf_schema_dir.resolve()
    generated_graphs_dir = args.generated_graphs_dir.resolve()
    annotations_path = args.annotations_path.resolve()
    output_dir = args.output_dir.resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    annotations_by_database = load_annotations_by_database(annotations_path)

    schema_files = sorted(rdf_schema_dir.glob("*.ttl"))
    aggregate_schema_path = rdf_schema_dir / "grafo.ttl"

    if not schema_files:
        raise FileNotFoundError(f"No TTL files found in {rdf_schema_dir}")
    if not aggregate_schema_path.exists():
        raise FileNotFoundError(f"Aggregate graph not found: {aggregate_schema_path}")

    reports: list[dict] = []

    for schema_graph_path in schema_files:
        if schema_graph_path.name == aggregate_schema_path.name:
            continue

        generated_graph_path = generated_graphs_dir / f"{schema_graph_path.stem}.ttl"
        report = decorate_single_graph(
            schema_graph_path=schema_graph_path,
            generated_graph_path=generated_graph_path,
            annotations_by_database=annotations_by_database,
            output_dir=output_dir,
        )
        reports.append(report)
        print(
            f"[db] {report['database_name']}: semantic_added={report['semantic_added']}, "
            f"missing_columns={report['missing_columns']}, generated_merged={report['generated_merged']}, "
            f"generated_linked={report['generated_linked']} -> {report['output_path'].name}"
        )

    aggregate_report = decorate_aggregate_graph(
        aggregate_schema_path=aggregate_schema_path,
        schema_dir=rdf_schema_dir,
        generated_dir=generated_graphs_dir,
        annotations_by_database=annotations_by_database,
        output_dir=output_dir,
    )
    print(
        f"[all] {aggregate_report['database_name']}: semantic_added={aggregate_report['semantic_added']}, "
        f"missing_columns={aggregate_report['missing_columns']}, generated_merged={aggregate_report['generated_merged']}, "
        f"generated_linked={aggregate_report['generated_linked']} -> {aggregate_report['output_path'].name}"
    )


if __name__ == "__main__":
    main()
