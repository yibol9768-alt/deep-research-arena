"""Smoke tests for the three V2 sanity baselines.

Each test:
    1. Starts a tiny in-process FastAPI stub of the search shim on port 8085
       returning 5 fake Tavily results.
    2. Sets ``_FLOWSEARCHER_TASK_ID=dr_cross_deep_0001`` (random / golden_dump
       baselines read this env var; see
       ``integrations/agents/baselines/random.py:run``).
    3. Builds an :class:`AgentServices` pointing search_url at the stub.
    4. Calls ``await agent.run(intent, services)``.
    5. Asserts ``result.error is None`` and ``len(result.markdown) > 100``.
    6. For random / golden_dump: asserts the markdown contains golden URLs.
       For stuffer: asserts the markdown contains the stub's content text.

The harness deliberately does NOT depend on ``pytest-asyncio``; we wrap each
``await`` in :func:`asyncio.run` so the test module works on a vanilla pytest
install.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Local imports must come after sys.path injection.
from integrations.agents import get_agent  # noqa: E402
from integrations.agents.base import AgentServices  # noqa: E402

TASK_ID = "dr_cross_deep_0001"
STUB_PORT = 8085
STUB_HOST = "127.0.0.1"
STUB_URL = f"http://{STUB_HOST}:{STUB_PORT}"

# A canary substring we plant in every stub result's ``content`` field so the
# stuffer test can assert verbatim passthrough.
STUB_CONTENT_CANARY = "STUB_CONTENT_CANARY_TOKEN_XYZ123"

# Five fake Tavily-shaped results pointing at sandbox URLs (real shopping host).
FAKE_RESULTS = [
    {
        "title": f"Fake result {i}",
        "url": f"http://localhost:7770/sony-{i}.html",
        "content": (
            f"Snippet {i} body referencing sandbox product. "
            f"{STUB_CONTENT_CANARY}"
        ),
    }
    for i in range(1, 6)
]


def _port_free(port: int, host: str = STUB_HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _wait_for_port(port: int, host: str = STUB_HOST, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"port {host}:{port} did not come up within {timeout}s")


def _build_stub_app():
    """Build a FastAPI app exposing ``POST /search`` Tavily-shaped."""
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/search")
    async def search(payload: dict):  # noqa: ANN001 — raw body fine for stub
        return {"results": FAKE_RESULTS, "query": payload.get("query", "")}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stub_server():
    """Run the FastAPI stub on STUB_PORT in a background thread.

    Yields the base URL string. Cleans up by signalling uvicorn to shut down
    after the module completes.
    """
    if not _port_free(STUB_PORT):
        pytest.skip(f"port {STUB_PORT} already bound; skipping baseline smoke")

    import uvicorn

    app = _build_stub_app()
    config = uvicorn.Config(
        app=app,
        host=STUB_HOST,
        port=STUB_PORT,
        log_level="warning",
        loop="asyncio",
        lifespan="off",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_port(STUB_PORT)
        yield STUB_URL
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)


@pytest.fixture
def services(stub_server: str) -> AgentServices:
    """Build an :class:`AgentServices` whose search_url points at the stub."""
    return AgentServices(
        search_url=stub_server,
        # Baselines never call the LLM, so any string works for the URL/key.
        llm_url="http://127.0.0.1:8085/llm-not-used",
        llm_key="not-used",
        sandbox_hosts={
            "shopping": "localhost:7770",
            "reddit": "localhost:9999",
            "wiki": "localhost:8090",
        },
        model="deepseek-v4-flash",
    )


@pytest.fixture
def task_env(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set ``_FLOWSEARCHER_TASK_ID`` to the test fixture task id."""
    monkeypatch.setenv("_FLOWSEARCHER_TASK_ID", TASK_ID)
    return TASK_ID


@pytest.fixture(scope="module")
def golden_urls() -> list[str]:
    """All must-cite URLs for the test task, used for substring assertions."""
    p = ROOT / "data" / "golden" / "deep" / f"{TASK_ID}.json"
    raw = json.loads(p.read_text())
    urls = [e.get("url", "") for e in raw.get("must_cite_urls", []) if e.get("url")]
    if not urls:
        pytest.fail(f"golden file {p} has no must_cite_urls")
    return urls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_agent(name: str, intent: str, services: AgentServices):
    """Synchronously execute ``agent.run`` for one of the registered slugs."""
    agent = get_agent(name)
    return asyncio.run(agent.run(intent, services))


def _assert_baseline_ok(result, *, name: str) -> None:
    assert result.error is None, f"{name}: agent errored: {result.error!r}"
    assert isinstance(result.markdown, str), f"{name}: markdown is not str"
    assert len(result.markdown) > 100, (
        f"{name}: markdown too short ({len(result.markdown)} chars), "
        f"head={result.markdown[:200]!r}"
    )
    # Defensive: baselines signal soft failures via "(... error: ...)" prefix.
    assert not result.markdown.startswith("("), (
        f"{name}: baseline emitted soft-error sentinel: {result.markdown[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


INTENT = (
    "Compile a cross-source landscape on consumer headphones / earbuds with "
    "supporting evidence from shopping, Reddit, and Wikipedia."
)


def test_baseline_random_smoke(services: AgentServices, task_env: str,
                               golden_urls: list[str]) -> None:
    """baseline-random: pulls golden pool URLs into a placeholder report."""
    result = _run_agent("baseline-random", INTENT, services)
    _assert_baseline_ok(result, name="baseline-random")

    # The random baseline samples 60 URLs from the golden pool. It should
    # contain at least one (in practice many) golden URL verbatim.
    hits = sum(1 for u in golden_urls if u in result.markdown)
    assert hits >= 5, (
        f"baseline-random: expected ≥5 golden URLs in markdown, got {hits}; "
        f"sample={golden_urls[:3]}"
    )


def test_baseline_stuffer_smoke(services: AgentServices) -> None:
    """baseline-stuffer: hits the stub once and inlines result content."""
    # Stuffer does NOT need _FLOWSEARCHER_TASK_ID; it only calls the shim.
    result = _run_agent("baseline-stuffer", INTENT, services)
    _assert_baseline_ok(result, name="baseline-stuffer")

    # The stub plants STUB_CONTENT_CANARY into every result's content field;
    # the stuffer concatenates `content` verbatim, so the canary must appear.
    assert STUB_CONTENT_CANARY in result.markdown, (
        "baseline-stuffer: stub canary not found in markdown — content not "
        "passed through verbatim"
    )

    # Each fake URL should also appear (links rendered as [title](url)).
    for r in FAKE_RESULTS:
        assert r["url"] in result.markdown, (
            f"baseline-stuffer: missing url {r['url']!r} in markdown"
        )


def test_baseline_golden_dump_smoke(services: AgentServices, task_env: str,
                                    golden_urls: list[str]) -> None:
    """baseline-golden-dump: dumps every must-cite URL verbatim."""
    result = _run_agent("baseline-golden-dump", INTENT, services)
    _assert_baseline_ok(result, name="baseline-golden-dump")

    # golden_dump emits ALL must-cite URLs — assert a comfortable majority
    # appear so a regression that drops half the list still trips the test.
    hits = sum(1 for u in golden_urls if u in result.markdown)
    assert hits >= max(10, len(golden_urls) // 2), (
        f"baseline-golden-dump: expected ≥{max(10, len(golden_urls)//2)} "
        f"golden URLs in markdown, got {hits}/{len(golden_urls)}"
    )
