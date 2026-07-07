"""Unit tests for the gpt-researcher lane adapter (pure functions only).

These do NOT require the .venv-gptr environment or a live sandbox: they cover
the adapter-layer logic that is statically verifiable on the workstation —
prompt-parity (no seed-injection), driver-script validity, and the grounding
diagnostic / report extraction from subprocess stdout.
"""
from __future__ import annotations

import ast

from scripts.runners import gpt_researcher_runner as gptr
from scripts.runners.registry import discover


def test_gpt_researcher_is_discovered() -> None:
    runners, errors = discover()
    assert "gpt-researcher" in runners
    assert "gpt_researcher_runner" not in errors


def test_enhance_intent_has_no_seed_injection() -> None:
    """Fairness (issue #19): the injected citation guidance must not seed a
    concrete example URL, a golden title, or the scorer's exact per-domain
    counts — those let a non-grounded model fabricate/echo without retrieving.
    """
    ei = gptr._enhance_intent("Recommend headphones for a noisy commute.")
    # The original task text is preserved.
    assert "Recommend headphones for a noisy commute." in ei
    # No leaked example URL (the archived run echoed this verbatim as a fake cite).
    assert "localhost:8090" not in ei
    assert "127.0.0.1" not in ei
    assert "Active noise control" not in ei
    # No teach-to-test per-domain quotas.
    assert "at least 15" not in ei
    assert "15 Wikipedia" not in ei
    # Anti-fabrication guidance is present.
    assert "do NOT invent" in ei
    assert "retrieved" in ei.lower()


def test_build_driver_script_is_valid_python() -> None:
    drv = gptr._build_driver_script(
        "Some research task.",
        "http://localhost:8081",
        "http://localhost:8088/v1",
        "qwen3-8b",
    )
    # Must parse (guards against f-string/brace breakage in the generated code).
    ast.parse(drv)
    # The reach-0 root fix: the shim-backed retriever class is defined and
    # bound at the name gpt-researcher's get_retriever('tavily') imports,
    # BEFORE GPTResearcher() is constructed. The old fragile `self.base_url`
    # monkey-patch must be gone.
    assert "class _ShimTavilyRetriever" in drv
    assert "_gr_pkg.TavilySearch = _ShimTavilyRetriever" in drv
    assert "_gr_tav.TavilySearch = _ShimTavilyRetriever" in drv
    assert "self.base_url" not in drv
    # The bind (Layer 2) must precede the GPTResearcher import (Layer 3) so the
    # late `from gpt_researcher.retrievers import TavilySearch` resolves to ours.
    assert drv.index("_gr_pkg.TavilySearch = _ShimTavilyRetriever") < drv.index(
        "from gpt_researcher import GPTResearcher"
    )
    # The grounding diagnostic must still be wired in.
    assert gptr._DIAG_MARK in drv
    assert "retrieved=%d localhost=%d" in drv


def _exec_retriever_block(shim_url: str, fake_post):
    """Exec just the shim-retriever source (no gpt_researcher install needed).

    Skips the trailing `import gpt_researcher.retrievers ...` bind lines (that
    package is not on the workstation) and returns the `_ShimTavilyRetriever`
    class wired to `fake_post` in place of `requests.post`.
    """
    import sys
    import types

    block = gptr._build_shim_retriever_block(shim_url)
    # Drop the bind epilogue (everything from the gpt_researcher import on): the
    # package is absent here; the bind itself is covered by the sys.modules
    # test below.
    block = block.split("# Bind at the name")[0]
    # The block runs `import requests as _rq`; the exec import machinery reads
    # sys.modules, so temporarily install a fake `requests` module carrying our
    # `post`.
    fake_requests = types.ModuleType("requests")
    fake_requests.post = fake_post
    saved = sys.modules.get("requests")
    sys.modules["requests"] = fake_requests
    try:
        ns: dict = {}
        exec(compile(block, "<shim_block>", "exec"), ns)
    finally:
        if saved is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = saved
    return ns["_ShimTavilyRetriever"]


def test_shim_retriever_posts_to_shim_and_maps_results() -> None:
    """Every search must POST to the shim /search and return the shim's URLs
    verbatim as [{href, body}] — proving the retriever contract gpt-researcher
    consumes (search_urls = [u['href'] ...]).
    """
    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"url": "http://localhost:8090/wiki/Noise", "content": "c1"},
                    {"url": "http://localhost:7770/products/1", "content": "c2",
                     "raw_content": "raw2"},
                ]
            }

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _Resp()

    Retriever = _exec_retriever_block("http://localhost:8081", fake_post)
    r = Retriever("best anc headphones", query_domains=None)
    hits = r.search(max_results=7)

    # Posted to the shim's /search, not api.tavily.com.
    assert captured["url"] == "http://localhost:8081/search"
    assert captured["payload"]["query"] == "best anc headphones"
    assert captured["payload"]["max_results"] == 7
    # Contract gpt-researcher expects: list of {"href", "body"}.
    assert hits == [
        {"href": "http://localhost:8090/wiki/Noise", "body": "c1"},
        {"href": "http://localhost:7770/products/1", "body": "raw2"},
    ]


def test_shim_retriever_empty_on_error_is_loud_not_silent() -> None:
    """A wiring break returns [] (so research proceeds) but must print a loud
    stderr marker — the reach-0 amplifier was gpt-researcher's silent
    swallow-to-empty. Here the failure is self-revealing.
    """
    def boom(url, json=None, timeout=None):
        raise RuntimeError("connection refused")

    Retriever = _exec_retriever_block("http://localhost:8081", boom)
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        hits = Retriever("q").search()
    assert hits == []
    assert "[gptr-shim] search FAILED" in buf.getvalue()


