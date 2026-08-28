"""baseline_naive_rag.py — starter e2e per l'hackathon «Il caso dei Mille».

Questo file è la baseline ufficiale da lanciare: ingest (Docling → chunk → embed →
Qdrant) + naive dense RAG + scrittura/validazione di submission.json.

In produzione conviene spezzare organizzare le varie parti
in moduli separati. Qui restano insieme per chiarezza didattica.

Requisiti: OPENAI_API_KEY nel .env (embedding + LLM). Nessun fallback senza API.

Esempio:
  python baseline_naive_rag.py \\
    --questions eval/sample_questions.json \\
    --round-id sample \\
    --output outputs/submission_sample.json \\
    --rebuild
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---------------------------------------------------------------------------
# Contratto submission (= forma di eval/submission.example.json)
# ConfigDict(extra="forbid"): campi non previsti → errore (come additionalProperties: false).
# ValidationError: eccezione di Pydantic quando il JSON non rispetta i Field.
# ---------------------------------------------------------------------------


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1, le=5)
    document_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ModelCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: int = Field(ge=0)
    declared_cost_eur: float = Field(ge=0)
    model_calls: list[ModelCall] = Field(default_factory=list)


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    contexts: list[Context] = Field(default_factory=list, max_length=5)
    telemetry: Telemetry


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    round_id: str = Field(min_length=1)
    answers: list[Answer] = Field(min_length=1)


def validate_payload(
    payload: dict,
    questions: dict | None = None,
    manifest: dict | None = None,
    round_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        submission = Submission.model_validate(payload)
    except ValidationError as exc:
        return [error["msg"] + " @ " + ".".join(map(str, error["loc"])) for error in exc.errors()]
    for answer in submission.answers:
        ranks = [context.rank for context in answer.contexts]
        if ranks != list(range(1, len(ranks) + 1)):
            errors.append(f"{answer.question_id}: i rank dei contesti devono essere 1..N senza buchi")
    ids = [answer.question_id for answer in submission.answers]
    if len(ids) != len(set(ids)):
        errors.append("question_id duplicati")
    if round_id and submission.round_id != round_id:
        errors.append(f"round_id atteso {round_id}, ricevuto {submission.round_id}")
    if questions:
        expected = [row["question_id"] for row in questions["questions"]]
        actual = [row.question_id for row in submission.answers]
        if set(actual) != set(expected) or len(actual) != len(expected):
            errors.append(f"Copertura question_id non esatta. Attesi {expected}; ricevuti {actual}")
    if manifest:
        allowed = {row["document_id"] for row in manifest["documents"]}
        for answer in submission.answers:
            for context in answer.contexts:
                if context.document_id not in allowed:
                    errors.append(f"{answer.question_id}: document_id non disponibile: {context.document_id}")
    return errors


# ---------------------------------------------------------------------------
# Telemetria / costo autodichiarato
# ---------------------------------------------------------------------------


def declared_cost_eur(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    override = os.getenv("DECLARED_COST_EUR")
    if override is not None and override.strip() != "":
        return max(0.0, float(override))
    input_rate = float(os.getenv("COST_INPUT_PER_MILLION_EUR", "0") or 0)
    output_rate = float(os.getenv("COST_OUTPUT_PER_MILLION_EUR", "0") or 0)
    cached_rate = float(os.getenv("COST_CACHED_INPUT_PER_MILLION_EUR", str(input_rate)) or 0)
    return round(
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate
        + (cached_input_tokens / 1_000_000) * cached_rate,
        6,
    )


def _token_usage(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0
    input_tokens = int(getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0)
    cached = int(getattr(usage, "cached_input_tokens", 0) or 0)
    return input_tokens, output_tokens, cached


def _meta_get(metadata: Any, key: str, default: str = "") -> str:
    if metadata is None:
        return default
    if isinstance(metadata, dict):
        value = metadata.get(key, default)
    else:
        value = getattr(metadata, key, default)
    return default if value is None else str(value)


# ---------------------------------------------------------------------------
# Scelta file primario dal manifest
# ---------------------------------------------------------------------------


def choose_primary(document: dict, project_root: Path) -> Path | None:
    """Un documento → un file. Se per errore ce ne fossero più, vince il PDF."""
    candidates: list[Path] = []
    for record in document.get("file_records", []):
        path = project_root / record["path"]
        if path.is_file():
            candidates.append(path)
    if not candidates:
        return None
    if len(candidates) > 1:
        candidates.sort(key=lambda p: (0 if p.suffix.lower() == ".pdf" else 1, p.name))
        print(f"warning: {document['document_id']} ha {len(candidates)} file; uso {candidates[0].name}")
    return candidates[0]


def iter_ingest_files(
    manifest: dict,
    project_root: Path,
    acts: list[int] | None = None,
) -> list[tuple[Path, dict]]:
    """File da ingerire, con la voce di manifest che li descrive.

    `acts=None` (default) = tutto il manifest.
    """
    rows: list[tuple[Path, dict]] = []
    for document in manifest["documents"]:
        if acts and document.get("act") not in acts:
            continue
        primary = choose_primary(document, project_root)
        if primary is None:
            print(f"skip (nessun file): {document['document_id']}")
            continue
        rows.append((primary, document))
    return rows


# ---------------------------------------------------------------------------
# Lab_08: ingest + naive dense RAG
# ---------------------------------------------------------------------------


EMB_NAME = "content_embedding"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
PARSE_CACHE = Path(os.getenv("PARSE_CACHE_PATH", "outputs/parse_cache"))
# Modality del manifest che corrispondono a PDF nativi digitali: hanno gia' un layer di testo
# pulito e l'OCR full-page lo peggiora (i->1, o->0, virgole->punto e virgola).
DIGITAL_MODALITIES = {"text", "table"}
# FORCE_OCR_ALL=1 riporta l'ingest al comportamento originale (OCR su tutto): serve per gli A/B
# sul parsing senza toccare il codice.
FORCE_OCR_ALL = os.getenv("FORCE_OCR_ALL") == "1"
CHUNK_MAX_CHAR = int(os.getenv("CHUNK_MAX_CHAR", "1024"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "128"))
CHUNK_MIN_CHAR = int(os.getenv("CHUNK_MIN_CHAR", "80"))
# E4: quanti candidati chiedere a ciascun retriever prima della fusione RRF. Misurato: 15, 30 e 60
# selezionano gli stessi cinque documenti, quindi resta 15.
FETCH_K = int(os.getenv("FETCH_K", "15"))
# HYBRID=0 torna al solo denso, per gli A/B senza toccare il codice.
HYBRID = os.getenv("HYBRID", "1") == "1"
# E2: 0 = consegna sempre k contesti; >0 = taglia sotto questa frazione del punteggio fuso migliore.
# Acceso a 0,90 dopo il round 2: la precision ufficiale e' `pertinenti / documenti unici consegnati`,
# quindi il quinto documento debole si paga e non porta niente. Misurato sul gold reale: recall e
# hit@5 restano identici (0,687 e 1,000), la precision sale da 0,260 a 0,402. Soglia prudente: taglia
# solo le code lontane dal primo, non i candidati vicini.
TRIM_RATIO = float(os.getenv("TRIM_RATIO", "0.90"))
# E15: il testo consegnato per ogni documento selezionato. Il feedback del round 2 mostra che il
# punteggio conta i `document_id` **deduplicati**: un fatto che sta nel documento ma fuori dal chunk
# vincente e' evidenza persa senza alcun risparmio (R2_Q004 aveva la mappa al rank 1 e ha comunque
# perso «22-24»). Sotto questa soglia si consegna il documento intero; sopra, una finestra contigua.
# La mediana dei documenti sta sui 2 000 caratteri, quindi a 4 000 quasi tutto l'archivio viaggia
# intero e si ritagliano solo le scansioni lunghe e rumorose (`garib_*`, fino a 85 000 char).
# Misurato: la latenza per domanda correla con i token di **output** (+0,79) e non con quelli di
# input (+0,03), e il costo ha dodici volte il margine necessario. L'evidenza in ingresso e' quindi
# quasi gratis: la si paga in lunghezza della risposta, non in ampiezza del contesto.
# E19: pseudo-relevance feedback. I documenti trovati al primo giro nominano spesso quelli che
# mancano — il verbale di Lanza cita il «dispaccio» e la «nota di rettifica», cioe' le due fonti
# perse su R2_Q007. Un secondo giro lessicale con i termini piu' distintivi dei primi risultati non
# costa nessuna chiamata: BM25 sta in memoria. Misurato: MRR da 0,758 a 0,808 su ogni combinazione
# provata, senza mai perdere recall o hit. PRF_SEEDS=0 lo spegne, per gli A/B.
PRF_SEEDS = int(os.getenv("PRF_SEEDS", "3"))
PRF_TERMS = int(os.getenv("PRF_TERMS", "80"))
DOC_TEXT_DIR = Path(os.getenv("DOC_TEXT_PATH", "outputs/doc_text"))
DOC_CONTEXT_MAX_CHAR = int(os.getenv("DOC_CONTEXT_MAX_CHAR", "4000"))
# E11: LEXICAL_META=0 indicizza in BM25 il solo testo del chunk, per gli A/B.
LEXICAL_META = os.getenv("LEXICAL_META", "1") == "1"
# Sotto questa soglia di caratteri indicizzati un documento e' muto: e' entrato nell'indice ma non
# puo' rispondere a niente (tipico delle immagini senza testo, es. una mappa senza annotazioni).
MUTE_DOCUMENT_CHARS = 40
# L'ingest e' dominato dal parsing Docling (l'OCR delle scansioni): i file vengono
# processati in parallelo con un worker per thread. Ogni worker tiene le proprie
# pipeline (il DocumentConverter di Docling non e' thread-safe). Le scritture su
# Qdrant restano sul thread main per evitare upsert concorrenti sul client locale.
# INGEST_WORKERS=1 ripristina l'esecuzione sequenziale, utile per gli A/B.
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "4"))

# E5: `reliability` del manifest tradotta in una qualifica leggibile dal generatore. Il modello non
# sa da solo che «articolo_propaganda_01» e' un foglio celebrativo o che una bozza e' stata
# rettificata: senza questa etichetta ripete la propaganda come fatto.
RELIABILITY_LABELS = {
    "official_but_simplified": "fonte ufficiale ma semplificata",
    "didactic": "testo didattico dell'archivio",
    "reference": "scheda di riferimento",
    "authentic_unreviewed": "documento originale non rivisto, OCR rumoroso",
    "partial": "fonte parziale o incompleta",
    "propaganda": "foglio di parte, propaganda",
    "ambiguous": "fonte ambigua",
    "allusive": "fonte allusiva, non esplicita",
    "draft": "bozza superata da una versione successiva",
    "revised": "versione riveduta che corregge una bozza precedente",
    "unverified_hearsay": "copia anonima, voci non verificate",
    "contested": "testimonianza tardiva e contestata",
}


def build_splitter():
    """RecursiveSplitter che rispetta davvero max_char.

    RecursiveSplitter raggruppa le foglie del nodo Docling, ma una foglia piu' grande di max_char
    passa intera (lo dice il suo stesso test: max_char=10 su 21 caratteri -> 1 chunk). In questo
    archivio il corpo di un documento e' spesso una foglia sola, quindi il limite non agiva mai e
    ogni documento finiva in un unico vettore diluito. Qui le eccedenze vengono ritagliate con
    TextSplitter, che e' gia' nella libreria.
    """
    from datapizza.modules.splitters import RecursiveSplitter, TextSplitter

    class SizedSplitter(RecursiveSplitter):
        def split(self, node):
            text_splitter = TextSplitter(max_char=self.max_char, overlap=self.overlap)
            chunks = []
            for chunk in super().split(node):
                if len(chunk.text) <= self.max_char:
                    chunks.append(chunk)
                    continue
                for piece in text_splitter.split(chunk.text):
                    piece.metadata.update(chunk.metadata)
                    chunks.append(piece)
            # Titoli e date isolati diventano chunk a se': corti, spesso duplicati (Docling ripete
            # l'intestazione di sezione) e ottimi da abbinare a una domanda breve. Occupavano fino a
            # 4 slot su 5 dei contesti senza portare evidenza, e il generatore si asteneva.
            seen: set[str] = set()
            kept = []
            for chunk in chunks:
                key = " ".join(chunk.text.split())
                if len(key) < CHUNK_MIN_CHAR or key in seen:
                    continue
                seen.add(key)
                kept.append(chunk)
            return kept

    return SizedSplitter(max_char=CHUNK_MAX_CHAR, overlap=CHUNK_OVERLAP)


def build_parser(ocr: bool):
    """DoclingParser che parsa ogni file una volta sola.

    Docling e' lo stadio lento dell'ingest (OCR): senza cache ogni --rebuild
    riprocessa l'intero archivio e un confronto A/B costa decine di minuti.
    Chiave = sha256(file) + engine OCR, cosi' cambiare engine non riusa un
    parsing prodotto da un altro. Import locale come nel resto del file.
    """
    from datapizza.modules.parsers.docling import DoclingParser
    from datapizza.modules.parsers.docling.ocr_options import OCREngine, OCROptions

    class CachedDoclingParser(DoclingParser):
        def parse_to_json(self, file_path: str) -> dict:
            key = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            cached = PARSE_CACHE / f"{key}-{self.ocr_options.engine.value}.json"
            if cached.is_file():
                print(f"parse cache: {Path(file_path).name}")
                return json.loads(cached.read_text(encoding="utf-8"))
            data = super().parse_to_json(file_path)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data

    engine = OCREngine.EASY_OCR if ocr else OCREngine.NONE
    return CachedDoclingParser(ocr_options=OCROptions(engine=engine))


def _local_qdrant(path: Path):
    """Qdrant embedded su disco.

    datapizza-ai espone `location`/`host`; per path locale inizializziamo il wrapper
    come fa il client sottostante (`QdrantClient(path=...)`).
    """
    from datapizza.vectorstores.qdrant import QdrantVectorstore

    store = QdrantVectorstore.__new__(QdrantVectorstore)
    store.host = None
    store.port = 6333
    store.api_key = None
    store.kwargs = {"path": str(path)}
    store.batch_size = 100
    return store


def build_clients(api_key: str, model: str):
    from datapizza.clients.openai import OpenAIClient
    from datapizza.embedders.openai import OpenAIEmbedder

    embedder = OpenAIEmbedder(api_key=api_key, model_name=EMBEDDING_MODEL)
    llm = OpenAIClient(api_key=api_key, model=model)
    return embedder, llm


def ingest_corpus(
    *,
    files: list[tuple[Path, dict]],
    embedder,
    qdrant_path: Path,
    collection: str,
    rebuild: bool,
):
    from datapizza.core.vectorstore import VectorConfig
    from datapizza.embedders import ChunkEmbedder
    from datapizza.pipeline import IngestionPipeline

    if rebuild and qdrant_path.exists():
        shutil.rmtree(qdrant_path)
    documents_dir = doc_text_dir(collection)
    if rebuild and documents_dir.exists():
        shutil.rmtree(documents_dir)
    qdrant_path.mkdir(parents=True, exist_ok=True)

    vector_store = _local_qdrant(qdrant_path)
    client = vector_store.get_client()
    if client.collection_exists(collection):
        if rebuild:
            vector_store.delete_collection(collection)
        else:
            n_chunk = len(list(vector_store.dump_collection(collection)))
            print(f"Indice esistente: {n_chunk} chunk in '{collection}' ({qdrant_path})")
            return vector_store

    vector_store.create_collection(
        collection_name=collection,
        vector_config=[VectorConfig(dimensions=EMBEDDING_DIM, name=EMB_NAME)],
    )


    def build_ingest_pipeline(ocr: bool):
        return IngestionPipeline(
            modules=[
                build_parser(ocr),
                build_splitter(),
                ChunkEmbedder(client=embedder, embedding_name=EMB_NAME),
            ],
        )

    workers = min(INGEST_WORKERS, len(files), os.cpu_count() or 1)
    local = threading.local()
    started = time.perf_counter()

    def ingest_one(path: Path, document: dict):
        needs_ocr = FORCE_OCR_ALL or document.get("modality", "") not in DIGITAL_MODALITIES
        pipelines = getattr(local, "pipelines", None)
        if pipelines is None:
            pipelines = local.pipelines = {}
        if needs_ocr not in pipelines:
            pipelines[needs_ocr] = build_ingest_pipeline(needs_ocr)
        pipeline = pipelines[needs_ocr]
        chunks = pipeline.run(file_path=str(path))
        # E15: il markdown del parser e' il testo da cui si ritagliano i contesti. La seconda parse
        # e' un colpo di cache (CachedDoclingParser), non un secondo OCR.
        return needs_ocr, chunks, pipeline.components[0].parse(str(path)).content

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(ingest_one, path, document) for path, document in files]
        results = [future.result() for future in futures]

    # Conteggio per documento: un documento solo-immagine puo' entrare nell'indice senza testo
    # utile e sparire in silenzio. La guida chiede di distinguere «il testo non e' stato
    # recuperato» da «recuperato ma interpretato male»: questo separa il primo caso. Con l'ingest
    # parallelo i chunk sono gia' in mano al chiamante: il conteggio non costa piu' una rilettura.
    all_chunks = []
    mute: list[str] = []
    documents_dir.mkdir(parents=True, exist_ok=True)
    for (path, document), (needs_ocr, chunks, content) in zip(files, results, strict=True):
        document_id = document["document_id"]
        (documents_dir / f"{document_id}.md").write_text(content, encoding="utf-8")
        for chunk in chunks:
            chunk.metadata.update({
                "document_id": document_id,
                "source_file": path.name,
                # E5: la qualifica della fonte viaggia col chunk e arriva al prompt.
                "act": document.get("act"),
                "title": document.get("title", ""),
                "reliability": document.get("reliability", "unknown"),
                "qualifica": RELIABILITY_LABELS.get(document.get("reliability", ""), "fonte non classificata"),
            })
        chars = sum(len((getattr(chunk, "text", None) or "").strip()) for chunk in chunks)
        if chars < MUTE_DOCUMENT_CHARS:
            mute.append(document_id)
        all_chunks.extend(chunks)
        print(
            f"ingest: {document_id} <- {path.name} (ocr={'on' if needs_ocr else 'off'})"
            f" -> {len(chunks)} chunk, {chars} caratteri"
        )
    if mute:
        print(f"ATTENZIONE: {len(mute)} documenti sono entrati senza testo utile: {', '.join(mute)}")
    if all_chunks:
        vector_store.add(all_chunks, collection)
    elapsed = time.perf_counter() - started
    n_chunk = len(list(vector_store.dump_collection(collection)))
    print(f"Ingest completato in {elapsed:.1f}s: {n_chunk} chunk in '{collection}' ({workers} worker)")
    return vector_store


# Ogni riga aggiunta dopo il round 2 corrisponde a una motivazione esplicita del giudice: i punti
# di generation persi non erano fonti mancanti, erano fatti presenti nei contesti e non riportati.
GROUNDING = (
    "Rispondi SOLO usando il contesto fornito. Ogni brano inizia con il suo document_id tra "
    "parentesi quadre, es. [cronologia_ufficiale_01], seguito dalla qualifica della fonte. Cita "
    "SEMPRE la fonte con ESATTAMENTE quel document_id.\n"
    # R2_Q003 (correttezza 0,10) e R2_Q004 (0,67): la mappa era al rank 1 e conteneva «22-24»,
    # «deposito Lo Bianco: 12 carri» e i toponimi. La risposta li ha riassunti invece di riportarli.
    "Riporta TESTUALMENTE le date, gli orari, le cifre, le quantita', i nomi di luogo e di persona e "
    "le formule esatte che compaiono nel contesto: non parafrasarli e non riassumerli via. Se il "
    "contesto elenca voci etichettate (A, B, C; righe di un registro), trattale una per una.\n"
    # R2_Q003 e R2_Q004 (ragionamento storico 0,65 e 0,40): il contesto diceva di se' «ANNOTAZIONI
    # NARRATIVE SIMULATE non storiche» e la risposta non l'ha detto.
    "Se un documento dichiara la propria natura o i propri limiti - annotazioni simulate o non "
    "storiche, copia non firmata, testo incompleto o illeggibile, foglio di parte - riportalo "
    "esplicitamente insieme a cio' che ne ricavi.\n"
    "Qualifica la fonte prima di riportarne il contenuto quando la qualifica lo richiede: "
    "propaganda, voci non verificate, testimonianze tardive o contestate, bozze superate. Non "
    "presentare mai come fatto cio' che una fonte di parte afferma: scrivi chi lo afferma.\n"
    # R2_Q009 (correttezza 0,60): la domanda confrontava piu' testi, la risposta ne ha trattato uno.
    "Se la domanda mette a confronto piu' testi, piu' versioni o piu' luoghi, tratta ESPLICITAMENTE "
    "ognuno, anche solo per dire che il contesto non lo copre.\n"
    # R2_Q001, Q006 e Q010 (fedelta' 0,92-0,94): inferenze ragionevoli presentate come lettura.
    "Distingui prova diretta, indizio e congettura, e dichiara cosa le carte non provano. Cio' che "
    "deduci e non leggi va introdotto con «e' un'inferenza:».\n"
    "Se due documenti sono versioni concorrenti dello stesso atto, riportale entrambe con le loro "
    "date: la versione riveduta non cancella la bozza.\n"
    "Riserva la formula esatta 'Non lo so' al caso in cui i brani non parlino affatto "
    "dell'argomento della domanda. Se contengono evidenza anche solo parziale o indiretta - e su "
    "una domanda di confronto o di sintesi e' quasi sempre cosi' - rispondi con quella e "
    "dichiarane i limiti: astenersi quando l'evidenza c'e' vale zero, dire cosa le carte mostrano "
    "e cosa non provano vale pieno.\n"
    # R2_Q008 e' una domanda a evidenza insufficiente: chiudere con «non e' una prova
    # incontrovertibile» lascia intendere che una prova parziale ci sia. La formula dev'essere netta.
    "Quando le carte non bastano a stabilire cio' che la domanda chiede, dillo in modo netto - «le "
    "carte non dimostrano che...», «non ci sono prove che...» - e mai con formule attenuate come "
    "«non e' una prova incontrovertibile», che lasciano intendere una prova parziale.\n"
    # Il tetto tiene le risposte dense, non serve a governare la latenza: misurata su giri ripetuti
    # a configurazione identica oscilla fra 3 345 e 4 630 ms, e la varianza dell'API e' piu' grande
    # di qualunque differenza fra 170 e 220 parole. La fascia dei 4 secondi era gia' una moneta
    # lanciata nel round 2 valutato (3 762 ms). L'ampiezza del contesto in ingresso non la sposta
    # affatto: l'evidenza in ingresso e' quasi gratis. Non tarare questo numero sul cronometro.
    "Massimo 170 parole: denso di fatti, senza preamboli, senza ripetere la domanda."
)


def build_naive_dag(llm):
    from datapizza.modules.prompt import ChatPromptTemplate
    from datapizza.pipeline import DagPipeline

    prompt_template = ChatPromptTemplate(
        user_prompt_template="Domanda: {{ user_prompt }}",
        retrieval_prompt_template=(
            "{% for chunk in chunks %}[{{ chunk.metadata.document_id }}] ({{ chunk.metadata.qualifica }})"
            "\n{{ chunk.text }}\n\n{% endfor %}"
        ),
    )
    dag = DagPipeline()
    dag.add_module("prompt_template", prompt_template)
    dag.add_module("llm", llm)
    dag.connect("prompt_template", "llm", target_key="memory")
    return dag


def dense_retrieve(embedder, vector_store, collection: str, domanda: str, k: int = 5):
    query_vector = embedder.embed(domanda)
    return vector_store.search(
        collection_name=collection,
        query_vector=query_vector,
        k=k,
        vector_name=EMB_NAME,
    )


# E4: nomi, luoghi e date del 1860 sono terreno lessicale. `rank_bm25` sarebbe una dipendenza in
# piu' per una formula di poche righe, quindi BM25 sta qui, in stdlib.
def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text.lower()))


def _lexical_text(chunk: Any) -> str:
    """Testo che il solo BM25 indicizza: contenuto + titolo + qualifica della fonte.

    E11: una domanda come «confrontando i tre testi propagandistici» non ha nessuna parola in
    comune con i fogli che cerca — «propaganda» sta nel manifest, non nel documento. Titolo e
    qualifica entrano quindi nell'indice lessicale. **Il testo consegnato al generatore non
    cambia**: il testo dei contesti resta tracciabile nel corpus.

    E13: anche il `document_id`, che e' spesso l'unico posto in cui la parola della domanda compare
    («agenda» di R2_Q001 sta li' e non nel titolo «Estratto dal taccuino della casa Sant'Elia»).
    Da solo non basta e costa 0,01 di MRR; serve invece al giro di feedback E19, a cui consegna semi
    migliori. Misurato insieme: +0,033 di recall e +0,050 di MRR. Le due cose si tengono o si
    tolgono insieme.
    """
    text = getattr(chunk, "text", "") or ""
    if not LEXICAL_META:
        return text
    metadata = getattr(chunk, "metadata", None)
    return " ".join([
        text,
        _meta_get(metadata, "document_id").replace("_", " "),
        _meta_get(metadata, "title"),
        _meta_get(metadata, "qualifica"),
        _meta_get(metadata, "reliability"),
    ])


class Bm25:
    """BM25 Okapi su tutti i chunk della collection. Nessuna API, nessuna dipendenza nuova."""

    def __init__(self, chunks: list[Any], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [_tokens(_lexical_text(chunk)) for chunk in chunks]
        self.lengths = [len(doc) for doc in self.docs]
        self.avg_length = (sum(self.lengths) / len(self.docs)) if self.docs else 0.0
        self.frequencies = [Counter(doc) for doc in self.docs]
        appearances = Counter(term for doc in self.docs for term in set(doc))
        n = len(self.docs)
        self.idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in appearances.items()
        }

    def search(self, domanda: str, k: int) -> list[Any]:
        query = _tokens(domanda)
        scored = []
        for index, frequencies in enumerate(self.frequencies):
            score = 0.0
            for term in query:
                tf = frequencies.get(term, 0)
                if not tf:
                    continue
                norm = 1 - self.b + self.b * self.lengths[index] / (self.avg_length or 1)
                score += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * norm)
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda row: -row[0])
        return [self.chunks[index] for _, index in scored[:k]]


def fuse_documents(rankings: list[list[Any]], k: int, constant: int = 60) -> list[tuple[str, Any]]:
    """RRF sui chunk, selezione sui **documenti**: un documento sale se compare in alto in
    *entrambe* le liste, ed entra nei contesti una volta sola.

    E14: il punteggio ufficiale conta i `document_id` deduplicati — due chunk dello stesso
    documento occupano due slot su cinque e ne valgono uno. Nel round 2 sono stati otto slot buttati
    su sei domande, proprio dove mancava recall (R2_Q007 e R2_Q008 hanno consegnato cinque contesti
    che valevano tre documenti).

    Dentro una lista si tiene solo il chunk migliore di ciascun documento (il **massimo**, non la
    somma: `garib_d08` ha 113 chunk sui 193 dell'indice e sommando vincerebbe qualunque domanda);
    fra liste diverse i punteggi si sommano, che e' il senso di RRF.

    E2: con TRIM_RATIO > 0 si consegnano meno di k documenti, tagliando quelli il cui punteggio
    scende sotto quella frazione del primo. Cinque contesti sono un massimo, non una quota.
    """
    scores: dict[str, float] = {}
    best: dict[str, tuple[int, Any]] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, chunk in enumerate(ranking, start=1):
            document_id = _meta_get(getattr(chunk, "metadata", None), "document_id")
            if not document_id or document_id in seen:
                continue
            seen.add(document_id)
            scores[document_id] = scores.get(document_id, 0.0) + 1 / (constant + rank)
            if rank < best.get(document_id, (10**9, None))[0]:
                best[document_id] = (rank, chunk)
    ordered = sorted(scores, key=lambda document_id: -scores[document_id])[:k]
    if TRIM_RATIO and ordered:
        floor = scores[ordered[0]] * TRIM_RATIO
        ordered = [document_id for document_id in ordered if scores[document_id] >= floor]
    return [(document_id, best[document_id][1]) for document_id in ordered]


def prf_query(domanda: str, seeds: list[Any], bm25: Bm25) -> str:
    """La domanda allargata coi termini piu' distintivi dei documenti gia' trovati (E19)."""
    seen: set[str] = set()
    terms: list[str] = []
    for chunk in seeds:
        for token in _tokens(getattr(chunk, "text", "") or ""):
            if len(token) > 3 and token not in seen:
                seen.add(token)
                terms.append(token)
    terms.sort(key=lambda token: -bm25.idf.get(token, 0.0))
    return " ".join([domanda, *terms[:PRF_TERMS]])


def retrieve(embedder, vector_store, collection: str, domanda: str, k: int, bm25: Bm25 | None):
    """Recupera largo e consegna stretto: denso (+ BM25, + il giro di feedback) fusi con RRF, poi i
    primi k **documenti**."""
    rankings = [dense_retrieve(embedder, vector_store, collection, domanda, k=FETCH_K)]
    if bm25 is not None:
        rankings.append(bm25.search(domanda, FETCH_K))
        if PRF_SEEDS and PRF_TERMS:
            seeds = [chunk for _, chunk in fuse_documents(rankings, PRF_SEEDS)]
            rankings.append(bm25.search(prf_query(domanda, seeds, bm25), FETCH_K))
    return fuse_documents(rankings, k)


def doc_text_dir(collection: str) -> Path:
    """Una cartella per collection: `--act 1 2` indicizza in `caso_dei_mille_act12` e non deve
    sovrascrivere i testi del corpus completo, che `--rebuild` cancellerebbe."""
    return DOC_TEXT_DIR / collection


@lru_cache(maxsize=None)
def _document_text(directory: Path, document_id: str) -> str:
    path = directory / f"{document_id}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def document_context(document_id: str, chunk: Any, directory: Path) -> Any:
    """Il contesto consegnato per un documento selezionato: il documento intero, oppure una
    finestra contigua centrata sul chunk che l'ha fatto emergere.

    Il testo deve restare **letterale**: un contesto non riconducibile al suo `document_id` azzera
    la Faithfulness della domanda. Ogni chunk e' una sottostringa esatta del markdown del parser
    (verificato su tutto l'archivio), quindi anche le finestre lo sono per costruzione.
    """
    metadata = getattr(chunk, "metadata", {})
    fallback = (getattr(chunk, "text", None) or "").strip()
    content = _document_text(directory, document_id)
    if not content:
        return SimpleNamespace(text=fallback, metadata=metadata)
    if len(content) <= DOC_CONTEXT_MAX_CHAR:
        text = content.strip()
    else:
        start = content.find(fallback)
        centre = (start + len(fallback) // 2) if start >= 0 else 0
        left = max(0, min(centre - DOC_CONTEXT_MAX_CHAR // 2, len(content) - DOC_CONTEXT_MAX_CHAR))
        text = content[left:left + DOC_CONTEXT_MAX_CHAR].strip()
    return SimpleNamespace(text=text or fallback, metadata=metadata)


# Un'astensione secca su una domanda che l'evidenza copriva vale zero su 35. E' successo davvero:
# due valutazioni dello stesso round 2, retrieval identico, e in un giro il modello ha risposto
# «Non lo so.» a R2_Q009 prendendo 0 invece di 28,8 — 3,5 punti sul totale, cinque volte quanto vale
# tutto il lavoro sul ranking. E' un evento raro e casuale, quindi il prompt da solo non basta:
# questa e' la rete. Il secondo giro parte solo su quel ramo, quindi non sposta la latenza media.
ABSTENTION_OPENERS = ("non lo so", "non lo sappiamo", "non e possibile stabilirlo")
RETRY_WITH_EVIDENCE = (
    "\n\nATTENZIONE: la risposta precedente si e' astenuta, ma i brani forniti contengono evidenza "
    "pertinente. Riscrivila usando quell'evidenza: di' che cosa le carte mostrano, con le citazioni "
    "esatte, e che cosa non provano. Non usare la formula 'Non lo so'."
)


def is_bare_abstention(answer: str) -> bool:
    """La risposta si apre con la formula di astensione? (Citare l'insufficienza delle prove nel
    corpo del testo non e' astenersi: si guarda l'inizio, come fa lo scorer.)"""
    stripped = unicodedata.normalize("NFKD", (answer or "").strip().lower())
    stripped = "".join(char for char in stripped if not unicodedata.combining(char))
    return " ".join(stripped.split()).startswith(ABSTENTION_OPENERS)


def naive_rag(dag, domanda: str, chunks: list[Any]):
    """Generazione sui contesti gia' selezionati."""
    return dag.run(
        {
            "prompt_template": {"user_prompt": domanda, "chunks": chunks},
            "llm": {"input": domanda, "system_prompt": GROUNDING},
        }
    )


def hits_to_contexts(hits: list[Any], max_contexts: int = 5) -> list[dict]:
    contexts: list[dict] = []
    for index, hit in enumerate(hits[:max_contexts], start=1):
        document_id = _meta_get(getattr(hit, "metadata", None), "document_id")
        content = (getattr(hit, "text", None) or "").strip()
        if not document_id or not content:
            continue
        contexts.append({"rank": index, "document_id": document_id, "content": content})
    # Re-numera 1..N dopo eventuali skip
    for index, row in enumerate(contexts, start=1):
        row["rank"] = index
    return contexts


def answer_one(
    question: dict,
    *,
    dag,
    embedder,
    vector_store,
    collection: str,
    model: str,
    k: int,
    bm25: Bm25 | None = None,
) -> dict:
    question_text = question["question"]
    started = time.perf_counter()
    selected = retrieve(embedder, vector_store, collection, question_text, k=k, bm25=bm25)
    # I contesti dichiarati sono esattamente quelli passati al generatore, nello stesso ordine.
    hits = [document_context(document_id, chunk, doc_text_dir(collection)) for document_id, chunk in selected]
    llm_out = naive_rag(dag, question_text, hits)["llm"]
    answer_text = getattr(llm_out, "text", None) or str(llm_out)
    calls = [llm_out]
    if hits and is_bare_abstention(answer_text):
        print(f"astensione su {question['question_id']} con {len(hits)} contesti: riprovo")
        retry = naive_rag(dag, question_text + RETRY_WITH_EVIDENCE, hits)["llm"]
        calls.append(retry)
        retry_text = getattr(retry, "text", None) or str(retry)
        if not is_bare_abstention(retry_text):
            answer_text = retry_text
    latency_ms = max(0, round((time.perf_counter() - started) * 1000))

    usage = [_token_usage(call) for call in calls]
    return {
        "question_id": question["question_id"],
        "question": question_text,
        "answer": answer_text,
        "contexts": hits_to_contexts(hits, max_contexts=k),
        "telemetry": {
            "latency_ms": latency_ms,
            "declared_cost_eur": round(sum(declared_cost_eur(*row) for row in usage), 6),
            "model_calls": [
                {
                    "provider": "openai",
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_input_tokens": cached,
                }
                for input_tokens, output_tokens, cached in usage
            ],
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY mancante: copiare .env.example → .env e impostare la chiave.")
    return api_key


def run_validate_only(args: argparse.Namespace) -> int:
    payload = json.loads(args.submission.read_text(encoding="utf-8"))
    questions = json.loads(args.questions.read_text(encoding="utf-8")) if args.questions else None
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
    errors = validate_payload(payload, questions, manifest, args.round_id)
    if errors:
        print("VALIDAZIONE FALLITA")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALIDAZIONE OK - il tentativo ufficiale non e stato consumato")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Baseline naive RAG (Lab_08) → submission.json")
    parser.add_argument("--questions", type=Path, help="JSON domande del round")
    parser.add_argument("--round-id", help="round_id da scrivere nella submission")
    parser.add_argument("--output", type=Path, help="Percorso submission.json in output")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--qdrant-path", type=Path, default=Path(os.getenv("QDRANT_PATH", "outputs/qdrant")))
    parser.add_argument("--collection", default=os.getenv("COLLECTION_NAME", "caso_dei_mille"))
    parser.add_argument(
        "--act",
        type=int,
        nargs="+",
        help="Indicizza e interroga solo gli act indicati (default: tutto il manifest)",
    )
    parser.add_argument("--k", type=int, default=int(os.getenv("MAX_CONTEXTS", "5")))
    parser.add_argument("--rebuild", action="store_true", help="Ricostruisce l'indice Qdrant")
    parser.add_argument("--validate-only", action="store_true", help="Valida una submission già prodotta")
    parser.add_argument("--submission", type=Path, help="Submission da validare (con --validate-only)")
    args = parser.parse_args()

    if not 1 <= args.k <= 5:
        raise SystemExit("--k deve essere tra 1 e 5")

    if args.act:
        args.collection = f"{args.collection}_act{''.join(str(a) for a in sorted(args.act))}"

    if args.validate_only:
        if not args.submission:
            raise SystemExit("--validate-only richiede --submission")
        return run_validate_only(args)

    if not args.questions or not args.round_id or not args.output:
        raise SystemExit("Richiesti --questions, --round-id e --output (oppure --validate-only)")

    api_key = _require_api_key()
    model = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("DATAPIZZA_MODEL")
        or "gpt-4o-mini"
    ).strip()

    project_root = Path.cwd()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    files = iter_ingest_files(manifest, project_root, args.act)
    if not files:
        raise SystemExit("Nessun documento ingeribile dal manifest")

    embedder, llm = build_clients(api_key, model)
    vector_store = ingest_corpus(
        files=files,
        embedder=embedder,
        qdrant_path=args.qdrant_path,
        collection=args.collection,
        rebuild=args.rebuild,
    )
    dag = build_naive_dag(llm)
    bm25 = Bm25(list(vector_store.dump_collection(args.collection))) if HYBRID else None

    answers = [
        answer_one(
            row,
            dag=dag,
            embedder=embedder,
            vector_store=vector_store,
            collection=args.collection,
            model=model,
            k=args.k,
            bm25=bm25,
        )
        for row in questions["questions"]
    ]
    payload = {"schema_version": "1.0", "round_id": args.round_id, "answers": answers}
    errors = validate_payload(payload, questions, manifest, args.round_id)
    if errors:
        raise SystemExit("Submission non valida:\n- " + "\n- ".join(errors))
    submission = Submission.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(submission.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Submission valida: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
