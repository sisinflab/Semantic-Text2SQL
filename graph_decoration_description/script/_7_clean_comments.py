import re
from rdflib import Graph, RDFS, Literal

# 1. Carica il grafo (sostituisci 'tuo_grafo.ttl' con il percorso del tuo file e imposta il formato corretto)
g = Graph()
g.parse("decorated_graphs/grafo.ttl", format="turtle")

contatore = 0

# 2. Itera su tutte le triple che hanno rdfs:comment come predicato
for soggetto, predicato, oggetto in g.triples((None, RDFS.comment, None)):
    testo_originale = oggetto.value
    
    # Controlla se il tag </think> è presente nel commento
    if "</think>" in testo_originale:
        contatore += 1
        
        # Regex per eliminare tutto ciò che precede </think> (incluso il tag e spazi/a capo successivi)
        testo_ripulito = re.sub(r"^.*?<\/think>\s*", "", testo_originale, flags=re.DOTALL)
        
        # Rimuovi la tripla vecchia dal grafo
        g.remove((soggetto, predicato, oggetto))
        
        # Aggiungi la tripla aggiornata con il testo ripulito (mantenendo la lingua se c'era)
        nuovo_oggetto = Literal(testo_ripulito, lang=oggetto.language)
        g.add((soggetto, predicato, nuovo_oggetto))

# 3. Salva il grafo ripulito
g.serialize(destination="grafo_ripulito.ttl", format="turtle")

print(f"Operazione completata! Trovati e corretti {contatore} commenti.")