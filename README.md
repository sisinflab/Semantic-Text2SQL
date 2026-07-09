# Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL

This repository contains the code and experimental components for the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the **ISWC 2026 Industry Track**.

The work is developed in collaboration with the **IBM T.J. Watson Research Center**.

## Overview

The project investigates how unified knowledge graphs can support adaptive semantic refinement in Text-to-SQL systems. The repository combines structural schema graphs, semantic graph decoration, multi-agent semantic selection, type-aware refinement, SQL generation, and evaluation utilities.

The core idea is to enrich Text-to-SQL generation with graph-based knowledge about database structure, semantic concepts, column descriptions, and data types. These signals are injected into specialized agents that select relevant semantic and type information before the final SQL generation step.

## Repository Structure

- `Structural_KG/`
  - Builds RDF/Turtle knowledge graphs from SQLite database schemas.
  - Produces structural graph representations of databases, tables, columns, keys, constraints, and relationships.

- `graph_decoration_description/`
  - Builds and decorates semantic knowledge graphs using database schemas and textual evidence.
  - Generates semantic descriptions, concept annotations, prompts, and enriched TTL graphs.

- `autoKG/`
  - Contains the AutoSchemaKG/ATLAS-based components used for knowledge graph construction and schema induction.
  - Includes local scripts that connect AutoKG workflows to the graph decoration pipeline.

- `multi_agent_text_to_sql/semantic_agent_description/`
  - Implements the semantic multi-agent pipeline.
  - Performs concept selection, refinement using RDF descriptions, semantic information extraction, dataset enrichment, and SQL generation.

- `multi_agent_text_to_sql/type_agent/`
  - Implements the data-type agent.
  - Selects relevant column data types and injects type-to-column mappings into the Text-to-SQL generation flow.

- `base_model_test/`
  - Runs the base vLLM Text-to-SQL model and saves SQL predictions.

- `test with bloked gold/`
  - Prepares locked gold outputs and evaluates pipeline predictions against them.

- `compute_pipeline_EX/`
  - Aggregates evaluation results and measures how different refinement stages correct base-model errors.

## High-Level Pipeline

1. Build structural RDF graphs from SQLite database schemas with `Structural_KG/`.
2. Generate semantic evidence and decorate the graph with `graph_decoration_description/`.
3. Use AutoKG components under `autoKG/` when schema induction or automatic KG construction is required.
4. Run the semantic agent pipeline in `multi_agent_text_to_sql/semantic_agent_description/`.
5. Run the type agent pipeline in `multi_agent_text_to_sql/type_agent/`.
6. Generate base or enriched SQL predictions with the vLLM scripts.
7. Evaluate predictions with the locked-gold utilities.
8. Aggregate correction results with `compute_pipeline_EX/`.

## Documentation

Each component includes a dedicated README with local usage instructions:

- [Structural_KG/README.md](Structural_KG/README.md)
- [graph_decoration_description/README.md](graph_decoration_description/README.md)
- [autoKG/README.md](autoKG/README.md)
- [autoKG/script/README.md](autoKG/script/README.md)
- [multi_agent_text_to_sql/semantic_agent_description/README.md](multi_agent_text_to_sql/semantic_agent_description/README.md)
- [multi_agent_text_to_sql/type_agent/README.md](multi_agent_text_to_sql/type_agent/README.md)
- [base_model_test/README.md](base_model_test/README.md)
- [test with bloked gold/README.md](test%20with%20bloked%20gold/README.md)
- [compute_pipeline_EX/README.md](compute_pipeline_EX/README.md)

## Requirements

Requirements vary by component. The main workflows use:

- Python 3.8+
- RDF and graph tooling, including `rdflib`
- LLM inference tooling, including `vllm`, `transformers`, `torch`, and `tqdm`
- SQLite databases from the target Text-to-SQL benchmark
- SLURM/GPU infrastructure for large vLLM runs

See the component-specific README files for exact inputs, paths, and execution commands.

## Notes

- Several scripts expect local benchmark paths, model paths, or cluster-specific settings to be configured before execution.
- Intermediate JSON and TTL files are intentionally kept inspectable to support debugging and ablation analysis.
- The generated RDF graph files should be checked before being used by downstream semantic agents.
