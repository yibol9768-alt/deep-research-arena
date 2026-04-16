# DeerFlow Integration

Monkey-patch adapters that retarget [DeerFlow v1](https://github.com/bytedance/deer-flow/tree/main-1.x)
multi-agent flow at our local sandboxed sites.

## Setup

```bash
# Outside this repo, clone DeerFlow main-1.x branch into ../third_party/deer-flow-v1
git clone --depth 1 --branch main-1.x https://github.com/bytedance/deer-flow.git \
    ../third_party/deer-flow-v1

# Install with Python 3.12 venv
cd ../third_party/deer-flow-v1
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e . beautifulsoup4 requests

# Copy our adapters into DeerFlow's working dir
cp ../../integrations/deerflow/{shop_adapter.py,reddit_adapter.py,conf.yaml} .

# Configure GLM (or any other Anthropic-compat endpoint) in conf.yaml
# Then run:
SHOPPING=http://localhost:7770 python shop_adapter.py dr_shop_0001
REDDIT=http://localhost:9999 python reddit_adapter.py dr_red_0002
```

## How it works

DeerFlow's `researcher_node` builds its tool list from
`get_web_search_tool()` and `crawl_tool` at runtime. We monkey-patch
both attributes (in `src.tools.search`, `src.graph.nodes`,
`src.tools.crawl`) before invoking the graph, swapping in our
sandbox-aware tools (`shop_search` / `shop_browse` / `reddit_list` /
`reddit_browse`).

We also bypass DeerFlow's hardcoded `mcp-github-trending` MCP server
by calling `graph.astream(...)` directly with `mcp_settings: {"servers": {}}`.

See `INTEGRATION_NOTES.md` for the full debugging story (httpx 502,
content-safety filters, DeerFlow v2 vs v1 split, etc.).
