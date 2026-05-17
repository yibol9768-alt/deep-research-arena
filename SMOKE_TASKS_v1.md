# Smoke task slice — v1 general-agent adaptation validation

Locked 5-task slice for v1 adaptation smoke matrix. Same 5 task IDs across **all 4 agents** (claude-code, codex, gemini-cli, opencode) so adaptation outcomes are directly comparable.

Total inventory in `/opt/deep_reserch/data/tasks/deep_research/cross_site_deep/`: **100 tasks**, 30 tagged with `domain` + `intent_type`, 70 untagged.

## Selection criteria
- **diverse domain coverage**: 2× Consumer (the bread-and-butter), 1× Finance (history of "junk golden URLs" bug — tests resilience), 1× Education, 1× Science.
- **diverse intent_type**: Market-Intelligence, Debunking, Comparison, Causal (×2 different domains).
- **inherits prior known-hard signal**: `dr_cross_deep_0013` (Finance/Comparison) was in the relevance-filter fix batch per `HANDOFF_2026-05-02.md` §"Golden data fix".

## Locked tasks (v1)

**Revised after surveying `/opt/deep_reserch/data/results/deep_v3/`**: tasks 0001-0005 already have 8-14 specialist agents scored AND claude-code already has scored reports (in `C:/tools/cc_runner/` on my5090). Reusing this slice gives instant head-to-head comparison without re-running specialists.

| Task ID | Domain | Intent type | Specialists already scored | claude-code |
|---|---|---|---|---|
| `dr_cross_deep_0001` | Consumer | Market-Intelligence | 14 (camel-ai, co-storm, deerflow, dzhng, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, local-deep-researcher, qx-agents, smolagents, storm, tongyi-dr) | ✅ 0.581 V3 |
| `dr_cross_deep_0002` | Consumer | (untagged) | 8 (deerflow, flowsearcher-ds, gpt-researcher, langchain-odr, ldr, qx-agents, smolagents, storm) | ✅ 0.723 V3 |
| `dr_cross_deep_0003` | Consumer | Comparison | 9 (+ii-researcher) | ✅ 0.433 V3 |
| `dr_cross_deep_0004` | Consumer | (untagged) | 9 | ✅ 0.713 V3 |
| `dr_cross_deep_0005` | Consumer | Market-Intelligence | 11 (camel-ai, co-storm, ...) | ✅ 0.652 V3 |

## Run protocol

```
for agent in claude-code codex gemini-cli opencode; do
  for task in dr_cross_deep_0001 dr_cross_deep_0006 dr_cross_deep_0013 dr_cross_deep_0023 dr_cross_deep_0030; do
    python3 scripts/run_deep_task.py --agent "$agent" --task "$task" --backbone deepseek-v4-flash
  done
done
```

Smoke timeout cap: **`timeout_s=900`** (15 min) per (agent, task), tighter than the 1800s production default — adaptation validation cares about ✅ "produced a valid report" not ✅ "produced the best report".

Total: 4 agents × 5 tasks = **20 runs**. At ~10-15 min/run with serial scheduling, wallclock 3.3-5h. With 2-way concurrency: 1.7-2.5h.

## Reports go to
- `/opt/deep_reserch/data/results/deep/<agent>__<task>.md`
- `/opt/deep_reserch/data/results/deep/<agent>__<task>.meta.json`
- After scoring: `/opt/deep_reserch/data/results/deep_v3/<agent>__<task>_matrix.score.json`

## Validation criteria
For each (agent, task) pair, runner is ✅ adapted iff:
1. Report file ≥ 500 chars markdown
2. ≥ 3 inline citations `[anchor](sandbox-url)`
3. ≥ 50% of cited URLs reachable via HEAD against the sandbox
4. No crash / no timeout (or graceful timeout diagnostic per `claudecode_runner.py:267-274` pattern)
5. tcpdump on the run shows zero packets to `api.openai.com` / `api.anthropic.com` / `generativelanguage.googleapis.com`

Agent passes overall iff ≥ 4 of 5 task runs satisfy all 5 criteria.

## v1.5 backlog
- `aider` (needs `pip install aider-chat` in WSL or a venv)
- `goose` (Block, needs installer in WSL)
- `crush` (Charm, needs `go install`)
- Stretch: `openhands` (Docker)
