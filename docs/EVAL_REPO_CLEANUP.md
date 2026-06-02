# Evaluation Repository Cleanup

Generated: 2026-06-03

## Purpose

This note records the evaluation cleanup decision so future work does not
recreate a second harness or confuse the V2, V3-RL, and FullEval layers.

## Canonical layers

### V2 public leaderboard

Purpose: public truthfulness-gated benchmark ranking.

Main files:

```text
scripts/run_deep_task.py
scripts/score_deep_answer.py
scripts/build_deep_leaderboard.py
src/scoring/leaderboard_composites.py::composite_v2_truthful
data/results/deep_v3/leaderboard_deep.json
```

Use this when the question is:

```text
Which agent wins the public benchmark under the citation truthfulness gate?
```

Important detail:

```text
scripts/score_deep_answer.py writes several per-run composites, including a
truthfulness-factored score with quote and NLI signals. The headline public
leaderboard is still recomputed by scripts/build_deep_leaderboard.py with
composite_v2_truthful = reachability * quality.
```

### V3-RL reward

Purpose: smooth, cheap reward for AgentRL and periodic diagnostic ranking.

Main files:

```text
src/eval/evaluator.py::ArenaEvaluator
src/scoring/leaderboard_composites.py::composite_v3_softfloor
src/scoring/leaderboard_composites.py::composite_v3_rl
scripts/build_deep_leaderboard_v3.py
docs/SCORING_V3_DIFF.md
```

Use this when the question is:

```text
How do we provide a nonzero training signal while preserving evidence quality?
```

Important detail:

```text
scripts/build_deep_leaderboard_v3.py is schema-only and dry-run in this local
worktree. The --real path is not implemented here because real verifier runs
belong on the benchmark host with the sandbox services available.
```

### FullEval

Purpose: user-facing long-form report acceptance.

Planned files:

```text
src/eval/full_report_evaluator.py
src/verifiers/atomic_claims.py
src/verifiers/atomic_claim_support_verifier.py
src/verifiers/task_aspect_coverage_verifier.py
src/verifiers/evidence_synthesis_verifier.py
src/verifiers/uncertainty_calibration_verifier.py
scripts/evaluate_full_report.py
docs/FULL_REPORT_EVAL_AGENTRL_ROADMAP.md
```

Use this when the question is:

```text
Can a user trust this long report as complete, factual, analytical, and useful?
```

## Historical code to treat carefully

`src/scoring/composite_v3.py` is an earlier V3-style composite with pillars:

```text
markdown_structure
citation
fact_kg
llm_judge
checklist
efficiency
```

It contains useful ideas, especially `fact_kg`, but it is not the current
AgentRL reward entry point. Do not route new training code through it unless it
is deliberately refactored into FullEval.

The name `V3` currently appears in three different senses:

```text
src/scoring/leaderboard_composites.py::composite_v3
  legacy 7-dimension floor-0.1 composite

src/scoring/leaderboard_composites.py::composite_v3_softfloor
  Workstream A smooth soft-floor composite

src/scoring/composite_v3.py::score
  older KG/full-report scorer exported as src.scoring.score_v3
```

Do not use the short name `V3` in new docs without saying which one is meant.

## Cleanup performed

Removed the parallel harness experiment:

```text
src/dr_harness/
scripts/dr_harness.py
tests/test_dr_harness_*.py
data/runs/
data/tasks/deep_research/browser_click_debug/
data/tasks/deep_research/browser_click_core/
docs/DR_HARNESS_EVAL_PLAN.md
docs/EXPERIMENT_MATRIX.md
docs/HUMAN_AUDIT_PROTOCOL.md
docs/templates/DR_RUN_SCHEMA.md
```

Reason:

```text
The project should extend the existing run_deep_task, score_deep_answer, and
leaderboard pipeline. Browser acquisition is already integrated as
scripts/runners/browser_dr_runner.py and should not live in a separate scoring
harness.
```

Removed generated cache artifacts:

```text
__pycache__/
*.pyc
.pytest_cache/
```

## Current mainline additions to keep

Keep these as part of the non-GPU AgentRL and acquisition work:

```text
src/rl/backends.py
src/rl/tools.py
src/rl/tools_rag.py
src/rl/tools_sql.py
src/rl/tools_crawl.py
src/rl/tools_exec.py
src/rl/tools_vision.py
src/rl/tools_write.py
src/rl/user_sim.py
src/verifiers/state_diff_verifier.py
integrations/agents/browser_dr/
scripts/runners/browser_dr_runner.py
scripts/build_rag_index.py
scripts/train_grpo_pilot.py
scripts/check_track_a_local.sh
tests/test_browser_dr_runner.py
tests/test_modality_parity.py
tests/test_tool_registry.py
tests/test_tools_*.py
```

These are not a parallel harness. They extend the existing env, tool registry,
agent registry, and training path.

## Directory ownership

Use this ownership map when adding new files:

| Directory | Owner concept | Add here when |
| --------- | ------------- | ------------- |
| `scripts/runners/` | agent runner adapters | adding a new benchmark agent entry point |
| `integrations/agents/` | agent registry and adapter packages | exposing an agent to `run_deep_task.py` |
| `src/eval/` | evaluator orchestration and rollout scoring | composing verifier outputs into rewards or report evals |
| `src/verifiers/` | single-purpose metrics | adding a reusable evidence, citation, report, or state check |
| `src/scoring/` | composite formulas and ranking math | adding a named score formula shared by scripts |
| `src/rl/` | train-time environment, tools, and policies | adding AgentRL execution or tool-use behavior |
| `data/tasks/deep_research/` | benchmark tasks | adding task specs, RL tasks, or full-report specs |
| `data/golden/` | task evidence and labels | adding golden URL pools, state specs, or labels |
| `docs/` | research and operation docs | documenting decisions and protocols |
| `frontend/` and `web/` | publication surfaces | only when doing an explicit site release |

Generated run outputs should stay under `data/results/` or local ignored
workspace paths. Do not create another top-level run harness directory.

## Files to label before future cleanup

Treat these as analysis or legacy unless a future task deliberately promotes
them:

```text
scripts/review_analyses.py
scripts/review_analyses_v3.py
scripts/scoring_ablation.py
scripts/multi_judge_slice.py
scripts/rescore_partial.py
scripts/rescore_ad_only.py
scripts/diagnostics/rerun_failed_judges.py
scripts/bench_v3.py
scripts/rescore_all_with_deepseek.py
scripts/build_final_leaderboard.py
src/scoring/composite_v3.py
```

They are useful for reproducing older analyses, but new production entry
points should use the three canonical layers above.

## Rule for future evaluation work

Before adding a new evaluation script, ask which layer it belongs to:

```text
V2 public leaderboard
V3-RL reward
FullEval user acceptance
```

If the answer is "another harness", stop and adapt it to one of the three
layers above.

Also do not resurrect:

```text
src/dr_harness/
scripts/dr_harness.py
data/runs/
data/tasks/deep_research/browser_click_debug/
data/tasks/deep_research/browser_click_core/
```

Browser acquisition belongs in `scripts/runners/browser_dr_runner.py` and
future full-report acceptance belongs in `src/eval/full_report_evaluator.py`.
