# Ported patterns — course code that maps directly onto hackaton-mille

Every snippet below is taken from the course archive (file cited) and is the shape the course
actually used. Adapt names to this repo's `baseline_naive_rag.py`; do not paste blindly.

---

## 1. Deterministic chunk ids → makes incremental ingestion safe

Source: `Lezione 07/Retrieval-Challenge/solution/ingest.py` + `Spiegazione.md` (PASSO 2).

```python
import uuid

def _id_chunk(file: str, testo: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file}::{testo}"))
```

Re-ingesting the same chunk yields the same id, so the upsert overwrites instead of duplicating. With
`uuid4()` every run adds duplicate points. This is the enabling trick for replacing this hackathon's
all-or-nothing `--rebuild` with an incremental ingest: hash the file, skip documents whose chunks are
already in the collection, and let the upsert dedupe the rest.

Note the constraint from `Mega Esercizio/README.md` Es.5/Es.7: a `datapizza.type.Chunk` `id` **must
be a valid UUID** — `"0-1"` will fail.

## 2. The two chunkers, and the measured result

Source: `Retrieval-Challenge/solution/ingest.py`, results narrated in `Spiegazione.md`.

- `_chunk_naive` — `TextSplitter(max_char=..., overlap=...).split(testo)`. `TextSplitter` works on a
  **string**; `NodeSplitter` works on a parsed **node** tree.
- `_chunk_structure_aware` — two phases: build atomic blocks by walking lines and toggling an
  `in_code` flag on ``` fences (never split a code block; blank line outside code = end of
  paragraph), then accumulate blocks into chunks up to `max_char`, saving the last `#` heading as a
  `breadcrumb` in the metadata.

**The measured outcome, which is the actual lesson:** at `max_char=600` the structure-aware chunker
scored *worse* than naive (79% vs 86%); only at `max_char=400` did the structural advantage appear
(93% vs 79%). Granularity and strategy interact — sweep them together, never assume the smarter
chunker wins.

## 3. Embedder factory + the dimension trap

Source: `Retrieval-Challenge/src/embeddings.py`, `config.py`, `Spiegazione.md` (PASSO 4).

- Select the model with one string; the factory exposes `.dim`, and the Qdrant collection is created
  from `embedder.dim`. Change the model (384 → 1024 → 1536) and the collection **must** be rebuilt.
- Use `embed_passages(...)` for documents and `embed_query(...)` for queries — models like
  `multilingual-e5-small` prepend different prefixes (`passage:` / `query:`) and lose quality if you
  mix them up.
- Free local multilingual options that need no API key, useful for cheap experiment sweeps before
  spending on `text-embedding-3-small`: `paraphrase-multilingual-MiniLM-L12-v2` (384),
  `intfloat/multilingual-e5-small` (384), `BAAI/bge-m3` (1024). All Italian-capable — relevant, since
  this archive is Italian.

## 4. Qdrant: named vectors, and payload filtering during search

Source: `Retrieval-Challenge/solution/{ingest,retrieve}.py`, `Lezione 06/corpus_qdrant_docs/03_filtering_payload.md`.

```python
from datapizza.type import Chunk, DenseEmbedding

store.add([Chunk(id=c["id"], text=c["text"],
                 embeddings=[DenseEmbedding(name="dense", vector=v)],
                 metadata=c["metadata"])
           for c, v in zip(chunks, vettori)], collection_name=COLLECTION)

hits = store.search(collection_name=COLLECTION, query_vector=embedder.embed_query(q),
                    k=k, vector_name="dense")
```

Filtered retrieval (the bonus in that challenge) — this is the hook for `act` / `reliability` /
`modality` awareness:

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

