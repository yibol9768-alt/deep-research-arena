"""Retarget DeerFlow's researcher from open web → our Reddit (Postmill) sandbox.

Mirrors shop_adapter.py but with Postmill-specific tools. Run as:
    REDDIT=http://localhost:9999 python reddit_adapter.py dr_red_0001
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import List

import requests
from langchain_core.tools import tool


REDDIT = os.environ.get("REDDIT", "http://localhost:9999").rstrip("/")


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        return r.text if r.status_code < 400 else ""
    except Exception as e:
        return f"ERROR: {e}"


_SUB_RE = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)


def _one_sub(block: str) -> dict:
    out: dict = {}
    m = re.search(r'<a\s+href="([^"]+)"[^>]*class="submission__link"[^>]*>([^<]+)</a>', block)
    if m:
        out["title"] = re.sub(r"&#039;", "'", m.group(2)).strip()
        link = m.group(1)
        out["external_url"] = None if link.startswith("/f/") else link
    m = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', block)
    if m:
        out["url"] = REDDIT + m.group(1)
    m = re.search(r'class="submission__submitter[^"]*"[^>]*><strong>([^<]+)', block)
    if m:
        out["author"] = m.group(1).strip()
    m = re.search(r'data-comment-count="(\d+)"', block)
    out["comments"] = int(m.group(1)) if m else 0
    m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', block)
    out["score"] = int(m.group(1)) if m else 0
    return out


@tool
def reddit_list(forum_or_url: str) -> str:
    """List submissions of a Postmill forum or page. `forum_or_url` can be a slug ('news'), a path ('/f/news', '/all/hot'), or a full URL on the sandbox. Returns JSON array of {title, url, author, comments, score}."""
    if "://" in forum_or_url:
        url = forum_or_url
    elif forum_or_url.startswith("/"):
        url = REDDIT + forum_or_url
    else:
        url = f"{REDDIT}/f/{forum_or_url}"
    html = _fetch(url)
    subs = [_one_sub(m.group(0)) for m in _SUB_RE.finditer(html or "")]
    return json.dumps({"url": url, "count": len(subs), "submissions": subs[:25]}, ensure_ascii=False)


@tool
def reddit_browse(url: str) -> str:
    """Fetch a URL on the Postmill sandbox. If it's a forum/listing page, returns the submissions. If it's a submission detail page, returns the post info + first 20 comments."""
    if "://" not in url:
        url = REDDIT + ("" if url.startswith("/") else "/") + url
    if REDDIT not in url:
        return json.dumps({"error": f"URL outside reddit domain: {url}"})
    html = _fetch(url)
    if not html:
        return json.dumps({"error": "empty response", "url": url})
    # Detail page?
    if '<h1 class="submission__title' in html or "submission__body" in html:
        out: dict = {"kind": "submission", "url": url}
        m = re.search(r'<a[^>]*class="submission__link"[^>]*>([^<]+)</a>', html)
        if m:
            out["title"] = re.sub(r"&#039;", "'", m.group(1)).strip()
        m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', html)
        out["score"] = int(m.group(1)) if m else 0
        # Comments
        comment_re = re.compile(r'<article[^>]*class="[^"]*comment[^"]*"[\s\S]*?</article>', re.I)
        comments = []
        for cm in comment_re.finditer(html):
            blk = cm.group(0)
            c: dict = {}
            am = re.search(r'comment__author[^>]*>([^<]+)|href="/user/([^"]+)"', blk)
            if am:
                c["author"] = (am.group(1) or am.group(2) or "").strip()
            bm = re.search(r'class="comment__body[^"]*"[^>]*>([\s\S]*?)</div>', blk)
            if bm:
                c["body"] = re.sub(r"<[^>]+>", " ", bm.group(1)).strip()[:400]
            sm = re.search(r'vote__net-score[^>]*>(-?\d+)', blk)
            c["score"] = int(sm.group(1)) if sm else 0
            comments.append(c)
        out["comments"] = comments[:20]
        out["num_comments"] = len(comments)
        return json.dumps(out, ensure_ascii=False)
    # Else, treat as listing
    subs = [_one_sub(m.group(0)) for m in _SUB_RE.finditer(html)]
    return json.dumps({"kind": "listing", "url": url, "count": len(subs), "submissions": subs[:25]}, ensure_ascii=False)


def install_reddit_tools() -> None:
    import src.tools.search as search_mod
    import src.tools.crawl as crawl_mod
    import src.graph.nodes as nodes_mod

    def _fake_get_web_search(*_a, **_kw):
        return reddit_list

    search_mod.get_web_search_tool = _fake_get_web_search
    nodes_mod.get_web_search_tool = _fake_get_web_search
    nodes_mod.crawl_tool = reddit_browse
    crawl_mod.crawl_tool = reddit_browse


async def run_dr_task(task_id: str):
    install_reddit_tools()

    from src.graph import build_graph
    from src.config.configuration import get_recursion_limit

    task_path = Path(__file__).resolve().parents[2] / "data" / "tasks" / "deep_research" / "reddit" / f"{task_id}.json"
    cfg = json.loads(task_path.read_text())

    prompt = (
        cfg["intent"]
        + "\n\nReport MUST be a single JSON object matching this schema:\n"
        + json.dumps(cfg["report_schema"], ensure_ascii=False, indent=2)
        + f"\n\nAll permalinks must start with {REDDIT}/ . "
          "Include a `citations` array with {field, url} entries for every "
          "numeric claim. Use reddit_list and reddit_browse tools; "
          "do NOT browse the open web."
    )

    graph = build_graph()

    initial_state = {
        "messages": [{"role": "user", "content": prompt}],
        "auto_accepted_plan": True,
        "enable_background_investigation": False,
        "research_topic": prompt,
        "clarified_research_topic": prompt,
        "enable_clarification": False,
    }
    config = {
        "configurable": {
            "thread_id": f"dr-{task_id}",
            "max_plan_iterations": 1,
            "max_step_num": 4,
            "mcp_settings": {"servers": {}},
        },
        "recursion_limit": get_recursion_limit(default=60),
    }

    final_state = None
    async for s in graph.astream(input=initial_state, config=config, stream_mode="values"):
        final_state = s
        msgs = s.get("messages") or []
        if msgs:
            last = msgs[-1]
            role = getattr(last, "type", "") or getattr(last, "role", "")
            name = getattr(last, "name", "") or ""
            content = getattr(last, "content", "")
            preview = content if isinstance(content, str) else str(content)
            print(f"\n--- [{role}/{name}] ---\n{preview[:800]}")

    if final_state:
        print("\n====== FINAL REPORT ======")
        rep = final_state.get("final_report") or final_state.get("reporter_output") or ""
        print((rep or "")[:3000])
        out = Path(__file__).resolve().parents[2] / "data" / "results" / f"deerflow_{task_id}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rep or "(no final_report)", encoding="utf-8")
        print(f"\nsaved: {out}")


if __name__ == "__main__":
    task_id = sys.argv[1] if len(sys.argv) > 1 else "dr_red_0001"
    asyncio.run(run_dr_task(task_id))
