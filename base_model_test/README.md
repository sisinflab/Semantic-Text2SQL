# Base Model Test

Questa cartella contiene lo script `test_model_vllm.py`, che usa un modello vLLM per generare query SQL e salvare le predizioni in un file JSON.

## Cosa fa

Lo script:

- carica il modello indicato in `MODEL_PATH`;
- legge il dataset;
- genera le query SQL in batch;
- salva le predizioni in un file JSON chiamato `vllm_pred_sqls<nome_modello>.json`.

## Input principali

- `MODEL_PATH`: percorso del modello da caricare;
- `system_prompt.txt`: prompt di sistema usato durante la generazione;
- il dataset con question, schema linking ed evidence.

## Output

Il risultato della generazione viene salvato in JSON, con una coppia:

- `id`
- `sql`

## Uso

Esegui lo script dalla cartella del progetto con le variabili di ambiente necessarie già impostate.

```bash
python test_model_vllm.py
```

## Nota

Lo script è pensato per produrre le predizioni SQL da confrontare con i gold in una fase successiva di valutazione.