# Repository Structure and Work Ownership

Generated: 2026-06-03

## Purpose

This repository should stay organized around one benchmark and training
pipeline. New work must extend the existing Deep Research Arena stack instead
of creating another harness.

## Top-level map

| Path | Role | Ownership rule |
| ---- | ---- | -------------- |
| `scripts/` | command-line entry points | thin wrappers around `src/` and `integrations/` |
| `scripts/runners/` | benchmark agent runners | one file per agent integration pattern |
| `integrations/agents/` | agent adapters and registry | expose runnable agents to `run_deep_task.py` |
| `integrations/search_shim/` | sandbox search compatibility layer | Tavily-like closed-world search |
| `integrations/mcp_server/` | MCP exposure | tool serving, not scoring logic |
| `src/eval/` | evaluator orchestration | compose verifiers into rewards or acceptance results |
| `src/verifiers/` | single-purpose checks | evidence, citation, report, state, and formatting verifiers |
| `src/scoring/` | composite formulas and ranking math | named formulas only, no duplicated script-local formulas |
| `src/rl/` | AgentRL environment and tools | train-time actions, policies, reward adapters |
| `data/tasks/deep_research/` | task definitions | benchmark, pilot, and RL task specs |
| `data/golden/` | golden evidence and labels | URL pools, state targets, expected facts, human labels |
| `data/results/` | generated benchmark outputs | run outputs and score JSON, not source logic |
| `docs/` | research and operational decisions | plans, protocols, delivery specs, route maps |
| `frontend/` | public site source | only touch during explicit site work |
| `web/` | Cloudflare publish artifact | do not edit unless releasing |

## Evaluation layers

| Layer | Entry point | Output | Purpose |
| ----- | ----------- | ------ | ------- |
| V2 public leaderboard | `scripts/run_deep_task.py` -> `scripts/score_deep_answer.py` -> `scripts/build_deep_leaderboard.py` | `data/results/deep_v3/leaderboard_deep.json` | headline truthfulness-gated ranking |
| V3-RL reward | `src/eval/evaluator.py::ArenaEvaluator.evaluate_rollout` | rollout reward and diagnostics | smooth train-time signal for AgentRL |
| FullEval | `src/eval/full_report_evaluator.py` | full-report acceptance JSON | user-facing long-report validity |

These layers may share verifier outputs, but they must not share acceptance
semantics. A report can be useful for train-time reward while still failing
user-facing FullEval.

## Mainline acquisition paths

| Agent or modality | Files | Notes |
| ----------------- | ----- | ----- |
| search shim agents | `scripts/run_deep_task.py`, existing runner registry | standard closed-world search and fetch |
| browser-driven agent | `integrations/agents/browser_dr/`, `scripts/runners/browser_dr_runner.py` | real browser navigation integrated as an agent |
| RAG tools | `src/rl/tools_rag.py`, `scripts/build_rag_index.py` | dense dependencies stay optional |
| SQL tools | `src/rl/tools_sql.py` | read-only, allowlisted, environment-configured |
| crawl tools | `src/rl/tools_crawl.py` | sandbox-local crawling only |
| vision tools | `src/rl/tools_vision.py` | captioner injected through `ctx.extras` |
| write tools | `src/rl/tools_write.py`, `src/verifiers/state_diff_verifier.py` | mock store now, resettable sandbox DB later |

## What not to recreate

Do not recreate these removed paths:

```text
src/dr_harness/
scripts/dr_harness.py
data/runs/
data/tasks/deep_research/browser_click_debug/
data/tasks/deep_research/browser_click_core/
```

The same goals belong in existing locations:

```text
browser interaction -> scripts/runners/browser_dr_runner.py
run scoring -> scripts/score_deep_answer.py or src/eval/evaluator.py
public ranking -> scripts/build_deep_leaderboard.py
full report acceptance -> src/eval/full_report_evaluator.py
demo artifacts -> data/results/ or frontend demo data during release work
```

## Multi-agent work split

When multiple agents work in parallel, split by ownership boundary:

| Agent lane | Files it may touch | Deliverable |
| ---------- | ------------------ | ----------- |
| Evaluation lead | `src/eval/`, `src/verifiers/`, `tests/test_*eval*`, `tests/test_*verifier*` | FullEval and reward correctness |
| Acquisition lead | `integrations/agents/`, `scripts/runners/`, browser tests | real website access and trace quality |
| Task lead | `data/tasks/deep_research/`, `data/golden/`, task docs | benchmark task specs and labels |
| Training lead | `src/rl/`, `scripts/train_grpo_pilot.py`, RL tests | AgentRL environment and reward plumbing |
| Documentation lead | `docs/`, selected README updates | route maps, protocols, handoff docs |

Cross-lane changes should be reviewed against `docs/EVAL_REPO_CLEANUP.md`
before they are staged.

## Immediate cleanup checklist

Keep the repository clean by checking:

```text
no __pycache__ directories
no *.pyc files
no .pytest_cache directories
no second harness entry point
no generated website changes unless publishing
no data/changelog.json changes unless publishing
```

Recommended checks:

```bash
find . -name '*.pyc' -o -name '__pycache__' -o -name '.pytest_cache'
rg -n "src/dr_harness|scripts/dr_harness.py|browser_click_debug|browser_click_core" docs src scripts tests data
git status --short
```
