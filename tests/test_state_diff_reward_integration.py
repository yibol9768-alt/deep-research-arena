from __future__ import annotations

from src.eval.evaluator import ArenaEvaluator
from src.eval.rollout import Rollout


def _evaluator(config: dict) -> ArenaEvaluator:
    ev = ArenaEvaluator("state_diff_synth", mode="fast")
    ev._task_config = config
    return ev


def test_state_diff_only_overrides_report_reward() -> None:
    config = {
        "task_id": "state_diff_synth",
        "intent": "Add an item to the cart.",
        "markdown_spec": {"min_words": 1, "max_words": 100, "min_citations": 0, "min_paragraphs": 1},
        "execution_goal": {
            "reward_mode": "state_diff_only",
            "initial_state": {"cart": {"items": []}},
            "expected_state": {"cart": {"items": [{"sku": "NOVAMAX", "qty": 1}]}},
        },
    }
    rollout = Rollout(
        task_id="state_diff_synth",
        report_md="Done.",
        trace={
            "tool_state_deltas": [
                {"delta": {"observed_state": {"cart": {"items": [{"sku": "NOVAMAX", "qty": 1}]}}}}
            ]
        },
    )

    result = _evaluator(config).evaluate_rollout(rollout)

    assert result.composite == 1.0
    assert result.reward_terms["execution"]["score"] == 1.0
    assert result.reward_terms["execution"]["mode"] == "state_diff_only"


def test_state_diff_blend_uses_state_weight() -> None:
    config = {
        "task_id": "state_diff_synth",
        "intent": "Cancel an order.",
        "markdown_spec": {"min_words": 1, "max_words": 100, "min_citations": 0, "min_paragraphs": 1},
        "execution_goal": {
            "reward_mode": "blend",
            "state_weight": 0.25,
            "initial_state": {"orders": {"A1": {"status": "placed"}}},
            "expected_state": {"orders": {"A1": {"status": "cancelled"}}},
        },
    }
    rollout = Rollout(
        task_id="state_diff_synth",
        report_md="The order is done.",
        trace={"tool_state_deltas": [{"delta": {"observed_state": {"orders": {"A1": {"status": "cancelled"}}}}}]},
    )

    result = _evaluator(config).evaluate_rollout(rollout)

    blend = result.breakdown["execution_blend"]
    assert blend["state_weight"] == 0.25
    assert blend["state_diff"] == 1.0
    assert 0.0 < result.composite <= 1.0


def test_read_only_rollout_has_no_execution_terms() -> None:
    config = {
        "task_id": "state_diff_synth",
        "intent": "Write a short answer.",
        "markdown_spec": {"min_words": 1, "max_words": 100, "min_citations": 0, "min_paragraphs": 1},
    }
    rollout = Rollout(task_id="state_diff_synth", report_md="Short answer.")

    result = _evaluator(config).evaluate_rollout(rollout)

    assert "execution" not in result.reward_terms
