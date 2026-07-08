"""Regression test for the bounded retry loop (D13).

The retry loops in ds_proxy used to be unbounded `while True`: a persistent
upstream 429/5xx would spin forever and hang a whole #39 run. These tests
drive both the non-streaming and streaming paths against a mock upstream that
ALWAYS 429s and assert the proxy gives up after RETRY_MAX_ATTEMPTS and returns
an explicit `upstream_retry_exhausted` error instead of looping.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from integrations.ds_proxy import app as dsapp


class _FakeResp:
    def __init__(self, status_code=429, body=None, ctype="application/json"):
        self.status_code = status_code
        self._body = json.dumps(body or {"error": {"code": "rate_limit"}}).encode()
        self.headers = {"content-type": ctype}

    @property
    def content(self):
        return self._body

    def json(self):
        return json.loads(self._body)

    @property
    def text(self):
        return self._body.decode()

    async def aread(self):
        return self._body

    async def aclose(self):
        return None


class _FakeClient:
    """Counts calls; every request 429s (retryable)."""
    calls = {"post": 0, "send": 0}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        _FakeClient.calls["post"] += 1
        return _FakeResp()

    def build_request(self, *a, **k):
        return object()

    async def send(self, *a, **k):
        _FakeClient.calls["send"] += 1
        return _FakeResp()

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast_pause(reason, attempt, delay, model):
        return 0.0
    monkeypatch.setattr(dsapp, "_retry_pause", _fast_pause)
    monkeypatch.setattr(dsapp, "RETRY_MAX_ATTEMPTS", 4)
    monkeypatch.setattr(dsapp.httpx, "AsyncClient", _FakeClient)
    _FakeClient.calls = {"post": 0, "send": 0}
    yield


def test_nonstreaming_retry_gives_up():
    client = TestClient(dsapp.app)
    r = client.post("/v1/chat/completions",
                    json={"model": "deepseek-v4-flash", "messages": []})
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["type"] == "upstream_retry_exhausted"
    assert err["attempts"] == 4
    # exactly RETRY_MAX_ATTEMPTS upstream calls, then it stops (no infinite loop)
    assert _FakeClient.calls["post"] == 4


def test_streaming_retry_gives_up():
    client = TestClient(dsapp.app)
    r = client.post("/v1/chat/completions",
                    json={"model": "deepseek-v4-flash", "messages": [], "stream": True})
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["type"] == "upstream_retry_exhausted"
    assert err["attempts"] == 4
    assert _FakeClient.calls["send"] == 4


def test_default_cap_is_eight():
    # guard the documented default so a future edit can't silently unbound it
    import importlib
    import integrations.ds_proxy.app as fresh
    importlib.reload(fresh)
    assert fresh.RETRY_MAX_ATTEMPTS == 8
