# Semantic Agent with Description Pipeline

This repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the ISWC 2026 Industry Track, and is developed in collaboration with the **IBM T.J. Watson Research Center**.

## Overview

This pipeline implements an **enhanced semantic multi-agent approach** for SQL query generation. Compared with the simpler `semantic_agent` version, it introduces a **second specialized agent** that generates **detailed descriptions** of semantic concepts, giving the SQL generation model richer context.

## Architecture

The pipeline includes three main components:

1. **Semantic Ontology (RDF)**: an RDF graph that maps semantic concepts to database columns
2. **Selection Agent - First Pass**: quickly identifies potentially relevant semantic concepts
3. **Selection Agent - Refinement**: validates and refines the selection using descriptions from the RDF graph

## Pipeline Workflow

### Step 0: Semantic Template (`_0_semantic_templete.py`)

- Support utility that provides query functions over the RDF graph
- Loads the graph file (RDF graph in Turtle format)
- Main functions:
  - `get_entities_by_database()`: retrieves available entities for a database
  - `concept_appears_as_semantic_meaning()`: checks whether a concept appears as a semantic meaning

### Step 1: Prompt Generation for the Selection Agent (`_1_create_prompt_for_selection_agent.py`)

- Processes the original dataset and creates prompts for the selection agent
- For each question (`question_id` + `db_id`), generates a prompt asking the agent to:
  - identify the **relevant semantic concepts** from the available list
  - briefly explain their importance for answering the question
- Output: `_1_generated_semantic_selection_prompts_by_id.json`

**Supported semantic concepts**:

- `identifier`, `foreign_identifier`
- `person_name`, `person_first_name`, `person_last_name`
- `organization_name`, `school_name`, `team_name`
- `event_name`, `title`, `description_text`
- `category`, `status`, `gender`, `nationality`, `country_name`
- and many others

### Step 2: Run Selection Agent - First Pass (`_2_run_agent_selection_prompts.py`)

- Runs `Qwen2.5-Coder-7B-Instruct` through vLLM
- Input: selection prompts generated in Step 1
- Output: `_2_vllm_semantic_agent_selection_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Job submission: `job_2_run_agent_selection_prompts.sh`
- **Result**: initial list of semantic concepts identified as relevant, without descriptions
- **Purpose**: perform a fast first pass over the long list of available concepts

### Step 2.1: Prompt Generation for the Refined Selection Agent (`_2.1_create_prompt_for_agent.py`)

- Processes the output of the first Selection Agent (Step 2)
- Takes only the semantic concepts already selected
- For each selected concept, generates a new prompt asking the model to:
  - verify concept relevance using the **descriptions from the RDF graph**
  - refine the initial selection
- **Enrichment**: incorporates semantic descriptions from the RDF graph for the selected concepts into the prompt
- Output: `_2.1_generated_semantic_prompts_by_id.json`

### Step 2.2: Run Refined Selection Agent (`_2.2_run_agent_prompts.py`)

- Runs the LLM for the second selection stage
- Input: refined prompts with RDF descriptions from Step 2.1
- Output: `_2.2_vllm_semantic_agent_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Job submission: `job_2.2_run_agent_prompts_vllm.sh`
- **Result**: final refined and validated list of relevant semantic concepts
- **Purpose**: perform a more accurate second selection using semantic graph context

### Step 3: Semantic Information Extraction (`_3_extract_semantic_info.py`)

- Processes the Description Agent output
- Extracts selected semantic concepts and their descriptions
- Queries the RDF graph to retrieve the columns associated with each concept
- Creates a structured mapping: concept -> description -> database columns
- Output: `_3_dataset_with_semantic_info.json`

### Step 4: Original Dataset Enrichment (`_4_add_semantic_info_to_original_dataset.py`)

- Integrates semantic information into the original dataset
- Adds the following information for each question:
  - list of selected semantic concepts
  - detailed descriptions for each concept
  - column-to-semantic-concept mapping
  - description context
- The result is question-specific semantic information for each dataset item
- Output: `_4_source_dataset_with_columns_by_semantic_concept.json`

### Step 5: SQL Generation with Enriched Semantic Context (`_5_execute_sql_generation_with_semantic.py`)

- Generates SQL queries using the LLM
- **Maximum prompt enrichment** includes:
  - database schema
  - natural-language question
  - relevant semantic concepts
  - **detailed descriptions** for each concept
  - mapping of which columns represent which concepts
  - semantic context from the Description Agent
