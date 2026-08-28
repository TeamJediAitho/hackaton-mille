# Full inventory — Corso AI Datapizza

Root: `/mnt/c/Users/djchr/OneDrive - Aitho/Desktop/Corso AI Datapizza`

Three top-level folders: `Lezioni/` (canonical material), `Laboratorio/` (partial duplicate of Labs
02–04 + an unusable Windows venv), `Documenti Vari/` (admin paperwork — ignore).

Relevance to hackaton-mille is marked ⭐⭐⭐ (direct transfer) / ⭐⭐ (useful) / ⭐ (context only).

---

## Lezione 01 — AI literacy, how LLMs are trained ⭐

- `AITHO_01.pdf` (~55 pp) — intro deck.
- `Lab_01_AI_Literacy_e_Prima_Interazione_LLM.ipynb`, `Lab_01_Esercizi_Autonomi.ipynb`.
- Interactive HTML explainers (open in a browser, self-contained):
  `ml-training-explainer.html`, `nlp-statistico-datapizza.html`, `rnn-lstm-gru-Senior.html`.

Background only. Nothing to port.

---

## Lezione 02 — Prompt engineering & structured output ⭐⭐

- `Prompt_Engineering.pdf` (~38 pp) — the deck.
- `Lab_02_demo.ipynb` — zero-shot / few-shot / chain-of-thought / role prompting; **token usage and
  cost estimation**; structured output (system-prompt+temperature 0 vs schema-enforced).
- `Lab_02_Capstone_guidato.ipynb` / `Lab_02_Capstone_autonomo.ipynb` — guided vs autonomous capstone.
- `session2.py`, `sample_report.pdf`, `sample_note.mp3`, `arch_diagram.png`, `er_diagram.png`.
- `Transformer.html`, `vit-explainer.html` — architecture explainers.
- `guida_jupyter_marimo.docx` — notebook tooling guide.

**Use for:** the prompt that makes the generator hedge instead of inventing, and the token→cost
arithmetic behind `declared_cost_eur`.

---

## Lezione 03 — Tool calling, agents, memory, cache ⭐⭐

- `Lab_03_demo_Senior.ipynb` — `@tool` decorator, ReAct loop, `tool_choice`, `planning_interval`,
  multi-agent via `can_call()`, Memory types, Window Memory, the cost of memory.
- `Cache_Memory/session_cache_memory.ipynb` — **exact cache, Redis cache, semantic cache
  (embedding-based)** with a visual comparison; Window / Summary / External memory.
- `Cache_Memory/session_cache_memory_lib.py` — the reusable library behind the notebook.
- `Cache_Memory/session_cache_memory_redis_optional.py`, `setup_session_cache_memory_env.sh`,
  `README_REDIS_INSTALL.md`.
- `S03_ToolCalling_Agent_Memory.pptx`, `s3_agent_toolcalling.html`.
- `Lab_03_Capstone_guidato.ipynb` / `_autonomo.ipynb`.

**Use for:** semantic caching of repeated/similar questions across rounds — the cheapest available
lever on `declared_cost_eur`.

---

## Lezione 04 — LLMs in production ⭐⭐

- `S04_LLM_Prod.pdf` (~22 pp).
- `S04_01_PokedexAI_Showcase.ipynb` — **streaming (`stream_invoke`, TTFT measurement), async
  (`a_invoke()` + `asyncio.gather()`), batch chunking**. Three "temporal contracts" for the same model.
- `S04_02_Osservabilità/` — full observability stack:
  - `Lab_04_OTel_01_ContextTracing_Intro.ipynb` — `ContextTracing`, manual spans, error tracing,
    multi-step pipeline traces, no infrastructure needed.
  - `Lab_04_OTel_02_Grafana_Live.ipynb`, `Lab_04_OTel_03_Capstone_Produzione.ipynb`.
  - `docker-compose.yml` + `prometheus.yml` + `tempo.yml` + `grafana/provisioning/**` (incl.
    `llm_monitoring.json` dashboard).
- `S04_03_LLM_Locali_e_Server_Remoti.ipynb` — Ollama / LM Studio / any OpenAI-compatible server via
  `OpenAILikeClient`; local vs cloud trade-off.
- `S04_04_streamlit_lab.ipynb` — Streamlit from zero to a chat UI wired to `datapizza-ai`
  (`st.session_state`, chat components).
