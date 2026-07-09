# Compute Pipeline EX

Questa cartella contiene lo script `compute_results.py`, usato per calcolare come opera la pipeline di correzione a partire dai risultati delle diverse estrazioni.

## Scopo dello script

Lo script confronta tre file JSON di input:

- `base.json`
- `type.json`
- `description.json`

L’obiettivo è misurare quante query sbagliate nella fase base vengono corrette dai passaggi successivi della pipeline, separando i contributi del primo e del secondo stadio di correzione.

## Come funziona

`compute_results.py` carica i tre JSON e usa `question_id` come chiave di allineamento tra i vari risultati.

Il flusso è il seguente:

1. parte dai casi con errore presenti in `base.json`;
2. verifica se `description.json` riesce a correggere quei casi;
3. sui residui non risolti, verifica se `type.json` riesce a correggerli;
4. aggrega i risultati per categoria di errore, ad esempio:
   - `Ambiguous Column`
   - `No Such Column`
   - `Syntax Error`
   - `Altro`

In questo modo si può capire in modo semplice e ripetibile quanto ogni fase della pipeline contribuisce alla correzione finale.

## Output

Lo script stampa a video un report aggregato con:

- numero di casi risolti nel primo step;
- numero di casi risolti nel secondo step;
- totale per categoria di errore;
- riepilogo finale dei question id corretti;
- salvataggio dei risultati in `2_report_results.json`.

## Uso

Esegui lo script dalla cartella del progetto:

```bash
python compute_results.py
```

I file `base.json`, `description.json` e `type.json` devono essere presenti nel percorso atteso dallo script, altrimenti i caricamenti falliranno.

## Nota

Questo script non genera le estrazioni, ma analizza i loro risultati per capire come la pipeline di correzione si comporta tra base, description e type.