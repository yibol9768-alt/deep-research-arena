"""Local Model Context Protocol (MCP) server for the Deep Research Arena.

Eval-side federation: this package exposes the search-shim's four corpus
capabilities (``search`` / ``extract`` / ``product_lookup`` / ``post_lookup``)
as standard MCP tools so external frontier agents (OpenAI Deep Research,
Claude Code, gpt-researcher, LangChain ODR, ...) can drive our Magento +
Postmill + Kiwix sandbox through the MCP wire protocol.

This is NOT a policy ``CallTool`` and is deliberately absent from
``src/rl/tools._PROVIDERS``: it federates the SAME corpus the native env
already reaches, it does not add a new acquisition action to the RL policy.

The ``mcp`` dependency is imported LAZILY inside :func:`build_mcp_server`
(and inside the server module's functions), so ``import
integrations.mcp_server`` and ``import integrations.mcp_server.server`` both
succeed on a plain interpreter with no ``mcp`` package installed.
"""

from __future__ import annotations

from .server import (
    MCP_TOOL_NAMES,
    SHIM_TOOL_SPECS,
    ShimTransport,
    build_mcp_server,
    list_tool_names,
)

__all__ = [
    "MCP_TOOL_NAMES",
    "SHIM_TOOL_SPECS",
    "ShimTransport",
    "build_mcp_server",
    "list_tool_names",
]
