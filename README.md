# Il caso dei Mille — starter RAG

Benvenuti nell'archivio. La missione non è raccontare bene il 1860: è trovare le carte giuste, usarle con misura e dichiarare l'incertezza quando le prove non bastano.

Questa starter contiene una baseline **naive dense RAG** pronta da eseguire end-to-end. Partite da qui, misurate cosa non funziona e migliorate la pipeline senza perdere il contratto della submission.

L'archivio ha **due Act**. L'Act 2 è quello più insidioso: molti documenti, scansioni, mappe, propaganda, versioni diverse e fonti contestate. La **Gold Run** arriva alla fine con domande nuove, ma usa lo stesso archivio completo: nessun terzo atto, nessun documento a sorpresa dopo l'Act 2.

Per la regia della giornata consultate la [guida partecipanti](../participant_kickoff/docs/PARTICIPANT_GUIDE.md). Per criteri, soglie ed esempi di valutazione, consultate le [regole di scoring](../participant_kickoff/docs/SCORING_AND_FAIRNESS.md).

## Primo checkpoint — circa 10 minuti

Obiettivo: produrre una submission sample valida in `outputs/`. I comandi seguenti installano le dipendenze, costruiscono l'indice e lanciano la baseline sulle domande di prova.

Requisiti: Python 3.11+ e una `OPENAI_API_KEY`. Per lavorare sulle scansioni servono anche Tesseract e un backend OCR supportato da Docling.

```bash
cd garibaldi-rag-starter            # se non siete già in questa cartella
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
# aggiungete OPENAI_API_KEY a .env
make sample
```

Se `make` non è disponibile, il comando equivalente è:

```bash
python baseline_naive_rag.py \
  --questions eval/sample_questions.json \
  --round-id sample \
  --output outputs/submission_sample.json \
  --rebuild
```

Il primo giro può richiedere più tempo dei successivi: deve leggere le carte, creare gli embedding e costruire Qdrant. Al termine cercate questa riga:

```text
Submission valida: outputs/submission_sample.json
```

Avete superato il checkpoint quando il file esiste e il comando termina senza errori. Per rieseguire il solo controllo locale, senza chiamare le API:

```bash
python baseline_naive_rag.py --validate-only \
  --submission outputs/submission_sample.json \
  --questions eval/sample_questions.json \
  --manifest data/manifest.json \
  --round-id sample
```

Output atteso:

```text
VALIDAZIONE OK - il tentativo ufficiale non e stato consumato
```

> Promemoria importante: `.env` contiene la chiave API. Lasciatelo fuori da Git: è già previsto dal `.gitignore`.

## Mappa della cartella

| Percorso | A cosa serve |
| --- | --- |
| `baseline_naive_rag.py` | Entrypoint: ingest, RAG, scrittura e validazione della submission |
| `data/act_1/`, `data/act_2/` | Le carte dell'archivio; l'Act 2 concentra i casi più difficili |
| `data/manifest.json` | Catalogo obbligatorio per ingest, indice e validazione dei `document_id` |
| `data/checksums.sha256` | Controllo di integrità dei file in `data/` |
| `data/license_manifest.csv` | Licenze e URL delle fonti autentiche |
| `eval/` | Domande e annotazioni sample, esempio e schema della submission |
| `scripts/install_release.py` | Installa un eventuale release pack dell'Act 2 e aggiorna il manifest |
| `outputs/` | Indice Qdrant e submission locali; artefatti generati e non versionati |
| `tests/` | Test del contratto di submission |
| `Makefile` | Scorciatoie: `setup`, `sample`, `test` |

`manifest.json` è la fonte di verità: i file in `data/` contano soltanto se sono presenti nel catalogo. Dopo aver modificato la baseline o il formato della submission, eseguite `make test`: verifica anche campi non ammessi e ranghi dei contesti consecutivi.

## Dal sample a un round

Le domande ufficiali arrivano dalla dashboard, non sono nel repository. Usate sempre un nome sotto `outputs/` per separare le prove dai file da caricare.

```bash
python baseline_naive_rag.py \
  --questions percorso/alle/domande_round_1.json \
  --round-id round_1 \
  --output outputs/submission_round_1.json
```

Il comando genera **e** valida il file. Se termina con `Submission valida: ...`, il JSON è pronto per la validazione in piattaforma. Prima di una conferma ufficiale potete ripetere il controllo locale:

```bash
python baseline_naive_rag.py --validate-only \
  --submission outputs/submission_round_1.json \
  --questions percorso/alle/domande_round_1.json \
  --manifest data/manifest.json \
  --round-id round_1
```

La validazione sul sito non consuma il tentativo. Solo **Conferma irreversibile** invia la submission ufficiale: fermatevi un minuto, fate la checklist qui sotto e confermate una sola versione condivisa dal team.

### Devo usare `--rebuild`?

