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

# Where we dial a source is not who that source thinks it is.
#
# The gateway reaches Magento over the compose network as `http://shopping:80`,
# but Magento's base_url is `http://localhost:7770`. Magento answers any request
# whose Host is not its base_url with a 302 to that base_url, dropping the query
# string on the way -- and `localhost:7770` is nothing inside the container. So
# `_search_shopping` dialed, got a 302, followed it into a closed port, took the
# ConnectionError, and returned []. `if r.status_code >= 400` never fires on a
# 302, so the store never once reported that it had been asked.
#
# The store was never searched, on any stack, in the whole life of this project.
# `fact` grades price and rating claims that only the store can support, so it
# read ~0 on 99% of reports and that was written off as narrative style. Absence
# of a source and absence of an answer produced identical data.
#
# `<SOURCE>_PUBLIC` is the origin the source knows itself by: sent as `Host`, and
# used to resolve the links it emits. It defaults to the dial address, which is
# correct whenever the two coincide (as they do when running on the host).
SHOPPING_PUBLIC = os.environ.get("SHOPPING_PUBLIC", SHOPPING).rstrip("/")
REDDIT_PUBLIC = os.environ.get("REDDIT_PUBLIC", REDDIT).rstrip("/")
KIWIX_PUBLIC = os.environ.get("KIWIX_PUBLIC", KIWIX).rstrip("/")

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


def _replace_origin(url: str, base: str) -> str:
    """Return ``url``'s path/query/fragment under ``base``'s origin.

    Source pages frequently emit absolute links carrying the compose-only dial
    host.  Merely absolutising relative links is therefore insufficient: both
    forms must be normalised to the public identity before a hit reaches an
    agent or the evidence log.
    """
    src = urllib.parse.urlsplit(url)
    dst = urllib.parse.urlsplit(base)
    return urllib.parse.urlunsplit(
        (dst.scheme or "http", dst.netloc, src.path or "/", src.query, src.fragment)
    )


def _public_link(href: str, public: str) -> str:
    """Resolve a source-emitted absolute *or* relative link as public."""
    href = str(href or "").strip()
    if not href:
        return ""
    parsed = urllib.parse.urlsplit(href)
    if parsed.scheme in {"http", "https"} or href.startswith("//"):
        # Protocol-relative links have an empty scheme.  Use the public scheme
        # while replacing their compose-only netloc.
        if href.startswith("//"):
            href = f"{urllib.parse.urlsplit(public).scheme or 'http'}:{href}"
        return _replace_origin(href, public)
    return urllib.parse.urljoin(public.rstrip("/") + "/", href)


def _source_routes() -> tuple[tuple[str, str, str], ...]:
    """Current ``(source, dial, public)`` routes.

    Build this at call time rather than once at import time.  Deployments and
    tests legitimately override the six environment-derived module values.
    """
    return (
        ("shopping", SHOPPING, SHOPPING_PUBLIC),
        ("reddit", REDDIT, REDDIT_PUBLIC),
        ("wiki", KIWIX, KIWIX_PUBLIC),
    )


def route_public_url(url: str) -> tuple[str, dict[str, str], str | None]:
    """Translate a public sandbox URL to its dial address and Host header.

    The returned URL is for the transport only.  Callers must continue to use
    the original ``url`` for responses and evidence records, otherwise a
    compose service name such as ``wiki:8080`` leaks into the scored identity.
    Unknown URLs pass through unchanged so open-mode behaviour is preserved.
    """
    origin = _netloc_of(url)
    for source, dial, public in _source_routes():
        if origin not in {_netloc_of(public), _netloc_of(dial)}:
            continue
        host = _netloc_of(public)
        headers = {"Host": host} if host else {}
        return _replace_origin(url, dial), headers, source
    return url, {}, None


