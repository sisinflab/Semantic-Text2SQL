from pathlib import Path
import sqlite3


DB_ROOT = Path(__file__).resolve().parents[2] / "data" / "original" / "dev_databases"


def get_database_path_sql(database_name: str) -> Path:
	"""
	Restituisce il path SQLite di un database nel formato:
	data/original/dev_databases/db_id/db_id.sqlite
	"""
	db_path = DB_ROOT / database_name / f"{database_name}.sqlite"
	if not db_path.exists():
		raise FileNotFoundError(f"Database non trovato: {db_path}")
	return db_path


def _quote_identifier(identifier: str) -> str:
	"""Escape minimo per nomi tabella usati in query dinamiche."""
	return '"' + identifier.replace('"', '""') + '"'


def query_columns_by_type_sql(database_name: str, data_type: str) -> list[tuple[str, str, str]]:
	"""
	Legge uno schema SQLite e restituisce le colonne del tipo richiesto.

	Args:
		database_name: Nome del database (db_id)
		data_type: Tipo da cercare (es. TEXT, INTEGER, REAL, DATE, DATETIME)

	Returns:
		Lista di tuple (table_name, column_name, column_type)
	"""
	db_path = get_database_path_sql(database_name)
	columns: list[tuple[str, str, str]] = []

	with sqlite3.connect(db_path) as conn:
		cur = conn.cursor()
		cur.execute(
			"""
			SELECT
				sm.name AS table_name,
				pti.name AS column_name,
				COALESCE(pti.type, '') AS column_type
			FROM sqlite_master AS sm
			JOIN pragma_table_info(sm.name) AS pti
			WHERE sm.type = 'table'
			  AND sm.name NOT LIKE 'sqlite_%'
			  AND UPPER(COALESCE(pti.type, '')) LIKE '%' || UPPER(?) || '%'
			ORDER BY sm.name, pti.name
			""",
			(data_type,),
		)

		for table_name, column_name, column_type in cur.fetchall():
			columns.append((table_name, column_name, column_type))

	return columns


def print_columns_by_type_sql(database_name: str, data_type: str) -> None:
	"""Stampa le colonne trovate in un formato leggibile."""
	print("=" * 60)
	print(f"COLONNE DI TIPO '{data_type}' IN {database_name}")
	print("=" * 60 + "\n")

	try:
		columns = query_columns_by_type_sql(database_name, data_type)
	except FileNotFoundError as exc:
		print(f"ERRORE: {exc}")
		return

	if not columns:
		print("Nessuna colonna trovata con questo tipo.")
		return

	current_table = None
	for table_name, col_name, col_type in columns:
		if table_name != current_table:
			print(f"\n- {table_name}")
			current_table = table_name
		print(f"   * {col_name} ({col_type})")

	print(f"\nTotale: {len(columns)} colonne")


if __name__ == "__main__":
	# Esempio di utilizzo
	print_columns_by_type_sql("codebase_community", "DATETIME")
