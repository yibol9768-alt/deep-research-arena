"""Schema-match tests for the FastAPI search_shim endpoints.

Each test pins the exact wire shape that the corresponding upstream framework
expects so we catch drift the moment it happens. We monkey-patch
`backend.search` to a deterministic stub so tests don't depend on the
sandbox actually running, and stub `httpx.AsyncClient` for the two LLM
passthroughs so the upstream ds_proxy is not contacted.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Ensure the project root is importable so `integrations.search_shim.app`
# resolves both inside this package and when pytest is launched from the
# repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from integrations.search_shim import app as app_module  # noqa: E402
from integrations.search_shim.backend import SearchHit  # noqa: E402


_FAKE_HITS = [
    SearchHit(
        url="http://localhost:7770/headphone-x.html",
        title="Headphone X",
        content="Wireless ANC over-ear, $199.99",
        score=0.9,
        source="shopping",
    ),
    SearchHit(
        url="http://localhost:9999/f/headphones/1/best-anc",
        title="r/headphones: Best ANC under $200?",
        content="Discussion thread comparing Sony, Bose, Sennheiser.",
        score=0.7,
        source="reddit",
    ),
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient with `backend.search` stubbed to deterministic hits."""

    def _fake_search(query: str, *, max_results: int = 10, **_kw: Any) -> list[SearchHit]:
        return _FAKE_HITS[:max_results]

    monkeypatch.setattr(app_module, "search", _fake_search)
    return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Existing endpoints: smoke tests that the new code didn't break them
# ---------------------------------------------------------------------------

def test_tavily_search_schema(client: TestClient) -> None:
    r = client.post(
        "/search",
        json={"query": "anc headphones", "max_results": 2},
        headers={"Authorization": "Bearer tvly-test"},
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"query", "results", "response_time", "request_id"}
    assert data["results"] and {"title", "url", "content", "score"} <= set(
        data["results"][0].keys()
    )