hits = store.get_client().query_points(
    collection_name=COLLECTION, query=q_vec, using="dense", limit=k, with_payload=True,
    query_filter=Filter(must=[FieldCondition(key="file", match=MatchValue(value=file))]),
).points
```

`03_filtering_payload.md` is worth reading in full: `must` / `should` / `must_not` semantics, and the
fact that Qdrant applies the filter **while traversing HNSW**, not afterwards — so a filtered search
still returns `k` results instead of a truncated list. It needs a payload index on the field.

## 5. Hybrid search: BM25 + dense, fused with RRF

Source: `Mega Esercizio/README.md` Es.0 (plus `Lezione 07/.../hybrid_search.html`).

Dense cosine captures meaning but is weak on exact lexical matches — acronyms, proper nouns, rare
terms. In this hackathon that is names, places, dates and unit designations from 1860. BM25 is the
opposite. RRF fuses them using only rank, so the incomparable score scales never meet:

```python
from rank_bm25 import BM25Okapi
bm25 = BM25Okapi([tokenizza(c.text) for c in chunks])
# per query: dense top-k, BM25 top-k by bm25.get_scores(tokens)
# score(doc) = Σ over rankings of 1 / (k_rrf + rank)
```

The course notes that `QdrantVectorstore` supports sparse vectors but exposes **no native fusion and
no sparse embedder**, so RRF is built by hand. Sweep `k_rrf ∈ {1, 10, 60, 200}` and observe how
little it moves — stability is the point.

## 6. Retrieve wide, rerank, deliver narrow

Source: `Mega Esercizio/README.md` Es.8.

"Recupera con generosità, consegna con parsimonia": retrieve `k=15`, rerank with a cross-encoder,
keep the top 5. That top-5 is exactly this hackathon's `contexts` cap, with `rank` 1..N consecutive.

```python
from datapizza.modules.rerankers.cohere import CohereReranker
CohereReranker(api_key=..., endpoint="https://api.cohere.com",
               top_n=5, model="rerank-v3.5").rerank(query, documents)  # -> list[Chunk]
