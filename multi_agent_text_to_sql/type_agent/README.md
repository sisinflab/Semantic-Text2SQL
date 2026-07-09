# Type Agent - Data-Type Information Pipeline

This repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the ISWC 2026 Industry Track, and is developed in collaboration with the **IBM T.J. Watson Research Center**.

## Overview

This folder contains scripts for selecting and inserting column data-type information (INTEGER, REAL, TEXT, DATE, DATETIME) into the Text-to-SQL flow. The pipeline supports two operating modes:

- through the RDF graph (SPARQL), useful when this agent is integrated with other agents that use the ontology;
- through the SQLite schema (SQL), useful when the agent is run in standalone mode without RDF.

Both templates (`_0_templete_sparql.py` and `_0_templete_sql.py`) are maintained to preserve usage flexibility. The current pipeline uses `_0_templete_sparql.py`, but it can be adapted easily.

## Requirements

- Python 3.8+
- Libraries: `rdflib`, `vllm`, `transformers`, `torch`, `tqdm`
- RDF file `grafo.ttl` when using SPARQL mode
- Folder `data/original/dev_databases/<db_id>/<db_id>.sqlite` when using SQL mode
- `MODEL_PATH` environment variable for vLLM scripts, unless running locally with `use_agent_local.py`

## Main Files and Updated Description

- `_1_agent.py`
  - Generates prompts asking which data types are needed for each question.
  - Input: `path/to/dataset.json`
  - Output: `_1_generated_prompts_by_id.json`
  - Usage: `python _1_agent.py`

- `_2_run_prompts_vllm.py` + `_2_job_run_prompts_vllm.sh`
  - Runs prompts through vLLM and normalizes the output into structured JSON.
  - Input: `_1_generated_prompts_by_id.json` and `MODEL_PATH`
  - Output: `_2_vllm_type_selection_agent_outputs.json`
  - Usage: `MODEL_PATH=/path/to/model python _2_run_prompts_vllm.py`

- `_3_create_dataset_with_data_type.py`
  - Processes the type-agent output, queries the RDF graph through `_0_templete_sparql.py` to retrieve columns associated with selected types, and produces `_3_dataset_with_sparql_types.json`.
  - If the graph is unavailable, the script can be adapted to work with SQL data.
  - Usage: `python _3_create_dataset_with_data_type.py`

- `_4_add_type_info_in_original.py`
  - Merges the file produced by the previous step with the original dataset, creating `_4_source_dataset_with_columns_by_type.json`.
  - Usage: `python _4_add_type_info_in_original.py`

- `_5_vllm_with_type.py` + `_5_job_vllm_with_type.sh`
  - Generates SQL queries using the enriched dataset, including data types and column mappings. Typically executed on a cluster.
  - Usage: `MODEL_PATH=/path/to_model python _5_vllm_with_type.py` or through `_5_job_vllm_with_type.sh`

- `_0_templete_sparql.py`
  - Contains utilities for querying the RDF graph `grafo.ttl`.
  - Main function: `query_columns_by_type_sparql(database_name, data_type)`.

- `_0_templete_sql.py`
  - Contains utilities for reading SQLite schemas and retrieving columns by type directly from the schema.
  - Main function: `query_columns_by_type_sql(database_name, data_type)`.

- `_0_check_sparql_sql_match.py`
  - Compares results obtained through SPARQL with results obtained through SQL queries over the schema. This is useful for validating consistency between the RDF graph and the real database.

Example files already present: `_3_dataset_with_sparql_types.json`, `_4_source_dataset_with_columns_by_type.json`, `_2_vllm_type_selection_agent_outputs.json`, `_5_pred_with_type.json`.

## Operating Modes and Recommendations

- SPARQL mode, recommended when integrating with other semantic agents: uses `_0_templete_sparql.py` to map types to columns through the RDF ontology. This makes it possible to reuse shared descriptions and semantic concepts.
- SQL mode, standalone: uses `_0_templete_sql.py` to extract types directly from the SQLite schema, useful when no RDF graph is available.
- Both SPARQL and SQL templates are maintained to support transitions or parallel operation.

## Recommended Clean Execution Order

1. Generate prompts for type selection.

```bash
python _1_agent.py
```

2. Run prompts with vLLM.

```bash
MODEL_PATH=/path/to_model python _2_run_prompts_vllm.py
# or use _2_job_run_prompts_vllm.sh on a cluster
```

3. Create the dataset with columns mapped by type, through SPARQL or SQL.

```bash
python _3_create_dataset_with_data_type.py
```

4. Merge the information into the original dataset.

```bash
python _4_add_type_info_in_original.py
```

5. Optionally check SPARQL-vs-SQL consistency.

```bash
python _0_check_sparql_sql_match.py
```

6. Generate SQL queries using the enriched dataset.

```bash
# on cluster
sbatch _5_job_vllm_with_type.sh

# locally, with MODEL_PATH configured
MODEL_PATH=/path/to_model python _5_vllm_with_type.py
```

## Practical Notes

- Verify the TTL file path in `_0_templete_sparql.py`.
- Check that `.sqlite` files are available under `data/original/dev_databases/<db_id>/`.
- Intermediate files, including prompts, vLLM outputs, and type-enriched datasets, are useful for debugging and can be inspected manually.
- Adapt job scripts (`.sh`) to the cluster resources, including GPU, RAM, and time limits.
