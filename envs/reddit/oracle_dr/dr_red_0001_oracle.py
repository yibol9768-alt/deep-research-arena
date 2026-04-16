"""Oracle for dr_red_0001: top-3 most-commented on /f/news."""

from __future__ import annotations
import json
from typing import Any

from envs.reddit.scrape import list_submissions


def oracle(page: Any, task_cfg: dict) -> str:
    subs = list_submissions(task_cfg["start_url"], page=page)
    subs.sort(key=lambda s: -s.get("comments", 0))
    top = subs[:3]
    report = {
        "posts": [
            {
                "title": s["title"],
                "comment_count": s["comments"],
                "score": s["score"],
                "permalink": s["url"],
            }
            for s in top
        ],
        "citations": [
            {"field": f"posts[{i}].comment_count", "url": s["url"]}
            for i, s in enumerate(top)
        ],
    }
    return json.dumps(report, ensure_ascii=False)
