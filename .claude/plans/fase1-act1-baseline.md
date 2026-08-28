# Fase 1 — Act 1: baseline e primo giro di apprendimento

## Context

`regolamento/docs/PARTICIPANT_GUIDE.md` § «Fase 1» prescrive cinque azioni in sequenza. La prima è
**già stata eseguita**: la baseline naive dense RAG ha girato end-to-end sulle 8 domande di
`eval/questions_round_1.json` e ha prodotto `outputs/round1/submission_round_1_pre_opt.json`.

Le quattro azioni restanti sono bloccate dallo stesso ostacolo: **nel repo non esiste nessuno
strumento di misura**. Non si può «confrontare i `document_id` con le annotazioni» (le annotazioni
per il round 1 non esistono), non si può «misurare retrieval, qualità, latenza e costo» (nessuno
scorer), e quindi non si può scegliere «un esperimento alla volta» perché non c'è un prima/dopo da
confrontare. Questo piano costruisce lo strumento e poi esegue il giro di apprendimento.

### Che cosa dice già la baseline (letta a mano da `submission_round_1_pre_opt.json`)

**Sistema — entrambe le fasce già al massimo, e c'è margine da spendere in qualità:**

| Voce | Valore misurato | Fascia (`SCORING_AND_FAIRNESS.md`) |
| --- | --- | --- |
| Latenza media | 2 667 ms | ≤ 4 s → **7/7** |
| Latenza peggiore (R1_Q008) | 4 477 ms | oltre la soglia dei 4 s |
| Costo medio/domanda | € 0,000298 | ≤ €0,005 → **8/8**, con ~16× di margine |
| Token totali | 11 391 in / 1 129 out | una sola chiamata LLM per domanda |

Conseguenza strategica: i 15 punti di sistema sono acquisiti e **si possono spendere fino a ~16×
del costo attuale** (un reranker, una seconda chiamata) restando nella fascia massima. La leva reale
sono i **70 punti di retrieval + generation**.

**Retrieval — tre sintomi distinti, tutti visibili a occhio nudo:**

1. **Ranking**: su R1_Q003 la fonte decisiva (`lettera_salina_01`) è al **rank 3**, dietro
   `elenco_personaggi_01` (una tabella di nomi) e `lettera_tancredi_01`. Su R1_Q006
   `nota_funzionario_borbonico_01` è al **rank 3**, dietro `giornale_borbonico_01`. Sono 5 punti di
   «Qualità del ranking» lasciati sul tavolo.
2. **Precisione**: su R1_Q001 i contesti 3–5 (`nota_funzionario_borbonico_01`,
   `giornale_liberale_01`, `garib_d09`) non c'entrano con «data e luogo dello sbarco» —
   `garib_d09` parla di un discorso a Marsala del **1862**, distrattore semantico perfetto. La
   baseline riempie sempre e comunque 5 contesti su 5.
3. **Qualità del testo estratto**: l'OCR corrompe sistematicamente il testo *anche dei PDF nativi
   digitali* — `"1 rapporti per"` (i→1), `"€ affinché"` (e→€), `"corrispondenze; note"` (virgola→
   punto e virgola), `"dell 'occidente"`, e sulla scansione `garib_d05` `"Nello slalo in cui si
   trova FItalia"`. Il default di `DoclingParser` è EasyOCR con `force_full_page=True`: OCR-izza
   pagine che avevano già un layer di testo pulito. È la causa del problema 1 di `TEAM_NOTES.md`
   (ingest lentissimo) **ed è anche un rischio di punteggio**: `SCORING_AND_FAIRNESS.md` dice che
   ogni contesto è confrontato col corpus «tramite supporto testuale normalizzato» e che un
   contenuto non riconducibile azzera la Faithfulness della domanda.

