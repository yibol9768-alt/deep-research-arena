# Sandbox Search-API Shim

A FastAPI server that makes our Magento + Postmill sandbox **impersonate
popular Deep-Research search APIs** (Tavily, Firecrawl, optional SearXNG),
so any research framework can benchmark on our sandbox with **zero code
changes** — just override their base URL.

## Why

Before this shim, we monkey-patched each framework (`integrations/deerflow/
unified_adapter.py`) to inject custom tools. Two problems:

1. Unfair — a broken adapter made DeerFlow look worse than it is (we saw a
   5000-char truncation bug that dropped DeerFlow from 8 PDPs to 0).
2. Doesn't scale — every new framework (GPT-Researcher, LangChain ODR,
   OpenHands, Skywork...) needs its own adapter.

Moving the translation **down to the HTTP layer** solves both: frameworks
talk to their usual Tavily / Firecrawl endpoints, the shim re-routes those
queries to our sandbox, and the response is in the exact wire schema the
framework already expects.

## Coverage

| Framework | Default search API | Covered by this shim |
|---|---|---|
| DeerFlow | Tavily | ✅ `TAVILY_API_URL` |
| GPT-Researcher | Tavily | ✅ |
| LangChain `open_deep_research` | Tavily | ✅ |
| OpenHands (deep-research) | Tavily (MCP) | ✅ |
| Skywork DeepResearchAgent | Tavily (when enabled) | ✅ |
| CAMEL-AI SearchToolkit | DuckDuckGo or Tavily | ✅ (via Tavily or DDG) |
| dzhng/deep-research | Firecrawl | ✅ `FIRECRAWL_BASE_URL` |
| Firecrawl-native `/deep-research` | Firecrawl | ✅ |
| Perplexica | SearXNG | ✅ `/searxng/search?format=json` |
| ii-researcher | SearXNG | ✅ |
| qx-agents (`agents-deep-research`) | Serper | ✅ `/v1/serper` |
| Tongyi DeepResearch | Serper | ✅ |
| smolagents `DuckDuckGoSearchTool` | DuckDuckGo Instant | ✅ `/duckduckgo/search` |
| Brave-API consumers | Brave Search | ✅ `/v1/brave/web/search` |
| OpenAI-SDK frameworks | OpenAI chat | ✅ `/llm/v1/chat/completions` |
| Anthropic-SDK frameworks | Anthropic messages | ✅ `/llm/v1/messages` |
| AutoGen MultimodalWebSurfer | Playwright (no API) | ✅ natively (HTML sandbox) |
| TheAgentCompany | Playwright (no API) | ✅ natively |

→ **All 13 frameworks unlocked by the combined Tavily/Firecrawl/Serper/Brave/SearxNG/DDG shim.**

## Quick start

```bash
# On the remote, start the shim on port 8081
uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081

# Verify Tavily endpoint:
curl -X POST http://localhost:8081/search \
  -H "Authorization: Bearer tvly-anything" \
  -H "Content-Type: application/json" \
  -d '{"query":"noise cancelling headphones","max_results":5}' | jq .
```

Any framework just needs:

```bash
export TAVILY_API_KEY=tvly-anything        # shim ignores the token
export TAVILY_API_URL=http://localhost:8081 # or our public sandbox host
```

## Endpoints

| Method | Path | Framework schema | Purpose |
|---|---|---|---|
| `POST` | `/search` | Tavily | ✅ Combined Magento + Postmill + Wiki search |
| `POST` | `/extract` | Tavily | ✅ Fetch full page body for given URLs |
| `POST` | `/v1/search` | Firecrawl v1 | ✅ Same search, dzhng/deep-research v1 envelope |
| `POST` | `/v2/search` | Firecrawl v2 | ✅ Same search, Firecrawl v2 envelope |
| `POST` | `/v1/scrape`, `/v2/scrape` | Firecrawl | ✅ Single-URL scrape |
| `POST` | `/v1/serper` | Serper | ✅ qx-agents, Tongyi DeepResearch |
| `GET`  | `/v1/brave/web/search` | Brave | ✅ Brave Search API consumers |
| `GET`  | `/searxng/search` | SearxNG | ✅ Perplexica, ii-researcher |
| `GET`  | `/duckduckgo/search` | DuckDuckGo Instant | ✅ smolagents default tool |
| `POST` | `/llm/v1/chat/completions` | OpenAI chat | ✅ Passthrough → ds_proxy:8088 |
| `POST` | `/llm/v1/messages` | Anthropic messages | ✅ Translated → ds_proxy:8088 |
| `POST` | `/post_lookup`, `/product_lookup` | structured | ✅ HTTP-only DB lookup |
| `GET`  | `/healthz` | — | liveness |

## How results are routed

1. Each query is sent to **both** Magento (`catalogsearch/result/?q=…`) and
   Postmill (`/f/*/new.atom` filtered by keyword match).
2. Up to `max_results` items are merged, deduped by URL, sorted by a naive
   relevance score.
3. For Tavily, items become `{title, url, content, score, raw_content?}`
   where `url` is the real sandbox URL (so when the agent calls the crawl
   step, it hits our sandbox HTML directly — no re-translation needed).
4. If the framework uses `include_domains=["reddit.com"]`, we honour it by
   only returning Postmill items. Domain filtering is cheap in-shim.

## Development

```bash
pip install -r integrations/search_shim/requirements.txt
pytest integrations/search_shim/tests/
```

Unit tests verify that the returned JSON matches Tavily + Firecrawl
schemas (no drift).
