"""Trivial oracle for `url_match` shopping tasks.

For these tasks, the only success criterion is that `page.url` matches
`eval.reference_url`. The oracle therefore just navigates the already-open
page to that URL and returns an empty answer.

This is effectively the upper-bound agent — any real agent that succeeds
must end up at the same URL (via search / click chains). We use this to
smoke-test the full runner pipeline:

    task.json → compose up → Playwright → oracle → URLVerifier → score=1.0

Usage (from runner):
    runner.run(task_cfg, agent=url_match_oracle)
"""

from __future__ import annotations

from typing import Any


def url_match_oracle(page: Any, task_cfg: dict) -> str:
    """Navigate to reference_url and return empty answer."""
    ref_url = (task_cfg.get("eval") or {}).get("reference_url", "")
    if ref_url:
        page.goto(ref_url)
    return ""
