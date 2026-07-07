"""Unit tests for the deerflow runner's pure conf.yaml builders.

These cover the opt-in DEERFLOW_TOKEN_LIMIT knob that pins DeerFlow's
context-compression threshold to the real backbone window (needed because
the runner writes ``model: placeholder`` into conf.yaml, which defeats
DeerFlow's model-name-based token-limit inference).
"""
from scripts.runners.deerflow_runner import _build_conf_yaml, _resolve_token_limit


def test_resolve_token_limit_parses_positive_int():
    assert _resolve_token_limit("65536") == 65536
    assert _resolve_token_limit("  60000 ") == 60000


def test_resolve_token_limit_rejects_bad_values():
    # Unset / typo / non-positive all degrade to None (defer to DeerFlow).
    assert _resolve_token_limit(None) is None
    assert _resolve_token_limit("") is None
    assert _resolve_token_limit("abc") is None
    assert _resolve_token_limit("0") is None
    assert _resolve_token_limit("-5") is None


def test_build_conf_yaml_default_omits_token_limit():
    conf = _build_conf_yaml("http://localhost:8081")
    assert "token_limit" not in conf
    # Core structure preserved (unchanged historical behaviour).
    assert "ENABLE_WEB_SEARCH: true" in conf
    assert "engine: tavily" in conf
    assert "include_raw_content: true" in conf
    assert 'base_url: "http://placeholder.invalid/v1"' in conf


def test_build_conf_yaml_injects_token_limit_under_basic_model():
    conf = _build_conf_yaml("http://localhost:8081", token_limit=60000)
    assert "  token_limit: 60000" in conf
    lines = conf.splitlines()
    # token_limit must sit inside the BASIC_MODEL block (before the blank
    # line that separates it from ENABLE_WEB_SEARCH).
    ti = lines.index("  token_limit: 60000")
    assert lines[0] == "BASIC_MODEL:"
    assert lines[ti - 1].strip() == "max_retries: 3"
    assert lines[ti + 1] == ""  # blank separator, block closed cleanly


def test_build_conf_yaml_yaml_parses_both_ways():
    import yaml  # PyYAML is a DeerFlow/runtime dependency

    d0 = yaml.safe_load(_build_conf_yaml("http://localhost:8081"))
    assert "token_limit" not in d0["BASIC_MODEL"]
    assert d0["ENABLE_WEB_SEARCH"] is True
    assert d0["SEARCH_ENGINE"]["engine"] == "tavily"

    d1 = yaml.safe_load(_build_conf_yaml("http://localhost:8081", token_limit=65536))
    assert d1["BASIC_MODEL"]["token_limit"] == 65536
    assert d1["SEARCH_ENGINE"]["include_raw_content"] is True
