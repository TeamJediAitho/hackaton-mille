import pytest

from score_submission import band_points, is_abstention, score_submission

COST_BANDS = ((0.005, 8), (0.02, 6))


def telemetry(latency_ms=1000, cost=0.001):
    return {
        "latency_ms": latency_ms,
        "declared_cost_eur": cost,
        "model_calls": [
            {"provider": "openai", "model": "gpt-4o-mini", "input_tokens": 1, "output_tokens": 1, "cached_input_tokens": 0}
        ],
    }


def answer(question_id, text, documents):
    return {
        "question_id": question_id,
        "question": "Domanda?",
        "answer": text,
        "contexts": [
            {"rank": rank, "document_id": doc, "content": "evidenza"}
            for rank, doc in enumerate(documents, start=1)
        ],
        "telemetry": telemetry(),
    }


def annotation(question_id, relevant, required_facts=None, requires_abstention=False):
    return {
        "question_id": question_id,
        "question": "Domanda?",
        "relevant_sources": relevant,
        "acceptable_sources": [],
        "requires_abstention": requires_abstention,
        "required_facts": required_facts or [],
    }


def fixture():
    submission = {
        "schema_version": "1.0",
        "round_id": "test",
        "answers": [
            # fonte rilevante al rank 3 -> ranking debole
            answer("Q1", "Risposta con dodici carri", ["d9", "d8", "d1"]),
            # nessuna fonte rilevante recuperata
            answer("Q2", "Risposta", ["d5", "d6"]),
            # astensione attesa e rispettata
            answer("Q3", "Non lo so.", ["d7"]),
            # fonte giusta ma fatto richiesto assente
            answer("Q4", "Risposta senza il numero", ["d4"]),
        ],
    }
    annotations = {
        "round_id": "test",
        "questions": [
            annotation("Q1", ["d1"], [["dodici"]]),
            annotation("Q2", ["d2"]),
            annotation("Q3", [], requires_abstention=True),
            annotation("Q4", ["d4"], [["dodici"]]),
        ],
    }
    return submission, annotations


def test_metrics_match_hand_computed_values():
    result = score_submission(*fixture())
    assert result["n_questions"] == 4
    assert result["n_scored"] == 3  # Q3 non ha fonti rilevanti: fuori da recall e MRR
    assert result["recall@5"] == pytest.approx((1 + 0 + 1) / 3)
    assert result["precision@5"] == pytest.approx((1 / 3 + 0 + 1) / 3)
    assert result["hit@5"] == pytest.approx(2 / 3)
    assert result["mrr"] == pytest.approx((1 / 3 + 0 + 1) / 3)
    assert result["dont_know_rate"] == 1.0
    assert result["undue_abstentions"] == 0


def test_verdicts_separate_retrieval_from_generation():
    verdicts = {row["question_id"]: row["verdict"] for row in score_submission(*fixture())["rows"]}
    assert verdicts == {
        "Q1": "RANK_WEAK",
        "Q2": "RETRIEVAL_FAIL",
        "Q3": "OK",
        "Q4": "GENERATION_FAIL",
    }


def test_abstention_only_when_the_answer_opens_with_the_formula():
    assert is_abstention("Non lo so.")
    # Citare l'insufficienza delle prove non e' astenersi (caso reale: SAMPLE_Q002)
    assert not is_abstention("Sì, il dossier dice che le prove non bastano.")


def test_band_points_follow_the_scoring_thresholds():
    assert band_points(0.001, COST_BANDS) == 8
    assert band_points(0.01, COST_BANDS) == 6
    assert band_points(0.5, COST_BANDS) == 0


def test_qualification_rate_flags_a_propaganda_source_used_as_plain_evidence():
    submission = {
        "schema_version": "1.0",
        "round_id": "test",
        "answers": [
            answer("Q1", "Il popolo era unanime [foglio]", ["foglio"]),
            answer("Q2", "Il foglio, di parte, parla di unanimità [foglio]", ["foglio"]),
            answer("Q3", "Risposta senza fonti dannose", ["d1"]),
        ],
    }
    harmful = {"harmful_if_unqualified": ["foglio"]}
    annotations = {
        "round_id": "test",
        "questions": [
            annotation("Q1", ["foglio"]) | harmful,
            annotation("Q2", ["foglio"]) | harmful,
            annotation("Q3", ["d1"]),
        ],
    }
    result = score_submission(submission, annotations)
    assert result["n_qualifiable"] == 2  # Q3 non tocca fonti da qualificare
    assert result["qualification_rate"] == pytest.approx(0.5)
    verdicts = {row["question_id"]: row["verdict"] for row in result["rows"]}
    assert verdicts["Q1"] == "UNQUALIFIED_SOURCE"
    assert verdicts["Q2"] == "OK"


def test_abstention_has_nothing_to_qualify():
    """Astenersi non afferma nulla: la fonte dannosa nei contesti non va qualificata."""
    submission = {
        "schema_version": "1.0",
        "round_id": "test",
        "answers": [answer("Q1", "Non lo so.", ["foglio"])],
    }
    annotations = {
        "round_id": "test",
        "questions": [annotation("Q1", [], requires_abstention=True) | {"harmful_if_unqualified": ["foglio"]}],
    }
    result = score_submission(submission, annotations)
    assert result["qualification_rate"] is None
    assert result["rows"][0]["verdict"] == "OK"


def test_forbidden_claim_is_a_generation_failure():
    submission = {
        "schema_version": "1.0",
        "round_id": "test",
        "answers": [answer("Q1", "Esiste un accordo formale provato dai documenti.", ["d1"])],
    }
    annotations = {
        "round_id": "test",
        "questions": [annotation("Q1", ["d1"]) | {"forbidden_claims": ["accordo formale provato"]}],
    }
    result = score_submission(submission, annotations)
    assert result["forbidden_claims"] == 1
    assert result["rows"][0]["verdict"] == "GENERATION_FAIL"


def test_a_reasoned_negative_counts_as_declaring_the_absence_of_proof():
    """«Le carte non provano X» vale come astensione; asserire il claim vietato no."""
    submission = {
        "schema_version": "1.0",
        "round_id": "test",
        "answers": [
            answer("Q1", "Le fonti disponibili non provano un accordo formale.", ["d1"]),
            answer("Q2", "Le fonti non provano nulla, ma l'accordo formale e provato.", ["d1"]),
        ],
    }
    forbidden = {"forbidden_claims": ["accordo formale e provato"]}
    annotations = {
        "round_id": "test",
        "questions": [
            annotation("Q1", [], requires_abstention=True),
            annotation("Q2", [], requires_abstention=True) | forbidden,
        ],
    }
    result = score_submission(submission, annotations)
    verdicts = {row["question_id"]: row["verdict"] for row in result["rows"]}
    assert verdicts == {"Q1": "OK", "Q2": "ABSTENTION_MISS"}
    assert result["dont_know_rate"] == 0.0  # nessuna delle due usa la formula esatta
    assert result["insufficiency_rate"] == pytest.approx(0.5)
