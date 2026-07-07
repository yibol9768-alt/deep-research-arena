"""Unified LLM gateway for the Deep Research Arena.

ONE OpenAI-compatible entry point (:8100 by convention) in front of every
backbone the arena uses. Framework lanes stop juggling ds_proxy / clamp proxy /
GLM proxy / direct-vLLM and per-lane base-URL env vars; they all point at this
gateway and per-model policy is applied server-side from a REGISTRY.

Design mirrors integrations/ds_proxy/app.py (proven mechanics: upstream
forwarding, streaming usage injection via stream_options.include_usage, usage
jsonl schema, POST /_mark run brackets, thinking-off injection) but adds:

  * a model REGISTRY keyed by model-name prefix (longest-prefix routing), with
    a distinct upstream + key + policy per backbone, extendable via
    LLM_GATEWAY_CONFIG (a JSON file);
  * a per-request policy pipeline: max_tokens_floor -> max_tokens_cap ->
    fit_to_window -> thinking_off;
  * a resilience retry that kills the "window+1" off-by-one class: when an
    upstream 400 complains about maximum context length / max_model_len, the
    reported prompt-token count is parsed, max_tokens is recomputed to fit, and
    the request is retried ONCE. This fixes claude-code, which budgets its
    prompt to (context_window - max_tokens) while vLLM counts one extra
    template/BOS token, so the naive request lands at exactly window+1 and 400s.

No plaintext API keys live in this file. Keys are read from the environment
named by each registry entry's `api_key_env`.

Run (workstation):
    LLMGW_USAGE_LOG=/var/log/llmgw_usage.jsonl \
    uvicorn integrations.llm_gateway.app:app --host 0.0.0.0 --port 8100

Client side:
    OPENAI_BASE_URL=http://127.0.0.1:8100/v1
    DS_PROXY_URL=http://127.0.0.1:8100/v1
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Each entry describes ONE backbone: where to send it, which env var holds its
# key (never the key itself), and the per-model policy knobs.
#
#   upstream          OpenAI-compat base URL (ends with /v1 or equivalent)
#   api_key_env       name of the env var holding the bearer key (or "")
#   context_window    total token window of the model
#   fit_to_window     clamp max_tokens so prompt+completion fits the window
#   fit_margin        safety slack subtracted during the fit (default 256)
#   max_tokens_cap    hard upper bound on max_tokens (lower it)
#   max_tokens_floor  lower bound on max_tokens (raise it)
#   thinking_off      inject {"thinking": {"type": "disabled"}} (ds_proxy knob)
# ---------------------------------------------------------------------------

_DASHSCOPE_BASE = os.environ.get(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")

DEFAULT_REGISTRY: list[dict[str, Any]] = [
    {
        "prefix": "qwen3-8b",
        "upstream": "http://127.0.0.1:8001/v1",
        "api_key_env": "",
        "context_window": 65536,
        "fit_to_window": True,
        "fit_margin": 256,
        "max_tokens_cap": 8192,
        "max_tokens_floor": 0,
        "thinking_off": False,
    },
    {
        "prefix": "glm-4.7-flash",
        "upstream": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "context_window": 204800,
        "fit_to_window": False,
        "fit_margin": 256,
        "max_tokens_cap": 0,
        # Thinking eats budget; a floor keeps the visible content non-empty.
        "max_tokens_floor": 131072,
        "thinking_off": False,
    },
    {
        "prefix": "deepseek-v4",
        "upstream": _DASHSCOPE_BASE,
        "api_key_env": "DASHSCOPE_API_KEY",
        "context_window": 65536,
        "fit_to_window": False,
        "fit_margin": 256,
        "max_tokens_cap": 0,
        "max_tokens_floor": 0,
        "thinking_off": True,
    },
]

_FIT_MARGIN_MIN = 256  # max_tokens never clamped below this


def _load_registry() -> list[dict[str, Any]]:
    """Built-in defaults, overridden/extended by LLM_GATEWAY_CONFIG (JSON).

    The config file may be a list of entries or an object with an "models"/
    "registry" key. Entries sharing a `prefix` with a default override it;
    new prefixes are appended. Missing policy keys inherit the default shape.
    """
    reg = {e["prefix"]: dict(e) for e in DEFAULT_REGISTRY}
    path = os.environ.get("LLM_GATEWAY_CONFIG", "").strip()
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                doc = json.load(f)
        except Exception:
            doc = None
        entries: list[dict[str, Any]] = []
        if isinstance(doc, list):
            entries = [e for e in doc if isinstance(e, dict)]
        elif isinstance(doc, dict):
            raw = doc.get("models") or doc.get("registry") or []
            if isinstance(raw, list):
                entries = [e for e in raw if isinstance(e, dict)]
        for e in entries:
            prefix = str(e.get("prefix", "")).strip()
            if not prefix:
                continue
            base = dict(reg.get(prefix, {"prefix": prefix}))
            base.update(e)
            reg[prefix] = base
    # Normalise defaults for any missing keys.
    out = []
    for e in reg.values():
        e.setdefault("api_key_env", "")
        e.setdefault("context_window", 65536)
        e.setdefault("fit_to_window", False)
        e.setdefault("fit_margin", _FIT_MARGIN_MIN)
        e.setdefault("max_tokens_cap", 0)
        e.setdefault("max_tokens_floor", 0)
        e.setdefault("thinking_off", False)
        out.append(e)
    # Longest prefix first so routing prefers the most specific match.
    out.sort(key=lambda e: len(e["prefix"]), reverse=True)
    return out


REGISTRY = _load_registry()


def _match_entry(model: str) -> dict[str, Any] | None:
    for e in REGISTRY:  # already longest-first
        if model.startswith(e["prefix"]):
            return e
    return None


# ---------------------------------------------------------------------------
# Usage accounting + run brackets
# ---------------------------------------------------------------------------
USAGE_LOG = os.environ.get("LLMGW_USAGE_LOG", "")
STREAM_USAGE = os.environ.get("LLMGW_STREAM_USAGE", "1") != "0"

# In-memory "currently open" run bracket, set by POST /_mark start/end. When a
# bracket is open every usage line is tagged with its run_id so the aggregator
# needs no timeline slicing for gateway-native runs.
_CURRENT_RUN: dict[str, Any] = {}


def _usage_write(record: dict) -> None:
    if not USAGE_LOG:
        return
    try:
        record.setdefault("ts", round(time.time(), 3))
        if _CURRENT_RUN.get("run_id") and "run_id" not in record:
            record["run_id"] = _CURRENT_RUN["run_id"]
        with open(USAGE_LOG, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Policy pipeline
# ---------------------------------------------------------------------------
def _estimate_prompt_tokens(messages: Any) -> int:
    """Cheap prompt-size heuristic (len(json.dumps(messages)) // 3)."""
    try:
        return len(json.dumps(messages, ensure_ascii=False)) // 3
    except Exception:
        return 0


def _apply_policy(entry: dict[str, Any], body: dict) -> list[str]:
    """Mutate `body` per the entry's policy. Order: floor -> cap ->
    fit_to_window -> thinking_off. Returns the list of adjustments applied
    (for usage accounting)."""
    adj: list[str] = []
    mt = body.get("max_tokens")

    # (1) floor: raise.
    floor = int(entry.get("max_tokens_floor") or 0)
    if floor > 0 and (mt is None or int(mt) < floor):
        body["max_tokens"] = floor
        mt = floor
        adj.append("floor")

    # (2) cap: lower.
    cap = int(entry.get("max_tokens_cap") or 0)
    if cap > 0 and mt is not None and int(mt) > cap:
        body["max_tokens"] = cap
        mt = cap
        adj.append("cap")

    # (3) fit_to_window: clamp so prompt + completion fits the window.
    if entry.get("fit_to_window"):
        window = int(entry.get("context_window") or 0)
        margin = int(entry.get("fit_margin") or _FIT_MARGIN_MIN)
        est = _estimate_prompt_tokens(body.get("messages"))
        fitted = window - est - margin
        if fitted < _FIT_MARGIN_MIN:
            fitted = _FIT_MARGIN_MIN
        if mt is None or int(mt) > fitted:
            body["max_tokens"] = fitted
            mt = fitted
            adj.append("fit")

    # (4) thinking_off: ds_proxy's exact disable knob.
    if entry.get("thinking_off") and "thinking" not in body:
        body["thinking"] = {"type": "disabled"}
        adj.append("thinking_off")

    return adj


# vLLM/OpenAI context-overflow errors. Grab the reported prompt tokens and, if
# present, the model's maximum context length so we can refit and retry ONCE.
_CTX_HINT_RE = re.compile(
    r"maximum context length|max_model_len|context length is|"
    r"reduce the length|too long",
    re.IGNORECASE,
)
# vLLM has shipped at least two phrasings of the overflow error:
#   old:   "... 65537 tokens (65281 in the messages) ..."
#   0.23:  "... your prompt contains at least 65281 input tokens ...
#           (parameter=input_tokens, value=65281)"
# Smoke 2026-07-07 (claude-code lane): the 0.23 phrasing did not match the old
# single-pattern regex, so the refit-and-retry never fired and the window+1
# 400 leaked through to the client.
#
# Smoke 2026-07-07 (refit proof, ~60k-token prompt): the 0.23 phrasing is a
# LOWER BOUND, not the true prompt size. vLLM reports input_tokens as exactly
# window+1-max_tokens (the smallest count that proves overflow), so a
# margin-step refit re-overflows every time: 8192 -> 400 "at least 57345"
# -> refit 7935 -> 400 "at least 57602" -> ... Each retry only shrinks
# max_tokens by margin+1. For that phrasing we additionally halve max_tokens
# geometrically and retry in a bounded loop (converges in <= log2 steps).
# The old "(N in the messages)" phrasing reports the true count and keeps the
# original one-shot margin-step behaviour.
_PROMPT_TOK_RE = re.compile(
    r"(?:(\d+)\s+in the messages"
    r"|prompt contains at least\s+(\d+)\s+input tokens"
    r"|parameter=input_tokens,\s*value=(\d+))",
    re.IGNORECASE,
)

# Bounded refit loop: enough for 8192 -> 8 by halving, with slack.
_REFIT_MAX_RETRIES = 6
_MAXLEN_RE = re.compile(
    r"(?:maximum context length is|max_model_len[\"']?\s*[:=]?\s*)\s*(\d+)",
    re.IGNORECASE,
)


def _is_ctx_overflow(content: bytes | None) -> bool:
    if not content:
        return False
    try:
        text = content.decode("utf-8", "replace")
    except Exception:
        return False
    return bool(_CTX_HINT_RE.search(text))


def _refit_from_error(
    entry: dict[str, Any], content: bytes | None, cur_max: int | None = None
) -> int | None:
    """Recompute a safe max_tokens from an upstream context-overflow 400.

    Uses the prompt-token count the upstream actually reported and the window
    (reported, else registry). When the count comes from vLLM 0.23's
    "at least N input tokens" phrasing it is only a lower bound (see comment
    above _PROMPT_TOK_RE), so we also cap the refit at half the max_tokens
    that just overflowed; the caller's bounded retry loop then converges
    geometrically instead of creeping down margin+1 per attempt."""
    if not content:
        return None
    text = content.decode("utf-8", "replace")
    m = _PROMPT_TOK_RE.search(text)
    if not m:
        return None
    groups = m.groups()
    reported_prompt = int(next(g for g in groups if g))
    # groups[0] is the old exact "(N in the messages)" phrasing; groups[1]/[2]
    # are the 0.23 lower-bound phrasings.
    reported_is_lower_bound = groups[0] is None
    win_m = _MAXLEN_RE.search(text)
    window = int(win_m.group(1)) if win_m else int(entry.get("context_window") or 0)
    if window <= 0:
        return None
    # Smoke 2026-07-07: clamping UP to _FIT_MARGIN_MIN re-overflowed when the
    # prompt (65281) left fewer than 256 tokens of window. Take whatever room
    # actually remains (minus 1 for the upstream's off-by-one counting); only
    # give up when nothing usable is left.
    avail = window - reported_prompt - 1
    if avail < 8:
        return None
    margin = int(entry.get("fit_margin") or _FIT_MARGIN_MIN)
    fitted = window - reported_prompt - margin
    if fitted < 1:
        fitted = avail
    fitted = min(fitted, avail)
    if reported_is_lower_bound and cur_max is not None and int(cur_max) > 0:
        half = int(cur_max) // 2
        if half < 8:
            return None  # shrunk to nothing: prompt fills the window
        fitted = min(fitted, half)
    return fitted


# ---------------------------------------------------------------------------
# Streaming usage scan (mirror ds_proxy)
# ---------------------------------------------------------------------------
_SSE_DATA_RE = re.compile(rb"^data:\s*(\{.*\})\s*$")


def _scan_sse_usage(lines: list[bytes]) -> dict | None:
    usage = None
    for ln in lines:
        if b'"usage"' not in ln:
            continue
        m = _SSE_DATA_RE.match(ln.strip())
        if not m:
            continue
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
    return usage


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="deep-research-arena unified LLM gateway")

