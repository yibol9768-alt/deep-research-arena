#!/usr/bin/env python3
"""Compare two minimal GPT route identity-probe payloads without logging text.

The credential is read only from the controlled environment.  The receipt
contains status, returned model identity, token usage and response hashes; it
never persists the credential or generated content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


URL = (
    "http://mmdcadamsminiserverproxy.polaris:25340/"
    "service/27797/v1/chat/completions"
)
MODEL = "gpt-5.6-sol"


def payloads() -> tuple[tuple[str, dict], ...]:
    base = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    }
    return (
        (
            "legacy_max_tokens_temperature",
            {**base, "max_tokens": 1, "temperature": 0},
        ),
        (
            "max_completion_tokens_no_temperature",
            {**base, "max_completion_tokens": 16},
        ),
    )


def _usage(value: object) -> dict:
    usage = value if isinstance(value, dict) else {}
    return {
        "input": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "output": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
        "total": int(usage.get("total_tokens", 0) or 0),
    }


def probe(token: str, platform_user: str, business: str) -> dict:
    rows = []
    for name, body in payloads():
        encoded = json.dumps(body, separators=(",", ":")).encode()
        request = urllib.request.Request(
            URL,
            data=encoded,
            headers={
                "Authorization": f"Bearer {token}",
                "Adams-Platform-User": platform_user,
                "Adams-Business": business,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.monotonic()
        status = None
        response_body = b""
        transport_error = None
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                status = response.status
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
        except Exception as exc:  # receipt keeps only the exception class
            transport_error = type(exc).__name__
        parsed = {}
        try:
            candidate = json.loads(response_body)
            if isinstance(candidate, dict):
                parsed = candidate
        except Exception:
            pass
        actual = parsed.get("model") if isinstance(parsed.get("model"), str) else None
        error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        rows.append(
            {
                "variant": name,
                "request_body_sha256": hashlib.sha256(encoded).hexdigest(),
                "http_status": status,
                "transport_error_type": transport_error,
                "actual_model_identity": actual,
                "identity_match": actual == MODEL if actual is not None else None,
                "usage": _usage(parsed.get("usage")),
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "response_body_sha256": (
                    hashlib.sha256(response_body).hexdigest() if response_body else None
                ),
                "response_error_type": error.get("type"),
                "response_error_code": error.get("code"),
            }
        )
    return {
        "schema_version": "gpt_route_payload_probe_v1",
        "url_service_id": 27797,
        "requested_model": MODEL,
        "credential_value_logged": False,
        "generated_content_logged": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("TRUTH1000_ADAMS_USER_TOKEN")
    if not token:
        raise SystemExit("controlled credential is absent")
    result = probe(
        token,
        os.environ.get("DRA_ADAMS_PLATFORM_USER", "sivenfuuliu"),
        os.environ.get("DRA_ADAMS_BUSINESS", "3939"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
