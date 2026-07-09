# Graph Decoration Description

This repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the ISWC 2026 Industry Track, and is developed in collaboration with the **IBM T.J. Watson Research Center**.

## Overview

This folder contains the tools and data used to build, decorate, and enrich a semantic knowledge graph (RDF/Turtle) from database schemas and textual evidence. The workflow includes semantic description generation, prompt generation, automatic component execution through auto-kg, and the creation of decorated graphs serialized as TTL.

The material is organized by database, including TTL files, descriptions, and concept comments, and by scripts that automate the workflow steps.

## Main Structure

- `rdf_schema/` - TTL files for individual databases and `grafo.ttl` (ontology/resource collection)
- `descriptions/` - `.semantic_evidence.txt` files containing textual evidence for databases
- `concept_comments/` - JSON files with comments and annotations for database-specific concepts
- `prompts/` and `system_prompts/` - templates and prompts used to interact with LLMs
- `script/` - Python scripts that automate the workflow
- `auto_kg_input/`, `auto_kg_output/` - input/output folders for auto-kg automation
- `decorated_graphs/`, `generated_graphs/` - RDF outputs produced by the jobs
- `semantic_evidence/` - directory for extracted or aggregated evidence

## Main Scripts (`script/`)

- `_0_build_prompts.py`
  - Builds prompts from descriptions, schema information, and rules, saving the templates under `prompts/`.

- `_0_generator.py`
  - Runs an LLM on the generated prompts to produce supporting text, such as descriptions and mapping suggestions.

- `_1_extract_semantic_evidence.py`
  - Extracts semantic evidence from input files, such as text and descriptions, and normalizes the results for prompt construction.

- `_2_generate_db_descriptions.py`
  - Generates extended descriptions for each database using generator outputs and evidence, then saves them under `descriptions/`.

- `_3_call_auto_kg.py`
  - Sends formatted input to the KG automation component (auto-kg) and collects the output under `auto_kg_output/`.

- `_3.5_generare_concept_descriptions.py`
  - Creates concept-specific descriptions based on evidence and schema information.

- `_4_build_semantic_kg.py`
  - Converts outputs such as mappings and descriptions into RDF triples and builds partial graphs.

- `_4.5_create_specfic_prompt.py`
  - Generates specific prompts to classify each column into one of the discovered semantic concepts.

- `_5_cls_colums.py`
  - Asks the agent to classify each column into a semantic concept using the prompts generated in the previous step.

- `_6_build_complete_kg.py`
  - Aggregates partial graphs and creates `grafo.ttl` or the individual decorated TTL files.

- `job_*.sh`
  - Batch scripts for submitting jobs, such as LLM execution and auto-kg, on a cluster. Adapt parameters according to the target infrastructure.

## Main Inputs and Outputs

- Primary inputs:
  - `data/original/*` (raw data, schemas, and related files)
  - files under `descriptions/` and `prompts/`
  - optional evidence files under `semantic_evidence/`

- Outputs:
  - `generated_graphs/` - automatically generated graphs (TTL, JSON-LD, and related formats)
  - `decorated_graphs/` - graphs enriched with semantic annotations
  - `concept_comments/*.concept_comments.json` - comments for each concept
  - log files and intermediate JSON files under `auto_kg_output/`

## Recommended Execution Order

1. Extract and normalize evidence.

```bash
python script/_1_extract_semantic_evidence.py
```

2. Generate database descriptions.

```bash
python script/_2_generate_db_descriptions.py
```

3. Call auto_kg.

```bash
sbatch script/job_3_call_auto_kg.sh
```

4. Generate concept descriptions.

```bash
sbatch script/job_3.5_geenrate_concept_description.sh
```

5. Build the RDF graph containing the concepts.

```bash
python script/_4_build_semantic_kg.py
```

6. Create prompts and classify columns.

```bash
python script/_4.5_create_specific_prompt.py
sbatch job_5_cls_colums.sh
```

7. Inspect the TTL files generated under `decorated_graphs/` and `generated_graphs/`.

## Practical Notes

- Keep a copy of `grafo.ttl` and update it only after manually checking the results.
- LLM jobs require compute resources; use GPU nodes with adequate memory for `_0_generator.py`.
- Check the files under `auto_kg_output/` for possible parsing errors.
- `concept_comments/*.json` can be used as an explanation layer for downstream agents.
