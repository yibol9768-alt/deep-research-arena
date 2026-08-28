#!/usr/bin/env python3
"""One OpenAI-compatible Adams gateway per matrix cell.

The credential stays in memory. Every accepted upstream request appends one
cell-owned usage event, including HTTP failures and responses without usage.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    finally:
        os.close(fd)


def _parse_response(body: bytes, content_type: str) -> tuple[str | None, dict, str | None]:
    model = None
    usage: dict = {}
    service_tier = None
    payloads: list[dict] = []
    if "text/event-stream" in content_type:
        for line in body.decode("utf-8", "replace").splitlines():
            if not line.startswith("data:"):
                continue
            value = line[5:].strip()
            if value == "[DONE]":
                continue
            try:
                payloads.append(json.loads(value))
            except Exception:
                continue
    else:
        try:
            value = json.loads(body)
            if isinstance(value, dict):
                payloads.append(value)
        except Exception:
            pass
    for payload in payloads:
        if isinstance(payload.get("model"), str):
            model = payload["model"]
        if isinstance(payload.get("service_tier"), str):
            service_tier = payload["service_tier"]
        if isinstance(payload.get("usage"), dict) and payload["usage"]:
            usage = payload["usage"]
    return model, usage, service_tier


def _tokens(usage: dict) -> dict:
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    return {
        "input": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "output": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
        "cached_input": int(details.get("cached_tokens", usage.get("cached_input_tokens", 0)) or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens", 0) or 0),
        "cache_write_5m": int(usage.get("cache_creation_5m_input_tokens", 0) or 0),
        "cache_write_1h": int(usage.get("cache_creation_1h_input_tokens", 0) or 0),
        "reasoning": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0) if isinstance(usage.get("completion_tokens_details"), dict) else 0,
        "total": int(usage.get("total_tokens", 0) or 0),
    }


def start_proxy(*, upstream_url: str, credential: str, credential_header: str, credential_scheme: str, cell_id: str, harness_id: str, run_id: str, requested_model: str, expected_identity: str, usage_log: Path, extra_headers: dict[str, str] | None = None, service_tier: str = "standard", timeout: float = 900):
    upstream_url = upstream_url.rstrip("/")
    extra_headers = dict(extra_headers or {})
    state_lock = threading.Lock()
    state = {"active_run_id": None, "requests": 0, "completed": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _json(self, status: int, body: dict):
            payload = json.dumps(body, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle(self):
            route = urllib.parse.urlsplit(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            if route == "/_mark" and self.command == "POST":
                try:
                    mark = json.loads(body)
                except Exception:
                    return self._json(400, {"error": "invalid_json"})
                phase, owner = mark.get("phase"), mark.get("run_id")
                with state_lock:
                    if phase == "start" and state["active_run_id"] in {None, owner}:
                        state["active_run_id"] = owner
                    elif phase == "end" and state["active_run_id"] == owner:
                        state["active_run_id"] = None
                    else:
                        return self._json(409, {"error": "bracket_owner_mismatch"})
                return self._json(200, {"ok": True, "phase": phase})
            if route == "/healthz":
                with state_lock:
                    return self._json(200, {"cell_id": cell_id, "smoke_budget": dict(state), "usage_log_bytes": usage_log.stat().st_size if usage_log.exists() else 0})

            caller_model = None
            outbound = body
            if body and "json" in self.headers.get("Content-Type", "application/json"):
                try:
                    request_doc = json.loads(body)
                    if isinstance(request_doc, dict):
                        caller_model = request_doc.get("model")
                        request_doc["model"] = requested_model
                        if request_doc.get("stream") is True:
                            opts = request_doc.setdefault("stream_options", {})
                            if isinstance(opts, dict):
                                opts["include_usage"] = True
                        outbound = json.dumps(request_doc, ensure_ascii=False).encode()
                except Exception:
                    pass
            suffix = self.path
            if suffix.startswith("/v1"):
                suffix = suffix[3:] or "/"
            target = upstream_url + suffix
            owned_headers = {
                "host", "connection", "content-length", "authorization",
                credential_header.lower(), *(key.lower() for key in extra_headers),
            }
            headers = {
                k: v for k, v in self.headers.items()
                if k.lower() not in owned_headers
            }
            headers[credential_header] = f"{credential_scheme} {credential}".strip()
            headers.update(extra_headers)
            headers["Content-Length"] = str(len(outbound))
            request = urllib.request.Request(target, data=outbound if outbound else None, headers=headers, method=self.command)
            started = time.monotonic()
            with state_lock:
                state["requests"] += 1
                active_owner = state["active_run_id"]
                request_index = state["requests"]
            try:
                try:
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        response_body, status, response_headers = response.read(), response.status, response.headers
                except urllib.error.HTTPError as exc:
                    response_body, status, response_headers = exc.read(), exc.code, exc.headers
                content_type = response_headers.get("Content-Type", "")
                actual, usage, response_service_tier = _parse_response(response_body, content_type)
                normalized_tokens = _tokens(usage)
                _append(usage_log, {
                    "schema_version": "2.0.0", "event_id": str(uuid.uuid4()), "at_ns": time.time_ns(),
                    "cell_id": cell_id, "harness_id": harness_id, "run_id": run_id,
                    "bracket_run_id": active_owner, "request_index": request_index,
                    "requested_model": requested_model, "caller_requested_model": caller_model,
                    "actual_model_identity": actual, "expected_actual_identity": expected_identity,
                    "identity_match": (actual == expected_identity) if actual is not None else None, "http_status": status,
                    "latency_ms": round((time.monotonic() - started) * 1000, 3),
                    "usage_observed": bool(usage), "usage_raw": usage,
                    "tokens": normalized_tokens,
                    "prompt_tokens_for_pricing": normalized_tokens["input"],
                    "service_tier": response_service_tier or service_tier,
                    "response_body_sha256": hashlib.sha256(response_body).hexdigest(),
                    "matrix_attribution": {"cell_id": cell_id, "requested_model": requested_model, "raw_usage_actual_identity": actual, "meta_actual_identity": actual},
                })
                with state_lock:
                    state["completed"] += 1
                self.send_response(status)
                for key, value in response_headers.items():
                    if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            except Exception as exc:
                _append(usage_log, {
                    "schema_version": "2.0.0", "event_id": str(uuid.uuid4()), "at_ns": time.time_ns(),
                    "cell_id": cell_id, "harness_id": harness_id, "run_id": run_id,
                    "bracket_run_id": active_owner, "request_index": request_index,
                    "requested_model": requested_model, "actual_model_identity": None,
                    "expected_actual_identity": expected_identity, "identity_match": None,
                    "http_status": None, "transport_error_type": type(exc).__name__,
                    "latency_ms": round((time.monotonic() - started) * 1000, 3), "usage_observed": False,
                    "tokens": _tokens({}), "usage_raw": {},
                    "prompt_tokens_for_pricing": 0, "service_tier": service_tier,
                    "matrix_attribution": {"cell_id": cell_id, "requested_model": requested_model, "raw_usage_actual_identity": None, "meta_actual_identity": None},
                })
                return self._json(502, {"error": "llm_upstream_failure", "type": type(exc).__name__})

        do_GET = _handle
        do_POST = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name=f"cell-dsproxy-{cell_id}")
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}/v1"


def stop_proxy(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
