# Type Agent — pipeline per informazioni di tipo

## Panoramica

Questa cartella contiene gli script per selezionare e inserire informazioni sul tipo di dato delle colonne (INTEGER, REAL, TEXT, DATE, DATETIME) nel flusso Text-to-SQL. Il pipeline supporta due modalità operative:

- tramite il grafo RDF (SPARQL) — utile quando si integra questo agente con altri agenti che usano l'ontologia;
- tramite lo schema SQLite (SQL) — utile quando l'agente viene eseguito in modalità standalone senza RDF.

Entrambi i template (`_0_templete_sparql.py` e `_0_templete_sql.py`) sono mantenuti e servono a garantire flessibilità d'uso. La Pipeline attualemnte usa `_0_templete_sparql.py` ma è facilmente modificabile.

## Requisiti

- Python 3.8+
- Librerie: rdflib, vllm, transformers, torch, tqdm
- File RDF `grafo.ttl` (se si usa la modalità SPARQL)
- Cartella `data/original/dev_databases/<db_id>/<db_id>.sqlite` (se si usa la modalità SQL)
- Variabile d'ambiente `MODEL_PATH` per gli script vLLM (oppure eseguire localmente con `use_agent_local.py`)

## File principali e descrizione aggiornata

- `_1_agent.py`
  - Genera i prompt chiedendo quali data types sono necessari per ciascuna domanda.
  - Input: "path/to/dataset.json" 
  - Output: `_1_generated_prompts_by_id.json`
  - Uso: `python _1_agent.py`

- `_2_run_prompts_vllm.py` + `_2_job_run_prompts_vllm.sh`
  - Esegue i prompt su vLLM e normalizza l'output in JSON strutturato.
  - Input: `_1_generated_prompts_by_id.json` e `MODEL_PATH`
  - Output: `_2_vllm_type_selection_agent_outputs.json`
  - Uso: `MODEL_PATH=/path/to/model python _2_run_prompts_vllm.py`

- `_3_create_dataset_with_data_type.py`
  - Elabora l'output del type-agent, interroga il grafo RDF (tramite `_0_templete_sparql.py`) per ottenere le colonne associate ai tipi selezionati e produce `_3_dataset_with_sparql_types.json`.
  - Se non è presente il grafo, lo script può essere adattato per lavorare con dati SQL.
  - Uso: `python _3_create_dataset_with_data_type.py`

- `_4_add_type_info_in_original.py`
  - Unisce il file prodotto dallo step precedente col dataset originale creando `_4_source_dataset_with_columns_by_type.json`.
  - Uso: `python _4_add_type_info_in_original.py`

- `_5_vllm_with_type.py` + `_5_job_vllm_with_type.sh`
  - Genera query SQL usando il dataset arricchito (tipi e mapping colonne). Tipicamente eseguito su cluster.
  - Uso: `MODEL_PATH=/path/to_model python _5_vllm_with_type.py` o tramite `_5_job_vllm_with_type.sh`

- `_0_templete_sparql.py`
  - Contiene le utility per interrogare il grafo RDF `grafo.ttl`.
  - Funzione principale: `query_columns_by_type_sparql(database_name, data_type)`.

- `_0_templete_sql.py`
  - Contiene le utility per leggere schemi SQLite e ottenere colonne per tipo direttamente dallo schema.
  - Funzione principale: `query_columns_by_type_sql(database_name, data_type)`.

- `_0_check_sparql_sql_match.py`
  - Confronta i risultati ottenuti tramite SPARQL e quelli ottenuti tramite query SQL sullo schema, utile per validare la coerenza tra RDF e database reale.

File di esempio già presenti: `_3_dataset_with_sparql_types.json`, `_4_source_dataset_with_columns_by_type.json`, `_2_vllm_type_selection_agent_outputs.json`, `_5_pred_with_type.json`.

## Modalità operative e raccomandazioni

- Modalità SPARQL (consigliata se si integra con altri agenti semantici): usa `_0_templete_sparql.py` per mappare tipi su colonne tramite l'ontologia RDF. Permette di sfruttare descrizioni e concetti semantici condivisi.
- Modalità SQL (standalone): usa `_0_templete_sql.py` per estrarre tipi direttamente dallo schema SQLite, utile quando non è disponibile il grafo RDF.
- I template SPARQL e SQL sono mantenuti entrambi per permettere transizione o funzionamento parallelo.

## Ordine consigliato di esecuzione (pulito)

1. Generare i prompt per il type-selection

```bash
python _1_agent.py
```

2. Eseguire i prompt con vLLM

```bash
MODEL_PATH=/path/to_model python _2_run_prompts_vllm.py
# oppure usare _2_job_run_prompts_vllm.sh su cluster
```

3. Creare il dataset con le colonne mappate per tipo (SPARQL o SQL)

```bash
python _3_create_dataset_with_data_type.py
```

4. Unire le informazioni al dataset originale

```bash
python _4_add_type_info_in_original.py
```

5. (Opzionale) Verificare coerenza SPARQL vs SQL

```bash
python _0_check_sparql_sql_match.py
```

6. Generare le query SQL usando il dataset arricchito

```bash
# su cluster
sbatch _5_job_vllm_with_type.sh

# in locale (assicurarsi MODEL_PATH)
MODEL_PATH=/path/to_model python _5_vllm_with_type.py
```

## Note pratiche

- Verificare il percorso del file TTL in `_0_templete_sparql.py`.
- Controllare che i file `.sqlite` siano presenti in `data/original/dev_databases/<db_id>/`.
- I file intermedi (prompt, output vLLM, dataset con tipi) sono utili per debug e possono essere ispezionati manualmente.
- Adattare gli script di job (`.sh`) alle risorse del cluster (GPU, RAM, tempo).
