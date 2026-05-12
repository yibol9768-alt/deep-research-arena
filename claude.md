# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Deep Research (DR) agent benchmark with sandbox-based evaluation. Tests 11 open-source DR frameworks on 30 cross-site tasks requiring ≥120 cited sandbox URLs across 3 sources.

## Architecture

### Sandbox (runs on westd WSL)
- **Shopping** (Magento): `localhost:7770` — ~2000 product pages
- **Reddit** (Postmill): `localhost:9999` — forum threads
- **Wikipedia** (Kiwix): `localhost:8090` — offline Wikipedia
- **Search Shim**: `localhost:8081` — Tavily-compatible search API proxying to sandbox
- **DS Proxy**: `localhost:8088` — OpenAI-compat proxy to DeepSeek V4 flash (auto-injects `thinking:disabled`)

### Key Scripts
- `scripts/run_deep_task.py` — Main runner. RUNNERS dict maps agent name → async function. Each agent runs against sandbox via shim.
- `scripts/score_deep_answer.py` — Scores one report: url_coverage + url_reachability + quote_match + checklist_judge + citation_alignment + presentation + analysis_depth → composite_v3
- `scripts/build_deep_leaderboard.py` — Reads all `*_matrix.score.json`, computes Bradley-Terry Elo, writes `LEADERBOARD_DEEP.md`
- `scripts/build_deep_golden.py` — Scrapes sandbox to build golden URL pools per task
- `scripts/runners/` — Clean runner modules per framework (deerflow, storm, ldr, qx-agents). Each exports `async def run(intent, model, shim_url, proxy_url) -> str`

### Scoring Formula (v3)
```
grounding_gate = max(0.1, reachability)
raw_score = 0.20*url_coverage + 0.20*quote_fidelity + 0.20*judge_pass + 0.10*spec + 0.15*citation_alignment + 0.10*analysis_depth + 0.05*presentation
composite_v3 = grounding_gate * raw_score
```
Also computes composite_v2 (multiplicative truthfulness gate) and composite_v1 (legacy additive) for backward compat.

### Verifiers (`src/verifiers/`)
- `url_coverage_verifier.py` — must-cite recall + pool coverage + domain balance
- `url_reachability_verifier.py` — HTTP probe all cited URLs
- `quote_match_verifier.py` — fuzzy match cited text against fetched page content
- `checklist_verifier.py` — 21-item task-specific checklist via LLM judge
- `citation_alignment_verifier.py` — does cited URL actually support the claim? (ALCE-style)
- `presentation_verifier.py` — 12 criteria: 6 deterministic + 6 LLM judge
- `analysis_depth_verifier.py` — 10 criteria: 4 structural + 6 LLM judge
- `judge_client.py` — routes LLM calls to JUDGE_BASE_URL (ds_proxy or gpt-5-chat)

### Memory Module (`src/memory/`)
- `hierarchical.py` — L1 (per-task) / L2 (per-intent) / L3 (global) memory for FlowSearcher agent
- `workflow_miner.py` — mines existing matrix results to cold-start memory

### Data Layout
- `data/tasks/deep_research/cross_site_deep/dr_cross_deep_XXXX.json` — 30 task definitions
- `data/golden/deep/dr_cross_deep_XXXX.json` — golden URL pools (120-130 must-cite per task)
- `data/results/deep/<agent>__<task>_matrix.md` — agent reports
- `data/results/deep/<agent>__<task>_matrix.score.json` — scored results
- `data/results/deep/LEADERBOARD_DEEP.md` — current leaderboard
- `configs/deep_topics/XXXX_*.yaml` — topic configs for golden scraper

## Running Experiments on westd

```bash
# SSH
ssh westd

# Enter WSL
wsl -d Ubuntu

# All services must be running:
# docker containers: kiwix, webarena_reddit, webarena_shopping
# ds_proxy: schtask DsProxy (port 8088)
# shim: schtask ShimDaemon (port 8081)

# Run one agent on one task
cd /opt/deep_reserch
.venv-camel/bin/python3 scripts/run_deep_task.py \
    --agent camel-ai --task dr_cross_deep_0001 \
    --backbone deepseek-v4-flash --out-suffix matrix

# Score
.venv-camel/bin/python3 scripts/score_deep_answer.py \
    --task dr_cross_deep_0001 \
    --answer data/results/deep/camel-ai__dr_cross_deep_0001_matrix.md \
    --out data/results/deep/camel-ai__dr_cross_deep_0001_matrix.score.json

# Rebuild leaderboard
.venv-camel/bin/python3 scripts/build_deep_leaderboard.py
```

## Framework Integration Pattern

Each framework needs: (1) search routed to shim, (2) LLM routed to ds_proxy, (3) no real internet access.

- **In-process agents** (camel-ai, smolagents, gpt-researcher, langchain-odr): monkey-patch tavily client or use framework config to point search at shim. `src/shim_intercept.py` patches requests/httpx/aiohttp at transport layer.
- **Subprocess agents** (deerflow, ldr, ii-researcher, qx-agents): run in their own venv via subprocess. Driver scripts written to `/tmp/` at runtime. Use env vars for config.
- **Clean runner agents** (storm, deerflow, ldr, qx-agents): `scripts/runners/*.py` modules that use framework-native config mechanisms instead of monkey-patching.

## Agent Venvs on westd
- `.venv-camel` — camel-ai + scoring + flowsearcher (main venv)
- `.venv-smol` — smolagents
- `.venv-gptr` — gpt-researcher
- `.venv-storm` — STORM (knowledge_storm)
- `.venv-langchain-odr` — langchain open_deep_research
- `.venv-ldr312` — local-deep-research (Python 3.12)
- `.venv-ii` — ii-researcher
- `.venv-qx` — qx-agents (agents-deep-research)
- `.venv-tongyi` — Tongyi DeepResearch (Alibaba-NLP/DeepResearch)

## Environment Variables
```
DS_PROXY_URL=http://localhost:8088/v1
SHIM_URL=http://localhost:8081
OPENAI_API_KEY=anything  # ds_proxy uses server-side key
JUDGE_BASE_URL=http://localhost:8088/v1
JUDGE_MODEL=deepseek-v4-flash
SHOPPING=http://localhost:7770
REDDIT=http://localhost:9999
WIKIPEDIA=http://localhost:8090
```

## Constraints
- All LLM judge/NLI calls MUST use DeepSeek V4 flash non-reasoning (via ds_proxy)
- Each deep task MUST have ≥120 must-cite URLs across 3 sandbox sources
- DO NOT touch proxy/network/Mihomo config on westd
- For long-running commands on westd, use schtasks (SSH drops after ~5 min)
