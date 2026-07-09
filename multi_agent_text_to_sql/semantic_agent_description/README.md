# Semantic Agent with Description Pipeline

## Overview

Questo pipeline implementa un approccio **multi-agente semantico potenziato** per la generazione di query SQL. A differenza della versione semplice (`semantic_agent`), introduce un **secondo agente specializzato** che genera **descrizioni dettagliate** dei concetti semantici, fornendo al modello di generazione SQL un contesto molto più ricco.

## Architettura

Il pipeline comprende tre componenti principali:

1. **Semantic Ontology (RDF)**: Grafo RDF che mappa i concetti semantici alle colonne dei database
2. **Selection Agent - Prima Scrematura**: Identifica velocemente i concetti semantici potenzialmente rilevanti
3. **Selection Agent - Raffinamento**: Valida e raffinata la selezione usando le descrizioni dal grafo RDF

## Workflow del Pipeline

### Step 0: Template Semantico (`_0_semantic_templete.py`)
- **Utility di supporto** che fornisce funzioni di query al grafo RDF
- Carica il file del grafo (grafo RDF in formato Turtle)
- Funzioni principali:
  - `get_entities_by_database()`: Recupera entità disponibili per un database
  - `concept_appears_as_semantic_meaning()`: Verifica se un concetto è presente come significato semantico

### Step 1: Generazione Prompt per Selection Agent (`_1_create_prompt_for_selection_agent.py`)
- Elabora il dataset originale e crea prompt per l'agente di selezione
- Per ogni domanda (question_id + db_id), genera un prompt che chiede all'agente di:
  - Identificare i **concetti semantici rilevanti** dalla lista disponibile
  - Elencare brevemente la loro importanza per rispondere alla domanda
- Output: `_1_generated_semantic_selection_prompts_by_id.json`

**Concetti semantici supportati**:
- `identifier`, `foreign_identifier`
- `person_name`, `person_first_name`, `person_last_name`
- `organization_name`, `school_name`, `team_name`
- `event_name`, `title`, `description_text`
- `category`, `status`, `gender`, `nationality`, `country_name`
- E molti altri...

### Step 2: Esecuzione Selection Agent - Prima Scrematura (`_2_run_agent_selection_prompts.py`)
- Esegue il modello `Qwen2.5-Coder-7B-Instruct` via vLLM
- Input: Prompt di selezione generati nello step 1
- Output: `_2_vllm_semantic_agent_selection_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Job submission: `job_2_run_agent_selection_prompts.sh`
- **Risultato**: Lista iniziale di concetti semantici identificati come rilevanti (SENZA descrizioni)
- **Scopo**: Fare una prima scrematura veloce dalla lista lunga di tutti i concetti disponibili

### Step 2.1: Generazione Prompt per Selection Agent Raffinato (`_2.1_create_prompt_for_agent.py`)
- Elabora l'output del primo Selection Agent (Step 2)
- Prende SOLO i concetti semantici già selezionati
- Per ogni concetto selezionato, genera un nuovo prompt che chiede al modello di:
  - Verificare la rilevanza del concetto usando le **descrizioni dal grafo RDF**
  - Raffinare la selezione iniziale
- **Arricchimento**: Incorpora nel prompt le descrizioni semantiche presenti nel grafo RDF per i concetti selezionati
- Output: `_2.1_generated_semantic_prompts_by_id.json`

### Step 2.2: Esecuzione Selection Agent Raffinato (`_2.2_run_agent_prompts.py`)
- Esegue il modello LLM per la SECONDA SELEZIONE
- Input: Prompt raffinati con descrizioni da RDF (Step 2.1)
- Output: `_2.2_vllm_semantic_agent_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Job submission: `job_2.2_run_agent_prompts_vllm.sh`
- **Risultato**: Lista finale, raffinata e validata di concetti semantici rilevanti
- **Scopo**: Fare una seconda selezione più accurata usando il contesto semantico del grafo

### Step 3: Estrazione Informazioni Semantiche (`_3_extract_semantic_info.py`)
- Elabora l'output del Description Agent
- Estrae i concetti semantici selezionati con le loro descrizioni
- Interroga il grafo RDF per ottenere le colonne associate a ogni concetto
- Crea un mapping strutturato: concetto → descrizione → colonne del database
- Output: `_3_dataset_with_semantic_info.json`

### Step 4: Arricchimento Dataset Originale (`_4_add_semantic_info_to_original_dataset.py`)
- Integra le informazioni semantiche nel dataset originale
- Aggiunce per ogni domanda:
  - Lista di concetti semantici selezionati
  - Descrizioni dettagliate di ogni concetto
  - Mapping colonne → concetti semantici
  - Contesto della descrizione
- Cosi si ottiene un informazione semantica specifica per ogni domanda
- Output: `_4_source_dataset_with_columns_by_semantic_concept.json`

### Step 5: Generazione SQL con Contesto Semantico Arricchito (`_5_execute_sql_generation_with_semantic.py`)
- Genera query SQL utilizzando il modello LLM
- **Arricchimento massimo del prompt**: Include:
  - Schema del database
  - Domanda naturale
  - Concetti semantici rilevanti
  - **Descrizioni dettagliate** di ogni concetto
  - Mapping di quali colonne rappresentano quali concetti
  - Contesto semantico dal Description Agent
- Output: `_5_vllm_execute.json` (predizioni SQL finale)
- Job submission: `job_5_vllm_execute_sql_with_semantic.sh`

