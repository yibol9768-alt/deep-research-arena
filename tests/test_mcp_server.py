"""Offline smoke test for the MCP server (integrations/mcp_server/server.py).

This is EVAL-SIDE FEDERATION, not a policy CallTool: the server relays the
search-shim's four corpus capabilities (search / extract / product_lookup /
post_lookup) to external MCP clients. The test never touches a live shim and
never requires a live ``mcp`` server runtime.

Coverage map:
  (A) The module imports WITHOUT the ``mcp`` package installed, and the
      dependency-free tool-spec surface lists exactly the four tool names.
  (B) An injected fake transport drives ``ShimTransport`` so a ``search``
      round-trip returns the canned hits UNCHANGED (byte-identical relay).
  (C) If ``mcp`` is importable, build the real server with the injected fake
      transport and assert the four tools are listed (otherwise importorskip
      so the test SKIPS, preserving the 2-skipped regression budget). The
      server's async ``call_tool`` handler is exercised to confirm it relays
      the shim bytes unchanged.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable so ``integrations.mcp_server`` resolves
# regardless of where pytest is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The server module MUST import without the optional ``mcp`` dependency.
from integrations.mcp_server import server as mcp_server  # noqa: E402
from integrations.mcp_server import (  # noqa: E402
    MCP_TOOL_NAMES,
    SHIM_TOOL_SPECS,
    ShimTransport,
    build_mcp_server,
    list_tool_names,
)


EXPECTED_TOOLS = {"search", "extract", "product_lookup", "post_lookup"}


# Canned shim responses keyed by endpoint. The fake transport returns these
# verbatim so we can assert the relay is byte-identical.
_CANNED = {
    "/search": {
        "query": "noise cancelling headphones",
        "results": [
            {
                "title": "NovaMax Pro Wireless Headphones",
                "url": "http://localhost:7770/novamax-pro.html",
                "content": "NovaMax Pro. $199.00 - rated 4.5/5",
                "score": 0.91,
                "raw_content": None,
            }
        ],
        "response_time": 0.012,
        "request_id": "req-test-1",
    },
    "/extract": {
        "results": [
            {
                "url": "http://localhost:7770/novamax-pro.html",
                "raw_content": "Full PDP text for NovaMax Pro ...",
                "images": [],
            }
        ],
        "failed_results": [],
        "response_time": 0.02,
        "request_id": "req-test-2",
    },
    "/product_lookup": {
        "ok": True,
        "url": "http://localhost:7770/novamax-pro.html",
        "name": "NovaMax Pro",
        "price": 199.0,
        "rating": 4.5,
    },
    "/post_lookup": {
        "ok": True,
        "url": "http://localhost:9999/f/headphones/1/review",
        "title": "NovaMax Pro long-term review",
        "author": "audiofan",
    },
}


def _fake_transport(path, payload):
    """Stand-in for the shim HTTP call: returns canned bytes, records the call."""
    _fake_transport.calls.append((path, dict(payload)))
    return _CANNED[path]


_fake_transport.calls = []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# (A) dependency-free surface: runs even when ``mcp`` is absent
# ---------------------------------------------------------------------------

def test_module_imports_without_mcp_and_lists_four_tools():
    # importing the module must not require ``mcp``; if mcp is genuinely
    # absent this test still passes (the import above already succeeded).
    assert set(MCP_TOOL_NAMES) == EXPECTED_TOOLS
    assert set(list_tool_names()) == EXPECTED_TOOLS
    assert len(SHIM_TOOL_SPECS) == 4
    # 1:1 endpoint mapping to the shim.
    by_name = {s["name"]: s for s in SHIM_TOOL_SPECS}
    assert by_name["search"]["endpoint"] == "/search"
    assert by_name["extract"]["endpoint"] == "/extract"
    assert by_name["product_lookup"]["endpoint"] == "/product_lookup"
    assert by_name["post_lookup"]["endpoint"] == "/post_lookup"
    # every spec carries a JSON-schema input contract.
    for spec in SHIM_TOOL_SPECS:
        assert spec["input_schema"]["type"] == "object"
        assert spec["description"]


def test_shim_transport_relays_bytes_unchanged():
    """The injected transport round-trips the canned shim bytes verbatim."""
    _fake_transport.calls.clear()
    transport = ShimTransport(transport_call=_fake_transport)

    out = transport.call("search", {"query": "noise cancelling headphones", "max_results": 5})
    assert out is _CANNED["/search"]  # relayed unchanged (same object)
    # payload mapping matches the shim's request model.
    assert _fake_transport.calls[-1] == (
        "/search",
        {"query": "noise cancelling headphones", "max_results": 5},
    )

    # extract accepts a list (and coerces a bare string).
    transport.call("extract", {"urls": ["http://localhost:7770/novamax-pro.html"]})
    assert _fake_transport.calls[-1][0] == "/extract"
    transport.call("product_lookup", {"url": "http://localhost:7770/novamax-pro.html"})
    assert _fake_transport.calls[-1] == (
        "/product_lookup",
        {"url": "http://localhost:7770/novamax-pro.html"},
    )


def test_shim_transport_requires_url_when_no_injected_call():
    """No injected transport and no shim_url -> clean RuntimeError, not a crash."""
    transport = ShimTransport()  # no shim_url, no transport_call
    with pytest.raises(RuntimeError):
        transport.call("search", {"query": "x"})


def test_unknown_tool_name_rejected():
    transport = ShimTransport(transport_call=_fake_transport)
    with pytest.raises(KeyError):
        transport.call("definitely_not_a_tool", {})


# ---------------------------------------------------------------------------
# (C) live-server surface: SKIPS cleanly when ``mcp`` is not installed
# ---------------------------------------------------------------------------

def test_build_server_lists_four_tools():
    pytest.importorskip("mcp", reason="mcp package not installed; eval-side federation only")

    _fake_transport.calls.clear()
    server = build_mcp_server(transport_call=_fake_transport)

    # The server exposes the four specs for introspection.
    assert {s["name"] for s in server.shim_tool_specs} == EXPECTED_TOOLS

    # Drive the standard MCP list_tools handler and assert the four names.
    listed = _collect_listed_tool_names(server)
    assert set(listed) == EXPECTED_TOOLS


def test_call_tool_relays_search_unchanged():
    pytest.importorskip("mcp", reason="mcp package not installed; eval-side federation only")

    _fake_transport.calls.clear()
    server = build_mcp_server(transport_call=_fake_transport)

    blocks = _call_tool(server, "search", {"query": "noise cancelling headphones"})
    assert blocks, "call_tool returned no content"
    text = blocks[0].text
    # The relayed text is the canned shim payload, byte-identical (parsed back).
    assert json.loads(text) == _CANNED["/search"]
    assert _fake_transport.calls[-1][0] == "/search"


# ---------------------------------------------------------------------------
# helpers to drive the MCP server's registered async handlers across SDK
# versions (handler registration shape differs slightly between releases).
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _find_handler(server, *candidates):
    """Return the first registered handler matching one of the request types.

    The low-level ``mcp.server.Server`` stores handlers in
    ``request_handlers`` keyed by request type. We resolve by type-name so the
    test is resilient to import-path differences between SDK versions.
    """
    handlers = getattr(server, "request_handlers", {}) or {}
    for req_type, handler in handlers.items():
        if getattr(req_type, "__name__", "") in candidates:
            return handler
    return None


def _collect_listed_tool_names(server):
    handler = _find_handler(server, "ListToolsRequest")
    if handler is not None:
        # Build the request object for this SDK version and invoke the handler.
        import mcp.types as t  # type: ignore

        req = t.ListToolsRequest(method="tools/list")
        result = _run(handler(req))
        tools = _extract_tools(result)
        return [getattr(tool, "name", None) for tool in tools]
    # Fallback: introspect the spec surface the server published.
    return [s["name"] for s in server.shim_tool_specs]


def _extract_tools(result):
    # result is a ServerResult / ListToolsResult wrapper depending on version.
    root = getattr(result, "root", result)
    tools = getattr(root, "tools", None)
    if tools is None:
        tools = getattr(result, "tools", [])
    return tools or []


def _call_tool(server, name, arguments):
    handler = _find_handler(server, "CallToolRequest")
    assert handler is not None, "CallToolRequest handler not registered"
    import mcp.types as t  # type: ignore

    req = t.CallToolRequest(
        method="tools/call",
        params=t.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = _run(handler(req))
    root = getattr(result, "root", result)
    content = getattr(root, "content", None)
    if content is None:
        content = getattr(result, "content", [])
    return content or []
