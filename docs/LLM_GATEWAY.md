# Unified LLM Gateway

One OpenAI-compatible entry point in front of every backbone the Deep Research
Arena uses. Framework lanes stop juggling a zoo of proxies and per-lane base-URL
env vars; they all point at the gateway and per-model policy is applied
server-side from a registry.

Source: `integrations/llm_gateway/app.py` (FastAPI, stdlib + fastapi + httpx,
same deps as `integrations/ds_proxy/`). Tests: `tests/test_llm_gateway.py`.

## The problem: the proxy zoo

Today a run can traverse up to five moving parts, each with its own port and
env var:

| Component | Port | Job |
| --- | --- | --- |
| `ds_proxy` | 8088 | OpenAI-compat proxy; injects `thinking:{"type":"disabled"}` for `deepseek-v4-*`; `OPENAI_PROXY_MIN_MAX_TOKENS` floor for GLM; `DSPROXY_USAGE_LOG` jsonl accounting incl. streaming; `POST /_mark` run brackets |
| max_tokens clamp proxy | 8002 | static output-token clamp (being retired) |
| GLM proxy | 8092 | Zhipu GLM forwarding |
| direct vLLM | 8001 | qwen3-8b, 65536-token window |
| per-lane env | n/a | `DS_PROXY_URL`, `OPENAI_BASE_URL`, `OPENCODE_DS_PROXY`, `FLOWSEARCHER_LLM_BASE_URL`, `LDR_LLM_OPENAI_ENDPOINT_URL`, plus per-runner precedence resolvers |

Two structural problems fall out of this:

1. Every backbone needs its own port and its own client wiring, so adding or
   moving a model is a scavenger hunt across lanes.
2. A static output-token clamp cannot fit `max_tokens` to a specific prompt.
   The clearest symptom is claude-code: it budgets its prompt to
   `context_window - max_tokens`, but vLLM counts one extra template/BOS token,
   so the final request lands at exactly `window + 1` and 400s. No fixed clamp
   value fixes this, because the safe ceiling depends on the actual prompt size.

## The design: registry + policy pipeline + accounting

### Registry (per-model policy, keyed by name prefix)

Defaults are built in and can be overridden or extended by pointing
`LLM_GATEWAY_CONFIG` at a JSON file (a list of entries, or an object with a
`models`/`registry` key). An entry sharing a `prefix` with a default overrides
it; a new prefix is appended.

| Prefix | Upstream | Key env | Window | Policy |
| --- | --- | --- | --- | --- |
| `qwen3-8b` | `http://127.0.0.1:8001/v1` | (none) | 65536 | `fit_to_window` (margin 256), `max_tokens_cap` 8192 |
| `glm-4.7-flash` | `https://open.bigmodel.cn/api/paas/v4` | `GLM_API_KEY` | 204800 | `max_tokens_floor` 131072 (thinking eats budget; floor keeps content non-empty) |
| `deepseek-v4` | `DASHSCOPE_BASE_URL` (default DashScope compat) | `DASHSCOPE_API_KEY` | 65536 | `thinking_off` (inject `{"thinking":{"type":"disabled"}}`, the exact ds_proxy knob) |

No plaintext keys live in the code or defaults. Each entry names the env var
that holds its key; the gateway reads it at request time.

Routing: `/v1/chat/completions` reads `body.model`, does a longest-prefix match
against the registry, and forwards to that upstream with that key. An unknown
model returns a 404 whose JSON lists the known prefixes; it is never forwarded.

### Policy pipeline (per request, in order)

1. `max_tokens_floor`: raise `max_tokens` up to the floor.
2. `max_tokens_cap`: lower `max_tokens` down to the cap.
3. `fit_to_window` (when enabled): estimate the prompt with
   `len(json.dumps(messages)) // 3` and clamp `max_tokens` to
   `context_window - estimate - margin`, never below 256.
4. `thinking_off` (when configured): inject `{"thinking":{"type":"disabled"}}`
   if the caller did not already set it.