def _allowlist_hosts() -> frozenset[str]:
    hosts = set(_STATIC_ALLOWLIST_HOSTS)
    # Both the dial address and the public identity: a source emits links at the
    # origin it knows itself by, and the agent must be allowed to open those.
    for base in (SHOPPING, REDDIT, KIWIX,
                 SHOPPING_PUBLIC, REDDIT_PUBLIC, KIWIX_PUBLIC):
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
    # Every forum named by a formal v2 task must be searchable.  The previous
    # list omitted seven of the ten task-declared boards, so agents were asked
    # for BuyItForLife, food, camera and keyboard experience through a tool
    # that could never return those sources.  The extra general boards remain
    # available for open-ended queries.  No `videogames`: that board is absent
    # from the frozen corpus.
    "technology,headphones,LifeProTips,personalfinance,gaming,news,science,askreddit,"
    "BuyItForLife,gadgets,food,iphone,consoles,pics,MechanicalKeyboards",
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
# Per-source diagnostics
# ---------------------------------------------------------------------------
#
# Every source searcher used to `return []` on a 4xx, a timeout, or a selector
# that stopped matching. A dead source and a source with no results for this
# query produced the same empty list, so the shim served a two-source sandbox
# while reporting a three-source one.
#
# It happened. Across 140 scored reports of the 13-task subset, ZERO citations
# point at the store, on any port. `fact` grades price and rating claims about
# store entities, so it read 0 on 99% of reports and everyone called it "the
# cost of decidability". The store was simply never reached.
#
# `last_source_diag` records, for the most recent `search()` in this process,
# why each source returned what it returned. `search_with_diagnostics` hands it
# to the caller so the shim can stamp it onto the run's evidence log: an empty
# source is now a fact in the data, not an absence in the data.
import threading as _threading

# Per-thread, not global. The shim serves requests from a threadpool, and a
# module-level dict lets one request read another's diagnostics: a search that
# queried only the wiki reads back "shopping is down" from a concurrent search
# that queried all three. Reproduced, so this is thread-local.
_DIAG = _threading.local()


def _diag_store() -> dict[str, dict]:
    d = getattr(_DIAG, "sources", None)
    if d is None:
        d = {}
        _DIAG.sources = d
    return d


def last_source_diag() -> dict[str, dict]:
    return {k: dict(v) for k, v in _diag_store().items()}


def _set_diag(source: str, n: int, error: str | None = None) -> None:
    _diag_store()[source] = {"n_results": n, "error": error}


# ---------------------------------------------------------------------------
# Shopping (Magento catalogsearch)
# ---------------------------------------------------------------------------

def _get_source(
    source: str,
    base: str,
    public: str,
    path: str,
    *,
    params: dict | None = None,
    timeout: int = 20,
) -> requests.Response | None:
    """Dial `base`, present `public` as Host, and never leave the origin.

    A redirect that stays on the origin is normal: the forum canonicalises
    `/f/<name>/new.atom` and answers 302 with a relative Location. Those are
    followed, bounded.

    A redirect that LEAVES the origin means the source does not recognise the
    address we dialled and is sending us to the one it does. That is a
    configuration fault, and the body behind it is a redirect stub with no
    content. `requests` follows such a redirect by default, straight into a port
    that is closed on the compose network, and the `except` returns `[]` --
    which is what hid the store for the life of the project. So it is reported,
    never followed and never silently emptied.
    """
    headers = {}
    host = _netloc_of(public)
    if host and host != _netloc_of(base):
        headers["Host"] = host

    origins = {_netloc_of(base), _netloc_of(public)} - {""}
    url = f"{base}{path}"
    for _hop in range(4):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers=headers, allow_redirects=False)
        except Exception as e:  # noqa: BLE001
            _set_diag(source, 0, f"{type(e).__name__}: {e} ({base})")
            return None

        if not (300 <= r.status_code < 400):
            break

        loc = r.headers.get("location", "")
        nxt = urllib.parse.urljoin(url, loc) if loc else ""
        if not nxt or _netloc_of(nxt) not in origins:
            _set_diag(source, 0,
                      f"HTTP {r.status_code} from {base} -> {loc or '(no Location)'}; "
                      f"the source does not answer to Host "
                      f"{host or _netloc_of(base)!r}. Set {source.upper()}_PUBLIC "
                      "to the origin it knows itself by.")
            return None
        url, params = nxt, None   # Location already carries the query string
    else:
        _set_diag(source, 0, f"redirect loop from {base}{path}")
        return None

    if r.status_code >= 400:
        _set_diag(source, 0, f"HTTP {r.status_code} from {base}")
        return None
    return r


