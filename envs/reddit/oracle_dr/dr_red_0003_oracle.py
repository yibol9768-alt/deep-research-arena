"""Oracle for dr_red_0003: top-3 most-prolific authors on /f/wallstreetbets page 1."""

from __future__ import annotations
import json
from collections import defaultdict
from typing import Any

from envs.reddit.scrape import list_submissions


def oracle(page: Any, task_cfg: dict) -> str:
    subs = list_submissions(task_cfg["start_url"], page=page)
    counts: dict[str, int] = defaultdict(int)
    sample: dict[str, str] = {}
    for s in subs:
        author = s.get("author")
        if not author:
            continue
        counts[author] += 1
        sample.setdefault(author, s["url"])
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    return json.dumps(
        {
            "authors": [
                {"username": a, "submission_count": c, "sample_permalink": sample[a]}
                for a, c in ranked
            ]
        },
        ensure_ascii=False,
    )
