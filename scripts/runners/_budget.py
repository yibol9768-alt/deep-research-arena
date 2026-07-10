"""Shared budget / no-progress policy for every DR lane.

WHY THIS MODULE EXISTS

Until 2026-07-08 every lane picked its own wall clock. Measured caps ranged
from 240s (qx-agents) to unlimited (camel-ai), with most native paths at 420s
and a few at 900/1500/1800s. That is a comparative time budget, and a
comparative time budget is unfair for two independent reasons:

  1. It punishes a lane for its BACKBONE, not its framework. A 420s cap on a
     local vLLM backbone that emits 8 tok/s aborts long before the same
     framework on an API backbone would.
  2. It cannot tell "the framework cannot converge" from "the box wedged".
     smolagents-qwen "timed out" on 6/13 tasks; the log showed a single
     128-token step taking 1206s -- the local vLLM intermittently stalling,
     not the framework diverging. Both landed in the same `timeout` cell.

Budget policy (config/lane_protocol.yaml `budget`, decided 2026-07-08):

  * No comparative wall clock. Cost is compared in TOKENS (ds_proxy usage,
    attributed by run_id), which is the cost-per-score axis.
  * One uniform no-progress watchdog: a lane that makes no LLM call and no shim
    call for `stall_timeout_s` (default 900s) is killed and recorded as
    `stalled` -- an infrastructure fault, never a framework failure, and
    rerunnable. `stalled` is a DISTINCT status from `timeout`.

This module is the single source of both numbers so run_deep_task.py and every
runner read the SAME policy. The in-code defaults below are the fallback when
lane_protocol.yaml is unreadable; the watchdog must still run in that case.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / "config" / "lane_protocol.yaml"

# Kept in sync with lane_protocol.yaml `budget:`. Used verbatim only when the
# file cannot be read, so a broken/absent config still yields a live watchdog
# rather than a silently-unbounded run.
_STALL_DEFAULT_S = 900
_WALL_DEFAULT_S: Optional[float] = None  # null == no comparative wall clock


def _coerce_none(v) -> Optional[float]:
    """Parse a wall-clock/native-timeout value, mapping 'unlimited' spellings
    to None. 0, -1, none, null, inf, empty -> None (no cap). Anything else that
    parses as a positive number is that many seconds."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"", "none", "null", "0", "-1", "inf", "unlimited", "off"}:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def load_budget() -> dict:
    """Resolve the budget policy: file defaults, then GLOBAL env overrides.

    The env overrides are deliberately not per-lane. A per-lane time budget is
    exactly the inequality this module removes; the only knobs are the two that
    apply to every lane at once.
    """
    stall: int = _STALL_DEFAULT_S
    wall: Optional[float] = _WALL_DEFAULT_S
    try:
        import yaml

        data = yaml.safe_load(_CONFIG.read_text()) or {}
        budget = data.get("budget") or {}
        if budget.get("stall_timeout_s") is not None:
            stall = int(budget["stall_timeout_s"])
        # wall_clock_s may legitimately be null -> no comparative wall clock.
        wall = _coerce_none(budget.get("wall_clock_s"))
    except Exception:
        # Missing PyYAML or unreadable file: keep the in-code defaults. Never
        # let a config error silently disable the watchdog.
        pass

    env_stall = os.environ.get("DRA_STALL_TIMEOUT_S")
    if env_stall not in (None, ""):
        try:
            stall = int(float(env_stall))
        except ValueError:
            pass
    if "DRA_WALL_CLOCK_S" in os.environ:
        wall = _coerce_none(os.environ.get("DRA_WALL_CLOCK_S"))

    return {"stall_timeout_s": stall, "wall_clock_s": wall}


# Import-time snapshot. The driver exports DRA_* / lane_protocol.yaml before the
# process starts, so a single read is correct. Callers that need a fresh read
# (e.g. a test that mutates env) can call load_budget() again.
_BUDGET = load_budget()
STALL_TIMEOUT_S: int = _BUDGET["stall_timeout_s"]
WALL_CLOCK_S: Optional[float] = _BUDGET["wall_clock_s"]


def native_timeout_default() -> Optional[float]:
    """The per-lane native self-abort wall clock, IDENTICAL for every lane.

    Equal to the (uniform) DRA_WALL_CLOCK_S: None means no native self-abort,
    and the no-progress watchdog is what terminates a wedged run. This default
    MUST be the same for all lanes -- see the module docstring for why a
    per-lane default is unfair. Each lane still honours its own
    *_NATIVE_TIMEOUT_S env for single-run debugging.
    """
    return WALL_CLOCK_S


def resolve_native_timeout(env_name: str) -> Optional[float]:
    """Read a lane's *_NATIVE_TIMEOUT_S env, else the shared default.

    Returns None for 'no native self-abort' (either the shared default is None,
    or the operator set the env to 0/none). A positive float is seconds.
    """
    raw = os.environ.get(env_name)
    if raw is None or raw.strip() == "":
        return native_timeout_default()
    return _coerce_none(raw)
