"""Shared pytest wiring for the test suite.

Two responsibilities:

1. The ``gates`` marker. Gate tests (G1 oracle tops out / G2 shell zeroes /
   G3 perturbation must lose) score all 100 answer keys and take minutes, so
   they are DESELECTED by default: a plain ``pytest tests/ -q`` never runs
   them. They run only via ``--run-gates`` (what ``scripts/run_gates.py``
   passes) or an explicit ``-m gates``.

2. Session fixtures the gate tests share (registry, answer-key paths, the
   optional box concept-page cache). They are lazy: a normal test run never
   touches them.

Determinism: everything here reads only committed files. No network, no
clock, no randomness.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_addoption(parser):
    parser.addoption(
        "--run-gates",
        action="store_true",
        default=False,
        help="run the slow gate tests (G1/G2/G3 full answer-key sweeps)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "gates: goal-gate test (GOAL_GATES_V1). Deselected by default; run "
        "with --run-gates or -m gates (see scripts/run_gates.py).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-gates"):
        return
    markexpr = config.getoption("markexpr", "") or ""
    if "gates" in markexpr:
        return
    deselected = [i for i in items if i.get_closest_marker("gates")]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = [i for i in items if not i.get_closest_marker("gates")]


# ---------------------------------------------------------------------------
# Gate fixtures (lazy; only gate tests request them)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def gates_repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def gates_registry():
    """The frozen-corpus UrlRegistry; a gate cannot run without it."""
    from src.eval.closed_world_eval import load_registry

    try:
        reg = load_registry()
    except Exception as exc:  # pragma: no cover - infra guard
        pytest.skip(f"url registry unavailable: {exc}")
    if not getattr(reg, "loaded", False):
        pytest.skip("url registry present but not loaded (degraded mode)")
    return reg


@pytest.fixture(scope="session")
def gates_key_paths(gates_repo_root) -> list:
    """All dr_cross_deep answer keys, sorted (deterministic order).

    ``DRA_GATES_TASK_LIMIT=N`` truncates to the first N keys so the suite can
    be tuned on a 13-task subset before the full 100-task run
    (scripts/run_gates.py --quick sets it)."""
    paths = sorted(
        (gates_repo_root / "data" / "golden" / "answer_keys").glob(
            "dr_cross_deep_*.json"))
    if not paths:
        pytest.skip("no dr_cross_deep answer keys under data/golden/answer_keys")
    try:
        limit = int(os.environ.get("DRA_GATES_TASK_LIMIT", "0") or 0)
    except ValueError:
        limit = 0
    return paths[:limit] if limit > 0 else paths


@pytest.fixture(scope="session")
def gates_concept_cache():
    """The box concept-page cache fixture in scorer shape, or None when the
    fixture has not been captured (tests then skip their concept share
    explicitly rather than fail)."""
    from src.eval.oracle_report import load_concept_cache

    return load_concept_cache()


@pytest.fixture(scope="session")
def gates_page_stats(gates_concept_cache):
    import src.eval.decidable_scorer as ds

    return ds.build_page_stats(gates_concept_cache or {})
