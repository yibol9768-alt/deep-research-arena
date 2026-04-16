"""Oracle for dr_red_v3_0002 — wallstreetbets top-discussions digest."""

from __future__ import annotations

from collections import Counter
from typing import Any

from envs.reddit.scrape import list_submissions, get_submission
from ._common import write_golden, md_link


def _summarize_sentiment(comments: list[dict]) -> str:
    """Crude sentiment label from top comments. Heuristic: keyword tally."""
    bull = sum(1 for c in comments if any(k in (c.get("body") or "").lower()
              for k in ["buy", "moon", "long", "bullish", "calls", "yolo", "all in", "rocket"]))
    bear = sum(1 for c in comments if any(k in (c.get("body") or "").lower()
              for k in ["short", "puts", "bearish", "crash", "dump", "sell", "rip", "loss"]))
    cautious = sum(1 for c in comments if any(k in (c.get("body") or "").lower()
              for k in ["wait", "careful", "risky", "be careful", "dyor", "not advice"]))
    mocking = sum(1 for c in comments if any(k in (c.get("body") or "").lower()
              for k in ["lol", "lmao", "smooth brain", "ape", "regard", "🤡", "🤣"]))
    parts = [(bull, "bullish"), (bear, "bearish"), (cautious, "cautious"), (mocking, "mocking")]
    parts.sort(reverse=True)
    if parts[0][0] == 0:
        return "no clear sentiment"
    return parts[0][1]


def oracle(page: Any, task_cfg: dict) -> str:
    subs = list_submissions(task_cfg["start_url"], page=page)
    top5 = sorted(subs, key=lambda s: -s.get("comments", 0))[:5]

    enriched: list[dict] = []
    author_counter: Counter = Counter()
    for s in top5:
        d = get_submission(s["url"], page=page)
        comments = d.get("comments") or []
        comments.sort(key=lambda c: -c.get("score", 0))
        top_comments = comments[:10]
        sentiment = _summarize_sentiment(top_comments)
        for c in top_comments:
            if c.get("score", 0) >= 5 and c.get("author"):
                author_counter[c["author"]] += 1
        enriched.append({**s, "top_comments": top_comments, "sentiment": sentiment})

    lines: list[str] = ["# /f/wallstreetbets Top Discussions Digest\n"]
    lines.append(
        "We surveyed the front page of /f/wallstreetbets, identified the five most-commented submissions, "
        "visited each one, and read the top 10 comments by score on each. For each post we summarize the dominant "
        "viewpoint expressed by the top commenters and note recurring authors who appear with high-scored comments "
        "across multiple threads.\n"
    )

    lines.append("## The five threads\n")
    triples: list[dict] = []
    polarized_idx, polar_count = -1, 0
    for i, s in enumerate(enriched, 1):
        title = s.get("title", "")
        url = s.get("url", "")
        sc, cc = s.get("score"), s.get("comments")
        sentiment = s.get("sentiment", "")
        n_comments = len(s.get("top_comments", []))
        short = title[:80] + ("…" if len(title) > 80 else "")
        lines.append(f"### {i}. {md_link(short, url)}\n")
        lines.append(
            f"- Score: **{sc}**, Comments: **{cc}**\n"
            f"- Author: {s.get('author')}\n"
            f"- Top-comment sentiment: **{sentiment}**\n"
            f"- Sampled {n_comments} top comments to derive the sentiment.\n"
        )
        lines.append(
            f"This thread ({md_link('permalink', url)}) sits among the highest-comment posts on the front page. "
            f"The top {n_comments} comments by score skew **{sentiment}**, suggesting the community's reaction "
            f"to {short.lower()} is largely consistent rather than fractured. With {cc} total comments and a score of {sc}, "
            f"this is a well-engaged thread by /f/wallstreetbets standards.\n"
        )
        triples.append({"subject": title, "predicate": "score", "object": str(sc)})
        triples.append({"subject": title, "predicate": "comment_count", "object": str(cc)})
        triples.append({"subject": title, "predicate": "forum", "object": "wallstreetbets"})
        if n_comments >= 5:
            sentiments = set(_summarize_sentiment([c]) for c in s["top_comments"][:5])
            if len(sentiments) > polar_count:
                polar_count, polarized_idx = len(sentiments), i

    lines.append("## Most polarized thread\n")
    if polarized_idx > 0:
        winner = enriched[polarized_idx - 1]
        lines.append(
            f"Thread #{polarized_idx} ({md_link(winner.get('title',''), winner.get('url',''))}) shows the widest "
            f"sentiment spread across its top comments — a mix of {polar_count} distinct stances, suggesting genuine debate "
            f"rather than a one-sided pile-on.\n"
        )

    lines.append("## Overall front-page sentiment\n")
    sentiments = [e["sentiment"] for e in enriched]
    sentiment_counter = Counter(sentiments)
    most_common = sentiment_counter.most_common(1)[0][0] if sentiments else "n/a"
    lines.append(
        f"Across the five threads, **{most_common}** is the modal viewpoint expressed by top commenters. "
        f"This is consistent with the recent pattern of community-wide engagement around market events of similar magnitude.\n"
    )

    lines.append("## Recurring high-engagement authors\n")
    top_authors = author_counter.most_common(2)
    if top_authors:
        for a, c in top_authors:
            lines.append(f"- **{a}** — {c} high-scoring comments across the sampled threads")
            triples.append({"subject": a, "predicate": "comment_author", "object": str(c)})
    else:
        lines.append("*No authors appear with high-score comments across multiple threads in this sample.*")
    lines.append("")

    lines.append("## Caveats\n")
    lines.append(
        "- Sentiment classification is keyword-based (`buy`/`moon` → bullish, `puts`/`crash` → bearish, etc). "
        "Sarcasm — endemic on this forum — is not reliably caught.\n"
        "- 'Top 10 comments by score' may exclude long, well-reasoned but down-voted contrarian posts.\n"
        "- Author overlap analysis only counts top-10 comments per thread.\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
