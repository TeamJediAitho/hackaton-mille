# Scoring, soglie e fairness

Questa è la scheda pratica per capire che cosa viene misurato e quali
comportamenti conviene rendere osservabili. La gara ha due Act con documenti
progressivi (il secondo è volutamente ricco e difficile), poi una Gold Run
finale con domande nuove sullo stesso archivio completo.

Il punteggio tecnico vale 90 punti. La Historical Review aggiunge fino a 10
punti dopo la Gold Run: il totale è 100.

## Quadro unico del punteggio

| Area | Metrica | Punti | Che cosa significa | Comportamento premiato |
| --- | --- | ---: | --- | --- |
| Retrieval | Recall@5 | 20 | Quante delle evidenze rilevanti finiscono nei primi cinque contesti | Cercare in modo da non perdere le fonti utili |
| Retrieval | Precision fino a 5 | 10 | Quanto sono pertinenti i contesti che scegliete, fino a cinque | Passare al generatore contesti pertinenti, non solo molti |
| Retrieval | Hit@5 | 5 | Se almeno un’evidenza rilevante compare nei primi cinque | Mettere almeno una fonte utile nella shortlist |
| Retrieval | Qualità del ranking | 5 | Quanto le fonti migliori sono ordinate in alto | Portare prima le evidenze più decisive |
| Generation | Faithfulness | 18 | Quanto le affermazioni della risposta sono sostenute dai contesti forniti al generatore | Citare e usare soltanto ciò che i contesti sostengono; dichiarare i limiti |
| Generation | Answer Correctness | 12 | Correttezza della risposta rispetto alla domanda e alle evidenze | Rispondere alla domanda senza aggiungere dettagli non giustificati |
| Generation | Historical Reasoning | 5 | Qualità del ragionamento storico richiesto dalla domanda | Distinguere fatti, interpretazioni, conflitti e assenza di prova |
| Sistema | Latenza | 7 | Tempo wall-clock end-to-end per domanda | Tenere la pipeline entro la soglia utile senza sacrificare l’affidabilità |
| Sistema | Costo | 8 | Costo medio autodichiarato in EUR per domanda | Scegliere modelli e numero di chiamate con costi tracciabili |
| Finale | Historical Review | 10 | Valutazione della presentazione orale dopo la Gold Run | Portare fonti, metodo, limiti e una tesi storica difendibile |

Non sono pubblicate qui formule o pesi più granulari delle voci sopra. Non assumete che aggiungere contesti o chiamate migliori automaticamente il punteggio: verificate l’effetto con una valutazione riproducibile.

## Retrieval: esempi per decidere che cosa passare al modello

### Caso buono

La domanda chiede quali preparativi concreti siano stati ordinati. Nei primi cinque contesti mettete prima la lettera che contiene l’ordine, poi la fonte che ne conferma data e quantità, infine eventuali fonti di confronto. Ogni contesto ha un `document_id` corretto e il testo realmente passato al generatore.

Questo comportamento tende a sostenere recall, precision e ranking.

### Caso debole

Per la stessa domanda mettete cinque frammenti vagamente legati allo sbarco, lasciando fuori la lettera con l’ordine. Anche se la risposta “suona” storica, la pipeline ha perso l’evidenza decisiva: la precisione o il recall possono risentirne e il generatore avrà basi più fragili.

`Top-5` indica i contesti finali passati al generatore, nello stesso ordine del ranking. Non ricostruite o correggete i contesti dopo aver generato la risposta.

## Generation: esempi di faithfulness

### Faithful

I contesti dicono che una fonte segnala dodici carri e che manca una firma.
La risposta ripete questi elementi, attribuendoli alla fonte, e dice che
sono indizi logistici: non li trasforma in una prova di accordo politico.

### Non faithful

I contesti parlano di movimenti e preparativi, ma non riportano una data precisa. La risposta aggiunge una data presa dalla memoria del modello o da una fonte non recuperata. Anche se la data fosse storicamente corretta, non è sostenuta dai contesti effettivamente forniti.

Ogni contesto caricato viene confrontato con il corpus tramite supporto testuale normalizzato. Se il contenuto non è riconducibile al documento indicato, la domanda viene segnalata e la Faithfulness della domanda è zero.

L’algoritmo è conservativo: i casi di OCR difficile devono essere moderati e
documentati.

## Latenza

La latenza è wall-clock end-to-end per domanda. Le soglie di riferimento sono:

| Latenza per domanda | Punti |
| --- | ---: |
| ≤ 4 s | 7 |
| ≤ 8 s | 5 |
| ≤ 15 s | 3 |
| ≤ 25 s | 1 |
| > 25 s | 0 |

Misurate la stessa porzione di pipeline che dichiarate e conservate il comando o il log usato per la misura. Questa pagina non specifica come viene aggregata la latenza tra domande: se vi serve quel dettaglio, chiedete o verificate il regolamento della piattaforma.

## Costo medio

I modelli sono liberi. Per ogni domanda autodichiarate il costo in EUR in `telemetry.declared_cost_eur`; dichiarate anche `latency_ms` e, per audit, `model_calls`.

La piattaforma applica le fasce al valore medio dichiarato:

| Costo medio per domanda | Punti |
| --- | ---: |
| ≤ €0,005 | 8 |
| ≤ €0,02 | 6 |
| ≤ €0,05 | 3 |
| ≤ €0,10 | 1 |
| > €0,10 | 0 |

Esempio di calcolo: sommate i costi dichiarati delle domande e dividete per il numero di domande valutate. Conservate però il dettaglio per
domanda e le chiamate modello, così il valore medio è auditabile. La fonte
ufficiale parla di valore medio, ma non definisce qui eventuali regole di
arrotondamento.

Dichiarazioni palesemente implausibili possono essere moderate dalla giuria.
Il testo disponibile non descrive la formula o l’entità della moderazione:
non trattatela come una soglia aggiuntiva nota.

## Rifiuto, zero e penalizzazione: non confonderli

Questa pagina documenta soltanto gli esiti esplicitamente descritti:

- **Zero di una componente:** una metrica può assegnare 0, per esempio
  Faithfulness quando un contesto non è supportato, latenza oltre 25 secondi o costo medio oltre €0,10. Non significa automaticamente che l’intera submission valga zero.
- **Segnalazione per moderazione:** OCR difficile e costi palesemente
  implausibili sono casi da documentare o moderare; il testo non stabilisce
  una penalità numerica automatica.

Non è definita qui una penalizzazione generale diversa dagli esiti sopra.
Quando annotate un caso ambiguo, riportate il messaggio della piattaforma,
il file coinvolto e la decisione dell’organizzazione.

## Come usare il punteggio per migliorare

Prima di cambiare la pipeline, registrate domanda, Act o Gold, contesti
recuperati, risposta, latenza, costo e comando eseguito. Poi cambiate una
variabile alla volta quando possibile e conservate prima/dopo. Un risultato
non riproducibile è un indizio, non ancora una conclusione.
