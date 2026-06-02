"""Offline tests for the simple grounding pillar + truth gate.

No network. Default support_fn is deterministic token overlap; the
internal_consistency test mocks the heavy judge so nothing calls out.
"""

from __future__ import annotations

from src.scoring.simple_score import grounding_score, gate_and_rank


# Two real sandbox-ish URLs the agent "fetched".
URL_A = "http://localhost:7770/product/sony-wh1000xm5"
URL_B = "http://localhost:8090/A/Microplastics"

GOLDEN = {
    "must_cite_urls": [
        {"url": URL_A},
        {"url": URL_B},
    ]
}

SNIPPETS = {
    URL_A: "The Sony WH-1000XM5 headphones offer industry leading active noise cancellation.",
    URL_B: "Microplastics are small plastic particles found in oceans and drinking water.",
}


def test_precision_drops_when_unsupported_citations_added():
    """Anti-volume: same supported set + extra junk citations -> lower precision."""
    supported = [
        (URL_A, "Sony WH-1000XM5 headphones active noise cancellation industry leading"),
        (URL_B, "Microplastics plastic particles oceans drinking water"),
    ]
    base = grounding_score(supported, SNIPPETS, GOLDEN)
    assert base["precision"] == 1.0
    assert base["n_supported"] == 2

    # Add junk citations: urls never fetched (no snippet) -> unsupported.
    with_junk = supported + [
        ("http://evil.example/spam1", "totally unrelated padding claim about nothing"),
        ("http://evil.example/spam2", "more irrelevant filler citation volume gaming"),
    ]
    junked = grounding_score(with_junk, SNIPPETS, GOLDEN)

    assert junked["n_supported"] == 2  # same supported set
    assert junked["n_cited"] == 4
    assert junked["precision"] < base["precision"]
    assert junked["precision"] == 0.5


def test_recall_reflects_must_cite_hits_only():
    """Adding non-golden citations does NOT raise recall."""
    one_hit = [(URL_A, "Sony WH-1000XM5 headphones active noise cancellation")]
    r1 = grounding_score(one_hit, SNIPPETS, GOLDEN)
    assert r1["must_cite_recall"] == 0.5  # 1 of 2 golden must-cite

    # Add a bunch of non-golden citations -> recall must stay 0.5.
    padded = one_hit + [
        ("http://localhost:7770/product/random-thing", "random padding"),
        ("http://localhost:9999/f/somesub", "more padding to inflate"),
    ]
    r2 = grounding_score(padded, SNIPPETS, GOLDEN)
    assert r2["must_cite_recall"] == 0.5
    assert r2["recall"] == r1["recall"]


def test_f1_zero_when_recall_zero():
    """f1 = 0 when recall = 0 even if precision is high."""
    # Cite a fetched+supported url that is NOT in the golden must-cite set.
    non_golden_url = "http://localhost:7770/product/some-other-item"
    snippets = {non_golden_url: "This product has great battery life and sound quality."}
    pairs = [(non_golden_url, "great battery life sound quality product")]
    res = grounding_score(pairs, snippets, GOLDEN)
    assert res["precision"] > 0.0   # supported
    assert res["recall"] == 0.0     # no golden hit
    assert res["f1"] == 0.0


def test_gate_and_rank():
    """Gate returns 0 on fabrication or below-floor grounding; else passes quality."""
    # Normal pass-through.
    assert gate_and_rank(0.8, 0.65, floor=0.15) == 0.65
    # Fabricated citation -> hard 0.
    assert gate_and_rank(0.9, 0.65, floor=0.15, fabricated=True) == 0.0
    # Grounding below floor -> 0.
    assert gate_and_rank(0.1, 0.65, floor=0.15) == 0.0
    # Exactly at floor passes.
    assert gate_and_rank(0.15, 0.42, floor=0.15) == 0.42


def test_grounding_accepts_bare_urls_with_report_text():
    """Bare-url list + report_text path recovers claim context via extractor."""
    report = (
        "The Sony WH-1000XM5 headphones offer industry leading active noise "
        f"cancellation according to the listing. Source: {URL_A}\n\n"
        f"Microplastics are found in drinking water. Source: {URL_B}\n"
    )
    res = grounding_score([URL_A, URL_B], SNIPPETS, GOLDEN, report_text=report)
    assert res["n_cited"] == 2
    assert res["must_cite_recall"] == 1.0
    assert res["n_supported"] >= 1


def test_internal_consistency_not_applicable_on_untestable_input(monkeypatch):
    """internal_consistency returns applicable=False (NOT score 1.0) when the
    report has no testable entity clusters."""
    import src.verifiers.internal_consistency_verifier as ic

    # Mock the heavy judge so nothing hits the network even if it were reached.
    monkeypatch.setattr(ic, "call_judge_heavy", lambda *a, **k: ("VERDICT: NEUTRAL", None))

    v = ic.InternalConsistencyVerifier()
    # Long enough to pass degeneracy + sentence-count gates, but built from
    # lowercase prose with no extractable capitalised entity clusters.
    sentence = (
        "this is a perfectly coherent statement about everyday matters that "
        "carries no named capitalised entities at all whatsoever here today. "
    )
    answer = sentence * 8  # many sentences, zero entity clusters
    res = v.verify(task_config={}, answer=answer, page=None)

    assert res.details.get("applicable") is False
    assert res.score is None
    assert res.passed is False
