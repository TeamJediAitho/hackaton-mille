from baseline_naive_rag import MIN_CONTEXTS, merge_contexts


def hit(document_id, text, score):
    return {"document_id": document_id, "text": text, "score": score}


def test_dedup_one_context_per_document():
    hits = [hit("a", "a1", 0.60), hit("a", "a2", 0.59), hit("b", "b1", 0.58)]
    ctx = merge_contexts(hits, max_docs=5, margin=0.10)
    assert [c["document_id"] for c in ctx] == ["a", "b"]
    assert ctx[0]["content"] == "a1\n\na2"  # chunk dello stesso doc accorpati
    assert [c["rank"] for c in ctx] == [1, 2]


def test_score_margin_trims_far_documents():
    hits = [hit("a", "x", 0.60), hit("b", "x", 0.58), hit("c", "x", 0.30)]
    ctx = merge_contexts(hits, max_docs=5, margin=0.05)
    assert [c["document_id"] for c in ctx] == ["a", "b"]  # c scartato: 0.30 << 0.60


def test_floor_keeps_minimum_even_with_one_clear_winner():
    hits = [hit("a", "x", 0.90), hit("b", "x", 0.10), hit("c", "x", 0.05)]
    ctx = merge_contexts(hits, max_docs=5, margin=0.02)
    assert len(ctx) == MIN_CONTEXTS


def test_cap_at_max_docs():
    hits = [hit(str(i), "x", 0.50) for i in range(8)]
    ctx = merge_contexts(hits, max_docs=5, margin=0.10)
    assert len(ctx) == 5
    assert [c["rank"] for c in ctx] == [1, 2, 3, 4, 5]
