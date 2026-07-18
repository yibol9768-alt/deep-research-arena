"""Unit tests for the ldr (local-deep-research) lane adapter (pure functions).

These do NOT require the .venv-ldr312 environment or a live sandbox: they cover
the adapter-layer logic that is statically verifiable on the workstation --
prompt-parity (no seed injection), generated-driver validity, faithful report
capture, and the fairness rule that a URL-light but substantive LDR report is
returned as-is rather than replaced by a synthesized/templated stand-in.
"""
from __future__ import annotations

import ast
import re
from urllib.parse import urlparse

from scripts.runners import ldr_runner as ldr
from scripts.runners.registry import discover


def test_ldr_is_discovered() -> None:
    runners, errors = discover()
    assert "ldr" in runners
    assert "ldr_runner" not in errors


def test_driver_has_no_seed_injection() -> None:
    """Fairness: the generated driver must not run its own sandbox search and
    paste the golden source URLs/snippets into the query. That is seed injection
    the shared task prompt never gives other lanes.
    """
    drv = ldr._build_driver_script(
        "Recommend headphones for a noisy commute.",
        "http://localhost:8081",
        "http://localhost:8088/v1",
        "qwen3-8b",
    )
    assert "_prefetch_sandbox_evidence" not in drv
    assert "PREFETCHED_EVIDENCE" not in drv
    assert "Prefetched local source evidence" not in drv
    # The model is handed the task only; it must discover sources itself.
    assert "QUERY = BASE_QUERY" in drv


def test_driver_does_not_fabricate_a_longer_report() -> None:
    """Fairness: the driver must not re-synthesize a >=4500-char report when
    LDR's real output is short or refuses -- that manufactures grounding the
    model never produced.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    assert "_fallback_synthesize" not in drv
    assert "at least 4500 characters" not in drv


def test_build_driver_script_is_valid_python() -> None:
    drv = ldr._build_driver_script(
        "Some research task with 'quotes' and\nnewlines.",
        "http://localhost:8081",
        "http://localhost:8088/v1",
        "qwen3-8b",
    )
    # Must parse (guards against f-string/brace breakage in the generated code).
    ast.parse(drv)
    # The Tavily->shim redirect and the report sentinels must be wired in.
    assert "api.tavily.com" in drv
    assert ldr._REPORT_START in drv
    assert ldr._REPORT_END in drv


def test_driver_registers_supported_sandbox_retriever() -> None:
    """Use LDR's public custom-retriever API inside the no-DNS worker.

    The built-in Tavily engine resolves/validates api.tavily.com before an HTTP
    rewrite runs, so it silently produces no results in the formal namespace.
    The registered retriever must relay only LDR's own queries to shim /search.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    assert "class DraSandboxRetriever(BaseRetriever):" in drv
    assert '"search.tool": RETRIEVER_NAME' in drv
    assert "retrievers={RETRIEVER_NAME: _retriever}" in drv
    assert "search_tool=RETRIEVER_NAME" in drv
    assert "self.shim_url.rstrip('/') + '/search'" in drv
    assert '"search.engine.web.tavily.api_key"' not in drv


def test_driver_keeps_only_canonical_sandbox_source_urls() -> None:
    """Embedded links in a sandbox post are content, not source identities.

    LDR's section writer promotes URL-looking text from Document bodies into
    citations.  The adapter must therefore retain localhost corpus URLs while
    omitting public outbound URL tokens before the Document enters LDR.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    tree = ast.parse(drv)
    klass = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DraSandboxRetriever"
    )
    methods = [
        node
        for node in klass.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_is_sandbox_source_url", "_sanitize_snippet"}
    ]
    test_class = ast.ClassDef(
        name="RetrieverForTest",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    namespace = {"re": re, "urlparse": urlparse}
    ast.fix_missing_locations(test_class)
    exec(compile(ast.Module(body=[test_class], type_ignores=[]), "<ldr-test>", "exec"), namespace)
    cls = namespace["RetrieverForTest"]

    text, omitted = cls._sanitize_snippet(
        "Quoted public link https://example.com/review plus canonical "
        "http://localhost:9999/f/headphones/1 and "
        "http://127.0.0.1:7770/product.html."
    )
    assert omitted == 1
    assert "example.com" not in text
    assert "[external URL omitted]" in text
    assert "http://localhost:9999/f/headphones/1" in text
    assert "http://127.0.0.1:7770/product.html" in text
    assert cls._is_sandbox_source_url("https://soundguys.com/review") is False


def test_driver_connectivity_preflight_retains_no_sources() -> None:
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    assert "SHIM.rstrip('/') + '/healthz'" in drv
    # The preflight is health-only; task search happens solely in the retriever.
    preflight = drv.split("# Connectivity-only preflight:", 1)[1].split(
        "settings = create_settings_snapshot", 1
    )[0]
    assert "'/search'" not in preflight


def test_build_driver_script_does_not_hardcode_context_length() -> None:
    """The lane must stay correct across the planned vLLM 65536/YaRN move and
    glm-4.7-flash@200k -- no context/window constant baked into the driver.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    for const in ("40960", "32768", "65536", "max_model_len", "max-model-len"):
        assert const not in drv


