import sqlite3
from pathlib import Path
from urllib.parse import quote
import csv

"""
This script processes input SQLite databases, inspects tables and columns (including
data types, primary keys, and NOT NULL constraints), and loads descriptive metadata 
from CSV files. 

It generates an RDF/Turtle graph representing the database schemas and table 
relationships.

Outputs:
- Individual RDF files for each processed database.
- A single, merged RDF file aggregating all schemas.
"""

BASE_PREFIXES = """@prefix ex: <http://example.org/schema#> .
@prefix res: <http://example.org/resource/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

"""

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

DEFAULT_SETTINGS = {
    "source_dir": PROJECT_DIR / "bird" / "bird_dev" / "dev_databases",
    "out_dir": PROJECT_DIR / "rdf_schema",
    "graph_base": "http://example.org/graph/database",
    "resource_base": "http://example.org/resource",
    "central_node_uri": "http://example.org/resource/central/main_ontology",
}

TABLE_METADATA_ALIASES = {
    "app_store": {
        "playstore": "googleplaystore",
        "user_reviews": "googleplaystore_user_reviews",
    }
}


def resolve_path(raw_path: str | Path, base_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def q(value: str) -> str:
    return quote(value, safe="")


def esc_lit(value: str) -> str:
    return (
        value.replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\n', '\\n')
    )


def norm_name(value: str) -> str:
    return value.strip().casefold()


def column_local_name(table_id: str, column_id: str) -> str:
    return f"{table_id}__{column_id}"


def format_prefixes(db_id: str, res_base: str, include_base: bool) -> str:
    lines: list[str] = []
    if include_base:
        lines.append(BASE_PREFIXES.rstrip("\n"))
    lines.append(f"@prefix db: <{res_base.rstrip('/')}/db/> .")
    lines.append(f"@prefix ctr: <{res_base.rstrip('/')}/central/> .")
    lines.append(f"@prefix tbl: <{res_base.rstrip('/')}/table/{db_id}/> .")
    lines.append(f"@prefix col: <{res_base.rstrip('/')}/column/{db_id}/> .")
    return "\n".join(lines) + "\n\n"


def merged_prefix_block(db_id: str, res_base: str) -> str:
    return (
        f"@prefix db_{db_id}: <{res_base.rstrip('/')}/db/> .\n"
        f"@prefix ctr_{db_id}: <{res_base.rstrip('/')}/central/> .\n"
        f"@prefix tbl_{db_id}: <{res_base.rstrip('/')}/table/{db_id}/> .\n"
        f"@prefix col_{db_id}: <{res_base.rstrip('/')}/column/{db_id}/> .\n"
    )


def iter_tables(conn: sqlite3.Connection):
    cur = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    for (name,) in cur.fetchall():
        yield name


def iter_columns(conn: sqlite3.Connection, table: str):
    cur = conn.execute(f"PRAGMA table_info('{table.replace("'", "''")}')")
    for cid, name, col_type, notnull, dflt_value, pk in cur.fetchall():
        yield {
            "cid": cid,
            "name": name,
            "type": col_type or "",
            "notnull": int(notnull),
            "pk": int(pk),
        }


def iter_foreign_keys(conn: sqlite3.Connection, table: str):
    cur = conn.execute(f"PRAGMA foreign_key_list('{table.replace("'", "''")}')")
    for fk_id, seq, ref_table, from_col, to_col, on_update, on_delete, match in cur.fetchall():
        yield {
            "ref_table": ref_table,
            "from_col": from_col,
            "to_col": to_col,
        }


def load_column_metadata(db_path: Path) -> dict[str, dict[str, dict[str, str]]]:
    db_dir = db_path.parent
    description_dir = db_dir / "database_description"
    if not description_dir.exists():
        description_dir = db_dir / "database_decription"
    if not description_dir.exists():
        return {}

    metadata: dict[str, dict[str, dict[str, str]]] = {}
    for csv_file in sorted(description_dir.glob("*.csv")):
        table_key = norm_name(csv_file.stem)
        table_map = metadata.setdefault(table_key, {})
        rows = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with csv_file.open("r", encoding=encoding, newline="") as handle:
                    rows = list(csv.DictReader(handle))
                break
            except (OSError, UnicodeDecodeError):
                rows = None
        if rows is None:
            continue

        for row in rows:
            if not row:
                continue
            original_col = (row.get("original_column_name") or "").strip()
            if not original_col:
                continue
            table_map[norm_name(original_col)] = {
                "synonym": (row.get("column_name") or "").strip(),
                "description": (row.get("column_description") or "").strip(),
            }
    return metadata


def build_db_graph(db_path: Path, graph_base: str, res_base: str, central_node_uri: str) -> tuple[str, str]:
    db_name = db_path.stem
    db_id = q(db_name)
    table_aliases = TABLE_METADATA_ALIASES.get(db_name, {})

    db_uri = f"<{res_base.rstrip('/')}/db/{db_id}>"
    graph_uri = f"<{graph_base.rstrip('/')}/{db_id}>"
    central_uri = f"<{central_node_uri.rstrip('/')}>"

    def table_ref(table_id: str, prefixed: bool) -> str:
        if prefixed:
            return f"tbl:{table_id}"
        return f"<{res_base.rstrip('/')}/table/{db_id}/{table_id}>"

    def col_ref(table_id: str, col_id: str, prefixed: bool) -> str:
        if prefixed:
            return f"col:{column_local_name(table_id, col_id)}"
        return f"<{res_base.rstrip('/')}/column/{db_id}/{table_id}/{col_id}>"

    central_local = q(central_node_uri.rstrip("/").split("/")[-1])
    db_uri_pref = f"db:{db_id}"
    central_uri_pref = f"ctr:{central_local}"

    db_uri_merged = f"db_{db_id}:{db_id}"
    central_uri_merged = f"ctr_{db_id}:{central_local}"

    lines_prefixed = [
        f"{central_uri_pref} a ex:CentralOntologyNode .",
        f"{central_uri_pref} ex:hasDatabase {db_uri_pref} .",
        f"{db_uri_pref} a ex:Database ;",
        f"  ex:name \"{esc_lit(db_name)}\" ;",
        f"  ex:belongsToCentralNode {central_uri_pref} ;",
        f"  ex:graphIRI {graph_uri} .",
    ]

    lines_full = [
        f"{central_uri} a ex:CentralOntologyNode .",
        f"{central_uri} ex:hasDatabase {db_uri} .",
        f"{db_uri} a ex:Database ;",
        f"  ex:name \"{esc_lit(db_name)}\" ;",
        f"  ex:belongsToCentralNode {central_uri} ;",
        f"  ex:graphIRI {graph_uri} .",
    ]

    lines_merged = [
        f"{central_uri_merged} a ex:CentralOntologyNode .",
        f"{central_uri_merged} ex:hasDatabase {db_uri_merged} .",
        f"{db_uri_merged} a ex:Database ;",
        f"  ex:name \"{esc_lit(db_name)}\" ;",
        f"  ex:belongsToCentralNode {central_uri_merged} ;",
        f"  ex:graphIRI {graph_uri} .",
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        table_names = list(iter_tables(conn))
        column_metadata = load_column_metadata(db_path)

        for table_name in table_names:
            table_id = q(table_name)
            table_ref_pref = table_ref(table_id, True)
            table_ref_full = table_ref(table_id, False)
            metadata_table_name = table_aliases.get(table_name, table_name)
            table_meta = column_metadata.get(norm_name(metadata_table_name), {})
            table_ref_merged = f"tbl_{db_id}:{table_id}"
            for lines, t_ref, db_ref in (
                (lines_prefixed, table_ref_pref, db_uri_pref),
                (lines_full, table_ref_full, db_uri),
                (lines_merged, table_ref_merged, db_uri_merged),
            ):
                lines.append(f"{db_ref} ex:hasTable {t_ref} .")
                lines.append(f"{t_ref} a ex:Table ;")
                lines.append(f"  ex:name \"{esc_lit(table_name)}\" ;")
                lines.append(f"  ex:belongsToDatabase {db_ref} .")

            for col in iter_columns(conn, table_name):
                col_id = q(col["name"])
                col_ref_pref = col_ref(table_id, col_id, True)
                col_ref_full = col_ref(table_id, col_id, False)
                col_ref_merged = f"col_{db_id}:{column_local_name(table_id, col_id)}"
                col_meta = table_meta.get(norm_name(col["name"]), {})
                for lines, t_ref, c_ref in (
                    (lines_prefixed, table_ref_pref, col_ref_pref),
                    (lines_full, table_ref_full, col_ref_full),
                    (lines_merged, table_ref_merged, col_ref_merged),
                ):
                    lines.append(f"{t_ref} ex:hasColumn {c_ref} .")
                    lines.append(f"{c_ref} a ex:Column ;")
                    lines.append(f"  ex:name \"{esc_lit(col['name'])}\" ;")
                    if col_meta.get("synonym"):
                        lines.append(f"  ex:synonym \"{esc_lit(col_meta['synonym'])}\" ;")
                    if col_meta.get("description"):
                        lines.append(f"  ex:description \"{esc_lit(col_meta['description'])}\" ;")
                    lines.append(f"  ex:dataType \"{esc_lit(col['type'])}\" ;")
                    lines.append(f"  ex:ordinalPosition \"{col['cid']}\"^^xsd:integer ;")
                    lines.append(f"  ex:isPrimaryKey \"{str(bool(col['pk'])).lower()}\"^^xsd:boolean ;")
                    lines.append(f"  ex:isNotNull \"{str(bool(col['notnull'])).lower()}\"^^xsd:boolean ;")
                    lines.append(f"  ex:belongsToTable {t_ref} .")

        table_set = set(table_names)
        for table_name in table_names:
            from_table_id = q(table_name)
            for fk in iter_foreign_keys(conn, table_name):
                ref_table = fk["ref_table"]
                from_col = fk["from_col"]
                to_col = fk["to_col"]

                if not ref_table or not from_col or not to_col:
                    continue
                if ref_table not in table_set:
                    continue

                from_col_id = q(from_col)
                to_table_id = q(ref_table)
                to_col_id = q(to_col)
                from_col_pref = col_ref(from_table_id, from_col_id, True)
                to_col_pref = col_ref(to_table_id, to_col_id, True)
                from_col_full = col_ref(from_table_id, from_col_id, False)
                to_col_full = col_ref(to_table_id, to_col_id, False)
                from_col_merged = f"col_{db_id}:{column_local_name(from_table_id, from_col_id)}"
                to_col_merged = f"col_{db_id}:{column_local_name(to_table_id, to_col_id)}"
                lines_prefixed.append(f"{from_col_pref} ex:references {to_col_pref} .")
                lines_full.append(f"{from_col_full} ex:references {to_col_full} .")
                lines_merged.append(f"{from_col_merged} ex:references {to_col_merged} .")
    finally:
        conn.close()

    merged_prefixes = merged_prefix_block(db_id, res_base)
    return (
        merged_prefixes + "\n".join(lines_merged) + "\n",
        "\n".join(lines_prefixed) + "\n",
    )


def main():
    source_dir = resolve_path(DEFAULT_SETTINGS["source_dir"], PROJECT_DIR)
    out_dir = resolve_path(DEFAULT_SETTINGS["out_dir"], PROJECT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    sqlite_files = sorted(source_dir.rglob("*.sqlite"))
    if not sqlite_files:
        raise SystemExit(f"No .sqlite files found in {source_dir}")

    merged_path = out_dir / "grafo.ttl"
    with merged_path.open("w", encoding="utf-8") as merged:
        merged.write(BASE_PREFIXES)
        for db_file in sqlite_files:
            trig_merged, trig_prefixed = build_db_graph(
                db_file,
                DEFAULT_SETTINGS["graph_base"],
                DEFAULT_SETTINGS["resource_base"],
                DEFAULT_SETTINGS["central_node_uri"],
            )
            per_db_path = out_dir / f"{db_file.stem}.ttl"
            per_db_path.write_text(BASE_PREFIXES + trig_merged, encoding="utf-8")
            merged.write(trig_merged)

    print(f"Generated {len(sqlite_files)} database graphs in: {out_dir}")
    print(f"Merged file: {merged_path}")


if __name__ == "__main__":
    main()
