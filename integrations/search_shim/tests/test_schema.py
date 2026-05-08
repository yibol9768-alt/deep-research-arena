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


# ---------------------------------------------------------------------------
# SearxNG-compat
# ---------------------------------------------------------------------------

def test_searxng_schema(client: TestClient) -> None:
    """SearxNG returns `{"results": [{url, title, content}], "query": "..."}`."""
    r = client.get(
        "/searxng/search",
        params={"q": "anc headphones", "format": "json", "pageno": 1},
    )
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"results", "query"}
    assert data["query"] == "anc headphones"
    item = data["results"][0]
    assert {"url", "title", "content"} <= set(item.keys())


# ---------------------------------------------------------------------------
# DuckDuckGo-compat
# ---------------------------------------------------------------------------

def test_duckduckgo_schema(client: TestClient) -> None:
    """DDG Instant Answer returns `{"AbstractText", "RelatedTopics": [{FirstURL, Text}]}`."""
    r = client.get("/duckduckgo/search", params={"q": "anc headphones"})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"AbstractText", "RelatedTopics"}
    assert data["AbstractText"]  # populated from top hit
    topic = data["RelatedTopics"][0]
    assert {"FirstURL", "Text"} <= set(topic.keys())
    assert topic["FirstURL"].startswith("http")


# ---------------------------------------------------------------------------
# OpenAI-compat passthrough — mock httpx so we don't hit ds_proxy
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
# Anthropic-compat passthrough — mock httpx, verify Anthropic envelope
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
