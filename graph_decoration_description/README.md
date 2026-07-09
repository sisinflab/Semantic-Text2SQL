# Graph Decoration Description — README

## Panoramica

Questa cartella contiene gli strumenti e i dati per costruire, decorare e arricchire un knowledge graph semantico (RDF/Turtle) a partire dagli schemi dei database e da evidenze testuali. Il workflow include la generazione di descrizioni semantiche, la produzione di prompt, l'esecuzione di componenti automatici (auto-kg), e la creazione di grafi decorati e serializzati in TTL.

Il materiale è organizzato per database (file TTL, descrizioni, commenti di concetto) e da una serie di script per automatizzare i passaggi.

## Struttura principale

- `rdf_schema/` — TTL dei singoli database e `grafo.ttl` (ontologia/insieme delle risorse)
- `descriptions/` — file `.semantic_evidence.txt` con evidence testuali per i database
- `concept_comments/` — JSON con commenti/annotazioni per concetti specifici per ogni db
- `prompts/` & `system_prompts/` — template e prompt usati per interagire con gli LLM
- `script/` — script Python che automatizzano tutto il workflow
- `auto_kg_input/`, `auto_kg_output/` — cartelle di input/output per l'automatizzazione (auto-kg)
- `decorated_graphs/`, `generated_graphs/` — output RDF prodotti dai job
- `semantic_evidence/` — directory per evidenze estratte/aggregate

## Script principali (`script/`)

- `_0_build_prompts.py`
  - Costruisce prompt a partire da descrizioni, schema e regole, salvando i template nella cartella `prompts/`.

- `_0_generator.py`
  - Esegue un modello LLM sui prompt generati per produrre testi di supporto (es. descrizioni, suggerimenti di mapping).

- `_1_extract_semantic_evidence.py`
  - Estrae evidenza semantica dai file di input (ad es. testi, descrizioni) e normalizza i risultati per uso nei prompt.

- `_2_generate_db_descriptions.py`
  - Genera descrizioni estese per ogni database (usa gli output del generatore e le evidenze) e salva in `descriptions/`.

- `_3_call_auto_kg.py`
  - Invia l'input formattato all'automazione di KG (auto-kg) e raccoglie l'output in `auto_kg_output/`.

- `_3.5_generare_concept_descriptions.py`
  - Crea descrizioni specifiche per i singoli concetti (encapsulation) basandosi su evidence e schema.

- `_4_build_semantic_kg.py`
  - Converte gli output (mapping/descrizioni) in triple RDF e costruisce grafi parziali.

- `_4.5_create_specfic_prompt.py`
  - Genera prompt specifici per classificare ogni colonna in uno dei concetti semnatici trovati.

- `_5_cls_colums.py`
  - Chiede all agente di classificare ogni colonna in un cocnetto semnatico usando i prompot generati dallo step precedente

- `_6_build_complete_kg.py`
  - Aggrega i grafi parziali e crea `grafo.ttl` o i singoli TTL decorati.

- `job_*.sh`
  - Script batch per sottomettere i job (esecuzione LLM, auto-kg) su cluster. Adattare parametri a seconda dell'infrastruttura.

## Input e output principali

- Input primari:
  - `data/original/*` (dati grezzi, schemi, ecc.)
  - file nella cartella `descriptions/` e `prompts/`
  - eventuali file di evidence in `semantic_evidence/`

- Output:
  - `generated_graphs/` — grafi prodotti automaticamente (TTL/JSON-LD/etc.)
  - `decorated_graphs/` — grafi arricchiti con annotazioni semantiche
  - `concept_comments/*.concept_comments.json` — commenti per concetto
  - file di log e JSON intermedi in `auto_kg_output/`

## Esecuzione: ordine consigliato

1. Estrai e normalizza evidenze

```bash
python script/_1_extract_semantic_evidence.py
```

2. Genera descrizioni di database 

```bash
python script/_2_generate_db_descriptions.py
```

3. Richiama auto_kg
''' 
sbatch script/job_3_call_auto_kg.sh
'''

4. Genera descrizioni dei concetti

''' 
sbatch script/job_3.5_geenrate_concept_description.sh
'''


6. Costruisci il grafo RDF contenente i concetti

```bash
python script/_4_build_semantic_kg.py
```

7. Crea i prompt e Classifica colonne 

```bash
python script/_4.5_create_specific_prompt.py
sbatch job_5_cls_colums.sh
```

8. Controlla i TTL generati in `decorated_graphs/` e `generated_graphs/`.

## Consigli pratici e note

- Mantieni una copia di `grafo.ttl` e aggiorna solo dopo controllo manuale dei risultati.
- I job LLM richiedono risorse: usare nodi GPU con adeguata memoria per `_0_generator.py`.
- Controllare i file in `auto_kg_output/` per eventuali errori di parsing.
- I `concept_comments/*.json` possono essere usati come layer di spiegazione per agenti downstream.

