"""Oracle for dr_red_0002: top-3 by score vs top-3 by comments on /f/technology."""

from __future__ import annotations
import json
from typing import Any

from envs.reddit.scrape import list_submissions


def oracle(page: Any, task_cfg: dict) -> str:
    subs = list_submissions(task_cfg["start_url"], page=page)
    fmt = lambda s: {"title": s["title"], "score": s["score"], "comment_count": s["comments"], "permalink": s["url"]}
    by_score = sorted(subs, key=lambda s: -s["score"])[:3]
    by_comm  = sorted(subs, key=lambda s: -s["comments"])[:3]
    overlap = len({s["url"] for s in by_score} & {s["url"] for s in by_comm})
    return json.dumps(
        {
            "top_by_score":    [fmt(s) for s in by_score],
            "top_by_comments": [fmt(s) for s in by_comm],
            "overlap_count":   overlap,
        },
        ensure_ascii=False,
    )
