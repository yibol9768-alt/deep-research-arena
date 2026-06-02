from __future__ import annotations

from src.eval.rollout import Rollout
from src.verifiers.state_diff_verifier import StateDiffVerifier


def test_state_diff_exact_recursive_subset_passes() -> None:
    cfg = {
        "execution_goal": {
            "expected_state": {
                "cart": {"items": [{"sku": "NMX-PRO", "quantity": 2}]},
                "orders": {"ord-1": {"status": "cancelled"}},
            }
        }
    }
    observed = {
        "cart": {"items": [{"sku": "NMX-PRO", "quantity": 2, "price": 299}]},
        "orders": {"ord-1": {"status": "cancelled", "total": 598}},
    }

    result = StateDiffVerifier().verify(task_config=cfg, observed_state=observed)

    assert result.passed is True
    assert result.score == 1.0


def test_state_diff_partial_match_scores_fraction() -> None:
    cfg = {"execution_goal": {"expected_state": {"order": {"status": "cancelled", "total": 10}}}}
    result = StateDiffVerifier().verify(
        task_config=cfg,
        observed_state={"order": {"status": "placed", "total": 10}},
    )

    assert result.passed is False
    assert result.score == 0.5


def test_state_diff_reconstructs_from_tool_state_deltas() -> None:
    cfg = {
        "execution_goal": {
            "initial_state": {},
            "expected_state": {"orders": {"ord-1": {"status": "cancelled"}}},
        }
    }
    rollout = Rollout(
        task_id="write_task",
        report_md="",
        trace={
            "tool_state_deltas": [
                {"tool": "order_place", "delta": {"op": "order_place", "result": {"order_id": "ord-1"}}},
                {
                    "tool": "order_cancel",
                    "delta": {"op": "order_cancel", "result": {"order_id": "ord-1", "status": "cancelled"}},
                },
            ]
        },
    )

    result = StateDiffVerifier().verify(task_config=cfg, rollout=rollout)

    assert result.passed is True
    assert result.details["observed_state"]["orders"]["ord-1"]["status"] == "cancelled"


def test_state_diff_missing_expected_state_fails() -> None:
    result = StateDiffVerifier().verify(task_config={}, observed_state={})
    assert result.passed is False
    assert result.details["reason"] == "missing_expected_state"
