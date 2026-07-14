"""Regression tests for hidden lane asymmetries missed by check_parity."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text()


def _function_source(path: str, name: str) -> str:
    source = _source(path)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"function {name!r} not found in {path}")


def test_shared_report_format_is_appended_once_at_dispatch():
    import scripts.run_deep_task as rdt

    resolved = rdt._resolve_intent({"intent": "Research this."})
    assert resolved == "Research this." + rdt.SHARED_REPORT_FORMAT
    assert resolved.count("Deliver your answer as a single self-contained markdown report") == 1

    # Per-lane wrappers must not reinforce the shared instruction a second time.
    assert "intent + SHARED_REPORT_FORMAT" not in _source("scripts/run_deep_task.py")
    assert "output_instructions=output_instructions" not in _source("scripts/runners/qx_runner.py")


def test_flowsearcher_formal_path_contains_no_scorer_quotas():
    formal = "\n".join(
        _function_source("scripts/run_flowsearcher.py", name)
        for name in (
            "_synthesize_workflow", "_select_pages_for_fetch",
            "_build_evidence_text", "_write_report", "run_flowsearcher",
        )
    )
    for forbidden in (
        "AT LEAST 80", "4000-7000", "30 paragraphs", "min_urls_to_cite",
        "target_domains", 'targets = {"shopping": 40', "8-15 search queries",
        "product URL + reddit URL + wiki URL", "temperature=0.3",
    ):
        assert forbidden not in formal


def test_framework_native_budgets_are_not_silently_overridden():
    deer = _source("scripts/runners/deerflow_runner.py")
    assert '"max_step_num": 3' in deer
    assert '"max_step_num": 6' not in deer

    qx = _source("scripts/runners/qx_runner.py")
    assert "MAX_TURNS = 10" in qx
    assert "max_iterations=5" in qx
    assert "max_time_minutes=10" in qx
    assert "from deep_researcher import DeepResearcher" in qx
    assert "researcher = DeepResearcher(" in qx
    assert "IterativeResearcher" not in qx
    assert "def _rp_fallback" not in qx
    assert "return typ.model_validate(_rp_po.parse_json_output(_rp_strip(output)))" in qx
    assert 'decoder.raw_decode(cleaned[index:])' in qx
    assert 'split("```")[1]' not in qx
    assert "for _schema_attempt in range(2)" in qx
    assert "retrying one schema-invalid native" in qx
    assert "_QX_SCHEMA_ERRORS" in qx

    tongyi = _source("scripts/runners/tongyi_runner.py")
    assert "MAX_LLM_CALLS = 100" in tongyi
    assert "time.time() - start_time > 1800" not in tongyi

    opencode = _source("scripts/runners/opencode_runner.py")
    assert "OPENCODE_MAX_OUTPUT_TOKENS_DEFAULT = 8192" in opencode

    storm = _source("scripts/runners/storm_runner.py")
    assert "search_top_k=3" in storm
    assert "max_thread_num=10" in storm
    assert "search_top_k=5" not in storm
    assert "max_thread_num=2" not in storm
    assert "k=5" not in storm


def test_storm_semantic_retriever_substitution_is_disclosed():
    protocol = _source("config/lane_protocol.yaml")
    assert "STORM's post-retrieval SentenceTransformer index is replaced" in protocol
    assert "deterministic lexical scorer" in protocol


def test_langchain_odr_formal_path_runs_native_supervisor_graph():
    source = _function_source("scripts/run_deep_task.py", "_run_langchain_odr_graph")
    assert "deep_researcher_builder.compile()" in source
    assert "graph.ainvoke" in source
    assert "queries[:2]" not in source
    assert "tool_calls[:1]" not in source
    assert "conduct_research_calls[:1]" not in source
    assert "_summarize_webpage_noop" not in source
    assert "final_report_generation" not in source


def test_short_native_cli_reports_are_never_replaced_by_stdout():
    for path in (
        "scripts/runners/opencode_runner.py",
        "scripts/runners/claudecode_runner.py",
        "scripts/runners/codex_runner.py",
    ):
        source = _source(path)
        assert "if len(report) < 500" not in source


def test_cli_capability_prompts_do_not_name_scored_corpus_modalities():
    for path in (
        "scripts/runners/opencode_runner.py",
        "scripts/runners/claudecode_runner.py",
        "scripts/runners/codex_runner.py",
    ):
        source = _source(path)
        assert "Magento sandbox (shopping)" not in source
        assert "Postmill sandbox (reddit-like)" not in source
        assert "Kiwix sandbox (offline Wikipedia)" not in source
    assert "model_reasoning_effort" not in _source("scripts/runners/codex_runner.py")


def test_costorm_never_builds_a_harness_report_on_native_failure():
    source = _source("scripts/runners/costorm_runner.py")
    assert "def _fallback_report" not in source
    run_source = _function_source("scripts/runners/costorm_runner.py", "run")
    assert 'error_stub("co-storm", "write"' in run_source
    assert "Knowledge Base Structure" not in run_source
    assert "Research Conversation" not in run_source


def test_adapter_tool_descriptions_do_not_prescribe_citations_or_source_mix():
    rdt = _source("scripts/run_deep_task.py")
    smol = _function_source("scripts/run_deep_task.py", "_run_smolagents")
    assert "Use only URLs returned by this tool for citations" not in smol
    assert "products, forum discussions, or encyclopedia" not in smol

    deepagents = _source("scripts/runners/deepagents_runner.py")
    assert "Always cite the URLs from the results" not in deepagents
    assert "product listings, forum" not in deepagents

    # Guard against accidentally deleting the shared instruction itself.
    assert "SHARED_REPORT_FORMAT" in rdt


def test_ii_driver_path_is_unique_and_cleaned():
    source = _function_source("scripts/run_deep_task.py", "_run_ii_researcher")
    assert '_egress.scratch_path("ii-researcher-driver")' in source
    assert "driver.unlink(missing_ok=True)" in source
    assert 'ROOT / "scripts" / "_ii_driver.py"' not in source


def test_qx_driver_path_is_unique_and_cleaned():
    source = _source("scripts/runners/qx_runner.py")
    assert '_egress.scratch_path("qx-benchmark-driver")' in source
    assert "driver_path.unlink(missing_ok=True)" in source
    assert 'QX_ROOT / "_benchmark_driver.py"' not in source


def test_model_probe_uses_each_cli_lanes_actual_endpoint(monkeypatch):
    import scripts.run_deep_task as rdt

    monkeypatch.setenv("DS_PROXY_URL", "http://canonical:8100/v1")
    monkeypatch.setenv("OPENCODE_LLM_BASE_URL", "http://opencode:9100/v1")
    monkeypatch.setenv("CODEX_DS_PROXY", "http://codex:9200/v1")
    monkeypatch.setenv("FLOWSEARCHER_LLM_BASE_URL", "http://flow:9300/v1")

    assert rdt._model_probe_endpoint("opencode") == (
        "http://opencode:9100/v1", "opencode-gateway"
    )
    assert rdt._model_probe_endpoint("codex") == (
        "http://codex:9200/v1", "codex-gateway"
    )
    assert rdt._model_probe_endpoint("flowsearcher-ds") == (
        "http://flow:9300/v1", "flowsearcher-gateway"
    )


def test_claude_endpoint_override_fails_closed(monkeypatch):
    import pytest
    import scripts.run_deep_task as rdt

    monkeypatch.setenv("CLAUDE_CODE_LOCAL_CCR_URL", "http://unknown-router:9999")
    with pytest.raises(RuntimeError, match="not identity-attestable"):
        rdt._model_probe_endpoint("claude-code")


def test_returned_error_stubs_cannot_be_recorded_as_pass():
    main_source = _function_source("scripts/run_deep_task.py", "main")
    classify_at = main_source.index("report_class = classify_report(report)")
    status_at = main_source.index('status = "fail" if err else "pass"')
    assert classify_at < status_at
    assert 'if report_class != "ok"' in main_source
    assert "runner returned {report_class}" in main_source


def test_codex_probe_fails_closed_on_loopback_endpoint(monkeypatch):
    """SPEC_ISSUES §2 (codex probe wrong host): codex executes on
    CODEX_SSH_HOST, where a loopback CODEX_DS_PROXY resolves to a DIFFERENT
    machine than the launcher probing it. Attesting the launcher's proxy while
    the lane's traffic uses the remote one certifies the wrong door; the
    protocol's own codex deviation says the probe belongs on the remote
    endpoint. Red on the old code, which returned the loopback tuple happily.
    """
    import pytest
    import scripts.run_deep_task as rdt

    monkeypatch.setenv("CODEX_DS_PROXY", "http://localhost:8100/v1")
    with pytest.raises(RuntimeError, match="not attestable"):
        rdt._model_probe_endpoint("codex")

    # The launcher-side default (no env at all) is loopback too: same refusal.
    monkeypatch.delenv("CODEX_DS_PROXY", raising=False)
    monkeypatch.delenv("DS_PROXY_URL", raising=False)
    with pytest.raises(RuntimeError, match="not attestable"):
        rdt._model_probe_endpoint("codex")

    # A both-hosts-reachable endpoint is attestable and proceeds unchanged.
    monkeypatch.setenv("CODEX_DS_PROXY", "http://my5090:8088/v1")
    assert rdt._model_probe_endpoint("codex") == (
        "http://my5090:8088/v1", "codex-gateway"
    )
