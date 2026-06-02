"""MCP server exposing the search-shim's four corpus capabilities.

The four MCP tools map 1:1 to shim HTTP endpoints. Each tool relays the
shim's bytes UNCHANGED so an external agent's evidence is byte-identical to
the native env path and therefore equally creditable by the reward:

    MCP tool          shim endpoint            payload                returns
    --------------    ----------------------   -------------------    ----------------------
    search            POST /search             {query, max_results}   Tavily hits {results:[...]}
    extract           POST /extract            {urls:[...]}           {results:[{url, raw_content}]}
    product_lookup    POST /product_lookup     {url}                  typed product record
    post_lookup       POST /post_lookup        {url}                  typed post record

Design constraints honoured here:

* The ``mcp`` package is imported LAZILY inside :func:`build_mcp_server` and
  inside the few functions that need it. Top-level import of this module never
  requires ``mcp``; ``SHIM_TOOL_SPECS`` / :func:`list_tool_names` are usable
  without it (the offline smoke test relies on this).
* The shim transport is injectable as ``transport_call(path, payload) -> dict``
  for offline tests. When not injected, a lazy ``requests`` POST is used
  against ``shim_url`` with the SAME ``proxies={"http": None, "https": None}``
  localhost pattern as ``HttpSandboxBackend`` / ``StructuredLookupTool``.
* Read-only relay to the localhost shim. It adds no new data and honours the
  strict allowlist via the shim it fronts (point the shim at SHIM_MODE=strict).
  It never contacts a non-localhost host.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

# Transport callable signature: (path, payload) -> decoded JSON dict.
TransportCall = Callable[[str, dict], dict]


# ---------------------------------------------------------------------------
# Tool specifications (pure data, no ``mcp`` dependency)
# ---------------------------------------------------------------------------
#
# Each spec describes one MCP tool: its public name, a one-line description,
# the shim endpoint it relays to, and a JSON-Schema ``input_schema``. Keeping
# this as plain data (rather than building it through the ``mcp`` SDK) lets the
# offline smoke test enumerate the four tools without importing ``mcp`` and
# without a live shim.

SHIM_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "search",
        "endpoint": "/search",
        "description": (
            "Search the Deep Research Arena corpus (Magento shop, Postmill "
            "forum, Kiwix Wikipedia). Returns Tavily-style hits with url, "
            "title, content and score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of hits to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "extract",
        "endpoint": "/extract",
        "description": (
            "Extract full page text for one or more corpus URLs. Returns the "
            "shim's raw_content for each URL unchanged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Corpus URLs to extract (sandbox allowlist).",
                },
            },
            "required": ["urls"],
        },
    },
    {
        "name": "product_lookup",
        "endpoint": "/product_lookup",
        "description": (
            "Return a typed product record (name, price, rating, sku, "
            "review_count, in_stock, ...) for a Magento product-detail URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Magento PDP URL (:7770)."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "post_lookup",
        "endpoint": "/post_lookup",
        "description": (
            "Return a typed forum-post record (title, author, forum, score, "
            "comment_count, body, top_comments) for a Postmill submission URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Postmill submission URL (:9999)."},
            },
            "required": ["url"],
        },
    },
)

# The four tool names, in registration order. Used by the smoke test.
MCP_TOOL_NAMES: tuple[str, ...] = tuple(spec["name"] for spec in SHIM_TOOL_SPECS)

# Endpoint lookup by tool name.
_ENDPOINT_BY_NAME: dict[str, str] = {
    spec["name"]: spec["endpoint"] for spec in SHIM_TOOL_SPECS
}


def list_tool_names() -> list[str]:
    """Return the four MCP tool names without importing ``mcp``.

    Convenience for callers / tests that only need the federated capability
    surface, not a live server object.
    """
    return list(MCP_TOOL_NAMES)


# ---------------------------------------------------------------------------
# Argument -> shim payload mapping
# ---------------------------------------------------------------------------

def _build_payload(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Translate MCP tool arguments into the shim's request body.

    Mirrors the shim's request models so the relayed bytes match what the
    native env path sends. Unknown extra keys are ignored.
    """
    args = arguments or {}
    if name == "search":
        payload: dict[str, Any] = {"query": str(args.get("query") or "")}
        if args.get("max_results") is not None:
            payload["max_results"] = int(args["max_results"])
        return payload
    if name == "extract":
        urls = args.get("urls") or []
        if isinstance(urls, str):
            urls = [urls]
        return {"urls": [str(u) for u in urls]}
    if name in ("product_lookup", "post_lookup"):
        return {"url": str(args.get("url") or "")}
    raise KeyError(f"unknown MCP tool: {name!r}")


