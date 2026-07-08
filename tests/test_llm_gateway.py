"""Unit tests for the unified LLM gateway (integrations/llm_gateway/app.py).

Upstream is faked with an httpx.MockTransport so no real backbone is hit. Each
test reloads the module under a clean env (the usage-log path and keys are read
at import time / request time) and monkeypatches the module's httpx.AsyncClient
so every forwarded request lands on our stub router.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Router:
    """Programmable stub upstream. `queue` is a list of (status, headers, body)
    the router returns in order (last one repeats). Records every request."""

    def __init__(self):
        self.queue: list[tuple[int, dict, object]] = []
        self.requests: list[httpx.Request] = []

    def add_json(self, status: int, body: dict):
        self.queue.append((status, {"content-type": "application/json"}, body))

    def add_text(self, status: int, text: str):
        self.queue.append((status, {"content-type": "text/plain"}, text))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        idx = min(len(self.requests) - 1, len(self.queue) - 1)
        status, headers, body = self.queue[idx]
        if isinstance(body, (dict, list)):
            return httpx.Response(status, headers=headers, json=body)
        return httpx.Response(status, headers=headers, content=str(body).encode())

    def last_body(self) -> dict:
        return json.loads(self.requests[-1].content)


@pytest.fixture
def make_gw(monkeypatch, tmp_path):
    """Factory: (env_overrides) -> (module, TestClient, Router)."""

    def _make(env: dict | None = None):
        env = env or {}
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        # Fresh import so import-time config (USAGE_LOG, registry) is re-read.
        sys.modules.pop("integrations.llm_gateway.app", None)
        mod = importlib.import_module("integrations.llm_gateway.app")
        mod = importlib.reload(mod)

        router = Router()
        transport = httpx.MockTransport(router.handler)

        real_client = mod.httpx.AsyncClient

        def _client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(mod.httpx, "AsyncClient", _client_factory)
        return mod, TestClient(mod.app), router

    return _make


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
def test_prefix_routing_qwen(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": [], "usage": {}})
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert str(router.requests[-1].url).startswith("http://127.0.0.1:8001/v1")


def test_prefix_routing_glm(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": [], "usage": {}})
    r = client.post("/v1/chat/completions",
                    json={"model": "glm-4.7-flash", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "bigmodel.cn" in str(router.requests[-1].url)


def test_unknown_model_404(make_gw):
    mod, client, router = make_gw()
    r = client.post("/v1/chat/completions",
                    json={"model": "gpt-9", "messages": []})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["type"] == "model_not_found"
    assert "qwen3-8b" in err["known_prefixes"]
    assert router.requests == []  # never forwarded


# ---------------------------------------------------------------------------
# Policy pipeline
# ---------------------------------------------------------------------------
def test_floor_raises(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": []})
    # glm floor is 131072; caller asks for a tiny budget.
    client.post("/v1/chat/completions",
                json={"model": "glm-4.7-flash", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]})
    assert router.last_body()["max_tokens"] == 131072


def test_cap_lowers(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": []})
    # qwen cap is 8192; small prompt so fit does not bite.
    client.post("/v1/chat/completions",
                json={"model": "qwen3-8b", "max_tokens": 50000,
                      "messages": [{"role": "user", "content": "hi"}]})
    assert router.last_body()["max_tokens"] == 8192


def test_fit_to_window_clamps(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": []})
    big = "x" * 180000  # ~60k estimated tokens
    messages = [{"role": "user", "content": big}]
    est = len(json.dumps(messages, ensure_ascii=False)) // 3
    client.post("/v1/chat/completions",
                json={"model": "qwen3-8b", "max_tokens": 50000, "messages": messages})
    expected = 65536 - est - 256
    assert router.last_body()["max_tokens"] == expected
    assert expected < 8192  # fit bit harder than the cap


# ---------------------------------------------------------------------------
# Resilience: context-overflow refit-and-retry
# ---------------------------------------------------------------------------
_CTX_ERR = {
    "error": {
        "message": ("This model's maximum context length is 65536 tokens. However, "
                    "you requested 65537 tokens (8961 in the messages, 56576 in the "
                    "completion). Please reduce the length of the messages or completion."),
        "type": "BadRequestError",
        "code": 400,
    }
}


def test_ctx_overflow_retry_succeeds(make_gw):
    mod, client, router = make_gw()
    router.add_json(400, _CTX_ERR)          # first attempt: window+1
    router.add_json(200, {"choices": []})   # retry: succeeds
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 56576,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert len(router.requests) == 2  # retried exactly once
    # window - reported_prompt - margin = 65536 - 8961 - 256
    assert router.last_body()["max_tokens"] == 65536 - 8961 - 256


def test_ctx_overflow_retry_only_once(make_gw):
    mod, client, router = make_gw()
    router.add_json(400, _CTX_ERR)  # always 400
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 56576,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400          # passed through
    assert len(router.requests) == 2     # original + one retry, no more


# vLLM 0.23's phrasing, captured VERBATIM from the live :8001 serve during the
# 2026-07-07 smoke8e refit proof. Crucially "at least N input tokens" is a
# LOWER BOUND: vLLM reports exactly window+1-max_tokens (the smallest count
# proving overflow), NOT the true prompt size. A margin-step refit therefore
# re-overflows: the live gateway went 8192 -> "at least 57345" -> refit 7935
# -> "at least 57602" -> 400 leaked to the client (true prompt ~59.9k).
def _vllm023_ctx_err(requested_out: int) -> dict:
    inp = 65537 - requested_out  # vLLM's lower-bound arithmetic
    return {
        "error": {
            "message": (
                f"This model's maximum context length is 65536 tokens. However, "
                f"you requested {requested_out} output tokens and your prompt "
                f"contains at least {inp} input tokens, for a total of at least "
                f"65537 tokens. Please reduce the length of the input prompt or "
                f"the number of requested output tokens. "
                f"(parameter=input_tokens, value={inp})"
            ),
            "type": "BadRequestError",
            "param": "input_tokens",
            "code": 400,
        }
    }


def test_ctx_overflow_vllm023_lower_bound_halves(make_gw):
    """0.23 lower-bound phrasing: refit must halve, not margin-step."""
    mod, client, router = make_gw()
    router.add_json(400, _vllm023_ctx_err(8192))  # first attempt overflows
    router.add_json(200, {"choices": []})         # halved retry fits
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 8192,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert len(router.requests) == 2
    # min(margin-step 65536-57345-256=7935, half 8192//2=4096) == 4096
    assert router.last_body()["max_tokens"] == 4096


def test_ctx_overflow_vllm023_converges_in_loop(make_gw):
    """True prompt ~64k: several lower-bound 400s, loop converges to 200."""
    mod, client, router = make_gw()
    router.add_json(400, _vllm023_ctx_err(8192))  # cur 8192 -> refit 4096
    router.add_json(400, _vllm023_ctx_err(4096))  # cur 4096 -> refit 2048
    router.add_json(400, _vllm023_ctx_err(2048))  # cur 2048 -> refit 1024
    router.add_json(200, {"choices": []})         # 64k + 1024 fits
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 8192,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert len(router.requests) == 4
    assert router.last_body()["max_tokens"] == 1024


def test_ctx_overflow_vllm023_gives_up_bounded(make_gw):
    """Upstream overflows on every attempt: loop stays bounded, 400 surfaces.

    The queue mirrors what a always-overflowing vLLM would report for the
    max_tokens sequence the gateway's halving refit actually produces:
    8192 -> 4096 -> 2048 -> 1024 -> 512 -> 255 -> 127 (255 because the
    margin-step bound 65536-65025-256=255 is tighter than half=256 there)."""
    mod, client, router = make_gw()
    for out in (8192, 4096, 2048, 1024, 512, 255, 127):
        router.add_json(400, _vllm023_ctx_err(out))
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 8192,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    # 1 original + exactly the 6-retry loop bound
    assert len(router.requests) == 7


def _exact_ctx_err(in_messages: int, in_completion: int) -> dict:
    """Old exact-count vLLM phrasing: '(N in the messages)' reports the TRUE
    prompt size, so the refit lands on window - N - 1 in one step."""
    total = in_messages + in_completion
    return {
        "error": {
            "message": (f"This model's maximum context length is 65536 tokens. "
                        f"However, you requested {total} tokens ({in_messages} in the "
                        f"messages, {in_completion} in the completion). Please reduce "
                        f"the length of the messages or completion."),
            "type": "BadRequestError",
            "code": 400,
        }
    }


def test_ctx_overflow_refit_clamps_to_window_minus_input(make_gw):
    """Regression (2026-07-07): the refit gave up whenever fewer than 8 output
    tokens remained. It must clamp max_tokens to window - input - 1 and retry
    as long as that is >= 1."""
    mod, client, router = make_gw()
    router.add_json(400, _exact_ctx_err(65530, 512))  # window - input - 1 == 5
    router.add_json(200, {"choices": []})
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 512,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert len(router.requests) == 2
    assert router.last_body()["max_tokens"] == 65536 - 65530 - 1


def test_ctx_overflow_prompt_fills_window_gives_up(make_gw):
    """Prompt alone fills the whole window: protocol-level unfixable. The 400
    passes through immediately (no futile retries) and carries the gateway
    diagnostics that name the ACTUAL routed model + window."""
    mod, client, router = make_gw()
    router.add_json(400, _exact_ctx_err(65536, 1))  # avail = -1
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 512,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    assert len(router.requests) == 1  # no pointless retry
    gw = r.json()["gateway"]
    assert gw["reason"] == "prompt_overflow_unfixable"
    assert gw["routed_model"] == "qwen3-8b"
    assert gw["context_window"] == 65536
    # original upstream error text is preserved alongside the tag
    assert "maximum context length" in r.json()["error"]["message"]


def test_stream_error_path_writes_usage(make_gw, tmp_path):
    """Regression (2026-07-07): streaming error responses wrote NO usage line,
    so the claude-code lane's leaked 400s were invisible in the usage log."""
    log = tmp_path / "usage.jsonl"
    mod, client, router = make_gw({"LLMGW_USAGE_LOG": str(log)})
    router.add_json(400, _exact_ctx_err(65536, 1))  # unfixable overflow
    r = client.post("/v1/chat/completions",
                    json={"model": "qwen3-8b", "max_tokens": 512, "stream": True,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
    assert r.json()["gateway"]["reason"] == "prompt_overflow_unfixable"
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    usage = [x for x in lines if x.get("model") == "qwen3-8b"]
    assert len(usage) == 1, "stream error path must write exactly one usage line"
    assert usage[0]["stream"] is True
    assert usage[0]["status"] == 400
    assert usage[0]["ctx_overflow_giveup"] is True


# ---------------------------------------------------------------------------
# thinking-off injection
# ---------------------------------------------------------------------------
def test_thinking_off_deepseek_only(make_gw):
    mod, client, router = make_gw()
    router.add_json(200, {"choices": []})
    client.post("/v1/chat/completions",
                json={"model": "deepseek-v4-flash",
                      "messages": [{"role": "user", "content": "hi"}]})
    assert router.last_body().get("thinking") == {"type": "disabled"}

    router.queue.clear()
    router.requests.clear()
    router.add_json(200, {"choices": []})
    client.post("/v1/chat/completions",
                json={"model": "qwen3-8b",
                      "messages": [{"role": "user", "content": "hi"}]})
    assert "thinking" not in router.last_body()


# ---------------------------------------------------------------------------
# Usage accounting + run brackets
# ---------------------------------------------------------------------------
def test_usage_log_tagged_with_run_id(make_gw, tmp_path):
    log = tmp_path / "usage.jsonl"
    mod, client, router = make_gw({"LLMGW_USAGE_LOG": str(log)})
    router.add_json(200, {"choices": [],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                    "total_tokens": 15}})
    assert client.post("/_mark", json={"phase": "start", "run_id": "run-42"}).status_code == 200
    client.post("/v1/chat/completions",
                json={"model": "qwen3-8b",
                      "messages": [{"role": "user", "content": "hi"}]})
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    usage_lines = [x for x in lines if x.get("prompt_tokens") == 10]
    assert usage_lines, "usage line not written"
    u = usage_lines[-1]
    assert u["run_id"] == "run-42"
    assert u["model"] == "qwen3-8b"
    assert "latency_ms" in u
    assert "fit_adjustments" in u


def test_mark_end_closes_bracket(make_gw, tmp_path):
    log = tmp_path / "usage.jsonl"
    mod, client, router = make_gw({"LLMGW_USAGE_LOG": str(log)})
    client.post("/_mark", json={"phase": "start", "run_id": "r1"})
    client.post("/_mark", json={"phase": "end", "run_id": "r1"})
    router.add_json(200, {"choices": [], "usage": {"prompt_tokens": 1}})
    client.post("/v1/chat/completions",
                json={"model": "qwen3-8b", "messages": [{"role": "user", "content": "hi"}]})
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    usage = [x for x in lines if x.get("prompt_tokens") == 1][-1]
    assert "run_id" not in usage  # bracket closed


# ---------------------------------------------------------------------------
# Introspection endpoints never leak keys
# ---------------------------------------------------------------------------
def test_healthz_no_key_leak(make_gw):
    secret = "sk-super-secret-DEADBEEF"
    mod, client, router = make_gw({"GLM_API_KEY": secret, "DASHSCOPE_API_KEY": secret})
    r = client.get("/healthz")
    assert r.status_code == 200
    assert secret not in r.text
    prefixes = [m["prefix"] for m in r.json()["models"]]
    assert "glm-4.7-flash" in prefixes and "deepseek-v4" in prefixes
    # only the env-var NAME is exposed, never contents
    assert any(m["api_key_env"] == "GLM_API_KEY" for m in r.json()["models"])


def test_models_listing(make_gw):
    mod, client, router = make_gw()
    r = client.get("/v1/models")
    ids = [m["id"] for m in r.json()["data"]]
    assert {"qwen3-8b", "glm-4.7-flash", "deepseek-v4"} <= set(ids)


# ---------------------------------------------------------------------------
# LLM_GATEWAY_CONFIG override
# ---------------------------------------------------------------------------
def test_config_extends_registry(make_gw, tmp_path):
    cfg = tmp_path / "gw.json"
    cfg.write_text(json.dumps([
        {"prefix": "my-model", "upstream": "http://example/v1",
         "context_window": 1000, "thinking_off": True},
    ]))
    mod, client, router = make_gw({"LLM_GATEWAY_CONFIG": str(cfg)})
    router.add_json(200, {"choices": []})
    client.post("/v1/chat/completions",
                json={"model": "my-model-x", "messages": [{"role": "user", "content": "hi"}]})
    assert "example" in str(router.requests[-1].url)
    assert router.last_body().get("thinking") == {"type": "disabled"}
