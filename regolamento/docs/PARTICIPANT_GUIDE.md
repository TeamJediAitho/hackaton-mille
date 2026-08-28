# Guida partecipanti — il diario dei mille

Benvenuti a questa sessione di hackathon! 👋👋

## Che dovete fa?

Costruite una pipeline RAG capace di orientarsi in un archivio narrativo ambientato nella Sicilia del 1860. Vince chi trova le carte giuste, distingue una prova da un indizio e sa dire **«non lo sappiamo»** quando l'archivio non basta.

Questa guida è il copilota della giornata. Per ogni fase indica cosa ricevete, la prossima azione concreta, il criterio per considerarla conclusa e le informazioni da lasciare al team (e a un futuro coding agent). Il README dello starter resta la fonte per comandi e dettagli tecnici; la dashboard resta la fonte per materiali e domande aggiornati.

> Questa guida penso di averla fatta molto AI readable. Cercate di leggere in particolar il mio commento sul perché Team Notes please :)

## Come usare questa guida

1. Aprite la sezione della fase corrente e fate prima le verifiche indicate.
2. Dopo ogni esperimento annotate **ipotesi, evidenza, modifica e risultato** in `TEAM_NOTES.md`.
3. Se qualcosa non torna, fermatevi con un esempio riproducibile: una correzione non misurata è soltanto una nuova ipotesi.
4. Prima di una submission fate sempre la checklist di validazione, anche se il comando precedente sembrava riuscito.

> Eccomi a tediarvi. Perché vi ho messo questo file?
> L'AI causa sempre più debito tecnico, penso che questo documento sia fondamentale per rimanere sul pezzo, continuare a crescere con programmatori e avere conoscenza di ciò che è stato cambiato dall'AI e di come rimanere nel loop e eventualmente intervenire. Tra l'altro, cosa che ho notato ultimamente è che Claude Code e Codex in particolare continuano a fare gli stessi errori, in questo modo è possibile evitare step in cui vengono fatte degli errori banali e dovete passare del tempo a correggerli.

## Come l'ho pensata oggi?

```text
Kickoff → Act 1 e primo prototipo → feedback e analisi degli errori
→ Act 2 (archivio ricco e difficile) → hardening e regressioni
→ Gold Run sullo stesso archivio → Historical Review e speech → consegna
```

Gli atti sono soltanto due. L'Act 2 aggiunge documenti interessanti e più insidiosi — scansioni, mappe, propaganda, versioni aggiornate e fonti contestate — ma dopo l'Act 2 il corpus resta invariato: la Gold Run usa gli stessi documenti e domande nuove, senza feedback durante la finestra della prova.

## Fase 0 — Kickoff e orientamento

### Ricevete

- accesso alla piattaforma e alla dashboard del team;
- regolamento (`participant_rules`), domande e materiali disponibili;
- lo starter RAG e il catalogo dei documenti (`data/manifest.json`);
- il canale ufficiale **Microsoft Teams** per annunci, orari e incidenti condivisi.

### Che dovete fare?

Ecco, semplicemente:

- scaricate lo starter;
- leggete README, schema di submission e score prima di cambiare la pipeline;
- verificate Python, dipendenze, `OPENAI_API_KEY` e integrità dei file;
- lanciate il sample e controllate il JSON generato in `outputs/`;
- assegnate nel team chi segue retrieval, generation, evaluation e diario.

### Avete finito quando

- il sample viene generato e validato localmente;
- sapete dove arrivano domande e release nella dashboard;
- ogni persona sa chi contattare su Teams e quale file aggiornare;
- esiste una prima nota in `TEAM_NOTES.md` con baseline, rischi e ipotesi.

### Annotate per il futuro

Scrivete modello, versione delle dipendenze, comando eseguito e tempo del primo ingest. Se il setup fallisce, conservate l'errore completo e l'ambiente: tra qualche ora sarà molto più utile di un generico «non funzionava».

### Attenzione