# ---------------------------------------------------------------------------
# Transport: injected callable, else a lazy requests POST against the shim
# ---------------------------------------------------------------------------

class ShimTransport:
    """Relays an MCP tool call to a shim HTTP endpoint.

    Resolution order, matching ``StructuredLookupTool``:
      1. an injected ``transport_call(path, payload) -> dict`` (tests / DI);
      2. a lazy ``requests`` POST against ``shim_url`` using the localhost
         ``proxies={"http": None, "https": None}`` pattern.

    ``requests`` is imported inside :meth:`call` so importing this module never
    requires it.
    """

    def __init__(
        self,
        shim_url: Optional[str] = None,
        transport_call: Optional[TransportCall] = None,
        *,
        bearer_token: str = "sandbox",
        timeout: float = 60.0,
    ) -> None:
        self._shim_url = (shim_url or os.environ.get("SHIM_URL") or "").rstrip("/")
        self._transport_call = transport_call
        self._bearer_token = bearer_token
        self._timeout = timeout

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        path = _ENDPOINT_BY_NAME.get(name)
        if path is None:
            raise KeyError(f"unknown MCP tool: {name!r}")
        payload = _build_payload(name, arguments)

        if self._transport_call is not None:
            return self._transport_call(path, payload)

        if not self._shim_url:
            raise RuntimeError(
                "MCP server requires a shim_url or an injected transport_call"
            )

        try:
            import requests  # lazy: module imports without requests installed
        except Exception as exc:  # pragma: no cover - exercised on the live box
            raise RuntimeError(
                "MCP server requires the 'requests' package for live shim calls"
            ) from exc

        headers = {"Content-Type": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        response = requests.post(
            f"{self._shim_url}{path}",
            json=payload,
            headers=headers,
            timeout=self._timeout,
            # localhost shim: never route through an HTTP proxy.
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        return response.json()


def _result_to_text(result: Any) -> str:
    """Render a shim JSON response as a deterministic text block.

    The shim returns dicts; we relay them as compact JSON so the external
    agent receives the exact same bytes the native path produced. Strings are
    passed through verbatim.
    """
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(result)


# ---------------------------------------------------------------------------
# Server construction (lazy ``mcp`` import lives here)
# ---------------------------------------------------------------------------

def build_mcp_server(
    shim_url: Optional[str] = None,
    transport_call: Optional[TransportCall] = None,
    *,
    name: str = "deep-research-arena",
    bearer_token: str = "sandbox",
    timeout: float = 60.0,
):
    """Build and return a configured MCP server exposing the four shim tools.

    Parameters
    ----------
    shim_url:
        Base URL of the running search-shim (e.g. ``http://localhost:8081``).
        Required only when ``transport_call`` is not supplied. Point the shim
        at ``SHIM_MODE=strict`` so the permanent allowlist is enforced.
    transport_call:
        Optional injected ``(path, payload) -> dict`` transport. When given,
        no network call is made (used by offline tests and custom relays).
    name:
        MCP server name advertised to clients.

    The ``mcp`` package is imported HERE (lazily). If it is missing this
    raises ``ImportError`` so callers / tests can ``importorskip`` cleanly.
    The returned object is a ``mcp.server.Server`` with the four tools
    registered via the standard ``list_tools`` / ``call_tool`` handlers.
    """
    # Lazy import: keeps module-level import clean on a plain interpreter.
    from mcp.server import Server  # type: ignore
    from mcp.types import TextContent, Tool  # type: ignore

    transport = ShimTransport(
        shim_url=shim_url,
        transport_call=transport_call,
        bearer_token=bearer_token,
        timeout=timeout,
    )

    server = Server(name)

    # Expose the tool specs on the server object for introspection / tests that
    # do not want to drive the async MCP handlers.
    server.shim_tool_specs = SHIM_TOOL_SPECS  # type: ignore[attr-defined]

    @server.list_tools()
    async def _list_tools() -> list[Any]:  # noqa: D401 - MCP handler
        return [
            Tool(
                name=spec["name"],
                description=spec["description"],
                inputSchema=spec["input_schema"],
            )
            for spec in SHIM_TOOL_SPECS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:  # noqa: D401
        if name not in _ENDPOINT_BY_NAME:
            raise ValueError(f"unknown MCP tool: {name!r}")
        # Relay to the shim; return the bytes UNCHANGED as MCP text content.
        result = transport.call(name, arguments or {})
        return [TextContent(type="text", text=_result_to_text(result))]

    return server
