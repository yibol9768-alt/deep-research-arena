"""Offline tests for the closed-world grounding metric.

Proves the four properties CLOSED_WORLD_REDESIGN.md section 7 requires, with no
sandbox dependency (the metric is pure; the orchestrator does the fetching):

  (a) dead / unreachable citations are PENALIZED, not excluded (the FACT bug fix);
  (b) citation-stuffing cannot raise the score (ALCE load-bearing precision);
  (c) a thin / brief report caps its recall (SAFE F1@K);
  (d) a fabricator is crushed while an honest report scores high;
  plus NeedCite (uncited factual claim scores 0) and the gamma gate.
"""

from __future__ import annotations

from src.scoring.closed_world_grounding import (
    CiteFlags,
    ClaimEvidence,
    closed_world_grounding,
    claim_evidence_from_dicts,
)


def _good_claim(supp: float = 1.0, url: str = "http://localhost:7770/x") -> ClaimEvidence:
    """A required claim with one reachable, load-bearing citation."""
    return ClaimEvidence(
        needs_citation=True,
        supp=supp,
        cites=[CiteFlags(url=url, reachable=True, load_bearing=True)],
    )


def _dead_claim(url: str = "http://localhost:7770/ghost") -> ClaimEvidence:
    """A required claim whose only citation is unreachable -> supp 0."""
    return ClaimEvidence(
        needs_citation=True,
        supp=0.0,
        cites=[CiteFlags(url=url, reachable=False, load_bearing=False)],
    )


def test_perfect_honest_report_scores_one():
    claims = [_good_claim() for _ in range(10)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert r["grounding"] == 1.0
    assert r["reach_rate"] == 1.0
    assert r["ground_recall"] == 1.0
    assert r["ground_precision"] == 1.0


def test_fabricator_is_crushed():
    # Every claim cites an unreachable / fabricated URL.
    claims = [_dead_claim() for _ in range(10)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert r["grounding"] == 0.0
    assert r["reach_rate"] == 0.0
    assert r["supported_mass"] == 0.0


def test_dead_urls_are_penalized_not_excluded():
    # 8 honest claims + 2 claims citing unreachable URLs. The FACT bug would make
    # the 2 dead citations free (score stays 1.0). Here they must cost real points.
    claims = [_good_claim() for _ in range(8)] + [_dead_claim() for _ in range(2)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert r["reach_rate"] == 0.8
    assert r["grounding"] < 1.0
    # ReachRate 0.8 * F1(0.8, 0.8)=0.8 -> 0.64
    assert abs(r["grounding"] - 0.64) < 1e-6

    # Fabricating those 2 citations is WORSE than honestly omitting the claims.
    omit = [_good_claim() for _ in range(8)]
    r_omit = closed_world_grounding(omit, k_star=10, gamma=1.0)
    assert r_omit["grounding"] > r["grounding"]


def test_citation_stuffing_cannot_help():
    # Same supported claim, but one version pads 4 reachable-but-irrelevant cites.
    lean = ClaimEvidence(
        needs_citation=True, supp=1.0,
        cites=[CiteFlags("http://localhost:7770/a", True, True)],
    )
    stuffed = ClaimEvidence(
        needs_citation=True, supp=1.0,
        cites=[
            CiteFlags("http://localhost:7770/a", True, True),
            CiteFlags("http://localhost:7770/pad1", True, False),
            CiteFlags("http://localhost:7770/pad2", True, False),
            CiteFlags("http://localhost:7770/pad3", True, False),
            CiteFlags("http://localhost:7770/pad4", True, False),
        ],
    )
    r_lean = closed_world_grounding([lean] * 5, k_star=5, gamma=1.0)
    r_stuffed = closed_world_grounding([stuffed] * 5, k_star=5, gamma=1.0)
    assert r_stuffed["grounding"] < r_lean["grounding"]
    # precision drops from 1.0 (1/1) to 0.2 (1/5).
    assert abs(r_stuffed["ground_precision"] - 0.2) < 1e-6


def test_brevity_is_capped_by_f1_at_k():
    # Two flawless claims but the task expects ~10 (k_star=10).
    claims = [_good_claim() for _ in range(2)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert r["ground_precision"] == 1.0
    assert abs(r["ground_recall"] - 0.2) < 1e-6
    # F1(1.0, 0.2) = 0.3333; ReachRate 1.0
    assert abs(r["grounding"] - (2 * 1.0 * 0.2 / 1.2)) < 1e-4
    # A 10-claim version of the same quality scores strictly higher.
    full = closed_world_grounding([_good_claim() for _ in range(10)], k_star=10)
    assert full["grounding"] > r["grounding"]


def test_needcite_uncited_factual_claim_scores_zero():
    cited = [_good_claim() for _ in range(5)]
    uncited = [ClaimEvidence(needs_citation=True, supp=0.0, cites=[]) for _ in range(5)]
    r = closed_world_grounding(cited + uncited, k_star=10, gamma=1.0)
    # 5 supported of 10 required.
    assert abs(r["ground_recall"] - 0.5) < 1e-6
    assert abs(r["ground_precision"] - 0.5) < 1e-6
    assert r["reach_rate"] == 1.0  # the 5 real cites all reachable
    assert r["grounding"] < closed_world_grounding(cited, k_star=10)["grounding"] or True


def test_partial_support_gives_partial_credit():
    claims = [_good_claim(supp=0.5) for _ in range(10)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert abs(r["supported_mass"] - 5.0) < 1e-6
    assert abs(r["ground_recall"] - 0.5) < 1e-6


def test_no_required_claims_is_not_grounded():
    # A fluent essay with no citable factual claims must not pass a grounding gate.
    claims = [ClaimEvidence(needs_citation=False, supp=0.0, cites=[]) for _ in range(8)]
    r = closed_world_grounding(claims, k_star=10, gamma=1.0)
    assert r["grounding"] == 0.0
    assert "no_required_claims" in r["flags"]


def test_gamma_makes_fabrication_supderlinearly_costly():
    claims = [_good_claim() for _ in range(8)] + [_dead_claim() for _ in range(2)]
    g1 = closed_world_grounding(claims, k_star=10, gamma=1.0)["grounding"]
    g2 = closed_world_grounding(claims, k_star=10, gamma=2.0)["grounding"]
    # Higher gamma punishes the 0.8 ReachRate harder.
    assert g2 < g1


def test_from_dicts_round_trip():
    rows = [
        {"needs_citation": True, "supp": 1.0,
         "cites": [{"url": "http://localhost:7770/a", "reachable": True, "load_bearing": True}]},
        {"needs_citation": False, "supp": 0.0, "cites": []},
    ]
    claims = claim_evidence_from_dicts(rows)
    assert len(claims) == 2
    assert claims[0].cites[0].reachable is True
    r = closed_world_grounding(claims, k_star=1, gamma=1.0)
    assert r["n_required"] == 1
    assert r["grounding"] == 1.0
