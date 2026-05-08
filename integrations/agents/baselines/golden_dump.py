"""Golden-dump sanity baseline.

Loads the must-cite list from the golden file verbatim and emits a markdown
report with one URL per line. No reasoning, no analysis. Designed to
saturate URL coverage / reachability / must_cite_recall while collapsing
judge / analysis_depth / presentation scores.

Signature matches scripts/runners/*_runner.py:
    async def run(intent, model, shim_url, proxy_url) -> str
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"

CLAIM_TEMPLATES = [
    "claim_template_A: cited as evidence for the report topic.",
    "claim_template_B: included to satisfy the must-cite requirement.",
    "claim_template_C: source bears on the question per golden pool.",
    "claim_template_D: representative example from the sandbox corpus.",
    "claim_template_E: data point listed without further analysis.",
]


def _load_golden(task_id: str) -> dict:
    p = GOLDEN_DIR / f"{task_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _title_for(entry: dict) -> str:
    """Use 'title' or 'detail' if present, else derive from URL slug."""
    for key in ("title", "detail"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:160]
    url = entry.get("url", "")
    slug = url.rstrip("/").split("/")[-1].split("?")[0].split("#")[0]
    slug = slug.removesuffix(".html").removesuffix(".htm")
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title[:160] or url


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Dump the must-cite list verbatim, one [title](url) per line."""
    task_id = os.environ.get("_FLOWSEARCHER_TASK_ID", "")
    if not task_id:
        return "(golden_dump baseline error: _FLOWSEARCHER_TASK_ID env var not set)"

    golden = _load_golden(task_id)
    entries = golden.get("must_cite_urls", []) or []
    if not entries:
        return f"(golden_dump baseline error: no must_cite_urls for {task_id})"

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_cat[e.get("category", "other")].append(e)

    lines: list[str] = [
        f"# Sanity-GoldenDump Baseline — {task_id}",
        "",
        f"Total must-cite URLs dumped: {len(entries)}",
        "",
    ]
    n = 0
    for cat, items in by_cat.items():
        lines.append(f"## {cat.replace('_', ' ').title()} ({len(items)})")
        lines.append("")
        for e in items:
            url = e.get("url", "")
            if not url:
                continue
            title = _title_for(e)
            tmpl = CLAIM_TEMPLATES[n % len(CLAIM_TEMPLATES)]
            lines.append(f"- [{title}]({url}) — {tmpl}")
            n += 1
        lines.append("")
    return "\n".join(lines)