_TIMEOUT = httpx.Timeout(
    connect=float(os.environ.get("LLMGW_CONNECT_TIMEOUT_S", "15") or "15"),
    read=float(os.environ.get("LLMGW_READ_TIMEOUT_S", "120") or "120"),
    write=30.0,
    pool=10.0,
)

# Some hosts (WSL boxes with blackholed IPv6 routes) resolve upstreams to IPv6
# addresses that never connect; getaddrinfo prefers them and each attempt eats
# the whole connect timeout. LLMGW_FORCE_IPV4=1 binds the local side to an
# IPv4 address, which pins the socket family to AF_INET, and adds connect-level
# retries for jittery links.
_FORCE_IPV4 = os.environ.get("LLMGW_FORCE_IPV4", "") == "1"


def _make_async_client() -> httpx.AsyncClient:
    if _FORCE_IPV4:
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
        return httpx.AsyncClient(timeout=_TIMEOUT, transport=transport)
    return httpx.AsyncClient(timeout=_TIMEOUT)


def _auth_headers(entry: dict[str, Any], request: Request) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key_env = entry.get("api_key_env") or ""
    key = os.environ.get(key_env, "") if key_env else ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    else:
        incoming = request.headers.get("authorization")
        if incoming:
            headers["Authorization"] = incoming
    return headers


