from __future__ import annotations

from _0_templete_sparql import query_columns_by_type_sparql
from _0_templete_sql import DB_ROOT, query_columns_by_type_sql


DATA_TYPES = ["INTEGER", "REAL", "TEXT", "DATE", "DATETIME"]


def _normalize_type(raw_type: str) -> str:
    value = (raw_type or "").upper().strip()
    if "#" in value:
        value = value.rsplit("#", 1)[-1]
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    return value


def _normalize_rows(rows: list[tuple[str, str, str]]) -> set[tuple[str, str, str]]:
    normalized = set()
    for table_name, column_name, data_type in rows:
        normalized.add((table_name.strip(), column_name.strip(), _normalize_type(data_type)))
    return normalized


def _list_database_ids() -> list[str]:
    database_ids: list[str] = []
    for db_dir in sorted(DB_ROOT.iterdir()):
        if not db_dir.is_dir():
            continue
        db_file = db_dir / f"{db_dir.name}.sqlite"
        if db_file.exists():
            database_ids.append(db_dir.name)
    return database_ids


def compare_results(database_name: str, data_type: str) -> tuple[int, int, list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    sparql_rows = query_columns_by_type_sparql(database_name, data_type)
    sql_rows = query_columns_by_type_sql(database_name, data_type)

    sparql_norm = _normalize_rows(sparql_rows)
    sql_norm = _normalize_rows(sql_rows)

    only_sparql = sorted(sparql_norm - sql_norm)
    only_sql = sorted(sql_norm - sparql_norm)

    return len(sparql_norm), len(sql_norm), only_sparql, only_sql


def main() -> int:
    database_ids = _list_database_ids()
    if not database_ids:
        print(f"ERRORE: nessun database trovato in {DB_ROOT}")
        return 2

    total_tests = len(database_ids) * len(DATA_TYPES)
    print(f"Eseguo {total_tests} test (tutte le combinazioni db x tipo)...")

    mismatches: list[tuple[str, str, int, int, list[tuple[str, str, str]], list[tuple[str, str, str]]]] = []

    for database_name in database_ids:
        for data_type in DATA_TYPES:
            sparql_total, sql_total, only_sparql, only_sql = compare_results(database_name, data_type)
            if only_sparql or only_sql:
                mismatches.append(
                    (database_name, data_type, sparql_total, sql_total, only_sparql, only_sql)
                )

    print("\n" + "=" * 80)
    print("RISULTATO FINALE")
    print("=" * 80)
    print(f"Test eseguiti: {total_tests}")
    print(f"Casi diversi: {len(mismatches)}")

    if not mismatches:
        print("Nessuna differenza trovata: tutti i risultati coincidono.")
        return 0

    for database_name, data_type, sparql_total, sql_total, only_sparql, only_sql in mismatches:
        print("\n" + "-" * 80)
        print(f"db={database_name} | type={data_type}")
        print(f"Totale SPARQL={sparql_total} | Totale SQL={sql_total}")

        if only_sparql:
            print(f"Solo in SPARQL ({len(only_sparql)}):")
            for row in only_sparql[:20]:
                print(f"  - {row}")
            if len(only_sparql) > 20:
                print(f"  ... altri {len(only_sparql) - 20} elementi")

        if only_sql:
            print(f"Solo in SQL ({len(only_sql)}):")
            for row in only_sql[:20]:
                print(f"  - {row}")
            if len(only_sql) > 20:
                print(f"  ... altri {len(only_sql) - 20} elementi")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())