"""Oracle for dr_red_0004: /f/news vs /f/worldnews engagement stats."""

from __future__ import annotations
import json
import statistics
from typing import Any

from envs.reddit.scrape import list_submissions


def _stats(subs: list[dict]) -> dict:
    scores = [s.get("score", 0) for s in subs]
    comms  = [s.get("comments", 0) for s in subs]
    return {
        "number_of_submissions": len(subs),
        "average_score":         round(statistics.fmean(scores), 2) if scores else 0.0,
        "average_comment_count": round(statistics.fmean(comms), 2) if comms else 0.0,
        "median_comment_count":  round(statistics.median(comms), 1) if comms else 0.0,
    }


def oracle(page: Any, task_cfg: dict) -> str:
    base = task_cfg["start_url"].rsplit("/f/", 1)[0]
    a = list_submissions(f"{base}/f/news", page=page)
    b = list_submissions(f"{base}/f/worldnews", page=page)
    sa, sb = _stats(a), _stats(b)
    higher = "news" if sa["median_comment_count"] >= sb["median_comment_count"] else "worldnews"
    return json.dumps(
        {
            "forums": [
                {"forum": "news", **sa},
                {"forum": "worldnews", **sb},
            ],
            "higher_median_comments": higher,
            "conclusion": (
                f"/f/{higher} shows higher median comment engagement "
                f"(median={max(sa['median_comment_count'], sb['median_comment_count'])} "
                f"vs {min(sa['median_comment_count'], sb['median_comment_count'])}) on first-page listings."
            ),
        },
        ensure_ascii=False,
    )
