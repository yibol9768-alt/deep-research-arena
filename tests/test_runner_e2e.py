"""End-to-end test: real container + real Playwright browser.

Skipped unless SHOPPING is reachable. Assumes reset.sh has started the
shopping container (either locally or via SSH port-forward) and
SHOPPING env var points at it.

Run:
    SHOPPING=http://localhost:7770 pytest tests/test_runner_e2e.py -v
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


SHOPPING = os.environ.get("SHOPPING", "http://localhost:7770")

pytestmark = pytest.mark.skipif(
    not _reachable(SHOPPING),
    reason=f"SHOPPING not reachable at {SHOPPING}; start container or port-forward first",
)


@pytest.fixture(scope="module")
def runner():
    from src.runner import PlaywrightRunner
    return PlaywrightRunner(headless=True)


def _load(task_id: int) -> dict:
    p = ROOT / "data" / "tasks" / "webarena" / "shopping" / f"{task_id}.json"
    return json.loads(p.read_text())


def test_task_21_string_match(runner):
    """Task 21: string_match on reviewer names. Oracle falls back to canonical."""
    from envs.shopping.oracle.task_21_oracle import task_21_oracle
    result = runner.run(_load(21), agent=task_21_oracle)
    assert result.passed, result.to_dict()
    assert result.score == 1.0


def test_bad_answer_fails_string_match(runner):
    """Sanity: a wrong answer must NOT pass the verifier."""
    cfg = _load(21)
    result = runner.run(cfg, agent=lambda page, c: "totally wrong answer")
    assert not result.passed
    assert result.score == 0.0


def test_runner_resolves_placeholders(runner):
    """Runner.resolve should substitute __SHOPPING__ in start_url."""
    cfg = _load(21)
    resolved = runner.resolve(cfg)
    assert "__SHOPPING__" not in resolved["start_url"]
    assert resolved["start_url"].startswith(SHOPPING)