def _search_shopping(query: str, max_results: int) -> list[SearchHit]:
    r = _get_source("shopping", SHOPPING, SHOPPING_PUBLIC,
                    f"/catalogsearch/result/?q={urllib.parse.quote(query)}")
    if r is None:
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
        # Always expose the public identity.  Magento can emit either relative
        # links or absolute links carrying the compose-only dial host.
        href = _public_link(a.get("href") or "", SHOPPING_PUBLIC)
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
    "bluetooth": ["headphones", "technology", "MechanicalKeyboards", "gadgets"],
    "noise":      ["headphones", "technology"],
    "audio":      ["headphones", "technology"],
    "office":     ["LifeProTips", "personalfinance"],
    "chair":      ["LifeProTips", "personalfinance"],
    "desk":       ["LifeProTips", "personalfinance", "technology", "BuyItForLife"],
    "budget":     ["LifeProTips", "personalfinance"],
    "money":      ["personalfinance", "LifeProTips"],
    "spend":      ["personalfinance", "LifeProTips"],
    "save":       ["personalfinance", "LifeProTips"],
    "cook":       ["LifeProTips", "personalfinance"],
    "kitchen":    ["food", "BuyItForLife", "LifeProTips"],
    "game":       ["gaming"],
    "pc":         ["gaming", "technology"],
    "gaming":     ["gaming"],
    "monitor":    ["gaming", "technology"],
    "keyboard":   ["MechanicalKeyboards", "gaming"],
    "mechanical": ["MechanicalKeyboards"],
    "console":    ["consoles", "gaming"],
    "camera":     ["pics", "gadgets"],
    "photo":      ["pics", "gadgets"],
    "phone":      ["gadgets", "iphone", "technology"],
    "iphone":     ["iphone", "gadgets"],
    "watch":      ["gadgets", "iphone", "technology"],
    "coffee":     ["food", "BuyItForLife"],
    "tea":        ["food", "BuyItForLife"],
    "food":       ["food"],
    "snack":      ["food"],
    "chocolate":  ["food"],
    "luggage":    ["BuyItForLife"],
    "carry-on":   ["BuyItForLife"],
    "backpack":   ["BuyItForLife"],
    "shoe":       ["BuyItForLife"],
    "boot":       ["BuyItForLife"],
    "durable":    ["BuyItForLife"],
    "durability": ["BuyItForLife"],
    "grinder":    ["food", "BuyItForLife"],
    "burr":       ["food", "BuyItForLife"],
    "zipper":     ["BuyItForLife"],
    "wheel":      ["BuyItForLife"],
    "anc":        ["headphones", "technology"],
    "earbud":     ["headphones", "technology"],
    "earphone":   ["headphones", "technology"],
    "speaker":    ["headphones", "technology"],
    "headband":   ["headphones", "technology"],
    "wired":      ["headphones", "technology"],
    "cable":      ["headphones", "technology", "BuyItForLife"],
    "switch":     ["MechanicalKeyboards", "gaming"],
    "membrane":   ["MechanicalKeyboards", "gaming"],
    "layout":     ["MechanicalKeyboards", "gaming"],
    "arrow":      ["MechanicalKeyboards", "gaming"],
    "silent":     ["MechanicalKeyboards"],
    "dampen":     ["MechanicalKeyboards"],
    "screen":     ["gadgets", "iphone", "technology"],
    "display":    ["gadgets", "iphone", "technology"],
    "oled":       ["gadgets", "iphone", "technology"],
    "lcd":        ["gadgets", "iphone", "technology"],
    "flagship":   ["gadgets", "iphone", "technology"],
    "espresso":   ["food", "BuyItForLife"],
    "arabica":    ["food", "BuyItForLife"],
    "robusta":    ["food", "BuyItForLife"],
    "decaf":      ["food", "BuyItForLife"],
    "caffeine":   ["food", "BuyItForLife"],
    "decaffeination": ["food", "BuyItForLife"],
    "sugar":      ["food"],
    "candy":      ["food"],
    "sweetener":  ["food"],
    "vacuum":     ["BuyItForLife", "food"],
    "jug":        ["BuyItForLife", "food"],
    "flask":      ["BuyItForLife", "food"],
    "steel":      ["BuyItForLife", "food"],
    "insulated":  ["BuyItForLife", "food"],
    "drinkware":  ["BuyItForLife", "food"],
    "bpa":        ["BuyItForLife", "food"],
    "knife":      ["BuyItForLife", "food"],
    "damascus":   ["BuyItForLife", "food"],
    "chef":       ["BuyItForLife", "food"],
    "induction":  ["BuyItForLife", "food"],
    "cooktop":    ["BuyItForLife", "food"],
    "kettle":     ["BuyItForLife", "food"],
    "cooker":     ["BuyItForLife", "food"],
    "ceramic":    ["BuyItForLife", "food"],
    "mug":        ["BuyItForLife", "food"],
    "lamp":       ["BuyItForLife", "technology"],
    "led":        ["BuyItForLife", "technology"],
    "light":      ["BuyItForLife", "technology"],
    "bulb":       ["BuyItForLife", "technology"],
    "fixture":    ["BuyItForLife", "technology"],
    "dimmable":   ["BuyItForLife", "technology"],
    "brightness": ["BuyItForLife", "technology"],
    "lumen":      ["BuyItForLife", "technology"],
    "sneaker":    ["BuyItForLife"],
    "leather":    ["BuyItForLife"],
    "footwear":   ["BuyItForLife"],
    "bag":        ["BuyItForLife", "technology"],
    "travel":     ["BuyItForLife", "technology"],
    "commute":    ["BuyItForLife", "technology"],
    "standing":   ["BuyItForLife", "technology"],
    "ergonomic":  ["BuyItForLife", "technology"],
    "pen":        ["BuyItForLife", "technology"],
    "writing":    ["BuyItForLife", "technology"],
    "wobble":     ["BuyItForLife", "technology"],
    "warranty":   ["BuyItForLife", "technology"],
    "chair":      ["BuyItForLife", "technology"],
    "seat":       ["BuyItForLife", "technology"],
    "strap":      ["gadgets", "iphone", "technology"],
    "wrist":      ["gadgets", "iphone", "technology"],
    "wearable":   ["gadgets", "iphone", "technology"],
    "battery":    ["gadgets", "iphone", "technology"],
    "heart-rate": ["gadgets", "iphone", "technology"],
    "rugged":     ["gadgets", "iphone", "technology", "BuyItForLife"],
    "charger":    ["gadgets", "iphone", "technology"],
    "enthusiast": ["gadgets", "pics", "technology"],
    "controller": ["consoles", "gaming", "technology"],
    "stick":      ["consoles", "gaming", "technology"],
    "hall-effect": ["consoles", "gaming", "technology"],
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


