# Compute Pipeline EX

This repository supports the paper **"Unified Knowledge Graphs for Adaptive Semantic Refinement in Text-to-SQL"**, submitted to the ISWC 2026 Industry Track, and is developed in collaboration with the **IBM T.J. Watson Research Center**.

This folder contains `compute_results.py`, a script used to measure how the correction pipeline behaves across the results of different extraction stages.

## Script Purpose

The script compares three input JSON files:

- `base.json`
- `type.json`
- `description.json`

The goal is to measure how many queries that fail in the base stage are corrected by the subsequent pipeline steps, separating the contributions of the first and second correction stages.

## How It Works

`compute_results.py` loads the three JSON files and uses `question_id` as the alignment key across the result sets.

The workflow is:

1. start from the error cases in `base.json`;
2. check whether `description.json` corrects those cases;
3. for the remaining unresolved cases, check whether `type.json` corrects them;
4. aggregate the results by error category, for example:
   - `Ambiguous Column`
   - `No Such Column`
   - `Syntax Error`
   - `Other`

This makes it possible to understand, in a simple and reproducible way, how much each pipeline stage contributes to the final correction.

## Output

The script prints an aggregated report with:

- number of cases solved in the first step;
- number of cases solved in the second step;
- total by error category;
- final summary of corrected question IDs;
- saved results in `2_report_results.json`.

## Usage

Run the script from the project folder:

```bash
python compute_results.py
```

The files `base.json`, `description.json`, and `type.json` must be available at the paths expected by the script; otherwise, loading will fail.

## Note

This script does not generate extraction outputs. It analyzes their results to show how the correction pipeline behaves across the base, description, and type stages.
