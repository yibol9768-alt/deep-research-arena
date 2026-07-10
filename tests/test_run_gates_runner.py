"""Runner-logic tests for scripts/run_gates.py.

These pin the runner's status mapping, not the gate contents. Deterministic:
subprocess is stubbed, no pytest is actually spawned.
"""

from __future__ import annotations

from scripts import run_gates


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_rc5_no_tests_collected_is_fail_not_skip(monkeypatch):
    """A gate mounted on a specific file that collects 0 tests is a BAD state
    (empty/renamed file), not a skip. Old code mapped rc=5 -> SKIP, letting a
    silently-emptied gate pass green; it must now FAIL."""
    monkeypatch.setattr(run_gates.subprocess, "run",
                        lambda *a, **k: _Proc(5, stdout="no tests ran"))
    status, detail = run_gates.run_gate(
        "G1", ["tests/test_gate_oracle.py::nonexistent"], [])
    assert status == "FAIL"
    assert "0 tests" in detail or "no tests collected" in detail


def test_rc0_is_pass(monkeypatch):
    monkeypatch.setattr(run_gates.subprocess, "run",
                        lambda *a, **k: _Proc(0, stdout="2 passed"))
    status, _ = run_gates.run_gate("G1", ["tests/x.py"], [])
    assert status == "PASS"


def test_rc1_is_fail(monkeypatch):
    monkeypatch.setattr(run_gates.subprocess, "run",
                        lambda *a, **k: _Proc(1, stdout="1 failed", stderr="boom"))
    status, _ = run_gates.run_gate("G1", ["tests/x.py"], [])
    assert status == "FAIL"


# --- preflight gates-smoke (GOAL_GATES_V1 permanent fixture) ----------------

def test_gates_smoke_passes_on_the_real_tree():
    """The goal-gate suite must be collectible and non-empty on the committed
    tree, so run_full_leaderboard.sh's `run_gates.py --quick` entry gate has
    something to run."""
    from scripts.preflight import check_gates_smoke
    results = check_gates_smoke()
    assert len(results) == 1
    assert results[0].ok is True, results[0].detail


def test_gates_smoke_fails_when_no_gate_nodes_are_declared(monkeypatch):
    """A GATES table with only non-pytest gates (nothing to collect) is a bad
    state the smoke check must catch."""
    from scripts import preflight
    monkeypatch.setattr(run_gates, "GATES",
                        {"G5": ("box-only", None, "box preflight")})
    results = preflight.check_gates_smoke()
    assert results[0].ok is False
    assert "no pytest gate nodes" in results[0].detail
