# Structural_KG

## Purpose

This folder contains the code and generated data used to convert SQLite database
schemas into RDF/Turtle knowledge graphs. The main script inspects each database,
extracts its structural metadata, enriches columns with available descriptive
metadata, and writes one RDF schema graph per database plus a merged graph for
all processed databases.

## Main Script

- `scripts/generate_rdf_schema.py`
  - Reads `.sqlite` files from the configured source directory:
    `bird/bird_dev/dev_databases`.
  - Inspects all user-defined SQLite tables, excluding internal `sqlite_%`
    tables.
  - Extracts table names, column names, SQLite data types, ordinal positions,
    primary-key flags, and `NOT NULL` constraints.
  - Extracts foreign-key relationships and represents them as `ex:references`
    links between column resources.
  - Loads optional column metadata from each database's
    `database_description/` directory. If needed, it also supports the common
    misspelled directory name `database_decription/`.
  - Adds column synonyms and descriptions when the metadata CSV files provide
    `column_name` and `column_description` values for an
    `original_column_name`.
  - Creates a central ontology node and links every generated database resource
    to that node.
  - Generates RDF/Turtle prefixes and IRIs for databases, tables, columns, and
    graph identifiers using the configured `http://example.org/...` base URIs.

## Outputs

- `rdf_schema/<database_name>.ttl`
  - Individual RDF/Turtle schema graph for each processed SQLite database.
- `rdf_schema/grafo.ttl`
  - Combined RDF/Turtle file containing the schema graphs for all processed
    databases.

The currently generated `rdf_schema/` directory contains schemas for databases
such as `california_schools`, `debit_card_specializing`, `financial`,
`formula_1`, `student_club`, and others.

## RDF Model

The generated graph uses the following main resource types and predicates:

- `ex:CentralOntologyNode` for the central node that groups all databases.
- `ex:Database` for each SQLite database.
- `ex:Table` for each table in a database.
- `ex:Column` for each table column.
- `ex:hasDatabase`, `ex:hasTable`, and `ex:hasColumn` for containment links.
- `ex:belongsToCentralNode`, `ex:belongsToDatabase`, and `ex:belongsToTable`
  for reverse containment links.
- `ex:dataType`, `ex:ordinalPosition`, `ex:isPrimaryKey`, and `ex:isNotNull`
  for structural column attributes.
- `ex:synonym` and `ex:description` for optional metadata loaded from CSV
  descriptions.
- `ex:references` for foreign-key links between columns.

## Usage

Run the generator from the `Structural_KG` folder:

```powershell
python scripts/generate_rdf_schema.py
```

The script creates `rdf_schema/` if it does not exist and overwrites the
generated `.ttl` files. If no `.sqlite` files are found under
`bird/bird_dev/dev_databases`, the script stops with an error.

## Notes

- The generated RDF is intended to make database structure readable by RDF and
  graph-based tools.
- The output can be used for semantic graph decoration, structural database
  analysis, and graph-based retrieval or querying workflows.
- Table-specific metadata aliases are currently defined in the script for the
  `app_store` database, mapping selected SQLite table names to their metadata
  CSV filenames.
