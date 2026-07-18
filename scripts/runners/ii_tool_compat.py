"""OpenAI-tool compatibility for ii-researcher's native action protocol.

ii-researcher 0.1.5 advertises ``web_search`` and ``page_visit`` only as
Python snippets in prompt text. Some OpenAI-compatible reasoning models ignore
that textual convention while supporting Chat Completions function tools. This
module describes the same two native tools to the API and translates a selected
function call back into the exact fenced-Python action ii already parses.

It does not execute a tool, choose a query, force tool use, or alter reports.
``tool_choice=auto`` remains the model's decision; the native agent executes the
translated action through its own registry and history.
"""
from __future__ import annotations

import json
from typing import Any


_ARGUMENTS = {
    "web_search": "queries",
    "page_visit": "urls",
}

# ii-researcher 0.1.5 has an unbounded ``while True`` action loop. Its native
# search suffix explicitly says every result "may not [be] enough" and to do
# more research, which can keep an instruction-following model searching until
# the outer 750k-token fuse. Ten native actions leave ample discovery room while
# guaranteeing that the framework reaches its own ReportBuilder.
MAX_NATIVE_ACTIONS = 10


def api_tool_schemas() -> list[dict[str, Any]]:
    """Return Chat Completions schemas equivalent to II's native tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search for one or more queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["queries"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "page_visit",
                "description": "Read one or more result URLs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["urls"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def tool_call_to_native_action(name: str, arguments: str | dict[str, Any]) -> str:
    """Translate one API function call to II's fenced-Python action syntax."""
    if name not in _ARGUMENTS:
        raise ValueError(f"unsupported ii tool call: {name!r}")
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("ii tool arguments are not valid JSON") from exc
    else:
        parsed = arguments
    if not isinstance(parsed, dict):
        raise ValueError("ii tool arguments must be a JSON object")
    expected = _ARGUMENTS[name]
    if set(parsed) != {expected}:
        raise ValueError(
            f"{name} requires exactly the {expected!r} argument; got {sorted(parsed)}"
        )
    values = parsed[expected]
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        raise ValueError(f"{name}.{expected} must be a non-empty list of strings")
    action = f"{name}({expected}={values!r})"
    return f"```py\n{action}\n```<end_code>"
