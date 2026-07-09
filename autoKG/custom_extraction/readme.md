# Custom Extraction Assets

This directory now only keeps the prompt and schema assets used by the local `autoKG` pipeline.

## Kept for this project

- `custom_benchmark/custom_prompt.json`
- `custom_benchmark/custom_schema.json`

These two files are used by:

- [run_schema_induction.py](</c:/Users/de_le/OneDrive/Desktop/Code/autoKG/script/run_schema_induction.py>)

They define:

- the triple extraction prompt
- the expected JSON schema for extracted triples

The old benchmarking and standalone demo scripts were removed because they are not part of the current pipeline.