## File Principali

### Input
- Dataset originale: "path/to/dataset.json" 
- Grafo RDF: `grafo.ttl` (formato Turtle, contiene la struttura semantica dei database)

### Output Intermedi
- Step 1: `_1_generated_semantic_selection_prompts_by_id.json`
- Step 2: `_2_vllm_semantic_agent_selection_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Step 2.1: `_2.1_generated_semantic_prompts_by_id.json`
- Step 2.2: `_2.2_vllm_semantic_agent_outputs_Qwen2.5-Coder-7B-Instruct_*.json`
- Step 3: `_3_dataset_with_semantic_info.json`
- Step 4: `_4_source_dataset_with_columns_by_semantic_concept.json`

### Output Finale
- `_5_vllm_execute.json` - Query SQL generate con contesto semantico arricchito

## Esecuzione

### Prerequisiti
- Python 3.x con librerie: `rdflib`, `transformers`, `vllm`, `torch`, `tqdm`
- Modello Qwen2.5-Coder-7B-Instruct disponibile
- Grafo RDF `grafo.ttl` nella cartella
- Accesso a infrastrutture GPU su CINECA

### Esecuzione Step-by-Step
```bash
# Step 0: (Utility - usato dagli altri script)
# Non eseguire direttamente

# Step 1: Generazione prompt per Selection Agent
python _1_create_prompt_for_selection_agent.py

# Step 2: Esecuzione Selection Agent (via SLURM su CINECA)
sbatch job_2_run_agent_selection_prompts.sh

# Step 2.1: Generazione prompt per Description Agent
python _2.1_create_prompt_for_agent.py

# Step 2.2: Esecuzione Description Agent (via SLURM su CINECA)
sbatch job_2.2_run_agent_prompts_vllm.sh

# Step 3: Estrazione informazioni semantiche
python _3_extract_semantic_info.py

# Step 4: Arricchimento dataset originale
python _4_add_semantic_info_to_original_dataset.py

# Step 5: Generazione SQL con contesto semantico (via SLURM su CINECA)
sbatch job_5_vllm_execute_sql_with_semantic.sh
```

## Flusso Logico

```
Domanda in linguaggio naturale
         ↓
   [Step 1] Crea prompt con TUTTI i concetti disponibili
         ↓
   [Step 2] Prima selezione veloce (lista lunga → lista più corta)
         ↓
   [Step 2.1] Crea prompt per i soli concetti selezionati + descrizioni da RDF
         ↓
   [Step 2.2] Seconda selezione raffinata usando descrizioni semantiche
         ↓
   [Step 3] Mapping: Concetti raffinati → Descrizioni → Colonne
         ↓
   [Step 4] Arricchimento dataset con concetti semantici validati
         ↓
   [Step 5] Generazione SQL con contesto semantico raffinato
         ↓
     Query SQL ottimizzata
```

## Vantaggi Rispetto alla Versione Semplice

1. **Due Fasi di Selezione**: Prima scrematura veloce per ridurre il set, poi raffinamento con descrizioni
2. **Selezione Consapevole del Contesto**: La seconda selezione usa le descrizioni RDF per valutare rilevanza
3. **Riduzione Rumore**: Filtra i concetti "falsi positivi" della prima selezione veloce
4. **Interpretazione Semantica Profonda**: Il modello valuta concetti non solo per nome, ma per descrizione
5. **Efficienza Computazionale**: Due agenti più leggeri invece di uno pesante
6. **Tracciabilità**: È possibile confrontare la prima e seconda selezione per capire il raffinamento

## Architettura dei Due Selection Agent

### Selection Agent - Fase 1 (Scrematura Veloce)
```
Input: Domanda + Schema + Lista COMPLETA di concetti
Processo: Analizza la domanda, seleziona concetti potenzialmente rilevanti
Output: [concetto_1, concetto_2, ...] (lista ristretta)
Nota: Non usa descrizioni RDF
```

### Selection Agent - Fase 2 (Raffinamento con Descrizioni)
```
Input: Domanda + Concetti selezionati in Fase 1 + Descrizioni RDF per questi concetti
Processo: Valida rilevanza usando contesto semantico del grafo RDF
Output: [concetto_1, concetto_2, ...] (lista ancora più raffinata)
Nota: Usa le descrizioni dal grafo per decisioni più accurate
```

### SQL Generation
```
Input: Domanda + Schema + Concetti (dalla Fase 2) + Mapping colonne
Processo: Genera query SQL usando i concetti semantici validati
Output: Query SQL
```

## Note Importanti

- Il grafo RDF deve essere mantenuto aggiornato quando lo schema del database cambia
- I concetti semantici predefiniti possono essere estesi aggiungendo nuove entry nella lista
- Il pipeline è ottimizzato per esecuzione su CINECA con accesso a infrastrutture GPU
- Ogni step produce file JSON intermedi che possono essere ispezionati per debugging
- Gli step 2, 2.2 e 5 richiedono tempo significativo e sono configurati per esecuzione via SLURM
- La prima selezione (Step 2) è veloce e serve solo come filtro iniziale
- La seconda selezione (Step 2.2) è più accurata perché usa il contesto semantico del grafo RDF
- È possibile confrontare gli output di Step 2 e Step 2.2 per capire come le descrizioni RDF influenzano le selezioni
- Il costo computazionale è simile alla versione semplice.
