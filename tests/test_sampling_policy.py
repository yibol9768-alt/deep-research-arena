"""One sampler, stamped where every lane's request passes.

The protocol declared the backbone knobs "identical across lanes AND across
backbones" and named the proxy as the enforcement point. No proxy enforced
anything. And enforcing it in ONE proxy equalises one lane:
`run_deep_task._setup_ds_backbone` points eleven lanes at ds_proxy (:8088); only
claude-code goes through llm_gateway (:8100). The first version of this fix
landed in the gateway alone.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations import sampling_policy as sp        # noqa: E402
from integrations.ds_proxy import app as dsp          # noqa: E402
from integrations.llm_gateway import app as gw        # noqa: E402


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    for v in ("DRA_FORCE_TEMPERATURE", "DRA_FORCE_TOP_P"):
        monkeypatch.delenv(v, raising=False)
    sp.reset_for_tests()
    yield
    sp.reset_for_tests()


def _declared() -> dict:
    return yaml.safe_load((ROOT / "config" / "lane_protocol.yaml").read_text())["backbone"]


def test_the_forced_values_come_from_the_protocol():
    d = _declared()
    assert sp.forced_temperature() == float(d["temperature"])
    assert sp.forced_top_p() == float(d["top_p"])


@pytest.mark.parametrize("body", [
    {"temperature": 0.7, "top_p": 0.9},   # storm / costorm
    {},                                   # inherits the upstream default (~1.0)
    {"temperature": 0.2},                 # conforming temperature, no top_p
])
def test_ds_proxy_path_stamps_both_knobs(body):
    """ds_proxy is the door eleven lanes use."""
    sp.apply_sampling(body)
    assert body["temperature"] == sp.forced_temperature()
    assert body["top_p"] == sp.forced_top_p()


@pytest.mark.parametrize("body", [{"temperature": 0.7, "top_p": 0.9}, {}])
def test_llm_gateway_path_stamps_both_knobs(body):
    gw._apply_policy({"thinking_off": False}, body)
    assert body["temperature"] == sp.forced_temperature()
    assert body["top_p"] == sp.forced_top_p()


def test_a_conforming_request_reports_no_adjustment():
    body = {"temperature": sp.forced_temperature(), "top_p": sp.forced_top_p()}
    assert sp.apply_sampling(body) == []


def test_override_can_be_disabled_for_a_non_benchmark_deployment(monkeypatch):
    monkeypatch.setenv("DRA_FORCE_TEMPERATURE", "off")
    monkeypatch.setenv("DRA_FORCE_TOP_P", "off")
    sp.reset_for_tests()
    body = {"temperature": 0.7, "top_p": 0.9}
    assert sp.apply_sampling(body) == []
    assert body == {"temperature": 0.7, "top_p": 0.9}


def test_thinking_declaration_describes_the_code_not_an_aspiration():
    """`thinking: uniform` was a word nothing checked. It is not uniform.

    glm keeps thinking ON per the 2026-07-06 decision and deepseek is forced OFF,
    so a cross-backbone board compares a reasoning model against a non-reasoning
    one. Equalising it is the maintainer's call; agreeing about what is true is
    not. This pins the declaration to `ds_proxy._needs_thinking_off`.
    """
    decl = sp.declared_thinking()
    per = {k: str(v).lower() for k, v in decl["per_backbone"].items()}
    actual = {p: ("off" if dsp._needs_thinking_off(p) else "on") for p in per}
    assert per == actual, f"declared {per} but code does {actual}"
    assert decl["uniform"] is False, \
        "if thinking is now uniform, say so and delete the disclosure"


# --- the output-token budget is part of the sampler contract ---------------
#
# lane_protocol declared max_output_tokens: 8192 "identical across lanes AND
# across backbones". What ran: the gateway capped qwen at 8192, left deepseek
# UNCAPPED, and RAISED glm to 131072 -- a 16x output-budget spread feeding
# completeness (0.33 of quality weight) -- and ds_proxy enforced nothing. glm's
# exception is the thinking decision made visible (thinking ON spends from the
# same max_tokens budget) and is now DECLARED in max_output_tokens_exceptions.

def test_ceiling_resolves_from_the_protocol_with_declared_exceptions():
    assert sp.max_output_tokens_for("qwen3-8b") == 8192
    assert sp.max_output_tokens_for("deepseek-v4-flash") == 8192
    assert sp.max_output_tokens_for("glm-4.7-flash") == 131072
    assert sp.max_output_tokens_for("some-new-model") == 8192, \
        "an undeclared backbone gets the uniform value, not a free ride"


@pytest.mark.parametrize("asked,want", [(999_999, 8192), (None, 8192), (4096, 4096)])
def test_deepseek_is_clamped_never_unbounded(asked, want):
    body = {"model": "deepseek-v4-flash"}
    if asked is not None:
        body["max_tokens"] = asked
    sp.apply_max_tokens(body)
    assert body["max_tokens"] == want


def test_a_lane_sending_nothing_does_not_inherit_the_upstream_default():
    """Absent max_tokens delegates to the upstream default, which differs per
    backbone -- the exact non-uniformity this exists to end."""
    body = {"model": "qwen3-8b"}
    assert sp.apply_max_tokens(body) == ["max_tokens"]
    assert body["max_tokens"] == 8192


def test_gateway_door_enforces_the_ceiling_end_to_end():
    import integrations.llm_gateway.app as gw
    for model, want in (("deepseek-v4-flash", 8192), ("qwen3-8b", 8192),
                        ("glm-4.7-flash", 131072)):
        body = {"model": model, "max_tokens": 999_999}
        gw._apply_policy(gw._match_entry(model) or {}, body)
        assert body["max_tokens"] == want, (model, body["max_tokens"])


def test_max_tokens_enforcement_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DRA_FORCE_MAX_TOKENS", "off")
    body = {"model": "deepseek-v4-flash", "max_tokens": 999_999}
    assert sp.apply_max_tokens(body) == []
    assert body["max_tokens"] == 999_999


# --- ops floor may never override the declared ceiling (SPEC_ISSUES §2) ------
#
# OPENAI_PROXY_MIN_MAX_TOKENS ran AFTER apply_max_tokens with no bound, so an
# ops env could push every ds_proxy request past the declared ceiling while the
# gateway door still enforced it: the same request left the two doors with
# different budgets, and the declaration stopped being the last word. The floor
# is now bounded by the per-model ceiling. Red on the old code: the first test
# read 200000.

def test_ds_proxy_ops_floor_is_bounded_by_the_declared_ceiling(monkeypatch):
    monkeypatch.setattr(dsp, "MIN_MAX_TOKENS", 200_000)
    body = {"model": "deepseek-v4-flash", "max_tokens": 256}
    dsp._apply_min_max_tokens(body)
    assert body["max_tokens"] == 8192  # raised to the ceiling, not past it


def test_ds_proxy_ops_floor_below_ceiling_still_rescues_a_starved_budget(monkeypatch):
    # The floor's declared purpose (room for CoT + answer) survives the bound.
    monkeypatch.setattr(dsp, "MIN_MAX_TOKENS", 4096)
    body = {"model": "deepseek-v4-flash", "max_tokens": 256}
    dsp._apply_min_max_tokens(body)
    assert body["max_tokens"] == 4096


def test_ds_proxy_ops_floor_respects_the_glm_exception_ceiling(monkeypatch):
    # Per-model ceiling, not the base: glm's declared exception is 131072.
    monkeypatch.setattr(dsp, "MIN_MAX_TOKENS", 200_000)
    body = {"model": "glm-4.7-flash", "max_tokens": 100}
    dsp._apply_min_max_tokens(body)
    assert body["max_tokens"] == 131_072


def test_ds_proxy_ops_floor_off_is_a_no_op(monkeypatch):
    monkeypatch.setattr(dsp, "MIN_MAX_TOKENS", 0)
    body = {"model": "deepseek-v4-flash", "max_tokens": 256}
    dsp._apply_min_max_tokens(body)
    assert body["max_tokens"] == 256