| Situazione | Usare `--rebuild`? | Perché |
| --- | :---: | --- |
| Primo `make sample` o primo avvio su una nuova macchina | Sì | L'indice non esiste ancora |
| Avete ricevuto soltanto nuove domande | No | Le domande non modificano l'indice |
| Avete appena installato l'Act 2 | Sì | I nuovi documenti devono entrare nell'indice |
| Avete cambiato chunking, embedding o logica di ingest | Sì | L'indice precedente non rappresenta più la pipeline |
| Avete modificato soltanto prompt o generazione | No | Potete riusare le stesse evidenze indicizzate |
| Non sapete quali documenti contiene l'indice | Sì, con cautela | Ricostruisce da una base nota, ma costa tempo e API |

`--rebuild` è tutto o niente: cancella la collection Qdrant e la ricostruisce da zero, riprocessando anche le carte già indicizzate. Il tempo e il costo crescono quindi con l'intero archivio, non soltanto con i file nuovi. È un buon primo candidato per un miglioramento di ingestion incrementale, ma non implementatelo senza testarlo.

### Se l'Act 2 arriva come release pack

Installate lo zip scaricato dalla dashboard e poi rilanciate la pipeline con `--rebuild`:

```bash
python scripts/install_release.py /percorso/al/act_2.zip

python baseline_naive_rag.py \
  --questions percorso/alle/domande_round_2.json \
  --round-id round_2 \
  --output outputs/submission_round_2.json \
  --rebuild
```

Controllate l'output dello script: deve indicare i file copiati e gli Act disponibili nel manifest. Se il manifest non include l'Act 2, non proseguite: state interrogando un archivio incompleto.

## Forma della submission

Partite da [`eval/submission.example.json`](eval/submission.example.json) e verificate le regole formali in [`eval/submission.schema.json`](eval/submission.schema.json). La baseline le applica già prima di scrivere il file.

In breve:

- top-level: `schema_version` (`"1.0"`), `round_id`, `answers`;
- per ogni domanda: `question_id`, `question`, `answer`, `contexts`, `telemetry`;
- fino a cinque contesti, con `rank` da 1 a N senza salti, `document_id` e `content`;
- telemetria: `latency_ms`, `declared_cost_eur`, `model_calls`.

I `contexts` sono le evidenze finali realmente passate al generatore, nello stesso ordine del top-k. Non aggiungete citazioni dopo la generazione e non inventate testo per rendere una fonte più convincente. Per mappe e scansioni, usate il `document_id` corretto e il contenuto OCR o la descrizione che avete effettivamente fornito al modello. Un contesto non riconducibile al corpus può azzerare la Faithfulness della domanda.

Non aggiungete campi non previsti dallo schema, ad esempio `chunk_id`, `page`, `location_label`, `confidence`, `repository_url` o `commit_hash`.

## Checklist prima di confermare

- [ ] Il file da caricare è sotto `outputs/` e ha il `round_id` corretto.
- [ ] Ogni domanda ufficiale è presente una sola volta.
- [ ] La validazione locale termina con `VALIDAZIONE OK`.
- [ ] I `document_id` sono nel manifest e i `content` provengono davvero da quelle carte.
- [ ] I contesti sono al massimo cinque e i loro `rank` sono consecutivi.
- [ ] Latenza, costo dichiarato e `model_calls` sono plausibili.
- [ ] Avete validato sulla piattaforma, letto l'esito e il team concorda sul file.
- [ ] State per premere **Conferma irreversibile** soltanto sul file scelto.

## Dove intervenire dopo la baseline

La baseline è volutamente semplice. Miglioramenti sensati includono hybrid search, reranking, query rewrite, chunking semantico, OCR e descrizioni per mappe, consapevolezza delle versioni, affidabilità delle fonti, abstention, self-check, ottimizzazione di costi/latenza e ingestion incrementale.

Fate un esperimento alla volta: formulate un'ipotesi, cambiate un componente, confrontate sample e feedback, poi tenete o scartate la modifica. Una RAG robusta non è quella che parla con più sicurezza; è quella che sa difendere le proprie risposte con le carte giuste.

## Problemi frequenti

| Se vedete questo | Provate prima questo |
| --- | --- |
| `OPENAI_API_KEY` mancante | Controllate che `.env` esista nella root della starter e contenga la chiave |
| `Nessun documento ingeribile dal manifest` | Eseguite dalla cartella `garibaldi-rag-starter` e controllate `data/manifest.json` |
| L'Act 2 non sembra influenzare le risposte | Verificate il manifest, poi rieseguite con `--rebuild` |
| La submission non è valida | Usate `--validate-only` con domande, manifest e `round-id` del round |
| Una scansione produce testo debole o vuoto | Trattatela come un problema di OCR/layout: non inventate il contenuto; registrate e testate un'alternativa |
| Il primo run è lento o costoso | È normale per l'indicizzazione completa; evitate rebuild inutili e misurate prima di ottimizzare |

Per le scansioni `garib_*` servono Tesseract e un backend OCR supportato da Docling. Sono scansioni autentiche, non PDF testuali puliti: OCR rumoroso e layout irregolare sono parte della sfida, non un invito a colmare i vuoti.

## Dopo la Gold Run

Conservate codice, test e `outputs/submission_gold.json`; l'URL del repository va caricato sulla piattaforma, mai dentro la submission. Lo speech finale dura **10 minuti** e include architettura, errori e correzioni, valutazione svolta e Historical Review. Non è richiesto un JSON separato per la Historical Review.
