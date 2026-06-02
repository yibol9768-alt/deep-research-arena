# Acquisition Modalities

Workstream C, Deep Research Arena.

The Deep Research environment separates **how evidence is acquired** (the
acquisition channel) from **how it is scored** (the reward). This document
specifies the pluggable modality layer: the channels we ship, why the reward
treats them identically, the task-schema capability field that selects a
channel, and the honest scope line on computer-use vision-RL.

The key design property is that adding a new acquisition channel is adding a
new **backend**, never a new action. The text-only C1 action space
(`Search` / `Open` / `Read` / `WriteMemory` / `ReadMemory` / `Cite` /
`Finalize`) is unchanged across every channel, so the same 4B text policy gets
real-browser or computer-use acquisition transparently.

## 1. Modality matrix

Three channels share one `SandboxBackend` protocol
(`src/rl/env.py`: `search(query) -> list[Hit]`, `fetch(url) -> str`). Each
channel lands the same `(url, page_text)` pairs into the env, so each is usable
everywhere the env runs.

| Channel | Backend class | Where it lands text | Arena eval | RL training | Reward |
| ------- | ------------- | ------------------- | ---------- | ----------- | ------ |
| `search_shim` (live) | `HttpSandboxBackend` (`src/rl/env.py`) | Tavily-compatible shim: `POST /search`, `POST /extract` `raw_content` | Yes (13 framework + baseline adapters use it today) | Yes (pilot default) | Identical |
| `browser` (Playwright) | `BrowserSandboxBackend` (`src/rl/backends.py`) | live DOM `document.body.innerText` via `page.evaluate` | Yes (`browser-dr` adapter plus `scripts/runners/browser_dr_runner.py`) | Yes (select via task field) | Identical |
| `computer_use` (page loop + stub) | `ComputerUseBackend` (`src/rl/backends.py`) | page-backed observe-act loop returns visible text; text-proxy stub delegates to an inner backend (byte-identical) | Wiring tested offline; real VLM live-gated | Factory-selectable; trained VLM weights are post-pilot | Identical |

Mock channel for offline tests: `MockSandboxBackend` (`pages` + `index` dicts)
and the `mock` modality of the factory return canned pages with no network.

Selection happens through the factory in `src/rl/backends.py`:

- `make_backend(modality, **kw)` returns the backend for an explicit modality
  string.
- `make_backend_from_task(task_config, *, shim_url=None, mock=None, **kw)`
  reads the task's `acquisition` block and dispatches to `make_backend`. A
  `mock` argument is a dependency-injection override returned verbatim, which
  is how the parity test and offline runs avoid any live service.

`src/rl/env.py` also re-exports the task-aware path as
`backend_from_task_config(...)` (a lazy thin wrapper over
`make_backend_from_task`) so callers can stay inside `src.rl.env`.

## 2. Why the reward is modality-agnostic

The grounding reward never inspects how a page was fetched. It reads only two
things off the rollout:

1. `rollout.retrieved_snippets` (a `dict[url] -> page_text` populated by
   `ResearchEnv._do_read`, keyed by `canonicalize_url(url)`), and
2. the ordered cited URLs extracted from `rollout.report_md`.

See `src/eval/evaluator.py::_compute_ground_signals`. The composite grounding
signal is

```
s_ground = 0.6 * f1_claim + 0.4 * r_resolve
```

where `r_resolve` is the fraction of cited URLs that appear in the retrieval
store, and `f1_claim` averages per-citation page-support leaves computed from
`store[url]` (the fetched text) against the claim text near the citation. There
is no reference anywhere in that function to the acquisition channel, the
backend type, the transport, or the runner.

The consequence is the **(url, snippet) grounding argument**: any backend that
fills `retrieved_snippets[canonicalize_url(url)]` with the page text and lets
the policy `Cite(url)` earns the identical reward. The reward credits the
acquired evidence, not the mechanism that acquired it.

### The modality-parity property (proven offline)

For a fixed `task_config` and a fixed acquisition outcome (an identical set of
`(url, page_text)` pairs and an identical sequence of cited URLs in the
report), the composite reward from `ArenaEvaluator.evaluate_rollout` is
identical regardless of which backend produced those pairs. Formally: if two
rollouts have equal `report_md`, equal `fetched_urls` (post `canonicalize_url`),
and equal `retrieved_snippets`, their `composite`, `per_dim`, policy, and
breakdown are equal.

`tests/test_modality_parity.py` proves this three ways. It drives the same
deterministic scripted policy through three `ResearchEnv` episodes whose only
difference is the backend (`MockSandboxBackend`; `BrowserSandboxBackend` over a
fake injected page; `ComputerUseBackend.text_proxy` wrapping a mock), then
asserts equal `retrieved_snippets` / `fetched_urls` / `report_md` and equal
`ArenaEvaluator(mode="fast")` composite plus `per_dim` across all three legs.
`mode="fast"` keeps the run fully offline and deterministic (no LLM judge), and
the fake page / mock backends keep it free of playwright, GPU, and any live
service. The test passes on system `python3`.