def test_extract_report_between_sentinels() -> None:
    stdout = (
        "boot noise\n"
        f"{ldr._REPORT_START}\n# Title\n\nBody line.\n{ldr._REPORT_END}\n"
        "trailing noise\n"
    )
    assert ldr._extract_report(stdout) == "# Title\n\nBody line."


def test_extract_report_missing_sentinels_returns_empty() -> None:
    assert ldr._extract_report("no sentinels here") == ""


# ---------------------------------------------------------------------------
# Source-capture fix: LDR's ``detailed_research()`` API returns an intermediate
# summary whose bracketed citations have no inline URL table.  Its native
# ``generate_report()`` API performs the actual report stage and appends LDR's
# own ``## Sources`` mapping.  The harness must capture that native report,
# never synthesize or append a source block itself.
# ---------------------------------------------------------------------------

def test_driver_emits_sources_block() -> None:
    """The generated driver mirrors URLs already in the native report between
    diagnostic sentinels without modifying the scored report.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    import ast as _ast
    _ast.parse(drv)
    assert ldr._SOURCES_START in drv
    assert ldr._SOURCES_END in drv
    assert "generate_report(" in drv
    assert 'result.get("content")' in drv
    assert "detailed_research(" not in drv
    assert "_sources.append({\"url\": _url})" in drv


def test_driver_keeps_shared_long_query_searchable() -> None:
    """The shared task/report prompt is longer than LDR's 300-char default.

    Preserve the native ``search_original_query=True`` behavior for exactly the
    supplied task length, so a formatting miss in the old follow-up-question
    parser cannot silently turn the run into zero searches.
    """
    drv = ldr._build_driver_script(
        "x" * 900,
        "http://localhost:8081",
        "http://localhost:8088/v1",
        "qwen3-8b",
    )
    assert '"app.max_user_query_length": max(300, len(BASE_QUERY))' in drv


def test_extract_sources_roundtrip() -> None:
    import json
    payload = [
        {"title": "HD681 review", "link": "http://localhost:9999/f/headphones/1", "index": "1"},
        {"title": "HD800S review", "url": "http://localhost:9999/f/headphones/2", "index": "2"},
    ]
    stdout = (
        f"{ldr._REPORT_START}\nbody\n{ldr._REPORT_END}\n"
        f"{ldr._SOURCES_START}\n{json.dumps(payload)}\n{ldr._SOURCES_END}\n"
    )
    assert ldr._extract_sources(stdout) == payload


def test_extract_sources_missing_or_bad_returns_empty() -> None:
    assert ldr._extract_sources("no sentinels") == []
    bad = f"{ldr._SOURCES_START}\nnot json\n{ldr._SOURCES_END}"
    assert ldr._extract_sources(bad) == []


def test_extract_diagnostics_roundtrip() -> None:
    import json

    payload = {
        "retriever": "dra_sandbox",
        "health_ok": True,
        "calls": 4,
        "results": 27,
        "errors": 0,
        "report_urls": 9,
    }
    stdout = (
        f"{ldr._DIAGNOSTICS_START}\n{json.dumps(payload)}\n"
        f"{ldr._DIAGNOSTICS_END}\n"
    )
    assert ldr._extract_diagnostics(stdout) == payload


def test_extract_diagnostics_missing_or_bad_returns_empty() -> None:
    assert ldr._extract_diagnostics("no sentinels") == {}
    bad = f"{ldr._DIAGNOSTICS_START}\nnot json\n{ldr._DIAGNOSTICS_END}"
    assert ldr._extract_diagnostics(bad) == {}


def test_sources_diagnostic_collects_urls_without_touching_the_report() -> None:
    """The retrieved link table is captured, never appended to the report.

    `_attach_sources` used to write LDR's `all_links_of_system` into the saved
    report as a "### Sources" block. Counterfactual rescore with the block
    removed: macro reach 0.9519 -> 0.0000 (qwen), 0.9868 -> 0.0000 (deepseek),
    with zero sandbox URLs anywhere in LDR's own prose. The lane that ranked #1
    on both boards had its entire grounding written by the harness. That is the
    construct deleted from ii-researcher as publish blocker B1 on 2026-07-06.
    """
    assert not hasattr(ldr, "_attach_sources")
    sources = [
        {"title": "HD681", "url": "http://localhost:9999/f/headphones/1", "index": "1"},
        {"title": "dupe", "link": "http://localhost:9999/f/headphones/1", "index": "2"},
        {"title": "no url", "index": "3"},
    ]
    diag = ldr.sources_diagnostic(sources)
    assert diag["n_sources_retrieved"] == 1
    assert diag["urls_retrieved"] == ["http://localhost:9999/f/headphones/1"]


def test_sources_diagnostic_empty_input() -> None:
    assert ldr.sources_diagnostic([])["n_sources_retrieved"] == 0
    assert ldr.sources_diagnostic(None)["urls_retrieved"] == []


def test_is_failed_report_true_for_genuine_failures() -> None:
    assert ldr._is_failed_report("") is True
    assert ldr._is_failed_report("   ") is True
    assert ldr._is_failed_report("(local-deep-research error: TimeoutError: x)") is True
    assert ldr._is_failed_report("(ldr: missing venv at /x)") is True
    assert ldr._is_failed_report("tiny stub") is True


def test_is_failed_report_false_for_substantive_url_light_report() -> None:
    """The core fairness invariant: a real, substantive LDR report that happens
    to carry zero sandbox URLs (a model/framework weakness) is NOT a failure and
    must be returned as-is, not swapped for a fabricated stand-in.
    """
    report = (
        "# Headphone buying guide\n\n"
        + "This is a substantive answer citing sources as [1], [4], [10]. " * 120
    )
    assert len(report) >= 3000
    assert "localhost" not in report  # zero sandbox URLs
    assert ldr._is_failed_report(report) is False


def test_unmask_report_is_a_noop_when_masking_is_off(monkeypatch) -> None:
    """With masking off (the default), _unmask_report must return the report
    BYTE-FOR-BYTE. The old code ran an unconditional literal-`replace` tail that
    rewrote onestopmarket.com / postmill.net / kiwipedia.org (and any
    en.wikipedia.org/wiki/X) into localhost EVEN when nothing was masked, so a
    model that emitted a public domain from parametric memory was laundered into
    sandbox grounding, this lane only. Off => byte-identical."""
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    report = (
        "See http://onestopmarket.com/p/1 and http://postmill.net/f/x and "
        "http://kiwipedia.org/A/Y and https://en.wikipedia.org/wiki/Coffee ."
    )
    # No model / a local backbone => masking off => nothing was masked to undo.
    assert ldr._unmask_report(report) == report
    assert ldr._unmask_report(report, model="qwen3-8b") == report
    assert ldr._unmask_report(report, model="deepseek-v4-flash") == report


def test_unmask_report_round_trips_only_when_masking_is_on(monkeypatch) -> None:
    """With LDR_INTENT_MASK on, the round trip reverses ONLY the masks this
    harness itself applied (the _UNMASK_MAP domains). A model-emitted public
    en.wikipedia.org URL is still left ALONE -- unmasking undoes masks, it does
    not launder drift."""
    monkeypatch.setenv("LDR_INTENT_MASK", "1")
    masked = (
        "See http://onestopmarket.com/p/1 and http://postmill.net/f/x and "
        "http://kiwipedia.org/A/Y and https://en.wikipedia.org/wiki/Coffee ."
    )
    out = ldr._unmask_report(masked)
    assert "postmill.net" not in out and "localhost:9999" in out
    assert "kiwipedia.org" not in out and "localhost:8090" in out
    assert "onestopmarket.com" not in out and "localhost:" in out
    # A model-emitted public Wikipedia URL is left ALONE even under masking.
    assert "https://en.wikipedia.org/wiki/Coffee" in out
    assert "wikipedia_en_all_nopic/A/Coffee" not in out


# ---------------------------------------------------------------------------
# Reverse-handicap fix: intent sanitization must PRESERVE the sandbox host
# roots for a local backbone (parity with every other lane), and only apply the
# information-destroying DeepSeek localhost rewrite for a DeepSeek backbone.
# ---------------------------------------------------------------------------

_SAMPLE_INTENT = (
    "Recommend noise-cancelling headphones for a noisy commute. "
    "Consult the product catalog (http://localhost:17770/catalogsearch/result/?q=headphones), "
    "the discussion forum (http://localhost:9999/search?q=headphones), and the "
    "encyclopedia (http://localhost:8090/search?pattern=noise). "
    "Source URLs MUST be sandbox-local. Do not fabricate URLs."
)


def test_sanitize_intent_preserves_sandbox_roots_for_local_backbone(monkeypatch) -> None:
    """A local backbone (qwen) must receive the same sandbox host roots the
    shared task prompt gives every other lane. The old code stripped them, a
    reverse handicap; the fix keeps them intact.
    """
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    out = ldr._sanitize_intent(_SAMPLE_INTENT, model="qwen3-8b")
    # All three sandbox host roots survive verbatim.
    assert "http://localhost:17770" in out
    assert "http://localhost:9999" in out
    assert "http://localhost:8090" in out
    # No substitution happened: the descriptive phrase still keeps its URL,
    # rather than the URL being deleted and replaced by the bare description.
    assert "the product catalog (http://localhost:17770" in out
    assert "the discussion forum (http://localhost:9999" in out
    # Grounding constraints are handed through unchanged.
    assert "Source URLs MUST be sandbox-local." in out


def test_sanitize_intent_no_longer_masks_for_deepseek(monkeypatch) -> None:
    """DeepSeek gets the same intent as every other backbone.

    The masking existed to dodge a DeepSeek safety filter said to refuse
    localhost URLs. Measured against the live API on 2026-07-08 (four arms,
    N=10): 0/10 refusals with localhost, 114 localhost URLs written. The premise
    is false, so the lane-specific privilege is gone.
    """
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    out = ldr._sanitize_intent(_SAMPLE_INTENT, model="deepseek-v4-flash")
    assert "http://localhost:17770" in out
    assert "http://localhost:9999" in out
    assert "Source URLs MUST be sandbox-local." in out


def test_sanitize_intent_mask_still_forceable(monkeypatch) -> None:
    """The escape hatch survives for investigating a provider that does refuse,
    but it must be set explicitly and declared in config/lane_protocol.yaml."""
    monkeypatch.setenv("LDR_INTENT_MASK", "1")
    out = ldr._sanitize_intent(_SAMPLE_INTENT, model="qwen3-8b")
    assert "localhost" not in out


def test_sanitize_intent_default_backbone_preserves(monkeypatch) -> None:
    """Default (no/unknown model) preserves information, never strips roots."""
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    out = ldr._sanitize_intent(_SAMPLE_INTENT, model=None)
    assert "http://localhost:17770" in out
    assert "http://localhost:8090" in out


def test_intent_mask_env_override(monkeypatch) -> None:
    """LDR_INTENT_MASK forces the behaviour regardless of backbone."""
    monkeypatch.setenv("LDR_INTENT_MASK", "1")
    out_on = ldr._sanitize_intent(_SAMPLE_INTENT, model="qwen3-8b")
    assert "localhost" not in out_on  # forced on -> stripped even for qwen
    monkeypatch.setenv("LDR_INTENT_MASK", "0")
    out_off = ldr._sanitize_intent(_SAMPLE_INTENT, model="deepseek-v4-flash")
    assert "http://localhost:17770" in out_off  # forced off -> preserved


def test_needs_intent_masking_is_off_for_every_backbone(monkeypatch) -> None:
    """No backbone gets masking by name any more.

    Keying a prompt rewrite on the backbone's name makes "same harness, swap the
    backbone" a two-variable experiment: the model changes AND the prompt
    changes. The cross-backbone board cannot mean anything under that design.
    """
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    for model in ("deepseek-v4-flash", "qwen3-8b", "glm-4.7-flash", None):
        assert ldr._needs_intent_masking(model) is False
    monkeypatch.setenv("LDR_INTENT_MASK", "1")
    assert ldr._needs_intent_masking("qwen3-8b") is True


def test_driver_never_masks_by_backbone(monkeypatch) -> None:
    """The generated driver keeps Layer-2 masking off for every backbone."""
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    for model in ("qwen3-8b", "deepseek-v4-flash", "glm-4.7-flash"):
        drv = ldr._build_driver_script(
            _SAMPLE_INTENT, "http://localhost:8081", "http://localhost:8088/v1", model
        )
        assert "_MASK_ENABLED = False" in drv
        import ast as _ast
        _ast.parse(drv)
