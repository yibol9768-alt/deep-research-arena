"""FastAPI app exposing Tavily + Firecrawl compatible endpoints backed by
our Magento + Postmill sandbox.

Run:
    uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081

Auth is intentionally lax: any `Authorization: Bearer tvly-*` or
`X-Subscription-Token: *` is accepted. Do NOT deploy to the public
internet without adding a real token gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional, Union
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from . import evidence
from .backend import (
    SearchHit,
    extract,
    last_source_diag,
    route_public_url,
    search,
)


# Upstream OpenAI-compat endpoint. Defaults to ds_proxy with deepseek-v4-flash.
# Override via SHIM_LLM_UPSTREAM (e.g. http://localhost:1234/v1 for an LM Studio
# Qwen3 server, or a tunneled port).
LLM_UPSTREAM = os.environ.get(
    "SHIM_LLM_UPSTREAM", "http://localhost:8088/v1"
).rstrip("/")

# Optional model-name rewrite. If set, every incoming `model` field is
# replaced with this value before the upstream call. Lets you point a fleet
# of agents that hardcode "deepseek-v4-flash" at an LM Studio server whose
# loaded model is "qwen3.5-35b-a3b": without touching agent code.
LLM_REWRITE_MODEL = os.environ.get("SHIM_LLM_REWRITE_MODEL", "").strip() or None


# ---------------------------------------------------------------------------
# Strict mode: Workstream C
# ---------------------------------------------------------------------------
#
# When `--mode strict` (or SHIM_MODE=strict) is set, the shim ENFORCES the
# closed-book contract: every URL returned from a search endpoint AND every
# URL targeted by an extract/scrape call MUST resolve to one of the four
# sandbox origins (Magento :7770, Postmill :9999, Kiwix :8090, shim :8081)
# on either localhost or 127.0.0.1.
#
# Any non-allowlist URL is replaced with a 403-error sentinel in /search
# responses and triggers an HTTP 403 in /extract|/scrape. Every blocked URL
# is appended to logs/shim_blocks.jsonl for audit.
#
# Open mode (the default and previous behavior) is unchanged: the gate is
# a no-op and every URL flows through.
# ---------------------------------------------------------------------------

# Origins that the strict gate accepts. Same set as
# `src/verifiers/sandbox_compliance_verifier.DEFAULT_ALLOWED_ORIGINS`:
# kept duplicated here so the shim has no Python-path dependency on the
# verifier package (the shim can be deployed standalone).
SHIM_ALLOWLIST_HOSTS: tuple[str, ...] = (
    "localhost:7770", "localhost:8090", "localhost:9999", "localhost:8081",
    "127.0.0.1:7770", "127.0.0.1:8090", "127.0.0.1:9999", "127.0.0.1:8081",
)


def _allowlist_hosts() -> set[str]:
    """Static public ports plus the backend's configured dial/public origins."""
    hosts = {h.lower() for h in SHIM_ALLOWLIST_HOSTS}
    try:
        from .backend import _allowlist_hosts as _backend_allowlist

        hosts.update(h.lower() for h in _backend_allowlist())
    except Exception:  # noqa: BLE001 -- strict gate keeps the static floor
        pass
    return hosts

# Where to log blocked URLs. Path is repo-relative so multiple shim
# instances writing concurrently still land in the same audit file.
_SHIM_ROOT = Path(__file__).resolve().parents[2]
_SHIM_BLOCKS_LOG = _SHIM_ROOT / "logs" / "shim_blocks.jsonl"


def _shim_mode() -> str:
    """Return the current shim mode: 'strict' or 'open'.

    Read at request time (not import time) so test fixtures can toggle the
    mode via the environment without restarting the process.
    """
    m = os.environ.get("SHIM_MODE", "open").strip().lower()
    return "strict" if m == "strict" else "open"


def _url_is_sandbox(url: str) -> bool:
    """Strict host:port equality check against `SHIM_ALLOWLIST_HOSTS`.

    Substring matching (``"localhost:7770" in url``) is unsafe: it admits
    ``http://localhost:77703/leak`` because the literal "localhost:7770" is
    a prefix. We parse the URL and compare ``host:port`` netlocs exactly.
    """
    if not url:
        return False
    try:
        p = urlparse(url)
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
    for allowed in _allowlist_hosts():
        a = allowed.lower()
        if ":" in a:
            if netloc == a:
                return True
        elif host == a:
            return True
    return False


def _log_blocked_url(url: str, endpoint: str, *, query: str | None = None) -> None:
    """Append a JSON line to `logs/shim_blocks.jsonl` for audit.

    Best-effort: log failures are swallowed so a missing/unwritable logs
    dir never breaks a request. The directory is created on first call.
    """
    try:
        _SHIM_BLOCKS_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": round(time.time(), 3),
            "endpoint": endpoint,
            "url": url,
            "query": query,
            "reason": "non_sandbox_url_blocked",
        }
        with _SHIM_BLOCKS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Also attribute the block to the open run. The global blocks log has no
    # run_id, so it can say "something was blocked" but never "this agent tried".
    evidence.record_block(url, endpoint, "non_sandbox_url_blocked")


def _filter_hits_strict(
    hits: list[SearchHit], *, endpoint: str, query: str | None = None,
) -> list[SearchHit]:
    """In strict mode, drop any hit whose URL is not in the allowlist and
    log it. In open mode this is a passthrough."""
    if _shim_mode() != "strict":
        return hits
    kept: list[SearchHit] = []
    for h in hits:
        if _url_is_sandbox(h.url):
            kept.append(h)
        else:
            _log_blocked_url(h.url, endpoint, query=query)
    return kept


def _ensure_url_allowed(url: str, endpoint: str) -> None:
    """In strict mode, raise HTTP 403 for non-sandbox extract/scrape targets.

    No-op in open mode. Logs every block to `logs/shim_blocks.jsonl` first
    so the audit trail captures the attempt even though the request fails.
    """
    if _shim_mode() != "strict":
        return
    if _url_is_sandbox(url):
        return
    _log_blocked_url(url, endpoint)
    raise HTTPException(
        status_code=403,
        detail={"error": "non_sandbox_url_blocked", "url": url},
    )