## 3. Task-schema capability field

A single optional top-level block named `acquisition` declares which channel a
task wants. It is a sibling of `sites` / `markdown_spec` in the
`cross_site_deep` task JSON.

```json
"acquisition": {
  "modalities": ["shim"],
  "backend": "shim",
  "shim_url": "http://localhost:8081",
  "max_results": 10
}
```

Field spec:

| Field | Type | Meaning | Default |
| ----- | ---- | ------- | ------- |
| `modalities` | `list[str]`, ordered preference | candidate channels; the first is used | `["shim"]` |
| `backend` | `str`, optional convenience scalar | if present it wins over `modalities[0]` | `modalities[0]` |
| `shim_url` | `str`, optional | shim base for the `shim` channel and the `browser` channel's SERP delegation | env / `http://localhost:8081` |
| `max_results` | `int`, optional | search breadth passthrough to `HttpSandboxBackend` | `10` |

Allowed channel values (case-insensitive), with the aliases the factory
accepts:

| Canonical | Accepted aliases |
| --------- | ---------------- |
| `search_shim` | `shim`, `search-shim`, `http` |
| `browser` | `browser` |
| `computer_use` | `computeruse`, `computer-use` |
| `mock` | `mock` (tests only) |

Anything else raises `ValueError("unknown acquisition modality: <x>")` at
construction, so a typo fails loud at build time rather than silently at reward
time.

**Default is `shim`.** When the `acquisition` block is absent or empty, the
modality resolves to `shim`, which reproduces today's `HttpSandboxBackend`
byte for byte. Every existing `cross_site_deep` task omits the field, so this
change is fully backward compatible: the canonical task files are unchanged and
score exactly as before.

### How the env selects a backend

`ResearchEnv` itself does not choose a backend; it receives one, unchanged. The
selection lives at the construction site that builds the
`backend_factory: Callable[[], SandboxBackend]` threaded through
`src/rl/runner.py::collect_group` and `src/rl/grpo.py::GRPOTrainer`. The
factory call is

```python
backend_from_task_config(task_config, shim_url=args.shim_url)
```

which reads `task_config["acquisition"]`, defaults to `shim`, and returns the
matching backend. `src.rl.env.backend_from_task_config(...)` is the lazy wrapper
over `make_backend_from_task(...)`, which keeps callers inside `src.rl.env`.
For the `browser` and `computer_use` branches the heavy imports (playwright, any
VLM client) are deferred to call time, so `import src.rl.backends` succeeds on a
plain `python3` with neither installed.

The arena path mirrors this. The `browser-dr` adapter
(`integrations/agents/browser_dr/agent.py`, slug registered lazily in
`integrations/agents/__init__.py`) drives the same text-only policy over a
`ResearchEnv` whose backend is a `BrowserSandboxBackend`, then returns
`env.to_rollout().report_md` as leaderboard markdown. The V1 bridge at
`scripts/runners/browser_dr_runner.py` exposes that adapter through the same
`async def run(intent, model, shim_url, proxy_url) -> str` contract every main
benchmark runner uses. `scripts/plan_full_leaderboard.py` also includes
`browser-dr` in the default queue. Therefore `python3 scripts/run_deep_task.py
--agent browser-dr ...` writes the normal
`data/results/deep/browser-dr__*.md` artifact, and the existing
`score_deep_answer.py` plus `build_deep_leaderboard.py` path handles it with no
alternate score schema or parallel leaderboard.

Its module top imports only `BaseAgent` and stdlib; playwright loads lazily
inside `run()`, and if it is missing `run()` returns a clean
`AgentResult(error="ImportError: ...")`. The V1 runner converts that to a short
`(browser-dr error: ...)` placeholder, which the existing degenerate-output
filters exclude from Elo just like other runner failures.

> Wiring status: `make_backend_from_task`, `backend_from_task_config`, and the
> three backends are implemented and tested offline. `browser-dr` is now also
> wired into the main Deep Research runner registry, not only the typed V2
> adapter registry. The pilot launcher `scripts/train_grpo_pilot.py` builds its
> `backend_factory` with `backend_from_task_config(task_config,
> shim_url=args.shim_url)`, so it honors the task field while staying
> byte-identical for default `shim` tasks. The computer-use page-backed
> observe-act loop is wired and covered by offline tests; the real VLM client or
> trained weights remain an injected seam and are live-gated.

## 4. Scope: computer-use vision-RL is post-pilot

Full computer-use vision-RL, meaning trained VLM weights that operate on
screenshots and emit GUI actions during RL, is explicitly out of scope for the
single-5090 pilot. It is not feasible to keep a trained vision policy in the
training loop on one 5090.

What we ship instead:

1. **The interface.** `ComputerUsePolicy` (a `Protocol` in
   `src/rl/backends.py`) defines `observe(url) -> {"screenshot", "text",
   "elements"}` and `act(observation) -> {"action": "scroll|click|type|done"}`.
   This is the seam a real VLM attaches to.
