from rdflib import Graph, Namespace

# Carica il file RDF/Turtle
SCHEMA_PATH = r"..\rdf_schema\grafo.ttl"

# Inizializzazione globale
print("Caricamento file RDF...")
g = Graph()
g.parse(SCHEMA_PATH, format="turtle")
print(f"✓ Caricate {len(g)} triple RDF\n")

EX = Namespace("http://example.org/schema#")


def query_columns_by_type_sparql(database_name: str, data_type: str) -> list:
    """
    Interroga il database RDF per ottenere colonne di un tipo specifico.
    
    Args:
        database_name: Nome del database (es. "california_schools", "card_games")
        data_type: Tipo di dato (es. "TEXT", "INTEGER", "REAL")
    
    Returns:
        Lista di tuple (table_name, column_name, data_type)
    """
    DATABASE = f"http://example.org/resource/db/{database_name}"
    
    query = f"""
    PREFIX ex: <http://example.org/schema#>
    
    SELECT ?table ?columnName ?dataType
    WHERE {{
        <{DATABASE}> ex:hasTable ?table .
        ?table ex:hasColumn ?column .
        ?column ex:name ?columnName ;
                ex:dataType ?dataType .
        FILTER(CONTAINS(STR(?dataType), "{data_type}"))
    }}
    ORDER BY ?table ?columnName
    """
    
    results = g.query(query)
    columns = []
    for row in results:
        table_name = str(row.table).split("/")[-1]
        col_name = str(row.columnName)
        col_type = str(row.dataType)
        columns.append((table_name, col_name, col_type))
    
    return columns


def print_columns_by_type_sparql(database_name: str, data_type: str) -> None:
    """
    Stampa le colonne di un tipo specifico nel formato tabellare.
    
    Args:
        database_name: Nome del database
        data_type: Tipo di dato possibili : INTEGER, REAL, TEXT, DATE, DATETIME
    """
    print("=" * 60)
    print(f"COLONNE DI TIPO '{data_type}' IN {database_name}")
    print("=" * 60 + "\n")
    
    columns = query_columns_by_type_sparql(database_name, data_type)
    
    if not columns:
        print("❌ Nessuna colonna trovata con questo tipo!")
        return
    
    current_table = None
    for table_name, col_name, col_type in columns:
        if table_name != current_table:
            print(f"\n📋 {table_name}")
            current_table = table_name
        
        print(f"   🔹 {col_name} ({col_type})")
    
    print(f"\n✓ Totale: {len(columns)} colonne")


# Main
if __name__ == "__main__":
    # Esempio di utilizzo
    print_columns_by_type_sparql("codebase_community", "DATETIME")


