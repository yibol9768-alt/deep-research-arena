from __future__ import annotations

import asyncio

from scripts.runners import serper_adapter as adapter_module


def test_adapter_internal_shim_hop_ignores_process_proxy(monkeypatch):
    seen: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            seen["status_checked"] = True

        def json(self):
            return {"results": [{"url": "http://localhost:9999/result"}]}

    class FakeClient:
        def __init__(self, *, trust_env, timeout):
            seen["trust_env"] = trust_env
            seen["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json):
            seen["url"] = url
            seen["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(adapter_module.httpx, "AsyncClient", FakeClient)
    adapter = adapter_module.SerperAdapter("http://10.240.7.1:18410")

    result = asyncio.run(adapter._query_shim("headphones for glasses", 7))

    assert result["results"][0]["url"] == "http://localhost:9999/result"
    assert seen == {
        "trust_env": False,
        "timeout": 60.0,
        "url": "http://10.240.7.1:18410/search",
        "payload": {"query": "headphones for glasses", "max_results": 7},
        "status_checked": True,
    }
