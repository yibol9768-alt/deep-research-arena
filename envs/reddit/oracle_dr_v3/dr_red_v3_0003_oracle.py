"""Oracle for dr_red_v3_0003 — /f/technology trending discourse themes."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Any

from envs.reddit.scrape import list_submissions
from ._common import write_golden, md_link


_THEMES = {
    "AI / language models": [r"\b(ai|llm|gpt|claude|chatgpt|openai|anthropic|gemini)\b", r"machine\s*learning|neural"],
    "Tech regulation":      [r"\b(regulation|antitrust|fcc|ftc|eu\b|congress|lawsuit|sue|court|dmca|gdpr)\b"],
    "Big-tech layoffs":     [r"\b(layoff|fire|cuts|job\s*cuts|hiring)\b"],
    "Crypto / blockchain":  [r"\b(crypto|bitcoin|ethereum|blockchain|nft|web3)\b"],
    "Consumer hardware":    [r"\b(iphone|android|samsung|pixel|laptop|chip|gpu|cpu|nvidia|amd|intel)\b"],
    "Privacy / security":   [r"\b(privacy|encryption|hack|breach|cyber|security)\b"],
    "Streaming / media":    [r"\b(netflix|disney|spotify|hulu|streaming|youtube|tiktok|twitter|x corp|meta)\b"],
}


def _classify(title: str) -> list[str]:
    n = title.lower()
    out = []
    for theme, pats in _THEMES.items():
        for p in pats:
            if re.search(p, n):
                out.append(theme)
                break
    return out


def oracle(page: Any, task_cfg: dict) -> str:
    base = task_cfg["start_url"]
    p1 = list_submissions(base, page=page)
    p2 = list_submissions(base + "?p=2", page=page)
    all_subs = p1 + p2

    by_theme: dict[str, list[dict]] = defaultdict(list)
    for s in all_subs:
        for theme in _classify(s.get("title", "")):
            by_theme[theme].append(s)

    # Keep themes with ≥2 posts
    themes_kept = [(t, group) for t, group in by_theme.items() if len(group) >= 2]
    themes_kept.sort(key=lambda kv: -len(kv[1]))
    themes_kept = themes_kept[:5]
    if len(themes_kept) < 3 and by_theme:
        # If few have ≥2, include single-post themes
        themes_kept = sorted(by_theme.items(), key=lambda kv: -len(kv[1]))[:5]

    lines: list[str] = ["# /f/technology Trending Discourse — Topic Themes Survey\n"]
    lines.append(
        f"We surveyed the first **two pages** of /f/technology on this Postmill instance ({len(all_subs)} submissions in total) "
        "and grouped titles into recurring discourse themes via keyword classification (e.g. AI, regulation, layoffs, crypto). "
        "Each theme is reported with example submissions, average score, and average comment count, so you can see at a glance "
        "which themes are simply *frequent* and which actually drive *engagement*.\n"
    )

    lines.append("## Themes by submission count\n")
    triples: list[dict] = []
    for theme, group in themes_kept:
        scores = [s.get("score", 0) for s in group]
        comms = [s.get("comments", 0) for s in group]
        avg_s = round(statistics.fmean(scores), 2) if scores else 0
        avg_c = round(statistics.fmean(comms), 2) if comms else 0
        lines.append(f"### {theme} — {len(group)} posts (avg score {avg_s}, avg comments {avg_c})\n")
        for s in group[:3]:
            lines.append(f"- {md_link(s.get('title',''), s.get('url',''))} — {s.get('comments')} comments, score {s.get('score')}")
            triples.append({"subject": s.get("title",""), "predicate": "comment_count", "object": str(s.get("comments"))})
            triples.append({"subject": s.get("title",""), "predicate": "score", "object": str(s.get("score"))})
            triples.append({"subject": s.get("title",""), "predicate": "post_title", "object": s.get("title","")})
        triples.append({"subject": f"theme:{theme}", "predicate": "n_posts", "object": str(len(group))})
        triples.append({"subject": f"theme:{theme}", "predicate": "avg_score", "object": str(avg_s)})
        triples.append({"subject": f"theme:{theme}", "predicate": "avg_comments", "object": str(avg_c)})
        lines.append("")

    # Frequency vs engagement winners
    by_count = max(themes_kept, key=lambda kv: len(kv[1]))[0] if themes_kept else "n/a"
    by_engagement = max(
        themes_kept,
        key=lambda kv: statistics.fmean([s.get("comments", 0) for s in kv[1]]) if kv[1] else 0,
    )[0] if themes_kept else "n/a"

    lines.append("## Volume vs engagement winners\n")
    lines.append(
        f"By raw submission count, **{by_count}** dominates the front pages of /f/technology — it's what people are *posting* about. "
        f"By average comments per submission, however, **{by_engagement}** drives the deepest discussion. "
        f"{'These coincide, indicating consensus interest.' if by_count == by_engagement else 'These differ — a classic case of a topic that is over-represented in posts but under-represented in actual discussion (or vice versa).'}\n"
    )

    lines.append("## Methodology and caveats\n")
    lines.append(
        "- Theme classification is keyword-regex; a title can be assigned to multiple themes if multiple keyword groups hit. "
        "This slightly inflates raw counts but keeps the analysis stable for ambiguous titles like 'AI chip cuts at Nvidia'.\n"
        "- Two pages of submissions (~50 posts) is a thin sample; broader trends would benefit from a 3-month rolling pull.\n"
        "- We ignore body text — themes derive from titles only.\n"
    )

    write_golden(task_cfg["task_id"], triples)
    return "\n".join(lines)
