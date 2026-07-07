"""Unit tests for the opencode runner's LLM-endpoint wiring.

Regression guard for the box smoke failure where opencode reached vLLM
(:8001) directly with an unclamped max_tokens (32000) and got an HTTP 400
(prompt 8961 + 32000 > --max-model-len 40960). Two seatbelts are asserted:

  1. The ds-shim `baseURL` defaults to the harness-wired proxy_url (the
     clamp proxy on the box), and is overridable, without hardcoding a
     box-specific port that would break GLM/CCR.
  2. The generated opencode config caps output tokens at <= 3840 by default,
     independent of any proxy, so the request is safe even if the clamp is
     bypassed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.runners.opencode_runner import (  # noqa: E402
    _opencode_config,
    _resolve_context_limit,
    _resolve_llm_base_url,
    _resolve_output_cap,
)

_ENDPOINT_ENV = (
    "OPENCODE_LLM_BASE_URL",
    "OPENCODE_DS_PROXY",
    "DS_PROXY_URL",
    "OPENCODE_MAX_OUTPUT_TOKENS",
    "OPENCODE_CONTEXT_LIMIT",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ENDPOINT_ENV:
        monkeypatch.delenv(k, raising=False)
    yield


def test_base_url_defaults_to_harness_proxy(monkeypatch):
    # No overrides set: the harness-wired proxy_url (the clamp proxy on the
    # box) must win. This is the exact bug fix: the stale :8088 default no
    # longer silently outranks proxy_url.
    assert _resolve_llm_base_url("http://127.0.0.1:8002/v1") == "http://127.0.0.1:8002/v1"


def test_explicit_ds_proxy_env_outranks_proxy_arg(monkeypatch):
    # glm_oneagent.sh sets OPENCODE_DS_PROXY=$DS_PROXY_URL; an explicit value
    # is still honoured (GLM/CCR path keeps working).
    monkeypatch.setenv("OPENCODE_DS_PROXY", "http://127.0.0.1:8092/v1")
    assert _resolve_llm_base_url("http://127.0.0.1:8002/v1") == "http://127.0.0.1:8092/v1"


def test_opencode_llm_base_url_is_top_priority(monkeypatch):
    monkeypatch.setenv("OPENCODE_LLM_BASE_URL", "http://127.0.0.1:9000/v1")
    monkeypatch.setenv("OPENCODE_DS_PROXY", "http://127.0.0.1:8092/v1")
    assert _resolve_llm_base_url("http://127.0.0.1:8002/v1") == "http://127.0.0.1:9000/v1"


def test_base_url_falls_back_to_ds_proxy_env(monkeypatch):
    monkeypatch.setenv("DS_PROXY_URL", "http://127.0.0.1:8002/v1")
    assert _resolve_llm_base_url(None) == "http://127.0.0.1:8002/v1"


def test_base_url_last_resort_default(monkeypatch):
    assert _resolve_llm_base_url(None) == "http://localhost:8088/v1"


def test_output_cap_default_is_safe():
    assert _resolve_output_cap() == 3840


def test_output_cap_and_context_env_override(monkeypatch):
    monkeypatch.setenv("OPENCODE_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("OPENCODE_CONTEXT_LIMIT", "131072")
    assert _resolve_output_cap() == 8192
    assert _resolve_context_limit() == 131072


def test_bad_env_values_fall_back(monkeypatch):
    monkeypatch.setenv("OPENCODE_MAX_OUTPUT_TOKENS", "garbage")
    monkeypatch.setenv("OPENCODE_CONTEXT_LIMIT", "")
    assert _resolve_output_cap() == 3840
    assert _resolve_context_limit() == 40960


def test_generated_config_qwen3_8b_endpoint_and_cap(monkeypatch):
    # The concrete artifact the box consumes: base_url points at the clamp
    # proxy and every model carries a <=3840 output cap + context window.
    base_url = _resolve_llm_base_url("http://127.0.0.1:8002/v1")
    cfg = _opencode_config("qwen3-8b", base_url, strict_sandbox=False)
    provider = cfg["provider"]["ds-shim"]
    assert provider["options"]["baseURL"] == "http://127.0.0.1:8002/v1"
    models = provider["models"]
    assert "qwen3-8b" in models
    for model_id, spec in models.items():
        assert spec["limit"]["output"] <= 3840, model_id
        assert spec["limit"]["context"] == 40960, model_id
    # The failing smoke's total would now be 8961 + 3840 = 12801 < 40960.
    assert 8961 + models["qwen3-8b"]["limit"]["output"] < 40960


def test_generated_config_has_no_hardcoded_box_port(monkeypatch):
    # GLM operator points opencode at their own proxy; nothing forces :8002.
    monkeypatch.setenv("OPENCODE_DS_PROXY", "http://127.0.0.1:8092/v1")
    base_url = _resolve_llm_base_url("http://127.0.0.1:8092/v1")
    cfg = _opencode_config("glm-4.7-flash", base_url, strict_sandbox=False)
    assert cfg["provider"]["ds-shim"]["options"]["baseURL"] == "http://127.0.0.1:8092/v1"