**Generation:** R1_Q007 astiene correttamente («Non lo so») — è il caso di successo riproducibile.
R1_Q002 elenca quattro categorie ma i contesti recuperati ne mostrano esplicitamente meno: è il
candidato n.1 a caso di fallimento di *generation* (risposta plausibile non sostenuta dai contesti),
esattamente lo scenario «Non faithful» descritto nelle regole di scoring.

### Decisioni prese con l'utente

- **Il loop misurato gira sul corpus completo del manifest (15 documenti).** La baseline `pre_opt`
  ha girato così — in 7 domande su 8 i contesti vengono da documenti di Act 2 — e le domande di
  round 1 lo richiedono (`lettera_salina_01`, `dispaccio_console_inglese_01`, `giornale_*`,
  `nota_funzionario_borbonico_01` sono tutti Act 2). Filtrare su Act 1 renderebbe il post-opt non
  confrontabile col pre-opt e toglierebbe la risposta a 5 domande su 8.
- **Il flag `--act` viene comunque implementato** (richiesta esplicita), ma come strumento
  diagnostico opzionale: default = tutto il manifest, comportamento attuale invariato.
- **Set di valutazione:** `eval/questions_round_1.json` (8 domande) + `eval/sample_questions.json`
  (2 domande, con le annotazioni ufficiali già presenti in `eval/sample_annotations.json`).
- **Scope:** strumenti, misura della baseline, e poi gli esperimenti eseguiti **uno alla volta**
  secondo il catalogo qui sotto, ciascuno con il suo prima/dopo.

---

## Step 1 — Baseline end-to-end ✅ FATTO

