"""
Simple script to query entities by database name using SPARQL over Turtle files.
"""

from pathlib import Path
from rdflib import Graph, Namespace, Literal
from urllib.parse import quote, unquote
from rdflib.plugins.sparql import prepareQuery


# Define namespaces
EX = Namespace("http://example.org/schema#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")

# SPARQL query template
ENTITIES_QUERY = """
PREFIX ex: <http://example.org/schema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?entity ?label ?comment ?dbName
WHERE {
    ?entity a ex:Entity ;
            ex:databaseName ?dbName ;
            rdfs:label ?label .
    OPTIONAL { ?entity rdfs:comment ?comment }
    FILTER (?dbName = "%s")
}
ORDER BY ?label
"""


def get_entities_by_database(ttl_file_path: str | Path, db_name: str) -> list[dict]:
    """
    Load a Turtle RDF file and find all entities associated with a given database.
    
    Args:
        ttl_file_path: Path to the .ttl file
        db_name: Name of the database to query
        
    Returns:
        List of dictionaries containing entity information
    """
    # Load the Turtle file
    graph = Graph()
    graph.parse(ttl_file_path, format="turtle")
    
    # Prepare the query with the database name
    query_str = ENTITIES_QUERY % db_name
    query = prepareQuery(query_str)
    
    # Execute the query
    results = graph.query(query)
    
    # Convert results to list of dicts
    entities = []
    for row in results:
        entity = {
            "uri": str(row.entity),
            "label": str(row.label),
            "database": str(row.dbName),
            "comment": str(row.comment) if row.comment else None,
        }
        entities.append(entity)
    
    return entities


def get_entities_by_concept(ttl_file_path: str | Path, db_name: str, concept_name: str) -> list[dict]:
    """
    Load a Turtle RDF file and find all entities associated with a given database and concept name.
    The concept_name is matched against the entity label or name.
    
    Args:
        ttl_file_path: Path to the .ttl file
        db_name: Name of the database to query
        concept_name: Name/label of the concept to query
        
    Returns:
        List of dictionaries containing entity information for the specific concept
    """
    # Load the Turtle file
    graph = Graph()
    graph.parse(ttl_file_path, format="turtle")
    
    # SPARQL query filtered by database and label/name matching concept
    concept_query = f"""
    PREFIX ex: <http://example.org/schema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?entity ?label ?comment ?dbName
    WHERE {{
        ?entity a ex:Entity ;
                ex:databaseName ?dbName ;
                rdfs:label ?label .
        OPTIONAL {{ ?entity rdfs:comment ?comment }}
        FILTER (?dbName = "{db_name}" && (LCASE(STR(?label)) = LCASE("{concept_name}")))
    }}
    ORDER BY ?label
    """
    
    query = prepareQuery(concept_query)
    
    # Execute the query
    results = graph.query(query)
    
    # Convert results to list of dicts
    entities = []
    for row in results:
        entity = {
            "uri": str(row.entity),
            "label": str(row.label),
            "database": str(row.dbName),
            "comment": str(row.comment) if row.comment else None,
        }
        entities.append(entity)
    
    return entities

