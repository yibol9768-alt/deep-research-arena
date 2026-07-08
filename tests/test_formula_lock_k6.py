"""FORMULA_LOCK_2026-07-08 (candidate K6) regression tests.

Locks the three structural decisions derived from the two adversarial criteria:
  * spec is OUT of truth (compliance is a separate column) -- C2;
  * floor-if-active: a zero-substance axis stays 0, only a >0 axis is buffered;
  * three evidence weights 0.39/0.28/0.33 summing to 1.0.

The headline assertion is C2: a format-compliant EMPTY SHELL (zero substance,
one real reachable citation, perfect spec) must score truth=0 -- strictly below
every honest report with any substance. Under the old four-axis K0 the shell
scored 0.145 and outranked the honest champion (0.113); K6 collapses it to 0.
"""

import itertools

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey


def test_quality_weights_three_axes_sum_one():
    w = ds.QUALITY_WEIGHTS
    assert set(w) == {"fact_support", "proof_of_fetch", "completeness"}
    assert "spec" not in w
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_spec_not_in_truth():
    """Two reports identical on the evidence axes but differing on spec compose
    to the SAME truth: spec is not multiplied in."""
    base = dict(reach=0.9, fact=0.4, pof=0.3, completeness=0.2)
    t_lo, q_lo, _ = ds.compose_truth(**base, spec=0.0)
    t_hi, q_hi, _ = ds.compose_truth(**base, spec=1.0)
    assert t_lo == t_hi
    assert q_lo == q_hi


def test_floor_if_active():
    """eps floors a >0 axis but never a zero axis."""
    # all three axes zero -> quality 0 (no unconditional floor)
    _t, q0, floors0 = ds.compose_truth(1.0, 0.0, 0.0, 0.0)
    assert q0 == 0.0
    assert not any(floors0.values())
    # a tiny positive axis is floored up to eps; the zero axes stay 0
    _t, q1, floors1 = ds.compose_truth(1.0, 0.01, 0.0, 0.0)
    assert floors1["fact_support"] is True
    assert floors1["completeness"] is False
    assert abs(q1 - ds.QUALITY_WEIGHTS["fact_support"] * ds.EPS_FLOOR) < 1e-9


def test_empty_shell_truth_is_zero_C2():
    """The empty-shell adversary: reach=1 (one real reachable citation),
    fact=pof=comp=0, spec=1 (perfect format). truth must be exactly 0."""
    for gamma in (1.0, 1.5, 2.0):
        t, q, _ = ds.compose_truth(1.0, 0.0, 0.0, 0.0, spec=1.0, gamma=gamma)
        assert q == 0.0
        assert t == 0.0


def test_shell_below_every_report_with_substance_C2():
    """Across a dense grid of honest reports that have ANY substance (a nonzero
    evidence axis), the empty shell never ties or beats them."""
    shell = ds.compose_truth(1.0, 0.0, 0.0, 0.0, spec=1.0)[0]
    assert shell == 0.0
    grid = (0.0, 0.05, 0.3, 0.6, 1.0)
    for reach in (0.3, 0.6, 0.9, 1.0):
        for fact, pof, comp in itertools.product(grid, repeat=3):
            if fact == 0.0 and pof == 0.0 and comp == 0.0:
                continue  # not a substance report
            t = ds.compose_truth(reach, fact, pof, comp, spec=0.0)[0]
            assert t > shell


def test_score_report_shell_is_zero_and_reports_compliance():
    """End to end through score_report: a spec-compliant report that cites a
    reachable page but has zero verifiable substance scores truth=0, yet still
    surfaces a nonzero compliance figure on the separate column."""
    ak = AnswerKey.load("data/golden/answer_keys/dr_cross_deep_0001.json")
    url = "http://localhost:7770/formula-lock-shell.html"
    cache = {url: {"status": 200,
                   "text": "<html><body>Assorted weather notes for the "
                           "region and other unrelated boilerplate.</body>"
                           "</html>"}}
    # narrative that names no DB entity, makes no price/rating claim, and
    # reproduces nothing verbatim from the cited page.
    shell_md = ("## Overview\n\nThis is a broad general survey of the topic "
                "with a table below and more than the required word count of "
                "filler prose repeated to satisfy any length quota. "
                * 6 + "\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
                "General reflections follow ([ref](" + url + ")).\n")
    # registry=None forces the cache-status fallback where a localhost 200 URL
    # is reachable, isolating the C2 property (reach>0, quality=0 -> truth 0).
    s = ds.score_report(shell_md, ak, cache, registry=None)
    assert s.reach > 0.0
    assert s.fact_support == 0.0
    assert s.proof_of_fetch == 0.0
    assert s.completeness == 0.0
    assert s.quality == 0.0
    assert s.truth == 0.0
    # compliance (spec) is still reported on its own column, not in truth
    assert s.compliance == s.spec
    assert "compliance" in s.detail