```

Cohere offers a free trial key. The course's own advice is to write a **local lexical fallback** so
the pipeline still runs without the key — worth doing here too, since a missing third-party key
during the Gold Run would be fatal.

## 7. Query rewriting before retrieval

Source: `Mega Esercizio/README.md` Es.4, live demo in `01_showcase_rag.ipynb` Parte 4.

```python
from ... import ToolRewriter
rw = ToolRewriter(client=make_client(system_prompt=SYS), system_prompt=SYS)
rw.rewrite(q)  # -> str
```

The course's A/B protocol: pick 2–3 vague queries, compare retrieved pages raw vs rewritten, and
measure Jaccard overlap of the retrieved sets. The honest finding is that rewriting helps on **vague
or paraphrased** queries and does nothing on already-easy factual ones — so measure the delta on hard
queries, not on the average. For a 19th-century archive the analogous move is expanding modern
phrasing into period vocabulary and spelling variants.

## 8. Other retrieval structures worth stealing

All from `Mega Esercizio/README.md`, each with steps and API hints:

- **Es.5 propositions / Dense-X** — index atomic self-contained sentences instead of raw chunks.
  Raises precision on pointed questions.
- **Es.6 synthetic questions and HyDE** — index the *questions* a chunk answers, or embed a
  hypothetical answer document instead of the question.
- **Es.7 parent-child (small-to-big)** — index small children (`TextSplitter(max_char=250,
  overlap=40)`) carrying `metadata["parent_id"]`, retrieve children, then deduplicate up to the
  parents (`max_char=1200`) and hand *those* to the generator. The small one finds, the big one
  answers. Directly relevant: this hackathon caps you at 5 contexts, so each context should carry as
  much usable evidence as possible.
- **Es.9 RAPTOR** — cluster chunk embeddings (KMeans), summarise each cluster with the LLM, index the
  summaries as level-1 nodes, retrieve per level. Good for "what happened overall" questions that no
  single 1860 document answers.
- **Es.2 reading order** — before chunking, check the text comes out in the right order. Compare
  naive `fitz` `page.get_text()` against Docling on a multi-column page. A wrong reading order
  poisons the embedding of every chunk downstream. Do this check on the `garib_*` scans.

## 9. Parse once, cache on disk

Source: `Mega Esercizio/base_pipeline.py::parse_document` (line 101) and `prewarm.py`.

Docling parsing is the slow, model-downloading step. The course pickles the parsed document tree into
a `.cache/` directory and reloads it in milliseconds, with a one-off `prewarm.py` to warm the models.
Adopt this before any chunking experiment: it turns a 10-minute sweep into a 10-second one, and it is
what makes "one experiment at a time" affordable.

## 10. Measuring retrieval, for free

Source: `Lezione 09 - 240726/Esercizi/s09_evals.py`; the judge pattern in
`Retrieval-Challenge/scripts/evaluate.py`.

- `recall_at_k(retrieve_fn, gold, k)` — is the expected source in the top-k?
- `mrr(retrieve_fn, gold, k)` — how *high* it lands (1.0 ideal). recall says *whether*, MRR says
  *where*.
- `hit@1 / hit@2 / hit@3` (Retrieval-Challenge) — the simplest possible judge. `hit@1` is the one
  that tells you the retriever genuinely understood the question.
- `run_experiments.py` — grid over `CHUNKERS × MAX_CHARS × OVERLAPS`, embedder loaded once (it is the
  heavy component). Copy this file's shape for your own sweeps.

None of these need an LLM or a human reference. Build them first.

## 11. Measuring generation, and what it costs

Source: `Lezione 09 - 240726/Esercizi/README.md` (the metric map) and `s09_evals.py`.

| Metric | Needs human reference? | Measures | Cost |
| --- | :---: | --- | --- |
| recall@k, precision@k, MRR, don't-know rate | no | retrieval / abstention | free |
| ContextPrecision | no | retrieval | LLM |
| ContextRecall | **yes** | retrieval | LLM |
| Faithfulness, AnswerRelevancy | no | generation | LLM |
| AnswerCorrectness | **yes** | generation | LLM |
| SemanticSimilarity | **yes** | generation | embeddings only |
| DeepEval HallucinationMetric | no (needs context) | generation | LLM |
| Calibrated pass/fail judge | **yes (human labels)** | end-to-end | LLM |
| Cohen's Kappa | — | *your* agreement with the judge | free |

The gold set unlocks half the panel. If time runs short, the course's own fallback is to keep
**Faithfulness + ContextPrecision + ContextRecall** and drop the rest — which is also the closest
proxy for this hackathon's scoring.

Wrappers ready to use: `ragas_generation(...)`, `ragas_retrieval(...)`,
`hallucination_deepeval(...)`. Pin `ragas==0.4.3` with `langchain-community>=0.3,<0.4.2` — the
course's requirements.txt documents why the pin is mandatory.

## 12. Abstention

Source: `s09_evals.py::dont_know_rate`, `gold_estate.py`.

The convention: gold entries with `source=None` are out-of-corpus; the correct behaviour is to
refuse, and `dont_know_rate` is the fraction of those where the system abstained (ideal 1.0). Build
the equivalent for the Garibaldi archive — questions whose answer genuinely is not in the 15
documents — and track that rate alongside faithfulness. It is the direct measurement of "declare
uncertainty when the evidence is not enough".

`gold_estate.py` is also a good model for gold-set *design*: indirect semantic paraphrases,
lexically-precise questions (where dense retrieval struggles), one **trap** question that is
semantically close to the wrong document, one multi-hop question, and the out-of-corpus set. Every
`ref` quotes only figures that literally appear in the cited source.

## 13. Latency and cost telemetry

Source: `s09_evals.py::estimate_cost` / `latency_cost`.

```python
def estimate_cost(prompt_tokens, completion_tokens, model="gpt-4o-mini"):
    p = PRICES[model]
    return (prompt_tokens * p["in"] + completion_tokens * p["out"]) / 1_000_000
