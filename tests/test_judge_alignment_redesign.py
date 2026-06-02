"""Offline tests for the judge-alignment redesign (Job A).

All judge backend calls are mocked: no network is touched. We monkeypatch
the module-level ``call_judge`` symbol that each verifier / pairwise module
imported, and capture the prompts that would have been sent.
"""

from __future__ import annotations

import pytest

import src.verifiers.depth_verifier as depth_mod
import src.verifiers.rigor_verifier as rigor_mod
import src.verifiers.style_verifier as style_mod
import src.verifiers.checklist_verifier as checklist_mod
import src.scoring.pairwise_judge as pairwise_mod
from src.verifiers import judge_client

from src.verifiers.depth_verifier import DepthVerifier
from src.verifiers.rigor_verifier import RigorVerifier
from src.verifiers.style_verifier import StyleVerifier
from src.verifiers.checklist_verifier import ChecklistVerifier


LONG_REPORT_HEAD = "HEAD_MARKER_UNIQUE_START. " + ("filler depth analysis. " * 400)
LONG_REPORT_TAIL = (" intermediate body. " * 400) + "CONCLUSION_MARKER_UNIQUE_END."
LONG_REPORT = LONG_REPORT_HEAD + LONG_REPORT_TAIL


def _capture(prompts: list[str], verdict_text: str = "LEVEL: 4\nEVIDENCE: ok"):
    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        prompts.append(user)
        return verdict_text, None
    return fake_call_judge


# --------------------------------------------------------------------------
# Acceptance 1: evidence kwarg does not raise, evidence text appears in prompt
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mod,Verifier,verdict",
    [
        (depth_mod, DepthVerifier, "LEVEL: 4\nEVIDENCE: synthesis present"),
        (rigor_mod, RigorVerifier, "LEVEL: 4\nEVIDENCE: hedged"),
        (style_mod, StyleVerifier, "LEVEL: 4\nEVIDENCE: well structured"),
    ],
)
def test_likert_verify_accepts_evidence_and_injects_it(monkeypatch, mod, Verifier, verdict):
    prompts: list[str] = []
    monkeypatch.setattr(mod, "call_judge", _capture(prompts, verdict))
    answer = "This report synthesises sources. " * 30
    evidence = {"https://example.com/source-x": "Source X says battery is 12 hours and it is grounded."}
    # Must not raise (the old bug: TypeError on evidence=).
    res = Verifier(n_samples=1).verify(
        task_config={"intent": "compare phones"},
        answer=answer,
        evidence=evidence,
    )
    assert res.score is not None
    assert prompts, "judge should have been called"
    joined = "\n".join(prompts)
    assert "https://example.com/source-x" in joined
    assert "Retrieved evidence" in joined


def test_checklist_verify_accepts_evidence_and_rubric_snapshot(monkeypatch, tmp_path):
    prompts: list[str] = []

    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        prompts.append(user)
        return "1. PASS\n2. FAIL", None

    monkeypatch.setattr(checklist_mod, "call_judge", fake_call_judge)
    import json
    cl = tmp_path / "checklists.json"
    cl.write_text(json.dumps({"task-1": ["criterion one", "criterion two"]}))
    v = ChecklistVerifier(checklist_path=cl, n_samples=1)
    evidence = {"https://ex.com/cl": "Evidence snippet for checklist grounding."}
    # Passing both evidence and rubric_snapshot (extra kwarg) must not raise.
    res = v.verify(
        task_config={"task_id": "task-1", "intent": "do x"},
        answer="A long enough report body. " * 30,
        evidence=evidence,
        rubric_snapshot={"unused": True},
    )
    assert res.details["total"] == 2
    assert "https://ex.com/cl" in "\n".join(prompts)


# --------------------------------------------------------------------------
# Acceptance 2: few-shot exemplars are injected into the prompt
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mod,Verifier",
    [
        (depth_mod, DepthVerifier),
        (rigor_mod, RigorVerifier),
        (style_mod, StyleVerifier),
    ],
)
def test_exemplars_injected(monkeypatch, mod, Verifier):
    prompts: list[str] = []
    monkeypatch.setattr(mod, "call_judge", _capture(prompts))
    Verifier(n_samples=1).verify(
        task_config={"intent": "compare phones"},
        answer="A grounded report body. " * 30,
    )
    joined = "\n".join(prompts)
    assert "Calibration exemplars" in joined
    assert "LEVEL 1" in joined  # at least one exemplar level rendered


