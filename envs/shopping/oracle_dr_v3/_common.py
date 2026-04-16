"""Shared helpers for v3 shopping oracles.

v3 oracles return a long-form markdown report (≥500 words) AND, as a
side-effect, dump the (subject, predicate, object) golden triples to
`data/golden/<task_id>.json` for the fact_kg verifier.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = REPO_ROOT / "data" / "golden"


def write_golden(task_id: str, triples: list[dict]) -> None:
    """Persist KG golden triples for a task."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLDEN_DIR / f"{task_id}.json"
    out.write_text(json.dumps(triples, indent=2, ensure_ascii=False))


def md_link(text: str, url: str) -> str:
    """Return a markdown inline link, escaping any unsafe pipe / brackets."""
    safe_text = re.sub(r"[\[\]]", "", text)[:120]
    return f"[{safe_text}]({url})"


def product_id_from_url(url: str) -> str | None:
    """Best-effort extract Magento product slug or numeric id from a product URL."""
    m = re.search(r"/([a-z0-9-]+)\.html$", url or "")
    return m.group(1) if m else None


def safe_get(d: dict | None, *keys, default=None):
    cur = d or {}
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default
