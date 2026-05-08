"""FastAPI app exposing Tavily + Firecrawl compatible endpoints backed by
our Magento + Postmill sandbox.

Run:
    uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081

Auth is intentionally lax: any `Authorization: Bearer tvly-*` or
`X-Subscription-Token: *` is accepted. Do NOT deploy to the public
internet without adding a real token gate.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Literal, Optional, Union

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .backend import SearchHit, extract, search


# Upstream OpenAI-compat endpoint (ds_proxy with deepseek-v4-flash). Override
# for tests via env var so a TestClient can point at a stubbed server.
LLM_UPSTREAM = os.environ.get(
    "SHIM_LLM_UPSTREAM", "http://localhost:8088/v1"
).rstrip("/")


app = FastAPI(
    title="Sandbox Search Shim",
    version="0.1.0",
    description="Tavily + Firecrawl-compatible wire protocol over our "
                "Magento + Postmill benchmark sandbox. Lets any research "
                "framework hit our sandbox with zero code change by "
                "overriding TAVILY_API_URL / FIRECRAWL_BASE_URL.",
)


# ============================================================================
# Tavily schema: POST /search, POST /extract
# ============================================================================

class TavilySearchRequest(BaseModel):
    # Lenient schema — real Tavily clients (gpt-researcher, langchain,
    # raw curl) send mildly different payloads. Accept None where list
    # is expected, ignore unknown fields (api_key in body, days, use_cache
    # etc. from gpt-researcher).
    model_config = {"extra": "ignore"}

    query: str
    search_depth: str = "basic"
    topic: str = "general"
    max_results: int = Field(default=5, ge=0, le=50)
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


def _hit_to_tavily(h: SearchHit, include_raw: Union[bool, str]) -> TavilySearchResultItem:
    raw = None
    if include_raw:
        # Defer heavy HTML fetches: extract endpoint is for that.
        # Here we just echo the snippet as raw content.
        raw = h.raw_content or h.content
    return TavilySearchResultItem(
        title=h.title,
        url=h.url,
        content=h.content,
        score=round(h.score, 3),
        raw_content=raw,
    )


@app.post("/search", response_model=TavilySearchResponse)
def tavily_search(
    req: TavilySearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> TavilySearchResponse:
    # Accept any bearer token; reject only if obviously garbage.
    if authorization and not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="expected Bearer token")

    t0 = time.time()
    hits = search(
        req.query,
        max_results=req.max_results or 5,
        include_domains=req.include_domains or [],
        exclude_domains=req.exclude_domains or [],
    )
    return TavilySearchResponse(
        query=req.query,
        results=[_hit_to_tavily(h, req.include_raw_content) for h in hits],
        response_time=round(time.time() - t0, 3),
        request_id=str(uuid.uuid4()),
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
    rows = extract(req.urls)
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
    hits = search(req.query, max_results=req.limit or 5)
    web = [FirecrawlSearchItem(
        title=h.title, description=h.content, url=h.url,
        markdown=h.content,  # shallow — /v2/scrape is where full markdown goes
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
    hits = search(req.query, max_results=req.limit or 5)
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
    rows = extract([req.url])
    if not rows:
        raise HTTPException(status_code=500, detail="extract returned no rows")
    row = rows[0]
    if row.get("status") and row["status"] >= 400:
        raise HTTPException(status_code=row["status"], detail=row.get("error") or "fetch failed")
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
# DB lookup endpoints — structured JSON lookup to equalize info access
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


@app.post("/post_lookup", response_model=PostLookupResponse)
def post_lookup(req: PostLookupRequest) -> PostLookupResponse:
    """Return structured JSON for a single Postmill submission. Delegates
    to envs.reddit.scrape.get_submission (requests-based, no Playwright)."""
    try:
        from envs.reddit.scrape import get_submission  # lazy import
        data = get_submission(req.url)
        if not data or not data.get("title"):
            return PostLookupResponse(ok=False, url=req.url, error="post not found or empty")
        return PostLookupResponse(
            ok=True,
            url=req.url,
            title=data.get("title"),
            author=data.get("author"),
            forum=data.get("forum"),
            score=data.get("score"),
            comment_count=data.get("comment_count"),
            body=data.get("body"),
            top_comments=data.get("comments") or [],
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
    best-effort extractor (no Playwright) — it parses price/rating/sku from
    the server-rendered HTML. Accuracy is lower than the Playwright-based
    envs.shopping.oracle_dr.magento_scrape.product_details, but all agents
    can call it through the shim."""
    import re
    try:
        import requests  # type: ignore
        r = requests.get(req.url, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            return ProductLookupResponse(ok=False, url=req.url,
                                         error=f"HTTP {r.status_code}")
        html = r.text
    except Exception as e:
        return ProductLookupResponse(ok=False, url=req.url,
                                     error=f"{type(e).__name__}: {e}")

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
    hits = search(req.q, max_results=req.num or 10)
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
    hits = search(q, max_results=count or 10)
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
    categories: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
) -> SearxNGResponse:
    """SearxNG meta-search compat (`/search?q=...&format=json&pageno=1`).
    Used by Perplexica and ii-researcher. Returns `{"results": [{url, title,
    content}], "query": "..."}`."""
    hits = search(q, max_results=10)
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
) -> DDGResponse:
    """DuckDuckGo Instant Answer compat (`api.duckduckgo.com/?q=...`). Used
    by smolagents' default `DuckDuckGoSearchTool`. Returns
    `{"AbstractText": "...", "RelatedTopics": [{FirstURL, Text}]}`."""
    hits = search(q, max_results=10)
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
# `deepseek-v4-*`). Auth header is accepted but ignored — ds_proxy uses its
# own server-side key.

@app.post("/llm/v1/chat/completions")
async def llm_chat_completions(
    body: dict[str, Any],
    authorization: Optional[str] = Header(default=None),
) -> Any:
    """OpenAI-compat passthrough → ds_proxy:8088 (deepseek-v4-flash). Body
    fields are forwarded verbatim; upstream JSON is returned verbatim."""
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
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
        return r.json()


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
    return {"ok": True, "version": app.version}
