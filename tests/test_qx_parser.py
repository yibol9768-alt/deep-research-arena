from __future__ import annotations

import sys
import types

import pytest

from scripts.runners.qx_runner import _ROBUST_PARSER_SRC, _persist_native_diagnostics


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