def get_columns_by_semantic_concept(ttl_file_path: str | Path, db_name: str, concept_name: str) -> list[dict]:
    """
    Find all columns linked to a semantic concept by matching the concept name and database.
    
    Args:
        ttl_file_path: Path to the .ttl file
        db_name: Name of the database to filter
        concept_name: Name of the semantic concept (partial or full match)
        
    Returns:
        List of dictionaries containing column information
    """
    # Try to resolve the real concept label first (decode percent-encoding)
    decoded_concept = unquote(concept_name)
    #print(f"Searching for concept '{concept_name}' (decoded: '{decoded_concept}') in database '{db_name}'...")

    graph = Graph()
    graph.parse(ttl_file_path, format="turtle")

    # Find entity URIs whose rdfs:label matches the provided concept (case-insensitive)
    label_query = f"""
    PREFIX ex: <http://example.org/schema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?entity
    WHERE {{
        ?entity a ex:Entity ;
                ex:databaseName "{db_name}" ;
                rdfs:label "{decoded_concept}" .

    }}
    """
    try:
        q = prepareQuery(label_query)
        label_results = graph.query(q)
       # print(f"Found {len(label_results)} entities matching concept '{concept_name}' in database '{db_name}'")
        entity_uris = [str(r.entity) for r in label_results]
       # print('entity_uris', entity_uris)
    except Exception:
        entity_uris = []

    # Always use exact semantic URI match (built from db_name + concept_name)
    target_semantic_uri = _build_semantic_meaning_uri(db_name, concept_name)
    
    if entity_uris:
        # Use exact semantic URI match for found entities via VALUES
        values_block = "\n".join(f"VALUES ?semanticUri {{ <{u}> }}" for u in entity_uris)
        columns_query = f"""
        PREFIX ex: <http://example.org/schema#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?column ?name ?dataType ?description ?table ?semanticUri ?semanticComment
        WHERE {{
            ?column a ex:Column ;
                    ex:name ?name ;
                    ex:dataType ?dataType ;
                    ex:belongsToTable ?table ;
                    ex:semantic_meaning ?semanticUri .
            OPTIONAL {{ ?column ex:description ?description }}
            OPTIONAL {{ ?semanticUri rdfs:comment ?semanticComment }}
            {values_block}
        }}
        ORDER BY ?name
        """
    else:
        # No entity found by label, use exact IRI match on constructed semantic meaning URI
        columns_query = f"""
        PREFIX ex: <http://example.org/schema#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?column ?name ?dataType ?description ?table ?semanticUri ?semanticComment
        WHERE {{
            ?column a ex:Column ;
                    ex:name ?name ;
                    ex:dataType ?dataType ;
                    ex:belongsToTable ?table ;
                    ex:semantic_meaning <{target_semantic_uri}> .
            OPTIONAL {{ ?column ex:description ?description }}
            OPTIONAL {{ <{target_semantic_uri}> rdfs:comment ?semanticComment }}
        }}
        ORDER BY ?name
        """

    query = prepareQuery(columns_query)
    results = graph.query(query)
    
    columns = []
    for row in results:
        #we can extract the last part of the URI after the last slash
        clean_table_name = str(row.table).split("/")[-1]
        column = {
            "uri": str(row.column),
            "name": str(row.name),
            "dataType": str(row.dataType),
            "table": str(clean_table_name),
            "description": str(row.description) if row.description else None,
            "semantic_meaning": str(row.semanticUri),
            "semantic_comment": str(row.semanticComment) if row.semanticComment else None,
        }
        columns.append(column)
    
    return columns


def _build_semantic_meaning_uri(db_name: str, concept_name: str) -> str:
    """
    Build the expected IRI for a semantic meaning resource.

    If the caller already passes a full IRI, keep it as-is.
    Otherwise, compose the resource IRI using the database name and the URL-encoded concept name.
    """
    cleaned_concept = unquote(str(concept_name).strip())
    if cleaned_concept.startswith("http://") or cleaned_concept.startswith("https://"):
        return cleaned_concept

    encoded_concept = quote(cleaned_concept, safe="")
    #print(f"Constructed semantic meaning URI for concept '{concept_name}' (cleaned: '{cleaned_concept}', encoded: '{encoded_concept}') in database '{db_name}'")
    return f"http://example.org/resource/entity/{db_name}/{encoded_concept}"


def concept_appears_as_semantic_meaning(ttl_file_path: str | Path, db_name: str, concept_name: str) -> bool:
    """
    Verifica se un concetto appare almeno una volta come semantic meaning nel database.

    Returns:
        True se esiste almeno una colonna collegata al concetto, altrimenti False.
    """
    target_semantic_uri = _build_semantic_meaning_uri(db_name, concept_name)

    graph = Graph()
    graph.parse(ttl_file_path, format="turtle")

    ask_query = f"""
    PREFIX ex: <http://example.org/schema#>

    ASK WHERE {{
        ?column a ex:Column ;
                ex:semantic_meaning <{target_semantic_uri}> .
    }}
    """

    try:
        query = prepareQuery(ask_query)
        result = graph.query(query)
        return bool(result)
    except Exception:
        return False


def main():
    GRAPH_FILE_PATH = Path(__file__).resolve().parent / "grafo.ttl"
    #print(get_entities_by_database(GRAPH_FILE_PATH, "toxicology"))
    print(concept_appears_as_semantic_meaning(GRAPH_FILE_PATH, "toxicology", "Atom%20identifier"))

    entitys = get_entities_by_database(GRAPH_FILE_PATH, "toxicology")
    entiti_semnatic_meaning= [e for e in entitys if concept_appears_as_semantic_meaning(GRAPH_FILE_PATH, "toxicology", e.get("label", ""))]
    print(entiti_semnatic_meaning)  


    



    
  

if __name__ == "__main__":
    main()
