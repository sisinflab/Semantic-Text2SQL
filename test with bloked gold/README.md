# Test con gold bloccati

Questa cartella contiene due script usati per separare la preparazione dei dati gold dalla verifica dei risultati prodotti dalla pipeline.

## `extract_gold_fields.py`

Questo script estrae i campi gold da un file JSON di valutazione e li salva in un file più leggero, di default `gold_only.json`.

Lo scopo è conservare solo le informazioni necessarie per la valutazione successiva, in particolare:

- `question_id`
- `question`
- `gold_result`
- `gold_error`

In questo modo il risultato gold viene calcolato una sola volta e può essere riutilizzato nelle esecuzioni successive, velocizzando i test e riducendo il costo delle valutazioni ripetute.

Esempio di utilizzo:

```bash
python extract_gold_fields.py --input base.json --output gold_only.json
```

## `test_sql.py`

Questo script serve a testare il risultato prodotto dalla pipeline.

Legge:

- il dataset di riferimento con le domande e le query gold,
- il file `base.json` con le predizioni della pipeline,
- il file `gold_only.json` generato dallo script precedente.

Poi confronta i risultati e calcola le metriche di valutazione, tra cui:

- exact match tra SQL predetto e SQL gold,
- similarità testuale,
- execution match sul database SQLite,
- conteggio di errori, timeout e casi mancanti.

In sintesi:

- `extract_gold_fields.py` prepara e salva i risultati gold una volta sola;
- `test_sql.py` usa quei risultati salvati per verificare rapidamente se l’output della pipeline coincide con il gold.

Esempio di utilizzo:

```bash
python test_sql.py
```

## Flusso consigliato

1. Eseguire `extract_gold_fields.py` per creare `gold_only.json`.
2. Eseguire `test_sql.py` per confrontare le predizioni della pipeline con i gold già salvati.

## Note

- I percorsi dei file possono essere adattati se il dataset o le predizioni sono in una cartella diversa.
- Se il file `gold_only.json` è già presente e aggiornato, non è necessario rieseguire l’estrazione dei gold a ogni test.