def _search_reddit_index(query: str, max_results: int) -> list[SearchHit]:
    """Search the full frozen Postmill index, not only 25 recent posts.

    Postmill's ``/search?q=`` page returns every matching submission in ranked
    order.  The old shim scanned ``new.atom`` for a small forum list, which made
    almost the entire forum corpus unreachable and silently omitted seven of
    ten boards declared by v2 tasks.  Parse canonical thread links from the
    full index first; recent feeds remain only a fallback.
    """
    q_lower = (query or "").lower()
    # Split hyphenated phrases into their semantic terms. Keeping
    # ``membrane-to-mechanical`` as one token prevented relaxation to the
    # searchable domain word ``mechanical``.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", q_lower)
    variants = [query]
    # Postmill combines search terms with AND. Agent-generated focused queries
    # often add one over-specific adjective, turning a rich forum corpus into
    # zero rows. Probe at most four deterministic topic-term variants; scoring
    # below still requires overlap with the original query.
    token_set = set(tokens)
    matched_hints = [
        kw for kw in _QUERY_FORUM_HINTS
        if kw in token_set or ("-" in kw and kw in q_lower)
    ]
    matched_hints.sort(key=lambda kw: (
        tokens.index(kw) if kw in token_set else len(tokens), q_lower.find(kw)
    ))
    generic = {"which", "what", "whether", "with", "from", "that", "this",
               "into", "only", "real", "good", "best", "first", "after",
               "before", "plus", "one", "tiny", "normal"}
    relax_terms = (([" ".join(matched_hints[:2])]
                    if len(matched_hints) >= 2 else [])
                   + matched_hints + sorted(
        {t for t in tokens if t not in generic and t not in matched_hints},
        key=lambda t: (-len(t), t),
    ))
    for candidate in relax_terms:
        if candidate and candidate not in variants:
            variants.append(candidate)
        if len(variants) >= 5:
            break

    soups = []
    for candidate in variants:
        r = _get_source("forum", REDDIT, REDDIT_PUBLIC, "/search",
                        params={"q": candidate}, timeout=30)
        if r is None:
            continue
        parsed = BeautifulSoup(r.text, "html.parser")
        if parsed.select_one("article.submission") is not None:
            soups.append(parsed)
    if not soups:
        return []
    hinted = {f.casefold() for f in _forums_hinted_by_query(query)}
    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    for soup in soups:
        for article in soup.select("article.submission"):
            thread_href = ""
            forum = ""
            for a in article.select("a[href]"):
                href = a.get("href") or ""
                m = re.match(r"^/f/([^/]+)/(\d+)(?:/|$)", href)
                if m:
                    thread_href = href
                    forum = urllib.parse.unquote(m.group(1))
                    break
            if not thread_href:
                continue
            title_el = (article.select_one("a.submission__link")
                        or article.select_one(".submission__title"))
            title = title_el.get_text(" ", strip=True) if title_el else ""
            body_el = article.select_one(".submission__body")
            body = body_el.get_text(" ", strip=True) if body_el else ""
            if not title and not body:
                continue
            tok_score = _score_reddit(query, title, body)
            if tok_score <= 0.0:
                continue
            public_url = _public_link(thread_href, REDDIT_PUBLIC)
            if public_url in seen_urls:
                continue
            seen_urls.add(public_url)
            bonus = 0.1 if forum.casefold() in hinted else 0.0
            score = min(1.0, 0.55 + 0.45 * tok_score + bonus)
            hits.append(SearchHit(
                url=public_url,
                title=f"r/{forum}: {title or 'Discussion'}",
                content=(body or title)[:600],
                score=score,
                source="reddit",
                raw_content=(body or title),
            ))
    hits.sort(key=lambda h: -h.score)
    return hits[:max_results]


