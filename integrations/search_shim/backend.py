"""Sandbox query backend — translates free-text queries into Magento
catalogsearch + Postmill forum fetches and returns a unified list of
SearchHit dicts. Schema-specific adapters (Tavily, Firecrawl) then wrap
these hits in their respective response envelopes.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup


SHOPPING = os.environ.get("SHOPPING", "http://localhost:7770").rstrip("/")
REDDIT = os.environ.get("REDDIT", "http://localhost:9999").rstrip("/")
KIWIX = os.environ.get("KIWIX", "http://localhost:8090").rstrip("/")
KIWIX_BOOK = os.environ.get("KIWIX_BOOK", "wikipedia_en_all_nopic")

# ---------------------------------------------------------------------------
# Strict-mode allowlist (closed-book contract enforcement)
# ---------------------------------------------------------------------------
#
# In strict mode (SHIM_MODE=strict) fetches must never leave the sandbox.
# app.py validates the *requested* URL via its own _url_is_sandbox gate, but
# that pre-fetch check is bypassed when a sandbox page 30x-redirects off
# origin and requests follows the redirect (allow_redirects=True). To close
# that hole, extract() must (a) not follow redirects and (b) re-validate the
# final response URL against the same allowlist before returning content.
#
# The host:port set mirrors app.SHIM_ALLOWLIST_HOSTS. It is kept self
# contained here (rather than importing app) so the backend has no dependency
# on the FastAPI layer and importing it has no side effects. It is also
# extended with the netlocs of the configured SHOPPING/REDDIT/KIWIX bases so
# the gate tracks whatever sandbox origins this process is actually pointed
# at.
_STATIC_ALLOWLIST_HOSTS: tuple[str, ...] = (
    "localhost:7770", "localhost:8090", "localhost:9999", "localhost:8081",
    "127.0.0.1:7770", "127.0.0.1:8090", "127.0.0.1:9999", "127.0.0.1:8081",
)


def _netloc_of(base: str) -> str:
    p = urllib.parse.urlparse(base)
    host = (p.hostname or "").lower()
    try:
        port = p.port
    except (ValueError, TypeError):
        port = None
    return f"{host}:{port}" if port else host


def _allowlist_hosts() -> frozenset[str]:
    hosts = set(_STATIC_ALLOWLIST_HOSTS)
    for base in (SHOPPING, REDDIT, KIWIX):
        n = _netloc_of(base)
        if n:
            hosts.add(n)
    return frozenset(hosts)


SHIM_ALLOWLIST_HOSTS: frozenset[str] = _allowlist_hosts()


def _shim_strict_mode() -> bool:
    """Return True when SHIM_MODE=strict. Read at call time so callers/tests
    can toggle the mode via the environment without reimporting."""
    return os.environ.get("SHIM_MODE", "open").strip().lower() == "strict"


def _url_is_sandbox(url: str) -> bool:
    """Strict host:port equality check against `SHIM_ALLOWLIST_HOSTS`.

    Mirrors app._url_is_sandbox: substring matching is unsafe (it admits
    http://localhost:77703/leak and userinfo tricks), so we parse the URL and
    compare host:port netlocs exactly.
    """
    if not url:
        return False
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    try:
        port = p.port
    except (ValueError, TypeError):
        port = None
    netloc = f"{host}:{port}" if port else host
    for allowed in SHIM_ALLOWLIST_HOSTS:
        a = allowed.lower()
        if ":" in a:
            if netloc == a:
                return True
        elif host == a:
            return True
    return False

# Reddit forums we search by default. Overridable via env.
_DEFAULT_REDDIT_FORUMS = os.environ.get(
    "SHIM_REDDIT_FORUMS",
    "technology,headphones,LifeProTips,personalfinance,gaming,videogames,news,science,askreddit",
).split(",")


@dataclass
class SearchHit:
    """Canonical internal hit record. Framework-specific endpoints wrap
    these in their own response envelope."""

    url: str
    title: str
    content: str  # short snippet shown in search results
    score: float  # 0-1, naive; used for ordering
    source: str  # "shopping" | "reddit"
    raw_content: str | None = None  # full markdown, if requested


# ---------------------------------------------------------------------------
# Shopping (Magento catalogsearch)
# ---------------------------------------------------------------------------

def _search_shopping(query: str, max_results: int) -> list[SearchHit]:
    url = f"{SHOPPING}/catalogsearch/result/?q={urllib.parse.quote(query)}"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code >= 400:
            return []
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    hits: list[SearchHit] = []
    for i, el in enumerate(
        soup.select("li.item.product.product-item, .products-grid .product-item")[: max_results * 3]
    ):
        a = el.select_one("a.product-item-link, .product-item-name a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href") or ""
        if not href.startswith("http"):
            href = f"{SHOPPING}{'' if href.startswith('/') else '/'}{href}"
        price = None
        p_el = el.select_one("[data-price-amount]")
        if p_el and p_el.get("data-price-amount"):
            try:
                price = float(p_el["data-price-amount"])
            except Exception:
                pass
        rating = None
        r_el = el.select_one("[title]")
        if r_el:
            m = re.search(r"(\d+)%", r_el.get("title") or "")
            if m:
                rating = int(m.group(1)) / 20
        parts: list[str] = []
        if price is not None:
            parts.append(f"${price:.2f}")
        if rating is not None:
            parts.append(f"rated {rating:.1f}/5")
        snippet = f"{title}. " + " · ".join(parts) if parts else title
        hits.append(SearchHit(
            url=href, title=title, content=snippet,
            score=max(0.0, 1.0 - i / max_results),
            source="shopping",
        ))
        if len(hits) >= max_results:
            break
    return hits


# ---------------------------------------------------------------------------
# Reddit (Postmill Atom feeds, filtered in-memory)
# ---------------------------------------------------------------------------

_ATOM_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_FIELD_RE = {
    "title": re.compile(r"<title[^>]*>(.*?)</title>", re.S),
    "link": re.compile(r'<link[^>]*href="([^"]+)"'),
    "summary": re.compile(r"<(?:summary|content)[^>]*>(.*?)</(?:summary|content)>", re.S),
    "updated": re.compile(r"<updated>([^<]+)</updated>"),
}


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _score_reddit(query: str, title: str, summary: str) -> float:
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", query)]
    if not tokens:
        return 0.0
    hay = (title + " " + summary).lower()
    hits = sum(1 for t in tokens if t in hay)
    return hits / len(tokens)


_QUERY_FORUM_HINTS = {
    # Topic keywords → forums that likely have relevant posts. Used to
    # include forum's top-recent posts even when per-post token overlap
    # is zero (matching real Tavily behaviour of including reddit posts
    # liberally for consumer-research queries).
    "headphone": ["headphones", "technology"],
    "bluetooth": ["headphones", "technology"],
    "noise":      ["headphones", "technology"],
    "audio":      ["headphones", "technology"],
    "office":     ["LifeProTips", "personalfinance"],
    "chair":      ["LifeProTips", "personalfinance"],
    "desk":       ["LifeProTips", "personalfinance"],
    "budget":     ["LifeProTips", "personalfinance"],
    "money":      ["personalfinance", "LifeProTips"],
    "spend":      ["personalfinance", "LifeProTips"],
    "save":       ["personalfinance", "LifeProTips"],
    "cook":       ["LifeProTips", "personalfinance"],
    "kitchen":    ["LifeProTips", "personalfinance"],
    "game":       ["gaming", "videogames"],
    "pc":         ["gaming", "technology"],
    "gaming":     ["gaming", "videogames"],
    "monitor":    ["gaming", "technology"],
}


def _forums_hinted_by_query(query: str) -> list[str]:
    q = query.lower()
    out: list[str] = []
    for kw, forums in _QUERY_FORUM_HINTS.items():
        if kw in q:
            for f in forums:
                if f not in out:
                    out.append(f)
    return out


def _search_reddit(query: str, max_results: int) -> list[SearchHit]:
    """Two-tier retrieval:
      (a) Forums hinted by query topic → take top-recent posts with a
          strong score bump even if per-post tokens don't overlap the
          query. This models how Tavily returns reddit posts for
          consumer-research queries even with thin lexical match.
      (b) All default forums → standard token-overlap scoring.
    Results are then sorted by score and capped at `max_results`.
    """
    hinted = _forums_hinted_by_query(query)
    hits: list[SearchHit] = []

    def _iter_forum(forum: str, bonus: float) -> None:
        try:
            r = requests.get(f"{REDDIT}/f/{forum}/new.atom", timeout=15)
            if r.status_code >= 400:
                return
        except Exception:
            return
        for entry_m in _ATOM_ENTRY_RE.finditer(r.text):
            entry = entry_m.group(1)
            def _grab(field: str) -> str:
                m = _FIELD_RE[field].search(entry)
                return _strip_html(m.group(1)) if m else ""
            title = _grab("title")
            link = _FIELD_RE["link"].search(entry)
            url = link.group(1) if link else ""
            if url and not url.startswith("http"):
                url = REDDIT + ("" if url.startswith("/") else "/") + url
            summary = _grab("summary")[:600]
            tok_score = _score_reddit(query, title, summary)
            score = min(1.0, tok_score + bonus)
            # Require GENUINE topical overlap. A hinted-forum bonus alone must
            # not inject zero-overlap off-topic posts (e.g. r/headphones threads
            # surfacing for a coffee query). The bonus only re-ranks posts that
            # actually match the query; it never includes irrelevant ones. If a
            # topic has no matching forum content in the corpus, return fewer
            # reddit hits rather than off-topic noise.
            if tok_score <= 0.0:
                continue
            hits.append(SearchHit(
                url=url, title=f"r/{forum}: {title}",
                content=summary[:300],
                score=score,
                source="reddit",
            ))

    # Hinted forums get a big recall bonus so they always show up
    for forum in hinted:
        _iter_forum(forum, bonus=0.5)
    # All default forums score on merit
    for forum in _DEFAULT_REDDIT_FORUMS:
        forum = forum.strip()
        if not forum or forum in hinted:
            continue
        _iter_forum(forum, bonus=0.0)

    # Dedupe by URL (hinted iteration may overlap)
    seen: set[str] = set()
    out: list[SearchHit] = []
    for h in sorted(hits, key=lambda h: -h.score):
        if h.url in seen:
            continue
        seen.add(h.url)
        out.append(h)
        if len(out) >= max_results:
            break
    return out


# ---------------------------------------------------------------------------
# Unified entry point + extract
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Wikipedia (kiwix) search
# ---------------------------------------------------------------------------

def _search_kiwix(query: str, max_results: int) -> list[SearchHit]:
    """Kiwix returns HTML for /search; parse result list."""
    url = f"{KIWIX}/search"
    params = {"pattern": query, "books.name": KIWIX_BOOK, "pageLength": max_results}
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code >= 400:
            return []
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    hits: list[SearchHit] = []
    # Result items are <li>..<a href="..."><cite>..snippet</cite></a>..</li>
    for i, li in enumerate(soup.select("ul.results li, .results li")):
        a = li.select_one("a[href]")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href") or ""
        if not href.startswith("http"):
            href = f"{KIWIX}{href if href.startswith('/') else '/' + href}"
        snippet_el = li.select_one("cite") or li.select_one("p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else title
        hits.append(SearchHit(
            url=href, title=title, content=snippet[:400],
            score=max(0.0, 1.0 - i / max_results),
            source="wiki",
        ))
        if len(hits) >= max_results:
            break
    return hits


def search(
    query: str,
    *,
    max_results: int = 10,
    include_domains: Iterable[str] = (),
    exclude_domains: Iterable[str] = (),
) -> list[SearchHit]:
    include = {d.lower() for d in include_domains}
    exclude = {d.lower() for d in exclude_domains}

    results: list[SearchHit] = []

    want_shopping = (not include) or any(d in {"shopping", "localhost:7770", "magento"} for d in include)
    want_reddit = (not include) or any(d in {"reddit", "localhost:9999", "postmill", "reddit.com"} for d in include)
    want_wiki = (not include) or any(d in {"wiki", "wikipedia", "wikipedia.org", "localhost:8090", "kiwix"} for d in include)

    if want_shopping:
        results.extend(_search_shopping(query, max_results))
    if want_reddit:
        results.extend(_search_reddit(query, max_results))
    if want_wiki:
        results.extend(_search_kiwix(query, max_results))

    # Exclude filter
    if exclude:
        results = [h for h in results if not any(d in h.url.lower() for d in exclude)]

    # Dedupe by URL
    seen: set[str] = set()
    out: list[SearchHit] = []
    for h in sorted(results, key=lambda h: -h.score):
        if h.url in seen:
            continue
        seen.add(h.url)
        out.append(h)
        if len(out) >= max_results:
            break
    return out


def extract(urls: Iterable[str], *, strict: bool | None = None) -> list[dict]:
    """Fetch full page content for `urls`. Returns list of
    {url, raw_content, title, source, status}.

    In strict mode (``strict=True``, or ``strict=None`` with
    ``SHIM_MODE=strict``) redirects are NOT followed and the final response
    URL is re-validated against the sandbox allowlist. This closes the hole
    where a sandbox page returns a 301/302 to an off-allowlist host: with
    allow_redirects=True the pre-fetch gate in app.py is bypassed because it
    only sees the requested (pre-redirect) URL. A blocked redirect is
    reported as a failed row (status preserved, error set, no raw_content) so
    no off-allowlist content is ever returned.
    """
    if strict is None:
        strict = _shim_strict_mode()
    out = []
    for url in urls:
        entry = {"url": url, "raw_content": "", "title": "", "source": "", "status": 0}
        try:
            t0 = time.time()
            r = requests.get(url, timeout=20, allow_redirects=not strict)
            entry["status"] = r.status_code
            if r.status_code >= 400:
                out.append(entry)
                continue
            if strict:
                # allow_redirects=False above means a 3xx is returned as-is
                # (with no body to parse). Treat any redirect, or a final URL
                # that left the allowlist, as a block so off-allowlist content
                # never leaks through the closed-book contract.
                if 300 <= r.status_code < 400 or not _url_is_sandbox(str(r.url)):
                    entry["error"] = "non_sandbox_redirect_blocked"
                    entry["raw_content"] = ""
                    out.append(entry)
                    continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Strip noisy nodes
            for sel in soup.select("script, style, nav, header, footer"):
                sel.decompose()
            # Prefer product-info-main / submission__body / main article
            main = (
                soup.select_one(".product-info-main, .product.info.detailed")
                or soup.select_one(".submission, .submission__body, article")
                or soup.select_one("main")
                or soup.body
            )
            text = main.get_text(" ", strip=True) if main else ""
            entry["raw_content"] = text[:20000]
            h1 = soup.select_one("h1")
            if h1:
                entry["title"] = h1.get_text(strip=True)
            entry["source"] = "shopping" if "localhost:7770" in url or "magento" in url else (
                "reddit" if "localhost:9999" in url or "reddit" in url else (
                "wiki" if "localhost:8090" in url or "wikipedia" in url else "other")
            )
            entry["elapsed_ms"] = int((time.time() - t0) * 1000)
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        out.append(entry)
    return out
