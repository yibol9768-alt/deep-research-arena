"""Offline tests for the closed-world CompletenessVerifier.

No sandbox / DB needed: the relevant_set is passed inline on the task_config, so
these run anywhere. They prove:
  (a) exact completeness against the complete DB-derived relevant_set;
  (b) an entity counts only when referenced AND stated with a DB-true fact;
  (c) a hallucinated entity cannot inflate the score (denominator is fixed);
  (d) importance weighting works;
  (e) a cited sandbox URL counts as a reference.
"""

from __future__ import annotations

from src.verifiers.completeness_verifier import CompletenessVerifier


def _task(relevant, **extra):
    cfg = {"completeness": {"relevant_set": relevant, **extra}}
    return cfg


RS = [
    {"url": "http://localhost:7770/akg-k72.html", "name": "AKG K72", "weight": 1.0,
     "facts": {"price": "53.99", "rating": "4.15"}},
    {"url": "http://localhost:7770/sony-wh1000.html", "name": "Sony WH-1000", "weight": 1.0,
     "facts": {"price": "278.00"}},
    {"url": "http://localhost:7770/bose-qc.html", "name": "Bose QC", "weight": 0.5,
     "facts": {"price": "199.00"}},
]


def test_full_completeness():
    report = (
        "The AKG K72 is a great pick at $53.99 with a 4.15 rating. "
        "The Sony WH-1000 sells for $278.00. The Bose QC is $199.00."
    )
    r = CompletenessVerifier().verify(task_config=_task(RS), answer=report)
    assert r.score == 1.0
    assert r.details["surfaced_count"] == 3


def test_partial_completeness_weighted_vs_unweighted():
    # Surfaces AKG (w1) and Bose (w0.5) but not Sony (w1).
    report = "The AKG K72 at $53.99 is solid. The Bose QC is $199.00 and comfy."
    r = CompletenessVerifier().verify(task_config=_task(RS), answer=report)
    # weighted: (1.0 + 0.5) / 2.5 = 0.6
    assert abs(r.score - 0.6) < 1e-6
    # unweighted: 2 / 3
    assert abs(r.details["completeness_unweighted"] - (2 / 3)) < 1e-4


def test_named_without_true_fact_is_not_credited():
    # AKG named but with a WRONG/invented price -> not grounded -> not surfaced.
    report = "The AKG K72 is amazing and costs $999.99."
    r = CompletenessVerifier().verify(task_config=_task(RS), answer=report)
    assert r.details["surfaced_count"] == 0
    assert r.score == 0.0


def test_hallucinated_entity_cannot_inflate():
    # Report covers 1 real entity fully + raves about a product not in the set.
    report = (
        "The AKG K72 at $53.99 (4.15 stars) is the best. "
        "Also the FAKE BrandX Phantom 9000 at $42.00 is incredible."
    )
    r = CompletenessVerifier().verify(task_config=_task(RS), answer=report)
    # Denominator stays 3 (the relevant_set); the hallucinated product is ignored.
    assert r.details["relevant_total"] == 3
    assert r.details["surfaced_count"] == 1
    # weighted 1.0 / 2.5 = 0.4
    assert abs(r.score - 0.4) < 1e-6


def test_cited_url_counts_as_reference():
    # Reference Sony purely by its cited sandbox URL (+ its true price).
    report = "See [this](http://localhost:7770/sony-wh1000.html) at $278.00."
    r = CompletenessVerifier().verify(task_config=_task(RS), answer=report)
    assert r.details["surfaced_count"] == 1


def test_no_relevant_set_fails_cleanly():
    r = CompletenessVerifier().verify(task_config={}, answer="anything")
    assert r.passed is False
    assert "relevant_set" in r.details.get("reason", "")