def _search_reddit(query: str, max_results: int) -> list[SearchHit]:
    """Full-index retrieval with recent-feed fallback for sparse queries."""
    hinted = _forums_hinted_by_query(query)
    hits: list[SearchHit] = _search_reddit_index(query, max_results)

    def _iter_forum(forum: str, bonus: float) -> None:
        r = _get_source("forum", REDDIT, REDDIT_PUBLIC,
                        f"/f/{forum}/new.atom", timeout=15)
        if r is None:
            return
        for entry_m in _ATOM_ENTRY_RE.finditer(r.text):
            entry = entry_m.group(1)
            def _grab(field: str) -> str:
                m = _FIELD_RE[field].search(entry)
                return _strip_html(m.group(1)) if m else ""
            title = _grab("title")
            link = _FIELD_RE["link"].search(entry)
            # Atom feeds vary between relative links and absolute links carrying
            # the service origin.  Neither form may leak the dial identity.
            url = _public_link(link.group(1) if link else "", REDDIT_PUBLIC)
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

    # Only consult feeds when the full index returned fewer rows than requested.
    if len(hits) < max_results:
        for forum in hinted:
            _iter_forum(forum, bonus=0.5)
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
    params = {"pattern": query, "books.name": KIWIX_BOOK, "pageLength": max_results}
    r = _get_source("wiki", KIWIX, KIWIX_PUBLIC, "/search", params=params)
    if r is None:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    hits: list[SearchHit] = []
    # Result items are <li>..<a href="..."><cite>..snippet</cite></a>..</li>
    for i, li in enumerate(soup.select("ul.results li, .results li")):
        a = li.select_one("a[href]")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = _public_link(a.get("href") or "", KIWIX_PUBLIC)
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

    _diag_store().clear()
    if want_shopping:
        hits = _search_shopping(query, max_results)
        if hits:
            _set_diag("shopping", len(hits))
        elif "shopping" not in last_source_diag():
            _set_diag("shopping", 0, None)   # queried, genuinely no match
        results.extend(hits)
    if want_reddit:
        hits = _search_reddit(query, max_results)
        # Keep the first transport error if one was recorded: a forum that
        # refused the connection is a different fact from a forum with no match.
        prev = last_source_diag().get("forum", {})
        _set_diag("forum", len(hits), prev.get("error"))
        results.extend(hits)
    if want_wiki:
        hits = _search_kiwix(query, max_results)
        if hits:
            _set_diag("wiki", len(hits))
        elif "wiki" not in last_source_diag():
            _set_diag("wiki", 0, None)
        results.extend(hits)

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


