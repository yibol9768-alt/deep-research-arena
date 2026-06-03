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


def test_state_diff_only_does_not_bypass_fabrication_nullify() -> None:
    # An agent that fabricates every citation (cites a sandbox URL it never
    # fetched) must score 0.0 even on an execution task whose state-diff is a
    # perfect 1.0. The state_diff_only override must not silently win over the
    # anti-fabrication nullify gate.
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
    ev = _evaluator(config)
    ev._rl_strict = True
    rollout = Rollout(
        task_id="state_diff_synth",
        report_md="Added it. See [product](http://localhost:7770/product/NOVAMAX).",
        fetched_urls=[],
        retrieved_snippets={},
        trace={
            "tool_state_deltas": [
                {"delta": {"observed_state": {"cart": {"items": [{"sku": "NOVAMAX", "qty": 1}]}}}}
            ]
        },
    )

    result = ev.evaluate_rollout(rollout)

    assert result.reward_terms["penalties"]["nullify"] is True
    assert result.reward_terms["execution"]["score"] == 1.0
    assert result.composite == 0.0
    assert result.breakdown["execution_override"]["nullified"] is True
    assert result.breakdown["execution_override"]["state_diff_effective"] == 0.0


def test_blend_does_not_bypass_fabrication_nullify() -> None:
    # Same fabrication, but a blend-mode execution task. The blended composite
    # must collapse to 0.0 as well, not leak the state-diff term through the
    # state_weight.
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
    ev = _evaluator(config)
    ev._rl_strict = True
    rollout = Rollout(
        task_id="state_diff_synth",
        report_md="Cancelled. See [order](http://localhost:7770/order/A1).",
        fetched_urls=[],
        retrieved_snippets={},
        trace={"tool_state_deltas": [{"delta": {"observed_state": {"orders": {"A1": {"status": "cancelled"}}}}}]},
    )

    result = ev.evaluate_rollout(rollout)

    assert result.reward_terms["penalties"]["nullify"] is True
    assert result.composite == 0.0
    assert result.breakdown["execution_blend"]["nullified"] is True
    assert result.breakdown["execution_blend"]["state_diff_effective"] == 0.0


def test_no_url_coverage_spec_drops_coverage_weight() -> None:
    # A task with no url_coverage spec yields coverage=0.0 with a `reason`
    # (no `error` key). That dim carries no signal and must be dropped and
    # renormalized out of weights_effective, not freeze ~18% of the reward
    # mass at a constant 0.0.
    config = {
        "task_id": "no_coverage_synth",
        "intent": "Write a report.",
        "markdown_spec": {"min_words": 1, "max_words": 1000, "min_citations": 0, "min_paragraphs": 1},
    }
    ev = _evaluator(config)
    rollout = Rollout(
        task_id="no_coverage_synth",
        report_md="A reasonably long report. " * 10 + "[link](http://localhost:7770/x).",
        fetched_urls=["http://localhost:7770/x"],
        retrieved_snippets={"http://localhost:7770/x": "content"},
    )

    result = ev.evaluate_rollout(rollout)

    assert "coverage" in result.reward_terms["degraded_dims"]
    assert "coverage" in result.breakdown["dims_dropped"]
    assert "coverage" not in result.breakdown["weights_effective"]


def test_read_only_rollout_has_no_execution_terms() -> None:
    config = {
        "task_id": "state_diff_synth",
        "intent": "Write a short answer.",
        "markdown_spec": {"min_words": 1, "max_words": 100, "min_citations": 0, "min_paragraphs": 1},
    }
    rollout = Rollout(task_id="state_diff_synth", report_md="Short answer.")

    result = _evaluator(config).evaluate_rollout(rollout)

    assert "execution" not in result.reward_terms