### Resilience: refit-and-retry (kills the window+1 class)

If an upstream returns a 400 whose body mentions `maximum context length` or
`max_model_len`, the gateway parses the reported prompt-token count (and the
reported window when present), recomputes
`max_tokens = window - reported_prompt_tokens - margin`, and retries ONCE. If it
still fails, the 400 passes through unchanged. Because the retry uses the
upstream's authoritative token count rather than a heuristic, it fixes the
claude-code `window + 1` off-by-one for every client without any per-client
tuning.

### Accounting

Set `LLMGW_USAGE_LOG` to a path and every upstream call appends one JSON line:
`ts`, `model`, `run_id` (when a `/_mark` bracket is open), `prompt_tokens`,
`completion_tokens`, `total_tokens`, `latency_ms`, and the `fit_adjustments`
applied (e.g. `["cap","fit"]` or `["refit_retry"]`). Streaming is covered the
same way ds_proxy does it: the gateway injects
`stream_options:{"include_usage":true}` and scans the SSE tail for the usage
chunk while piping the stream through untouched.

`POST /_mark` uses the same contract as ds_proxy (free-form JSON;
conventional fields `run_id`, `phase` `start`/`end`, `agent`, `task_id`,
`backbone`). A `start` with a `run_id` opens an in-memory bracket that tags
subsequent usage lines; an `end` closes it.

Introspection: `GET /healthz` returns the registry summary (prefixes, upstreams,
the env-var NAME of each key, window, and policy flags) and never any key
material; `GET /v1/models` lists the registry as an OpenAI models listing.

## Migration table: many envs become one

The per-runner precedence resolvers added this week already honor
`DS_PROXY_URL`, so pointing every lane at the gateway is a single variable:

```
DS_PROXY_URL=http://127.0.0.1:8100/v1
```

| Lane / client | Env used today | After migration |
| --- | --- | --- |
| generic OpenAI clients | `OPENAI_BASE_URL` | `DS_PROXY_URL` (or set `OPENAI_BASE_URL` to the gateway) |
| ds-shim lanes | `DS_PROXY_URL` | unchanged; now targets `:8100` |
| opencode | `OPENCODE_DS_PROXY` | unnecessary; resolver falls back to `DS_PROXY_URL` |
| flowsearcher | `FLOWSEARCHER_LLM_BASE_URL` | unnecessary; resolver falls back to `DS_PROXY_URL` |
| local-deep-research | `LDR_LLM_OPENAI_ENDPOINT_URL` | unnecessary; resolver falls back to `DS_PROXY_URL` |

The GLM floor (`OPENAI_PROXY_MIN_MAX_TOKENS`), the deepseek thinking-off knob,
and the max_tokens clamp all become per-model registry policy, so the clamp
proxy (:8002) and the standalone GLM proxy (:8092) are retired once every lane
is on the gateway.

## Deployment

Workstation:

```
LLMGW_USAGE_LOG=/var/log/llmgw_usage.jsonl \
GLM_API_KEY=... DASHSCOPE_API_KEY=... \
uvicorn integrations.llm_gateway.app:app --host 0.0.0.0 --port 8100
```

my5090 box (same, bound on :8100 for the sandboxed lanes):

```
LLMGW_USAGE_LOG=/root/logs/llmgw_usage.jsonl \
uvicorn integrations.llm_gateway.app:app --host 0.0.0.0 --port 8100
```

## Notes

- claude-code window+1: solved by the refit-and-retry above. No client-side
  budget tuning is required; the gateway fits `max_tokens` from the upstream's
  own reported token count.
- CCR (the anthropic-protocol translation layer) stays a separate process; it
  should point its OpenAI upstream at the gateway (`:8100/v1`) so its lanes get
  the same registry policy and accounting.
- DO NOT SWITCH YET: the live GLM full run keeps using its current proxies
  (ds_proxy / GLM proxy) until it finishes. Migrate at the next run boundary,
  not mid-run.
```