- `llm_locali_guida.html`.
- `Lab_04_Capstone_v2_guidato.ipynb` / `_autonomo.ipynb`.

**Use for:** parallelising per-question generation across a round, latency percentiles, and a demo UI
for the final speech.

---

## Lezione 05 — Ideathon ⭐

- `ideathon_regolamento.html` — the rules format (mirrors how the hackathon is judged).
- `CommAIndo/Problem Statement Iniziale.pdf`, `CommAIndo/Problem Framing e architettura della
  soluzione.pdf` — a worked problem-framing → architecture pair.
- `EstimatesAI - SuperAIQuattro.md`, `AISolver/AI Solver.docx`, `Aitho.pptx`,
  `Ideathon_Iscrizione_Gruppi.xlsx`.
- `Ctrl+C-Ctrl+V/file-architettura-errato.md` + screenshots — a worked *counter*-example of an
  architecture write-up.

**Use for:** structuring the 10-minute final speech (architecture, errors and fixes, evaluation).

---

## Lezione 06 — Embeddings & RAG base ⭐⭐⭐

- `S06_Embeddings_RAG_Base.pdf` (~50 pp).
- `S06_RAG_Ingestion_e_Retrieval.ipynb` — **the ingestion canon**: source docs and their structure,
  tokenization as the real unit, chunking (§4: naive fixed-char / token-based / overlap /
  structure-aware, then all four compared), what to watch during ingestion, embedding, Qdrant,
  simple retrieval, and *how chunking changes retrieval*.
- `S06_NLP_Embeddings_Showcase.ipynb` — TF-IDF → GloVe → BERT → SBERT, PCA/UMAP visualisation,
  TF-IDF vs SBERT head-to-head. (Why lexical and dense retrieval fail differently → the argument for
  hybrid search.)
- `corpus_qdrant_docs/` — **five Italian reference docs on Qdrant**, also the corpus for the
  Retrieval Challenge: `00_guida_rapida.md`, `01_concetti_collections.md`,
  `02_indicizzazione_hnsw.md`, `03_filtering_payload.md` (⭐ payload filters, `must`/`should`/
  `must_not`, filtering during HNSW traversal), `04_deploy_produzione.md`.
- `data/embedding_corpus_it.json`, `requirements.txt`.
- `word2vec-explainer.html`, `word-embeddings-distance.html`, `S06_da_Word2Vec_a_SBERT.html`.

---

## Lezione 07 — Advanced RAG ⭐⭐⭐ (the richest lesson for this hackathon)

Split into three sub-folders.

### `Lezione 07 - 260626/` — the Advanced RAG live + challenge

- `01_showcase_rag.ipynb` — the live showcase: Docling structured parsing + `NodeSplitter`;
  **multimodal (figures + tables + captions)**; linear indexing chain; `DagPipeline` +
  `ToolRewriter` (with a rewriter ON/OFF demo); visual grounding in Streamlit.
- `app.py` — Streamlit app that answers over a PDF **and draws translucent rectangles on the PDF
  pages over the passages actually used** (PyMuPDF + PIL). Evidence you can show on stage.
- `prewarm.py` — run once to warm the Docling model cache; every later parse loads from
  `.docling_cache/` in milliseconds.
- `Mega Esercizio/` — ⭐ **the single most valuable folder**:
  - `README.md` — ten Advanced RAG exercises, each with *why · what to build · steps · API hints ·
    stretch goal · question*: **Es.0 hybrid BM25+dense+RRF**, Es.1 chunk granularity, Es.2 reading
    order (Docling vs naive PyMuPDF on 2-column layout), Es.3 measured granularity trade-off,
    Es.4 query rewriter, Es.5 propositions / Dense-X, Es.6 synthetic questions + HyDE,
    Es.7 parent-child (small-to-big), Es.8 reranker (Cohere + local fallback), Es.9 RAPTOR.
    Also: Late Chunking (and why it is impossible with `OpenAIEmbedder`), Modular RAG / RAG Fusion /
    Corrective RAG / Self-RAG.
  - `base_pipeline.py` — the reusable scaffold. Key functions: `load_env` (62), `make_client` (86),
    `make_embedder` (92), `parse_document` (101, disk-cached), `split_document` (121),
    `build_index` (138), `retrieve` (154), `ChunkFilter` (163), `build_ingestion_pipeline` (186),
    `ingest` (206), `build_base_dag` (249), `answer` (271). Also exports `FACT_TARGETS`: verified
    `(question, expected_page, keyword)` triples used as ground truth.
  - `materiale/GoogleSDLC.pdf` (51 pp prose report), `presentazione.pdf` (Advanced RAG deck),
    `skill-opt.pdf` (2-column paper — the reading-order test case).
  - `esercizi/00_hybrid_search/main.py` — stub only. `Soluzione/` is **missing** from this copy.
