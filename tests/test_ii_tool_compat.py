from __future__ import annotations

import pytest

from scripts.runners.ii_tool_compat import (
    MAX_NATIVE_ACTIONS,
    api_tool_schemas,
    tool_call_to_native_action,
)


def test_native_action_budget_is_finite_and_disclosed():
    assert MAX_NATIVE_ACTIONS == 10


def test_schemas_expose_only_ii_native_search_and_visit_tools():
    schemas = api_tool_schemas()
    assert [item["function"]["name"] for item in schemas] == [
        "web_search",
        "page_visit",
    ]
    assert schemas[0]["function"]["parameters"]["required"] == ["queries"]
    assert schemas[1]["function"]["parameters"]["required"] == ["urls"]
    assert all(
        item["function"]["parameters"]["additionalProperties"] is False
        for item in schemas
    )


def test_api_calls_translate_to_the_existing_fenced_python_protocol():
    assert tool_call_to_native_action(
        "web_search", '{"queries":["anc headphones glasses"]}'
    ) == (
        "```py\nweb_search(queries=['anc headphones glasses'])\n```<end_code>"
    )
    assert tool_call_to_native_action(
        "page_visit", {"urls": ["http://localhost:9999/f/1"]}
    ) == (
        "```py\npage_visit(urls=['http://localhost:9999/f/1'])\n```<end_code>"
    )


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("unknown", "{}"),
        ("web_search", "not-json"),
        ("web_search", '{"queries":[]}'),
        ("web_search", '{"queries":[""]}'),
        ("web_search", '{"queries":["x"],"urls":["y"]}'),
    ],
)
def test_invalid_or_expanded_tool_calls_fail_closed(name, arguments):
    with pytest.raises(ValueError):
        tool_call_to_native_action(name, arguments)
