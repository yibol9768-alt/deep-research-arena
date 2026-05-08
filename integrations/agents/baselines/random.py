"""Random-URL sanity baseline.

Picks 60 random must-cite URLs from the golden file for the task and emits
a ~3000-word markdown report with placeholder claims linking each URL.

Goal: should achieve high reachability and decent must_cite_recall (because
URLs are real sandbox URLs) but tank judge / analysis_depth / presentation
because the report contains no real reasoning.

Signature matches scripts/runners/*_runner.py:
    async def run(intent, model, shim_url, proxy_url) -> str
"""

from __future__ import annotations

import hashlib
import json
import os
import random as _random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"

N_URLS = 60
WORD_TARGET = 3000


def _seed_for_task(task_id: str) -> int:
    """Deterministic seed derived from the task_id."""
    h = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _load_must_cite(task_id: str) -> list[dict]:
    p = GOLDEN_DIR / f"{task_id}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("must_cite_urls", []) or []


def _proportional_sample(entries: list[dict], k: int, rng: _random.Random) -> list[dict]:
    """Sample `k` entries with category mix proportional to the source pool."""
    if not entries:
        return []
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_cat[e.get("category", "other")].append(e)

    total = len(entries)
    quotas = {c: max(1, round(k * len(v) / total)) for c, v in by_cat.items()}
    # Adjust rounding so we end up with exactly k.
    diff = k - sum(quotas.values())
    cats = list(quotas.keys())
    while diff != 0 and cats:
        c = rng.choice(cats)
        if diff > 0 and quotas[c] < len(by_cat[c]):
            quotas[c] += 1
            diff -= 1
        elif diff < 0 and quotas[c] > 0:
            quotas[c] -= 1
            diff += 1
        else:
            cats.remove(c)

    picked: list[dict] = []
    for c, q in quotas.items():
        pool = by_cat[c][:]
        rng.shuffle(pool)
        picked.extend(pool[:q])
    rng.shuffle(picked)
    return picked[:k]


def _slug_to_title(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1].split("?")[0].split("#")[0]
    slug = slug.removesuffix(".html").removesuffix(".htm")
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title[:120] or url


def _build_report(task_id: str, intent: str, picks: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"# Sanity-Random Baseline Report — {task_id}")
    lines.append("")
    lines.append(f"**Intent (truncated):** {intent[:300]}")
    lines.append("")
    lines.append("## Summary")
    lines.append(
        "This report is a sanity baseline produced by uniformly sampling "
        f"{len(picks)} URLs from the golden must-cite pool. It contains "
        "placeholder claims and is intended to probe URL-coverage and "
        "reachability metrics in isolation from reasoning quality."
    )
    lines.append("")

    # Group by category for structure.
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in picks:
        by_cat[e.get("category", "other")].append(e)

    section_n = 0
    for cat, items in by_cat.items():
        section_n += 1
        lines.append(f"## {section_n}. {cat.replace('_', ' ').title()}")
        lines.append("")
        for i, e in enumerate(items, 1):
            url = e.get("url", "")
            title = _slug_to_title(url)
            lines.append(
                f"- ({section_n}.{i}) **{title}**: this source is referenced "
                f"as evidence for the topic. Placeholder claim_{section_n}_{i}: "
                f"the cited material is treated as a baseline data point in this "
                f"automated sanity report. See [{title}]({url})."
            )
        lines.append("")

    body = "\n".join(lines)

    # Pad to roughly WORD_TARGET words by repeating a deterministic filler block.
    filler = (
        "This paragraph is sanity-baseline padding inserted to match the report "
        "word-count target without introducing additional claims or analysis. "
        "Each cited URL above is real and resolvable inside the benchmark sandbox; "
        "the absence of reasoning is intentional. "
    )
    while len(body.split()) < WORD_TARGET:
        body += "\n\n" + filler
    return body


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Pick 60 random must-cite URLs and emit a placeholder report."""
    task_id = os.environ.get("_FLOWSEARCHER_TASK_ID", "")
    if not task_id:
        return "(random baseline error: _FLOWSEARCHER_TASK_ID env var not set)"

    entries = _load_must_cite(task_id)
    if not entries:
        return f"(random baseline error: no must_cite_urls for {task_id})"

    rng = _random.Random(_seed_for_task(task_id))
    picks = _proportional_sample(entries, min(N_URLS, len(entries)), rng)
    return _build_report(task_id, intent, picks)