- `chunking-rag-pdf-multimodali.html`, `hybrid_search.html` — the theory explainers for exactly the
  two hardest parts of this hackathon.
- `Challenge iniziale 🐝/Best challenge.docx`.

### `Retrieval-Challenge/` — ⭐⭐⭐ a complete, small, config-driven retrieval lab

Structure worth copying wholesale: **all parameters in `config.py`, ingestion/retrieval/evaluation in
separate files, data under `data/`.**

- `config.py` — `EMBEDDER` (`openai` | `minilm-it` | `minilm-en` | `e5-small` | `bge-m3`),
  `CHUNKER` (`naive` | `structure_aware`), `CHUNK_MAX_CHAR`, `CHUNK_OVERLAP`, `TOP_K`, `COLLECTION`.
- `src/embeddings.py` — embedder factory keyed by a string; exposes `.dim` so the Qdrant collection
  is created with the right vector size.
- `src/ingest.py` (with TODOs) / `solution/ingest.py` (complete) — both chunkers, embedding, upsert.
- `src/retrieve.py` / `solution/retrieve.py` — query embedding + k-NN search; `retrieve_filtered`
  bonus (search inside one document only).
- `scripts/evaluate.py` — the judge: `hit@1 / hit@2 / hit@3` over the gold set.
- `scripts/run_experiments.py` — grid over `CHUNKERS × MAX_CHARS × OVERLAPS`.
- `data/corpus/` — 8 Italian docs (Qdrant + Pinecone), `data/gold/queries.json` — 14 gold queries.
- `README.md` (the brief, the levers, the timeline) and `Spiegazione.md` (a full walkthrough of every
  step with the reasoning and the surprising results).
- `S07_Capstone_Retrieval_Challenge.pptx`, `QA.md`.

### `Lezione7_12_06/` — the Lesson-06 lab material

- `Lab_06_demo.ipynb` — Word2Vec → BERT → SBERT → OpenAI embeddings, `small` vs `large` cost/benefit,
  first semantic search.
- `Lab_06_Capstone_guidato.ipynb` / `_autonomo.ipynb`, `S06_Companion.html`,
  `S06_Embedding_Ricerca_Semantica.pdf` (~51 pp).
- `corpus_s06/` — 15 markdown docs (runbooks, incident reports, Marvel-themed distractors). A good
  ready-made corpus for smoke-testing a retrieval change.

---

## Lezione 08 — Coding agents ⭐⭐

`Lezione 08 - 100726/` — five exercises, each in Python and Java:

1. `1_documentazione/` — documenting an existing codebase (`cost_monitor` app) + `PROMPT_SUGGERITI.md`.
2. `2_refactor/` — guided refactor + `PROMPT_REFACTOR.md`.
3. `3_istruzioni/` — ⭐ **`istruzioni_template/`**: `AGENTS.md`, `refactor.instructions.md`,
   `refactor-per-criteri.prompt.md`, `CRITERI_ESEMPIO.md`, `scripts/verify.py`. A working pattern for
   steering a coding agent with criteria files and a deterministic verifier.
4. `4_test/` — test generation (`danno.py` / `test_danno.py`), `skills_da_provare/README.md`.
5. `5_debug/` — a broken DevOps setup (Dockerfile, CI workflow, `ci_error_log.txt`) to debug.

Plus `GROUP_REVIEW_TEMPLATE.md` and `Track Senior.pdf` (~68 pp).

---

## Lezione 09 — RAG evaluation ⭐⭐⭐

Scenario: "OndaCloud" help-desk RAG; build a judge you can trust while the team is on holiday.

- `Showcase_S09.ipynb` — two families of failure; the hand-written judge and why the rubric is
  everything; **the three judge biases and how to defuse them**; absolute scoring vs pairwise; RAGAS;
  tracing as the genealogy of a score.