Artefatto: `outputs/round1/submission_round_1_pre_opt.json` (8 risposte, `round_id: round_1`).
**Va congelato**: è il riferimento anti-regressione di tutta la Fase 1, come chiede la guida
(«conservate anche l'output precedente per confrontare le regressioni»). Nessun comando lo deve
sovrascrivere: la convenzione di naming diventa
`outputs/round1/submission_round_1_<pre_opt|E1|E2|…>.json`.

Prima di procedere, ri-verificarlo senza consumare il tentativo:

```bash
python baseline_naive_rag.py --validate-only \
  --submission outputs/round1/submission_round_1_pre_opt.json \
  --questions eval/questions_round_1.json \
  --manifest data/manifest.json --round-id round_1
```

---

## Step 2 — Confrontare i `document_id` recuperati con le annotazioni

**2a. Annotazioni sample (già disponibili).** `eval/sample_annotations.json` è l'unico gold
ufficiale che abbiamo: 2 domande, con `relevant_sources`, `required_facts`, `requires_abstention`.
Serve da *taratura* dello scorer — se lo scorer dà recall@5 = 1.0 su `SAMPLE_Q001` /
`SAMPLE_Q002` (le cui fonti attese, `cronologia_ufficiale_01` e `dossier_introduttivo_01`, sono
effettivamente al rank 1 in `outputs/submission_sample.json`), allora lo scorer legge correttamente
la submission.

**2b. Annotazioni round 1 (da scrivere).** Nuovo file `eval/annotations_round_1.json`, **stessa
identica forma** di `eval/sample_annotations.json` — riusare quei campi, non inventarne:
`question_id`, `question`, `type`, `difficulty`, `expected_answer`, `relevant_sources`,
`acceptable_sources`, `distractor_sources`, `harmful_if_unqualified`, `forbidden_claims`,
`requires_abstention`, `required_facts`, `uncertainty_required`, `judge_notes`.

Mappatura di partenza, già verificata su manifest + testo dei contesti della baseline:

| Domanda | `relevant_sources` | Note |
| --- | --- | --- |
| R1_Q001 | `cronologia_ufficiale_01` | `distractor_sources`: `garib_d09` (Marsala 1862) |
| R1_Q002 | `dossier_introduttivo_01` | `required_facts`: le 4 categorie, verbatim dal PDF |
| R1_Q003 | `lettera_salina_01` | `distractor_sources`: `elenco_personaggi_01`, `lettera_tancredi_01` |
| R1_Q004 | `dispaccio_console_inglese_01` | afferma / nega: due `required_facts` distinti |
| R1_Q005 | `giornale_borbonico_01` + `giornale_liberale_01` | servono **entrambi**: recall@5 = 2 fonti |
| R1_Q006 | `nota_funzionario_borbonico_01` | `distractor_sources`: `giornale_borbonico_01` |
| R1_Q007 | — | `requires_abstention: true` (`type: insufficient_evidence`) |
| R1_Q008 | da fissare leggendo i testi | cross-document, `uncertainty_required: true` |

Regola di compilazione: si citano **solo fatti letteralmente presenti** nei documenti, leggendo il
testo estratto (dump della cache di parsing, step E0). Sono etichette **nostre, non ufficiali**:
dichiararlo in `judge_notes` e in `TEAM_NOTES.md`, così un giudizio non viene scambiato per verità.

---

## Step 3 — Misurare retrieval, qualità delle risposte, latenza e costo

Nuovo file `score_submission.py` **nella radice del repo** (come `baseline_naive_rag.py`, così i
test lo importano direttamente: `eval/` non è un package). Nessuna dipendenza nuova, **nessuna
chiamata LLM**: sono tutte metriche gratuite (playbook `corso-datapizza` §10, §12, §13).

```bash
python score_submission.py \
  --submission outputs/round1/submission_round_1_pre_opt.json \
  --annotations eval/annotations_round_1.json \
  --manifest data/manifest.json
```

Cosa stampa, in corrispondenza 1:1 con la tabella punteggio di `SCORING_AND_FAIRNESS.md`:

- **Retrieval**: `recall@5` (20 pt), `precision@5` (10 pt), `hit@5` (5 pt), `MRR` come proxy della
  «qualità del ranking» (5 pt).
- **Astensione**: `dont_know_rate` sulle domande con `requires_abstention` — e, altrettanto
  importante, le **astensioni indebite** (ha detto «Non lo so» avendo la fonte giusta in mano).
- **Sistema**: latenza media, p95 e massima; costo medio; con accanto la fascia di punteggio
  raggiunta, così una regressione di fascia si vede subito.
- **Tabella per domanda con la diagnosi che la guida chiede** («sapete quali errori sono di
  retrieval e quali di generation»):
  - `RETRIEVAL_FAIL` — nessuna `relevant_source` nei 5 contesti;
  - `RANK_WEAK` — fonte presente ma sotto il rank 2;
  - `GENERATION_FAIL` — fonte presente ma `required_facts` assenti dalla risposta, oppure
    astensione indebita;
  - `OK`.
- **Diff fra due submission** (`--baseline outputs/round1/submission_round_1_pre_opt.json`): per
  ogni metrica prima → dopo con il segno, e l'elenco delle domande che sono cambiate di stato. È il
  «prima/dopo annotato» richiesto, prodotto dal comando invece che a mano.

Target `make score` nel `Makefile`.

Il file `tests/test_score.py` (nuovo) verifica lo scorer su una submission sintetica con valori
calcolati a mano — una domanda con la fonte al rank 2, una senza fonte rilevante, una di astensione
— con assert su `recall@5`, `precision@5`, `hit@5`, `MRR`, `dont_know_rate`.
`tests/test_submission_schema.py` resta intoccato.

---

## Step 4 — Un esperimento alla volta

### E0 — Cache di parsing Docling (abilitatore, non un esperimento)

Senza questo, ogni `--rebuild` ri-OCR-izza l'intero archivio e un confronto A/B costa decine di
minuti: «un esperimento alla volta» diventa inaccessibile. È anche la risposta al problema 1 di
`TEAM_NOTES.md`.

`DoclingParser.parse()` passa sempre da `self.parse_to_json(file_path)`
(`.venv/…/datapizza/modules/parsers/docling/docling_parser.py:760`), quindi bastano ~12 righe in
`baseline_naive_rag.py`:

```python
class CachedDoclingParser(DoclingParser):
    """Docling parsa una volta sola. Chiave: sha256(file) + engine OCR."""
    def parse_to_json(self, file_path: str) -> dict:
        key = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        cached = PARSE_CACHE / f"{key}-{self.ocr_options.engine.value}.json"
        if cached.is_file():
            return json.loads(cached.read_text(encoding="utf-8"))
        data = super().parse_to_json(file_path)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
```

`PARSE_CACHE = outputs/parse_cache/` (già coperto da `.gitignore`). La chiave include l'engine OCR,
così E1 non riusa una cache prodotta con un altro parser. Nessuna dipendenza nuova (`hashlib`).
**Non è un esperimento**: a parità di engine l'output è identico, cambia solo il tempo. Va comunque
verificato che lo sia (`--rebuild` due volte, submission identiche).

Insieme a E0 entra anche il flag diagnostico **`--act`**: `iter_ingest_files(manifest, root,
acts=None)` filtra su `document["act"]`; se il flag è passato la collection prende il suffisso
(`caso_dei_mille_act1`) così i due indici convivono. Default assente = comportamento odierno,
contratto CLI intatto.

### Protocollo comune a tutti gli esperimenti

1. Si cambia **una sola** variabile.
2. Si rigenera la submission in `outputs/round1/submission_round_1_E<n>.json` (mai sovrascrivendo
   `pre_opt`).
3. `python score_submission.py --submission …_E<n>.json --baseline …_pre_opt.json`.
4. Si tiene solo se **recall@5 e precision@5 non peggiorano ed almeno una migliora**, senza uscire
   dalle fasce latenza ≤4 s e costo ≤€0,005.
5. Blocco in `TEAM_NOTES.md` nel formato richiesto dalla guida: *domanda, contesti recuperati,
   risposta, sintomo, causa ipotizzata, fix, metrica prima/dopo, decisione (tenere / revertire /
   approfondire)*.

### Catalogo degli esperimenti, in ordine di evidenza

**E1 — Qualità del parsing: niente OCR sui PDF nativi, Tesseract `ita` sulle scansioni**

- *Ipotesi*: EasyOCR `force_full_page=True` rigenera da immagine anche pagine con testo digitale
  già pulito, introducendo errori (`i`→`1`, `e`→`€`, `,`→`;`) che degradano gli embedding, la
  leggibilità dei contesti e il *supporto testuale normalizzato* usato dalla piattaforma.
- *Evidenza*: corruzioni presenti in **ogni** contesto della baseline, citate sopra.
- *Modifica*: `OCROptions(engine=OCREngine.NONE)` per i documenti con `modality` ∈ {`text`,
  `table`}, `OCREngine.TESSERACT` con `tesseract_lang=["ita"]` per `modality` ∈ {`scan`, `map`}
  (`ocr_options.py` espone entrambi). Il `modality` è già nel manifest per tutti i 15 documenti.
- *Metriche attese*: recall@5 e precision@5 in su; tempo di ingest giù di molto; contesti
  leggibili → minor rischio di Faithfulness azzerata.
- *Rischio*: se un PDF «text» in realtà non ha layer testuale, con OCR spento diventa vuoto →
  controllo obbligatorio che ogni `document_id` produca ancora chunk (l'ingest lo stampa).

**E2 — Consegnare meno di 5 contesti quando non servono (taglio adattivo)**

- *Ipotesi*: riempire sempre 5 slot regala precisione. Tagliare i contesti sotto una soglia di
  similarità (o sotto una frazione del punteggio del rank 1) alza la Precision e riduce il rumore
  passato al generatore.
- *Evidenza*: R1_Q001 ha 3 contesti su 5 fuori tema; R1_Q002 ne ha 2.
- *Modifica*: soglia in `hits_to_contexts()`; i rank restano 1..N consecutivi (il contratto ammette
  **fino a** 5 contesti, non esattamente 5).
- *Attenzione*: è la mossa che può far scendere il recall. Va misurata su entrambe le metriche
  insieme — è esattamente il caso su cui la guida avverte («non aumentate top-k senza misurare»,
  che vale anche al contrario).

**E3 — Recuperare largo, consegnare stretto: reranking `k=15 → 5`**

- *Ipotesi*: il denso trova i documenti giusti ma li ordina male; un reranker cross-encoder sui
  primi 15 rimette in cima l'evidenza decisiva.
- *Evidenza*: `lettera_salina_01` al rank 3 (R1_Q003), `nota_funzionario_borbonico_01` al rank 3
  (R1_Q006).
- *Modifica*: `CohereReranker(top_n=5, model="rerank-v3.5")` (playbook §6) **con fallback lessicale
  locale** se la chiave manca — una dipendenza esterna che cade durante la Gold Run sarebbe fatale.
- *Costo*: una chiamata in più; il margine di 16× lo assorbe, ma va dichiarata in `model_calls` e
  la latenza ricontrollata (R1_Q008 è già a 4,5 s).

**E4 — Ricerca ibrida BM25 + RRF**

- *Ipotesi*: su un archivio del 1860 le domande girano su nomi propri, luoghi e date, dove il denso
  è debole e BM25 è forte; la fusione RRF usa solo i rank, quindi non richiede scale comparabili.
- *Evidenza*: R1_Q001 chiede una data e un luogo e recupera un distrattore che nomina lo stesso
  luogo in un anno diverso — sintomo tipico di similarità puramente semantica.
- *Modifica*: BM25 in memoria sui chunk + fusione RRF (playbook §5), `k_rrf = 60`.
- *Nota*: `rank_bm25` sarebbe una dipendenza nuova → prima verificare se basta una BM25 in ~30
  righe di stdlib, coerentemente con la regola del repo sulle dipendenze.

**E5 — Prompt e astensione**

- *Ipotesi*: il prompt `GROUNDING` attuale ottiene già l'astensione secca su R1_Q007, ma non impone
  di distinguere *fatto / indizio / congettura* né di qualificare le fonti propagandistiche —
  richieste esplicite di «Historical Reasoning» (5 pt) e di `SCORING_AND_FAIRNESS.md`.
- *Evidenza*: R1_Q002 elenca quattro categorie senza che tutte siano visibili nei contesti passati
  (candidato caso «Non faithful»); R1_Q005 confronta due giornali di propaganda senza etichettarli
  come tali.
- *Modifica*: aggiungere al prompt (a) l'obbligo di non affermare ciò che non è nei contesti, (b) la
  qualificazione della fonte quando `reliability` ∈ {`propaganda`, `ambiguous`, `contested`}, (c) la
  distinzione fatto/indizio. La `reliability` è nel manifest → va messa nel payload dei chunk ed
  esposta nel template.
- *Costo*: zero API in più, nessun re-ingest se la `reliability` viene aggiunta insieme a E1.

**E6 — Sweep del chunking (`max_char × overlap`)**

- *Ipotesi*: `RecursiveSplitter(max_char=1024, overlap=128)` taglia a metà frase e spezza le
  definizioni che una domanda enumerativa richiede intere.
- *Evidenza*: il contesto al rank 1 di R1_Q002 inizia a metà periodo (`"una spiegazione ragionevole
  e acquisti forza…"`), e la domanda chiede quattro categorie che stanno in sezioni diverse.
- *Modifica*: griglia `max_char ∈ {512, 768, 1024}` × `overlap ∈ {64, 128, 256}`, giudicata su
  `hit@5` e `MRR`. Fattibile solo grazie a E0.
- *Nota dal playbook §2*: il chunker «più intelligente» ha perso a 600 char e vinto a 400 — la
  granularità ribalta il risultato, quindi si sweepa, non si assume.

**Ordine di esecuzione**: E0 (abilitatore) → E1 → E2 → E3 → E4 → E5 → E6, ognuno con il proprio
gate. Chi non supera il criterio del punto 4 viene revertito e resta a verbale come esperimento
fallito: `TEAM_NOTES.md` registra i negativi esattamente come i positivi.

---

## Step 5 — Submission finale e conservazione del pre-opt

```bash
python baseline_naive_rag.py \
  --questions eval/questions_round_1.json --round-id round_1 \
  --output outputs/round1/submission_round_1_post_opt.json --rebuild
python baseline_naive_rag.py --validate-only \
  --submission outputs/round1/submission_round_1_post_opt.json \
  --questions eval/questions_round_1.json \
  --manifest data/manifest.json --round-id round_1
```

`submission_round_1_pre_opt.json` e tutte le `_E<n>.json` restano sul disco: sono la storia della
fase e la base per le regressioni dell'Act 2.

---

## Chiusura di fase — «Avete finito quando»

| Criterio della guida | Come lo si soddisfa |
| --- | --- |
| Sapete quali errori sono di retrieval e quali di generation | Colonna diagnosi di `score_submission.py` (`RETRIEVAL_FAIL` / `RANK_WEAK` / `GENERATION_FAIL`) |
| Almeno un successo e un fallimento riproducibili | Successo: R1_Q007, astensione corretta. Fallimento: R1_Q003, fonte decisiva al rank 3 — entrambi con comando e output allegati |
| Ogni modifica importante ha un prima/dopo annotato | `--baseline` dello scorer + un blocco `TEAM_NOTES.md` per esperimento |
| La submission passa validazione locale e di piattaforma | `--validate-only` in locale (non consuma il tentativo) + validazione sul sito |

**Formato della riga d'errore in `TEAM_NOTES.md`** (richiesto testualmente dalla guida): domanda ·
contesti recuperati · risposta · sintomo · causa ipotizzata · fix · metrica prima/dopo · decisione.
Deve bastare a un altro agente per riprodurre il caso senza chiedere nulla a chi era presente.

---

## File toccati

| File | Modifica |
| --- | --- |
| `baseline_naive_rag.py` | `CachedDoclingParser`, OCR per `modality`, `acts=` + flag `--act`, `reliability` nel payload, soglia in `hits_to_contexts`, prompt |
| `score_submission.py` | **nuovo** — metriche, diagnosi per domanda, diff prima/dopo |
| `eval/annotations_round_1.json` | **nuovo** — gold delle 8 domande, etichette nostre |
| `tests/test_score.py` | **nuovo** — check dello scorer su dati sintetici |
| `Makefile` | target `score` |
| `TEAM_NOTES.md` | blocco baseline + un blocco per esperimento (anche per quelli falliti) |

## Verifica

1. `make test` — verde, compresi i test esistenti sul contratto di submission.
2. `make sample` — termina con `Submission valida: outputs/submission_sample.json`: il default della
   CLI non è cambiato.
3. Lo scorer sulle annotazioni **sample** dà `recall@5 = 1.0` e `hit@5 = 1.0` → lo scorer è tarato.
4. Due `--rebuild` consecutivi: il secondo è molto più rapido e produce una submission identica →
   la cache di parsing è attiva e neutra.
5. Ogni `_E<n>.json` supera `--validate-only`: ≤5 contesti, rank 1..N consecutivi, `document_id` nel
   manifest, nessun campo extra.
6. `git status` pulito (niente `.env`, niente `outputs/`), PR verso `main` aperta con `gh`, con
   descrizione e checklist di test, lasciata in review.

## Fuori scope (deliberatamente)

Query rewriting / HyDE, parent-child, RAPTOR, cache semantica, async fan-out, loop dedicato ad
Act 2. Ognuno è un esperimento con la sua misura: entra dopo, se i numeri di questa fase dicono che
serve.
