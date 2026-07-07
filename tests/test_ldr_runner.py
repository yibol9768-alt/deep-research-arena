"""Unit tests for the ldr (local-deep-research) lane adapter (pure functions).

These do NOT require the .venv-ldr312 environment or a live sandbox: they cover
the adapter-layer logic that is statically verifiable on the workstation --
prompt-parity (no seed injection), generated-driver validity, faithful report
capture, and the fairness rule that a URL-light but substantive LDR report is
returned as-is rather than replaced by a synthesized/templated stand-in.
"""
from __future__ import annotations

import ast

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
# Source-capture fix: LDR returns its retrieved URL table in the sibling
# `sources` field (all_links_of_system); the narrative in `summary` cites those
# sources by bracketed [N] only. The old capture read just `summary`, dropping
# every localhost URL regardless of backbone. The driver now also emits the
# sources list, and the parent re-attaches it -- faithful capture, not
# fabricated grounding.
# ---------------------------------------------------------------------------

def test_driver_emits_sources_block() -> None:
    """The generated driver must serialize LDR's `sources` field between the
    sources sentinels so the parent can resolve [N] citations to real URLs.
    """
    drv = ldr._build_driver_script(
        "task", "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    import ast as _ast
    _ast.parse(drv)
    assert ldr._SOURCES_START in drv
    assert ldr._SOURCES_END in drv
    # It must read LDR's own sources field, not synthesize links.
    assert 'result.get("sources")' in drv


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


def test_attach_sources_appends_localhost_urls() -> None:
    """A narrative that cites [1]/[2] but carries zero URLs gets LDR's own
    localhost source table appended, resolving the bracketed citations.
    """
    report = "# Headphones\n\nOver-ear seal analysis citing [1] and [2].\n\n### References\n\n[1] HD681 review – partial.\n[2] HD800S review – critical."
    sources = [
        {"title": "HD681 review", "link": "http://localhost:9999/f/headphones/126745", "index": "1"},
        {"title": "HD800S review", "url": "http://localhost:9999/f/headphones/126762", "index": "2"},
    ]
    out = ldr._attach_sources(report, sources)
    assert "### Sources" in out
    assert "http://localhost:9999/f/headphones/126745" in out
    assert "http://localhost:9999/f/headphones/126762" in out
    assert "[1] HD681 review" in out
    assert "[2] HD800S review" in out


def test_attach_sources_noop_when_no_sources() -> None:
    report = "# Report\n\nBody with no URLs."
    assert ldr._attach_sources(report, []) == report
    assert ldr._attach_sources(report, None) == report


def test_attach_sources_noop_when_report_already_has_localhost() -> None:
    """If the model already inlined sandbox URLs, do not duplicate the table."""
    report = "See http://localhost:9999/f/headphones/1 for details [1]."
    sources = [{"title": "x", "url": "http://localhost:9999/f/headphones/1", "index": "1"}]
    assert ldr._attach_sources(report, sources) == report


def test_attach_sources_dedupes_and_skips_urlless_entries() -> None:
    report = "Body citing [1] [2] with no URLs."
    sources = [
        {"title": "dup", "url": "http://localhost:9999/f/a/1", "index": "1"},
        {"title": "dup again", "url": "http://localhost:9999/f/a/1", "index": "1"},
        {"title": "no url entry", "index": "2"},
        {"title": "second", "link": "http://localhost:8090/content/x", "index": "3"},
    ]
    out = ldr._attach_sources(report, sources)
    assert out.count("http://localhost:9999/f/a/1") == 1
    assert "http://localhost:8090/content/x" in out
    # The url-less entry contributes no line.
    assert "no url entry" not in out


def test_attach_sources_invented_urls_never_appear() -> None:
    """Fairness guard: only LDR-provided URLs are attached; the function never
    manufactures a URL for a source that lacks one.
    """
    report = "Body [1]."
    sources = [{"title": "sourceless", "index": "1"}]
    assert ldr._attach_sources(report, sources) == report


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


def test_unmask_report_restores_sandbox_urls() -> None:
    masked = (
        "See http://onestopmarket.com/p/1 and http://postmill.net/f/x and "
        "http://kiwipedia.org/A/Y and https://en.wikipedia.org/wiki/Coffee ."
    )
    out = ldr._unmask_report(masked)
    assert "postmill.net" not in out and "localhost:9999" in out
    assert "kiwipedia.org" not in out and "localhost:8090" in out
    # en.wikipedia.org is rewritten to the local Kiwix content path.
    assert "en.wikipedia.org" not in out
    assert "localhost:8090/content/wikipedia_en_all_nopic/A/Coffee" in out


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


def test_sanitize_intent_masks_only_for_deepseek(monkeypatch) -> None:
    """A DeepSeek backbone still gets the refusal-avoiding localhost rewrite."""
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    out = ldr._sanitize_intent(_SAMPLE_INTENT, model="deepseek-v4-flash")
    assert "localhost" not in out
    assert "the product catalog" in out


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


def test_needs_intent_masking_keying(monkeypatch) -> None:
    monkeypatch.delenv("LDR_INTENT_MASK", raising=False)
    assert ldr._needs_intent_masking("deepseek-v4-flash") is True
    assert ldr._needs_intent_masking("qwen3-8b") is False
    assert ldr._needs_intent_masking("glm-4.7-flash") is False
    assert ldr._needs_intent_masking(None) is False


def test_driver_bypasses_llm_mask_for_local_backbone() -> None:
    """The generated driver must disable Layer-2 localhost masking for a local
    backbone so the LLM sees real localhost URLs (parity with other lanes).
    """
    drv_local = ldr._build_driver_script(
        _SAMPLE_INTENT, "http://localhost:8081", "http://localhost:8088/v1", "qwen3-8b"
    )
    assert "_MASK_ENABLED = False" in drv_local
    drv_ds = ldr._build_driver_script(
        _SAMPLE_INTENT, "http://localhost:8081", "http://localhost:8088/v1", "deepseek-v4-flash"
    )
    assert "_MASK_ENABLED = True" in drv_ds
    # Both remain valid Python.
    import ast as _ast
    _ast.parse(drv_local)
    _ast.parse(drv_ds)