app = FastAPI(
    title="Sandbox Search Shim",
    version="0.2.0",
    description="Tavily + Firecrawl-compatible wire protocol over our "
                "Magento + Postmill benchmark sandbox. Lets any research "
                "framework hit our sandbox with zero code change by "
                "overriding TAVILY_API_URL / FIRECRAWL_BASE_URL.",
)


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _build_identity() -> dict[str, str]:
    """Content identity used by launch gates to reject stale shim processes."""
    return {
        "app_sha256": _file_sha256(Path(__file__)),
        "backend_sha256": _file_sha256(Path(__file__).with_name("backend.py")),
        "build_commit": os.environ.get("DRA_SEARCH_BUILD_COMMIT", "unknown"),
    }


# ============================================================================
# Run brackets and transport-level evidence
# ============================================================================
#
# See integrations/search_shim/evidence.py for why this exists. In short: the
# scorer used to infer "did the agent read this page" from the report prose.
# It now reads what the shim actually served.

@app.post("/_mark")
async def run_mark(request: Request):
    """Open or close a run bracket: {run_id, phase: "start"|"end", lane, task,
    backbone, worker}.

    A reentrant `start` returns HTTP 409 instead of silently interleaving two
    runs into one evidence log. Concurrent workers must each get their own shim
    instance; the harness runs two, so this is not hypothetical.
    """
    try:
        body = json.loads(await request.body() or b"{}")
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    phase = str(body.get("phase") or "start").lower()
    try:
        if phase == "end":
            return evidence.mark_end(body)
        ctx = evidence.mark_start(body)
    except evidence.RunAlreadyActive as e:
        raise HTTPException(status_code=409, detail={"error": "run_already_active", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "run_id": ctx.run_id, "recording": evidence.enabled()}


SOURCE_CANARY = os.environ.get("SHIM_SOURCE_CANARY", "headphones")
_SOURCES_TTL_S = float(os.environ.get("SHIM_SOURCES_TTL_S", "600"))
_SOURCES_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}


@app.get("/_sources/health")
def sources_health(fresh: bool = False):
    """Did every sandbox source actually answer? Read-only, cached.

    A source that is unreachable returns no hits, and a source with no match for
    this query returns no hits. The store spent the project in the first state
    while every report was scored as though it were in the second. The harness
    calls this before it opens a run bracket and refuses to start when a source
    is down, so a run can no longer be scored against a corpus it could not see.

    Probes `backend.search`, not the recorded `/search` chokepoint: a health
    check must not write into the open run's evidence log, or it would inflate
    that run's `search_returned` set and with it the `pof` denominator.
    """
    now = time.monotonic()
    cached = _SOURCES_CACHE["payload"]
    if not fresh and cached and now - _SOURCES_CACHE["at"] < _SOURCES_TTL_S:
        return {**cached, "cached": True}

    try:
        hits = search(SOURCE_CANARY, max_results=3)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "sources": {},
            "down": {"*": f"{type(e).__name__}: {e}"},
            "not_queried": [],
            "sample_urls": [],
            "query": SOURCE_CANARY,
            "cached": False,
            **_build_identity(),
        }

    # The caller holds the registry; the shim does not. Hand back what a real
    # search would have handed the agent, so the harness can ask the question the
    # shim cannot: would the scorer count these as fabricated?
    sample_urls = [h.url for h in hits][:12]
    diag = last_source_diag()
    # `down` is the undetectable failure: the source handed back nothing, which
    # reads exactly like "no product matches this query". `degraded` is a source
    # that answered despite an error on part of the fan-out -- the forum queries
    # several boards and one may 404. That is visible in the data, so it warns
    # rather than blocks; blocking on it would ground every run over one board.
    down = {s: (d.get("error") or "zero hits")
            for s, d in diag.items() if not d.get("n_results")}
    degraded = {s: d["error"] for s, d in diag.items()
                if d.get("error") and d.get("n_results")}
    never_asked = [s for s in ("shopping", "forum", "wiki") if s not in diag]
    payload = {"ok": not down and not never_asked, "sources": diag, "down": down,
               "degraded": degraded, "not_queried": never_asked,
               "sample_urls": sample_urls, "query": SOURCE_CANARY,
               **_build_identity()}
    _SOURCES_CACHE.update(at=now, payload=payload)
    return {**payload, "cached": False}


@app.get("/_evidence/status")
def evidence_status():
    ctx = evidence.active()
    return {
        "recording": evidence.enabled(),
        "dir": str(evidence.evidence_dir()),
        "active_run": ctx.run_id if ctx else None,
        "counters": evidence.counters(),
    }


@app.get("/fetch")
def sandbox_fetch(url: str = Query(..., description="canonical sandbox URL")):
    """Recorded page read. The ONLY page-fetch path agents may use.

    CLI lanes (claude-code, opencode) used to `curl` the sandbox origins
    directly, so page reads left no trace and the shim only ever saw /search.
    Their command allowlists now permit the shim origin only, and this endpoint
    is what they curl. The response body is returned verbatim, and the exact
    bytes served are content-addressed so the scorer never re-fetches.
    """
    _ensure_url_allowed(url, endpoint="/fetch")
    dial_url, dial_headers, _source = route_public_url(url)
    try:
        # Dial the compose/service address while presenting the source's public
        # identity as Host.  The requested/public URL remains the evidence key.
        r = httpx.get(
            dial_url,
            headers=dial_headers,
            timeout=30.0,
            follow_redirects=False,
        )
        body = r.content or b""
        status = r.status_code
        err = None
    except Exception as e:  # noqa: BLE001
        body, status, err = b"", 0, f"{type(e).__name__}: {e}"
    # /fetch returns the full raw HTML verbatim, so the agent sees every <a href>
    # on the page (nav included). Parse the WHOLE document for navigable links so
    # a URL the agent reached by following any on-page link is later scored
    # `linked`, not `hallucinated_grounding`. Best-effort: a parse failure leaves
    # links unset and the scorer falls back to the blob regex.
    links = None
    ctype = ""
    try:
        ctype = (r.headers.get("content-type") or "") if err is None else ""
    except Exception:  # noqa: BLE001
        ctype = ""
    if body and status and status < 400 and "html" in ctype.lower():
        try:
            from .backend import BeautifulSoup, _navigable_links
            soup = BeautifulSoup(body.decode("utf-8", "replace"), "html.parser")
            links = _navigable_links(soup, url)
        except Exception:  # noqa: BLE001
            links = None
    evidence.record_fetch(url, status, body, endpoint="/fetch", error=err, links=links)
    if err or status == 0:
        raise HTTPException(status_code=502, detail=err or "fetch failed")
    return Response(content=body, status_code=status,
                    media_type=r.headers.get("content-type", "text/plain"))