@app.post("/_mark")
async def usage_mark(request: Request):
    """Append a run-boundary marker to the usage log and open/close the current
    run bracket. Same contract as ds_proxy: free-form JSON, conventional fields
    run_id, phase ('start'|'end'), agent, task_id, backbone."""
    try:
        body = json.loads(await request.body() or b"{}")
    except Exception:
        body = {}
    if isinstance(body, dict):
        phase = str(body.get("phase", "")).lower()
        if phase == "start" and body.get("run_id"):
            _CURRENT_RUN.clear()
            _CURRENT_RUN["run_id"] = body["run_id"]
        elif phase == "end":
            _CURRENT_RUN.clear()
        _usage_write({"mark": True, **body})
    else:
        _usage_write({"mark": True})
    return {"ok": True, "logging": bool(USAGE_LOG), "run_id": _CURRENT_RUN.get("run_id")}


async def _forward(path: str, request: Request) -> Any:
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        body = {}

    model = str(body.get("model", ""))
    entry = _match_entry(model)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "message": f"no registered backbone for model {model!r}",
                    "type": "model_not_found",
                    "known_prefixes": [e["prefix"] for e in REGISTRY],
                }
            },
        )

    adjustments = _apply_policy(entry, body)
    headers = _auth_headers(entry, request)
    url = f"{entry['upstream'].rstrip('/')}{path}"
    stream = bool(body.get("stream"))

    if stream:
        return await _forward_stream(entry, url, headers, body, adjustments)
    return await _forward_unary(entry, url, headers, body, adjustments)


