"""Shared scrapers for WebArena Postmill (http://localhost:9999/).

All functions take either a Playwright `Page` OR a URL string. Playwright
path uses `page.evaluate`; string path uses `requests` + regex (no JS
required — Postmill renders everything server-side).

Postmill HTML cheat sheet (verified 2026-04-16):
  - <article class="submission ...">
      <a class="submission__link" href="/f/<forum>/<id>/<slug>">TITLE</a>
      <a class="submission__submitter" href="/user/<username>">USER</a>
      <time class="submission__timestamp" datetime="ISO">
      .vote__net-score                              →   score
      .js-display-new-comments[data-comment-count]  →   N comments
  - <article class="comment ...">
      .comment__author  → author
      .comment__body    → HTML body
      .comment__time datetime="ISO"
"""

from __future__ import annotations

import json
import re
from typing import Any


REDDIT_DEFAULT = "http://localhost:9999"


def _fetch(url: str) -> str:
    """HTTP GET via requests (works where httpx 502s — see shop_adapter notes)."""
    try:
        import requests  # type: ignore
        r = requests.get(url, timeout=30, allow_redirects=True)
        return r.text if r.status_code < 400 else ""
    except Exception:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""


_SUB_RE = re.compile(r'<article[^>]*class="[^"]*submission[^"]*"[\s\S]*?</article>', re.I)
_COMMENT_RE = re.compile(r'<article[^>]*class="[^"]*comment[^"]*"[\s\S]*?</article>', re.I)


def _one_submission(block: str, base: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # submission__link title + external/internal URL
    m = re.search(r'<a\s+href="([^"]+)"[^>]*class="submission__link"[^>]*>([^<]+)</a>', block)
    if m:
        out["title"] = re.sub(r"&#039;", "'", m.group(2)).strip()
        link = m.group(1)
        # For link posts, submission__link is an external URL — preserve
        # it as `external_url` so the agent can cite it if useful.
        if link.startswith("/f/"):
            out["external_url"] = None
        else:
            out["external_url"] = link
    # The canonical comment-page URL is an internal /f/<forum>/<id>/<slug>.
    m = re.search(r'href="(/f/[A-Za-z0-9_]+/\d+/[^"]+)"', block)
    if m:
        out["url"] = base + m.group(1)
    m = re.search(r'class="submission__submitter[^"]*"[^>]*><strong>([^<]+)</strong>', block)
    if m:
        out["author"] = m.group(1).strip()
    m = re.search(r'submission__timestamp[^>]*datetime="([^"]+)"', block)
    if m:
        out["posted_at"] = m.group(1)
    m = re.search(r'data-comment-count="(\d+)"', block)
    out["comments"] = int(m.group(1)) if m else 0
    m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', block)
    out["score"] = int(m.group(1)) if m else 0
    m = re.search(r'<a[^>]+href="(/f/[A-Za-z0-9_]+)"\s+class="submission__forum', block)
    if m:
        out["forum_url"] = base + m.group(1)
        out["forum"] = m.group(1).rsplit("/", 1)[-1]
    return out


def list_submissions(forum_or_url: str, *, base: str = REDDIT_DEFAULT, page: Any = None) -> list[dict]:
    """List submissions on a forum or forum-equivalent URL.

    `forum_or_url` can be:
      - A forum slug like 'news'  →  /f/news
      - A forum path like '/f/news'
      - A full URL (including /all/hot, /f/news/new, etc.)
    """
    if "://" in forum_or_url:
        url = forum_or_url
    elif forum_or_url.startswith("/"):
        url = base + forum_or_url
    else:
        url = f"{base}/f/{forum_or_url}"
    if page is not None:
        try:
            page.goto(url)
            page.wait_for_load_state("domcontentloaded")
            html = page.content()
        except Exception:
            html = _fetch(url)
    else:
        html = _fetch(url)
    out: list[dict] = []
    for m in _SUB_RE.finditer(html or ""):
        d = _one_submission(m.group(0), base)
        if d.get("url"):
            out.append(d)
    return out


def get_submission(url_or_path: str, *, base: str = REDDIT_DEFAULT, page: Any = None) -> dict:
    """Fetch a submission detail page + extract title/score/comments/body."""
    url = url_or_path if "://" in url_or_path else base + url_or_path
    if page is not None:
        try:
            page.goto(url)
            page.wait_for_load_state("domcontentloaded")
            html = page.content()
        except Exception:
            html = _fetch(url)
    else:
        html = _fetch(url)

    out: dict[str, Any] = {"url": url}
    m = re.search(r'<h1[^>]*class="submission__title[^"]*"[^>]*>\s*<a[^>]*>([^<]+)', html or "")
    if not m:
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html or "")
    if m:
        out["title"] = re.sub(r"&#039;", "'", m.group(1)).strip()
    m = re.search(r'class="vote__net-score"[^>]*>(-?\d+)', html or "")
    out["score"] = int(m.group(1)) if m else 0
    m = re.search(r'submission__submitter[^"]*"[^>]*><strong>([^<]+)', html or "")
    if m:
        out["author"] = m.group(1).strip()
    # Post body
    body_m = re.search(r'<div[^>]*class="[^"]*submission__body[^"]*"[\s\S]*?</div>', html or "")
    out["body_html"] = body_m.group(0) if body_m else ""
    # Comments
    comments = [_one_comment(m.group(0)) for m in _COMMENT_RE.finditer(html or "")]
    out["comments"] = comments
    out["num_comments"] = len(comments)
    return out


def _one_comment(block: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = re.search(r'comment__author[^>]*>([^<]+)', block)
    if m:
        out["author"] = m.group(1).strip()
    else:
        m = re.search(r'href="/user/([^"]+)"', block)
        if m:
            out["author"] = m.group(1).strip()
    m = re.search(r'class="comment__body[^"]*"[^>]*>([\s\S]*?)</div>', block)
    if m:
        out["body"] = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
    else:
        m = re.search(r'<p>([^<]+)</p>', block)
        if m:
            out["body"] = m.group(1).strip()
    m = re.search(r'vote__net-score[^>]*>(-?\d+)', block)
    out["score"] = int(m.group(1)) if m else 0
    m = re.search(r'comment__time[^>]*datetime="([^"]+)"', block)
    if m:
        out["posted_at"] = m.group(1)
    return out


def list_user_submissions(username: str, *, base: str = REDDIT_DEFAULT, page: Any = None) -> list[dict]:
    """Return a user's recent submissions from /user/<username>/submissions."""
    return list_submissions(f"/user/{username}/submissions", base=base, page=page)


if __name__ == "__main__":
    subs = list_submissions("news")
    print(f"/f/news  has {len(subs)} submissions on first page")
    if subs:
        print("top by comments:")
        for s in sorted(subs, key=lambda x: -x["comments"])[:3]:
            print(f"  c={s['comments']:4d} s={s['score']:3d}  {s['title'][:70]}")
            print(f"  url={s['url']}")
