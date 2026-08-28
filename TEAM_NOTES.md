# Team Notes

## Problema 1

- **Problema:** Il tempo della prima ingestion con Docling risulta enorme, soprattutto per documenti scannerizzati e non digitali. Docling gira in locale ed è molto lento: primo ingest completo misurato in **37 min 18 s** (10:39:57 → 11:17:15, 15 doc → 140 chunk; `garib_d08`, scansione 24 pagine, da solo = 94 chunk). Concausa: `easy_ocr_force_full_page=True` fa girare l'OCR anche sui PDF di testo puliti.
- **Com'è stato risolto:** Non è stato risolto, ma discusso internamente.
- **Cosa ho imparato:** In funzione dell'ambiente e delle risorse a disposizione può essere utile sostituire Docling con una soluzione non locale, ad es. le API di parsing/OCR di OpenAI, o usare librerie di parsing più coerenti. Utilizzando ad esempio una pipeline di check del file (se scanned o digital) potrebbe essere utile utilizzare OCR solo sui documenti scansionati. Un'altra idea potrebbe essere parallelizzare il parsing. Tesseract è spesso più veloce. NOTA: le impostazioni sulla lingua potrebbero migliorare la qualità.

---

## Problema 2 — Round 1: score 69.71/90 sulla baseline

- **Problema (sintomo):** submission baseline del round 1 (`outputs/round1/submission_round_1_pre_opt.json`) valutata **69.71/90**, nessun dettaglio per voce dalla piattaforma. Due difetti visibili nel file:
  1. **Contesti duplicati** — i 5 slot contengono spesso 2-3 chunk dello **stesso** `document_id` (Q002 dossier ×3, Q004 dispaccio ×3, Q005 solo 2 documenti unici su 5). Slot sprecati → Precision e Ranking bassi.
  2. **Astensione secca** — su R1_Q007 (`insufficient_evidence`) la risposta è `"Non lo so."` e basta. Il prompt `GROUNDING` imponeva testualmente *"di' esattamente 'Non lo so'"*. Butta via Answer Correctness + Historical Reasoning su quella domanda.
- **Causa ipotizzata:**
  1. `hits_to_contexts` prendeva i top-5 **chunk**; con doc di testo brevi il retriever restituisce più chunk dello stesso documento.
  2. istruzione di sistema troppo rigida.
  - (Verificato che **non** è un problema di Faithfulness: overlap normalizzato contesto↔PDF pulito = 96.4% medio, l'OCR sporco non azzera la Faithfulness a questi livelli.)
- **Fix (branch `feature/round1-improvements`):**
  - **C — prompt astensione argomentata:** `GROUNDING` riscritto: quando le fonti non bastano, dichiararlo e spiegare *quali indizi ci sono, cosa manca, se le fonti sono di parte*; distinguere indizio da prova. Nessun `--rebuild`.
  - **B — un documento per contesto:** nuovo `merge_contexts()` — retrieval largo (`RETRIEVE_K=10`), accorpa i chunk per `document_id` (max `CHUNKS_PER_DOC=2`), tiene solo i documenti con score entro `SCORE_MARGIN=0.08` dal migliore, pavimento `MIN_CONTEXTS=2`, tetto 5. Sostituito il DAG con una chiamata `llm.invoke` diretta (elimina anche il fallback retriever fuori dal timer di latenza). Nessun `--rebuild`. Test: `tests/test_merge_contexts.py`.
- **Metrica prima/dopo** (locale, sul round 1 — la piattaforma darà il numero vero):
  - contesti: da 5-con-duplicati a 2-5 documenti **distinti** per domanda.
  - R1_Q007: da `"Non lo so."` a astensione argomentata con 3 fonti citate.
  - R1_Q002 / R1_Q006: risposte più complete (spiegano invece di elencare).
  - latenza media 2667 → 3027 ms (1/8 domande > 4 s, era 2/8); costo medio €0.00048 → €0.00030.
  - sample (con annotazioni): SAMPLE_Q001 e Q002 ancora Hit + fatti richiesti presenti → nessuna regressione.
- **Decisione:** tenere C e B, caricare `submission_round_1_post_opt.json`. `SCORE_MARGIN` / `MIN_CONTEXTS` / `CHUNKS_PER_DOC` sono knob da tarare col feedback del round 2.
- **Limite noto:** `merge_contexts` senza feedback per-voce è tarato a occhio; su R1_Q008 (cross-document) scende a 2 contesti, possibile rischio Recall. **Buco da chiudere prima della Gold:** OCR per-modalità (testo → nessun OCR, `garib_*` → OCR) per pulire il testo e sbloccare l'ingest — vedi Problema 1.

---

Copiate il blocco per aggiungere un nuovo problema, tranquilli che anche il coding agent lo sa gestire