async def _forward_unary(entry, url, headers, body, adjustments) -> Any:
    t0 = time.time()
    async with _make_async_client() as client:
        r = await client.post(url, json=body, headers=headers)

        # Resilience: bounded refit-and-retry loop on context-overflow 400s.
        # This is what kills the claude-code window+1 class for good. A loop
        # (not retry-once) because vLLM 0.23 reports input_tokens as a lower
        # bound, so one refit can legitimately re-overflow (see
        # _refit_from_error); the exact-count phrasing still converges in one
        # step because the recomputed fit is then a fixed point.
        for _ in range(_REFIT_MAX_RETRIES):
            if not (r.status_code == 400 and _is_ctx_overflow(r.content)):
                break
            fitted = _refit_from_error(entry, r.content, body.get("max_tokens"))
            if fitted is None or fitted == body.get("max_tokens"):
                break
            body["max_tokens"] = fitted
            adjustments = list(adjustments) + ["refit_retry"]
            r = await client.post(url, json=body, headers=headers)

        latency_ms = round((time.time() - t0) * 1000, 1)
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
            _u = data.get("usage") if isinstance(data, dict) else None
            _usage_write({
                "model": body.get("model"),
                "stream": False,
                "prompt_tokens": (_u or {}).get("prompt_tokens"),
                "completion_tokens": (_u or {}).get("completion_tokens"),
                "total_tokens": (_u or {}).get("total_tokens"),
                "latency_ms": latency_ms,
                "fit_adjustments": adjustments,
            })
            return JSONResponse(status_code=r.status_code, content=data)
        _usage_write({
            "model": body.get("model"), "stream": False,
            "latency_ms": latency_ms, "fit_adjustments": adjustments,
            "non_json": True,
        })
        return JSONResponse(status_code=r.status_code, content={"raw": r.text})


