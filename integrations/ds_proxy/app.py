"""Tiny OpenAI-compat proxy that forwards to DeepSeek, injecting
`thinking: {"type": "disabled"}` for any `deepseek-v4-*` model so framework
clients that don't expose `extra_body` still get non-reasoning responses.

Run on westd:
    OPENAI_PROXY_UPSTREAM=https://api.deepseek.com \
    OPENAI_PROXY_KEY=sk-... \
    uvicorn integrations.ds_proxy.app:app --host 0.0.0.0 --port 8088

Client side:
    OPENAI_BASE_URL=http://localhost:8088/v1
    OPENAI_API_KEY=whatever   # proxy uses server-side key, ignores client key
"""

from __future__ import annotations

import json
import os
import re
import asyncio
import fcntl
import ipaddress
import threading
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from integrations import sampling_policy as _sampling

UPSTREAM = os.environ.get("OPENAI_PROXY_UPSTREAM", "https://api.deepseek.com").rstrip("/")
UPSTREAM_KEY = os.environ.get("OPENAI_PROXY_KEY", "")
INJECT_THINKING_DISABLED = os.environ.get("OPENAI_PROXY_THINKING_DISABLED", "1") != "0"

# Optional model-name rewrite. Useful when point UPSTREAM at an LM Studio
# server whose loaded model is `qwen3.5-35b-a3b` but agents hardcode
# `deepseek-v4-flash`. Set OPENAI_PROXY_REWRITE_MODEL=qwen3.5-35b-a3b.
REWRITE_MODEL = os.environ.get("OPENAI_PROXY_REWRITE_MODEL", "").strip() or None

# Optional minimum max_tokens floor. Reasoning models (Qwen3, DeepSeek-R1)
# burn 200-800 tokens on chain-of-thought *before* the actual answer; if the
# caller passed max_tokens=256 and the CoT alone needs 400, the answer never
# appears, the closing </think> tag never lands, and the strip regex can't
# salvage anything. Bumping every incoming request to at least N tokens lets
# the model finish thinking AND produce the answer. 2048 is the empirical
# sweet spot for Qwen3-27b on JSON-mode judges.
MIN_MAX_TOKENS = int(os.environ.get("OPENAI_PROXY_MIN_MAX_TOKENS", "0") or "0")
RETRY_INITIAL_S = float(os.environ.get("OPENAI_PROXY_RETRY_INITIAL_S", "2") or "2")
RETRY_MAX_S = float(os.environ.get("OPENAI_PROXY_RETRY_MAX_S", "60") or "60")
# Hard cap on retry attempts. The retry loops below used to be unbounded
# `while True`: a persistent upstream 429/5xx (or a wedged endpoint) would spin
# forever, hanging a whole #39 run instead of failing the one request. Bound it
# so the proxy gives up after N tries and returns an explicit error the caller
# can log and skip. Backoff itself is already capped at RETRY_MAX_S per pause.
RETRY_MAX_ATTEMPTS = int(os.environ.get("OPENAI_PROXY_RETRY_MAX_ATTEMPTS", "8") or "8")
CHAT_READ_TIMEOUT_S = float(os.environ.get("OPENAI_PROXY_CHAT_READ_TIMEOUT_S", "120") or "120")

# Strip `<think>...</think>` blocks from response content for reasoning models
# (Qwen3, DeepSeek-R1) when their tags leak into chat output.
#
# Two real failure modes we have to handle:
#
# 1. The well-formed case: full ``<think>...</think>\n\n<answer>``. The regex
#    below catches this. Trivial.
#
# 2. The truncated case: response started ``<think>Thinking Process: ...``
#    but the closing tag never appeared because max_tokens ran out. The
#    answer is missing entirely, so the safest thing is to return ``""``
#    rather than leak the chain-of-thought as the "answer". JSON-mode judges
#    that get a CoT preamble will fail their `json.loads` and the run lands
#    in degenerate-filter territory, polluting Elo with phantom failures.
#
# 3. The "no opening tag" case: some Qwen variants emit ``Thinking Process:``
#    prose without wrapping it in tags. Same treatment — strip the prose
#    block before returning, falling back to empty if there's no clear
#    "answer" segment after the thinking.
STRIP_THINKING = os.environ.get("OPENAI_PROXY_STRIP_THINKING", "1") != "0"
_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL | re.IGNORECASE)
# Matches an unclosed ``<think>`` block at the start (truncated response).
_THINK_OPEN_NO_CLOSE_RE = re.compile(r"^\s*<think>(?!.*</think>)", flags=re.DOTALL | re.IGNORECASE)
# Matches the bare ``Thinking Process:`` prose preamble Qwen3 sometimes emits
# WITHOUT wrapping in tags. We treat the entire numbered/bulleted analysis
# block as preamble and look for the first non-list paragraph after it.
_QWEN_PROSE_THINK_RE = re.compile(
    r"^\s*Thinking Process:.*?(?=\n\n(?:[A-Za-z\{\[\"]|Final Answer|Output|Answer))",
    flags=re.DOTALL | re.IGNORECASE,
)
_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", flags=re.DOTALL | re.IGNORECASE)


