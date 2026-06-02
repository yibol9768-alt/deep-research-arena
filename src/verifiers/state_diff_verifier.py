"""State-diff verifier for write-action RL tasks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.verifiers.base import VerifierResult


class StateDiffVerifier:
    """Score final sandbox state against an opt-in expected-state subset."""

    kind = "state_diff"

    def verify(
        self,
        *,
        task_config: dict[str, Any],
        answer: str = "",
        page: Any = None,
        observed_state: dict[str, Any] | None = None,
        rollout: Any | None = None,
        trace: dict[str, Any] | None = None,
    ) -> VerifierResult:
        del answer, page
        expected = _expected_state(task_config)
        if expected is None:
            return VerifierResult.fail("missing_expected_state")
        observed = observed_state
        if observed is None:
            observed = _observed_from_trace(task_config, trace=trace, rollout=rollout)
        if observed is None:
            return VerifierResult.fail("missing_observed_state")

        matched, total = _score_subset(expected, observed)
        score = 1.0 if total == 0 else matched / total
        return VerifierResult(
            score=score,
            passed=score >= 1.0,
            details={
                "matched": matched,
                "total": total,
                "expected_state": expected,
                "observed_state": observed,
            },
        )


def _expected_state(task_config: dict[str, Any]) -> dict[str, Any] | None:
    goal = task_config.get("execution_goal") or task_config.get("state_diff") or {}
    expected = goal.get("expected_state") if isinstance(goal, dict) else None
    return dict(expected) if isinstance(expected, dict) else None


def _observed_from_trace(
    task_config: dict[str, Any],
    *,
    trace: dict[str, Any] | None = None,
    rollout: Any | None = None,
) -> dict[str, Any] | None:
    goal = task_config.get("execution_goal") or {}
    state = deepcopy(goal.get("initial_state") or {}) if isinstance(goal, dict) else {}
    source = trace if trace is not None else getattr(rollout, "trace", None)
    if not isinstance(source, dict):
        return state or None
    for row in source.get("tool_state_deltas") or []:
        delta = row.get("delta") if isinstance(row, dict) else row
        if isinstance(delta, dict):
            _apply_delta(state, delta)
    return state


def _apply_delta(state: dict[str, Any], delta: dict[str, Any]) -> None:
    if isinstance(delta.get("observed_state"), dict):
        _deep_merge(state, delta["observed_state"])
        return
    if isinstance(delta.get("state"), dict):
        _deep_merge(state, delta["state"])
        return
    result = delta.get("result") if isinstance(delta.get("result"), dict) else {}
    if isinstance(result.get("observed_state"), dict):
        _deep_merge(state, result["observed_state"])
        return

    op = str(delta.get("op") or "")
    if op == "cart_add":
        cart = state.setdefault("cart", {})
        items = cart.setdefault("items", [])
        item = dict(delta.get("item") or {})
        item.update(result.get("item") or {})
        if item:
            items.append(item)
    elif op == "order_place":
        orders = state.setdefault("orders", {})
        order_id = str(result.get("order_id") or (delta.get("order") or {}).get("order_id") or "")
        if order_id:
            orders[order_id] = {**dict(result), "status": result.get("status") or "placed"}
    elif op == "order_cancel":
        orders = state.setdefault("orders", {})
        order_id = str(result.get("order_id") or (delta.get("order") or {}).get("order_id") or "")
        if order_id:
            current = orders.setdefault(order_id, {})
            current.update(result)
            current["status"] = result.get("status") or "cancelled"


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = deepcopy(value)


def _score_subset(expected: Any, observed: Any) -> tuple[int, int]:
    if isinstance(expected, dict):
        total = 0
        matched = 0
        if not isinstance(observed, dict):
            return 0, _leaf_count(expected)
        for key, exp_value in expected.items():
            m, t = _score_subset(exp_value, observed.get(key))
            matched += m
            total += t
        return matched, total
    if isinstance(expected, list):
        if not expected:
            return 1, 1
        if not isinstance(observed, list):
            return 0, _leaf_count(expected)
        matched = 0
        total = 0
        for exp_item in expected:
            item_total = _leaf_count(exp_item)
            total += item_total
            best = 0
            for obs_item in observed:
                m, _t = _score_subset(exp_item, obs_item)
                best = max(best, m)
            matched += best
        return matched, total
    return (1, 1) if expected == observed else (0, 1)


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(v) for v in value.values()) or 1
    if isinstance(value, list):
        return sum(_leaf_count(v) for v in value) or 1
    return 1


__all__ = ["StateDiffVerifier"]