- `Esercizi/README.md` — ⭐ includes a **metric map**: for each metric, whether it needs a human
  reference, what it measures, and what it costs (recall@k / precision@k / MRR / don't-know rate free;
  ContextPrecision, Faithfulness, AnswerRelevancy = LLM, no reference; ContextRecall,
  AnswerCorrectness, SemanticSimilarity = need a reference; Cohen's Kappa measures *you vs the judge*).
- `Esercizi/base_eval.py` — real ingest of the 15-doc corpus into in-memory Qdrant, then
  `dense_retrieve(domanda, k)` / `naive_rag(domanda, k)`.
- `Esercizi/s09_evals.py` — ⭐ copy-ready: `recall_at_k`, `mrr`, `contesto_testuale`,
  `dont_know_rate`, `estimate_cost`, `latency_cost` (p50/p95), `ragas_generation`,
  `ragas_retrieval`, `hallucination_deepeval`.
- `Esercizi/gold_estate.py` — a 12-question gold set + 3 out-of-corpus questions, each with a
  documented *purpose* (indirect-semantic, lexical, trap, multi-hop, abstention).
- `Esercizi/materiale/` — `ticket_pool.py` (24 raw help-desk tickets → raw material for a gold set),
  `valida_gold.py` (deterministic, no-LLM gold validator), `casi_calibrazione.py` (human-labelled
  cases for judge calibration).
- `Esercizi/s09_tracer.py` — a teaching-grade OpenTelemetry/OpenInference-style tracer; the docstring
  explains how `datapizza.tracing.ContextTracing` maps onto it.
- `Esercizi/esercizi/00..07/` — briefs; `Esercizi/Soluzione/00..07/` — **full solutions present**,
  including `04_calibrazione/` with `NOTA_TARATURA.md` and `REVISIONE_ETICHETTE.md`.
- `Esercizi/corpus_estate/` — 15 docs (runbooks, incidents, beach-club notes).
- `Teoria/Artefatti/bias_giudice.html`, `ragas_eval.html`; `Teoria/Slide in slidev/` — the deck source
  with interactive Vue components (`CalibrationLab`, `RecallLab`, `RankingLab`, `JudgeSwap`,
  `TraceExplorer`, `FailureDiagnosis`, …) and a built `dist/`.

---

## EstimatesAI ⭐⭐ — a full reference implementation

`Lezioni/EstimatesAI/` — a production-shaped `datapizza-ai` project (the Ideathon winner's build).

- `README.md` + `PRESENTAZIONE_DETTAGLIATA.md` + `Presentation.pptx.pdf` — description, stakeholders,
  ROI, architecture, components, workflow, future improvements. A model for the final speech.
- `src/estimates_ai/` — `agent/orchestrator.py`, `llm/client_factory.py`, `config/settings.py`,
  `config/pricing.py`, `memory/store.py`, `observability/{tracing,metrics,traced_tool}.py`
  (Prometheus counters/histograms for requests, prompt/completion tokens, latency, errors),
  `schemas/*.py` (one pydantic schema per tool), `tools/*.py` + `tools/test/*_test.py`.
- `app/streamlit_app.py` + `app/components/{chat,sidebar}.py`.
- Caveat: `config/pricing.py`, `observability/traced_tool.py` and `memory/store.py` are **empty
  stubs** in this copy — the working cost table is the `PRICES` dict in `Lezione 09/Esercizi/s09_evals.py`.
- `monitoring/` — Grafana/Prometheus/Tempo provisioning; `docker-compose.yaml`; `pyproject.toml` + `uv.lock`.

**Use for:** project layout, per-tool pydantic schemas, and the cost/metrics plumbing that feeds a
`declared_cost_eur` field honestly.

---

## Standalone HTML explainers (self-contained, open in a browser)

`Lezione 01`: ml-training, nlp-statistico, rnn-lstm-gru · `Lezione 02`: Transformer, vit-explainer ·
`Lezione 03`: s3_agent_toolcalling · `Lezione 04`: llm_locali_guida · `Lezione 06`: word2vec,
word-embeddings-distance, da_Word2Vec_a_SBERT · `Lezione 07`: **chunking-rag-pdf-multimodali**,
**hybrid_search**, S06_Companion · `Lezione 09`: bias_giudice, ragas_eval.

The two bolded ones cover the hackathon's hardest problems.
