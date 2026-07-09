# Script Order

These scripts now use `graph_decoration/script/_0_generator.py` as the LLM entrypoint.

1. `build_extraction_json.py`
   Builds `extraction_input/*.json` from `semantic_evidence/*.semantic_evidence.json`.

2. `run_schema_induction.py`
   Runs triple extraction, CSV conversion, concept generation, schema induction, and GraphML export for one database.

3. `run_full_pipeline.py`
   Convenience runner that executes steps 1 and 2 in sequence.

4. `generator_adapter.py`
   Adapter layer that lets AutoKG call the shared `_0_generator` utilities used by the rest of `graph_decoration`.

## Typical commands

Build extraction input only:

```powershell
python autoKG\script\build_extraction_json.py
```

Run extraction plus schema induction for one DB:

```powershell
python autoKG\script\run_schema_induction.py --keyword california_schools
```

Run extraction with an explicit local model path:

```powershell
python autoKG\script\run_schema_induction.py --keyword california_schools --model-path /path/to/Qwen2.5-Coder-7B-Instruct
```

Run the full pipeline for one DB:

```powershell
python autoKG\script\run_full_pipeline.py --keyword california_schools
```

Run the full pipeline for all DBs:

```powershell
python autoKG\script\run_full_pipeline.py --all
```
