"""Offline tests for the GroundingVerifier orchestrator (section 7).

No sandbox: page text is mocked (build_claim_evidence is pure; the verifier takes
an injected fetch_fn). Proves the orchestration wires the pieces correctly:
reachability from the fetch result, ALCE load-bearing flags, NeedCite for uncited
factual sentences, and the end-to-end ReachRate gate.
"""

from __future__ import annotations

from src.verifiers.grounding_verifier import (
    build_claim_evidence,
    default_needs_citation,
    GroundingVerifier,
)


REPORT = (
    "The AKG K72 costs 53.99 according to [the listing](http://localhost:7770/akg.html).\n"
    "The Sony WH-1000 is priced at 278.00 [source](http://localhost:7770/sony-ghost.html).\n"
    "Overall these headphones are a nice choice for everyone."
)

PAGES_OK = {
    "http://localhost:7770/akg.html":
        "AKG K72 closed-back studio headphones. The listing shows it costs 53.99 dollars.",
    "http://localhost:7770/sony-ghost.html": None,  # unreachable / fabricated
}


def test_build_claim_evidence_honest_and_dead():
    claims = build_claim_evidence(REPORT, PAGES_OK)
    # Two factual (numeric) sentences are required claims; the AKG one is cited and
    # reachable, the Sony one cites a dead URL. The "nice choice" sentence is not
    # a required claim (no number).
    required = [c for c in claims if c.needs_citation]
    assert len(required) == 2

    akg = next(c for c in required if any(f.reachable for f in c.cites))
    assert akg.supp == 1.0
    assert akg.cites[0].reachable is True
    assert akg.cites[0].load_bearing is True

    sony = next(c for c in required if c.cites and not c.cites[0].reachable)
    assert sony.supp == 0.0
    assert sony.cites[0].reachable is False


def test_dead_url_drags_grounding_via_reach_gate():
    v = GroundingVerifier(gamma=1.0, k_star=2, fetch_fn=lambda urls: PAGES_OK)
    r = v.verify(task_config={}, answer=REPORT)
    # ReachRate = 1 reachable / 2 cited = 0.5
    assert r.details["reach_rate"] == 0.5
    # supported mass = 1.0 (AKG only)
    assert abs(r.details["supported_mass"] - 1.0) < 1e-6
    assert r.score < 1.0

    # An all-reachable version of the same two claims scores strictly higher.
    pages_all = {
        "http://localhost:7770/akg.html": PAGES_OK["http://localhost:7770/akg.html"],
        "http://localhost:7770/sony-ghost.html":
            "Sony WH-1000 wireless headphones, priced at 278.00.",
    }
    v2 = GroundingVerifier(gamma=1.0, k_star=2, fetch_fn=lambda urls: pages_all)
    r2 = v2.verify(task_config={}, answer=REPORT)
    assert r2.details["reach_rate"] == 1.0
    assert r2.score > r.score


def test_stuffing_cites_are_not_load_bearing():
    report = "The AKG K72 costs 53.99 [a](http://localhost:7770/akg.html)[b](http://localhost:7770/pad.html)."
    pages = {
        "http://localhost:7770/akg.html": "AKG K72 headphones costs 53.99 listing.",
        "http://localhost:7770/pad.html": "Totally unrelated bonsai gardening content.",
    }
    claims = build_claim_evidence(report, pages)
    req = [c for c in claims if c.needs_citation][0]
    by_url = {f.url: f for f in req.cites}
    akg = next(f for f in req.cites if "akg" in f.url)
    pad = next(f for f in req.cites if "pad" in f.url)
    assert akg.load_bearing is True
    assert pad.reachable is True and pad.load_bearing is False


def test_needcite_uncited_factual_sentence_is_required():
    report = "Headphones generally cost between 20 and 400 dollars on the market."
    claims = build_claim_evidence(report, {})
    # One numeric sentence, no citation -> a required claim scoring 0.
    assert len(claims) == 1
    assert claims[0].needs_citation is True
    assert claims[0].cites == []
    assert claims[0].supp == 0.0


def test_needcite_heuristic():
    assert default_needs_citation("The AKG K72 costs 53.99 dollars.") is True
    assert default_needs_citation("It has a 4.5 star rating.") is True
    assert default_needs_citation("These are a nice choice overall.") is False
    assert default_needs_citation("Good.") is False


def test_no_citations_is_zero():
    v = GroundingVerifier(fetch_fn=lambda urls: {})
    r = v.verify(task_config={}, answer="Headphones are nice. No links here.")
    assert r.score == 0.0
    assert r.details.get("reason") == "no_citations"
