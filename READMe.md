# Multi-Agent SQL Correction Pipeline

Repository con esperimenti e pipeline per Text-to-SQL, dalla costruzione dei grafi alla generazione e correzione delle query.

## Indice

- `autoKG/` - framework per costruire knowledge graph e schema da dati testuali, con esempi, script e documentazione.
- `Structural_KG/` - costruzione di grafi RDF/Turtle a partire dagli schemi SQLite dei database.
- `graph_decoration_description/` - pipeline per arricchire i grafi con descrizioni semantiche e informazioni di supporto.
- `multi_agent_text_to_sql/semantic_agent_description/` - pipeline multi-agent che usa i grafi semantici e le descrizioni dei concetti per arricchire il dataset e generare SQL.
- `multi_agent_text_to_sql/type_agent/` - pipeline analoga alla precedente ma basata sui tipi delle colonne.
- `compute_pipeline_EX/` - analisi dei risultati delle estrazioni `base`, `type` e `description` per misurare la correzione della pipeline.
- `test with bloked gold/` - estrazione e riuso dei gold risultati per velocizzare la valutazione delle query.
- `base_model_test/` - generazione di query SQL con un modello vLLM di base e salvataggio delle predizioni.

## Sintesi

Il flusso generale del repository è:

1. costruzione o arricchimento del grafo dei database;
2. arricchimento del dataset con informazioni semantiche o strutturali;
3. generazione delle query SQL con modelli o agenti dedicati;
4. valutazione e confronto con i gold.



