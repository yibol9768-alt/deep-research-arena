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
