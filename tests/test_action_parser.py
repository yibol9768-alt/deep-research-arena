from __future__ import annotations

import json

from src.rl.action_parser import parse_action, render_observation
from src.rl.env import CallTool, Cite, Finalize, Open, Read, ReadMemory, Search, WriteMemory


def test_parse_each_directive_line():
    cases = [
        ("SEARCH: alpha headphone reviews", Search, "query", "alpha headphone reviews"),
        ("OPEN: <http://localhost:7770/product-a.html>", Open, "url", "http://localhost:7770/product-a.html"),
        ("READ", Read, None, None),
        ("NOTE: keep the product page evidence", WriteMemory, "note", "keep the product page evidence"),
        ("RECALL", ReadMemory, None, None),
        ("CITE: [product](http://localhost:7770/product-a.html)", Cite, "url", "http://localhost:7770/product-a.html"),
    ]

    for text, cls, attr, expected in cases:
        action = parse_action(text)
        assert isinstance(action, cls)
        if attr is not None:
            assert getattr(action, attr) == expected


def test_parse_fenced_json_directive():
    action = parse_action(
        '```json\n{"action": "search", "query": "forum comfort evidence"}\n```'
    )

    assert isinstance(action, Search)
    assert action.query == "forum comfort evidence"


def test_unparseable_falls_back_to_read_memory():
    assert isinstance(parse_action("I should think more before using a tool."), ReadMemory)


def test_finalize_block_yields_markdown():
    text = """```text
FINALIZE:
# Report

Alpha evidence appears in [product](http://localhost:7770/product-a.html).
```"""

    action = parse_action(text)

    assert isinstance(action, Finalize)
    assert action.report_md == (
        "# Report\n\n"
        "Alpha evidence appears in [product](http://localhost:7770/product-a.html)."
    )


def test_inline_finalize_with_markdown_links_is_report():
    text = (
        "FINALIZE this answer: Alpha is supported by "
        "[product](http://localhost:7770/product-a.html)."
    )

    action = parse_action(text)

    assert isinstance(action, Finalize)
    assert action.report_md == text


def test_tool_call_shape_routes_to_call_tool_with_args():
    # The natural {"tool": <name>, "args": {...}} shape must reach CallTool with
    # its args intact, not be misrouted by treating the tool name as a verb.
    cases = [
        ("rag_search", {"query": "alpha comfort"}),
        ("sql_query", {"sql": "select 1"}),
        ("crawl", {"url": "http://localhost:7770/a.html"}),
        ("run_code", {"code": "print(1)"}),
        ("cart_add", {"sku": "A1", "qty": 2}),
    ]
    for name, args in cases:
        action = parse_action(json.dumps({"tool": name, "args": args}))
        assert isinstance(action, CallTool)
        assert action.name == name
        assert action.args == args


def test_floor_tool_call_shape_preserves_query_and_url():
    # {"tool":"search","args":{"query":"x"}} previously became Search(query='').
    search = parse_action(json.dumps({"tool": "search", "args": {"query": "comfort"}}))
    assert isinstance(search, CallTool)
    assert search.name == "search"
    assert search.args == {"query": "comfort"}

    # {"tool":"fetch","args":{"url":...}} previously fell back to ReadMemory.
    fetch = parse_action(
        json.dumps({"tool": "fetch", "args": {"url": "http://localhost:7770/a.html"}})
    )
    assert isinstance(fetch, CallTool)
    assert fetch.name == "fetch"
    assert fetch.args == {"url": "http://localhost:7770/a.html"}


def test_tool_name_via_arguments_or_input_aliases():
    for key in ("arguments", "input"):
        action = parse_action(json.dumps({"tool": "rag_search", key: {"query": "x"}}))
        assert isinstance(action, CallTool)
        assert action.name == "rag_search"
        assert action.args == {"query": "x"}


def test_action_verb_with_nested_args_is_not_dropped():
    # A floor verb under "action" that nests operands in "args" should still
    # recover the operand instead of producing an empty Search/Open.
    search = parse_action(json.dumps({"action": "search", "args": {"query": "nested"}}))
    assert isinstance(search, Search)
    assert search.query == "nested"

    opened = parse_action(
        json.dumps({"action": "open", "args": {"url": "http://localhost:7770/a.html"}})
    )
    assert isinstance(opened, Open)
    assert opened.url == "http://localhost:7770/a.html"


def test_action_tool_envelope_with_name_still_works():
    # The pre-existing {"action":"tool","name":...,"args":...} form is unchanged.
    action = parse_action(
        json.dumps({"action": "tool", "name": "rag_search", "args": {"query": "x"}})
    )
    assert isinstance(action, CallTool)
    assert action.name == "rag_search"
    assert action.args == {"query": "x"}


def test_render_observation_compacts_search_page_and_memory():
    rendered = render_observation(
        {
            "last_action": "read",
            "tool_calls_used": 3,
            "tool_calls_remaining": 7,
            "search_results": [
                {
                    "title": "Product A",
                    "url": "http://localhost:7770/product-a.html",
                    "snippet": "Balanced sound and comfort evidence.",
                }
            ],
            "current_url": "http://localhost:7770/product-a.html",
            "current_page_text": "Alpha headphones have balanced sound.",
            "memory": ["alpha note"],
        }
    )

    assert "search_results:" in rendered
    assert "http://localhost:7770/product-a.html" in rendered
    assert "current_page:" in rendered
    assert "memory:" in rendered
