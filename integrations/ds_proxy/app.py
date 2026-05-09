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
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAM = os.environ.get("OPENAI_PROXY_UPSTREAM", "https://api.deepseek.com").rstrip("/")
UPSTREAM_KEY = os.environ.get("OPENAI_PROXY_KEY", "")
INJECT_THINKING_DISABLED = os.environ.get("OPENAI_PROXY_THINKING_DISABLED", "1") != "0"

# Optional model-name rewrite. Useful when point UPSTREAM at an LM Studio
# server whose loaded model is `qwen3.5-35b-a3b` but agents hardcode
# `deepseek-v4-flash`. Set OPENAI_PROXY_REWRITE_MODEL=qwen3.5-35b-a3b.
REWRITE_MODEL = os.environ.get("OPENAI_PROXY_REWRITE_MODEL", "").strip() or None

# Strip `<think>...</think>` blocks from response content for reasoning models
# (Qwen3, DeepSeek-R1) when their tags leak into chat output.
STRIP_THINKING = os.environ.get("OPENAI_PROXY_STRIP_THINKING", "1") != "0"
_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL | re.IGNORECASE)


def _strip_think(content: Any) -> Any:
    if not STRIP_THINKING or not isinstance(content, str) or not content:
        return content
    return _THINK_TAG_RE.sub("", content).lstrip("\n")

EMB_UPSTREAM = os.environ.get(
    "OPENAI_PROXY_EMB_UPSTREAM",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
EMB_UPSTREAM_KEY = os.environ.get("OPENAI_PROXY_EMB_KEY", "")
EMB_FORCE_MODEL = os.environ.get("OPENAI_PROXY_EMB_MODEL", "text-embedding-v4")

app = FastAPI(title="deepseek-v4 thinking-inject proxy")


def _needs_thinking_off(model: str) -> bool:
    if not INJECT_THINKING_DISABLED:
        return False
    return model.startswith("deepseek-v4")


async def _forward(path: str, request: Request) -> Any:
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        body = {}

    model = body.get("model", "")
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

    # DeepSeek v4 only supports `{"type":"json_object"}` for structured output.
    # Downgrade `json_schema` (LangChain's `with_structured_output(method="json_schema")`)
    # to `json_object` and inject the schema as a system-prompt nudge so the
    # model still emits valid JSON of the right shape.
    if model.startswith("deepseek-v4"):
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

    headers = {"Content-Type": "application/json"}
    if UPSTREAM_KEY:
        headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"
    else:
        incoming = request.headers.get("authorization")
        if incoming:
            headers["Authorization"] = incoming

    url = f"{UPSTREAM}{path}"
    stream = bool(body.get("stream"))

    timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)

    if stream:
        client = httpx.AsyncClient(timeout=timeout)
        req = client.build_request("POST", url, json=body, headers=headers)
        upstream_resp = await client.send(req, stream=True)

        async def _stream():
            try:
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
            finally:
                await upstream_resp.aclose()
                await client.aclose()

        return StreamingResponse(
            _stream(),
            status_code=upstream_resp.status_code,
            media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=body, headers=headers)
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
            # Strip <think>...</think> from any reasoning-model output so
            # client frameworks see a clean assistant message.
            for choice in (data.get("choices") if isinstance(data, dict) else None) or []:
                msg = choice.get("message") or {}
                if isinstance(msg.get("content"), str):
                    msg["content"] = _strip_think(msg["content"])
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
    headers = {"Authorization": f"Bearer {UPSTREAM_KEY}"} if UPSTREAM_KEY else {
        "Authorization": request.headers.get("authorization", "")
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{UPSTREAM}/models", headers=headers)
        return JSONResponse(status_code=r.status_code, content=r.json())


@app.get("/healthz")
async def healthz():
    return {"ok": True, "upstream": UPSTREAM, "inject_thinking_off": INJECT_THINKING_DISABLED}
