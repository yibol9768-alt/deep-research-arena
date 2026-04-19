"""FastAPI app exposing Tavily + Firecrawl compatible endpoints backed by
our Magento + Postmill sandbox.

Run:
    uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081

Auth is intentionally lax: any `Authorization: Bearer tvly-*` or
`X-Subscription-Token: *` is accepted. Do NOT deploy to the public
internet without adding a real token gate.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .backend import SearchHit, extract, search


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
    include_answer: bool | str = False
    include_raw_content: bool | str = False
    include_images: bool = False
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    time_range: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    country: str | None = None


class TavilySearchResultItem(BaseModel):
    title: str
    url: str
    content: str
    score: float
    raw_content: str | None = None


class TavilySearchResponse(BaseModel):
    query: str
    answer: str | None = None
    images: list[dict] = []
    results: list[TavilySearchResultItem]
    response_time: float
    request_id: str


def _hit_to_tavily(h: SearchHit, include_raw: bool | str) -> TavilySearchResultItem:
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
    authorization: str | None = Header(default=None),
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
    authorization: str | None = Header(default=None),
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
    formats: list[dict] | list[str] = Field(default_factory=lambda: [{"type": "markdown"}])


class FirecrawlSearchRequest(BaseModel):
    # Lenient: dzhng/deep-research uses Firecrawl JS SDK v1 which sends
    # {query, limit, tbs, filter, lang, country, location, origin, timeout,
    #  scrapeOptions: {formats: ["markdown"]}}. We accept v1 and v2 shapes.
    model_config = {"extra": "ignore"}

    query: str
    limit: int = 5
    sources: list[str] = Field(default_factory=lambda: ["web"])
    scrapeOptions: FirecrawlScrapeOptions | None = None
    lang: str | None = None
    country: str | None = None
    tbs: str | None = None
    filter: str | None = None
    location: str | None = None
    origin: str | None = None
    timeout: int | None = None


class FirecrawlSearchItem(BaseModel):
    title: str
    description: str
    url: str
    markdown: str | None = None


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
    authorization: str | None = Header(default=None),
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
    authorization: str | None = Header(default=None),
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
    html: str | None = None
    metadata: dict


class FirecrawlScrapeResponse(BaseModel):
    success: bool
    data: FirecrawlScrapeData


@app.post("/v1/scrape", response_model=FirecrawlScrapeResponse)
@app.post("/v2/scrape", response_model=FirecrawlScrapeResponse)
def firecrawl_scrape(
    req: FirecrawlScrapeRequest,
    authorization: str | None = Header(default=None),
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
# Health
# ============================================================================

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "version": app.version}