# ============================================================================
# Tavily schema: POST /search, POST /extract
# ============================================================================

class TavilySearchRequest(BaseModel):
    # Lenient schema: real Tavily clients (gpt-researcher, langchain,
    # raw curl) send mildly different payloads. Accept None where list
    # is expected, ignore unknown fields (api_key in body, days, use_cache
    # etc. from gpt-researcher).
    model_config = {"extra": "ignore"}

    query: str
    search_depth: str = "basic"
    topic: str = "general"
    max_results: int = Field(default=5, ge=0, le=100)
    include_answer: Union[bool, str] = False
    include_raw_content: Union[bool, str] = False
    include_images: bool = False
    include_domains: Optional[list[str]] = None
    exclude_domains: Optional[list[str]] = None
    time_range: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    country: Optional[str] = None


class TavilySearchResultItem(BaseModel):
    title: str
    url: str
    content: str
    score: float
    raw_content: Optional[str] = None


class TavilySearchResponse(BaseModel):
    query: str
    answer: Optional[str] = None
    images: list[dict] = []
    results: list[TavilySearchResultItem]
    response_time: float
    request_id: str


def _hit_to_tavily(
    h: SearchHit,
    include_raw: Union[bool, str],
    *,
    fetched_raw_content: Optional[str] = None,
) -> TavilySearchResultItem:
    raw = None
    if include_raw:
        # Tavily defines include_raw_content as the cleaned webpage body, not a
        # duplicate of the search snippet.  Some official clients (notably
        # LangChain Open Deep Research) intentionally use this one-call path
        # instead of invoking /extract separately.
        raw = fetched_raw_content or h.raw_content
    return TavilySearchResultItem(
        title=h.title,
        url=h.url,
        content=h.content,
        score=round(h.score, 3),
        raw_content=raw,
    )


def _search_recorded(query: str, *, endpoint: str, **kw) -> list[SearchHit]:
    """Every search the shim serves, recorded against the open run.

    This is the single chokepoint for `backend.search`. Recording here (rather
    than in each of the seven wire-protocol endpoints) is what makes
    `retrieval_utilization` and the searched/linked/guessed provenance classes
    computable: without `urls_returned` a cited URL cannot be told apart from
    one the model guessed.
    """
    hits = search(query, **kw)
    from .backend import last_source_diag
    evidence.record_search(
        query, [h.url for h in hits], endpoint=endpoint,
        source_diag=last_source_diag(),
    )
    return hits


def _extract_recorded(
    urls: list[str],
    *,
    endpoint: str,
    extract_depth: Literal["basic", "advanced"] = "basic",
) -> list[dict]:
    """Single chokepoint for `backend.extract`. Stores the served bytes.

    The scorer reads these bytes (by digest) instead of re-fetching the page at
    scoring time, so `quote_support` compares the report against what the agent
    was actually shown.
    """
    # Keep every legacy caller, including Firecrawl and one-argument test or
    # harness adapters, on the byte-identical basic call shape. Only Tavily's
    # explicit advanced request opts into the v3 multi-section extractor.
    rows = (
        extract(urls, extract_depth="advanced")
        if extract_depth == "advanced"
        else extract(urls)
    )
    for row in rows:
        body = (row.get("raw_content") or "").encode("utf-8", "replace")
        # `links` were captured from the page HTML before get_text() stripped
        # the hrefs. Pass them so an on-page-link citation is scored `linked`,
        # not `hallucinated_grounding`. `row.get("links")` is None on a blocked
        # or errored page (never parsed), which record_fetch leaves unstamped.
        evidence.record_fetch(
            row.get("url", ""), int(row.get("status") or 0), body,
            endpoint=endpoint, error=row.get("error"),
            links=row.get("links"),
        )
    return rows