`.env` contiene la chiave API e non deve finire in Git. I file contano nel corpus soltanto se sono presenti nel `manifest.json`; trovare un PDF in `data/` non significa che la pipeline lo stia usando.

## Fase 1 — Act 1: baseline e primo giro di apprendimento

### Ricevete

- il corpus dell'Act 1;
- un set di domande di prova o del primo round, pubblicato nella dashboard;
- eventuale feedback dopo la submission, secondo il programma dell'organizzazione.

### Fate

- eseguite la baseline end-to-end prima di ottimizzarla;
- confrontate i `document_id` recuperati con le annotazioni sample quando disponibili;
- misurate retrieval, qualità delle risposte, latenza e costo;
- scegliete un esperimento alla volta (chunking, query, reranking, prompt, abstention o altro);
- fate una submission in `outputs/` e conservate anche l'output precedente per confrontare le regressioni.

### Avete finito quando

- sapete quali errori sono di retrieval e quali di generation;
- avete almeno un caso di successo e un caso di fallimento riproducibili;
- ogni modifica importante ha un prima/dopo annotato;
- la submission passa la validazione locale e quella della piattaforma.

### Annotate per il futuro

Per ogni errore compilate una riga con: domanda, contesti recuperati, risposta, sintomo, causa ipotizzata, fix, metrica prima/dopo e decisione (tenere, revertire, approfondire). Un futuro coding agent deve poter riprodurre il caso senza interrogare chi era presente.

### Attenzione

Un buon testo non dimostra che il retrieval sia buono. Un contesto irrilevante o inventato può danneggiare la Faithfulness. Non aumentate `top-k` senza misurare precisione, costo e qualità della risposta.

## Fase 2 — Act 2: archivio ricco, casi difficili e hardening

### Ricevete

- i materiali dell'Act 2 e le relative domande, indicati nella dashboard del team;
- domande più ambigue e documenti volutamente difficili da interpretare;
- eventuali risultati o feedback del giro precedente.

L'Act 2 può contenere scansioni e mappe, OCR rumoroso, tabelle, propaganda, versioni concorrenti e fonti contestate.

### Fate

- allineate la working copy e il manifest ai materiali indicati dalla dashboard;
- ricostruite l'indice quando cambiano i documenti (il `--rebuild` riprocessa l'intero archivio);
- testate separatamente testo, OCR/immagini, conflitti tra versioni e fonti non affidabili;
- mantenete un set di regressione con i fallimenti dell'Act 1;
- verificate che ogni contesto finale sia davvero quello passato al generatore e abbia `document_id` valido;
- prima della Gold, congelate una versione della pipeline e fate un dry run completo.

### Avete finito quando

Non so se mi sto dimenticando qualcosa: 

- tutte le domande disponibili producono submission valide in `outputs/`;
- conoscete latenza, costo medio e limiti residui della pipeline;
- il diario contiene le tre evidenze più importanti da raccontare nello speech.

### Annotate per il futuro

Segnate per ogni documento problematico: `document_id`, modality, qualità dell'OCR, trasformazioni applicate, cosa ha funzionato e cosa no. Separate sempre «il testo non è stato recuperato» da «il modello lo ha recuperato ma lo ha interpretato male».

### Attenzione

Una fonte propagandistica o contestata può essere utile, ma va presentata come tale. Una versione aggiornata non cancella il valore documentario della bozza. Non sostituite il testo originale con una ricostruzione più leggibile.

## Fase 3 — Gold Run: una sola occasione

### Ricevete

- domande nuove, rese disponibili dalla dashboard;
- lo stesso archivio completo dell'Act 1 + Act 2, senza nuovi documenti durante la prova.

### Fate

- congelate codice, configurazione, prompt e modello;
- generate `outputs/submission_gold.json`;
- eseguite prima la validazione locale e poi quella sul sito;
- controllate schema, domande complete, rank consecutivi, massimo cinque contesti, `document_id` e telemetria;
- confermate soltanto quando tutto il team ha verificato il file.

