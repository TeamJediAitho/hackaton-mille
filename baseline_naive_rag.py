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
from pathlib import Path
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
# E4: quanti candidati chiedere a ciascun retriever prima della fusione RRF.
FETCH_K = int(os.getenv("FETCH_K", "15"))
# HYBRID=0 torna al solo denso, per gli A/B senza toccare il codice.
HYBRID = os.getenv("HYBRID", "1") == "1"
# E2: 0 = consegna sempre k contesti; >0 = taglia sotto questa frazione del punteggio fuso migliore.
TRIM_RATIO = float(os.getenv("TRIM_RATIO", "0"))
# E10: quanti chunk al massimo puo' occupare uno stesso documento nei contesti finali.
# 0 = nessun limite. Le domande cross-document hanno cinque slot per due o tre fonti: un
# documento lungo e rumoroso (garib_d05, garib_d08) puo' prenderseli quasi tutti. Default 1:
# nove domande su dieci del gold ufficiale vogliono da due a cinque documenti DISTINTI nei
# cinque slot, e R2_Q010 ne vuole cinque.
MAX_PER_DOC = int(os.getenv("MAX_PER_DOC", "1"))
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
# E7: una mappa o un manifesto restituiscono all'OCR un elenco di parole nell'ordine in cui
# stanno sull'immagine, con le etichette coperte dai riquadri. Un modello con visione le rilegge
# in chiaro. La didascalia entra ACCANTO al testo OCR, mai al posto suo: la guida vieta di
# sostituire l'originale con una ricostruzione piu' leggibile. CAPTION_IMAGES=0 la spegne.
CAPTION_IMAGES = os.getenv("CAPTION_IMAGES", "1") == "1"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

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


def caption_image(path: Path, model: str, api_key: str) -> str:
    """Trascrizione del testo visibile in un'immagine, in cache come il parsing.

    Una chiamata per immagine in ingest, zero per domanda. La cache vive accanto a quella di
    Docling e usa la stessa chiave sha256, cosi' un file immutato non si ripaga mai due volte.
    """
    key = hashlib.sha256(path.read_bytes()).hexdigest()
    cached = PARSE_CACHE / f"{key}-caption-{model}.txt"
    if cached.is_file():
        print(f"caption cache: {path.name}")
        return cached.read_text(encoding="utf-8")
    import base64
    from openai import OpenAI

    payload = base64.b64encode(path.read_bytes()).decode()
    response = OpenAI(api_key=api_key).chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": (
                "Trascrivi TUTTO il testo visibile in questa immagine: titolo, toponimi, etichette, "
                "legenda, annotazioni, numeri. Riporta le parole come sono scritte, senza "
                "interpretarle e senza aggiungere nulla che non sia scritto. Elenco secco."
            )},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{payload}"}},
        ]}],
    )
    text = (response.choices[0].message.content or "").strip()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


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
    caption_model: str = "",
    caption_key: str = "",
):
    from datapizza.core.vectorstore import VectorConfig
    from datapizza.embedders import ChunkEmbedder
    from datapizza.pipeline import IngestionPipeline

    if rebuild and qdrant_path.exists():
        shutil.rmtree(qdrant_path)
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
        chunks = list(pipelines[needs_ocr].run(file_path=str(path)))
        # E7: la didascalia si AGGIUNGE al testo OCR, non lo sostituisce - l'OCR resta nel
        # contesto parola per parola, tracciabile. Sta nello STESSO chunk perche' MAX_PER_DOC=1
        # da' un solo slot per documento: due chunk se lo ruberebbero a vicenda. Il file di
        # appoggio riusa splitter ed embedder, senza costruire tipi a mano.
        if CAPTION_IMAGES and caption_model and path.suffix.lower() in IMAGE_SUFFIXES:
            text = caption_image(path, caption_model, caption_key)
            if text:
                ocr_text = "\n".join((getattr(c, "text", "") or "") for c in chunks).strip()
                side = PARSE_CACHE / f"caption-{document['document_id']}.md"
                side.parent.mkdir(parents=True, exist_ok=True)
                side.write_text(
                    f"{ocr_text}\n\nTrascrizione automatica dell'immagine:\n{text}",
                    encoding="utf-8",
                )
                if False not in pipelines:
                    pipelines[False] = build_ingest_pipeline(False)
                chunks = list(pipelines[False].run(file_path=str(side)))
        return needs_ocr, chunks

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(ingest_one, path, document) for path, document in files]
        results = [future.result() for future in futures]

    # Conteggio per documento: un documento solo-immagine puo' entrare nell'indice senza testo
    # utile e sparire in silenzio. La guida chiede di distinguere «il testo non e' stato
    # recuperato» da «recuperato ma interpretato male»: questo separa il primo caso. Con l'ingest
    # parallelo i chunk sono gia' in mano al chiamante: il conteggio non costa piu' una rilettura.
    all_chunks = []
    mute: list[str] = []
    for (path, document), (needs_ocr, chunks) in zip(files, results, strict=True):
        document_id = document["document_id"]
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


