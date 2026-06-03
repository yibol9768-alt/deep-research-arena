"""Offline tests for the pairwise judge's report window.

Regression test for the bug where ``_judge_once`` clipped each report to the
first ~5000 chars, hiding a long report's conclusion (where synthesis lives)
from the judge that drives the leaderboard. The fix raises the cap
(``PAIRWISE_REPORT_CAP``, default ~12000) and uses head+tail smart truncation
so the judge sees BOTH the intro and the conclusion.

The judge backend is mocked: no network is touched. We monkeypatch the
module-level ``call_judge`` symbol the pairwise module imported and capture the
user prompt that would have been sent.
"""

from __future__ import annotations

import src.scoring.pairwise_judge as pairwise_mod
from src.scoring.pairwise_judge import battle


HEAD_MARKER = "HEAD_MARKER_UNIQUE_TOKEN"
UNIQUE_CONCLUSION_MARKER = "UNIQUE_CONCLUSION_MARKER_TOKEN"


def _capture(prompts: list[str]):
    def fake_call_judge(system, user, **kwargs):  # type: ignore[no-untyped-def]
        prompts.append(user)
        return "reason\nVERDICT: A", None

    return fake_call_judge


def _long_report() -> str:
    # >15000 chars: head marker, big filler middle, tail conclusion marker.
    filler = "lorem ipsum dolor sit amet " * 800  # ~21k chars
    return f"# Intro\n{HEAD_MARKER}\n{filler}\n## Conclusion\n{UNIQUE_CONCLUSION_MARKER}\n"


def test_long_report_keeps_head_and_conclusion(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(pairwise_mod, "call_judge", _capture(prompts))

    long_a = _long_report()
    assert len(long_a) > 15000

    battle(
        task_intent="Compare two reports.",
        agent_a="alpha",
        answer_a=long_a,
        agent_b="beta",
        answer_b="short report B",
        swap_for_position_bias=False,
        n_samples=1,
    )

    assert prompts, "judge was never called"
    joined = "\n".join(prompts)
    # Both ends of the long report must survive into the judge prompt.
    assert HEAD_MARKER in joined, "head of long report was dropped"
    assert UNIQUE_CONCLUSION_MARKER in joined, "conclusion of long report was dropped"


def test_short_report_passed_verbatim(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(pairwise_mod, "call_judge", _capture(prompts))

    short = "A concise report with " + HEAD_MARKER + " and " + UNIQUE_CONCLUSION_MARKER + "."
    assert len(short) < pairwise_mod._report_cap()

    battle(
        task_intent="Compare.",
        agent_a="alpha",
        answer_a=short,
        agent_b="beta",
        answer_b="other short report",
        swap_for_position_bias=False,
        n_samples=1,
    )

    joined = "\n".join(prompts)
    # Verbatim: no elision marker, full text present.
    assert short in joined
    assert "middle of report omitted" not in joined


def test_env_cap_override(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(pairwise_mod, "call_judge", _capture(prompts))
    monkeypatch.setenv("PAIRWISE_REPORT_CAP", "20000")

    assert pairwise_mod._report_cap() == 20000

    long_a = _long_report()  # ~21k, just over the 20k override
    battle(
        task_intent="Compare.",
        agent_a="alpha",
        answer_a=long_a,
        agent_b="beta",
        answer_b="short",
        swap_for_position_bias=False,
        n_samples=1,
    )
    joined = "\n".join(prompts)
    assert HEAD_MARKER in joined
    assert UNIQUE_CONCLUSION_MARKER in joined
