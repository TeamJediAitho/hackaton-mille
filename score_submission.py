"""score_submission.py — misura una submission contro le annotazioni. Nessuna chiamata API.

Le metriche seguono la tabella di `regolamento/docs/SCORING_AND_FAIRNESS.md`: recall@5 (20 pt),
precision fino a 5 (10 pt), hit@5 (5 pt), MRR come proxy della qualita' del ranking (5 pt), piu'
latenza (7 pt) e costo (8 pt). La diagnosi per domanda separa gli errori di retrieval da quelli di
generation, come chiede la Fase 1 della guida partecipanti.

Esempio:
  python score_submission.py \\
    --submission outputs/round1/submission_round_1_pre_opt.json \\
    --annotations eval/annotations_round_1.json \\
    --baseline outputs/round1/submission_round_1_pre_opt.json
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

# Il prompt GROUNDING impone la formula esatta "Non lo so": si controlla l'inizio della risposta,
# non una sottostringa qualsiasi, altrimenti una risposta che *cita* l'insufficienza delle prove
# ("il dossier dice che le prove non bastano") verrebbe scambiata per un'astensione.
ABSTENTION_MARKERS = ("non lo so", "non lo sappiamo", "non e possibile stabilirlo")

# Fasce di SCORING_AND_FAIRNESS.md
LATENCY_BANDS = ((4000, 7), (8000, 5), (15000, 3), (25000, 1))
COST_BANDS = ((0.005, 8), (0.02, 6), (0.05, 3), (0.10, 1))


def normalize(text: str) -> str:
    """Minuscole, senza accenti, spazi compattati: l'OCR dell'archivio e' rumoroso."""
    stripped = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(char for char in stripped if not unicodedata.combining(char))
    return " ".join(stripped.split())


def is_abstention(answer: str) -> bool:
    normalized = normalize(answer)
    return normalized.startswith(ABSTENTION_MARKERS)


def missing_facts(answer: str, required_facts: list[list[str]]) -> list[list[str]]:
    """Un fatto e' coperto se almeno una delle sue varianti compare nella risposta."""
    normalized = normalize(answer)
    return [group for group in required_facts if not any(normalize(v) in normalized for v in group)]


def band_points(value: float, bands: tuple[tuple[float, int], ...]) -> int:
    for threshold, points in bands:
        if value <= threshold:
            return points
    return 0


