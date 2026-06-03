"""Unit tests for PerspectiveBalanceVerifier (no network / no browser).

Focus: tier-B judge-error handling. A judge / infra failure on an entity must
NOT be conflated with a report that genuinely lacks balance. See the bug fix
in src/verifiers/perspective_balance_verifier.py (_tier_b denominator + the
all-errored not-applicable path).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.verifiers.perspective_balance_verifier as pbv
from src.verifiers.perspective_balance_verifier import PerspectiveBalanceVerifier


# A report that mentions three entities with both praise and concrete downsides.
_REPORT = """
# ANC Headphone Recommendations

This report covers three leading active noise cancelling headphones with both
their strengths and their limitations so readers get a balanced picture.

### Sony WH-1000XM5

The Sony WH-1000XM5 offers excellent noise cancellation and a comfortable fit.
However, reviewers complain that the build feels flimsy and the price is
overpriced compared with the previous generation.

### Bose QuietComfort Ultra

The Bose QuietComfort Ultra is praised for a natural, balanced sound. A common
criticism is the short battery life and a confusing companion app.

### Sennheiser Momentum 4

The Sennheiser Momentum 4 has a reliable, durable build. A frequent drawback is
that the touch controls are laggy and the case is bulky.
""".strip()


def _task(min_score: float = 0.50) -> dict:
    return {
        "perspective_balance": {
            "evaluated_entities": [
                "Sony WH-1000XM5",
                "Bose QuietComfort Ultra",
                "Sennheiser Momentum 4",
            ],
            "min_score": min_score,
        }
    }


def _patch_judge(monkeypatch, fn):
    monkeypatch.setattr(pbv, "call_judge", fn)


def test_all_pass_when_judge_says_pass(monkeypatch):
    _patch_judge(monkeypatch, lambda *a, **k: ("VERDICT: PASS", None))
    res = PerspectiveBalanceVerifier().verify(task_config=_task(), answer=_REPORT)
    assert res.details["applicable"] is True
    assert res.details["tier_b"]["rate"] == 1.0
    assert res.details["tier_b"]["n_errors"] == 0
    # tier_a + tier_b both strong => high combined score, passes gate.
    assert res.score >= 0.5
    assert res.passed is True


def test_judge_error_on_one_entity_excluded_from_denominator(monkeypatch):
    """One of three entities errors; tier-B rate is over the 2 evaluated
    entities, NOT diluted by treating the errored one as a FAIL."""
    calls = {"n": 0}

    def judge(*a, **k):
        calls["n"] += 1
        # First entity errors (infra), the other two PASS.
        if calls["n"] == 1:
            return (None, "judge backend 503")
        return ("VERDICT: PASS", None)

    _patch_judge(monkeypatch, judge)
    res = PerspectiveBalanceVerifier().verify(task_config=_task(), answer=_REPORT)
    assert res.details["applicable"] is True
    tb = res.details["tier_b"]
    assert tb["n_errors"] == 1
    # 2 evaluated entities, both PASS => rate 1.0 (not 2/3 ~= 0.67).
    assert tb["rate"] == 1.0
    verdicts = [r["verdict"] for r in tb["rows"]]
    assert verdicts.count("ERROR") == 1
    assert verdicts.count("PASS") == 2


def test_judge_error_does_not_penalize_vs_no_error(monkeypatch):
    """A report scored with one errored entity must score AT LEAST as high as
    the same report where that entity is (incorrectly) counted as a FAIL."""
    # Case A (fixed behaviour): one error, two PASS.
    seq_a = iter([(None, "down"), ("VERDICT: PASS", None), ("VERDICT: PASS", None)])
    _patch_judge(monkeypatch, lambda *a, **k: next(seq_a))
    res_a = PerspectiveBalanceVerifier().verify(task_config=_task(), answer=_REPORT)

    # Case B: same two PASS but the third genuinely FAILs (real signal).
    seq_b = iter([("VERDICT: FAIL", None), ("VERDICT: PASS", None), ("VERDICT: PASS", None)])
    _patch_judge(monkeypatch, lambda *a, **k: next(seq_b))
    res_b = PerspectiveBalanceVerifier().verify(task_config=_task(), answer=_REPORT)

    # The errored case must not be punished below the genuine-FAIL case.
    assert res_a.details["tier_b"]["rate"] >= res_b.details["tier_b"]["rate"]
    assert res_a.score >= res_b.score


def test_all_entities_errored_returns_not_applicable(monkeypatch):
    """If the judge backend is down for every entity, the pillar is excluded
    (score=None, applicable=False) rather than scored a misleading 0.0."""
    _patch_judge(monkeypatch, lambda *a, **k: (None, "judge backend down"))
    res = PerspectiveBalanceVerifier().verify(task_config=_task(), answer=_REPORT)
    assert res.score is None
    assert res.passed is False
    assert res.details["applicable"] is False
    assert res.details["reason"] == "tier_b_all_errored"
    assert res.details["n_errors"] == 3
    # tier_a detail is still surfaced for debugging.
    assert "tier_a" in res.details


def test_not_mentioned_entity_still_counts_as_fail(monkeypatch):
    """An entity the report never mentions is a genuine FAIL (omission), not an
    infra error, so it stays in the denominator."""
    _patch_judge(monkeypatch, lambda *a, **k: ("VERDICT: PASS", None))
    task = _task()
    task["perspective_balance"]["evaluated_entities"].append("Apple AirPods Max")
    res = PerspectiveBalanceVerifier().verify(task_config=task, answer=_REPORT)
    tb = res.details["tier_b"]
    rows = {r["entity"]: r for r in tb["rows"]}
    assert rows["Apple AirPods Max"]["verdict"] == "FAIL"
    assert rows["Apple AirPods Max"]["reason"] == "not_mentioned"
    assert tb["n_errors"] == 0
    # 3 PASS + 1 not-mentioned FAIL over 4 evaluated => 0.75.
    assert tb["rate"] == 0.75


def test_empty_entities_is_neutral(monkeypatch):
    """No evaluated entities and no H3 entity headings => N/A, neutral 1.0."""
    _patch_judge(monkeypatch, lambda *a, **k: ("VERDICT: PASS", None))
    answer = (
        "This is a timeline report describing a sequence of historical events "
        "over the course of several years, with more than enough words present "
        "in the body so that the verifier safely clears the degenerate answer "
        "guard and actually evaluates the prose. There are no rated product "
        "entities here and no third level headings, so the verifier should "
        "reach the no-entity branch and return a neutral score of exactly one "
        "to signal that this dimension simply does not apply to the task."
    )
    res = PerspectiveBalanceVerifier().verify(task_config={}, answer=answer)
    assert res.details["applicable"] is False
    assert res.details["reason"] == "no_evaluated_entities"
    assert res.score == 1.0
