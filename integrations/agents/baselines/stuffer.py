"""Single-search stuffer sanity baseline.

Hits the Tavily-compatible shim once with the intent as the query, then
concatenates the returned `content` snippets verbatim into a markdown report
with [title](url) links per result. No LLM call. The shim's results are
already routed to sandbox URLs, so reachability should be fine; coverage and
recall depend on what the shim ranks first.

Signature matches scripts/runners/*_runner.py:
    async def run(intent, model, shim_url, proxy_url) -> str
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

MAX_RESULTS = 80
WORD_FLOOR = 3500
WORD_CEILING = 7000


def _search(shim_url: str, query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    try:
        resp = requests.post(
            f"{shim_url.rstrip('/')}/search",
            json={
                "query": query,
                "api_key": os.environ.get("TAVILY_API_KEY", "tvly-shim-fake"),
                "max_results": max_results,
                "include_raw_content": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return list(resp.json().get("results", []))
    except Exception as exc:
        logger.error("stuffer shim error: %s", exc)
        return []


def _format_section(idx: int, item: dict) -> str:
    url = (item.get("url") or "").strip()
    title = (item.get("title") or url or f"result_{idx}").strip()
    content = (item.get("content") or "").strip()
    if not url:
        return ""
    header = f"### {idx}. [{title}]({url})"
    body = content if content else "(no snippet returned by shim)"
    return f"{header}\n\n{body}\n"


def _word_count(text: str) -> int:
    return len(text.split())


def _truncate_to_words(text: str, n: int) -> str:
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n])


def _pad_to_floor(text: str, floor: int, sections: Iterable[str]) -> str:
    """Repeat existing sections (verbatim) until the report meets the floor."""
    section_list = [s for s in sections if s.strip()]
    if not section_list:
        return text
    out = text
    cycle = 0
    while _word_count(out) < floor:
        cycle += 1
        out += "\n\n## Repeated snippets (cycle " + str(cycle) + ")\n\n"
        out += "\n\n".join(section_list)
        if cycle > 6:  # safety break
            break
    return out


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Single-search stuffer; pure passthrough, no LLM."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _search, shim_url, intent, MAX_RESULTS)
    if not results:
        return f"(stuffer baseline error: shim returned 0 results for intent prefix '{intent[:120]}')"

    sections = []
    for i, item in enumerate(results, 1):
        s = _format_section(i, item)
        if s:
            sections.append(s)

    head = (
        f"# Sanity-Stuffer Baseline\n\n"
        f"**Intent (truncated):** {intent[:300]}\n\n"
        f"**Source:** single Tavily-shim search, max_results={MAX_RESULTS}, "
        f"returned={len(results)}.\n\n"
        f"---\n\n"
    )
    body = "\n".join(sections)
    report = head + body

    if _word_count(report) > WORD_CEILING:
        report = _truncate_to_words(report, WORD_CEILING)
    elif _word_count(report) < WORD_FLOOR:
        report = _pad_to_floor(report, WORD_FLOOR, sections)
    return report
