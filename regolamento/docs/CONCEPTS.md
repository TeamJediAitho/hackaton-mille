# Concetti chiave — mini-manuale

Qui trovate i termini che ricorrono nell'hackathon. Per ogni voce: prima una spiegazione semplice, poi un esempio e infine il motivo per cui è utile tenerla presente. Le definizioni sono volutamente operative: servono a decidere cosa cambiare nella pipeline e come raccontarlo a un futuro sviluppatore.

## RAG e archivio

### RAG (Retrieval-Augmented Generation)

**In parole semplici:** una pipeline che prima cerca evidenze nell'archivio e poi chiede a un modello di formulare una risposta usando quelle evidenze.

**Esempio:** per una domanda su una spedizione, il retriever trova tre carte; il generatore risponde soltanto sulla base del testo di quelle carte.

**Perché conta:** separare ricerca e scrittura aiuta a capire se un errore nasce dal recupero sbagliato o dall'interpretazione del modello.

### Corpus

**In parole semplici:** l'insieme delle fonti che la pipeline può consultare in una determinata fase.

**Esempio:** prima della Gold il corpus è Act 1 + Act 2; la Gold usa lo stesso corpus, non un archivio ricostruito a memoria.

**Perché conta:** un documento fuori dal corpus non può essere usato come evidenza valida, anche se il suo contenuto sembra corretto.

### Manifest

**In parole semplici:** il catalogo ufficiale del corpus, con identità, atto, modalità, origine e riferimenti ai file.

**Esempio:** `data/manifest.json` dice quali file appartengono a un `document_id` e come interpretarli.

**Perché conta:** ingestione, validazione e audit si basano sul manifest; un file presente in `data/` ma assente dal catalogo non è automaticamente disponibile.

### Document ID

**In parole semplici:** l'identificatore stabile di un documento nel manifest.

**Esempio:** un contesto deve citare `document_id: "garib_d05"`, non un nome inventato o il percorso locale del PDF.

**Perché conta:** permette di collegare la risposta alla fonte e consente alla piattaforma di verificare il contesto dichiarato.

### Provenance

**In parole semplici:** la storia ricostruibile di una fonte: origine, URL, licenza, trasformazioni e hash quando disponibili.

**Esempio:** annotare che un PDF è stato scaricato da un URL, sottoposto a OCR e indicizzato in una certa versione.

**Perché conta:** una risposta è più difendibile quando si sa da quale file arriva e quali trasformazioni possono averne alterato il testo.

## Come funziona la ricerca

### Chunk

**In parole semplici:** un pezzo più piccolo ricavato da un documento per poterlo indicizzare e recuperare.

**Esempio:** una lettera di dieci pagine viene divisa in blocchi che mantengono abbastanza contesto senza diventare enormi.

**Perché conta:** chunk troppo corti perdono il filo; troppo lunghi mescolano temi e sprecano contesto. Ogni modifica va verificata sui casi reali.

### Embedding

**In parole semplici:** una rappresentazione numerica del significato approssimato di un testo.

**Esempio:** domanda e chunk che parlano entrambi di una partenza possono avere vettori vicini anche se non condividono le stesse parole.

**Perché conta:** gli embedding alimentano la ricerca semantica, ma possono confondere persone, date, negazioni o documenti con tono simile.

### Retrieval

**In parole semplici:** la fase che seleziona dall'indice i chunk più utili per la domanda.

**Esempio:** data una domanda, il retriever restituisce i cinque candidati più promettenti prima della generation.

**Perché conta:** se la carta decisiva non entra nei contesti, un prompt perfetto non può recuperarla per magia.

### Top-k

**In parole semplici:** il numero massimo di risultati che passano alla fase successiva.

**Esempio:** `top-k = 5` significa portare al generatore al massimo cinque contesti, ordinati dal rank 1 al rank 5.

**Perché conta:** k più alto aumenta la copertura ma può portare rumore, costo e conflitti; nella submission il limite è cinque contesti.

### Reranking

**In parole semplici:** un secondo ordinamento dei candidati recuperati, con un modello o regole più precise rispetto alla prima ricerca.

**Esempio:** la ricerca semantica recupera dieci chunk; un reranker porta in cima quello che contiene la data e il soggetto richiesti.

**Perché conta:** può migliorare il ranking senza cambiare tutto l'indice, ma va misurato: più latenza o costo non garantiscono una risposta migliore.

### Precision e recall

**In parole semplici:** la precisione misura quanti risultati recuperati sono pertinenti; il recall misura quante delle evidenze pertinenti siete riusciti a recuperare.

**Esempio:** recuperare 5 chunk di cui 4 utili dà precision alta; perderne uno tra le 2 evidenze necessarie abbassa il recall.

