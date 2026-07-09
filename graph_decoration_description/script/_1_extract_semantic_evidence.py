import csv
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

'''
This script extracts semantic evidence from SQLite database files, including column metadata, value distributions, and sample values. 
The extracted evidence is saved as JSON files, and a manifest is created to index the evidence for multiple databases. 
This can be used as base information from LLMs to perform graph decoration tasks.
'''

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
print(f"Script directory: {SCRIPT_DIR}")
print(f"Project directory: {PROJECT_DIR}")

DEFAULT_SETTINGS = {
    "source_dir": PROJECT_DIR / "../data\\original\\dev_databases",
    "out_dir": PROJECT_DIR / "semantic_evidence",
    "sample_size": 8,
    "profile_scan_limit": 200,
    "top_value_limit": 5,
    "max_text_length": 80,
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


def to_relative_path(raw_path: Path, base_dir: Path) -> str:
    try:
        return os.path.relpath(raw_path.resolve(), base_dir.resolve())
    except ValueError:
        # Keep absolute when paths are on different drives or unrelated roots.
        return str(raw_path.resolve())


def norm_name(value: str) -> str:
    return value.strip().casefold()


def sanitize_identifier(identifier: str) -> str:
    return identifier.replace('"', '""')


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
    safe_table = table.replace("'", "''")
    cur = conn.execute(f"PRAGMA table_info('{safe_table}')")
    for cid, name, col_type, notnull, dflt_value, pk in cur.fetchall():
        yield {
            "cid": cid,
            "name": name,
            "type": col_type or "",
            "notnull": int(notnull),
            "pk": int(pk),
        }


def iter_foreign_keys(conn: sqlite3.Connection, table: str):
    safe_table = table.replace("'", "''")
    cur = conn.execute(f"PRAGMA foreign_key_list('{safe_table}')")
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
                "data_format": (row.get("data_format") or "").strip(),
                "value_description": (row.get("value_description") or "").strip(),
            }
    return metadata


def split_identifier_tokens(value: str) -> list[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    parts = re.sub(r"[_\-.]+", " ", parts)
    tokens = [token.casefold() for token in parts.split() if token.strip()]
    return tokens


def detect_name_hints(tokens: list[str]) -> dict[str, bool]:
    token_set = set(tokens)
    return {
        "looks_like_identifier": "id" in token_set or any(token.endswith("id") for token in token_set),
        "looks_like_name": "name" in token_set or "forename" in token_set or "surname" in token_set,
        "looks_like_date": any(token in token_set for token in ("date", "dob", "birthday", "year", "month")),
        "looks_like_location": any(token in token_set for token in ("city", "country", "state", "zip", "address", "location")),
        "looks_like_contact": any(token in token_set for token in ("email", "phone", "url", "website")),
        "looks_like_amount": any(token in token_set for token in ("price", "amount", "total", "cost", "salary", "spent", "remaining")),
    }


def safe_json_value(value, max_text_length: int) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()
    if not text:
        return None
    return text[:max_text_length]


def collect_column_stats(
    conn: sqlite3.Connection,
    table_name: str,
    table_row_count: int,
    column_name: str,
    sample_size: int,
    profile_scan_limit: int,
    top_value_limit: int,
    max_text_length: int,
) -> dict:
    safe_table = sanitize_identifier(table_name)
    safe_column = sanitize_identifier(column_name)

    base_query = f'SELECT "{safe_column}" FROM "{safe_table}"'
    non_null_count = conn.execute(
        f'SELECT COUNT(*) FROM "{safe_table}" WHERE "{safe_column}" IS NOT NULL'
    ).fetchone()[0]

    profile_rows = conn.execute(
        f'{base_query} WHERE "{safe_column}" IS NOT NULL LIMIT ?',
        (max(sample_size, profile_scan_limit),),
    ).fetchall()
    value_types = Counter()
    observed_lengths = []
    normalized_profile_values = []
    for (raw_value,) in profile_rows[:profile_scan_limit]:
        if isinstance(raw_value, bool):
            value_types["boolean"] += 1
        elif isinstance(raw_value, int):
            value_types["integer"] += 1
        elif isinstance(raw_value, float):
            value_types["float"] += 1
        else:
            value_types["text"] += 1
        normalized = safe_json_value(raw_value, max_text_length)
        if normalized is not None:
            normalized_profile_values.append(normalized)
            if isinstance(normalized, str):
                observed_lengths.append(len(normalized))

    sample_values = normalized_profile_values[:sample_size]
    top_values = [
        {"value": value, "count": count}
        for value, count in Counter(normalized_profile_values).most_common(top_value_limit)
    ]

    avg_text_length = None
    if observed_lengths:
        avg_text_length = round(sum(observed_lengths) / len(observed_lengths), 2)

    distinct_count = len(set(normalized_profile_values))
    null_count = table_row_count - non_null_count
    null_ratio = None
    if table_row_count:
        null_ratio = round(null_count / table_row_count, 4)

    distinct_ratio = None
    if normalized_profile_values:
        distinct_ratio = round(distinct_count / len(normalized_profile_values), 4)

    return {
        "row_count": table_row_count,
        "non_null_count": non_null_count,
        "null_count": null_count,
        "null_ratio": null_ratio,
        "profiled_value_count": len(normalized_profile_values),
        "distinct_count_in_profile": distinct_count,
        "distinct_ratio_in_profile": distinct_ratio,
        "value_type_distribution": dict(value_types),
        "avg_text_length": avg_text_length,
        "sample_values": sample_values,
        "top_values": top_values,
    }


def build_foreign_key_index(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, str]]:
    fk_index: dict[tuple[str, str], dict[str, str]] = {}
    for table_name in iter_tables(conn):
        for fk in iter_foreign_keys(conn, table_name):
            from_col = fk["from_col"]
            ref_table = fk["ref_table"]
            to_col = fk["to_col"]
            if not from_col or not ref_table or not to_col:
                continue
            fk_index[(table_name, from_col)] = {
                "references_table": ref_table,
                "references_column": to_col,
            }
    return fk_index