def _tavily_search_response(
    query: str,
    *,
    max_results: int = 5,
    include_raw_content: Union[bool, str] = False,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> TavilySearchResponse:
    t0 = time.time()
    hits = _search_recorded(
        query,
        endpoint="/search",
        max_results=max_results or 5,
        include_domains=include_domains or [],
        exclude_domains=exclude_domains or [],
    )
    hits = _filter_hits_strict(hits, endpoint="/search", query=query)
    fetched_by_url: dict[str, str] = {}
    if include_raw_content and hits:
        # Preserve Tavily's native one-call search+page-content contract.  The
        # fetch still goes through the same strict sandbox extractor and is
        # recorded independently, so raw content cannot be confused with a
        # snippet or escape the corpus allowlist.
        rows = _extract_recorded(
            [hit.url for hit in hits],
            endpoint="/search",
        )
        fetched_by_url = {
            str(row.get("url")): str(row.get("raw_content"))
            for row in rows
            if row.get("url") and row.get("raw_content")
        }
    return TavilySearchResponse(
        query=query,
        results=[
            _hit_to_tavily(
                h,
                include_raw_content,
                fetched_raw_content=fetched_by_url.get(h.url),
            )
            for h in hits
        ],
        response_time=round(time.time() - t0, 3),
        request_id=str(uuid.uuid4()),
    )


@app.post("/search", response_model=TavilySearchResponse)
def tavily_search(
    req: TavilySearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> TavilySearchResponse:
    # Accept any bearer token; reject only if obviously garbage.
    if authorization and not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="expected Bearer token")

    return _tavily_search_response(
        req.query,
        max_results=req.max_results or 5,
        include_domains=req.include_domains or [],
        exclude_domains=req.exclude_domains or [],
        include_raw_content=req.include_raw_content,
    )


def _search_get_payload(
    query: str,
    *,
    max_results: int,
    include_raw_content: bool = False,
) -> dict[str, Any]:
    response = _tavily_search_response(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    payload["web"] = {
        "results": [
            {
                "title": item["title"],
                "url": item["url"],
                "description": item.get("content", ""),
            }
            for item in payload.get("results", [])
        ]
    }
    return payload


@app.get("/search")
def tavily_search_get(
    q: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    count: int = Query(default=5, ge=0, le=100),
    max_results: Optional[int] = Query(default=None, ge=0, le=100),
    include_raw_content: bool = Query(default=False),
) -> dict[str, Any]:
    # Some agent tools use Brave-like GET /search?q=... while others expect the
    # Tavily shape. Return both shapes so the shim stays a single endpoint.
    text = query or q
    if not text:
        raise HTTPException(status_code=422, detail="missing q or query")
    return _search_get_payload(
        text,
        max_results=max_results if max_results is not None else count,
        include_raw_content=include_raw_content,
    )


class TavilyExtractRequest(BaseModel):
    urls: list[str]
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"
    include_images: bool = False


class TavilyExtractResultItem(BaseModel):
    url: str
    raw_content: str
    images: list[dict] = []


class TavilyExtractResponse(BaseModel):
    results: list[TavilyExtractResultItem]
    failed_results: list[dict] = []
    response_time: float
    request_id: str


@app.post("/extract", response_model=TavilyExtractResponse)
def tavily_extract(
    req: TavilyExtractRequest,
    authorization: Optional[str] = Header(default=None),
) -> TavilyExtractResponse:
    t0 = time.time()
    # Strict mode: refuse the WHOLE call if any target is off-allowlist.
    # Returning a partial result would let an agent silently confirm which
    # URLs the gate considers private; a single 403 is cleaner.
    for u in req.urls:
        _ensure_url_allowed(u, endpoint="/extract")
    rows = _extract_recorded(
        list(req.urls),
        endpoint="/extract",
        extract_depth=req.extract_depth,
    )
    results: list[TavilyExtractResultItem] = []
    failed: list[dict] = []
    for row in rows:
        if row.get("status") and row["status"] < 400 and row.get("raw_content"):
            results.append(TavilyExtractResultItem(
                url=row["url"], raw_content=row["raw_content"], images=[],
            ))
        else:
            failed.append({"url": row["url"], "error": row.get("error") or f"status {row.get('status')}"})
    return TavilyExtractResponse(
        results=results,
        failed_results=failed,
        response_time=round(time.time() - t0, 3),
        request_id=str(uuid.uuid4()),
    )


# ============================================================================
# Firecrawl schema: POST /v2/search, POST /v2/scrape
# ============================================================================

class FirecrawlScrapeOptions(BaseModel):
    formats: Union[list[dict], list[str]] = Field(default_factory=lambda: [{"type": "markdown"}])


class FirecrawlSearchRequest(BaseModel):
    # Lenient: dzhng/deep-research uses Firecrawl JS SDK v1 which sends
    # {query, limit, tbs, filter, lang, country, location, origin, timeout,
    #  scrapeOptions: {formats: ["markdown"]}}. We accept v1 and v2 shapes.
    model_config = {"extra": "ignore"}

    query: str
    limit: int = 5
    sources: list[str] = Field(default_factory=lambda: ["web"])
    scrapeOptions: Optional[FirecrawlScrapeOptions] = None
    lang: Optional[str] = None
    country: Optional[str] = None
    tbs: Optional[str] = None
    filter: Optional[str] = None
    location: Optional[str] = None
    origin: Optional[str] = None
    timeout: Optional[int] = None


class FirecrawlSearchItem(BaseModel):
    title: str
    description: str
    url: str
    markdown: Optional[str] = None


class FirecrawlSearchResponse(BaseModel):
    success: bool
    data: dict


def _do_firecrawl_search(req: FirecrawlSearchRequest) -> FirecrawlSearchResponse:
    hits = _search_recorded(req.query, endpoint="/v2/search", max_results=req.limit or 5)
    hits = _filter_hits_strict(hits, endpoint="/v2/search", query=req.query)
    web = [FirecrawlSearchItem(
        title=h.title, description=h.content, url=h.url,
        markdown=h.content,  # shallow: /v2/scrape is where full markdown goes
    ).model_dump() for h in hits]
    return FirecrawlSearchResponse(success=True, data={"web": web})


@app.post("/v2/search", response_model=FirecrawlSearchResponse)
def firecrawl_search_v2(
    req: FirecrawlSearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> FirecrawlSearchResponse:
    return _do_firecrawl_search(req)


class FirecrawlV1SearchResponse(BaseModel):
    """dzhng/deep-research's Firecrawl JS SDK v1 expects top-level
    ``{success, data: [ {url, markdown, title, ...} ]}`` with ``data`` as a
    flat array (NOT the v2 ``{web: [...]}`` envelope). Keep the v1 shape
    so dzhng works zero-code."""

    success: bool
    data: list[dict]


@app.post("/v1/search", response_model=FirecrawlV1SearchResponse)
def firecrawl_search_v1(
    req: FirecrawlSearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> FirecrawlV1SearchResponse:
    hits = _search_recorded(req.query, endpoint="/v1/search", max_results=req.limit or 5)
    hits = _filter_hits_strict(hits, endpoint="/v1/search", query=req.query)
    items = [
        {
            "url": h.url,
            "title": h.title,
            "description": h.content,
            "markdown": h.content,
        }
        for h in hits
    ]
    return FirecrawlV1SearchResponse(success=True, data=items)


class FirecrawlScrapeRequest(BaseModel):
    url: str
    formats: list[str] = Field(default_factory=lambda: ["markdown"])


class FirecrawlScrapeData(BaseModel):
    markdown: str
    html: Optional[str] = None
    metadata: dict


class FirecrawlScrapeResponse(BaseModel):
    success: bool
    data: FirecrawlScrapeData


@app.post("/v1/scrape", response_model=FirecrawlScrapeResponse)
@app.post("/v2/scrape", response_model=FirecrawlScrapeResponse)
def firecrawl_scrape(
    req: FirecrawlScrapeRequest,
    authorization: Optional[str] = Header(default=None),
) -> FirecrawlScrapeResponse:
    _ensure_url_allowed(req.url, endpoint="/scrape")
    rows = _extract_recorded([req.url], endpoint="/scrape")
    if not rows:
        raise HTTPException(status_code=500, detail="extract returned no rows")
    row = rows[0]
    # Mirror the success condition used in tavily_extract: a row counts as a
    # success only when it has non-empty raw_content, a sub-400 status, and no
    # 'error'. extract() seeds each row with status=0 and, on a request
    # exception (connection refused, DNS failure, timeout), leaves status=0
    # and sets 'error' with no raw_content. status==0 is falsy, so the old
    # guard `if row.get("status") and row["status"] >= 400` skipped the
    # exception path entirely and reported a failed fetch as a successful
    # empty scrape. Treat status==0 (the exception sentinel) and any present
    # 'error' as a failure.
    if not row.get("raw_content") or (row.get("status") or 0) >= 400 or row.get("error"):
        raise HTTPException(
            status_code=(row.get("status") or 502),
            detail=row.get("error") or "fetch failed",
        )
    return FirecrawlScrapeResponse(
        success=True,
        data=FirecrawlScrapeData(
            markdown=row.get("raw_content") or "",
            html=None,
            metadata={
                "title": row.get("title"),
                "source": row.get("source"),
                "sourceURL": row["url"],
                "elapsed_ms": row.get("elapsed_ms"),
            },
        ),
    )


# ============================================================================
# DB lookup endpoints: structured JSON lookup to equalize info access
# across agents (fixes the methodology bias flagged in 2026-04-20 paper
# discussion: react uses envs.*.scrape directly, everyone else only sees
# Tavily-compat snippets; these endpoints expose the same structured data
# via HTTP so any agent can call them).
# ============================================================================

class PostLookupRequest(BaseModel):
    url: str  # full Postmill post URL, or /f/<forum>/<id>/<slug> path


class PostLookupResponse(BaseModel):
    ok: bool
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    forum: Optional[str] = None
    score: Optional[int] = None
    comment_count: Optional[int] = None
    body: Optional[str] = None
    top_comments: list[dict] = Field(default_factory=list)
    error: Optional[str] = None


def _forum_from_url(url: str) -> Optional[str]:
    """Derive the Postmill forum slug from a submission URL or path.

    Postmill canonical comment-page URLs are ``/f/<forum>/<id>/<slug>``.
    get_submission does not return a top-level forum for the detail page, so
    parse it from the path. Returns None if no ``/f/<forum>`` segment exists.
    """
    if not url:
        return None
    try:
        path = urlparse(url).path or url
    except Exception:
        path = url
    m = re.search(r"/f/([A-Za-z0-9_]+)", path)
    return m.group(1) if m else None


def _get_submission(url: str) -> dict:
    """Lazy production adapter, patchable when optional envs are absent."""
    from envs.reddit.scrape import get_submission

    return get_submission(url)


@app.post("/post_lookup", response_model=PostLookupResponse)
def post_lookup(req: PostLookupRequest) -> PostLookupResponse:
    """Return structured JSON for a single Postmill submission. Delegates
    to envs.reddit.scrape.get_submission (requests-based, no Playwright)."""
    # Honor SHIM_MODE=strict: get_submission's _fetch does an unrestricted
    # requests.get on any URL containing '://', so without this gate an agent
    # could fetch arbitrary off-allowlist/external URLs through this endpoint
    # (SSRF / closed-book contract violation). Enforce the same allowlist as
    # tavily_extract and firecrawl_scrape BEFORE any fetch.
    _ensure_url_allowed(req.url, endpoint="/post_lookup")
    try:
        data = _get_submission(req.url)
        if not data or not data.get("title"):
            return PostLookupResponse(ok=False, url=req.url, error="post not found or empty")
        # get_submission (envs/reddit/scrape.py:127-145) only sets these
        # top-level keys: url, title, score, author, body_html, comments
        # (a list), num_comments. It never sets comment_count, a top-level
        # forum, or body. Map to the actual keys so this endpoint stops
        # returning null comment_count/forum/body for valid posts.
        comments = data.get("comments") or []
        comment_count = data.get("num_comments")
        if comment_count is None:
            comment_count = len(comments)
        # Strip HTML from the post body_html for a plain-text body.
        body_html = data.get("body_html") or ""
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body_html)).strip() or None
        return PostLookupResponse(
            ok=True,
            url=req.url,
            title=data.get("title"),
            author=data.get("author"),
            forum=data.get("forum") or _forum_from_url(req.url),
            score=data.get("score"),
            comment_count=comment_count,
            body=body,
            top_comments=comments,
        )
    except Exception as e:
        return PostLookupResponse(ok=False, url=req.url, error=f"{type(e).__name__}: {e}")


class ProductLookupRequest(BaseModel):
    url: str  # full Magento PDP URL (e.g. http://localhost:7770/some-product.html)


class ProductLookupResponse(BaseModel):
    ok: bool
    url: str
    name: Optional[str] = None
    price: Optional[float] = None
    rating: Optional[float] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    review_count: Optional[int] = None
    in_stock: Optional[bool] = None
    error: Optional[str] = None


@app.post("/product_lookup", response_model=ProductLookupResponse)
def product_lookup(req: ProductLookupRequest) -> ProductLookupResponse:
    """Return structured JSON for a single Magento PDP. This is an HTTP-only
    best-effort extractor (no Playwright): it parses price/rating/sku from
    the server-rendered HTML. Accuracy is lower than the Playwright-based
    envs.shopping.oracle_dr.magento_scrape.product_details, but all agents
    can call it through the shim."""
    import re
    # Honor SHIM_MODE=strict: this handler does requests.get on the raw
    # client-supplied URL, so without this gate an agent could fetch arbitrary
    # off-allowlist/external URLs (SSRF / closed-book contract violation).
    # Enforce the allowlist BEFORE any fetch, and outside the try below so the
    # 403 is not swallowed by the broad except.
    _ensure_url_allowed(req.url, endpoint="/product_lookup")
    strict = _shim_mode() == "strict"
    dial_url, dial_headers, _source = route_public_url(req.url)
    try:
        import requests  # type: ignore
        # In strict mode do not follow redirects: a sandbox PDP that
        # 30x-redirects off origin would otherwise bypass the pre-fetch
        # allowlist gate (which only saw the requested URL) and let requests
        # return off-allowlist content. Re-validate the final response URL too.
        r = requests.get(
            dial_url,
            headers=dial_headers,
            timeout=20,
            allow_redirects=not strict,
        )
        if strict and (300 <= r.status_code < 400 or not _url_is_sandbox(str(r.url))):
            evidence.record_fetch(
                req.url,
                r.status_code,
                b"",
                endpoint="/product_lookup",
                error="non_sandbox_redirect_blocked",
            )
            _log_blocked_url(str(r.url), endpoint="/product_lookup")
            raise HTTPException(
                status_code=403,
                detail={"error": "non_sandbox_redirect_blocked", "url": str(r.url)},
            )
        if r.status_code >= 400:
            evidence.record_fetch(
                req.url,
                r.status_code,
                getattr(r, "content", b"") or b"",
                endpoint="/product_lookup",
                error=f"HTTP {r.status_code}",
            )
            return ProductLookupResponse(ok=False, url=req.url,
                                         error=f"HTTP {r.status_code}")
        html = r.text
    except HTTPException:
        # The strict redirect block must propagate as a 403, not be swallowed
        # by the broad except below and turned into an ok=False 200 body.
        raise
    except Exception as e:
        evidence.record_fetch(
            req.url,
            0,
            b"",
            endpoint="/product_lookup",
            error=f"{type(e).__name__}: {e}",
        )
        return ProductLookupResponse(ok=False, url=req.url,
                                     error=f"{type(e).__name__}: {e}")

    # Structured lookup is still a page read.  Record the public identity and
    # the source bytes from which the JSON response was derived, never the
    # compose-only dial URL.
    links = None
    try:
        from .backend import BeautifulSoup, _navigable_links

        soup = BeautifulSoup(html, "html.parser")
        links = _navigable_links(soup, req.url)
    except Exception:  # noqa: BLE001
        links = None
    evidence.record_fetch(
        req.url,
        r.status_code,
        getattr(r, "content", b"") or html.encode("utf-8", "replace"),
        endpoint="/product_lookup",
        links=links,
    )

    def _first(pattern: str, flags=0):
        m = re.search(pattern, html, flags)
        return m.group(1).strip() if m else None

    name = _first(r'<span[^>]+itemprop="name"[^>]*>([^<]+)</span>') or \
           _first(r'<h1[^>]*class="page-title"[^>]*>\s*<span[^>]*>([^<]+)</span>')
    price_raw = _first(r'data-price-amount="([0-9.]+)"')
    price = float(price_raw) if price_raw else None
    # Magento stores rating in title="N%" of .rating-result; decode to 0..5
    pct_raw = _first(r'class="rating-result"[^>]*title="([0-9]+)%"')
    rating = round(int(pct_raw)/20 * 10)/10 if pct_raw else None
    sku = _first(r'<div[^>]+itemprop="sku"[^>]*>([^<]+)</div>') or \
          _first(r'"sku":"([^"]+)"')
    desc = _first(r'<meta[^>]+name="description"[^>]+content="([^"]+)"')
    review_count_raw = _first(r'id="customer-reviews"[^>]*>[\s\S]{0,4000}?\((\d+)\s+Reviews?\)', re.I)
    review_count = int(review_count_raw) if review_count_raw else None
    in_stock = "In stock" in html or "in-stock" in html.lower()

    return ProductLookupResponse(
        ok=True, url=req.url,
        name=name, price=price, rating=rating, sku=sku,
        description=desc, review_count=review_count, in_stock=in_stock,
    )


# ============================================================================
# Serper-compat: POST /v1/serper
# ============================================================================
#
# Serper is a Google-SERP-as-a-service API. Its `/search` endpoint takes
# `{"q": "...", "num": N}` and returns `{"organic": [{title, link, snippet}],
# "credits": N}`. Used by qx-agents (`agents-deep-research/serper_search.py`)
# and Tongyi DeepResearch.

class SerperRequest(BaseModel):
    model_config = {"extra": "ignore"}

    q: str
    num: int = Field(default=10, ge=0, le=50)
    gl: Optional[str] = None
    hl: Optional[str] = None
    page: Optional[int] = None
    autocorrect: Optional[bool] = None


class SerperOrganicItem(BaseModel):
    title: str
    link: str
    snippet: str


class SerperResponse(BaseModel):
    organic: list[SerperOrganicItem]
    credits: int = 1


@app.post("/v1/serper", response_model=SerperResponse)
def serper_search(
    req: SerperRequest,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> SerperResponse:
    """Serper-compat (`google.serper.dev/search`). Used by qx-agents and
    Tongyi DeepResearch. Body: `{"q": "...", "num": N}`. Returns
    `{"organic": [{title, link, snippet}], "credits": 1}`."""
    hits = _search_recorded(req.q, endpoint="/v1/serper", max_results=req.num or 10)
    hits = _filter_hits_strict(hits, endpoint="/v1/serper", query=req.q)
    organic = [
        SerperOrganicItem(title=h.title, link=h.url, snippet=h.content)
        for h in hits
    ]
    return SerperResponse(organic=organic, credits=1)


# ============================================================================
# Brave-compat: GET /v1/brave/web/search
# ============================================================================
#
# Brave Search API responds to `GET /res/v1/web/search?q=...&count=N` with
# `{"web": {"results": [{url, title, description, ...}]}}`. We mount it under
# `/v1/brave/web/search` so frameworks that point `BRAVE_API_URL` at the shim
# get drop-in compat.

class BraveResultItem(BaseModel):
    url: str
    title: str
    description: str


class BraveWeb(BaseModel):
    results: list[BraveResultItem]


class BraveResponse(BaseModel):
    web: BraveWeb


@app.get("/v1/brave/web/search", response_model=BraveResponse)
def brave_search(
    q: str = Query(...),
    count: int = Query(default=10, ge=0, le=50),
    x_subscription_token: Optional[str] = Header(default=None),
) -> BraveResponse:
    """Brave Search API compat (`api.search.brave.com/res/v1/web/search`).
    Returns Brave-style `{"web": {"results": [{url, title, description}]}}`."""
    hits = _search_recorded(q, endpoint="/v1/brave/web/search", max_results=count)
    hits = _filter_hits_strict(hits, endpoint="/v1/brave/web/search", query=q)
    items = [
        BraveResultItem(url=h.url, title=h.title, description=h.content)
        for h in hits
    ]
    return BraveResponse(web=BraveWeb(results=items))


# ============================================================================
# SearxNG-compat: GET /searxng/search
# ============================================================================
#
# SearxNG meta-search exposes `GET /search?q=...&format=json&pageno=N` and
# returns `{"results": [{url, title, content}], "query": "..."}`. Used by
# Perplexica (front-end search wrapper) and ii-researcher.

class SearxNGResultItem(BaseModel):
    url: str
    title: str
    content: str


class SearxNGResponse(BaseModel):
    results: list[SearxNGResultItem]
    query: str
    number_of_results: int = 0


@app.get("/searxng/search", response_model=SearxNGResponse)
def searxng_search(
    q: str = Query(...),
    format: str = Query(default="json"),
    pageno: int = Query(default=1, ge=1),
    count: int = Query(default=10, ge=0, le=50),
    categories: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
) -> SearxNGResponse:
    """SearxNG meta-search compat (`/search?q=...&format=json&pageno=1`).
    Used by Perplexica and ii-researcher. Returns `{"results": [{url, title,
    content}], "query": "..."}`."""
    hits = _search_recorded(q, endpoint="/searxng/search", max_results=count)
    hits = _filter_hits_strict(hits, endpoint="/searxng/search", query=q)
    items = [
        SearxNGResultItem(url=h.url, title=h.title, content=h.content)
        for h in hits
    ]
    return SearxNGResponse(
        results=items, query=q, number_of_results=len(items),
    )


# ============================================================================
# DuckDuckGo-compat: GET /duckduckgo/search
# ============================================================================
#
# DuckDuckGo's Instant Answer API returns
# `{"AbstractText": "...", "RelatedTopics": [{FirstURL, Text}]}`. The
# smolagents default `DuckDuckGoSearchTool` hits `api.duckduckgo.com/?q=...`
# expecting that shape. We mount it at `/duckduckgo/search` so any client
# pointing `DDG_API_URL` (or rerouting the host) at the shim gets compat.

class DDGRelatedTopic(BaseModel):
    FirstURL: str
    Text: str


class DDGResponse(BaseModel):
    AbstractText: str
    AbstractURL: str = ""
    Heading: str = ""
    RelatedTopics: list[DDGRelatedTopic]


@app.get("/duckduckgo/search", response_model=DDGResponse)
def duckduckgo_search(
    q: str = Query(...),
    format: str = Query(default="json"),
    no_html: int = Query(default=1),
    skip_disambig: int = Query(default=1),
    count: int = Query(default=10, ge=0, le=50),
) -> DDGResponse:
    """DuckDuckGo Instant Answer compat (`api.duckduckgo.com/?q=...`). Used
    by smolagents' default `DuckDuckGoSearchTool`. Returns
    `{"AbstractText": "...", "RelatedTopics": [{FirstURL, Text}]}`."""
    hits = _search_recorded(q, endpoint="/duckduckgo/search", max_results=count)
    hits = _filter_hits_strict(hits, endpoint="/duckduckgo/search", query=q)
    abstract = hits[0].content if hits else ""
    abstract_url = hits[0].url if hits else ""
    heading = hits[0].title if hits else q
    related = [
        DDGRelatedTopic(FirstURL=h.url, Text=f"{h.title} - {h.content}")
        for h in hits
    ]
    return DDGResponse(
        AbstractText=abstract,
        AbstractURL=abstract_url,
        Heading=heading,
        RelatedTopics=related,
    )


# ============================================================================
# OpenAI-compat LLM passthrough: POST /llm/v1/chat/completions
# ============================================================================
#
# Frameworks that hard-code an `OPENAI_BASE_URL` (e.g. `gpt-researcher`,
# `langchain` with a fixed base) sometimes prefer to share the shim's host
# rather than juggle a second port. This endpoint simply proxies to the
# ds_proxy on :8088 (which itself injects `thinking:disabled` for
# `deepseek-v4-*`). Auth header is accepted but ignored: ds_proxy uses its
# own server-side key.

_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL | re.IGNORECASE)


def _strip_thinking(content: str) -> str:
    """Remove ``<think>...</think>`` blocks emitted by Qwen3 / DeepSeek-R1 /
    other reasoning models. Frameworks calling the shim expect a flat
    assistant message, not a reasoning trace."""
    if not content:
        return content
    return _THINK_TAG_RE.sub("", content).lstrip("\n")


@app.post("/llm/v1/chat/completions")
async def llm_chat_completions(
    body: dict[str, Any],
    authorization: Optional[str] = Header(default=None),
) -> Any:
    """OpenAI-compat passthrough → ds_proxy:8088 (or any OpenAI-compat
    upstream set via SHIM_LLM_UPSTREAM env, e.g. an LM Studio Qwen3 server).

    Post-processes each choice's ``message.content`` to strip
    ``<think>...</think>`` blocks so reasoning-model output looks normal
    to client frameworks.
    """
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    if LLM_REWRITE_MODEL and isinstance(body, dict):
        body = {**body, "model": LLM_REWRITE_MODEL}
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{LLM_UPSTREAM}/chat/completions", json=body, headers=headers,
        )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=r.status_code,
                detail=r.text,
            )
        data = r.json()
        for choice in data.get("choices", []) or []:
            msg = choice.get("message") or {}
            if "content" in msg and isinstance(msg["content"], str):
                msg["content"] = _strip_thinking(msg["content"])
        return data


