---
name: corso-datapizza
description: Navigate the AITHO/Datapizza AI course archive (~/Desktop/Corso AI Datapizza) to find prior art for hackaton-mille. Use when working on this RAG pipeline and you need a worked example, an API signature, a measured result, or a technique the course already covered — chunking, hybrid search / BM25+RRF, reranking, query rewrite, HyDE, parent-child, Docling parsing, OCR and multimodal PDFs, Qdrant payload filtering, gold datasets, recall@k / MRR / hit@k, RAGAS faithfulness, LLM-as-judge calibration, abstention / don't-know rate, token cost and latency measurement, caching, tracing, Streamlit demos. Do NOT re-derive from scratch what the course already solved.
---

# Corso AI Datapizza — archive navigator for hackaton-mille

The course archive is a 9-lesson AITHO/Datapizza GenAI program built on the **same stack this
hackathon uses**: `datapizza-ai`, `OpenAIEmbedder` (`text-embedding-3-small`, 1536 dim), Qdrant,
`DoclingParser`, `DagPipeline`. Almost every problem in `hackaton-mille` has a worked, runnable
precedent in there.

**Archive root** (quote it — spaces in the path):

```bash
CORSO="/mnt/c/Users/djchr/OneDrive - Aitho/Desktop/Corso AI Datapizza"
```

## How to use this skill

1. Find your problem in the routing table below → open only the file(s) named.
2. If you need the full inventory (every lesson, every deck, every notebook), read
   `references/course-map.md`.
3. If you want the ported code patterns and the course's *measured* results (what actually worked,
   with numbers), read `references/rag-playbook.md`.

Read the specific file, not the whole lesson folder. Notebooks are large — grep them or extract
markdown headers before dumping cells.

## Routing table — hackathon problem → course file

