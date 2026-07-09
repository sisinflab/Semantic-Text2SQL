# Multi-Agent SQL Correction Pipeline

This repository contains experiments and pipelines for Text-to-SQL, covering the full workflow from knowledge graph construction to SQL query generation, semantic refinement, correction, and evaluation.

The repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the **ISWC 2026 Industry Track**.

The work is developed in collaboration with the **IBM T.J. Watson Research Center**.

## Index

- `autoKG/` - framework for building knowledge graphs and schemas from textual data, with examples, scripts, and documentation.
- `Structural_KG/` - construction of RDF/Turtle graphs from SQLite database schemas.
- `graph_decoration_description/` - pipeline for enriching graphs with semantic descriptions and supporting information.
- `multi_agent_text_to_sql/semantic_agent_description/` - multi-agent pipeline that uses semantic graphs and concept descriptions to enrich the dataset and generate SQL.
- `multi_agent_text_to_sql/type_agent/` - pipeline analogous to the semantic-agent pipeline, but based on column data types.
- `compute_pipeline_EX/` - analysis of the `base`, `type`, and `description` extraction results to measure pipeline correction behavior.
- `test with bloked gold/` - extraction and reuse of gold results to speed up query evaluation.
- `base_model_test/` - SQL query generation with a base vLLM model and prediction saving.

## Summary

The general repository workflow is:

1. build or enrich the database graph;
2. enrich the dataset with semantic or structural information;
3. generate SQL queries with dedicated models or agents;
4. evaluate and compare predictions against gold outputs.

## Component Documentation

Each component includes a dedicated README with local usage instructions:

- [autoKG/README.md](autoKG/README.md)
- [autoKG/script/README.md](autoKG/script/README.md)
- [Structural_KG/README.md](Structural_KG/README.md)
- [graph_decoration_description/README.md](graph_decoration_description/README.md)
- [multi_agent_text_to_sql/semantic_agent_description/README.md](multi_agent_text_to_sql/semantic_agent_description/README.md)
- [multi_agent_text_to_sql/type_agent/README.md](multi_agent_text_to_sql/type_agent/README.md)
- [compute_pipeline_EX/README.md](compute_pipeline_EX/README.md)
- [test with bloked gold/README.md](test%20with%20bloked%20gold/README.md)
- [base_model_test/README.md](base_model_test/README.md)

## Requirements

Requirements vary by component. The main workflows use Python, RDF tooling such as `rdflib`, LLM inference tooling such as `vllm`, `transformers`, and `torch`, SQLite benchmark databases, and SLURM/GPU infrastructure for large model runs.

See the component-specific README files for exact inputs, paths, and execution commands.
