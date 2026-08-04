"""Sandbox query backend: translates free-text queries into Magento
catalogsearch + Postmill forum fetches and returns a unified list of
SearchHit dicts. Schema-specific adapters (Tavily, Firecrawl) then wrap
these hits in their respective response envelopes.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from math import log
from typing import Iterable

import requests
from bs4 import BeautifulSoup


SHOPPING = os.environ.get("SHOPPING", "http://localhost:7770").rstrip("/")
REDDIT = os.environ.get("REDDIT", "http://localhost:9999").rstrip("/")
KIWIX = os.environ.get("KIWIX", "http://localhost:8090").rstrip("/")
KIWIX_BOOK = os.environ.get("KIWIX_BOOK", "wikipedia_en_all_nopic")
# Kiwix's first full-text lookup after an idle period is measurably slower than
# the other corpus services.  On my5090 a healthy cold query took 15.75s on the
# host; the same lookup crossed the old 20s deadline when launched by the
# trusted formal-run supervisor.  Give this source explicit cold-start
# headroom while keeping the timeout bounded and operator-configurable.
KIWIX_SEARCH_TIMEOUT_S = max(
    1, int(os.environ.get("KIWIX_SEARCH_TIMEOUT_S", "45") or "45")
)
KIWIX_RESULTS_PER_CONCEPT = max(
    1, int(os.environ.get("KIWIX_RESULTS_PER_CONCEPT", "1") or "1")
)
REDDIT_FEED_TIMEOUT_S = max(
    1, int(os.environ.get("REDDIT_FEED_TIMEOUT_S", "5") or "5")
)
REDDIT_FEED_FALLBACK_LIMIT = max(
    1, int(os.environ.get("REDDIT_FEED_FALLBACK_LIMIT", "4") or "4")
)
SEARCH_MIN_RELATIVE_SCORE = min(
    1.0,
    max(0.0, float(os.environ.get("SEARCH_MIN_RELATIVE_SCORE", "0.08") or "0.08")),
)

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
    score: float  # 0-1 lexical relevance after source-local reranking
    source: str  # "shopping" | "reddit" | "wiki"
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
    def candidates_for(retrieval_query: str) -> list[SearchHit]:
        r = _get_source(
            "shopping",
            SHOPPING,
            SHOPPING_PUBLIC,
            f"/catalogsearch/result/?q={urllib.parse.quote(retrieval_query)}",
        )
        if r is None:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        hits: list[SearchHit] = []
        # Magento's own rank is only a candidate generator. Pull a wider window
        # and apply the same exact-token/IDF gate used for forum and wiki.
        candidate_cap = max(max_results * 5, 20)
        for el in soup.select(
            "li.item.product.product-item, .products-grid .product-item"
        )[:candidate_cap]:
            a = el.select_one("a.product-item-link, .product-item-name a")
            if not a:
                continue
            title = a.get_text(strip=True)
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
                url=href,
                title=title,
                content=snippet,
                score=0.0,
                source="shopping",
            ))
        return hits

    variants = _shopping_query_variants(query)
    ranked_groups: list[list[SearchHit]] = []
    for retrieval_query in variants:
        candidates = candidates_for(retrieval_query)
        ranked = _rerank_hits(retrieval_query, candidates, max_results)
        if len(variants) > 1:
            ranked = [
                hit for hit in ranked
                if not _product_variant_conflicts(retrieval_query, hit)
            ]
        if ranked:
            ranked_groups.append(ranked)
            continue

        # A store can match a category through fields absent from the rendered
        # grid.  Trust Magento's candidate order only for one unambiguous topic
        # term. Multi-term queries still require lexical evidence.
        profile = _query_profile(retrieval_query)
        if (
            len(variants) == 1
            and len(profile.terms) == 1
            and len(profile.anchors) == 1
        ):
            denominator = max(1, min(len(candidates), max_results))
            ranked_groups.append([
                dataclass_replace(
                    hit,
                    score=round(max(0.01, 1.0 - index / denominator), 6),
                )
                for index, hit in enumerate(candidates[:max_results])
            ])

    if len(variants) == 1:
        return ranked_groups[0] if ranked_groups else []

    # Multi-item query: one result per named item before taking a second result
    # for any item.  This prevents the first easy product family from consuming
    # the entire result budget.
    out: list[SearchHit] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < max_results and any(
        depth < len(rows) for rows in ranked_groups
    ):
        for rows in ranked_groups:
            if depth >= len(rows):
                continue
            hit = rows[depth]
            if hit.url in seen:
                continue
            seen.add(hit.url)
            out.append(hit)
            if len(out) >= max_results:
                break
        depth += 1
    return out


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


_LEXICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# These words are useful instructions to a search engine, but poor evidence
# that a returned document is about the user's subject.  Treating them like
# product/model terms is what admitted baby-budget, iPhone-battery and machine-
# learning-comparison pages into audio queries.
_STOP_TERMS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "before", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "give",
    "has", "have", "how", "i", "in", "into", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "please", "should", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "to",
    "under", "use", "using", "was", "we", "what", "when", "where",
    "whether", "which", "who", "why", "will", "with", "would", "you",
    "your",
})

_WEAK_QUERY_TERMS = frozenset({
    "amazon", "best", "budget", "buy", "cheap", "compare", "comparison",
    "current", "detail", "find", "full", "good", "latest", "listing",
    "model", "new", "official", "page", "price", "problem", "product",
    "quality", "recommendation", "review", "shop", "spec", "specification",
    "technical", "test", "website",
})

_BROAD_DOMAIN_TERMS = frozenset({
    "audio", "battery", "bluetooth", "device", "driver", "headphone",
    "portable", "sound", "speaker", "waterproof", "wireless",
})

# Product-list queries are not one bag of words.  A task such as
# "resistance bands yoga mat dumbbell foam roller" names four independent
# retrieval targets.  Sending the whole sentence to Magento and then accepting
# any card that happens to cover three tokens admitted headbands, flip-flops and
# hair rollers.  These are semantic item heads, used only to split an explicit
# multi-item query into short, reviewable lexical searches.  They do not invent
# a product that the caller did not name.
_PRODUCT_ITEM_HEADS = frozenset({
    "accessory", "adapter", "bag", "band", "bean", "bed", "blanket", "book",
    "bottle", "brewer", "bulb", "cable", "camera", "case", "chair", "charger",
    "cleaner", "clothing", "controller", "converter", "cooker", "cushion",
    "desk", "dumbbell", "earbud", "filter", "flask", "grinder",
    "headphone", "kettle", "keyboard", "kit", "lamp", "light", "lighting",
    "mat", "monitor", "mouse", "mug", "organizer", "pan", "pen", "phone",
    "powerbank", "roller", "rope", "serum", "shoe", "speaker", "stand",
    "storage", "supplement", "table", "tool", "toy", "tripod", "vacuum",
})

_PRODUCT_CONTEXT_TERMS = frozenset({
    "beginner", "budget", "category", "cheap", "compare", "comparison",
    "equipment", "essential", "fitness", "gear", "home", "item", "office",
    "outdoor", "product", "recommendation", "setup", "starter", "under",
})

_PRODUCT_HEAD_CONFLICTS: dict[str, frozenset[str]] = {
    "band": frozenset({"headband", "wristband"}),
    "dumbbell": frozenset({"poster", "shirt", "tank", "tee"}),
    "mat": frozenset({"flip", "flop", "sandal", "shoe", "slipper"}),
    "roller": frozenset({"curler", "curling", "hair"}),
}

_CONCEPT_INTENT_CUES = frozenset({
    "concept", "definition", "explain", "explainer", "meaning", "mechanism",
    "overview", "principle", "standard", "theory", "what",
})

_COMMERCE_INTENT_CUES = frozenset({
    "amazon", "buy", "listing", "price", "product", "rating", "review", "shop",
    "store",
})

_COMMUNITY_INTENT_CUES = frozenset({
    "community", "complaint", "experience", "forum", "owner", "reddit", "user",
})

# Capitalisation is a useful model/brand signal in agent-generated queries, but
# publisher and search-site names must not become mandatory document identity.
_IDENTITY_EXCLUSIONS = frozenset({
    "aac", "amazon", "aptx", "cnet", "eq", "google", "ldac", "manual",
    "official", "pdf", "reddit", "rms", "rtings", "sbc", "soundguys",
    "thd", "usb", "website", "wikipedia", "wirecutter", "youtube",
})

_COMPARISON_CUES = frozenset({
    "compare", "compared", "comparing", "comparison", "versus", "vs",
})
_COMPARISON_SEPARATORS = frozenset({
    "against", "and", "compare", "compared", "comparing", "comparison", "or",
    "versus", "vs", "with",
})

_TERM_ALIASES = {
    "batteries": "battery",
    "codecs": "codec",
    "degrees": "degree",
    "drivers": "driver",
    "headphones": "headphone",
    "radiators": "radiator",
    "reviews": "review",
    "speakers": "speaker",
    "specifications": "specification",
    "specs": "specification",
    "wattage": "watt",
    "watts": "watt",
}


def _normalise_term(raw: str) -> str:
    term = raw.casefold()
    if term in _TERM_ALIASES:
        return _TERM_ALIASES[term]
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if (len(term) > 4 and term.endswith("s")
            and not term.endswith(("is", "ss", "us"))):
        return term[:-1]
    return term


def _lexical_tokens(text: str) -> list[str]:
    """Boundary-aware terms; never let ``anc`` match ``performance``."""
    return [
        _normalise_term(raw)
        for raw in _LEXICAL_TOKEN_RE.findall(text or "")
        if raw
    ]


def _shopping_query_variants(query: str) -> tuple[str, ...]:
    """Split an explicit multi-item shopping query into short noun phrases.

    The splitter is intentionally lexical and conservative.  It activates only
    when at least two distinct product heads are present and the query carries
    no named/model identity.  Exact product queries therefore retain their
    current strict identity behaviour.
    """
    profile = _query_profile(query)
    if profile.identity_groups:
        return (query,)

    terms = _lexical_tokens(query)
    positions = [
        index for index, term in enumerate(terms)
        if term in _PRODUCT_ITEM_HEADS
    ]
    if len({terms[index] for index in positions}) < 2:
        return (query,)

    variants: list[str] = []
    for index in positions:
        head = terms[index]
        phrase = [head]
        cursor = index - 1
        while cursor >= 0 and len(phrase) < 3:
            term = terms[cursor]
            if term in _STOP_TERMS or term in _WEAK_QUERY_TERMS:
                break
            if term in _PRODUCT_CONTEXT_TERMS:
                break
            # A preceding item head normally starts the previous target.  The
            # one useful exception is a compound ending in a role noun, such as
            # "desk converter" or "camera bag".
            if term in _PRODUCT_ITEM_HEADS:
                if head in {"accessory", "adapter", "bag", "case", "converter",
                            "kit", "organizer", "stand"}:
                    phrase.insert(0, term)
                    cursor -= 1
                    continue
                break
            phrase.insert(0, term)
            cursor -= 1
        value = " ".join(phrase)
        if value not in variants:
            variants.append(value)

    return tuple(variants) if len(variants) >= 2 else (query,)


def _product_variant_conflicts(retrieval_query: str, hit: SearchHit) -> bool:
    """Reject obvious lexical homonyms for a decomposed product target."""
    terms = _lexical_tokens(retrieval_query)
    if not terms:
        return False
    conflicts = _PRODUCT_HEAD_CONFLICTS.get(terms[-1], frozenset())
    if not conflicts:
        return False
    title_terms = set(_lexical_tokens(hit.title))
    return bool(title_terms & conflicts)


def _concept_only_intent(query: str) -> bool:
    """Whether a query asks for canonical explanation rather than products."""
    terms = set(_lexical_tokens(query))
    concept = bool(terms & _CONCEPT_INTENT_CUES)
    commerce = bool(terms & _COMMERCE_INTENT_CUES)
    community = bool(terms & _COMMUNITY_INTENT_CUES)
    return concept and not commerce and not community


def _unique_in_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _term_weight(term: str) -> float:
    if term in _STOP_TERMS:
        return 0.0
    if term.isdigit():
        return 0.20
    if term in _WEAK_QUERY_TERMS:
        return 0.25
    if term in _BROAD_DOMAIN_TERMS:
        return 0.65
    if any(ch.isdigit() for ch in term):
        return 1.60
    return min(1.40, 1.0 + max(0, len(term) - 6) * 0.05)


@dataclass(frozen=True)
class _QueryProfile:
    terms: tuple[str, ...]
    weights: dict[str, float]
    anchors: tuple[str, ...]
    named_identity: tuple[str, ...]
    coded_identity: tuple[str, ...]
    identity_groups: tuple[tuple[str, ...], ...]
    phrases: tuple[tuple[str, ...], ...]


def _query_profile(query: str) -> _QueryProfile:
    raw_terms = _LEXICAL_TOKEN_RE.findall(query or "")
    normalised = [_normalise_term(raw) for raw in raw_terms]
    terms = _unique_in_order(
        term for term in normalised if _term_weight(term) > 0.0
    )
    weights = {term: _term_weight(term) for term in terms}
    anchors = tuple(
        term for term in terms
        if term not in _WEAK_QUERY_TERMS and not term.isdigit()
    )

    def identity_term(raw: str, term: str) -> str | None:
        if (term in _STOP_TERMS or term in _WEAK_QUERY_TERMS
                or term in _BROAD_DOMAIN_TERMS
                or term in _IDENTITY_EXCLUSIONS):
            return None
        has_alpha = any(ch.isalpha() for ch in term)
        has_digit = any(ch.isdigit() for ch in term)
        # IP ratings are technical requirements, not product/model identity.
        # Keep watt/model/ASIN tokens such as 40W, X30 and B08KCX841R.
        if (has_alpha and has_digit and len(term) >= 3
                and not re.fullmatch(r"ipx\d+", term)):
            return term
        if len(raw) >= 3 and (raw.isupper() or raw[:1].isupper()):
            return term
        return None

    comparison_mode = any(term in _COMPARISON_CUES for term in normalised)
    # "A or B" is also a genuine alternate-product query when both sides carry
    # identity. It is intentionally narrower than treating every "with" as a
    # comparison, which would split normal feature phrases.
    comparison_mode = comparison_mode or "or" in normalised
    raw_segments: list[list[tuple[str, str]]] = [[]]
    for raw, term in zip(raw_terms, normalised):
        if comparison_mode and term in _COMPARISON_SEPARATORS:
            if raw_segments[-1]:
                raw_segments.append([])
            continue
        raw_segments[-1].append((raw, term))

    identity_groups: list[tuple[str, ...]] = []
    for segment in raw_segments:
        group = _unique_in_order(
            identity
            for raw, term in segment
            if (identity := identity_term(raw, term)) is not None
        )
        if group:
            identity_groups.append(group)

    all_identity = _unique_in_order(
        identity for group in identity_groups for identity in group
    )
    named = tuple(
        term for term in all_identity
        if not (any(ch.isalpha() for ch in term)
                and any(ch.isdigit() for ch in term))
    )
    coded = tuple(term for term in all_identity if term not in named)

    phrases: list[tuple[str, ...]] = []
    for size in (3, 2):
        for start in range(0, max(0, len(normalised) - size + 1)):
            phrase = tuple(normalised[start:start + size])
            if any(t in _STOP_TERMS for t in phrase):
                continue
            if all(t in _WEAK_QUERY_TERMS or t.isdigit() for t in phrase):
                continue
            if sum(_term_weight(t) for t in phrase) < 1.3:
                continue
            phrases.append(phrase)

    return _QueryProfile(
        terms=terms,
        weights=weights,
        anchors=_unique_in_order(anchors),
        named_identity=named,
        coded_identity=coded,
        identity_groups=tuple(identity_groups),
        phrases=tuple(dict.fromkeys(phrases)),
    )


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    return any(tuple(tokens[i:i + size]) == phrase
               for i in range(0, len(tokens) - size + 1))


def _passes_relevance_gate(
    profile: _QueryProfile,
    document_terms: set[str],
    *,
    phrase_match: bool = False,
) -> bool:
    """Reject rows admitted solely by a generic term.

    Identity-bearing queries are strict about the named model/brand. Otherwise
    two topic anchors (three for a very broad task sentence) are required. A
    genuinely one-word query still works; the shim cannot infer missing context.
    """
    if not profile.terms:
        return False
    named_identity = set(profile.named_identity)
    coded_identity = set(profile.coded_identity)

    def group_matches(group: tuple[str, ...]) -> bool:
        named = [term for term in group if term in named_identity]
        coded = [term for term in group if term in coded_identity]
        named_hits = sum(term in document_terms for term in named)
        coded_hits = sum(term in document_terms for term in coded)
        if len(named) >= 2:
            # Full multi-token product identity, e.g. Soundcore Flare or
            # Anker Soundcore Flare. Property/model codes may be absent from a
            # compact result card once this identity is exact.
            return named_hits == len(named)
        if len(named) == 1:
            # A brand alone is not enough when the query supplies a model/value
            # discriminator such as Ortizan 40W or Ortizan B08KCX841R.
            return named_hits == 1 and (not coded or coded_hits >= 1)
        return bool(coded) and coded_hits >= 1

    if profile.identity_groups:
        if not any(group_matches(group) for group in profile.identity_groups):
            return False
    elif profile.anchors:
        if len(profile.anchors) == 1:
            required = 1
        elif len(profile.anchors) <= 5 or phrase_match:
            required = 2
        else:
            required = 3
        anchor_hits = sum(term in document_terms for term in profile.anchors)
        if anchor_hits < required:
            return False

    matched_weight = sum(
        weight for term, weight in profile.weights.items()
        if term in document_terms
    )
    total_weight = sum(profile.weights.values()) or 1.0
    # Exact model identity is already a strong gate. Non-identity queries need
    # enough of their weighted meaning present, not one accidental generic hit.
    floor = 0.08 if (profile.named_identity or profile.coded_identity) else 0.18
    return matched_weight / total_weight >= floor


def _score_relevance_single(query: str, title: str, body: str) -> float:
    profile = _query_profile(query)
    title_terms = _lexical_tokens(title)
    body_terms = _lexical_tokens(body)
    doc_terms = set(title_terms) | set(body_terms)
    phrase_match = any(
        _contains_phrase(title_terms, phrase)
        or _contains_phrase(body_terms, phrase)
        for phrase in profile.phrases
        if len(phrase) >= 2
    )
    if not _passes_relevance_gate(
        profile, doc_terms, phrase_match=phrase_match
    ):
        return 0.0
    total_weight = sum(profile.weights.values()) or 1.0
    covered = sum(
        weight for term, weight in profile.weights.items()
        if term in doc_terms
    ) / total_weight
    title_covered = sum(
        weight for term, weight in profile.weights.items()
        if term in set(title_terms)
    ) / total_weight
    phrase_hits = sum(
        _contains_phrase(title_terms, phrase)
        or _contains_phrase(body_terms, phrase)
        for phrase in profile.phrases
    )
    phrase_bonus = min(0.20, phrase_hits * 0.05)
    return min(1.0, 0.72 * covered + 0.28 * title_covered + phrase_bonus)


def _search_hit_title_for_ranking(hit: SearchHit) -> str:
    # A forum label is metadata, not evidence that the post discusses a query.
    # Otherwise every random row from r/headphones matches "headphones".
    return re.sub(r"^r/[^:]+:\s*", "", hit.title or "", flags=re.I)


def _rerank_hits(
    query: str,
    hits: Iterable[SearchHit],
    max_results: int,
    *,
    allow_phrase_relaxation: bool = False,
) -> list[SearchHit]:
    """BM25/IDF-style source-local reranking with an absolute relevance gate."""
    candidates = list(hits)
    if max_results <= 0 or not candidates:
        return []
    profile = _query_profile(query)
    prepared: list[tuple[int, SearchHit, list[str], list[str]]] = []
    for index, hit in enumerate(candidates):
        title_terms = _lexical_tokens(_search_hit_title_for_ranking(hit))
        body_terms = _lexical_tokens(hit.content or hit.raw_content or "")
        # Relaxing a long query from three anchors to two is safe only when the
        # exact topic phrase is in the title.  A body-only aside such as "some
        # coffee grinders" inside an unrelated vintage-cast-iron post is not a
        # strong enough reason to surface that post.
        phrase_match = any(
            _contains_phrase(title_terms, phrase)
            for phrase in profile.phrases
            if len(phrase) >= 2
        )
        if not _passes_relevance_gate(
            profile,
            set(title_terms) | set(body_terms),
            phrase_match=phrase_match and allow_phrase_relaxation,
        ):
            continue
        prepared.append((index, hit, title_terms, body_terms))
    if not prepared:
        return []

    n_docs = len(prepared)
    document_frequency = {
        term: sum(term in (set(title) | set(body))
                  for _idx, _hit, title, body in prepared)
        for term in profile.terms
    }
    lengths = [len(title) * 2 + len(body) for _i, _h, title, body in prepared]
    avg_len = sum(lengths) / len(lengths) if lengths else 1.0
    raw_rows: list[tuple[float, int, SearchHit]] = []
    for (index, hit, title_terms, body_terms), doc_len in zip(prepared, lengths):
        title_counts = Counter(title_terms)
        body_counts = Counter(body_terms)
        raw_score = 0.0
        for term, query_weight in profile.weights.items():
            tf = 2.4 * title_counts.get(term, 0) + body_counts.get(term, 0)
            if tf <= 0:
                continue
            df = document_frequency.get(term, 0)
            idf = log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            norm = tf + 1.2 * (1.0 - 0.75 + 0.75 * doc_len / max(avg_len, 1.0))
            raw_score += query_weight * idf * ((tf * 2.2) / norm)

        for phrase in profile.phrases:
            if _contains_phrase(title_terms, phrase):
                raw_score += 0.70 * len(phrase)
            elif _contains_phrase(body_terms, phrase):
                raw_score += 0.30 * len(phrase)

        # The canonical concept/product page should beat a derivative page
        # that merely repeats the same word more often in its snippet.
        if tuple(title_terms) == profile.terms:
            raw_score += 2.50

        identity_terms = set(profile.named_identity) | set(profile.coded_identity)
        identity_hits = len(identity_terms & (set(title_terms) | set(body_terms)))
        raw_score += 0.35 * identity_hits
        # Stable, small source-rank prior only breaks near ties; it cannot make
        # an irrelevant row pass the gate.
        raw_score += 0.01 / (index + 1)
        raw_rows.append((raw_score, index, hit))

    raw_rows.sort(key=lambda row: (-row[0], row[1], row[2].url))
    ceiling = raw_rows[0][0] or 1.0
    out: list[SearchHit] = []
    for raw, _index, hit in raw_rows:
        relative_score = min(1.0, raw / ceiling)
        if relative_score < SEARCH_MIN_RELATIVE_SCORE:
            continue
        out.append(dataclass_replace(hit, score=round(relative_score, 6)))
        if len(out) >= max_results:
            break
    return out


def _score_reddit(query: str, title: str, summary: str) -> float:
    return _score_relevance_single(query, title, summary)


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
    query_terms = _lexical_tokens(query)
    query_set = set(query_terms)
    out: list[str] = []
    for kw, forums in _QUERY_FORUM_HINTS.items():
        kw_terms = tuple(_lexical_tokens(kw))
        matched = (
            bool(kw_terms)
            and (
                (len(kw_terms) == 1 and kw_terms[0] in query_set)
                or (len(kw_terms) > 1 and _contains_phrase(query_terms, kw_terms))
            )
        )
        if not matched:
            continue
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
            bonus = 0.03 if forum.casefold() in hinted else 0.0
            score = min(1.0, tok_score + bonus)
            hits.append(SearchHit(
                url=public_url,
                title=f"r/{forum}: {title or 'Discussion'}",
                content=(body or title)[:600],
                score=score,
                source="reddit",
                raw_content=(body or title),
            ))
    return _rerank_hits(
        query,
        hits,
        max_results,
        allow_phrase_relaxation=True,
    )


def _search_reddit(query: str, max_results: int) -> list[SearchHit]:
    """Full-index retrieval with recent-feed fallback for sparse queries."""
    hinted = _forums_hinted_by_query(query)
    hits: list[SearchHit] = _search_reddit_index(query, max_results)

    def _iter_forum(forum: str, bonus: float) -> None:
        r = _get_source("forum", REDDIT, REDDIT_PUBLIC,
                        f"/f/{forum}/new.atom", timeout=REDDIT_FEED_TIMEOUT_S)
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
            # Forum selection is only a tiny tie-breaker. It must never turn a
            # generic battery/budget hit into a relevant result by itself.
            score = min(1.0, tok_score + min(bonus, 0.03))
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

    # Do not scan every recent feed merely to fill Top-K. The full index has
    # already returned the relevant rows it can find, and padding those rows
    # was both the slowest path in the shim and the main way unrelated recent
    # posts entered otherwise focused searches. Use a small, query-routed feed
    # fallback only when the full index is completely empty.
    if not hits:
        fallback_forums = hinted or [
            forum.strip() for forum in _DEFAULT_REDDIT_FORUMS if forum.strip()
        ]
        for forum in fallback_forums[:REDDIT_FEED_FALLBACK_LIMIT]:
            _iter_forum(forum, bonus=0.03 if forum in hinted else 0.0)

    # Dedupe by URL (hinted iteration may overlap)
    seen: set[str] = set()
    out: list[SearchHit] = []
    for h in _rerank_hits(
        query,
        hits,
        max(len(hits), max_results),
        allow_phrase_relaxation=True,
    ):
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

def _kiwix_query_variants(query: str) -> tuple[str, ...]:
    """Turn explicit technical cues into short Kiwix concept lookups.

    This is deliberately not an LLM planner: it cannot invent a subgoal that
    the agent never asked about. It only prevents an already-present concept
    such as IPX7 or passive radiator from being buried inside a product-length
    query that Kiwix cannot retrieve well.
    """
    terms = set(_lexical_tokens(query))
    variants: list[str] = []

    def add(value: str, condition: bool) -> None:
        if condition and value not in variants:
            variants.append(value)

    add("Artificial intelligence", {"artificial", "intelligence"} <= terms)
    add("Large language model", {"large", "language", "model"} <= terms)
    add("Technological unemployment", (
        "job" in terms and bool({"displacement", "automation"} & terms)
    ))
    add("Inflation", "inflation" in terms)
    add("Consumer price index", {"consumer", "price", "index"} <= terms)
    add("Active noise control", (
        "noise" in terms
        and bool({"cancel", "cancelling", "cancellation"} & terms)
        and "headphone" in terms
    ))
    add("IP code", "ipx7" in terms or {"ingress", "protection"} <= terms)
    add("Passive radiator (speaker)", {"passive", "radiator"} <= terms)
    add("Total harmonic distortion", bool({"distortion", "thd"} & terms))
    add("Audio power", bool({"watt", "rms"} & terms)
        and bool({"speaker", "audio", "amplifier"} & terms))
    speaker_context = (
        "speaker" in terms
        or (
            "sound" in terms
            and bool({"driver", "radiator"} & terms)
        )
    )
    add("Loudspeaker acoustics", (
        speaker_context
        and bool({"360", "dispersion", "radiation", "soundstage"} & terms)
    ))
    add("LDAC (codec)", "ldac" in terms)
    add("High-resolution audio", (
        "audio" in terms
        and (
            {"high", "resolution"} <= terms
            or {"hi", "res"} <= terms
        )
    ))
    add("Bluetooth", "bluetooth" in terms and "codec" in terms)

    if variants:
        return tuple(variants[:4])
    return (query,)


def _search_kiwix(query: str, max_results: int) -> list[SearchHit]:
    """Kiwix candidate retrieval followed by short-query lexical reranking."""
    per_variant: list[list[SearchHit]] = []
    candidate_k = max(max_results * 4, 12)
    for retrieval_query in _kiwix_query_variants(query):
        params = {
            "pattern": retrieval_query,
            "books.name": KIWIX_BOOK,
            "pageLength": candidate_k,
        }
        r = _get_source(
            "wiki",
            KIWIX,
            KIWIX_PUBLIC,
            "/search",
            params=params,
            timeout=KIWIX_SEARCH_TIMEOUT_S,
        )
        if r is None:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        candidates: list[SearchHit] = []
        # Result items are <li>..<a href="..."><cite>..snippet</cite></a>..</li>
        for li in soup.select("ul.results li, .results li")[:candidate_k]:
            a = li.select_one("a[href]")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = _public_link(a.get("href") or "", KIWIX_PUBLIC)
            snippet_el = li.select_one("cite") or li.select_one("p")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else title
            candidates.append(SearchHit(
                url=href,
                title=title,
                content=snippet[:400],
                score=0.0,
                source="wiki",
            ))
        ranked = _rerank_hits(
            retrieval_query,
            candidates,
            min(max_results, KIWIX_RESULTS_PER_CONCEPT),
        )
        if ranked:
            per_variant.append(ranked)

    # One result per explicit concept before taking a second from any concept.
    # This is a within-source quota, not an invitation to pad with weak pages.
    out: list[SearchHit] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < max_results and any(depth < len(rows) for rows in per_variant):
        for rows in per_variant:
            if depth >= len(rows):
                continue
            hit = rows[depth]
            if hit.url in seen:
                continue
            seen.add(hit.url)
            out.append(hit)
            if len(out) >= max_results:
                break
        depth += 1
    return out


def _source_priority(query: str, available: Iterable[str]) -> list[str]:
    terms = set(_lexical_tokens(query))
    base_order = {"shopping": 0, "reddit": 1, "wiki": 2}
    scores = {source: 0 for source in available}
    for cue in {"amazon", "buy", "listing", "model", "price", "product",
                "shop", "spec", "specification"} & terms:
        if "shopping" in scores:
            scores["shopping"] += 1
    for cue in {"community", "complaint", "experience", "forum", "owner",
                "reddit", "review", "user"} & terms:
        if "reddit" in scores:
            scores["reddit"] += 1
    for cue in {"codec", "concept", "definition", "dispersion", "distortion",
                "ipx7", "ldac", "mechanism", "radiator", "rms", "standard",
                "thd", "watt"} & terms:
        if "wiki" in scores:
            scores["wiki"] += 1
    return sorted(
        scores,
        key=lambda source: (-scores[source], base_order.get(source, 99), source),
    )


def _merge_source_hits(
    query: str,
    groups: dict[str, list[SearchHit]],
    max_results: int,
    *,
    explicit_sources: bool = False,
) -> list[SearchHit]:
    """Quota merge already-filtered sources instead of comparing fake scores.

    Source-local BM25 numbers have no shared denominator. Round-robin preserves
    at least one result from every non-empty requested source before any source
    gets a second slot, while `_rerank_hits` ensures weak rows cannot enter just
    to satisfy a quota.
    """
    if max_results <= 0:
        return []
    # A canonical definition/mechanism query with a good encyclopedia hit is
    # harmed, not helped, by quota-padding the remaining slots with products
    # that merely repeat the term.  Explicit include_domains remains sovereign:
    # callers that deliberately requested multiple sources still receive them.
    if (
        not explicit_sources
        and _concept_only_intent(query)
        and groups.get("wiki")
    ):
        groups = {"wiki": groups["wiki"]}
    order = _source_priority(query, (s for s, rows in groups.items() if rows))
    out: list[SearchHit] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < max_results and any(depth < len(groups[s]) for s in order):
        for source in order:
            rows = groups[source]
            if depth >= len(rows):
                continue
            hit = rows[depth]
            if hit.url in seen:
                continue
            seen.add(hit.url)
            out.append(hit)
            if len(out) >= max_results:
                break
        depth += 1
    return out


def search(
    query: str,
    *,
    max_results: int = 10,
    include_domains: Iterable[str] = (),
    exclude_domains: Iterable[str] = (),
) -> list[SearchHit]:
    include = {d.lower() for d in include_domains}
    exclude = {d.lower() for d in exclude_domains}

    groups: dict[str, list[SearchHit]] = {}
    concept_only = not include and _concept_only_intent(query)

    want_shopping = (
        ((not include) and not concept_only)
        or any(d in {"shopping", "localhost:7770", "magento"} for d in include)
    )
    want_reddit = (
        ((not include) and not concept_only)
        or any(
            d in {"reddit", "localhost:9999", "postmill", "reddit.com"}
            for d in include
        )
    )
    want_wiki = (not include) or any(d in {"wiki", "wikipedia", "wikipedia.org", "localhost:8090", "kiwix"} for d in include)

    _diag_store().clear()
    if want_shopping:
        hits = _search_shopping(query, max_results)
        if hits:
            _set_diag("shopping", len(hits))
        elif "shopping" not in last_source_diag():
            _set_diag("shopping", 0, None)   # queried, genuinely no match
        groups["shopping"] = hits
    if want_reddit:
        hits = _search_reddit(query, max_results)
        # Keep the first transport error if one was recorded: a forum that
        # refused the connection is a different fact from a forum with no match.
        prev = last_source_diag().get("forum", {})
        _set_diag("forum", len(hits), prev.get("error"))
        groups["reddit"] = hits
    if want_wiki:
        hits = _search_kiwix(query, max_results)
        if hits:
            _set_diag("wiki", len(hits))
        elif "wiki" not in last_source_diag():
            _set_diag("wiki", 0, None)
        groups["wiki"] = hits

    # Exclude filter
    if exclude:
        groups = {
            source: [
                hit for hit in hits
                if not any(domain in hit.url.lower() for domain in exclude)
            ]
            for source, hits in groups.items()
        }

    return _merge_source_hits(
        query,
        groups,
        max_results,
        explicit_sources=bool(include),
    )


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


def _navigable_links_many(nodes: Iterable, page_url: str, *, cap: int = 300) -> list[str]:
    """Merge links from several served content nodes without changing order."""
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        for url in _navigable_links(node, page_url, cap=cap):
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
            if len(out) >= cap:
                return out
    return out


def _advanced_content_nodes(soup, source: str, fallback) -> list:
    """Return all evidence-bearing nodes for the opt-in v3 extraction path.

    The legacy/basic extractor intentionally selects one node. Magento splits
    identity and price from description/specifications, while Postmill keeps
    the submission and comments in sibling nodes. Advanced extraction exposes
    those source-specific sections together so the served snapshot contains
    the evidence that is visibly present on the page.
    """
    if source == "shopping":
        nodes = list(soup.select(".product-info-main, .product.info.detailed"))
    elif source == "reddit":
        nodes = []
        submission = soup.select_one(".submission")
        if submission is not None:
            nodes.append(submission)
        nodes.extend(soup.select(".comment__body"))
    else:
        nodes = []
    if not nodes and fallback is not None:
        nodes.append(fallback)
    return nodes


def _joined_node_text(title: str, nodes: Iterable, *, cap: int = 20000) -> str:
    """Join non-empty, non-duplicate visible sections in source order."""
    sections: list[str] = []
    seen: set[str] = set()
    raw_sections = [title, *(node.get_text(" ", strip=True) for node in nodes)]
    for raw_text in raw_sections:
        text = re.sub(r"\s+", " ", raw_text).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        sections.append(text)
    return "\n\n".join(sections)[:cap]


def extract(
    urls: Iterable[str],
    *,
    strict: bool | None = None,
    extract_depth: str = "basic",
) -> list[dict]:
    """Fetch full page content for `urls`. Returns list of
    {url, raw_content, title, source, status}.

    ``extract_depth=basic`` preserves the legacy single-node response.
    ``extract_depth=advanced`` is an opt-in v3 path that combines the distinct
    evidence-bearing sections of Magento and Postmill pages.

    In strict mode (``strict=True``, or ``strict=None`` with
    ``SHIM_MODE=strict``) redirects are NOT followed and the final response
    URL is re-validated against the sandbox allowlist. This closes the hole
    where a sandbox page returns a 301/302 to an off-allowlist host: with
    allow_redirects=True the pre-fetch gate in app.py is bypassed because it
    only sees the requested (pre-redirect) URL. A blocked redirect is
    reported as a failed row (status preserved, error set, no raw_content) so
    no off-allowlist content is ever returned.
    """
    if extract_depth not in {"basic", "advanced"}:
        raise ValueError("extract_depth must be 'basic' or 'advanced'")
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
            advanced_title = ""
            if extract_depth == "advanced":
                title_node = soup.select_one("h1") or soup.select_one("title")
                if title_node is not None:
                    advanced_title = title_node.get_text(" ", strip=True)
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
            source = routed_source or (
                "shopping" if "localhost:7770" in url or "magento" in url else (
                    "reddit" if "localhost:9999" in url or "reddit" in url else (
                        "wiki" if "localhost:8090" in url or "wikipedia" in url else "other")
                )
            )
            use_multi_section = (
                extract_depth == "advanced" and source in {"shopping", "reddit"}
            )
            if use_multi_section:
                content_nodes = _advanced_content_nodes(soup, source, main)
                entry["links"] = _navigable_links_many(content_nodes, url)
                entry["raw_content"] = _joined_node_text(
                    advanced_title,
                    content_nodes,
                )
            else:
                entry["links"] = _navigable_links(main, url) if main else []
                text = main.get_text(" ", strip=True) if main else ""
                entry["raw_content"] = text[:20000]
            h1 = soup.select_one("h1")
            if h1:
                entry["title"] = h1.get_text(strip=True)
            elif use_multi_section:
                entry["title"] = advanced_title
            entry["source"] = source
            entry["elapsed_ms"] = int((time.time() - t0) * 1000)
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        out.append(entry)
    return out