| You are working on | Go to (relative to `$CORSO`) |
| --- | --- |
| **Advanced RAG technique menu** (hybrid, granularity, rewriter, propositions, HyDE, parent-child, reranker, RAPTOR) — each with steps + API hints | `Lezioni/Lezione 07/Lezione 07 - 260626/Mega Esercizio/README.md` ⭐ **start here** |
| **Reusable RAG scaffold** in `datapizza-ai`: parse-with-cache → split → filter → embed → Qdrant → DagPipeline | `Lezioni/Lezione 07/Lezione 07 - 260626/Mega Esercizio/base_pipeline.py` |
| **Docling parsing, multimodal figures/tables, `ToolRewriter`, `DagPipeline`** | `Lezioni/Lezione 07/Lezione 07 - 260626/01_showcase_rag.ipynb` |
| **Scans / OCR / bad reading order** (`data/act_2/garib_*.pdf`) | Mega Esercizio README §Es.2 + `01_showcase_rag.ipynb` Parte 1–2; caching of Docling models: `Mega Esercizio/prewarm.py` |
| **Chunking strategies** (fixed-char, token, overlap, structure-aware) | `Lezioni/Lezione 06/S06_RAG_Ingestion_e_Retrieval.ipynb` §4 |
| **Chunker implementations + measured comparison** | `Lezioni/Lezione 07/Retrieval-Challenge/solution/ingest.py` and `Spiegazione.md` |
| **Retrieval eval harness** (config-driven, `hit@k` judge, param grid) | `Lezioni/Lezione 07/Retrieval-Challenge/` — `config.py`, `scripts/evaluate.py`, `scripts/run_experiments.py` |
| **Metric functions ready to copy**: recall@k, MRR, don't-know rate, cost, p50/p95 latency, RAGAS, DeepEval | `Lezioni/Lezione 09 - 240726/Esercizi/s09_evals.py` ⭐ |
| **Building a gold set** (incl. trap, multi-hop and out-of-corpus questions) | `Lezioni/Lezione 09 - 240726/Esercizi/gold_estate.py`, `materiale/valida_gold.py`, `esercizi/01_gold_dataset/` |
| **Abstention / "non lo so"** — the hackathon's *declare uncertainty* requirement | `s09_evals.py::dont_know_rate` + the `FUORI_CORPUS` entries in `gold_estate.py` |
| **Faithfulness, answer relevancy, judge bias, pairwise vs absolute** | `Lezioni/Lezione 09 - 240726/Showcase_S09.ipynb`; theory artefacts `Teoria/Artefatti/bias_giudice.html`, `ragas_eval.html` |
| **Calibrating an LLM judge against human labels (Cohen's Kappa)** | `Lezioni/Lezione 09 - 240726/Esercizi/esercizi/04_calibrazione/` + `Soluzione/04_calibrazione/` |
| **Qdrant: collections, HNSW, payload filtering, prod deploy** — for filtering by `act` / `reliability` / `modality` | `Lezioni/Lezione 06/corpus_qdrant_docs/*.md` (03 = filtering) |
| **`declared_cost_eur` + `model_calls` telemetry** | `s09_evals.py::estimate_cost` / `latency_cost`; token accounting in `Lezioni/Lezione 02/Lab_02_demo.ipynb` §Stima dei Costi |
| **Cutting cost**: exact cache, Redis cache, semantic cache | `Lezioni/Lezione 03/Cache_Memory/session_cache_memory.ipynb` + `session_cache_memory_lib.py` |
| **Cutting latency**: streaming, `a_invoke()` + `asyncio.gather()`, batching | `Lezioni/Lezione 04/S04_01_PokedexAI_Showcase.ipynb` |
| **Tracing / observability** (`ContextTracing`, OTel, Grafana+Prometheus+Tempo stack) | `Lezioni/Lezione 04/S04_02_Osservabilità/` (3 notebooks + `docker-compose.yml`); teaching tracer: `Lezione 09 - 240726/Esercizi/s09_tracer.py` |
| **Prompt engineering + structured/pydantic output** | `Lezioni/Lezione 02/Lab_02_demo.ipynb`; deck `Lezioni/Lezione 02/Prompt_Engineering.pdf` |
| **Tool calling, agents, ReAct, multi-agent, memory** | `Lezioni/Lezione 03/Lab_03_demo_Senior.ipynb` |
| **Production project layout** (src layout, per-tool pydantic schemas, prometheus metrics, Streamlit + docker-compose) | `Lezioni/EstimatesAI/` — a full reference implementation |
| **Streamlit demo UI** | `Lezioni/Lezione 04/S04_04_streamlit_lab.ipynb`; visual PDF grounding app: `Lezioni/Lezione 07/Lezione 07 - 260626/app.py` |
| **Final 10-min speech / problem framing** | `Lezioni/Lezione 05 - Ideathon/` (`ideathon_regolamento.html`, `CommAIndo/Problem Framing e architettura della soluzione.pdf`, `EstimatesAI - SuperAIQuattro.md`) |
| **Driving coding agents well** (AGENTS.md, instruction files, refactor/test/debug prompts) | `Lezioni/Lezione 08/Lezione 08 - 100726/3_istruzioni/istruzioni_template/` |

## Mapping the archive onto *this* hackathon's specifics

`hackaton-mille` is a RAG over a 1860 Garibaldi archive: **15 documents**, acts 1–2, with
`origin_type` ∈ {simulated, authentic, derived}, `modality` ∈ {text, scan, table, map} and
`reliability` ∈ {reference, official_but_simplified, partial, propaganda, ambiguous, allusive,
didactic, authentic_unreviewed}. Scoring rewards faithful answers with real cited contexts,
abstention when evidence is thin, and plausible cost/latency telemetry.

That shapes which course material actually pays off:

- **`reliability` and `act` are payload fields, not decoration.** Index them as Qdrant payload and
  filter/re-weight on them — `Lezione 06/corpus_qdrant_docs/03_filtering_payload.md` explains that
  Qdrant filters *during* HNSW traversal, so filtered search still returns k results.
- **Propaganda vs contested versions** is a reranking + prompt problem: retrieve wide, rerank
  (Mega Esercizio Es.8), and let the generator see the reliability label so it can hedge.
- **4 of the 15 docs are real scans** (`garib_*`) and one is a map PNG. Es.2 (reading order) and the
  multimodal part of `01_showcase_rag.ipynb` are the only places the course handles this. Whatever
  OCR text or image description you feed the model is what must go into `contexts[].content`.
- **`--rebuild` is all-or-nothing and expensive.** The course's fix for exactly this is deterministic
  chunk ids (`uuid5` over file+text, see `Retrieval-Challenge/Spiegazione.md` PASSO 2) plus the
  on-disk parse cache in `base_pipeline.parse_document()`. That combination is what makes
  incremental ingestion safe.
- **Max 5 contexts, ranks 1..N consecutive** matches the course's "retrieve wide (k=15), rerank,
  deliver top-5" pattern one-for-one.

## Archive gotchas

- `Lezioni/` is canonical. `Laboratorio/` is a partial working copy of Labs 02–04 (same notebooks,
  different execution outputs) — prefer `Lezioni/`.
- `Laboratorio/.venv` is a **Windows** Python 3.10 venv; it cannot be activated from WSL. Build your
  own env in the hackathon repo.
- The `Lezione 0X ....zip` files at the top of `Lezioni/` are the original downloads, already
  extracted alongside. Ignore them.
- `Documenti Vari/` is course admin paperwork (attendance, questionnaires). Nothing technical.
- Lesson 06 material is split across **two** folders: `Lezione 06/` (embeddings + RAG ingestion) and
  `Lezione 07/Lezione7_12_06/` (Lab_06 demo + capstone + the S06 deck). Lesson 07's own material is
  under `Lezione 07/Lezione 07 - 260626/`.
- `Mega Esercizio/Soluzione/` is referenced by its README but is **not present** in this copy — only
  `esercizi/00_hybrid_search/main.py` (a stub) survives. The README's step-by-step + API hints are
  the real deliverable there.
- Several `.env` files sit in the archive with live keys (`Laboratorio/.env`,
  `Lezione 07/.../Mega Esercizio/.env`, `Lezioni/EstimatesAI/.env`). Never copy them into this repo
  or into any output.
- The PDFs are image-heavy slide decks (22–68 pages). Read them with the `pages` parameter, and
  prefer the HTML explainers or notebooks when an equivalent exists — they carry the same content in
  greppable form.

## Language note

Everything in the archive is in Italian, including variable names in some solutions
(`domanda`, `risposta`, `contesto`, `fonte`). Keep that in mind when grepping.
