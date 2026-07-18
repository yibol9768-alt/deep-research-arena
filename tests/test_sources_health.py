"""The pre-run source check must be honest and must not contaminate the run.

Two ways this guard could quietly fail:

1. It probes through the recorded `/search` chokepoint. Then the health check's
   own hits land in the open run's evidence log, inflating `search_returned` --
   the denominator of `pof` and the set that decides `snippet_only` vs
   `hallucinated_grounding`. The instrument would alter what it measures.

2. It serves a cached verdict. A source that died since the last probe stays
   green for the rest of the TTL, and the runs launched in that window are scored
   against a corpus they could not see. `run_deep_task` therefore asks for
   `?fresh=true`.
"""

from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.search_shim import app as shim_app  # noqa: E402
from integrations.search_shim import backend, evidence  # noqa: E402
from src.eval.fetch_log import load_run_evidence  # noqa: E402


class _Hit:
    def __init__(self, url):
        self.url = url
        self.title = "t"
        self.content = "c"
        self.score = 1.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SHIM_EVIDENCE", "1")
    evidence.reset_for_tests()
    shim_app._SOURCES_CACHE.update(at=0.0, payload=None)
    return TestClient(shim_app.app), tmp_path


def _fake_search(alive):
    def go(query, max_results=5, **kw):
        backend._diag_store().clear()
        hits = []
        for src, n in alive.items():
            for i in range(n):
                hits.append(_Hit(f"http://localhost:9999/{src}/{i}"))
            backend._set_diag(src, n, None if n else "connection refused")
        return hits
    return go


def test_all_sources_up_is_ok(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 2, "forum": 2, "wiki": 2}))
    h = c.get("/_sources/health").json()
    assert h["ok"] is True and not h["down"]


def test_a_dead_store_is_not_ok(client, monkeypatch):
    """Zero hits from one source while others answer is the exact shape of the
    bug that hid the store for the life of the project."""
    c, _ = client
    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 0, "forum": 2, "wiki": 2}))
    h = c.get("/_sources/health").json()
    assert h["ok"] is False
    assert "shopping" in h["down"]


def test_a_source_never_queried_is_not_ok(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(shim_app, "search", _fake_search({"forum": 2, "wiki": 2}))
    h = c.get("/_sources/health").json()
    assert h["ok"] is False
    assert "shopping" in h["not_queried"]


def test_fresh_bypasses_the_cache(client, monkeypatch):
    """A source that dies mid-campaign must not stay green for the whole TTL."""
    c, _ = client
    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 2, "forum": 2, "wiki": 2}))
    assert c.get("/_sources/health").json()["ok"] is True

    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 0, "forum": 2, "wiki": 2}))
    assert c.get("/_sources/health").json()["cached"] is True, "expected a cache hit"
    assert c.get("/_sources/health").json()["ok"] is True, "stale verdict, as designed"

    fresh = c.get("/_sources/health?fresh=true").json()
    assert fresh["cached"] is False and fresh["ok"] is False, \
        "run_deep_task asks for fresh; a dead source must surface"


def test_health_probe_does_not_write_into_the_open_run(client, monkeypatch):
    """The probe must not inflate `search_returned`, which is `pof`'s denominator."""
    c, tmp = client
    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 2, "forum": 2, "wiki": 2}))
    evidence.mark_start({"run_id": "r1", "lane": "L", "task": "T", "backbone": "B"})
    c.get("/_sources/health?fresh=true")
    evidence.mark_end({"run_id": "r1"})

    log = tmp / "r1.jsonl"
    if not log.exists():
        return  # nothing recorded at all is also "did not contaminate"
    ev = load_run_evidence(log)
    assert not ev.searches, "the health probe was recorded as the agent's search"
    assert not ev.search_returned, "probe URLs entered the pof denominator"


def test_kiwix_search_has_bounded_cold_start_headroom(monkeypatch):
    """A healthy cold Kiwix query can exceed the generic 20-second deadline."""
    seen = {}

    def fake_get_source(source, base, public, path, *, params=None, timeout=20):
        seen.update(source=source, path=path, timeout=timeout, params=params)
        return SimpleNamespace(text='<ul class="results"></ul>')

    monkeypatch.setattr(backend, "_get_source", fake_get_source)
    assert backend._search_kiwix("headphones", 5) == []
    assert seen["source"] == "wiki" and seen["path"] == "/search"
    assert seen["timeout"] == backend.KIWIX_SEARCH_TIMEOUT_S
    assert seen["timeout"] >= 45


# --- the run-time gate, not just preflight ---------------------------------

def test_health_reports_the_urls_it_would_hand_the_agent(client, monkeypatch):
    """Liveness alone cannot see the box's actual failure.

    On the box today the store answers with three hits whose URLs carry a host
    `url_registry` does not list, so `classify` returns `host_not_in_sandbox` and
    the scorer counts a citation of them as FABRICATED. `ok` is True and the run
    would start. The shim has no registry; it hands the sample back so the
    harness, which does, can refuse.
    """
    c, _ = client
    monkeypatch.setattr(shim_app, "search",
                        _fake_search({"shopping": 2, "forum": 1, "wiki": 1}))
    h = c.get("/_sources/health?fresh=true").json()
    assert h["ok"] is True
    assert len(h["sample_urls"]) == 4
    assert all(u.startswith("http://") for u in h["sample_urls"])


def test_harness_refuses_when_the_tool_returns_off_registry_urls(monkeypatch):
    import scripts.run_deep_task as rdt

    class _Reg:
        def classify(self, u):
            return {"in_corpus": ":7770" in u}

    monkeypatch.setattr("src.eval.closed_world_eval.load_registry", lambda *a, **k: _Reg())

    good = ["http://localhost:7770/sony-xm4.html"]
    bad = ["http://localhost:17770/sony-xm4.html"]
    assert rdt._uncorpus_sample(good) == []
    assert rdt._uncorpus_sample(bad) == bad, \
        "the agent would be scored as fabricating a URL the tool gave it"


def test_missing_registry_does_not_block_the_run(monkeypatch):
    """A registry we cannot load is the scorer's refusal to make, not a guess here."""
    import scripts.run_deep_task as rdt
    monkeypatch.setattr("src.eval.closed_world_eval.load_registry", lambda *a, **k: None)
    assert rdt._uncorpus_sample(["http://localhost:17770/x.html"]) == []
