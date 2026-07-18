from __future__ import annotations

from scripts.run_route_b_audio_0002_pilot import run


def test_real_audio_0002_route_b_pilot_replays_dual_metrics(tmp_path) -> None:
    summary = run(tmp_path / "route-b-audio-0002")
    assert summary["required_steps"] == 15

    positive = summary["scenarios"]["positive"]
    assert positive == {
        "status": "scored",
        "withheld": False,
        "passed_steps": 15,
        "required_steps": 15,
        "partial_completion": 1.0,
        "full_pass": 1,
        "final_answer_pass": True,
        "fabricated_citations": 0,
        "failure_reasons": [],
    }

    partial = summary["scenarios"]["partial"]
    assert partial["passed_steps"] == 10
    assert partial["required_steps"] == 15
    assert partial["partial_completion"] == 10 / 15
    assert partial["full_pass"] == 0
    assert partial["final_answer_pass"] is False

    fabricated = summary["scenarios"]["fabricated"]
    assert fabricated["passed_steps"] == 15
    assert fabricated["partial_completion"] == 1.0
    assert fabricated["full_pass"] == 0
    assert fabricated["final_answer_pass"] is True
    assert fabricated["fabricated_citations"] == 1