2. **A page-backed observe-act loop.** `ComputerUseBackend` can receive an
   injected Playwright-like `page` or `page_factory` plus a
   `ComputerUsePolicy`. Its `fetch(url)` navigates, captures
   `{"screenshot", "a11y", "text", "elements", "url"}`, asks the policy for
   an action, applies GUI actions such as click, type, scroll, keypress, move,
   drag, wait, or screenshot, and repeats until `done` or `max_steps`. It then
   returns the visible page text for grounding. Offline tests use a fake page,
   so the loop wiring is covered without requiring a live VLM.
3. **A text-proxy stub.** `ComputerUseBackend.text_proxy(inner=...)` ships an
   offline-safe `ComputerUsePolicy` whose `observe` returns the inner backend's
   page text in the vision-shaped envelope and whose `act` always returns
   `{"action": "done"}`. Its `fetch` and `search` delegate to the inner backend,
   so the bytes are identical to whatever inner channel it wraps. The stub
   keeps the `observe`/`act` seam available for computer-use.
4. **A real-browser backend the text policy can use today.**
   `BrowserSandboxBackend` is a complete Playwright channel: persistent page,
   sentinel resolution (`__SHOPPING__` to `:7770`, `__REDDIT__` to `:9999`,
   `__WIKIPEDIA__` to `:8090`), `fetch` returning DOM `innerText`, and `search`
   delegating SERP breadth to the shim (or scraping the catalog page when no
   shim is given). The existing text policy uses it with no change to the action
   space.

The invariant a real vision policy must preserve, documented in the module
docstring and not implemented here: `fetch()` must still terminate by returning
the page's grounding text, because the reward credits `retrieved_snippets`
regardless of how the bytes were obtained. Swapping the stub for a VLM changes
the acquisition mechanism, never the reward contract.

## 5. Stamping the capability field onto tasks

`scripts/stamp_task_modality.py` adds the `acquisition` block to a task JSON in
place. It is idempotent: re-running with the same modality is a no-op, and it
never overwrites an existing block unless `--force` is passed. It handles both
task layouts (a single-task file and a `{task_id -> task_config}` collection
file).

The RL task files are authored by a separate process and will be stamped later,
so this helper exists but is not run against any task data here. Usage:

```bash
# Stamp one task file with the default shim modality (no-op if already shim).
python3 scripts/stamp_task_modality.py data/tasks/.../dr_cross_deep_0001.json

# Stamp the browser modality with an explicit shim base.
python3 scripts/stamp_task_modality.py path/to/task.json --modality browser --shim-url http://localhost:8081

# Preview without writing.
python3 scripts/stamp_task_modality.py path/to/task.json --modality browser --dry-run
```

## 6. Eval-side federation: the MCP server

The channels above are how the RL policy acquires evidence. There is also an
eval-side path for external frontier agents that already speak the
[Model Context Protocol](https://modelcontextprotocol.io). The local MCP server
at `integrations/mcp_server/` exposes the search-shim's four corpus
capabilities as standard MCP tools so an OpenAI Deep Research, Claude Code,
gpt-researcher, or LangChain ODR agent can drive the same Magento + Postmill +
Kiwix sandbox with no bespoke adapter.

This is federation, not a new action. The server is deliberately absent from
`src/rl/tools._PROVIDERS`: it does not register a policy `CallTool` and does not
change the C1 action space. It federates the same corpus the native env already
reaches, and it relays the shim's bytes unchanged, so the evidence is
byte-identical to the native path and the grounding reward is unchanged.

The four MCP tools map 1:1 to shim endpoints:

| MCP tool         | shim endpoint          | returns                              |
| ---------------- | ---------------------- | ------------------------------------ |
| `search`         | `POST /search`         | Tavily-style hits `{results: [...]}` |
| `extract`        | `POST /extract`        | `{results: [{url, raw_content}]}`    |
| `product_lookup` | `POST /product_lookup` | typed Magento product record         |
| `post_lookup`    | `POST /post_lookup`    | typed Postmill submission record     |

Construction is `build_mcp_server(shim_url=None, transport_call=None)`. The
`mcp` dependency is imported lazily inside that factory, so
`import integrations.mcp_server` succeeds on a plain interpreter without `mcp`;
the dependency-free helpers `list_tool_names()` and `SHIM_TOOL_SPECS` expose the
federated capability surface without building a live server. The shim transport
is injectable as `transport_call(path, payload) -> dict` for offline tests,
otherwise a lazy `requests` POST hits `shim_url` using the same localhost
`proxies={"http": None, "https": None}` pattern as `HttpSandboxBackend`. Point
the shim at `SHIM_MODE=strict` so the permanent allowlist is enforced.

Security is read-only relay only. The server adds no new data, honours the
strict allowlist via the shim it fronts, and never contacts a non-local host.
The offline smoke test `tests/test_mcp_server.py` asserts the module imports
without `mcp`, that the four tools are listed, and that a `search` round-trip
through an injected fake transport relays the canned hits unchanged. Its
live-server assertions `importorskip("mcp")` so they skip cleanly when `mcp` is
not installed, preserving the regression skip budget. See
`integrations/mcp_server/README.md` for the client-side connection details.