**Perché conta:** aiutano a distinguere «ho trovato troppo rumore» da «non ho trovato la carta che serviva», due problemi con fix diversi.

## Come si produce una risposta affidabile

### Grounding

**In parole semplici:** ancorare ogni affermazione ai contesti forniti al generatore.

**Esempio:** se nei contesti compare soltanto «partì in primavera», la risposta non deve trasformarlo in una data precisa.

**Perché conta:** il grounding riduce dettagli plausibili ma non dimostrati e rende la risposta verificabile.

### Faithfulness

**In parole semplici:** quanto le affermazioni della risposta sono sostenute dai contesti effettivamente passati al modello.

**Esempio:** una data storicamente vera ma assente nei contesti non è faithful in quella submission.

**Perché conta:** la metrica premia il legame tra risposta ed evidenza, non la conoscenza generale del modello; un contesto non supportato può portare Faithfulness a zero per la domanda.

### Answer Correctness

**In parole semplici:** quanto la risposta copre i fatti richiesti e rispetta i vincoli della domanda e della rubric.

**Esempio:** elencare due persone quando la domanda ne chiede tre è incompleto, anche se le due citate sono corrette.

**Perché conta:** una risposta può essere fedele ai contesti ma non rispondere davvero alla domanda; le due qualità vanno controllate separatamente.

### Abstention

**In parole semplici:** dichiarare esplicitamente che l'archivio non consente una conclusione abbastanza solida.

**Esempio:** «Le fonti disponibili non permettono di stabilire chi abbia scritto la lettera» quando i documenti sono contraddittori o incompleti.

**Perché conta:** ammettere un limite è meglio che inventare certezza, soprattutto davanti a propaganda, OCR incerto o fonti contestate.

### Historical Reasoning

**In parole semplici:** ragionare sul tipo e sul limite delle fonti, non soltanto estrarre parole.

**Esempio:** distinguere una testimonianza diretta da un volantino propagandistico e segnalare che una versione successiva corregge una bozza.

**Perché conta:** l'archivio contiene contraddizioni intenzionali; la cautela documentata fa parte della qualità tecnica e della Historical Review.

### Evidence

**In parole semplici:** un contenuto verificabile in una fonte disponibile e correttamente identificata.

**Esempio:** una frase estratta dal documento indicato nel contesto, non un fatto ricordato dal modello.

**Perché conta:** è l'unità minima per difendere una risposta e per diagnosticare un errore di retrieval o di generation.

### Version awareness

**In parole semplici:** riconoscere che una fonte può avere versioni, correzioni o date diverse senza cancellare la storia del documento precedente.

**Esempio:** preferire un registro aggiornato per la data finale, ma citare la bozza quando la domanda chiede cosa si pensasse in precedenza.

**Perché conta:** evita di trattare ogni conflitto come rumore e aiuta a rispondere alla domanda effettiva.

### Harmful if unqualified

**In parole semplici:** una fonte che può fare danno se usata senza dichiararne limiti, conflitti o natura propagandistica.

**Esempio:** usare un manifesto come prova neutrale di ciò che è realmente accaduto.

**Perché conta:** la fonte può essere pertinente e tuttavia richiedere una qualifica esplicita nella risposta.

## Misure e oggetti della submission

### Latency

**In parole semplici:** il tempo wall-clock end-to-end per rispondere a una domanda, dalla richiesta al risultato.

**Esempio:** includere retrieval, chiamate al modello e serializzazione della risposta in `telemetry.latency_ms`.

**Perché conta:** una pipeline accurata ma troppo lenta può perdere punti; misuratela nello stesso modo in cui la dichiarate.

### Declared cost

**In parole semplici:** il costo autodichiarato in euro per domanda, con i token e le chiamate utili per l'audit.

**Esempio:** `telemetry.declared_cost_eur` insieme a `model_calls` documenta quanto è costata la generation.

**Perché conta:** il costo medio incide sul punteggio e rende confrontabili scelte di modello, reranking e numero di chiamate.

### Gold Run

**In parole semplici:** la prova finale con domande nuove e archivio invariato dopo Act 1 + Act 2, senza feedback immediato e con una sola conferma ufficiale.

**Esempio:** generate `outputs/submission_gold.json`, validatelo, poi confermatelo sulla piattaforma.

**Perché conta:** misura la pipeline congelata su casi mai visti; non è il momento di aggiungere documenti o cambiare configurazione.

### Historical Review

**In parole semplici:** la parte orale dopo la Gold in cui spiegate una domanda storica, le fonti decisive, i conflitti e il grado di certezza.

**Esempio:** mostrare perché una fonte è stata qualificata come propaganda e quale evidenza avrebbe fatto cambiare tesi.

**Perché conta:** collega il lavoro tecnico alla capacità umana di motivare una conclusione prudente; contribuisce al punteggio finale secondo il regolamento.