# ============================================================================
# Anthropic-compat LLM passthrough: POST /llm/v1/messages
# ============================================================================
#
# Frameworks that expect Claude (e.g. anything written against
# `anthropic.Anthropic`) hit `/v1/messages` with
# `{model, system, messages: [{role, content}], max_tokens}`. We translate to
# OpenAI chat-completions, proxy to ds_proxy:8088, then translate the response
# back so the framework sees a normal Anthropic envelope.

class AnthropicMessage(BaseModel):
    model_config = {"extra": "ignore"}

    role: str
    content: Any  # str OR list of {type, text} blocks


class AnthropicMessagesRequest(BaseModel):
    model_config = {"extra": "ignore"}

    model: str
    messages: list[AnthropicMessage]
    system: Any = None  # str OR list of {type, text}
    max_tokens: int = 1024
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stop_sequences: Optional[list[str]] = None


def _anthropic_content_to_text(content: Any) -> str:
    """Anthropic content can be a plain string or a list of content blocks
    `[{"type": "text", "text": "..."}]`. Flatten to plain text for OpenAI."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content is not None else ""


@app.post("/llm/v1/messages")
async def llm_messages(
    req: AnthropicMessagesRequest,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Anthropic-compat passthrough → ds_proxy:8088. Translates Anthropic's
    `{model, system, messages, max_tokens}` to OpenAI chat-completions and
    translates the response back to Anthropic's `{id, type, role, content,
    stop_reason, usage}` envelope. Used by frameworks expecting Claude."""
    openai_messages: list[dict[str, str]] = []
    sys_text = _anthropic_content_to_text(req.system)
    if sys_text:
        openai_messages.append({"role": "system", "content": sys_text})
    for m in req.messages:
        openai_messages.append({
            "role": m.role,
            "content": _anthropic_content_to_text(m.content),
        })

    openai_body: dict[str, Any] = {
        "model": req.model,
        "messages": openai_messages,
        "max_tokens": req.max_tokens,
    }
    if req.temperature is not None:
        openai_body["temperature"] = req.temperature
    if req.top_p is not None:
        openai_body["top_p"] = req.top_p
    if req.stop_sequences:
        openai_body["stop"] = req.stop_sequences

    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    elif x_api_key:
        headers["Authorization"] = f"Bearer {x_api_key}"

    timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{LLM_UPSTREAM}/chat/completions",
            json=openai_body, headers=headers,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        upstream = r.json()

    # Translate OpenAI -> Anthropic.
    choice = (upstream.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    finish_reason = choice.get("finish_reason") or "end_turn"
    stop_reason = {
        "stop": "end_turn",
        "length": "max_tokens",
        "content_filter": "stop_sequence",
        "tool_calls": "tool_use",
    }.get(finish_reason, "end_turn")
    usage_oai = upstream.get("usage") or {}
    return {
        "id": upstream.get("id") or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": upstream.get("model") or req.model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage_oai.get("prompt_tokens", 0),
            "output_tokens": usage_oai.get("completion_tokens", 0),
        },
    }


