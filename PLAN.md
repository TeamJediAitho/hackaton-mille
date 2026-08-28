# Piano — Il caso dei Mille

## Dove siamo (28 ago)

- Setup completo: venv 3.13, dipendenze, `pytest` 8/8.
- `make sample` eseguito → `outputs/submission_sample.json` prodotto e **validato** (`VALIDAZIONE OK`).
- La baseline funziona: entrambe le domande di prova hanno risposta e fonte corrette.
- **Prossimo:** migliorare retrieval e generation (Act 1).

## Come funziona la pipeline

```
Domanda
  → 1. RETRIEVAL: la domanda diventa un vettore, Qdrant restituisce i chunk più simili (= i "contesti")
  → 2. GENERATION: i contesti vanno in un prompt, gpt-4o-mini risponde usando SOLO quelli
  → risposta + contesti + telemetria (latenza, costo)
```

Due tipi di errore, si correggono in modo diverso:
- **Retrieval** — la carta giusta non è tra i contesti. Nessun prompt la recupera.
- **Generation** — la carta c'è, ma il modello risponde male o inventa dettagli non presenti.

L'indice si costruisce una volta (`--rebuild`). Le fasi 1-2 girano a ogni domanda.

## Punteggio — cosa conta davvero

| Voce | Punti | Stato |
|---|---:|---|
| Retrieval (Recall@5, Precision, Hit@5, Ranking) | 40 | **da migliorare** |
| Faithfulness (risposta aderente ai contesti) | 18 | attenzione: 1 contesto non aderente → 0 a quella domanda |
| Answer Correctness | 12 | ok sul sample |
| Historical Reasoning | 5 | da curare (propaganda, versioni) |
| Latenza | 7 | ✅ 2,5s → massimo |
| Costo | 8 | ✅ €0,0002 → massimo, **non toccare** |
| Historical Review (speech) | 10 | fine giornata |

Regola: ogni chiamata LLM in più costa **latenza**, non soldi. Reranker/query-rewrite si valutano così.

## I passi

| # | Cosa | File | Fatto? |
|---|---|---|---|
| 0 | Setup + `make sample` | — | ✅ |
| 1 | **Scorer retrieval locale**: misura Recall@5 / Precision / Hit@5 confrontando i `document_id` dei contesti con `eval/sample_annotations.json` | nuovo `eval/score_retrieval.py` | — |
| 2 | **Dedup contesti per documento**: oggi fino a 3 contesti su 5 sono lo stesso documento → slot sprecati. Recuperare più chunk, tenere il migliore per documento, tagliare a 5 | `baseline_naive_rag.py` (`hits_to_contexts`) | — |
| 3 | **Abstention argomentata**: il prompt dice di rispondere "Non lo so" secco → butta Correctness e Reasoning. Sostituire con un'astensione che nomina il buco di evidenza | `baseline_naive_rag.py` (`GROUNDING`) | — |
| 4 | **Ciclo esperimenti**: 1 modifica alla volta, giro scorer + sample, prima/dopo in `TEAM_NOTES.md`, tengo o scarto | — | — |
| 5 | **Submission round ufficiale** quando arrivano le domande dalla dashboard | `outputs/submission_round_N.json` | — |
| 6 | **Act 2**: 9 documenti nuovi (scansioni, mappe, 2 giornali di propaganda, lettere ambigue). OCR con Tesseract, propaganda da qualificare | — | — |
| 7 | **Gold Run** (one-shot, no feedback) + **speech 10 min** | `outputs/submission_gold.json` | — |

I passi 1-3 non richiedono `--rebuild` (l'indice non cambia). Ciclo di test veloce.

## Problema aperto: ingest lento (~55 min)

Docling fa OCR anche sui PDF di testo puliti e li degrada (`"1 rapporti"` invece di `"I rapporti"`). Le scansioni `garib_*` sono il collo di bottiglia.
Già discusso dal team (`TEAM_NOTES.md` problema 1): fare OCR **solo** sui file scansionati, parallelizzare il parsing, valutare Tesseract, impostare la lingua.
→ Lo affrontiamo come esperimento di ingest, prima dell'Act 2.

## Regole del repo (da AGENTS.md / CLAUDE.md)

- Ogni modifica su un branch `feature/<nome>`, **mai su `main`**.
- Push del branch → **PR via `gh` verso `main`**, con descrizione + testing checklist. **Niente self-merge.**
- **Un esperimento alla volta**, risultato in `TEAM_NOTES.md`.
- venv 3.13 + `requirements.txt`. Comandi con `./.venv/Scripts/python.exe ...` (non `make`: prende l'interprete sbagliato).
- `.env` mai committato. `outputs/` non versionato (tranne `submission_gold.json` alla consegna).

## Divisione team (dalla guida)

Retrieval · Generation · Evaluation · Diario. Assegnare una persona per ruolo.
