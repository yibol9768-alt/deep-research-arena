# Deep Research Arena MCP server

A local [Model Context Protocol](https://modelcontextprotocol.io) server that
exposes the search-shim's four corpus capabilities as standard MCP tools, so
external frontier agents (OpenAI Deep Research, Claude Code, gpt-researcher,
LangChain ODR, ...) can drive the Magento + Postmill + Kiwix sandbox through
the MCP wire protocol with no bespoke adapter.

This is **eval-side federation**, not a policy action. It is intentionally
absent from `src/rl/tools._PROVIDERS`: it federates the same corpus the native
RL environment already reaches, it does not add a new acquisition action to the
policy. The reward is unchanged because the evidence bytes are identical.

## The four tools

`tools/list` mirrors the shim's four corpus capabilities exactly:

| MCP tool         | shim endpoint           | returns                                  |
| ---------------- | ----------------------- | ---------------------------------------- |
| `search`         | `POST /search`          | Tavily-style hits `{results: [...]}`     |
| `extract`        | `POST /extract`         | `{results: [{url, raw_content}]}`        |
| `product_lookup` | `POST /product_lookup`  | typed Magento product record             |
| `post_lookup`    | `POST /post_lookup`     | typed Postmill submission record         |

Each tool relays the shim's bytes **unchanged**, so an external agent's
evidence is byte-identical to what the native env path sees and is therefore
equally creditable by the grounding reward.

## Allowlist and security

The server is a read-only relay to the localhost shim. It adds no new data and
honours the strict sandbox allowlist via the shim it fronts. Run the shim in
strict mode so the permanent allowlist is enforced:

```bash
python integrations/search_shim/app.py --mode strict   # or SHIM_MODE=strict
```

The server only ever contacts the shim on localhost (it uses
`proxies={"http": None, "https": None}` so no HTTP proxy is consulted) and never
reaches a non-local host.

## Connecting an external agent

```python
from integrations.mcp_server import build_mcp_server

# Lazy 'mcp' import happens inside build_mcp_server.
server = build_mcp_server(shim_url="http://localhost:8081")
# ... wire `server` to your transport (stdio / SSE) per the MCP SDK ...
```

For tests or custom relays, inject a transport instead of hitting the network:

```python
def fake(path, payload):
    return {"results": [...]}        # canned shim response

server = build_mcp_server(transport_call=fake)
```

## Dependencies

The `mcp` package is imported lazily inside `build_mcp_server`, so
`import integrations.mcp_server` succeeds on a plain interpreter without `mcp`.
The dependency-free helpers `list_tool_names()` and `SHIM_TOOL_SPECS` expose the
federated capability surface without building a live server. Live shim calls use
`requests`, also imported lazily.

Install the runtime dependency only where you actually serve MCP:

```bash
pip install mcp
```

## Smoke test

`tests/test_mcp_server.py` asserts the module imports without `mcp`, that the
four tools are listed, and that a `search` round-trip through an injected fake
transport relays the canned hits unchanged. The live-server assertions
`importorskip("mcp")` so they skip cleanly when `mcp` is not installed.