def _strip_think(content: Any) -> Any:
    if not STRIP_THINKING or not isinstance(content, str) or not content:
        return content
    # Case 1: well-formed <think>...</think>
    out = _THINK_TAG_RE.sub("", content)
    if out != content:
        return out.lstrip("\n")
    # Case 2: <think> opened but never closed -> the answer never landed.
    # Returning the raw CoT would poison JSON-mode judges, so emit empty
    # string and let the caller's degenerate filter handle it.
    if _THINK_OPEN_NO_CLOSE_RE.match(content):
        return ""
    # Case 3: no tags, but ``Thinking Process:`` preamble.
    if content.lstrip().startswith("Thinking Process:"):
        out = _QWEN_PROSE_THINK_RE.sub("", content, count=1).lstrip()
        if out and out != content:
            return out
        # No clear answer after the preamble -> CoT-only response, drop it.
        return ""
    return content


def _strip_json_fence(content: Any) -> Any:
    if not isinstance(content, str) or "```" not in content:
        return content
    m = _JSON_FENCE_RE.match(content)
    if not m:
        return content
    inner = m.group(1).strip()
    try:
        json.loads(inner)
    except Exception:
        return content
    return inner

EMB_UPSTREAM = os.environ.get(
    "OPENAI_PROXY_EMB_UPSTREAM",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
EMB_UPSTREAM_KEY = os.environ.get("OPENAI_PROXY_EMB_KEY", "")
EMB_FORCE_MODEL = os.environ.get("OPENAI_PROXY_EMB_MODEL", "text-embedding-v4")

# ---------------------------------------------------------------------------
# Whole-run token accounting (cost-per-score feature).
#
# Set DSPROXY_USAGE_LOG to a path and EVERY upstream call's usage is appended
# as one JSON line with a timestamp — including STREAMING calls: the proxy
# injects `stream_options: {"include_usage": true}` (opt out with
# DSPROXY_STREAM_USAGE=0) and scans the SSE tail for the usage chunk while
# piping it through untouched.
#
# Run attribution: agent frameworks cannot be asked to tag their requests, so
# the runner brackets each run with POST /_mark {"run_id": ..., "phase":
# "start"|"end", ...}; marks land in the same JSONL and the aggregator
# (scripts/aggregate_run_costs.py) slices the serial timeline into runs.
# ---------------------------------------------------------------------------
USAGE_LOG = os.environ.get("DSPROXY_USAGE_LOG", "")
STREAM_USAGE = os.environ.get("DSPROXY_STREAM_USAGE", "1") != "0"

# Several credential files may still share one upstream account and allowance.
# Keep every worker's own proxy/usage ledger while admitting only a declared
# number of cross-process requests into that shared account at once. Advisory
# flock locks are released automatically if a worker dies. This is opt-in, so
# existing deployments retain their current transport policy.
SHARED_SLOTS_DIR = os.environ.get("OPENAI_PROXY_SHARED_SLOTS_DIR", "").strip()
SHARED_SLOTS = int(os.environ.get("OPENAI_PROXY_SHARED_SLOTS", "0") or "0")
SHARED_SLOT_POLL_S = float(
    os.environ.get("OPENAI_PROXY_SHARED_SLOT_POLL_S", "0.1") or "0.1"
)
SHARED_SLOT_HEARTBEAT_S = float(
    os.environ.get("OPENAI_PROXY_SHARED_SLOT_HEARTBEAT_S", "30") or "30"
)
MAX_CALLS = int(os.environ.get("DSPROXY_MAX_CALLS", "0") or "0")
MAX_TOTAL_TOKENS = int(
    os.environ.get("DSPROXY_MAX_TOTAL_TOKENS", "0") or "0"
)
_ALLOWED_CLIENT_CIDRS_RAW = os.environ.get(
    "DSPROXY_ALLOWED_CLIENT_CIDRS", ""
).strip()
if SHARED_SLOTS < 0:
    raise ValueError("OPENAI_PROXY_SHARED_SLOTS must be non-negative")
if SHARED_SLOTS and not SHARED_SLOTS_DIR:
    raise ValueError(
        "OPENAI_PROXY_SHARED_SLOTS_DIR is required when shared slots are enabled"
    )
if SHARED_SLOT_POLL_S <= 0:
    raise ValueError("OPENAI_PROXY_SHARED_SLOT_POLL_S must be positive")
if SHARED_SLOT_HEARTBEAT_S <= 0:
    raise ValueError("OPENAI_PROXY_SHARED_SLOT_HEARTBEAT_S must be positive")
if MAX_CALLS < 0 or MAX_TOTAL_TOKENS < 0:
    raise ValueError("DSPROXY smoke budgets must be non-negative")

_BUDGET_LOCK = threading.Lock()
_ACCEPTED_CALLS = 0
_OBSERVED_TOTAL_TOKENS = 0

try:
    ALLOWED_CLIENT_NETWORKS = tuple(
        ipaddress.ip_network(item.strip(), strict=False)
        for item in _ALLOWED_CLIENT_CIDRS_RAW.split(",")
        if item.strip()
    )
except ValueError as exc:
    raise ValueError(f"invalid DSPROXY_ALLOWED_CLIENT_CIDRS: {exc}") from exc

# The comment above described slicing a SERIAL timeline into runs. The harness
# is not serial: measured over the 312-run 13-task subset, max concurrency is 2
# (always cross-backbone). Two concurrent workers interleave their marks in one
# log, so timeline slicing silently mis-attributes tokens. It happened to work
# only because the two workers used different `model` values; the #39 full run
# is single-backbone, where that accident disappears entirely.
#
# Fix: every usage record carries the open run's identity. Attribution no
# longer depends on which pair of marks a line happens to fall between. Each
# concurrent worker still needs its own proxy instance (own port, own
# DSPROXY_USAGE_LOG); `_run_ctx_set` refuses to interleave two open runs.
_RUN_CTX: dict[str, Any] = {}
_RUN_CTX_LOCK = threading.Lock()


class RunAlreadyActive(RuntimeError):
    """A second `/_mark start` arrived while another run was open."""


class RunOwnerMismatch(RuntimeError):
    """An `/_mark end` caller does not own the currently open run."""


class ClientDisconnectedBeforeAdmission(RuntimeError):
    """The caller went away while waiting for an upstream slot."""


def _run_ctx_set(body: dict) -> dict:
    run_id = str(body.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    fields = {
        "run_id": run_id,
        "lane": body.get("lane") or body.get("agent"),
        "task": body.get("task") or body.get("task_id"),
        "backbone": body.get("backbone"),
        "worker": body.get("worker") or os.environ.get("DRA_WORKER_ID") or None,
    }
    with _RUN_CTX_LOCK:
        open_id = _RUN_CTX.get("run_id")
        if open_id and open_id != run_id:
            raise RunAlreadyActive(
                f"run {open_id!r} is still open; refusing to interleave {run_id!r}. "
                "Give each concurrent worker its own ds_proxy instance."
            )
        _RUN_CTX.clear()
        _RUN_CTX.update({k: v for k, v in fields.items() if v is not None})
        return dict(_RUN_CTX)


def _run_ctx_clear(expected_run_id: str | None = None, *, require_owner: bool = False) -> dict:
    """Clear the run context, optionally proving ownership first.

    Internal test/reset callers may clear unconditionally.  The HTTP ``end``
    path always sets ``require_owner=True``: an empty or stale end marker must
    never clear a sibling worker's token-attribution bracket.
    """
    with _RUN_CTX_LOCK:
        if require_owner:
            expected_run_id = str(expected_run_id or "").strip()
            if not expected_run_id:
                raise ValueError("run_id is required for phase=end")
            open_id = str(_RUN_CTX.get("run_id") or "").strip()
            if not open_id:
                raise RunOwnerMismatch(
                    f"cannot close {expected_run_id!r}: no run is currently open"
                )
            if open_id != expected_run_id:
                raise RunOwnerMismatch(
                    f"cannot close {expected_run_id!r}: run {open_id!r} owns the bracket"
                )
        prev = dict(_RUN_CTX)
        _RUN_CTX.clear()
        return prev


def _run_ctx() -> dict:
    with _RUN_CTX_LOCK:
        return dict(_RUN_CTX)


def _upstream_headers(request: Request) -> dict[str, str]:
    """Build chat/completions headers, including the active run identity.

    CLIProxyAPI uses ``X-Session-ID`` for session affinity. The harness already
    owns the exact run identity through the per-worker ``/_mark`` bracket, so
    this proxy is the one transport-independent place to attach it for every
    framework. Identity probes occur outside the bracket and therefore make no
    run-affinity claim.
    """
    headers = {"Content-Type": "application/json"}
    if UPSTREAM_KEY:
        headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"
    else:
        incoming = request.headers.get("authorization")
        if incoming:
            headers["Authorization"] = incoming
    run_id = str(_run_ctx().get("run_id") or "").strip()
    if run_id:
        headers["X-Session-ID"] = run_id
    return headers


def _usage_write(record: dict, *, run_ctx: dict[str, Any] | None = None) -> None:
    if not USAGE_LOG:
        return
    try:
        record.setdefault("ts", round(time.time(), 3))
        # Attribute a request using the bracket that was open when it was
        # admitted. A watchdog/operator can close the live bracket while an
        # already-admitted upstream request is still completing; consulting
        # only the live context here would turn that billable completion into
        # an `_untagged` call.
        context = _run_ctx() if run_ctx is None else run_ctx
        for k, v in context.items():
            record.setdefault(k, v)
        with open(USAGE_LOG, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _usage_record(model: Any, stream: bool, usage: dict[str, Any]) -> dict[str, Any]:
    """Normalize billable usage without discarding provider cache counters.

    DeepSeek prices cache-hit and cache-miss prompt tokens differently.  The
    old ledger retained only aggregate prompt tokens, which made exact money
    accounting impossible even though the upstream response supplied the
    split.  Keep both the DeepSeek top-level fields and the OpenAI-compatible
    ``prompt_tokens_details.cached_tokens`` fallback.
    """
    prompt_tokens = usage.get("prompt_tokens")
    cache_hit = usage.get("prompt_cache_hit_tokens")
    cache_miss = usage.get("prompt_cache_miss_tokens")
    details = usage.get("prompt_tokens_details")
    if cache_hit is None and isinstance(details, dict):
        cache_hit = details.get("cached_tokens")
    if cache_miss is None and cache_hit is not None and prompt_tokens is not None:
        cache_miss = max(int(prompt_tokens) - int(cache_hit), 0)

    record: dict[str, Any] = {
        "model": model,
        "stream": stream,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    if cache_hit is not None:
        record["prompt_cache_hit_tokens"] = int(cache_hit)
    if cache_miss is not None:
        record["prompt_cache_miss_tokens"] = int(cache_miss)
    return record


async def _shared_slot_acquire(
    *,
    run_ctx: dict[str, Any] | None = None,
    request: Request | None = None,
) -> int | None:
    """Acquire one process-shared upstream slot without blocking asyncio."""
    if not SHARED_SLOTS:
        return None
    os.makedirs(SHARED_SLOTS_DIR, mode=0o755, exist_ok=True)
    started = time.monotonic()
    last_heartbeat = started
    while True:
        if request is not None and await request.is_disconnected():
            waited = time.monotonic() - started
            _usage_write({
                "non_call_event": True,
                "client_disconnected_before_admission": True,
                "wait_s": round(waited, 3),
            }, run_ctx=run_ctx)
            raise ClientDisconnectedBeforeAdmission(
                "client disconnected before an upstream slot became available"
            )
        for index in range(SHARED_SLOTS):
            path = os.path.join(SHARED_SLOTS_DIR, f"slot-{index}.lock")
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            waited = time.monotonic() - started
            if waited >= SHARED_SLOT_POLL_S:
                _usage_write({
                    "non_call_event": True,
                    "admission_wait": True,
                    "slot": index,
                    "wait_s": round(waited, 3),
                }, run_ctx=run_ctx)
            return fd
        now = time.monotonic()
        if now - last_heartbeat >= SHARED_SLOT_HEARTBEAT_S:
            _usage_write({
                "non_call_event": True,
                "admission_waiting": True,
                "wait_s": round(now - started, 3),
            }, run_ctx=run_ctx)
            last_heartbeat = now
        await asyncio.sleep(SHARED_SLOT_POLL_S)


def _shared_slot_release(fd: int | None) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _budget_admit() -> str | None:
    """Admit one logical proxy request or return a stable exhaustion reason."""
    global _ACCEPTED_CALLS
    with _BUDGET_LOCK:
        if MAX_CALLS and _ACCEPTED_CALLS >= MAX_CALLS:
            return f"call limit reached ({_ACCEPTED_CALLS}/{MAX_CALLS})"
        if MAX_TOTAL_TOKENS and _OBSERVED_TOTAL_TOKENS >= MAX_TOTAL_TOKENS:
            return (
                "token limit reached "
                f"({_OBSERVED_TOTAL_TOKENS}/{MAX_TOTAL_TOKENS})"
            )
        _ACCEPTED_CALLS += 1
    return None


def _budget_exhausted_response(
    reason: str,
    *,
    run_ctx: dict[str, Any],
) -> JSONResponse:
    _usage_write({
        "non_call_event": True,
        "budget_exhausted": True,
        "reason": reason,
    }, run_ctx=run_ctx)
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": f"ds_proxy smoke budget exhausted: {reason}",
                "type": "smoke_budget_exhausted",
            }
        },
    )


def _client_disconnected_response() -> JSONResponse:
    return JSONResponse(
        status_code=499,
        content={
            "error": {
                "message": "client disconnected before upstream admission",
                "type": "client_disconnected",
            }
        },
    )


def _budget_record_tokens(usage: dict | None) -> None:
    global _OBSERVED_TOTAL_TOKENS
    if not isinstance(usage, dict):
        return
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    with _BUDGET_LOCK:
        _OBSERVED_TOTAL_TOKENS += max(0, total)


def _client_ip_allowed(raw: str | None) -> bool:
    """Restrict a non-loopback listener to host and attested worker veths."""
    if not ALLOWED_CLIENT_NETWORKS:
        return True
    try:
        address = ipaddress.ip_address(str(raw or ""))
    except ValueError:
        return False
    return any(address in network for network in ALLOWED_CLIENT_NETWORKS)


def _client_denied(request: Request) -> JSONResponse | None:
    peer = request.client.host if request.client else None
    if _client_ip_allowed(peer):
        return None
    return JSONResponse(
        status_code=403,
        content={"error": {
            "message": "ds_proxy client network is not allowed",
            "type": "client_network_denied",
        }},
    )


def _contains_code(obj: Any, code: str) -> bool:
    if isinstance(obj, dict):
        for k in ("code", "error_code", "status_code"):
            if str(obj.get(k, "")).strip() == code:
                return True
        return any(_contains_code(v, code) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_code(v, code) for v in obj)
    return False


def _retryable_payload(status_code: int, content: bytes | None) -> tuple[bool, str]:
    if status_code == 429:
        return True, "http_429"
    if status_code in (502, 503, 504):
        return True, f"http_{status_code}"
    data = None
    if content:
        try:
            data = json.loads(content)
        except Exception:
            pass
        # CLIProxyAPI/OpenAI can return ``deactivated_workspace`` for one
        # routed attempt and then serve the same credential/session normally
        # on the next attempt.  We observed both outcomes seconds apart on the
        # formal GPT-5.6 Luna path, so treating this exact payload as a terminal
        # payment/account error aborts an otherwise healthy harness run.  Retry
        # only this machine-readable code; unrelated HTTP 402 responses still
        # pass through immediately.
        if status_code == 402 and _contains_code(data, "deactivated_workspace"):
            return True, "deactivated_workspace"
        if _contains_code(data, "1305"):
            return True, "code_1305"
        if _contains_code(data, "1234"):
            return True, "code_1234"
    return False, ""


async def _retry_pause(
    reason: str,
    attempt: int,
    delay: float,
    model: str | None,
    *,
    run_ctx: dict[str, Any] | None = None,
) -> float:
    _usage_write({
        "retry": True,
        "reason": reason,
        "attempt": attempt,
        "sleep_s": delay,
        "model": model,
    }, run_ctx=run_ctx)
    await asyncio.sleep(delay)
    return min(RETRY_MAX_S, max(delay * 2, RETRY_INITIAL_S))


def _retry_exhausted(reason: str, attempt: int, model: str | None,
                     upstream_status: int | None = None,
                     upstream_body: bytes | None = None, *,
                     run_ctx: dict[str, Any] | None = None) -> JSONResponse:
    """Give up after RETRY_MAX_ATTEMPTS and return an explicit gateway error
    instead of looping forever. Logged to the usage stream so the run
    aggregator can see which requests were dropped."""
    _usage_write({
        "retry_exhausted": True,
        "reason": reason,
        "attempts": attempt,
        "model": model,
    }, run_ctx=run_ctx)
    err: dict[str, Any] = {
        "message": (f"ds_proxy: upstream retry limit reached after {attempt} "
                    f"attempt(s) (last reason: {reason})"),
        "type": "upstream_retry_exhausted",
        "reason": reason,
        "attempts": attempt,
    }
    if upstream_status is not None:
        err["upstream_status"] = upstream_status
    if upstream_body:
        err["upstream_body"] = upstream_body.decode("utf-8", "replace")[:500]
    return JSONResponse(status_code=502, content={"error": err})


_SSE_DATA_RE = re.compile(rb"^data:\s*(\{.*\})\s*$")


def _scan_sse_usage(lines: list[bytes]) -> dict | None:
    """Find the final usage object in SSE data lines (vLLM/OpenAI emit it in
    the last chunk when stream_options.include_usage is set)."""
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


app = FastAPI(title="deepseek-v4 thinking-inject proxy")


@app.post("/_mark")
async def usage_mark(request: Request):
    """Open or close a run bracket: {run_id, phase: 'start'|'end', lane, task,
    backbone, worker}.

    While a bracket is open every usage record is stamped with its identity, so
    token attribution no longer depends on log-line ordering. A reentrant
    `start` returns HTTP 409 rather than mixing two runs' tokens.
    No-op (but still 200) when DSPROXY_USAGE_LOG is unset.
    """
    try:
        body = json.loads(await request.body() or b"{}")
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    phase = str(body.get("phase") or "start").lower()
    if phase == "end":
        try:
            prev = _run_ctx_clear(body.get("run_id"), require_owner=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RunOwnerMismatch as e:
            raise HTTPException(
                status_code=409,
                detail={"error": "run_owner_mismatch", "message": str(e)},
            )
        _usage_write({"mark": True, "phase": "end", **prev})
        return {"ok": True, "closed": prev.get("run_id"), "logging": bool(USAGE_LOG)}
    try:
        ctx = _run_ctx_set(body)
    except RunAlreadyActive as e:
        raise HTTPException(status_code=409, detail={"error": "run_already_active", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _usage_write({"mark": True, "phase": "start", **ctx})
    return {"ok": True, "run_id": ctx["run_id"], "logging": bool(USAGE_LOG)}


# model prefixes that accept the `thinking: {"type": "disabled"}` body knob
# (DeepSeek v4 and Zhipu GLM share the format); extend via env, comma-sep.
# (GLM full run 2026-07-06: thinking stays ON per user decision, so glm- is
# NOT in the default; pair it with OPENAI_PROXY_MIN_MAX_TOKENS so framework
# max_tokens budgets don't get eaten by the CoT before the answer lands.)
THINKING_OFF_PREFIXES = tuple(
    p.strip() for p in os.environ.get(
        "OPENAI_PROXY_THINKING_OFF_PREFIXES", "deepseek-v4").split(",")
    if p.strip())


def _needs_thinking_off(model: str) -> bool:
    if not INJECT_THINKING_DISABLED:
        return False
    return model.startswith(THINKING_OFF_PREFIXES)


def _apply_min_max_tokens(body: dict) -> None:
    """Raise a too-small max_tokens to the OPS floor, NEVER above the declared
    ceiling.

    The former code ran this floor AFTER _sampling.apply_max_tokens with no
    bound, so an operator env (OPENAI_PROXY_MIN_MAX_TOKENS) could push every
    request past the ceiling lane_protocol.yaml declares ("clamp, never raise")
    -- the declared budget stopped being the last word on this door while the
    gateway door still enforced it (SPEC_ISSUES §2, floor/ceiling entry). The
    floor is now bounded by the declared per-model ceiling: it can rescue a
    reasoning model from a starved CoT budget but can never grant more than the
    protocol allows, and both proxy doors agree the declaration wins.
    """
    if MIN_MAX_TOKENS <= 0:
        return
    floor = MIN_MAX_TOKENS
    ceiling = _sampling.max_output_tokens_for(str(body.get("model", "")))
    if ceiling is not None:
        floor = min(floor, ceiling)
    cur = body.get("max_tokens")
    if cur is None or int(cur) < floor:
        body["max_tokens"] = floor


async def _forward(path: str, request: Request) -> Any:
    denied = _client_denied(request)
    if denied is not None:
        return denied
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        body = {}

    # This immutable snapshot follows the request through queueing, retries and
    # streaming finalizers even if /_mark end clears the worker's live bracket
    # before the upstream response arrives.
    request_run_ctx = _run_ctx()

    model = body.get("model", "")
    # The declared sampler, stamped where every lane's request must pass.
    # `run_deep_task._setup_ds_backbone` points ELEVEN lanes here; only
    # claude-code goes through llm_gateway. Equalising temperature in the
    # gateway alone equalised exactly one lane.
    _sampling.apply_sampling(body)
    _sampling.apply_max_tokens(body)
    if _needs_thinking_off(model) and "thinking" not in body:
        body["thinking"] = {"type": "disabled"}
    # Optional model rewrite — set when UPSTREAM is LM Studio with a fixed
    # loaded model that doesn't match the slug agents send.
    if REWRITE_MODEL:
        body["model"] = REWRITE_MODEL
        # If we rewrote to a non-deepseek model, drop the deepseek-only
        # `thinking` extra-body field (Qwen / others reject it).
        if not REWRITE_MODEL.lower().startswith("deepseek-v4"):
            body.pop("thinking", None)

    # Ensure reasoning models have room for both CoT and answer -- bounded by
    # the declared ceiling (see _apply_min_max_tokens).
    _apply_min_max_tokens(body)

    # DeepSeek v4 only supports `{"type":"json_object"}` for structured output.
    # Downgrade `json_schema` (LangChain's `with_structured_output(method="json_schema")`)
    # to `json_object` and inject the schema as a system-prompt nudge so the
    # model still emits valid JSON of the right shape.
    if model.startswith(("deepseek-v4", "glm-")):
        rf = body.get("response_format")
        if isinstance(rf, dict) and rf.get("type") == "json_schema":
            schema_obj = rf.get("json_schema") or {}
            schema_doc = json.dumps(schema_obj.get("schema") or schema_obj, ensure_ascii=False)
            body["response_format"] = {"type": "json_object"}
            messages = body.setdefault("messages", [])
            nudge = (
                "Return ONLY a single valid JSON object that conforms to this JSON "
                f"Schema (no prose, no code fences):\n{schema_doc[:4000]}"
            )
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = (messages[0].get("content") or "") + "\n\n" + nudge
            else:
                messages.insert(0, {"role": "system", "content": nudge})

    headers = _upstream_headers(request)

    url = f"{UPSTREAM}{path}"
    stream = bool(body.get("stream"))
    wants_json = isinstance(body.get("response_format"), dict)

    timeout = httpx.Timeout(connect=15.0, read=CHAT_READ_TIMEOUT_S, write=30.0, pool=10.0)
    req_model = body.get("model")

    if stream:
        # Ask the upstream to append the usage chunk to the stream so whole-run
        # token accounting also covers streaming frameworks. The extra final
        # chunk (empty choices + usage) is OpenAI-spec and piped through as-is.
        if USAGE_LOG and STREAM_USAGE and "stream_options" not in body:
            body["stream_options"] = {"include_usage": True}
        delay = RETRY_INITIAL_S
        attempt = 0
        budget_admitted = False
        while True:
            attempt += 1
            client = httpx.AsyncClient(timeout=timeout)
            try:
                slot_fd = await _shared_slot_acquire(
                    run_ctx=request_run_ctx,
                    request=request,
                )
            except ClientDisconnectedBeforeAdmission:
                await client.aclose()
                return _client_disconnected_response()
            if not budget_admitted:
                budget_error = _budget_admit()
                if budget_error:
                    _shared_slot_release(slot_fd)
                    await client.aclose()
                    return _budget_exhausted_response(
                        budget_error,
                        run_ctx=request_run_ctx,
                    )
                budget_admitted = True
            try:
                req = client.build_request("POST", url, json=body, headers=headers)
                upstream_resp = await client.send(req, stream=True)
            except httpx.TimeoutException:
                _shared_slot_release(slot_fd)
                await client.aclose()
                if attempt >= RETRY_MAX_ATTEMPTS:
                    return _retry_exhausted(
                        "timeout", attempt, req_model,
                        run_ctx=request_run_ctx,
                    )
                delay = await _retry_pause(
                    "timeout", attempt, delay, req_model,
                    run_ctx=request_run_ctx,
                )
                continue
            except BaseException:
                _shared_slot_release(slot_fd)
                await client.aclose()
                raise

            ctype = upstream_resp.headers.get("content-type", "")
            if upstream_resp.status_code != 200 or ctype.startswith("application/json"):
                content = await upstream_resp.aread()
                _shared_slot_release(slot_fd)
                retry, reason = _retryable_payload(upstream_resp.status_code, content)
                if retry:
                    await upstream_resp.aclose()
                    await client.aclose()
                    if attempt >= RETRY_MAX_ATTEMPTS:
                        return _retry_exhausted(
                            reason, attempt, req_model,
                            upstream_resp.status_code, content,
                            run_ctx=request_run_ctx,
                        )
                    delay = await _retry_pause(
                        reason, attempt, delay, req_model,
                        run_ctx=request_run_ctx,
                    )
                    continue
                await upstream_resp.aclose()
                await client.aclose()
                if ctype.startswith("application/json"):
                    try:
                        return JSONResponse(status_code=upstream_resp.status_code, content=json.loads(content))
                    except Exception:
                        pass
                return JSONResponse(status_code=upstream_resp.status_code, content={"raw": content.decode("utf-8", "replace")})
            break

        async def _stream():
            tail = b""
            sse_lines: list[bytes] = []
            try:
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
                    if USAGE_LOG:
                        tail += chunk
                        *done, tail = tail.split(b"\n")
                        sse_lines.extend(ln for ln in done if b'"usage"' in ln)
                        if len(tail) > 262144:  # never buffer unbounded
                            tail = tail[-262144:]
            finally:
                await upstream_resp.aclose()
                await client.aclose()
                _shared_slot_release(slot_fd)
                if USAGE_LOG:
                    if tail.strip():
                        sse_lines.append(tail)
                    usage = _scan_sse_usage(sse_lines)
                    if usage:
                        _budget_record_tokens(usage)
                        _usage_write(
                            _usage_record(req_model, True, usage),
                            run_ctx=request_run_ctx,
                        )
                    else:
                        _usage_write({"model": req_model, "stream": True,
                                      "usage_missing": True},
                                     run_ctx=request_run_ctx)

        return StreamingResponse(
            _stream(),
            status_code=upstream_resp.status_code,
            media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
        )

    delay = RETRY_INITIAL_S
    attempt = 0
    budget_admitted = False
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            attempt += 1
            try:
                slot_fd = await _shared_slot_acquire(
                    run_ctx=request_run_ctx,
                    request=request,
                )
            except ClientDisconnectedBeforeAdmission:
                return _client_disconnected_response()
            if not budget_admitted:
                budget_error = _budget_admit()
                if budget_error:
                    _shared_slot_release(slot_fd)
                    return _budget_exhausted_response(
                        budget_error,
                        run_ctx=request_run_ctx,
                    )
                budget_admitted = True
            try:
                r = await client.post(url, json=body, headers=headers)
            except httpx.TimeoutException:
                _shared_slot_release(slot_fd)
                if attempt >= RETRY_MAX_ATTEMPTS:
                    return _retry_exhausted(
                        "timeout", attempt, req_model,
                        run_ctx=request_run_ctx,
                    )
                delay = await _retry_pause(
                    "timeout", attempt, delay, req_model,
                    run_ctx=request_run_ctx,
                )
                continue
            except BaseException:
                _shared_slot_release(slot_fd)
                raise
            _shared_slot_release(slot_fd)
            retry, reason = _retryable_payload(r.status_code, r.content)
            if not retry:
                break
            if attempt >= RETRY_MAX_ATTEMPTS:
                return _retry_exhausted(
                    reason, attempt, req_model, r.status_code, r.content,
                    run_ctx=request_run_ctx,
                )
            delay = await _retry_pause(
                reason, attempt, delay, req_model,
                run_ctx=request_run_ctx,
            )
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
            # Whole-run token accounting (see header). No-op when unset.
            _u = data.get("usage") if isinstance(data, dict) else None
            if _u:
                _budget_record_tokens(_u)
                _usage_write(
                    _usage_record(body.get("model"), False, _u),
                    run_ctx=request_run_ctx,
                )
            # Strip <think>...</think> from reasoning-model output so client
            # frameworks see a clean answer. Preserve the original (with
            # thinking) in `reasoning_content` so judge_client._call_openai
            # can detect "answer truncated by max_tokens" and auto-retry with
            # 8192 tokens. Without this, a 1500-token max_tokens that gets
            # eaten entirely by Qwen's CoT preamble produces empty content
            # AND empty reasoning_content, so the retry never fires and the
            # judge silently records "21/21 unclear" for every checklist.
            for choice in (data.get("choices") if isinstance(data, dict) else None) or []:
                msg = choice.get("message") or {}
                if isinstance(msg.get("content"), str):
                    original = msg["content"]
                    stripped = _strip_think(original)
                    if wants_json:
                        stripped = _strip_json_fence(stripped)
                    msg["content"] = stripped
                    # Only set reasoning_content if we *changed* the content
                    # (i.e. there was thinking to strip). If the response
                    # already had clean output, leave reasoning_content alone.
                    if stripped != original and not msg.get("reasoning_content"):
                        msg["reasoning_content"] = original
            return JSONResponse(status_code=r.status_code, content=data)
        return JSONResponse(status_code=r.status_code, content={"raw": r.text})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await _forward("/chat/completions", request)


@app.post("/v1/completions")
async def completions(request: Request):
    return await _forward("/completions", request)


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    """Forward embedding requests to DashScope text-embedding-v4 (chat upstream
    doesn't have embeddings). Strip unsupported model name and force v4."""
    denied = _client_denied(request)
    if denied is not None:
        return denied
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        body = {}
    body["model"] = EMB_FORCE_MODEL
    if isinstance(body.get("input"), str):
        body["input"] = [body["input"]]

    headers = {"Content-Type": "application/json"}
    if EMB_UPSTREAM_KEY:
        headers["Authorization"] = f"Bearer {EMB_UPSTREAM_KEY}"
    else:
        incoming = request.headers.get("authorization")
        if incoming:
            headers["Authorization"] = incoming
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{EMB_UPSTREAM}/embeddings", json=body, headers=headers)
        return JSONResponse(
            status_code=r.status_code,
            content=r.json() if r.headers.get("content-type", "").startswith("application/json")
                   else {"raw": r.text},
        )


@app.get("/v1/models")
async def models(request: Request):
    denied = _client_denied(request)
    if denied is not None:
        return denied
    headers = {"Authorization": f"Bearer {UPSTREAM_KEY}"} if UPSTREAM_KEY else {
        "Authorization": request.headers.get("authorization", "")
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{UPSTREAM}/models", headers=headers)
        return JSONResponse(status_code=r.status_code, content=r.json())


@app.get("/healthz")
async def healthz():
    usage_log_bytes = 0
    if USAGE_LOG:
        try:
            usage_log_bytes = os.path.getsize(USAGE_LOG)
        except OSError:
            pass
    return {
        "ok": True,
        "upstream": UPSTREAM,
        "inject_thinking_off": INJECT_THINKING_DISABLED,
        "shared_upstream_slots": SHARED_SLOTS or None,
        "shared_slots_enabled": bool(SHARED_SLOTS),
        "client_network_gate": bool(ALLOWED_CLIENT_NETWORKS),
        # The worker chroot cannot stat the host-side ledger directly. Expose
        # only its byte count so the uniform watchdog can observe admission
        # heartbeat/retry/completion progress without exposing ledger content.
        "usage_log_bytes": usage_log_bytes,
        "smoke_budget": {
            "max_calls": MAX_CALLS or None,
            "accepted_calls": _ACCEPTED_CALLS,
            "max_total_tokens": MAX_TOTAL_TOKENS or None,
            "observed_total_tokens": _OBSERVED_TOTAL_TOKENS,
        },
    }
