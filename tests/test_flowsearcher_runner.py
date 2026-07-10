"""Unit tests for scripts/run_flowsearcher.py fixes (2026-07-06).

Covers the three defects fixed this round:
  D1 endpoint precedence: the pure resolver and its env-backed wrappers.
  D2 failure laundering: the honest error-stub shape (and that it classifies
     as a stub rather than a scored real report).
  D3 starved writer: bounded, deterministic page-fetch wiring into the writer
     evidence, with the fetcher monkeypatched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_flowsearcher as fs  # noqa: E402
from src.eval.report_stubs import classify_report  # noqa: E402


# --------------------------------------------------------------------------
# D1: endpoint precedence
# --------------------------------------------------------------------------

def test_resolve_endpoint_precedence_is_pure():
    # explicit wins over everything
    assert fs._resolve_endpoint("A", "B", "C", "D") == "A"
    # arg wins when no explicit
    assert fs._resolve_endpoint(None, "B", "C", "D") == "B"
    # fallback env wins when no explicit/arg
    assert fs._resolve_endpoint(None, None, "C", "D") == "C"
    # default is last resort
    assert fs._resolve_endpoint(None, None, None, "D") == "D"
    # empty strings are treated as absent
    assert fs._resolve_endpoint("", "", "", "D") == "D"


def test_resolve_llm_base_url_precedence(monkeypatch):
    monkeypatch.delenv("FLOWSEARCHER_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DS_PROXY_URL", raising=False)
    # default
    assert fs._resolve_llm_base_url() == fs.DEFAULT_DS_PROXY
    # harness arg beats default
    assert fs._resolve_llm_base_url("http://harness:9000/v1") == "http://harness:9000/v1"
    # DS_PROXY_URL env beats the default but loses to the arg
    monkeypatch.setenv("DS_PROXY_URL", "http://envproxy:8088/v1")
    assert fs._resolve_llm_base_url() == "http://envproxy:8088/v1"
    assert fs._resolve_llm_base_url("http://harness:9000/v1") == "http://harness:9000/v1"
    # explicit flowsearcher env beats the harness arg
    monkeypatch.setenv("FLOWSEARCHER_LLM_BASE_URL", "http://explicit:1/v1")
    assert fs._resolve_llm_base_url("http://harness:9000/v1") == "http://explicit:1/v1"


def test_resolve_shim_url_precedence(monkeypatch):
    monkeypatch.delenv("FLOWSEARCHER_SHIM_URL", raising=False)
    monkeypatch.delenv("SHIM_URL", raising=False)
    assert fs._resolve_shim_url() == fs.DEFAULT_SHIM_URL
    assert fs._resolve_shim_url("http://harness:8081") == "http://harness:8081"
    monkeypatch.setenv("SHIM_URL", "http://envshim:8081")
    assert fs._resolve_shim_url() == "http://envshim:8081"
    assert fs._resolve_shim_url("http://harness:8081") == "http://harness:8081"
    monkeypatch.setenv("FLOWSEARCHER_SHIM_URL", "http://explicit:8081")
    assert fs._resolve_shim_url("http://harness:8081") == "http://explicit:8081"


# --------------------------------------------------------------------------
# D2: honest error stub
# --------------------------------------------------------------------------

def test_error_stub_shape():
    stub = fs._error_stub("write", "LLM writer returned empty after retries")
    assert stub == "(flowsearcher error: write: LLM writer returned empty after retries)"


def test_error_stub_collapses_whitespace_and_caps_reason():
    stub = fs._error_stub("search", "boom\n  with   newlines\tand tabs")
    assert "\n" not in stub and "\t" not in stub
    assert stub == "(flowsearcher error: search: boom with newlines and tabs)"
    long = fs._error_stub("write", "x" * 500)
    # reason capped at 200 chars, plus the fixed prefix/suffix
    assert len(long) < 240


def test_error_stub_is_classified_as_a_stub_not_ok():
    # The whole point of D2: the failure must surface, never score as a report.
    stub = fs._error_stub("write", "LLM writer returned empty after retries")
    assert classify_report(stub) == "stub_exception"
    # The old laundered sentinel must no longer appear anywhere in the module.
    src = (ROOT / "scripts" / "run_flowsearcher.py").read_text()
    assert "(empty flowsearcher report)" not in src


def test_write_report_returns_error_stub_when_writer_empty_and_no_evidence(monkeypatch):
    monkeypatch.setattr(fs, "_llm_call", lambda *a, **k: "")
    out = fs._write_report(
        "some intent", subgoal_results=[], all_found={},
        model="m", base_url="http://x/v1", shim_url="http://s",
        fetch_fn=lambda url, shim, n: "",
    )
    assert out == "(flowsearcher error: write: LLM writer returned empty and no sandbox evidence was collected)"
    assert classify_report(out) == "stub_exception"


def test_write_report_benchmark_default_emits_error_stub_not_ghostwritten(monkeypatch):
    # Fairness: in benchmark mode (the default, EVIDENCE_FALLBACK_ENABLE unset) a
    # writer failure must surface an honest stub even when evidence exists. The
    # harness must NOT assemble an evidence dump on flowsearcher's behalf.
    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)
    monkeypatch.setattr(fs, "_llm_call", lambda *a, **k: "")
    all_found = {
        "http://localhost:7770/p1.html": {
            "url": "http://localhost:7770/p1.html", "title": "P1",
            "snippet": "a product", "domain": "shopping", "query": "q",
        }
    }
    sg = [{"section_title": "S", "subgoal": "A", "n_urls_found": 1,
           "results": list(all_found.values())}]
    out = fs._write_report(
        "intent", sg, all_found, "m", "http://x/v1", "http://s",
        fetch_fn=lambda url, shim, n: "",
    )
    assert out.startswith("(flowsearcher error")
    assert "FlowSearcher-DS Evidence Report" not in out
    assert classify_report(out) == "stub_exception"


# --------------------------------------------------------------------------
# Weak-but-real capture policy: capture never judges quality, the scorer does.
# Regression (observed 2026-07): flowsearcher-ds ran its full native pipeline
# and wrote a real report, and the benchmark adapter binned it as
# "(flowsearcher error: write: native report weak/under-threshold)".
# --------------------------------------------------------------------------

WEAK_REAL_REPORT = (
    "# Verdict\n\n"
    "A real but under-threshold flowsearcher report with a single citation: "
    "[p1](http://localhost:7770/p1.html). It is far below the 3000-char/3-URL "
    "floor, yet it is the framework's own output and must be saved verbatim.\n"
)


def test_write_report_returns_weak_real_writer_output_verbatim(monkeypatch):
    # A short-but-real writer output must be returned verbatim in benchmark
    # mode; the write-phase error stub is reserved for EMPTY writer output.
    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)
    monkeypatch.setattr(fs, "_llm_call", lambda *a, **k: WEAK_REAL_REPORT)
    all_found = {
        "http://localhost:7770/p1.html": {
            "url": "http://localhost:7770/p1.html", "title": "P1",
            "snippet": "a product", "domain": "shopping", "query": "q",
        }
    }
    sg = [{"section_title": "S", "subgoal": "A", "n_urls_found": 1,
           "results": list(all_found.values())}]
    out = fs._write_report(
        "intent", sg, all_found, "m", "http://x/v1", "http://s",
        fetch_fn=lambda url, shim, n: "",
    )
    assert out == WEAK_REAL_REPORT
    assert classify_report(out) == "ok"


def test_lane_adapter_keeps_weak_real_native_report_verbatim(monkeypatch):
    # The benchmark lane adapter must save flowsearcher's weak-but-real native
    # report verbatim instead of replacing it with a write-phase error stub.
    import asyncio

    import scripts.run_deep_task as rdt

    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)
    monkeypatch.delenv("FLOWSEARCHER_FORCE_FALLBACK", raising=False)

    async def _fake_run_flowsearcher(intent, model, task_id="", shim_url=None, proxy_url=None):
        return WEAK_REAL_REPORT

    monkeypatch.setattr(fs, "run_flowsearcher", _fake_run_flowsearcher)
    out = asyncio.run(rdt._run_flowsearcher_ds("intent", "m"))
    assert out == WEAK_REAL_REPORT
    assert classify_report(out) == "ok"


def test_lane_adapter_still_stubs_native_exception(monkeypatch):
    # Exceptions remain honest stubs: keeping weak-but-real output must not
    # weaken the failure channel.
    import asyncio

    import scripts.run_deep_task as rdt

    monkeypatch.delenv("EVIDENCE_FALLBACK_ENABLE", raising=False)
    monkeypatch.delenv("FLOWSEARCHER_FORCE_FALLBACK", raising=False)

    async def _boom(intent, model, task_id="", shim_url=None, proxy_url=None):
        raise RuntimeError("kaput")

    monkeypatch.setattr(fs, "run_flowsearcher", _boom)
    out = asyncio.run(rdt._run_flowsearcher_ds("intent", "m"))
    assert out == "(flowsearcher error: native: RuntimeError: kaput)"
    assert classify_report(out) == "stub_exception"


def test_write_report_evidence_fallback_only_when_explicitly_enabled(monkeypatch):
    # With the explicit non-benchmark flag set, a writer failure degrades to the
    # grounded fallback report instead of an error stub.
    monkeypatch.setenv("EVIDENCE_FALLBACK_ENABLE", "1")
    monkeypatch.setattr(fs, "_llm_call", lambda *a, **k: "")
    all_found = {
        "http://localhost:7770/p1.html": {
            "url": "http://localhost:7770/p1.html", "title": "P1",
            "snippet": "a product", "domain": "shopping", "query": "q",
        }
    }
    sg = [{"section_title": "S", "subgoal": "A", "n_urls_found": 1,
           "results": list(all_found.values())}]
    out = fs._write_report(
        "intent", sg, all_found, "m", "http://x/v1", "http://s",
        fetch_fn=lambda url, shim, n: "",
    )
    assert not out.startswith("(flowsearcher error")
    assert "FlowSearcher-DS Evidence Report" in out


# --------------------------------------------------------------------------
# D3: bounded, deterministic page fetching
# --------------------------------------------------------------------------

def _mk_result(url, domain, title="t", snippet="snip"):
    return {"url": url, "domain": domain, "title": title, "snippet": snippet}


def test_select_pages_for_fetch_is_deterministic_and_bounded():
    sg = [{
        "section_title": "S",
        "results": [
            _mk_result("http://localhost:7770/a", "shopping"),
            _mk_result("http://localhost:7770/b", "shopping"),
            _mk_result("http://localhost:9999/c", "reddit"),
            _mk_result("http://localhost:8090/d", "wiki"),
            _mk_result("http://localhost:7770/e", "shopping"),
        ],
    }]
    picked = fs._select_pages_for_fetch(sg, pages_per_subgoal=3)
    # 3 per subgoal, preserving framework discovery order. The harness must not
    # rebalance toward the benchmark's scored source classes.
    assert picked == [
        "http://localhost:7770/a",
        "http://localhost:7770/b",
        "http://localhost:9999/c",
    ]


def test_select_pages_dedupes_across_subgoals():
    sg = [
        {"section_title": "S1", "results": [_mk_result("http://localhost:7770/a", "shopping")]},
        {"section_title": "S2", "results": [_mk_result("http://localhost:7770/a", "shopping"),
                                            _mk_result("http://localhost:9999/b", "reddit")]},
    ]
    picked = fs._select_pages_for_fetch(sg, pages_per_subgoal=3)
    assert picked == ["http://localhost:7770/a", "http://localhost:9999/b"]


def test_fetch_evidence_pages_respects_total_cap():
    sg = [{
        "section_title": "S",
        "results": [_mk_result(f"http://localhost:7770/{i}", "shopping") for i in range(5)],
    }]
    calls = []

    def fake_fetch(url, shim, n):
        calls.append(url)
        return "X" * n

    fetched = fs._fetch_evidence_pages(
        sg, "http://s", fake_fetch, per_page_chars=1000, total_cap=2500)
    # After 3 pages (3000 chars) we exceed the 2500 cap, so the loop stops.
    assert len(fetched) == 3
    assert all(len(v) == 1000 for v in fetched.values())


def test_fetch_evidence_pages_degrades_on_fetch_failure():
    sg = [{"section_title": "S",
           "results": [_mk_result("http://localhost:7770/a", "shopping")]}]

    def boom(url, shim, n):
        raise RuntimeError("network down")

    fetched = fs._fetch_evidence_pages(sg, "http://s", boom)
    assert fetched == {}


def test_build_evidence_text_prefers_full_page_over_snippet():
    sg = [{"section_title": "Landscape",
           "results": [_mk_result("http://localhost:7770/a", "shopping",
                                   title="Product A", snippet="short snippet")]}]
    fetched = {"http://localhost:7770/a": "FULL PAGE BODY " * 20}
    text = fs._build_evidence_text(sg, fetched, per_page_chars=3000)
    assert "FULL PAGE BODY" in text
    assert "### Landscape" in text
    assert "URL: http://localhost:7770/a" in text
    assert "[Product A](" not in text


def test_build_evidence_text_uses_snippet_when_not_fetched():
    sg = [{"section_title": "Landscape",
           "results": [_mk_result("http://localhost:7770/a", "shopping",
                                   title="Product A", snippet="the snippet text")]}]
    text = fs._build_evidence_text(sg, fetched={})
    assert "the snippet text" in text


def test_build_evidence_text_respects_budget():
    results = [_mk_result(f"http://localhost:7770/{i}", "shopping",
                          snippet="s" * 100) for i in range(500)]
    sg = [{"section_title": "S", "results": results}]
    text = fs._build_evidence_text(sg, fetched={}, budget=2000)
    assert len(text) <= 2100  # budget plus the short truncation marker


def test_fetch_page_goes_through_shim_extract(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"url": "http://localhost:7770/a",
                                 "raw_content": "<p>hello   world</p>"}]}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(fs.requests, "post", fake_post)
    out = fs._fetch_page("http://localhost:7770/a", "http://s:8081", max_chars=100)
    assert captured["url"] == "http://s:8081/extract"
    assert captured["json"] == {"urls": ["http://localhost:7770/a"]}
    assert out == "hello world"


def test_benchmark_prompts_do_not_embed_scorer_rubric(monkeypatch):
    captured = []

    def fake_llm(messages, **kwargs):
        captured.append((messages, kwargs))
        if "workflow planner" in messages[0]["content"]:
            return '[{"subgoal":"A","search_queries":["q"],"section_title":"S"}]'
        return "# Report"

    monkeypatch.setattr(fs, "_llm_call", fake_llm)
    plan = fs._synthesize_workflow(
        "user task", [{"label": "A", "title": "S", "body": "user task"}],
        "", "m", "http://x/v1",
    )
    assert plan[0]["search_queries"] == ["q"]

    all_found = {
        "http://localhost:7770/p": {
            "url": "http://localhost:7770/p", "title": "P", "snippet": "s",
            "domain": "shopping", "query": "q",
        }
    }
    fs._write_report(
        "user task", [{"section_title": "S", "results": list(all_found.values())}],
        all_found, "m", "http://x/v1", "http://s",
        fetch_fn=lambda *_: "",
    )

    prompts = "\n".join(call[0][0]["content"] for call in captured)
    forbidden = (
        "AT LEAST 80", "4000-7000", "30 paragraphs", "min_urls_to_cite",
        "target_domains", "shopping=", "reddit=", "wiki=", "8-15 search",
        "product URL + reddit URL + wiki URL",
    )
    assert not any(term in prompts for term in forbidden)
    assert all(call[1].get("temperature") == 0.2 for call in captured)