- Output: `_5_vllm_execute.json` (final SQL predictions)
- Job submission: `job_5_vllm_execute_sql_with_semantic.sh`

## Main Files

### Input

- Original dataset: `path/to/dataset.json`
- RDF graph: `grafo.ttl` (Turtle format, contains the semantic structure of the databases)

### Intermediate Outputs

- Step 1: `_1_generated_semantic_selection_prompts_by_id.json`
- Step 2: `_2_vllm_semantic_agent_selection_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Step 2.1: `_2.1_generated_semantic_prompts_by_id.json`
- Step 2.2: `_2.2_vllm_semantic_agent_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Step 3: `_3_dataset_with_semantic_info.json`
- Step 4: `_4_source_dataset_with_columns_by_semantic_concept.json`

### Final Output

- `_5_vllm_execute.json` - SQL queries generated with enriched semantic context

## Execution

### Prerequisites

- Python 3.x with `rdflib`, `transformers`, `vllm`, `torch`, and `tqdm`
- Available Qwen2.5-Coder-7B-Instruct model
- RDF graph `grafo.ttl` in the folder
- Access to GPU infrastructure on CINECA

### Step-by-Step Execution

```bash
# Step 0: Utility used by the other scripts
# Do not run directly

# Step 1: Generate prompts for the Selection Agent
python _1_create_prompt_for_selection_agent.py

# Step 2: Run Selection Agent (through SLURM on CINECA)
sbatch job_2_run_agent_selection_prompts.sh

# Step 2.1: Generate prompts for the Description Agent
python _2.1_create_prompt_for_agent.py

# Step 2.2: Run Description Agent (through SLURM on CINECA)
sbatch job_2.2_run_agent_prompts_vllm.sh

# Step 3: Extract semantic information
python _3_extract_semantic_info.py

# Step 4: Enrich the original dataset
python _4_add_semantic_info_to_original_dataset.py

# Step 5: Generate SQL with semantic context (through SLURM on CINECA)
sbatch job_5_vllm_execute_sql_with_semantic.sh
```

## Logical Flow

```text
Natural-language question
         |
   [Step 1] Create prompts with all available concepts
         |
   [Step 2] Fast first selection (long list -> shorter list)
         |
   [Step 2.1] Create prompts only for selected concepts + RDF descriptions
         |
   [Step 2.2] Refined second selection using semantic descriptions
         |
   [Step 3] Mapping: refined concepts -> descriptions -> columns
         |
   [Step 4] Enrich dataset with validated semantic concepts
         |
   [Step 5] Generate SQL with refined semantic context
         |
     Optimized SQL query
```

## Advantages over the Simple Version

1. **Two Selection Stages**: fast first pass to reduce the set, followed by refinement with descriptions
2. **Context-Aware Selection**: the second selection uses RDF descriptions to assess relevance
3. **Noise Reduction**: filters false-positive concepts from the fast first selection
4. **Deeper Semantic Interpretation**: the model evaluates concepts not only by name, but also by description
5. **Computational Efficiency**: two lighter agents instead of one heavier agent
6. **Traceability**: the first and second selections can be compared to understand the refinement process

## Two-Agent Selection Architecture

### Selection Agent - Phase 1 (Fast First Pass)

```text
Input: Question + schema + complete list of concepts
Process: Analyze the question and select potentially relevant concepts
Output: [concept_1, concept_2, ...] (restricted list)
Note: Does not use RDF descriptions
```

### Selection Agent - Phase 2 (Refinement with Descriptions)

```text
Input: Question + concepts selected in Phase 1 + RDF descriptions for those concepts
Process: Validate relevance using semantic context from the RDF graph
Output: [concept_1, concept_2, ...] (further refined list)
Note: Uses graph descriptions for more accurate decisions
```

### SQL Generation

```text
Input: Question + schema + concepts from Phase 2 + column mapping
Process: Generate SQL using the validated semantic concepts
Output: SQL query
```

## Important Notes

- The RDF graph must be kept up to date when the database schema changes.
- Predefined semantic concepts can be extended by adding new entries to the list.
- The pipeline is optimized for execution on CINECA with access to GPU infrastructure.
- Each step produces intermediate JSON files that can be inspected for debugging.
- Steps 2, 2.2, and 5 require significant time and are configured for SLURM execution.
- The first selection (Step 2) is fast and only acts as an initial filter.
- The second selection (Step 2.2) is more accurate because it uses semantic context from the RDF graph.
- Step 2 and Step 2.2 outputs can be compared to understand how RDF descriptions affect the selections.
- The computational cost is similar to the simple version.