async def _forward_stream(entry, url, headers, body, adjustments) -> Any:
    # Ask upstream to append the usage chunk so streaming lanes are accounted.
    if USAGE_LOG and STREAM_USAGE and "stream_options" not in body:
        body["stream_options"] = {"include_usage": True}

    t0 = time.time()
    client = _make_async_client()
    req = client.build_request("POST", url, json=body, headers=headers)
    upstream = await client.send(req, stream=True)

    ctype = upstream.headers.get("content-type", "")
    # Error / non-SSE response: buffer it, run the bounded refit-retry loop on
    # ctx overflow (mirrors _forward_unary; see _refit_from_error for why a
    # single retry is not enough under vLLM 0.23's lower-bound phrasing).
    if upstream.status_code != 200 or ctype.startswith("application/json"):
        content = await upstream.aread()
        await upstream.aclose()
        for _ in range(_REFIT_MAX_RETRIES):
            if not (upstream.status_code == 400 and _is_ctx_overflow(content)):
                break
            fitted = _refit_from_error(entry, content, body.get("max_tokens"))
            if fitted is None or fitted == body.get("max_tokens"):
                break
            body["max_tokens"] = fitted
            adjustments = list(adjustments) + ["refit_retry"]
            req = client.build_request("POST", url, json=body, headers=headers)
            upstream = await client.send(req, stream=True)
            ctype = upstream.headers.get("content-type", "")
            if upstream.status_code == 200 and not ctype.startswith("application/json"):
                return _sse_response(entry, client, upstream, body, adjustments, t0)
            content = await upstream.aread()
            await upstream.aclose()
        await client.aclose()
        try:
            payload = json.loads(content)
        except Exception:
            payload = {"raw": content.decode("utf-8", "replace")}
        return JSONResponse(status_code=upstream.status_code, content=payload)

    return _sse_response(entry, client, upstream, body, adjustments, t0)


def _sse_response(entry, client, upstream, body, adjustments, t0) -> StreamingResponse:
    async def _stream():
        tail = b""
        sse_lines: list[bytes] = []
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
                if USAGE_LOG:
                    tail += chunk
                    *done, tail = tail.split(b"\n")
                    sse_lines.extend(ln for ln in done if b'"usage"' in ln)
                    if len(tail) > 262144:
                        tail = tail[-262144:]
        finally:
            await upstream.aclose()
            await client.aclose()
            if USAGE_LOG:
                if tail.strip():
                    sse_lines.append(tail)
                usage = _scan_sse_usage(sse_lines) or {}
                _usage_write({
                    "model": body.get("model"),
                    "stream": True,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                    "fit_adjustments": adjustments,
                    "usage_missing": not bool(usage),
                })

    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await _forward("/chat/completions", request)


@app.post("/v1/completions")
async def completions(request: Request):
    return await _forward("/completions", request)


@app.get("/v1/models")
async def models():
    """Aggregate the registry as an OpenAI /v1/models listing. Never leaks
    keys; each backbone is one entry keyed by its prefix."""
    return {
        "object": "list",
        "data": [
            {
                "id": e["prefix"],
                "object": "model",
                "owned_by": "deep-research-arena-gateway",
                "context_window": e.get("context_window"),
            }
            for e in REGISTRY
        ],
    }


@app.get("/healthz")
async def healthz():
    """Registry summary: prefixes + policy flags. Deliberately omits keys and
    even the api_key_env value's contents; only the env-var NAME is shown."""
    return {
        "ok": True,
        "usage_log": bool(USAGE_LOG),
        "open_run": _CURRENT_RUN.get("run_id"),
        "models": [
            {
                "prefix": e["prefix"],
                "upstream": e["upstream"],
                "api_key_env": e.get("api_key_env") or None,
                "context_window": e.get("context_window"),
                "fit_to_window": bool(e.get("fit_to_window")),
                "fit_margin": e.get("fit_margin"),
                "max_tokens_cap": e.get("max_tokens_cap") or None,
                "max_tokens_floor": e.get("max_tokens_floor") or None,
                "thinking_off": bool(e.get("thinking_off")),
            }
            for e in REGISTRY
        ],
    }
