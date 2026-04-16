"""Oracle for dr_red_v3_0004 — MarvelsGrantMan136 user behavior profile."""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from envs.reddit.scrape import list_user_submissions
from ._common import write_golden, md_link


def oracle(page: Any, task_cfg: dict) -> str:
    user = "MarvelsGrantMan136"
    subs = list_user_submissions(user, page=page) or []

    forum_counter: Counter = Counter(s.get("forum") for s in subs if s.get("forum"))
    top_forums = forum_counter.most_common(3)
    by_score = sorted(subs, key=lambda s: -s.get("score", 0))[:3]
    avg_score = round(statistics.fmean([s.get("score", 0) for s in subs]), 2) if subs else 0

    lines: list[str] = [f"# Posting Behavior Profile: u/{user}\n"]
    lines.append(
        f"We pulled the visible recent submissions for **u/{user}** from /user/{user}/submissions "
        f"({len(subs)} posts visible) and analyzed their cross-forum activity, top-engagement posts, "
        "and overall posting volume to characterize their behavior on this Postmill instance.\n"
    )

    lines.append("## Top forums (by submission count)\n")
    triples: list[dict] = [{"subject": user, "predicate": "author", "object": user}]
    for forum, n in top_forums:
        lines.append(f"- **/f/{forum}** — {n} submissions")
        triples.append({"subject": user, "predicate": "forum", "object": forum})
        triples.append({"subject": f"author:{user}/forum:{forum}", "predicate": "n_posts", "object": str(n)})
    if not top_forums:
        lines.append("*No forum activity visible.*")
    lines.append("")

    lines.append("## Top-3 highest-scored posts\n")
    for s in by_score:
        title, url = s.get("title",""), s.get("url","")
        sc, cc = s.get("score"), s.get("comments")
        lines.append(f"- {md_link(title, url)} — **score {sc}**, {cc} comments (in /f/{s.get('forum')})")
        triples.append({"subject": title, "predicate": "score", "object": str(sc)})
        triples.append({"subject": title, "predicate": "comment_count", "object": str(cc)})
        triples.append({"subject": title, "predicate": "forum", "object": s.get("forum","")})
    lines.append("")

    lines.append(f"## Aggregate metrics\n")
    lines.append(f"- Total visible submissions: **{len(subs)}**\n- Average score per submission: **{avg_score}**\n")
    triples.append({"subject": user, "predicate": "n_visible_submissions", "object": str(len(subs))})
    triples.append({"subject": user, "predicate": "avg_score", "object": str(avg_score)})

    # Behavior characterization
    lines.append("## Behavior profile\n")
    if forum_counter:
        diversity = len(forum_counter)
        top_share = top_forums[0][1] / max(len(subs), 1)
        if diversity >= 5 and top_share < 0.4:
            label = "**cross-forum generalist**"
            why = (f"Posts across {diversity} different forums with no single forum exceeding {int(top_share*100)}% of activity. "
                   "Behavior pattern is broad-spectrum aggregator more than topic specialist.")
        elif top_share >= 0.6:
            label = "**niche enthusiast**"
            why = (f"Concentrates {int(top_share*100)}% of activity in /f/{top_forums[0][0]}, suggesting strong topical commitment "
                   "to that community.")
        else:
            label = "**multi-forum participant**"
            why = (f"Spread across {diversity} forums with /f/{top_forums[0][0]} being the favorite ({int(top_share*100)}% of posts). "
                   "Mixes broad participation with a clear primary venue.")
        lines.append(f"u/{user} fits the profile of a {label}: {why}")
    else:
        lines.append("Insufficient activity to characterize.")
    lines.append("")

    lines.append("## Caveats\n")
    lines.append(
        "- This view is limited to the *visible recent* submissions on the user's page; deep history requires authenticated access.\n"
        "- Average score may be biased upward by Postmill's seeded score floors (often 1).\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
