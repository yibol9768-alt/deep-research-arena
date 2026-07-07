"""Unit tests for the benchmark fairness gate on the shared evidence writer.

Smoke8c defect: three distinct frameworks (flowsearcher-ds, smolagents, storm)
all fell through to ``evidence_fallback.synthesize_report`` and, because the
generator is deterministic given a fixed task+shim, emitted byte-identical
21052-byte reports with 56 localhost citations each. A harness-written report
standing in for a failed framework is a fairness violation.

These tests pin the fix:
  - the generator is DISABLED by default (benchmark mode) and refuses loudly;
  - it runs only behind the explicit EVIDENCE_FALLBACK_ENABLE opt-in;
  - the honest per-lane stub has the exact shape classify_report flags as a
    stub_exception, for every lane that used to ghostwrite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.runners import evidence_fallback as ef  # noqa: E402
from src.eval.report_stubs import classify_report  # noqa: E402


# --------------------------------------------------------------------------
# The gate: disabled by default, opt-in only.
# --------------------------------------------------------------------------

def test_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)
    assert ef.fallback_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", "  On  "])
def test_fallback_enabled_only_for_explicit_truthy(monkeypatch, val):
    monkeypatch.setenv("EVIDENCE_FALLBACK_ENABLE", val)
    assert ef.fallback_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "native"])
def test_fallback_stays_off_for_falsey(monkeypatch, val):
    monkeypatch.setenv("EVIDENCE_FALLBACK_ENABLE", val)
    assert ef.fallback_enabled() is False


def test_synthesize_report_refuses_in_benchmark_mode(monkeypatch):
    # The generator must never run without the explicit flag, even if evidence
    # collection would otherwise succeed. It refuses before doing any work.
    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)

    def _boom(*a, **k):  # collect_sandbox_evidence must not even be reached
        raise AssertionError("evidence collection ran despite the benchmark gate")

    monkeypatch.setattr(ef, "collect_sandbox_evidence", _boom)
    with pytest.raises(ef.EvidenceFallbackDisabled):
        ef.synthesize_report("intent", "model", "http://s", "http://p/v1")


def test_synthesize_report_runs_when_enabled(monkeypatch):
    monkeypatch.setenv("EVIDENCE_FALLBACK_ENABLE", "1")
    monkeypatch.setenv("EVIDENCE_FALLBACK_SKIP_LLM", "1")  # deterministic path only
    monkeypatch.setattr(
        ef,
        "collect_sandbox_evidence",
        lambda *a, **k: [
            {
                "query": "q",
                "title": "Endgame thread",
                "url": "http://localhost:9999/f/headphones/126764",
                "content": "some forum text",
            }
        ],
    )
    out = ef.synthesize_report("intent", "model", "http://s", "http://p/v1")
    assert "# Source-Grounded Answer" in out
    assert "http://localhost:9999/f/headphones/126764" in out


# --------------------------------------------------------------------------
# The honest stub: exact shape, classified as stub_exception.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lane", ["smolagents", "storm", "flowsearcher"])
def test_error_stub_shape_and_classification(lane):
    stub = ef.error_stub(lane, "native", "TimeoutError: boom")
    assert stub == f"({lane} error: native: TimeoutError: boom)"
    assert classify_report(stub) == "stub_exception"


def test_error_stub_collapses_whitespace_and_caps_reason():
    stub = ef.error_stub("storm", "write", "line one\n  line   two\ttab")
    assert "\n" not in stub and "\t" not in stub
    assert stub == "(storm error: write: line one line two tab)"
    long = ef.error_stub("smolagents", "native", "x" * 500)
    assert len(long) < 260
    assert classify_report(long) == "stub_exception"


def test_error_stub_handles_empty_fields():
    stub = ef.error_stub("", "", "")
    assert stub == "(runner error: unknown: unknown)"
    assert classify_report(stub) == "stub_exception"