def percentile(values: list[float], share: float) -> float:
    """Percentile nearest-rank: con 8 domande non serve interpolare."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * len(ordered) + 0.5) - 1))
    return ordered[index]


def score_question(answer: dict, annotation: dict, in_scope: set[str] | None = None) -> dict:
    """Metriche e diagnosi di una singola domanda.

    `in_scope`: document_id effettivamente indicizzati. Una domanda le cui fonti rilevanti sono
    tutte fuori scope (es. con --act 1) diventa una domanda di astensione.
    """
    relevant = set(annotation.get("relevant_sources", []))
    acceptable = set(annotation.get("acceptable_sources", []))
    if in_scope is not None:
        relevant &= in_scope
        acceptable &= in_scope
    pertinent = relevant | acceptable
    expects_abstention = annotation.get("requires_abstention", False) or not relevant

    retrieved = [context["document_id"] for context in answer["contexts"]]
    hit_ranks = [rank for rank, doc in enumerate(retrieved, start=1) if doc in relevant]
    abstained = is_abstention(answer["answer"])
    absent = missing_facts(answer["answer"], annotation.get("required_facts", []))

    row = {
        "question_id": annotation["question_id"],
        "expects_abstention": expects_abstention,
        "abstained": abstained,
        "retrieved": retrieved,
        "recall": len(set(retrieved) & relevant) / len(relevant) if relevant else None,
        "precision": (len([d for d in retrieved if d in pertinent]) / len(retrieved)) if retrieved else 0.0,
        "hit": bool(hit_ranks),
        "rr": 1 / hit_ranks[0] if hit_ranks else 0.0,
        "first_rank": hit_ranks[0] if hit_ranks else None,
        "missing_facts": absent,
    }

    if expects_abstention:
        row["verdict"] = "OK" if abstained else "ABSTENTION_MISS"
    elif not hit_ranks:
        row["verdict"] = "RETRIEVAL_FAIL"
    elif abstained or absent:
        row["verdict"] = "GENERATION_FAIL"
    elif hit_ranks[0] > 2:
        row["verdict"] = "RANK_WEAK"
    else:
        row["verdict"] = "OK"
    return row


def score_submission(payload: dict, annotations: dict, in_scope: set[str] | None = None) -> dict:
    by_id = {row["question_id"]: row for row in annotations["questions"]}
    rows = [
        score_question(answer, by_id[answer["question_id"]], in_scope)
        for answer in payload["answers"]
        if answer["question_id"] in by_id
    ]
    scored = [row for row in rows if row["recall"] is not None]
    abstention = [row for row in rows if row["expects_abstention"]]
    latencies = [answer["telemetry"]["latency_ms"] for answer in payload["answers"]]
    costs = [answer["telemetry"]["declared_cost_eur"] for answer in payload["answers"]]

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "rows": rows,
        "n_questions": len(rows),
        "n_scored": len(scored),
        "recall@5": mean([row["recall"] for row in scored]),
        "precision@5": mean([row["precision"] for row in scored]),
        "hit@5": mean([float(row["hit"]) for row in scored]),
        "mrr": mean([row["rr"] for row in scored]),
        "dont_know_rate": mean([float(row["abstained"]) for row in abstention]) if abstention else None,
        "undue_abstentions": sum(1 for row in scored if row["abstained"]),
        "latency_mean_ms": mean(latencies),
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_max_ms": max(latencies) if latencies else 0,
        "cost_mean_eur": mean(costs),
    }


METRICS = ("recall@5", "precision@5", "hit@5", "mrr")


def report(result: dict, baseline: dict | None = None) -> None:
    print(f"Domande valutate: {result['n_questions']} ({result['n_scored']} con fonti rilevanti in scope)\n")
    print("RETRIEVAL")
    for key in METRICS:
        delta = f"   (prima {baseline[key]:.3f}, {result[key] - baseline[key]:+.3f})" if baseline else ""
        print(f"  {key:<12} {result[key]:.3f}{delta}")

    print("\nASTENSIONE")
    rate = result["dont_know_rate"]
    print(f"  dont_know_rate        {'n/d' if rate is None else f'{rate:.3f}'}")
    print(f"  astensioni indebite   {result['undue_abstentions']}")

    print("\nSISTEMA")
    latency_pts = band_points(result["latency_mean_ms"], LATENCY_BANDS)
    cost_pts = band_points(result["cost_mean_eur"], COST_BANDS)
    print(f"  latenza media         {result['latency_mean_ms']:.0f} ms  -> {latency_pts}/7")
    print(f"  latenza p95 / max     {result['latency_p95_ms']:.0f} / {result['latency_max_ms']:.0f} ms")
    print(f"  costo medio           EUR {result['cost_mean_eur']:.6f}  -> {cost_pts}/8")

    print("\nPER DOMANDA")
    print(f"  {'id':<8} {'esito':<16} {'rec':>5} {'prec':>5} {'rank':>5}  note")
    previous = {row["question_id"]: row["verdict"] for row in baseline["rows"]} if baseline else {}
    for row in result["rows"]:
        recall = "  n/d" if row["recall"] is None else f"{row['recall']:5.2f}"
        rank = "    -" if row["first_rank"] is None else f"{row['first_rank']:5d}"
        notes = []
        if row["first_rank"] and row["first_rank"] > 2:
            notes.append("prima fonte rilevante sotto il rank 2")
        if row["missing_facts"]:
            notes.append("fatti mancanti: " + "; ".join("|".join(g) for g in row["missing_facts"]))
        if row["expects_abstention"]:
            notes.append("astensione attesa: " + ("sì" if row["abstained"] else "NO"))
        was = previous.get(row["question_id"])
        if was and was != row["verdict"]:
            notes.append(f"era {was}")
        print(f"  {row['question_id']:<8} {row['verdict']:<16} {recall} {row['precision']:5.2f} {rank}  {' / '.join(notes)}")


def in_scope_documents(manifest_path: Path | None, acts: list[int] | None) -> set[str] | None:
    if not manifest_path or not acts:
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {row["document_id"] for row in manifest["documents"] if row.get("act") in acts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Misura una submission contro le annotazioni")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, help="Submission precedente, per il confronto prima/dopo")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--act", type=int, nargs="+", help="Limita le fonti attese agli act indicati")
    args = parser.parse_args()

    annotations = json.loads(args.annotations.read_text(encoding="utf-8"))
    scope = in_scope_documents(args.manifest, args.act)
    result = score_submission(json.loads(args.submission.read_text(encoding="utf-8")), annotations, scope)
    baseline = None
    if args.baseline:
        baseline = score_submission(json.loads(args.baseline.read_text(encoding="utf-8")), annotations, scope)
        print(f"Confronto con {args.baseline}\n")
    report(result, baseline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