def test_exemplars_missing_falls_back(monkeypatch):
    # When the exemplar file is missing, format block is empty and the prompt
    # is built without raising.
    monkeypatch.setattr(judge_client, "_EXEMPLAR_ROOT", judge_client.Path("/nonexistent/dir"))
    assert judge_client.load_exemplars("depth") == []
    assert judge_client.format_exemplars_block([]) == ""


# --------------------------------------------------------------------------
# Acceptance 3: de-truncation keeps head AND conclusion for long reports
# --------------------------------------------------------------------------

def test_smart_truncate_keeps_head_and_tail():
    assert len(LONG_REPORT) > 6000
    out = judge_client.smart_truncate(LONG_REPORT, cap=9000)
    assert "HEAD_MARKER_UNIQUE_START" in out
    assert "CONCLUSION_MARKER_UNIQUE_END" in out
    assert len(out) <= 9000


def test_long_report_prompt_keeps_conclusion(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(depth_mod, "call_judge", _capture(prompts))
    DepthVerifier(n_samples=1).verify(
        task_config={"intent": "x"}, answer=LONG_REPORT
    )
    joined = "\n".join(prompts)
    assert "HEAD_MARKER_UNIQUE_START" in joined
    assert "CONCLUSION_MARKER_UNIQUE_END" in joined


# --------------------------------------------------------------------------
# Acceptance 4: verify_pairwise returns a dict with winner in {a,b,tie}
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mod,Verifier",
    [
        (depth_mod, DepthVerifier),
        (rigor_mod, RigorVerifier),
        (style_mod, StyleVerifier),
        (checklist_mod, ChecklistVerifier),
    ],
)
def test_verify_pairwise_returns_winner(monkeypatch, mod, Verifier):
    # The verifiers delegate to pairwise_judge.battle, which calls
    # call_judge inside the pairwise module. Mock that one.
    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        return "Reason bullet.\nVERDICT: A", None

    monkeypatch.setattr(pairwise_mod, "call_judge", fake_call_judge)
    res = Verifier().verify_pairwise(
        {"intent": "compare"},
        "Report A body that is reasonably long. " * 10,
        "Report B body that is reasonably long. " * 10,
    )
    assert isinstance(res, dict)
    assert res["winner"] in ("a", "b", "tie")
    # Judge always says A in original order; under swap it says A again
    # (= original B), so A vs B disagree and the debiased result is tie.
    assert res["winner"] == "tie"


def test_verify_pairwise_consistent_judge_picks_a(monkeypatch):
    # Judge that always prefers whichever report is shown FIRST would tie,
    # but here we make it prefer the actual content "ALPHA" regardless of
    # position so the debiased verdict resolves to a real winner.
    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        # Report A text contains ALPHA; find which slot ALPHA is in.
        a_idx = user.find("ALPHA")
        b_idx = user.find("BETA")
        verdict = "A" if a_idx < b_idx else "B"
        return f"reason\nVERDICT: {verdict}", None

    monkeypatch.setattr(pairwise_mod, "call_judge", fake_call_judge)
    res = DepthVerifier().verify_pairwise(
        {"intent": "compare"},
        "ALPHA report is deep and synthesises sources. " * 5,
        "BETA report just lists facts. " * 5,
    )
    assert res["winner"] == "a"


# --------------------------------------------------------------------------
# Acceptance 5: dimension-aware battle issues depth-specific prompt + swaps
# --------------------------------------------------------------------------

def test_battle_dimension_specific_prompt_and_swap(monkeypatch):
    systems: list[str] = []
    users: list[str] = []

    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        systems.append(system)
        users.append(user)
        return "reason\nVERDICT: A", None

    monkeypatch.setattr(pairwise_mod, "call_judge", fake_call_judge)
    res = pairwise_mod.battle(
        task_intent="compare phones",
        agent_a="agentA",
        answer_a="AAA report",
        agent_b="agentB",
        answer_b="BBB report",
        dimension="depth",
        n_samples=1,
    )
    # depth-specific framing present in the system prompt
    assert any("DEPTH" in s for s in systems)
    assert res.get("dimension") == "depth"
    # position-swap: with n_samples=1 and swap on, exactly two judge calls,
    # and the report order is swapped between them.
    assert len(users) == 2
    first_a = users[0].find("AAA report")
    first_b = users[0].find("BBB report")
    second_a = users[1].find("AAA report")
    second_b = users[1].find("BBB report")
    assert first_a < first_b  # A shown first in round 1
    assert second_b < second_a  # B shown first in the swapped pass


