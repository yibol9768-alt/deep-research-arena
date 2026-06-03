"""Regression test for the codex_runner stdout-fallback bug.

Bug: when codex fails to write the report file, the runner fell back to the raw
merged ``2>&1`` stdout stream (chain-of-thought, tool-call logs, curl output,
error traces) and returned it as if it were a research report. That dump
frequently exceeds 600 chars and echoes sandbox URLs from curl tool calls, so it
slipped past the leaderboard's degenerate filter and polluted analysis_depth /
presentation / URL coverage scoring and the Bradley-Terry/Elo computation.

Fix: the fallback now prefixes the recognized ``(codex produced no report after
Ns, exit=N)`` marker so ``_looks_degenerate`` / ``is_degenerate_answer``
reliably exclude it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.runners.codex_runner import (  # noqa: E402
    _degenerate_marker,
    _wrap_stdout_fallback,
)
from scripts.build_deep_leaderboard import _RUNNER_FAILURE_PREFIX_RE  # noqa: E402


# A realistic merged 2>&1 stdout dump: long, full of sandbox URLs echoed from
# curl tool calls, no real report. Pre-fix this passed every leaderboard filter.
_FAKE_STDOUT = (
    "thinking: I should search the shim for relevant products...\n"
    "$ curl -s -X POST http://localhost:8081/search -d '{\"query\":\"laptop\"}'\n"
    "{\"results\":[{\"url\":\"http://localhost:7770/catalog/product/view/id/42\"}]}\n"
    "$ curl -s -L 'http://localhost:7770/catalog/product/view/id/42' | head -c 8000\n"
    "<html>...sandbox page body...</html>\n"
    "error: write tool denied: path outside workspace\n"
) * 20  # well over 600 chars


def test_fake_stdout_alone_would_not_be_caught():
    """Sanity: the bare stdout dump is exactly what the old filter missed."""
    assert len(_FAKE_STDOUT) > 600
    # No recognized marker at the head -> filter would NOT flag it.
    assert not _RUNNER_FAILURE_PREFIX_RE.match(_FAKE_STDOUT.lstrip())


def test_wrapped_fallback_has_recognized_marker():
    wrapped = _wrap_stdout_fallback(_FAKE_STDOUT, elapsed_s=123.0, returncode=1)
    # Marker is the leading line and matches the leaderboard's failure regex.
    assert _RUNNER_FAILURE_PREFIX_RE.match(wrapped.lstrip())
    # Original stdout is preserved for debugging.
    assert "sandbox page body" in wrapped


def test_degenerate_marker_format_matches_regex():
    # Includes None (timeout/defensive) and a negative signal code (-9 on
    # POSIX). The leaderboard regex needs exit=\d+, so both must be normalized
    # to a recognized non-negative code.
    for rc in (0, 1, 137, None, -9):
        marker = _degenerate_marker(7.4, rc)
        assert _RUNNER_FAILURE_PREFIX_RE.match(marker), marker


def test_looks_degenerate_drops_wrapped_fallback(tmp_path):
    """End-to-end: a score row whose answer is the wrapped fallback is dropped."""
    from scripts.build_deep_leaderboard import _looks_degenerate

    wrapped = _wrap_stdout_fallback(_FAKE_STDOUT, elapsed_s=900.0, returncode=137)
    ans = tmp_path / "answer.md"
    ans.write_text(wrapped, encoding="utf-8")

    # Mimic a score row that otherwise looks "healthy" (long answer, some URL
    # reachability) so only the marker-based check can catch it.
    score = {
        "answer_chars": len(wrapped),
        "answer_path": str(ans),
        "url_reachability": {"score": 0.5, "details": {}},
        "checklist": {"pass_rate": 0.3},
    }
    assert _looks_degenerate(score) is True


def test_looks_degenerate_keeps_real_report(tmp_path):
    """Control: a genuine report (no marker) is NOT dropped."""
    from scripts.build_deep_leaderboard import _looks_degenerate

    real = (
        "# Research Report\n\n"
        "This is a genuine report citing "
        "[a product](http://localhost:7770/catalog/product/view/id/42).\n"
    ) * 30
    ans = tmp_path / "answer.md"
    ans.write_text(real, encoding="utf-8")
    score = {
        "answer_chars": len(real),
        "answer_path": str(ans),
        "url_reachability": {"score": 0.8, "details": {}},
        "checklist": {"pass_rate": 0.6},
    }
    assert _looks_degenerate(score) is False
