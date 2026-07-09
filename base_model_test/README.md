# Base Model Test

This repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the ISWC 2026 Industry Track, and is developed in collaboration with the **IBM T.J. Watson Research Center**.

This folder contains `test_model_vllm.py`, which uses a vLLM model to generate SQL queries and save predictions to a JSON file.

## What It Does

The script:

- loads the model specified in `MODEL_PATH`;
- reads the dataset;
- generates SQL queries in batches;
- saves predictions to a JSON file named `vllm_pred_sqls<model_name>.json`.

## Main Inputs

- `MODEL_PATH`: path to the model to load;
- `system_prompt.txt`: system prompt used during generation;
- the dataset with questions, schema linking, and evidence.

## Output

The generation result is saved as JSON entries containing:

- `id`
- `sql`

## Usage

Run the script from the project folder with the required environment variables already configured.

```bash
python test_model_vllm.py
```

## Note

This script is intended to produce SQL predictions that can later be compared against gold outputs during evaluation.
