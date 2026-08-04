"""Offline regression tests for two judge bugs.

B2: ``pairwise_judge.battle(model=...)`` must actually use the chosen model.
    Previously ``_judge_once`` called ``call_judge(...)`` WITHOUT a model, so
    ``call_judge`` re-read JUDGE_MODEL from the environment and the resolved /
    stamped ``judge_model`` could lie. We assert the model arg is threaded all
    the way into ``call_judge`` and stamped truthfully.

B4: GLM-family judges must have reasoning/thinking disabled (or be given an
    adequate token budget) so chain-of-thought does not eat the tight 1500
    pairwise budget and yield empty content -> spurious TIE. We assert the
    extra body sent to the backend disables thinking for glm-* models, both on
    the OpenAI-compatible path and the bigmodel anthropic-compatible path.

Everything is mocked; no network and no API key are touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.scoring.pairwise_judge as pairwise_mod  # noqa: E402
import src.verifiers.judge_client as jc  # noqa: E402
from src.scoring.pairwise_judge import battle  # noqa: E402
from src.verifiers.judge_client import call_judge  # noqa: E402


# ---------------------------------------------------------------------------
# B2: the chosen model is honored end to end through battle -> call_judge
# ---------------------------------------------------------------------------
def _capture_calls(calls: list[dict]):
    def fake_call_judge(system, user, *, model=None, max_tokens=2000, **kw):  # type: ignore[no-untyped-def]
        calls.append({"model": model, "max_tokens": max_tokens})
        return "reason\nVERDICT: A", None

    return fake_call_judge


def test_battle_threads_explicit_model_into_call_judge(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(pairwise_mod, "call_judge", _capture_calls(calls))
    # Set a DIFFERENT model in the env. If the model arg were dropped, the
    # captured model would be this env value, not the explicit one.
    monkeypatch.setenv("JUDGE_MODEL", "deepseek-v4-flash")
    monkeypatch.delenv("PAIRWISE_JUDGE_MODEL", raising=False)

    res = battle(
        task_intent="Compare.",
        agent_a="alpha",
        answer_a="report A",
        agent_b="beta",
        answer_b="report B",
        model="glm-5.1",
        swap_for_position_bias=True,
        n_samples=2,
    )

    assert calls, "call_judge was never invoked"
    # Every call_judge invocation got the explicit model, not the env default.
    assert all(c["model"] == "glm-5.1" for c in calls), calls
    # The stamped judge_model reflects the ACTUAL model used, not the env.
    assert res["judge_model"] == "glm-5.1"


def test_battle_default_model_falls_back_to_env(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(pairwise_mod, "call_judge", _capture_calls(calls))
    monkeypatch.setenv("PAIRWISE_JUDGE_MODEL", "glm-5.1")
    monkeypatch.delenv("JUDGE_MODEL", raising=False)

    res = battle(
        task_intent="Compare.",
        agent_a="alpha",
        answer_a="report A",
        agent_b="beta",
        answer_b="report B",
        # no explicit model -> resolves from env (PAIRWISE_JUDGE_MODEL)
        swap_for_position_bias=False,
        n_samples=1,
    )

    assert calls and calls[0]["model"] == "glm-5.1"
    assert res["judge_model"] == "glm-5.1"


def test_call_judge_model_arg_overrides_env(monkeypatch):
    """call_judge(model=...) must override JUDGE_MODEL for that call."""
    seen: dict = {}

    def fake_openai(system, user, *, model, max_tokens, temperature):  # type: ignore[no-untyped-def]
        seen["model"] = model
        return "ok", None

    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(jc, "_call_openai", fake_openai)

    call_judge("sys", "user", model="glm-5.1")
    assert seen["model"] == "glm-5.1"

    # Without an explicit model, fall back to the env default (back-compat).
    seen.clear()
    call_judge("sys", "user")
    assert seen["model"] == "deepseek-v4-flash"


# ---------------------------------------------------------------------------
# B4: GLM-family judges disable thinking so the 1500-token budget is usable
# ---------------------------------------------------------------------------
class _FakeMessage:
    def __init__(self, content):
        self.content = content
        self.reasoning_content = ""


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeChatResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeOpenAIClient:
    """Records the kwargs passed to chat.completions.create."""

    last_kwargs: dict = {}

    def __init__(self, *a, **k):
        pass

    class _Chat:
        class _Completions:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                _FakeOpenAIClient.last_kwargs = kwargs
                return _FakeChatResp("reason\nVERDICT: A")

        def __init__(self):
            self.completions = _FakeOpenAIClient._Chat._Completions()

    @property
    def chat(self):
        return _FakeOpenAIClient._Chat()


def test_glm_disables_thinking_on_openai_path(monkeypatch):
    # _call_openai does `from openai import OpenAI` at call time, so patching
    # the OpenAI attribute on the openai module makes the local import resolve
    # to our fake client.
    import openai as openai_mod

    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAIClient, raising=False)

    text, err = call_judge("sys", "user", model="glm-5.1", max_tokens=1500)
    assert err is None and text
    extra = _FakeOpenAIClient.last_kwargs.get("extra_body") or {}
    assert extra.get("thinking") == {"type": "disabled"}, _FakeOpenAIClient.last_kwargs


def test_deepseek_v4_still_disables_thinking_on_openai_path(monkeypatch):
    import openai as openai_mod

    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAIClient, raising=False)

    call_judge("sys", "user", model="deepseek-v4-flash", max_tokens=1500)
    extra = _FakeOpenAIClient.last_kwargs.get("extra_body") or {}
    assert extra.get("thinking") == {"type": "disabled"}


def test_non_reasoning_model_sends_no_thinking_flag(monkeypatch):
    import openai as openai_mod

    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAIClient, raising=False)

    _FakeOpenAIClient.last_kwargs = {}
    call_judge("sys", "user", model="deepseek-chat", max_tokens=1500)
    # extra_body is passed as None when empty (back-compat: do not send thinking).
    assert _FakeOpenAIClient.last_kwargs.get("extra_body") is None


def test_openai_json_object_mode_is_explicitly_opt_in(monkeypatch):
    import openai as openai_mod

    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")
    monkeypatch.setenv("JUDGE_JSON_OBJECT", "1")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAIClient, raising=False)

    _FakeOpenAIClient.last_kwargs = {}
    call_judge("sys", "user", model="qwen3-8b", max_tokens=1500)

    assert _FakeOpenAIClient.last_kwargs["response_format"] == {
        "type": "json_object"
    }


def test_openai_json_schema_takes_precedence_over_json_object_mode(monkeypatch):
    import openai as openai_mod

    schema = {
        "type": "object",
        "properties": {"verdicts": {"type": "array"}},
        "required": ["verdicts"],
        "additionalProperties": False,
    }
    monkeypatch.setenv("JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")
    monkeypatch.setenv("JUDGE_JSON_OBJECT", "1")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAIClient, raising=False)

    _FakeOpenAIClient.last_kwargs = {}
    call_judge(
        "sys",
        "user",
        model="qwen3-8b",
        max_tokens=1500,
        response_schema=schema,
    )

    assert _FakeOpenAIClient.last_kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "dra_audited_judge_response",
            "schema": schema,
            "strict": True,
        },
    }


# --- anthropic-compatible (bigmodel) path -----------------------------------
# The anthropic SDK may not be installed in CI. ``_call_anthropic`` imports it
# locally, so we inject a fake ``anthropic`` module into sys.modules; the local
# import then resolves to our fake regardless of whether the real SDK exists.
import types  # noqa: E402


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeAnthropicResp:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeAnthropicClient:
    last_kwargs: dict = {}

    def __init__(self, *a, **k):
        self.messages = self

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        _FakeAnthropicClient.last_kwargs = kwargs
        return _FakeAnthropicResp("reason\nVERDICT: A")


def _install_fake_anthropic(monkeypatch):
    fake = types.ModuleType("anthropic")
    fake.Anthropic = _FakeAnthropicClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def test_glm_disables_thinking_on_anthropic_path(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("JUDGE_PROVIDER", "anthropic")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")

    _FakeAnthropicClient.last_kwargs = {}
    text, err = call_judge("sys", "user", model="glm-5.1", max_tokens=1500)
    assert err is None and text
    extra = _FakeAnthropicClient.last_kwargs.get("extra_body") or {}
    assert extra.get("thinking") == {"type": "disabled"}, _FakeAnthropicClient.last_kwargs


def test_claude_path_sends_no_thinking_flag(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("JUDGE_PROVIDER", "anthropic")
    monkeypatch.setenv("JUDGE_API_KEY", "dummy-key")

    _FakeAnthropicClient.last_kwargs = {}
    call_judge("sys", "user", model="claude-3-7-sonnet", max_tokens=1500)
    # Legacy Claude path unchanged: no extra_body thinking flag.
    assert _FakeAnthropicClient.last_kwargs.get("extra_body") is None