### Avete finito quando

- la piattaforma mostra la validazione riuscita;
- è stata premuta **Conferma irreversibile** una sola volta;
- la submission ufficiale e il commit/versione usati sono tracciati nel diario;
- sapete spiegare almeno un successo, un limite e una scelta di astensione.

### Annotate per il futuro

Conservate comando, timestamp, hash o riferimento della versione, modello, configurazione, latenza e costo. Dopo la Gold non correggete retroattivamente i dati: annotate cosa avreste cambiato e perché.

### Attenzione

La validazione sul sito non consuma il tentativo; **Conferma irreversibile** sì. La Gold è one-shot e non offre feedback immediato. Un file valido non è necessariamente un file accurato: controllate anche le evidenze.

## Validazione e forma della submission

La submission deve stare sempre sotto `outputs/`. Usate [lo schema](../../garibaldi-rag-starter/eval/submission.schema.json) e [l'esempio](../../garibaldi-rag-starter/eval/submission.example.json) nello starter.

Campi essenziali:

- `schema_version` (`"1.0"`) e `round_id`;
- `answers[]` con `question_id`, testo della `question`, `answer`, `contexts` e `telemetry`;
- ogni contesto con `rank` consecutivo da 1, `document_id` e `content`;
- telemetria con `latency_ms`, `declared_cost_eur` e `model_calls`.

`contexts` sono le evidenze finali passate al generatore, nello stesso ordine e con massimo cinque elementi. Non aggiungete campi vietati o inventate contesti dopo la generazione. In locale potete usare `--validate-only`: non chiama le API.

## Fase 4 — Historical Review e speech finale

### Ricevete

- i risultati della Gold Run secondo i tempi della piattaforma;
- una domanda o un caso da discutere nella Historical Review;
- il tempo per preparare slide e racconto usando il diario del team.

### Fate

Preparate uno speech di **massimo 10 minuti**. Una scaletta efficace è:

1. 1 minuto: problema e obiettivo;
2. 2 minuti: architettura e motivazioni;
3. 2 minuti: esperimenti, metriche e risultati;
4. 5 minuti: Historical Review — fonti decisive, conflitti, limiti e tesi prudente.

Mostrate anche un errore che vi ha fatto crescere: il percorso da sintomo a causa, fix e verifica vale più di una lista di feature. La giuria registra e valuta la parte storica secondo il regolamento; non è richiesta una consegna JSON separata per la Historical Review.

### Avete finito quando

- la prova dura al massimo 10 minuti anche con una domanda;
- ogni numero mostrato è riconducibile a un esperimento annotato;
- distinguete fatti nelle fonti, inferenze del team e incertezze;
- il repository è pronto per la consegna.

### Annotate per il futuro

Salvate la scaletta, le metriche usate e le domande ricevute dalla giuria. Chi leggerà il progetto dopo di voi deve capire non soltanto cosa avete costruito, ma come avete imparato dagli errori.

### Attenzione

Dichiarare un limite supportato dalle fonti è parte della qualità del lavoro.

## Consegna repository

Consegnate codice, test, README, `TEAM_NOTES.md` (o equivalente) e `outputs/submission_gold.json`. L'URL GitHub, branch o tag va inserito sulla piattaforma, non nel JSON.

## Supporto e incidenti

Per annunci, orari e incidenti usate **Microsoft Teams**. Per starter, regole, atti e domande usate la **dashboard**. Quando chiedete aiuto, includete comando, errore completo, fase, file coinvolti e cosa avete già provato: così la risposta è più rapida e diventa documentazione utile per tutti.

## Diario per persone e coding agent

Usate il template in [`TEAM_NOTES.md`](../../garibaldi-rag-starter/TEAM_NOTES.md) per registrare esperimenti, failure, decisioni e passaggi di consegne. Se una decisione non è scritta, per il prossimo sviluppatore non esiste: lasciate sempre comando riproducibile, risultato atteso, risultato osservato e limite noto.
