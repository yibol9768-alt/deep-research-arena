# Strict-Sandbox Contract

Workstream C, Deep Research Arena.

## The contract

> In strict mode, every URL that appears in any agent report MUST resolve
> to one of the four sandbox origins listed below. No exceptions, no
> caveats. A report that cites even one off-sandbox URL is a policy
> violation and is disqualified from leaderboard composites.

Allowed origins (both `localhost` and `127.0.0.1` forms are accepted —
they're the same socket):

| Service          | Origin                  |
| ---------------- | ----------------------- |
| Magento sandbox  | `http://localhost:7770` |
| Postmill sandbox | `http://localhost:9999` |
| Kiwix Wikipedia  | `http://localhost:8090` |
| FastAPI search shim | `http://localhost:8081` |

Strict mode is opt-in via `--strict-sandbox` on `scripts/run_deep_task.py`
(or `SHIM_MODE=strict` for the shim alone).

## Why this matters

1. **Reproducibility.** Every URL we cite in a report resolves to a
   running container we control. Anyone reproducing the benchmark gets
   identical pages — no LLM-vintage drift, no Wikipedia edit drift, no
   stale Amazon listings. The arena is a fully owned corpus.
2. **Factuality is grounded in DB.** Each sandbox endpoint is backed by a
   structured dataset (Magento product DB, Postmill submission DB, Kiwix
   ZIM file). Verifier scores can be computed from the source of truth,
   not from a snapshot.
3. **Fairness across agents.** Some agents (ClaudeCode, OpenCode) were
   previously locked down by ad-hoc disallowlists that left obvious
   escape hatches (e.g. `Bash(curl <any-url>)`). Strict mode replaces
   those with a uniform, machine-checkable contract that every agent
   must clear the same way.

## The three enforcement layers

```
┌──────────────────────────────────────────────────────┐
│ Layer 1: per-adapter tool allowlist                  │
│   ClaudeCode --allowed-tools (whitelist, not deny)   │
│   OpenCode   opencode.json commands.allowed          │
│   gpt-researcher TAVILY_API_KEY=tvly-shim-fake hard  │
│   deerflow / lcdr / storm  HTTP-layer requests gate  │
│   smolagents / camel-ai    in-proc requests.send gate│
└──────────────────────────────────────────────────────┘
                          │   any tool call
                          ▼
┌──────────────────────────────────────────────────────┐
│ Layer 2: shim-level URL gate (SHIM_MODE=strict)      │
│   /search    drops non-allowlist URLs from response  │
│   /extract,  /scrape  -> HTTP 403                    │
│   Every block logged to logs/shim_blocks.jsonl       │
└──────────────────────────────────────────────────────┘
                          │   final report
                          ▼
┌──────────────────────────────────────────────────────┐
│ Layer 3: post-run domain audit                       │
│   src/verifiers/sandbox_compliance_verifier          │
│   Scans every citation style (markdown / bare /      │
│   numbered / footnote / Source: / bullet) and writes │
│   policy_violation into <agent>__<task>.meta.json    │
└──────────────────────────────────────────────────────┘
```

Each layer is independently sufficient for a well-behaved agent. The
three together close the gaps that any single layer leaves.

## Per-adapter behavior under `--strict-sandbox`

`STRICT_SANDBOX_ELIGIBLE = True` runners may run. `False` runners are
refused pre-flight. Runners absent from the table run best-effort —
they're gated by Layer 2 (shim) and audited by Layer 3 (verifier) but
have no Layer 1 enforcement, so trust them only as far as their upstream
framework can be trusted.

| Agent                  | Layer 1 mechanism                                     | Strict-eligible | Notes                                                                                          |
| ---------------------- | ----------------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------- |
| claude-code            | `--allowed-tools` whitelist incl. `Bash(curl http://localhost*)` | YES             | Closes the historical Bash-curl gap. Previously only `WebSearch WebFetch NotebookEdit` banned. |
| opencode               | per-run `opencode.json -> commands.allowed`           | YES             | Soft prompt no longer the gate.                                                                |
| gpt-researcher         | RETRIEVER=tavily + shim base-URL + key-leak guard     | YES             | Refuses to run if a real `TAVILY_API_KEY` is in the env.                                       |
| deerflow               | crawl_tool monkey-patch + in-driver HTTP gate         | YES             | Re-binds `crawl_tool` in every loaded `src.*` module; refuses non-sandbox URLs at requests layer. |
| storm                  | SandboxSearchRM + in-proc HTTP gate                   | YES             | Retrieval was already shim-only via SandboxSearchRM; gate covers STORM's internal WebPageHelper. |
| local-deep-researcher  | TavilyClient patch + driver HTTP gate                 | YES             | Catches the 38 historical `en.wikipedia.org` URLs the framework otherwise emits.                |
| smolagents             | TavilyClient patch + in-proc HTTP gate                | YES (in-proc)   | `VisitWebpageTool` would otherwise fetch any URL the model hallucinates.                       |
| camel-ai               | TavilyClient patch + in-proc HTTP gate                | YES (in-proc)   | SearchToolkit is a moving target; HTTP gate is the durable safety net.                         |
| langchain-odr          | TavilyClient patch (existing)                         | unverified      | Best-effort. No Layer 1 in this Workstream; relies on shim + audit.                            |
| ldr                    | TavilyClient patch (existing)                         | unverified      | As above.                                                                                      |
| ii-researcher          | TavilyClient + SCRAPER_PROVIDER=bs                    | unverified      | As above.                                                                                      |
| qx-agents              | Serper adapter -> shim                                | unverified      | As above.                                                                                      |
| dzhng                  | Firecrawl shim                                        | unverified      | As above. External Node API on :3051.                                                          |
| flowsearcher-ds        | Direct shim integration                               | unverified      | As above.                                                                                      |
| tongyi-dr              | Custom ReAct loop -> shim                             | unverified      | As above.                                                                                      |
| co-storm               | TavilyClient patch (existing)                         | unverified      | As above. Output format is footnote-only so URL audit signal is low anyway.                    |
| deepagents             | LangGraph -> Tavily shim                              | unverified      | As above.                                                                                      |

To mark a currently-unverified runner as eligible, add
`STRICT_SANDBOX_ELIGIBLE = True` at the top of its `*_runner.py` AND wire
its `run()` to accept `strict_sandbox: bool = False`. Then audit it
against a known-leaky task and confirm Layer 3 reports zero off-sandbox
URLs.

## How to run `--strict-sandbox` end-to-end

```bash
# 1. Start the shim in strict mode.
python integrations/search_shim/app.py --mode strict &

# (or equivalently)
SHIM_MODE=strict uvicorn integrations.search_shim.app:app --port 8081 &

# 2. Bring up the sandbox containers (unchanged from open mode).
docker compose -f infra/sandbox/docker-compose.yaml up -d

# 3. Run an agent in strict mode.
python scripts/run_deep_task.py \
    --agent claude-code \
    --task dr_cross_deep_0001 \
    --backbone deepseek-v4-flash \
    --strict-sandbox

# 4. Inspect the post-run audit.
jq .sandbox_audit data/results/deep/claude-code__dr_cross_deep_0001.meta.json
# {
#   "sandbox_url_pct": 1.0,
#   "total_urls": 62,
#   "sandbox_urls": 62,
#   "non_sandbox_urls": [],
#   "policy_violation": false
# }

# 5. Inspect what the shim refused.
tail logs/shim_blocks.jsonl
# {"ts": ..., "endpoint": "/search", "url": "https://en.wikipedia.org/wiki/...", "reason": "non_sandbox_url_blocked"}
```

## Known gaps / TODOs

1. **Subprocess venvs cannot all enforce Layer 1.** Runners like
   `tongyi-dr`, `deepagents`, `dzhng` are not yet wired with
   `STRICT_SANDBOX_ELIGIBLE`. They will rely on Layer 2 (shim) and Layer
   3 (audit) only. Promote them by:
   a) adding `STRICT_SANDBOX_ELIGIBLE = True` to the module,
   b) adding an HTTP-layer gate inside the driver script that the runner
      builds (see `deerflow_runner._build_driver_script` for the pattern), and
   c) running the agent on a known-adversarial task; confirm zero
      `non_sandbox_urls` in the audit.
2. **dzhng runs as a remote Node service on :3051.** Its strict
   enforcement must live INSIDE the Node service, not in this Python
   runner. TODO at `third_party/deep-research/src/api.ts` would need a
   pre-fetch URL allowlist check.
3. **ClaudeCode `--allowed-tools` pattern grammar.** The patterns we
   inject (`Bash(curl http://localhost*)`) match the documented format
   but the engine's escape-sequence handling for `*` is undocumented. A
   prefix-matching agent could in principle craft `curl http://localhost
   ; curl evil.com` and pass the textual pattern. Layer 2 catches that,
   but a stricter parser would be preferable. TODO: file upstream with
   the claude-code maintainers.
4. **OpenCode `commands.allowed` is per-line, not per-tool.** A model
   that combined two commands with `&&` would bypass the allowlist on
   the second command. The runner injects 12 prefix patterns; if a model
   constructs `curl http://localhost:7770/a && curl https://evil.com`,
   only the first part is matched. Layer 2 catches it.
5. **Storm's footnote citation style yields no URL signal.** Layer 3
   reports `total_urls=0, policy_violation=False` vacuously. Combine with
   storm-specific URL-extraction from `url_to_info.json` (already added
   in `storm_runner` to append References section) so the audit sees the
   real bibliography.