```

`latency_cost` returns `latency_p50_s`, `latency_p95_s`, `cost_per_query_usd`, with the standing
instruction: **watch p95, not the mean** — the tail is what the user feels. This hackathon's
`telemetry.declared_cost_eur` and `model_calls[].{input_tokens, output_tokens, cached_input_tokens}`
want the same accounting, per question, in EUR. Keep a price table per model — the course's is a
plain dict of USD per 1M tokens at the top of `s09_evals.py`:

```python
PRICES = {
    "gpt-4o-mini":            {"in": 0.15, "out": 0.60},
    "text-embedding-3-small": {"in": 0.02, "out": 0.0},
}
```

Extend it for the models you actually call, count embedding tokens too, and convert USD → EUR once at
the end rather than per call.

Levers the course covers, in order of payoff here:

1. **Semantic cache** (`Lezione 03/Cache_Memory/`) — exact, Redis, and embedding-based caches. Repeated
   or near-identical questions across rounds cost nothing the second time. Note `cached_input_tokens`
   exists in the submission schema.
2. **Async fan-out** (`Lezione 04/S04_01_PokedexAI_Showcase.ipynb`) — `a_invoke()` +
   `asyncio.gather()` turns N sequential questions into one wall-clock batch.
3. **Fewer model calls** — every rewrite, proposition pass, HyDE generation and LLM rerank is an extra
   call that lands in `model_calls`. Measure whether it earns its place.

## 14. Tracing

Source: `Lezione 04/S04_02_Osservabilità/Lab_04_OTel_01_ContextTracing_Intro.ipynb`,
`Lezione 09/Esercizi/s09_tracer.py`.

```python
from datapizza.tracing import ContextTracing
with ContextTracing().trace("nome_operazione") as t:
    ...
```

`ContextTracing` sits on top of OpenTelemetry; in production it exports over OTLP to Langfuse, Arize
Phoenix or LangSmith. `S04_02_Osservabilità/docker-compose.yml` brings up Grafana + Prometheus +
Tempo with a provisioned `llm_monitoring.json` dashboard if you want a live picture during the demo.
`s09_tracer.py` shows the underlying span mechanics if you'd rather stay dependency-free.

---

## Suggested order of attack for hackaton-mille

Grounded in the course's own workflow rule — *one experiment at a time; hypothesis, change one
component, compare, keep or discard*:

1. **Instrument before optimising.** Port `recall_at_k` / `mrr` / `hit@k` and write a small gold set
   over `eval/sample_questions.json` plus your own questions. Without it every later change is a guess.
2. **Fix ingestion.** Docling parse cache + deterministic ids; check reading order on the `garib_*`
   scans; decide what text a map/scan actually contributes and make sure that same text is what
   lands in `contexts[].content`.
3. **Sweep chunking.** `max_char × overlap × chunker`, judged by `hit@1`. Cheap, local, and the
   course's evidence says the ranking of strategies flips with granularity.
4. **Add hybrid BM25 + RRF.** Highest expected payoff on a corpus full of proper nouns and dates.
5. **Add a reranker** with a local fallback; retrieve 15, deliver 5.
6. **Then, and only then**, query rewriting / HyDE / parent-child, each measured against the same gold.
7. **Reliability awareness.** Put `act`, `reliability`, `origin_type`, `modality` in the payload;
   filter or re-weight; expose the label to the generator so it can hedge on propaganda and
   contested versions.
8. **Abstention + faithfulness.** Out-of-corpus questions and a don't-know rate; RAGAS faithfulness
   on the rest.
9. **Cost and latency.** Semantic cache, async fan-out, prune superfluous model calls; fill telemetry
   from real token counts, never estimates.
10. **The speech.** `Lezione 05 - Ideathon/` for framing, `EstimatesAI/README.md` for how to present
    an architecture, and your own experiment log for "errors and fixes" — which the course's whole
    measure-then-change method produces for free.
