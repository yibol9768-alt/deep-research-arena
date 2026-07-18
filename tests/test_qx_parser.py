from __future__ import annotations

import ast
import sys
import types

import pytest

from scripts.runners.qx_runner import (
    _ROBUST_PARSER_SRC,
    _build_driver_script,
    _persist_native_diagnostics,
)


class _OutputParserError(Exception):
    pass


def _load_parser(monkeypatch):
    deep = types.ModuleType("deep_researcher")
    agents = types.ModuleType("deep_researcher.agents")
    utils = types.ModuleType("deep_researcher.agents.utils")
    parse_output = types.ModuleType("deep_researcher.agents.utils.parse_output")
    for package in (deep, agents, utils):
        package.__path__ = []
    parse_output.OutputParserError = _OutputParserError
    deep.agents = agents
    agents.utils = utils
    utils.parse_output = parse_output
    for name, module in (
        ("deep_researcher", deep),
        ("deep_researcher.agents", agents),
        ("deep_researcher.agents.utils", utils),
        ("deep_researcher.agents.utils.parse_output", parse_output),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    namespace: dict[str, object] = {}
    exec(_ROBUST_PARSER_SRC, namespace)
    return namespace["_rp_parse_json"]


def test_qx_parser_accepts_strict_fenced_and_prose_wrapped_json(monkeypatch):
    parse = _load_parser(monkeypatch)
    assert parse('{"tasks": []}') == {"tasks": []}
    assert parse('```json\n{"tasks": [{"query": "x"}]}\n```') == {
        "tasks": [{"query": "x"}]
    }
    assert parse('Here is the result: {"research_complete": true, "outstanding_gaps": []}.') == {
        "research_complete": True,
        "outstanding_gaps": [],
    }


def test_qx_parser_reports_invalid_text_without_index_error(monkeypatch):
    parse = _load_parser(monkeypatch)
    with pytest.raises(_OutputParserError, match="Failed to parse output as JSON"):
        parse("plain text with no structured result")


def test_failed_native_transcript_is_persisted_outside_scored_files(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("DEEP_RUN_OUT_DIR", str(tmp_path))
    target = _persist_native_diagnostics("native stdout", "native stderr")
    assert target == tmp_path / ".diagnostics" / "qx-native"
    assert (target / "stdout.log").read_text() == "native stdout"
    assert (target / "stderr.log").read_text() == "native stderr"


def test_qx_driver_fails_closed_when_native_search_tool_is_not_registered():
    driver = _build_driver_script(
        "research task",
        "http://127.0.0.1:19100",
        "gpt-5.6-luna",
        "http://127.0.0.1:18500/v1",
        "http://127.0.0.1:18400",
    )
    ast.parse(driver)
    assert "init_search_agent(config)" in driver
    assert "config.search_provider != 'searchxng'" in driver
    assert "expected one invokable web_search tool" in driver
    assert "_QX_SEARCH_ADAPTER_HOST" in driver
    assert "self._trust_env = False" in driver
    assert "_QX_SEARCH_ADAPTER_URL + '/healthz'" in driver
    assert "_qx_research_module.init_tool_agents = _qx_init_sandbox_tool_agents" in driver
    assert "'SiteCrawlerAgent': _search_agent" in driver
    assert "SiteCrawlerAgent is not mapped to the" in driver
    assert "Treat URLs contained in successful tool results as a closed source set" in driver
    assert "Never infer, reconstruct, or guess a source URL" in driver
    assert "_QX_SUCCESSFUL_FETCH_URLS.add(_site_url)" in driver
    assert "_agent_name in ('WriterAgent', 'LongWriterAgent')" in driver
    assert "<QX_SUCCESSFUL_FETCH_URL_MANIFEST>" in driver
    assert "Only URLs copied verbatim from this list" in driver
    assert "do not change their scheme" in driver
    assert "[qx-preflight] provider=searchxng tool=web_search" in driver
    assert "registered=1 host=" in driver
    assert "adapter_status=" in driver
    assert "site_crawler=searchxng-remap" in driver
    assert "source_contract=closed-set" in driver
    assert "source_manifest=http-200-fetches" in driver