def test_battle_overall_prompt_when_no_dimension(monkeypatch):
    systems: list[str] = []

    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        systems.append(system)
        return "reason\nVERDICT: TIE", None

    monkeypatch.setattr(pairwise_mod, "call_judge", fake_call_judge)
    pairwise_mod.battle(
        task_intent="t", agent_a="a", answer_a="x", agent_b="b", answer_b="y",
        n_samples=1,
    )
    # The overall (non-dimension) system prompt is the legacy one.
    assert any("better answers the" in s for s in systems)


# --------------------------------------------------------------------------
# Acceptance 6: checklist median-of-N + cross-family selection
# --------------------------------------------------------------------------

def test_checklist_median_of_n(monkeypatch, tmp_path):
    import json
    cl = tmp_path / "checklists.json"
    cl.write_text(json.dumps({"t": ["crit one", "crit two", "crit three"]}))

    # Three samples. Item 1: PASS,PASS,FAIL -> majority PASS.
    # Item 2: FAIL,FAIL,FAIL -> FAIL. Item 3: PASS,FAIL,FAIL -> FAIL.
    sample_outputs = [
        "1. PASS\n2. FAIL\n3. PASS",
        "1. PASS\n2. FAIL\n3. FAIL",
        "1. FAIL\n2. FAIL\n3. FAIL",
    ]
    calls = {"i": 0}

    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        out = sample_outputs[calls["i"] % len(sample_outputs)]
        calls["i"] += 1
        return out, None

    monkeypatch.setattr(checklist_mod, "call_judge", fake_call_judge)
    v = ChecklistVerifier(checklist_path=cl, n_samples=3)
    res = v.verify(task_config={"task_id": "t", "intent": "x"}, answer="body " * 30)
    assert res.details["n_samples"] == 3
    assert calls["i"] == 3  # three judge calls (median-of-N)
    per_item = res.details["per_item"]
    assert per_item[0]["passed"] is True   # majority PASS
    assert per_item[1]["passed"] is False  # all FAIL
    assert per_item[2]["passed"] is False  # majority FAIL
    assert res.details["passed_count"] == 1


def test_cross_family_selection_picks_other_family(monkeypatch):
    # Two families configured: GLM (primary) and DeepSeek (alt).
    monkeypatch.setenv("JUDGE_MODEL", "glm-5.1")
    monkeypatch.setenv("JUDGE_MODEL_ALT", "deepseek-v4-flash")
    sel = judge_client.select_cross_family_judge("glm-4-agent")
    assert sel["cross_family"] is True
    assert sel["family"] == "deepseek"
    assert "deepseek" in sel["model"].lower()

    # Reverse: a DeepSeek agent should get the GLM judge.
    sel2 = judge_client.select_cross_family_judge("deepseek-chat")
    assert sel2["family"] == "glm"


def test_cross_family_single_family_falls_back(monkeypatch):
    monkeypatch.setenv("JUDGE_MODEL", "glm-5.1")
    monkeypatch.delenv("JUDGE_MODEL_ALT", raising=False)
    sel = judge_client.select_cross_family_judge("glm-4-agent")
    assert sel["cross_family"] is False
    assert sel["model"] == "glm-5.1"


def test_cross_family_unknown_agent_uses_default(monkeypatch):
    monkeypatch.setenv("JUDGE_MODEL", "glm-5.1")
    monkeypatch.setenv("JUDGE_MODEL_ALT", "deepseek-v4-flash")
    sel = judge_client.select_cross_family_judge(None)
    assert sel["cross_family"] is False
    assert sel["model"] == "glm-5.1"


def test_family_of():
    assert judge_client.family_of("glm-5.1") == "glm"
    assert judge_client.family_of("deepseek-v4-flash") == "deepseek"
    assert judge_client.family_of("claude-3-7-sonnet") == "claude"
    assert judge_client.family_of("totally-unknown-model") is None
    assert judge_client.family_of(None) is None