def test_tavily_search_raw_content_fetches_pages(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """include_raw_content must serve page text, not duplicate a snippet."""
    seen: dict[str, Any] = {}

    def _fake_extract(urls: Any) -> list[dict]:
        seen["urls"] = list(urls)
        return [
            {
                "url": url,
                "raw_content": f"FULL PAGE FOR {url}",
                "title": "page",
                "source": "sandbox",
                "status": 200,
            }
            for url in seen["urls"]
        ]

    monkeypatch.setenv("SHIM_EVIDENCE", "0")
    monkeypatch.setattr(app_module, "extract", _fake_extract)
    response = client.post(
        "/search",
        json={
            "query": "anc headphones",
            "max_results": 2,
            "include_raw_content": True,
        },
    )

    assert response.status_code == 200
    assert seen == {
        "urls": [hit.url for hit in _FAKE_HITS],
    }
    first = response.json()["results"][0]
    assert first["raw_content"] == f"FULL PAGE FOR {_FAKE_HITS[0].url}"
    assert first["raw_content"] != first["content"]


def test_tavily_search_without_raw_content_does_not_fetch(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    def _unexpected_extract(*_args: Any, **_kwargs: Any) -> list[dict]:
        raise AssertionError("plain Tavily search must remain snippet-only")

    monkeypatch.setattr(app_module, "extract", _unexpected_extract)
    response = client.post(
        "/search",
        json={"query": "anc headphones", "max_results": 2},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["raw_content"] is None


def test_tavily_search_get_schema(client: TestClient) -> None:
    r = client.get("/search", params={"q": "anc headphones", "count": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["query"] == "anc headphones"
    assert len(data["results"]) == 2
    assert {"title", "url", "content", "score"} <= set(data["results"][0].keys())
    assert len(data["web"]["results"]) == 2
    assert {"title", "url", "description"} <= set(data["web"]["results"][0].keys())


# ---------------------------------------------------------------------------
# Serper-compat
# ---------------------------------------------------------------------------

def test_serper_schema(client: TestClient) -> None:
    """Serper expects `{"organic": [{title, link, snippet}], "credits": N}`."""
    r = client.post("/v1/serper", json={"q": "anc headphones", "num": 2})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"organic", "credits"}
    assert data["credits"] == 1
    assert len(data["organic"]) == 2
    item = data["organic"][0]
    assert set(item.keys()) == {"title", "link", "snippet"}
    assert item["link"].startswith("http")


# ---------------------------------------------------------------------------
# Brave-compat
# ---------------------------------------------------------------------------

def test_brave_schema(client: TestClient) -> None:
    """Brave returns `{"web": {"results": [{url, title, description}]}}`."""
    r = client.get("/v1/brave/web/search", params={"q": "anc headphones", "count": 2})
    assert r.status_code == 200
    data = r.json()
    assert "web" in data and "results" in data["web"]
    results = data["web"]["results"]
    assert len(results) == 2
    item = results[0]
    assert set(item.keys()) == {"url", "title", "description"}
    assert client.get(
        "/v1/brave/web/search", params={"q": "anc headphones", "count": 0}
    ).json()["web"]["results"] == []


# ---------------------------------------------------------------------------
# SearxNG-compat
# ---------------------------------------------------------------------------

def test_searxng_schema(client: TestClient) -> None:
    """SearxNG returns `{"results": [{url, title, content}], "query": "..."}`."""
    r = client.get(
        "/searxng/search",
        params={
            "q": "anc headphones",
            "format": "json",
            "pageno": 1,
            "count": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"results", "query"}
    assert data["query"] == "anc headphones"
    assert len(data["results"]) == 1
    item = data["results"][0]
    assert {"url", "title", "content"} <= set(item.keys())


# ---------------------------------------------------------------------------
# DuckDuckGo-compat
# ---------------------------------------------------------------------------

def test_duckduckgo_schema(client: TestClient) -> None:
    """DDG Instant Answer returns `{"AbstractText", "RelatedTopics": [{FirstURL, Text}]}`."""
    r = client.get(
        "/duckduckgo/search",
        params={"q": "anc headphones", "count": 1},
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"AbstractText", "RelatedTopics"}
    assert data["AbstractText"]  # populated from top hit
    assert len(data["RelatedTopics"]) == 1
    topic = data["RelatedTopics"][0]
    assert {"FirstURL", "Text"} <= set(topic.keys())
    assert topic["FirstURL"].startswith("http")


# ---------------------------------------------------------------------------
# OpenAI-compat passthrough: mock httpx so we don't hit ds_proxy
# ---------------------------------------------------------------------------

class _StubAsyncResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""

    def json(self) -> dict:
        return self._payload


class _StubAsyncClient:
    """Captures the last POST call and returns a pre-canned JSON payload."""

    last_url: str | None = None
    last_json: dict | None = None
    payload: dict = {}
    status_code: int = 200

    def __init__(self, *_a: Any, **_kw: Any) -> None: ...
    async def __aenter__(self) -> "_StubAsyncClient":
        return self
    async def __aexit__(self, *_a: Any) -> None: ...

    async def post(self, url: str, *, json: dict, headers: dict) -> _StubAsyncResponse:
        type(self).last_url = url
        type(self).last_json = json
        return _StubAsyncResponse(type(self).status_code, type(self).payload)


def test_openai_passthrough(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """`POST /llm/v1/chat/completions` proxies to ds_proxy and returns
    upstream JSON verbatim."""
    upstream_payload = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "deepseek-v4-flash",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hello"},
             "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    _StubAsyncClient.payload = upstream_payload
    _StubAsyncClient.status_code = 200
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _StubAsyncClient)

    body = {"model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8}
    r = client.post(
        "/llm/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer anything"},
    )
    assert r.status_code == 200
    assert r.json() == upstream_payload
    # Body forwarded verbatim to ds_proxy chat-completions endpoint.
    assert _StubAsyncClient.last_url and _StubAsyncClient.last_url.endswith("/chat/completions")
    assert _StubAsyncClient.last_json == body


# ---------------------------------------------------------------------------
# Anthropic-compat passthrough: mock httpx, verify Anthropic envelope
# ---------------------------------------------------------------------------

def test_anthropic_passthrough(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """`POST /llm/v1/messages` translates Anthropic body to OpenAI, proxies,
    and translates response back into Anthropic envelope."""
    _StubAsyncClient.payload = {
        "id": "chatcmpl-7",
        "model": "deepseek-v4-flash",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hi there"},
             "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    _StubAsyncClient.status_code = 200
    monkeypatch.setattr(app_module.httpx, "AsyncClient", _StubAsyncClient)

    r = client.post(
        "/llm/v1/messages",
        json={
            "model": "claude-sonnet-4",
            "system": "You are helpful.",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hello"}]}
            ],
            "max_tokens": 32,
        },
        headers={"x-api-key": "sk-test"},
    )
    assert r.status_code == 200
    data = r.json()

    # Anthropic envelope shape.
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["stop_reason"] == "end_turn"
    assert data["content"] == [{"type": "text", "text": "hi there"}]
    assert data["usage"] == {"input_tokens": 12, "output_tokens": 3}

    # Forwarded body should be OpenAI chat-completions shape with system flattened.
    sent = _StubAsyncClient.last_json or {}
    assert sent["model"] == "claude-sonnet-4"
    assert sent["max_tokens"] == 32
    assert sent["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert sent["messages"][1] == {"role": "user", "content": "hello"}


# ---------------------------------------------------------------------------
# firecrawl_scrape: a failed fetch must NOT be reported as an empty success
# ---------------------------------------------------------------------------

def test_firecrawl_scrape_failed_fetch_is_error(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """extract()'s except branch returns a row with status=0, no raw_content,
    and an 'error' field. The scrape endpoint must surface that as an HTTP
    error, not success=True with empty markdown."""

    def _fake_extract(urls: Any) -> list[dict]:
        # Exact shape produced by backend.extract() on a request exception.
        return [{
            "url": list(urls)[0],
            "raw_content": "",
            "title": "",
            "source": "",
            "status": 0,
            "error": "ConnectionError: refused",
        }]

    monkeypatch.setattr(app_module, "extract", _fake_extract)
    r = client.post("/v2/scrape", json={"url": "http://localhost:7770/dead.html"})
    assert r.status_code >= 400
    # The old buggy guard returned 200 with success=True and empty markdown.
    assert r.status_code != 200


def test_firecrawl_scrape_success(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A genuine fetch with raw_content and status<400 still succeeds."""

    def _fake_extract(urls: Any) -> list[dict]:
        return [{
            "url": list(urls)[0],
            "raw_content": "Full page markdown here.",
            "title": "Headphone X",
            "source": "shopping",
            "status": 200,
            "elapsed_ms": 12,
        }]

    monkeypatch.setattr(app_module, "extract", _fake_extract)
    r = client.post("/v2/scrape", json={"url": "http://localhost:7770/headphone-x.html"})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["data"]["markdown"] == "Full page markdown here."


def test_tavily_extract_advanced_is_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Only an explicit advanced request may use the v3 extraction path."""
    seen: dict[str, Any] = {}

    def _fake_extract(urls: Any, *, extract_depth: str) -> list[dict]:
        seen["urls"] = list(urls)
        seen["extract_depth"] = extract_depth
        return [{
            "url": seen["urls"][0],
            "raw_content": "title\n\nmain\n\ndetails",
            "title": "title",
            "source": "shopping",
            "status": 200,
        }]

    monkeypatch.setenv("SHIM_EVIDENCE", "0")
    monkeypatch.setattr(app_module, "extract", _fake_extract)
    r = client.post(
        "/extract",
        json={
            "urls": ["http://localhost:7770/headphone-x.html"],
            "extract_depth": "advanced",
        },
    )
    assert r.status_code == 200
    assert seen == {
        "urls": ["http://localhost:7770/headphone-x.html"],
        "extract_depth": "advanced",
    }
    assert r.json()["results"][0]["raw_content"] == "title\n\nmain\n\ndetails"


# ---------------------------------------------------------------------------
# post_lookup: field names must align with get_submission's actual keys
# ---------------------------------------------------------------------------

def test_post_lookup_field_mapping(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """get_submission returns num_comments / body_html / comments (list) and
    no top-level forum. post_lookup must map those to comment_count / body /
    forum (derived from the URL) instead of returning None."""

    def _fake_get_submission(url: str, **_kw: Any) -> dict:
        return {
            "url": url,
            "title": "Best ANC under $200?",
            "score": 42,
            "author": "alice",
            "body_html": "<p>Looking for <b>quiet</b> headphones.</p>",
            "comments": [{"author": "bob", "body": "Sony.", "score": 5}],
            "num_comments": 1,
        }

    monkeypatch.setattr(app_module, "_get_submission", _fake_get_submission)

    r = client.post(
        "/post_lookup",
        json={"url": "http://localhost:9999/f/headphones/1/best-anc"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["comment_count"] == 1  # mapped from num_comments, not None
    assert data["body"] == "Looking for quiet headphones."  # from body_html
    assert data["forum"] == "headphones"  # derived from the URL path
    assert len(data["top_comments"]) == 1


# ---------------------------------------------------------------------------
# Strict mode: post_lookup / product_lookup must honor the URL allowlist
# ---------------------------------------------------------------------------

def test_post_lookup_strict_blocks_offlist_url(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """In strict mode an off-allowlist URL must be rejected with 403 BEFORE
    any fetch, not silently fetched (SSRF / closed-book violation)."""
    monkeypatch.setenv("SHIM_MODE", "strict")

    def _boom(*_a: Any, **_kw: Any) -> dict:
        raise AssertionError("get_submission must not be called for blocked URL")

    monkeypatch.setattr(app_module, "_get_submission", _boom)

    r = client.post("/post_lookup", json={"url": "http://evil.example.com/x"})
    assert r.status_code == 403


def test_product_lookup_strict_blocks_offlist_url(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """product_lookup must also enforce the allowlist in strict mode."""
    monkeypatch.setenv("SHIM_MODE", "strict")

    import requests as _requests  # type: ignore

    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("requests.get must not be called for blocked URL")

    monkeypatch.setattr(_requests, "get", _boom)

    r = client.post("/product_lookup", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Strict mode: a sandbox page that 30x-redirects off origin must NOT leak
# off-allowlist content. The pre-fetch gate only sees the requested URL, so
# extract()/product_lookup must not follow redirects in strict mode and must
# re-validate the final response URL.
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for requests.Response with a settable final .url."""

    def __init__(self, *, status_code: int, url: str, text: str = "") -> None:
        self.status_code = status_code
        self.url = url
        self.text = text


def test_extract_strict_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In strict mode extract() must pass allow_redirects=False and treat a
    3xx (returned as-is, no body) as a blocked fetch, not a success."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.setenv("SHIM_MODE", "strict")
    seen_kwargs: dict[str, Any] = {}

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        seen_kwargs.update(kwargs)
        # Sandbox page replies with a 302 to an external host. With
        # allow_redirects=False this 302 is returned verbatim (empty body).
        return _FakeResponse(status_code=302, url=url, text="")

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)

    rows = backend_mod.extract(["http://localhost:7770/p.html"])
    assert seen_kwargs.get("allow_redirects") is False
    assert len(rows) == 1
    row = rows[0]
    assert row["raw_content"] == ""
    assert row.get("error") == "non_sandbox_redirect_blocked"


def test_extract_strict_rejects_offlist_final_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even on a 200, if the final response URL left the allowlist (e.g. a
    transparently-followed redirect in some client), extract() must discard
    the content rather than return off-allowlist HTML."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.setenv("SHIM_MODE", "strict")

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        # Final URL is off-allowlist even though status is 200.
        return _FakeResponse(
            status_code=200,
            url="http://evil.example.com/leak",
            text="<html><body>secret</body></html>",
        )

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)

    rows = backend_mod.extract(["http://localhost:7770/p.html"])
    assert len(rows) == 1
    assert rows[0]["raw_content"] == ""
    assert rows[0].get("error") == "non_sandbox_redirect_blocked"


def test_extract_open_mode_follows_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In open mode (default) behavior is unchanged: redirects are followed
    and content is returned."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.delenv("SHIM_MODE", raising=False)

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        assert kwargs.get("allow_redirects") is True
        return _FakeResponse(
            status_code=200, url=url,
            text="<html><body><main>hello world</main></body></html>",
        )

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)

    rows = backend_mod.extract(["http://localhost:7770/p.html"])
    assert rows[0]["status"] == 200
    assert "hello world" in rows[0]["raw_content"]
    assert "error" not in rows[0]


def test_extract_basic_keeps_legacy_single_product_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default/basic output must not change when advanced extraction is added."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.delenv("SHIM_MODE", raising=False)
    html = """
    <html><body><main>
      <h1>Headphone X</h1>
      <div class="product-info-main">In stock $199.99</div>
      <div class="product info detailed">Over-ear ANC, folds flat, 30 hours.</div>
    </main></body></html>
    """

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(status_code=200, url=url, text=html)

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)
    rows = backend_mod.extract(["http://localhost:7770/headphone-x.html"])
    assert rows[0]["raw_content"] == "In stock $199.99"
    assert "Over-ear ANC" not in rows[0]["raw_content"]


def test_extract_advanced_combines_product_identity_and_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advanced Magento extraction exposes title, offer, and detail sections."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.delenv("SHIM_MODE", raising=False)
    html = """
    <html><body><main>
      <h1>Headphone X</h1>
      <div class="product-info-main">
        In stock $199.99 <a href="/warranty">Warranty</a>
      </div>
      <div class="product info detailed">
        Over-ear ANC, folds flat, 30 hours.
        <a href="/manual">Manual</a>
      </div>
    </main></body></html>
    """

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(status_code=200, url=url, text=html)

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)
    rows = backend_mod.extract(
        ["http://localhost:7770/headphone-x.html"],
        extract_depth="advanced",
    )
    row = rows[0]
    assert row["raw_content"].split("\n\n") == [
        "Headphone X",
        "In stock $199.99 Warranty",
        "Over-ear ANC, folds flat, 30 hours. Manual",
    ]
    assert row["links"] == [
        "http://localhost:7770/warranty",
        "http://localhost:7770/manual",
    ]


def test_extract_advanced_adds_postmill_comments_without_changing_basic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postmill comments are v3 evidence only when advanced is requested."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.delenv("SHIM_MODE", raising=False)
    html = """
    <html><body>
      <article class="submission">
        <header><h1 class="submission__title">Glasses with headphones</h1></header>
        <div class="submission__body">Do glasses hurt headphone performance?</div>
      </article>
      <article class="comment">
        <header>D00M98 wrote</header>
        <div class="comment__body">
          With closed-back headphones, seal is important for bass.
          Glasses will break that seal, reducing bass.
        </div>
      </article>
    </body></html>
    """

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(status_code=200, url=url, text=html)

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)
    url = "http://localhost:9999/f/headphones/61980/example"
    basic = backend_mod.extract([url])[0]
    advanced = backend_mod.extract([url], extract_depth="advanced")[0]
    assert basic["raw_content"] == "Do glasses hurt headphone performance?"
    assert "seal is important for bass" not in basic["raw_content"]
    assert advanced["raw_content"].split("\n\n") == [
        "Glasses with headphones",
        "Do glasses hurt headphone performance?",
        (
            "With closed-back headphones, seal is important for bass. "
            "Glasses will break that seal, reducing bass."
        ),
    ]


def test_extract_advanced_leaves_other_sources_on_basic_content_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advanced is source-specific and must not rewrite Kiwix/general pages."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.delenv("SHIM_MODE", raising=False)
    html = """
    <html><body><main>
      <h1>Active noise control</h1>
      <p>Cancellation uses destructive interference.</p>
    </main></body></html>
    """

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(status_code=200, url=url, text=html)

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)
    url = "http://localhost:8090/content/wiki/Active_noise_control"
    basic = backend_mod.extract([url])[0]
    advanced = backend_mod.extract([url], extract_depth="advanced")[0]
    assert advanced["raw_content"] == basic["raw_content"]
    assert advanced["links"] == basic["links"]


def test_extract_strict_allows_inorigin_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal in-allowlist 200 still succeeds in strict mode."""
    from integrations.search_shim import backend as backend_mod

    monkeypatch.setenv("SHIM_MODE", "strict")

    def _fake_get(url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(
            status_code=200, url=url,
            text="<html><body><main>product page</main></body></html>",
        )

    monkeypatch.setattr(backend_mod.requests, "get", _fake_get)

    rows = backend_mod.extract(["http://localhost:7770/p.html"])
    assert rows[0]["status"] == 200
    assert "product page" in rows[0]["raw_content"]
    assert "error" not in rows[0]


def test_product_lookup_strict_blocks_offlist_redirect(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """product_lookup must 403 when an allowlisted PDP 30x-redirects off
    origin, instead of returning the redirected (off-allowlist) content."""
    monkeypatch.setenv("SHIM_MODE", "strict")

    import requests as _requests  # type: ignore

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        assert kwargs.get("allow_redirects") is False
        # Sandbox PDP responds with a 301 to an external host.
        return _FakeResponse(status_code=301, url="http://evil.example.com/x", text="")

    monkeypatch.setattr(_requests, "get", _fake_get)

    r = client.post("/product_lookup", json={"url": "http://localhost:7770/p.html"})
    assert r.status_code == 403