def build_column_evidence(
    db_path: Path,
    sample_size: int,
    profile_scan_limit: int,
    top_value_limit: int,
    max_text_length: int,
) -> dict:
    db_name = db_path.stem
    conn = sqlite3.connect(str(db_path))
    try:
        table_names = list(iter_tables(conn))
        fk_index = build_foreign_key_index(conn)
        column_metadata = load_column_metadata(db_path)
        table_aliases = TABLE_METADATA_ALIASES.get(db_name, {})

        tables = []
        for table_name in table_names:
            metadata_table_name = table_aliases.get(table_name, table_name)
            table_meta = column_metadata.get(norm_name(metadata_table_name), {})
            table_row_count = conn.execute(
                f'SELECT COUNT(*) FROM "{sanitize_identifier(table_name)}"'
            ).fetchone()[0]
            table_item = {
                "table_name": table_name,
                "row_count": table_row_count,
                "column_count": 0,
                "columns": [],
            }

            for col in iter_columns(conn, table_name):
                col_name = col["name"]
                col_meta = table_meta.get(norm_name(col_name), {})
                lexical_tokens = split_identifier_tokens(col_name)
                stats = collect_column_stats(
                    conn,
                    table_name,
                    table_row_count,
                    col_name,
                    sample_size=sample_size,
                    profile_scan_limit=profile_scan_limit,
                    top_value_limit=top_value_limit,
                    max_text_length=max_text_length,
                )
                column_item = {
                    "database_name": db_name,
                    "table_name": table_name,
                    "column_name": col_name,
                    "ordinal_position": col["cid"],
                    "sqlite_declared_type": col["type"],
                    "is_primary_key": bool(col["pk"]),
                    "is_not_null": bool(col["notnull"]),
                    "is_foreign_key": (table_name, col_name) in fk_index,
                    "foreign_key_target": fk_index.get((table_name, col_name)),
                    "metadata": {
                        "synonym": col_meta.get("synonym") or None,
                        "description": col_meta.get("description") or None,
                        "data_format": col_meta.get("data_format") or None,
                        "value_description": col_meta.get("value_description") or None,
                    },
                    "lexical_evidence": {
                        "tokens": lexical_tokens,
                        "name_hints": detect_name_hints(lexical_tokens),
                    },
                    "value_evidence": stats,
                }
                table_item["columns"].append(column_item)

            table_item["column_count"] = len(table_item["columns"])
            tables.append(table_item)

        return {
            "database_name": db_name,
            "database_path": str(db_path),
            "table_count": len(tables),
            "tables": tables,
        }
    finally:
        conn.close()


def main():
    source_dir = resolve_path(DEFAULT_SETTINGS["source_dir"], PROJECT_DIR)
    out_dir = resolve_path(DEFAULT_SETTINGS["out_dir"], PROJECT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    sqlite_files = sorted(source_dir.rglob("*.sqlite"))
    if not sqlite_files:
        raise SystemExit(f"No .sqlite files found in {source_dir}")

    manifest = []
    for db_file in sqlite_files:
        evidence = build_column_evidence(
            db_file,
            sample_size=DEFAULT_SETTINGS["sample_size"],
            profile_scan_limit=DEFAULT_SETTINGS["profile_scan_limit"],
            top_value_limit=DEFAULT_SETTINGS["top_value_limit"],
            max_text_length=DEFAULT_SETTINGS["max_text_length"],
        )
        out_path = out_dir / f"{db_file.stem}.semantic_evidence.json"
        evidence["database_path"] = to_relative_path(db_file, out_dir)
        out_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=True), encoding="utf-8")
        manifest.append(
            {
                "database_name": db_file.stem,
                "database_path": to_relative_path(db_file, manifest_path.parent),
                "evidence_path": to_relative_path(out_path, manifest_path.parent),
                "table_count": evidence["table_count"],
                "column_count": sum(table["column_count"] for table in evidence["tables"]),
            }
        )
        print(f"Extracted evidence for database: {db_file.stem}")

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"Extracted semantic evidence for {len(sqlite_files)} databases into: {out_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