def _navigable_links(node, page_url: str, *, cap: int = 300) -> list[str]:
    """Absolute http(s) URLs an agent could follow from `node`.

    Resolves relative hrefs against `page_url` (Kiwix `../A/X`, Postmill `/f/x`
    are relative), drops non-navigational schemes (mailto/javascript/#anchor),
    dedupes preserving order, and caps the count so a link-farm page cannot
    bloat the evidence log. These are stored on the fetch record so the scorer
    classifies an on-page-link citation as `linked` (honest navigation) instead
    of `hallucinated_grounding`.
    """
    out: list[str] = []
    seen: set[str] = set()
    for a in node.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
            continue
        absu = urllib.parse.urljoin(page_url, href)
        if not absu.startswith(("http://", "https://")):
            continue
        if absu in seen:
            continue
        seen.add(absu)
        out.append(absu)
        if len(out) >= cap:
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
            dial_url, headers, routed_source = route_public_url(url)
            r = requests.get(
                dial_url,
                timeout=20,
                headers=headers,
                allow_redirects=not strict,
            )
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
            # Capture navigable links from the SAME node the agent is shown
            # (main), BEFORE get_text() discards every <a href>. Relative Kiwix/
            # Postmill hrefs are resolved to absolute sandbox URLs. Without this
            # the served blob is stripped text with zero URLs, so a real page the
            # agent reached by following an on-page link would be scored
            # `hallucinated_grounding` (a false accusation). Captured from `main`
            # rather than the whole document because that is exactly the content
            # returned to the agent; nav/header/footer were decomposed and are
            # not part of what it could navigate from this extract. See
            # FETCH_PATH_AUDIT_2026-07-08.md.
            entry["links"] = _navigable_links(main, url) if main else []
            text = main.get_text(" ", strip=True) if main else ""
            entry["raw_content"] = text[:20000]
            h1 = soup.select_one("h1")
            if h1:
                entry["title"] = h1.get_text(strip=True)
            entry["source"] = routed_source or (
                "shopping" if "localhost:7770" in url or "magento" in url else (
                    "reddit" if "localhost:9999" in url or "reddit" in url else (
                    "wiki" if "localhost:8090" in url or "wikipedia" in url else "other")
                )
            )
            entry["elapsed_ms"] = int((time.time() - t0) * 1000)
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        out.append(entry)
    return out
