#!/usr/bin/env python3
"""Probe all six frozen model routes without persisting prompts or credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def probe_payload(route: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": route["request_name"],
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    }
    if route["model_id"] == "gpt-5-6-sol":
        body["max_completion_tokens"] = 16
    else:
        body["max_tokens"] = 1
        body["temperature"] = 0
    return body


def normalized_usage(value: object) -> dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    cached_tokens = int(
        usage.get("cached_tokens")
        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        or 0
    )
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cached": cached_tokens,
        "total": int(usage.get("total_tokens", input_tokens + output_tokens) or 0),
    }


def run_probe(routes: dict[str, Any], token: str) -> dict[str, Any]:
    contract = routes["credential_contract"]
    rows = []
    for route in routes["models"]:
        body = probe_payload(route)
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        request = urllib.request.Request(
            route["upstream_url"].rstrip("/") + "/chat/completions",
            data=encoded,
            headers={
                contract["header"]: f"{contract['scheme']} {token}".strip(),
                "Adams-Platform-User": contract["platform_user"],
                "Adams-Business": contract["business"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        status = None
        response_body = b""
        transport_error = None
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                status = response.status
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
        except Exception as exc:  # receipt stores only the exception class
            transport_error = type(exc).__name__
        parsed: dict[str, Any] = {}
        try:
            candidate = json.loads(response_body)
            if isinstance(candidate, dict):
                parsed = candidate
        except Exception:
            pass
        actual = parsed.get("model") if isinstance(parsed.get("model"), str) else None
        error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        expected = route["expected_actual_identity"]
        rows.append(
            {
                "model_id": route["model_id"],
                "upstream_service_id": route["upstream_url"].split("/service/", 1)[-1].split("/", 1)[0],
                "upstream_request_model": route["request_name"],
                "expected_actual_identity": expected,
                "actual_model_identity": actual,
                "identity_match": actual == expected,
                "http_status": status,
                "transport_error_type": transport_error,
                "request_contract": (
                    "max_completion_tokens_16_no_temperature"
                    if route["model_id"] == "gpt-5-6-sol"
                    else "max_tokens_1_temperature_0"
                ),
                "request_body_sha256": hashlib.sha256(encoded).hexdigest(),
                "response_body_sha256": hashlib.sha256(response_body).hexdigest() if response_body else None,
                "response_error_type": error.get("type"),
                "response_error_code": error.get("code"),
                "usage": normalized_usage(parsed.get("usage")),
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        )
    passed = all(
        row["http_status"] == 200
        and row["transport_error_type"] is None
        and row["identity_match"] is True
        for row in rows
    )
    return {
        "schema_version": "q1_v2_model_route_probe_v1",
        "status": "PASS" if passed else "BLOCKED",
        "route_count": len(rows),
        "credential_value_logged": False,
        "generated_content_logged": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    routes = json.loads((ROOT / "config" / "model_routes.json").read_text())
    token = os.environ.get(routes["credential_contract"]["env"])
    if not token:
        raise SystemExit("controlled credential is absent")
    result = run_probe(routes, token)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