def test_registry_bind_replaces_the_class_get_retriever_imports() -> None:
    """Prove the injection point: gpt-researcher's get_retriever('tavily') does
    a late `from gpt_researcher.retrievers import TavilySearch`. We reproduce
    that exact resolution against a fake gpt_researcher package tree, run the
    bind epilogue, and assert the resolved class is our shim retriever.

    (Final proof is the box smoke with the real .venv-gptr; this pins the
    wiring statically on the workstation where the package is absent.)
    """
    import sys
    import types

    # Build a fake package tree mirroring the real one: retrievers/__init__
    # re-exports TavilySearch from the tavily submodule (same object identity).
    class _RealTavily:  # stand-in for the real class we must displace
        pass

    pkg = types.ModuleType("gpt_researcher")
    retr = types.ModuleType("gpt_researcher.retrievers")
    tav_pkg = types.ModuleType("gpt_researcher.retrievers.tavily")
    tav_mod = types.ModuleType("gpt_researcher.retrievers.tavily.tavily_search")
    tav_mod.TavilySearch = _RealTavily
    retr.TavilySearch = _RealTavily  # re-exported, same object
    pkg.retrievers = retr
    retr.tavily = tav_pkg
    tav_pkg.tavily_search = tav_mod

    saved = {k: sys.modules.get(k) for k in (
        "gpt_researcher", "gpt_researcher.retrievers",
        "gpt_researcher.retrievers.tavily",
        "gpt_researcher.retrievers.tavily.tavily_search")}
    sys.modules["gpt_researcher"] = pkg
    sys.modules["gpt_researcher.retrievers"] = retr
    sys.modules["gpt_researcher.retrievers.tavily"] = tav_pkg
    sys.modules["gpt_researcher.retrievers.tavily.tavily_search"] = tav_mod
    try:
        # Run the WHOLE block (class def + bind epilogue) as the driver does.
        block = gptr._build_shim_retriever_block("http://localhost:8081")
        exec(compile(block, "<shim_block_full>", "exec"), {})

        # Reproduce gpt-researcher's get_retriever("tavily") resolution exactly.
        from gpt_researcher.retrievers import TavilySearch as _Resolved
        assert _Resolved.__name__ == "_ShimTavilyRetriever"
        assert _Resolved is not _RealTavily
        # Both namespaces were rebound (agent.py imports via the package, the
        # submodule attr is the belt-and-braces second binding).
        assert retr.TavilySearch is _Resolved
        assert tav_mod.TavilySearch is _Resolved
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_driver_does_not_compensate_the_report_writer() -> None:
    """Fairness (box smoke8c, World-(b) close-as-model): gpt-researcher 0.12.3
    already threads each scraped source URL into the writer context as
    ``Source: <url>`` and its prompt mandates citing them, so the adapter must
    NOT re-inject a curated URL list or otherwise write citations on the
    framework's behalf. The old revision appended a "CITE ONLY FROM THESE
    VERBATIM RETRIEVED URLS" block and mutated ``r.query`` post-construction.
    Both were dead code (no ``custom_prompt`` kwarg; ReportGenerator snapshots
    the query at ``__init__``) and, worse, harness compensation for a model
    weakness. Guard against either creeping back in.
    """
    drv = gptr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    # No fabricated-URL-injection appendix, in any casing.
    assert "CITE ONLY FROM THESE VERBATIM" not in drv
    # No unsupported write_report kwarg (raised TypeError; a silent no-op).
    assert "custom_prompt" not in drv
    # No post-construction query mutation to smuggle a URL list into the prompt.
    assert "r.query = QUERY +" not in drv
    # The writer is invoked plainly, letting the framework+model own citations.
    assert "await r.write_report()" in drv
    # The read-only grounding diagnostic is retained (it never edits the report).
    assert gptr._DIAG_MARK in drv
    assert "retrieved=%d localhost=%d" in drv


def test_build_driver_script_does_not_hardcode_context_length() -> None:
    """The lane must stay correct across the planned vLLM 65536/YaRN move and
    glm-4.7-flash@200k — it must not bake a context/window constant into the
    driver.
    """
    drv = gptr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    for const in ("40960", "32768", "65536", "max_model_len"):
        assert const not in drv


def test_extract_report_between_sentinels() -> None:
    stdout = (
        "boot noise\n"
        f"{gptr._DIAG_MARK} retrieved=3 localhost=3\n"
        f"{gptr._REPORT_START}\n# Title\n\nBody line.\n{gptr._REPORT_END}\n"
        "trailing noise\n"
    )
    assert gptr._extract_report(stdout) == "# Title\n\nBody line."


def test_extract_diag_parses_marker_line() -> None:
    stdout = (
        "noise\n"
        f"{gptr._DIAG_MARK} retrieved=0 localhost=0\n"
        f"{gptr._REPORT_START}\nreport\n{gptr._REPORT_END}\n"
    )
    assert gptr._extract_diag(stdout) == f"{gptr._DIAG_MARK} retrieved=0 localhost=0"
    # The diagnostic is emitted OUTSIDE the report sentinels, so it must never
    # leak into the captured report.
    assert gptr._DIAG_MARK not in gptr._extract_report(stdout)


def test_extract_diag_absent_returns_empty() -> None:
    assert gptr._extract_diag("no diagnostic emitted here") == ""
