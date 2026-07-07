"""Regression test guarding the B1 excision (fairness audit 2026-07-06).

Bug removed here: ``_run_ii_researcher`` in :mod:`scripts.run_deep_task` used
to build a subprocess driver that, after the ii-researcher framework produced
its report, GRAFTED real shim search-result Wikipedia URLs onto bare title
mentions in the finished text (``out = out.replace(...)`` style injection). A
single injected reachable localhost URL flipped ``grounding_gate`` from 0.1 to
1.0 (a 10x multiplier on the truth-gated headline). That is harness-manufactured
grounding, not agent grounding.

The excision keeps URL COLLECTION (``_collected_urls``) as DIAGNOSTICS ONLY:
the collected URLs must never be written back into the report. This test pins
that contract at the source level, since the driver is emitted as an inline
string literal by ``_run_ii_researcher`` (there is no separate pure builder to
call). If a future edit re-introduces the graft, this test fails.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

# Make the repo root importable regardless of pytest invocation cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_deep_task as rdt  # noqa: E402


def _ii_driver_source() -> str:
    """Full source of the ii-researcher runner, including the driver string."""
    return inspect.getsource(rdt._run_ii_researcher)


def test_ii_driver_contains_no_url_graft():
    """The emitted driver must not inject collected URLs back into the report."""
    src = _ii_driver_source()

    # The canonical graft pattern the audit removed.
    assert "out = out.replace" not in src, (
        "B1 regression: ii-researcher driver re-introduced the "
        "`out = out.replace(...)` citation graft."
    )

    # Any other shape that mutates the report `out` in place is also banned.
    banned_patterns = [
        r"\bout\s*\+=",          # out += ...
        r"\bout\s*=\s*out\s*\+",  # out = out + ...
        r"\bout\s*=\s*out\.",     # out = out.<anything>(...)
    ]
    for pat in banned_patterns:
        assert not re.search(pat, src), (
            f"B1 regression: ii-researcher driver mutates the report `out` "
            f"(matched {pat!r}); the saved report must be the framework's own "
            f"output verbatim."
        )

    # The old graft narration marker must be gone.
    assert "Injected" not in src, (
        "B1 regression: ii-researcher driver mentions 'Injected' URLs again."
    )


def test_ii_driver_collects_urls_diagnostics_only():
    """URL collection stays present but is append-only (never fed into `out`)."""
    src = _ii_driver_source()

    # Collection is still wired (so we are actually guarding the live seam).
    assert "_collected_urls" in src, (
        "expected ii-researcher driver to still collect search URLs for "
        "diagnostics; the guard is meaningless if collection was deleted."
    )

    # Every reference to the collection list is either its declaration or an
    # append. It must never be read into the report body (e.g. joined onto out).
    for line in src.splitlines():
        if "_collected_urls" not in line:
            continue
        assert (
            "_collected_urls = []" in line
            or "_collected_urls.append(" in line
            or "collected for DIAGNOSTICS" in line  # explanatory comment line
        ), f"unexpected use of _collected_urls (possible graft): {line.strip()!r}"


def test_ii_driver_report_is_framework_output():
    """`out` is derived solely from the framework result, not post-processed."""
    src = _ii_driver_source()
    # The report must be assembled from the framework's own result fields.
    assert "result.get('final_report')" in src or 'result.get("final_report")' in src, (
        "expected ii-researcher driver to take the report from the framework "
        "result (final_report/answer)."
    )