# ============================================================================
# Health
# ============================================================================

@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "version": app.version,
        "mode": _shim_mode(),
        **_build_identity(),
    }


# ============================================================================
# Direct CLI launch: `python integrations/search_shim/app.py --mode strict`
# ============================================================================
#
# Most callers run the shim via `uvicorn integrations.search_shim.app:app`,
# but the arena harness wants a one-shot CLI that takes `--mode strict`
# (sets SHIM_MODE=strict for the lifetime of the process) so the operator
# does not have to remember to export an env var separately.
#
# Either approach works: strict mode is keyed off the SHIM_MODE env var
# inside the request path, so `SHIM_MODE=strict uvicorn ...` is equivalent.
# This `__main__` block is just the convenience entrypoint.

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Tavily/Firecrawl/Serper/Brave compatible shim over the "
                    "Deep Research Arena sandbox.",
    )
    ap.add_argument(
        "--mode", choices=("open", "strict"),
        default=os.environ.get("SHIM_MODE", "open"),
        help=(
            "open: every backend hit flows through unchanged (default, "
            "previous behavior). "
            "strict: enforce the sandbox URL allowlist: non-allowlist "
            "URLs are dropped from /search responses and rejected with "
            "HTTP 403 from /extract|/scrape, and every block is logged "
            "to logs/shim_blocks.jsonl. Equivalent to SHIM_MODE=strict."
        ),
    )
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--reload", action="store_true", help="uvicorn auto-reload")
    args = ap.parse_args()

    # The gate reads SHIM_MODE at request time, so we just set it.
    os.environ["SHIM_MODE"] = args.mode
    print(f"[shim] mode={args.mode} host={args.host} port={args.port}")
    if args.mode == "strict":
        print(f"[shim] allowlist hosts: {SHIM_ALLOWLIST_HOSTS}")
        print(f"[shim] blocks logged to: {_SHIM_BLOCKS_LOG}")

    import uvicorn  # type: ignore
    uvicorn.run(
        "integrations.search_shim.app:app",
        host=args.host, port=args.port, reload=args.reload,
    )
