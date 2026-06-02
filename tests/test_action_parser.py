from __future__ import annotations

from src.rl.action_parser import parse_action, render_observation
from src.rl.env import Cite, Finalize, Open, Read, ReadMemory, Search, WriteMemory


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
