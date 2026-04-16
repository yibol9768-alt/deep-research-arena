"""Oracle for dr_red_v3_0001 — /f/news vs /f/worldnews engagement."""

from __future__ import annotations

import statistics
from typing import Any

from envs.reddit.scrape import list_submissions
from ._common import write_golden, md_link


def _stats(subs: list[dict]) -> dict:
    scores = [s.get("score", 0) for s in subs]
    comms = [s.get("comments", 0) for s in subs]
    return {
        "n": len(subs),
        "avg_score":  round(statistics.fmean(scores), 2) if scores else 0,
        "avg_comments": round(statistics.fmean(comms), 2) if comms else 0,
        "median_comments": round(statistics.median(comms), 1) if comms else 0,
    }


def oracle(page: Any, task_cfg: dict) -> str:
    base = task_cfg["start_url"].rsplit("/f/", 1)[0]
    a = list_submissions(f"{base}/f/news", page=page)
    b = list_submissions(f"{base}/f/worldnews", page=page)
    sa, sb = _stats(a), _stats(b)
    a_top = sorted(a, key=lambda s: -s.get("comments", 0))[:3]
    b_top = sorted(b, key=lambda s: -s.get("comments", 0))[:3]
    higher = "/f/news" if sa["median_comments"] >= sb["median_comments"] else "/f/worldnews"
    gap = abs(sa["median_comments"] - sb["median_comments"])

    lines: list[str] = ["# /f/news vs /f/worldnews: A Comparative Engagement Analysis\n"]
    lines.append(
        "We compared the first-page engagement profile of two Postmill news communities on this server. "
        f"Both forums were sampled in their default 'Hot' ordering; we collected up to 25 submissions each "
        f"and computed average score, average comment count, and median comment count.\n"
    )

    lines.append("## Side-by-side metrics\n")
    lines.append("| Forum | n | Avg score | Avg comments | Median comments |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(f"| /f/news | {sa['n']} | {sa['avg_score']} | {sa['avg_comments']} | {sa['median_comments']} |")
    lines.append(f"| /f/worldnews | {sb['n']} | {sb['avg_score']} | {sb['avg_comments']} | {sb['median_comments']} |\n")

    triples: list[dict] = [
        {"subject": "forum:news",      "predicate": "median_comments", "object": str(sa["median_comments"])},
        {"subject": "forum:worldnews", "predicate": "median_comments", "object": str(sb["median_comments"])},
        {"subject": "forum:news",      "predicate": "avg_score", "object": str(sa["avg_score"])},
        {"subject": "forum:worldnews", "predicate": "avg_score", "object": str(sb["avg_score"])},
    ]

    lines.append(f"## Which forum has more debate?\n")
    lines.append(
        f"On median comment engagement, **{higher}** leads with a gap of {gap:.1f} comments per submission. "
        f"Median is the right yardstick here because the comment-count distribution on these subs has a long tail — "
        f"a single viral thread can drag the mean dramatically while leaving the median stable.\n"
    )

    lines.append("## Top-3 most-commented submissions per forum\n")
    lines.append("### /f/news\n")
    for s in a_top:
        lines.append(f"- {md_link(s.get('title',''), s.get('url',''))} — **{s.get('comments')}** comments, score {s.get('score')}, by {s.get('author')}")
        triples.append({"subject": s.get("title",""), "predicate": "comment_count", "object": str(s.get("comments"))})
        triples.append({"subject": s.get("title",""), "predicate": "score", "object": str(s.get("score"))})
        triples.append({"subject": s.get("title",""), "predicate": "forum", "object": "news"})
    lines.append("\n### /f/worldnews\n")
    for s in b_top:
        lines.append(f"- {md_link(s.get('title',''), s.get('url',''))} — **{s.get('comments')}** comments, score {s.get('score')}, by {s.get('author')}")
        triples.append({"subject": s.get("title",""), "predicate": "comment_count", "object": str(s.get("comments"))})
        triples.append({"subject": s.get("title",""), "predicate": "score", "object": str(s.get("score"))})
        triples.append({"subject": s.get("title",""), "predicate": "forum", "object": "worldnews"})
    lines.append("")

    lines.append("## Hypotheses for the gap\n")
    lines.append(
        "1. **Topic breadth** — /f/news leans US-domestic (politics, regional incidents) which tend to mobilize larger audiences "
        "with strong priors; /f/worldnews covers wider geography but each story competes with many parallel threads.\n"
        "2. **Audience size & overlap** — both forums share many users; the more familiar /f/news 'wins' attention by default "
        "for general visitors. Less-engaged users still upvote in both, but only the strongly-opinionated comment.\n"
    )

    lines.append("## Recommendation\n")
    lines.append(
        f"For a researcher monitoring high-debate news content on this Postmill instance, "
        f"**{higher}** is the more reliable feed: its median comment engagement gives a consistent stream of multi-comment "
        f"threads worth sampling, whereas the other forum's engagement is more skewed by occasional viral hits.\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
