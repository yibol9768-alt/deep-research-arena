"""Offline test for the closed-world weighted rubric layer (section 9).

Mocks the judge so it runs with no LLM. Verifies that:
  (a) a task's `rubric_path` is loaded and routed to the graded snapshot path;
  (b) weighted scoring uses RR/DRACO normalization (positive weights only);
  (c) negative (penalty) criteria pull the score down and it clamps to [0,1].
"""

from __future__ import annotations

import src.verifiers.checklist_verifier as cv
from src.verifiers.checklist_verifier import ChecklistVerifier

TASK = {
    "task_id": "dr_cw_pilot_0001",
    "intent": "pick noise-cancelling headphones",
    "rubric_path": "data/tasks/deep_research/cross_site_deep/rubrics_cw.json",
}
# rubric weights, in order: 5, 5, 4, 3, 4, 2, -3, -3  (6 positive sum=23, 2 penalty)


def _mock_judge(verdicts):
    text = "\n".join(f"{i+1}. {v}" for i, v in enumerate(verdicts))
    def fake_call_judge(system, prompt, max_tokens=1500):
        return text, None
    return fake_call_judge


def test_good_report_scores_one(monkeypatch):
    # positive criteria FULL, penalty criteria NONE (not triggered) -> 23/23 = 1.0
    monkeypatch.setattr(cv, "call_judge",
                        _mock_judge(["FULL"] * 6 + ["NONE", "NONE"]))
    r = ChecklistVerifier(n_samples=1).verify(task_config=TASK, answer="a grounded report")
    assert r.details.get("version") == "cw-1"
    assert abs(r.score - 1.0) < 1e-6
    assert r.passed is True


def test_penalty_criteria_pull_score_down_and_clamp(monkeypatch):
    # positive criteria NONE, penalty criteria FULL (triggered) -> -6/23 -> clamp 0.0
    monkeypatch.setattr(cv, "call_judge",
                        _mock_judge(["NONE"] * 6 + ["FULL", "FULL"]))
    r = ChecklistVerifier(n_samples=1).verify(task_config=TASK, answer="off-topic padded report")
    assert r.score == 0.0


def test_partial_positive_no_penalty(monkeypatch):
    # all positive PARTIAL (credit 0.5), penalties NONE -> 11.5/23 = 0.5
    monkeypatch.setattr(cv, "call_judge",
                        _mock_judge(["PARTIAL"] * 6 + ["NONE", "NONE"]))
    r = ChecklistVerifier(n_samples=1).verify(task_config=TASK, answer="partially good report")
    assert abs(r.score - 0.5) < 1e-6