GROUNDING = (
    "Rispondi SOLO usando il contesto fornito. Ogni brano inizia con il suo document_id tra "
    "parentesi quadre, es. [cronologia_ufficiale_01], seguito dalla qualifica della fonte. Cita "
    "SEMPRE la fonte con ESATTAMENTE quel document_id.\n"
    "Qualifica la fonte prima di riportarne il contenuto quando la qualifica lo richiede: "
    "propaganda, voci non verificate, testimonianze tardive o contestate, bozze superate. Non "
    "presentare mai come fatto cio' che una fonte di parte afferma: scrivi chi lo afferma.\n"
    "Distingui prova diretta, indizio e congettura, e dichiara cosa le carte non provano.\n"
    # E12: il gold cerca stringhe nella risposta. Un riassunto corretto ma generico perde i
    # fatti: date, quantita' e toponimi vanno riportati come stanno scritti, non parafrasati.
    "Riporta i particolari cosi' come compaiono nei brani: date, quantita', nomi di luogo e "
    "di persona, numeri di registro, orari. Quando un documento adotta o cancella una formula, "
    "citala fra virgolette con le parole esatte del documento.\n"
    # E12: le domande di sintesi e di evidenza insufficiente si vincono sulla frase di chiusura.
    "Chiudi sempre con una frase che dice fin dove arrivano le carte, nella forma 'l'archivio "
    "non prova ...', 'non esiste prova di ...', 'resta una voce, non una garanzia', 'non "
    "permette di misurare ...'. Vale anche quando la risposta e' affermativa: dichiara il "
    "limite.\n"
    # E13: il gold cerca stringhe. Il modello parafrasava le conclusioni («non risulta un
    # accordo») mentre il documento le esprime con parole proprie («non e' stata rinvenuta
    # prova»): stesso senso, fatto perso. Qui gli si chiede di riusare quel lessico.
    "Quando concludi, riusa le PAROLE ESATTE con cui i documenti esprimono quella stessa "
    "conclusione invece di sinonimi: se un atto dice 'non e' stata rinvenuta prova', 'rettifica', "
    "'smentisce', 'nessun ordine scritto', 'nessuna firma', 'autorizzazione verbale', usa quelle "
    "parole. Nomina esplicitamente cio' che manca agli atti, con le parole degli atti.\n"
    "Se due documenti sono versioni concorrenti dello stesso atto, riportale entrambe con le loro "
    "date: la versione riveduta non cancella la bozza.\n"
    "Se il contesto non contiene la risposta, di' esattamente: 'Non lo so'. Se contiene evidenza "
    "anche solo parziale, rispondi con quella e dichiarane i limiti invece di astenerti."
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
    cambia**: i contesti restano il `chunk.text` originale, tracciabile nel corpus.
    """
    text = getattr(chunk, "text", "") or ""
    if not LEXICAL_META:
        return text
    metadata = getattr(chunk, "metadata", None)
    return " ".join([
        text,
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


def reciprocal_rank_fusion(rankings: list[list[Any]], k: int, constant: int = 60) -> list[Any]:
    """RRF: un documento sale se compare in alto in *entrambe* le liste.

    E2: con TRIM_RATIO > 0 si consegnano meno di k contesti, tagliando quelli il cui punteggio
    fuso scende sotto quella frazione del primo. Cinque contesti sono un massimo, non una quota.
    """
    scores: dict[tuple[str, str], float] = {}
    chunks: dict[tuple[str, str], Any] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            key = (_meta_get(getattr(chunk, "metadata", None), "document_id"), getattr(chunk, "text", ""))
            scores[key] = scores.get(key, 0.0) + 1 / (constant + rank)
            chunks.setdefault(key, chunk)
    ordered = sorted(scores, key=lambda key: -scores[key])
    if MAX_PER_DOC:
        seen: dict[str, int] = {}
        capped = []
        for key in ordered:
            document_id = key[0]
            if seen.get(document_id, 0) >= MAX_PER_DOC:
                continue
            seen[document_id] = seen.get(document_id, 0) + 1
            capped.append(key)
        ordered = capped
    ordered = ordered[:k]
    if TRIM_RATIO and ordered:
        floor = scores[ordered[0]] * TRIM_RATIO
        ordered = [key for key in ordered if scores[key] >= floor]
    return [chunks[key] for key in ordered]


def retrieve(embedder, vector_store, collection: str, domanda: str, k: int, bm25: Bm25 | None):
    """Recupera largo e consegna stretto: denso + BM25 fusi con RRF, poi i primi k."""
    if bm25 is None:
        return dense_retrieve(embedder, vector_store, collection, domanda, k=k)
    dense = dense_retrieve(embedder, vector_store, collection, domanda, k=FETCH_K)
    return reciprocal_rank_fusion([dense, bm25.search(domanda, FETCH_K)], k)


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
    hits = retrieve(embedder, vector_store, collection, question_text, k=k, bm25=bm25)
    result = naive_rag(dag, question_text, hits)
    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    llm_out = result["llm"]
    answer_text = getattr(llm_out, "text", None) or str(llm_out)
    input_tokens, output_tokens, cached = _token_usage(llm_out)
    return {
        "question_id": question["question_id"],
        "question": question_text,
        "answer": answer_text,
        "contexts": hits_to_contexts(hits, max_contexts=k),
        "telemetry": {
            "latency_ms": latency_ms,
            "declared_cost_eur": declared_cost_eur(input_tokens, output_tokens, cached),
            "model_calls": [
                {
                    "provider": "openai",
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_input_tokens": cached,
                }
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
        caption_model=model,
        caption_key=api_key,
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
