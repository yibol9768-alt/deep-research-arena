#!/usr/bin/env python3
"""One-call compatibility probe for the local vLLM JSON-Schema decoder."""

from __future__ import annotations

import json

from openai import OpenAI


schema = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 8},
                    "ok": {"type": "boolean"},
                },
                "required": ["id", "ok"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}
def main() -> int:
    client = OpenAI(
        base_url="http://127.0.0.1:8000/v1",
        api_key="EMPTY",
        timeout=120,
    )
    response = client.chat.completions.create(
        model="qwen3-8b",
        temperature=0,
        max_tokens=128,
        messages=[
            {
                "role": "system",
                "content": "Return the requested JSON and nothing else.",
            },
            {
                "role": "user",
                "content": 'Return one item whose id is "x" and ok is true.',
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "dra_schema_probe",
                "schema": schema,
                "strict": True,
            },
        },
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    text = response.choices[0].message.content or ""
    parsed = json.loads(text)
    assert parsed == {"items": [{"id": "x", "ok": True}]}, parsed
    print(json.dumps({"passed": True, "response": parsed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
