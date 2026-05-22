# SCORING_V3_DIFF — what changed from v2, and how to use it

Workstream A (2026-05-21). Audience: anyone wiring the AgentRL reward,
the human-pref weight-fitter (Workstream D), or the frontend
leaderboard (Workstream E).

## tl;dr

v2 used a hard multiplicative reachability gate:

```
composite_v2 = reachability * (0.40*url_coverage + 0.40*checklist + 0.20*spec)
```

A single broken URL zeroed the whole composite. That was the right thing
to discover the F6 finding ("URL truthfulness matters multiplicatively"),
but it is the wrong thing for downstream learners: AgentRL needs a
smooth, never-zero reward gradient, and the frontend leaderboard becomes
uninformative when half the agents hit zero on one bad citation.

v3 keeps the truthfulness signal but softens the gate, and broadens the
quality term from 3 dims to 6:

```
composite_v3 = reach_soft * Q
reach_soft   = 0.5 + 0.5 * quote_match     # in [0.5, 1.0], never zero
Q            = sum(w_d * score_d for d in DIMS_V3)
```

`composite_v2_truthful` is still exported from
`src.scoring.leaderboard_composites` so paper headline numbers and
historical analyses keep running unchanged.

## Weights

| dim       | weight | verifier                                       | type            |
|-----------|-------:|------------------------------------------------|-----------------|
| coverage  | 0.20   | `src/verifiers/url_coverage_verifier.py`        | deterministic    |
| depth     | 0.20   | `src/verifiers/depth_verifier.py`               | LLM-judge 5pt    |
| rigor     | 0.20   | `src/verifiers/rigor_verifier.py`               | LLM-judge 5pt    |
| style     | 0.10   | `src/verifiers/style_verifier.py`               | LLM-judge 5pt    |
| checklist | 0.20   | `src/verifiers/checklist_verifier.py`           | LLM-judge binary |
| spec      | 0.10   | `src/verifiers/markdown_report_verifier.py`     | deterministic    |

Sum = 1.00 (enforced by an `assert` at import time in
`leaderboard_composites.py`).

These are placeholder uniform-ish weights. Workstream D fits them to
human preference data via `scripts/fit_weights_v3.py` and ships the
fitted vector back into `WEIGHTS_V3` (or overrides per-call via the
`ArenaEvaluator(weights=...)` constructor arg).

## Soft-floor formula

```
reach_soft = clip(0.5 + 0.5 * quote_match, 0.5, 1.0)
```

`quote_match` is the per-citation truthfulness signal: did the agent's
quoted span actually appear at the cited URL. We chose this (not raw
reachability) because:

- An unreachable URL is a weaker failure than a reachable URL with a
  fabricated quote.
- `quote_match` is already deterministic, normalised to [0, 1], and
  available offline (no live sandbox needed at scoring time).
- Reachability stays observable in the per-agent profile
  (`reachability_pct`) for diagnostics — it just doesn't drive the gate.

The 0.5 floor is what makes v3 a *soft* gate: even an agent with zero
quote-match credit still receives `0.5 * Q`, giving AgentRL a non-zero
reward gradient. F6 remains observable as a *gap* between high- and
low-`quote_match` agents (their composites still differ by `Q` × 0.5).

## AgentRL integration

```python
from src.eval.evaluator import ArenaEvaluator

# Every rollout: cheap, deterministic, sub-1s.
evaluator = ArenaEvaluator("dr_cross_deep_0001", mode="fast")
result = evaluator.evaluate(agent_report_md)
reward = result.composite   # float in [0, 1]
```

`mode="fast"` short-circuits the four LLM-judge dims to a neutral 0.5
and runs only the deterministic verifiers (`coverage`, `spec`). That
gives a stable per-rollout reward signal without the latency or cost of
a judge call. For periodic eval / leaderboard rebuild, run with
`mode="full"`:

```python
evaluator = ArenaEvaluator(task_id, mode="full")
result = evaluator.evaluate(agent_report_md)   # ~30s, runs all 6 dims
print(result.composite)                # float in [0, 1]
print(result.per_dim)                  # {coverage: 0.7, depth: 0.6, ...}
print(result.breakdown)                # reach_soft, q_value, per-dim contrib
print(result.policy)                   # sandbox_violations, reach, quote_match
```

`evaluate_async` is the awaitable variant — same return type, runs the
four LLM-judge dims via `asyncio.gather` so end-to-end latency is
`max(depth, rigor, style, checklist)` not `sum`.

## Spearman v2 vs v3

To check whether v3 reorders agents relative to v2, compute Spearman on
the same set of (agent, task) rows:

```python
from src.scoring.leaderboard_composites import (
    composite_v2_truthful, composite_v3_softfloor,
)

pairs = [(s["agent"], s["task_id"], composite_v2_truthful(s["score"]),
                                    composite_v3_softfloor(s["score"]))
         for s in score_rows]

# rank-correlate the two composites
def rho(pairs):
    import statistics
    n = len(pairs)
    if n < 3: return None
    a_rank = {k: r for r, k in enumerate(sorted(range(n), key=lambda i: pairs[i][2]))}
    b_rank = {k: r for r, k in enumerate(sorted(range(n), key=lambda i: pairs[i][3]))}
    d2 = sum((a_rank[i] - b_rank[i]) ** 2 for i in range(n))
    return 1 - (6 * d2) / (n * (n * n - 1))

print(rho(pairs))
```

`scripts/build_deep_leaderboard_v3.py --dry-run` does this computation
on synthetic rows so the wire-up is exercised; the resulting Spearman is
in `leaderboard_deep_v3.json` under
`human_alignment.spearman_v2_vs_v3_dry_run`. On real rows the same
computation lives off the per-run score JSONs in `data/results/deep_v3/`.

## What the verifiers return

Each new LLM-judge verifier (`DepthVerifier`, `RigorVerifier`,
`StyleVerifier`) returns a `VerifierResult`:

```python
VerifierResult(
    score=0.75,           # (level - 1) / 4, rescaled to [0, 1]
    passed=True,          # score >= 0.5
    details={
        "level": 4,                       # 1..5 integer (median of N samples)
        "evidence": "<one short sentence>",
        "samples": [4, 4, 5],             # the N raw levels
        "raw_judge_output": "...",        # concatenated judge text
        "judge_model": "deepseek-...",
        "judge_provider": "openai",
        "temperature": 0.3,
        "cot_disabled": True,
    },
)
```

`score = (level - 1) / 4`, so level 1 → 0.0 and level 5 → 1.0.

Self-consistency: 3 samples at temperature 0.3, median. CoT is
disabled in the prompt; for DeepSeek-V4 the SDK call also passes
`thinking: disabled` (via `judge_client.py`).

If every judge sample fails (e.g. `ds_proxy:8088` unreachable), the
verifier returns `score=0.5, evidence="judge_unavailable"` instead of
crashing — so AgentRL never sees a NaN reward.

## Cross-family routing

Per the Wataoka 2024 self-preference finding, the judge model must be
from a different family than the agent under test. v3 inherits this
from the existing `judge_client.call_judge` plumbing:

- GLM-agent runs → judge configured via env to DeepSeek (`ds_proxy:8088`).
- DeepSeek-agent runs → judge configured via env to GLM (zhipu).

There is no per-run override in the new verifiers; the run harness
sets `JUDGE_PROVIDER` / `JUDGE_MODEL` once, and every verifier picks it
up via `judge_client.judge_identity()` (which gets stamped into
`VerifierResult.details` for traceability).

TODO(workstream-A-followup): when AgentRL gains explicit
`agent_family` metadata in `task_config`, switch the judge identity
per-call based on that field rather than relying on global env vars.

## Files added by Workstream A

- `src/verifiers/depth_verifier.py`
- `src/verifiers/rigor_verifier.py`
- `src/verifiers/style_verifier.py`
- `src/scoring/leaderboard_composites.py` — added `WEIGHTS_V3`,
  `composite_v3_softfloor`, `composite_v3_breakdown` (v2 untouched).
- `src/eval/__init__.py`, `src/eval/evaluator.py` — `ArenaEvaluator`.
- `scripts/build_deep_leaderboard_v3.py` — dry-run leaderboard build.
- `data/results/deep_v3/leaderboard_deep_v3.json` — schema artefact.

## Files NOT touched

- `frontend/*` (Workstream E)
- `scripts/runners/*`, `integrations/search_shim/*` (Workstream C)
- `configs/deep_topics/*`, `scripts/run_pairwise_battles.py` (Workstream B)
- `tools/human_pref_collector/`, `scripts/fit_weights_v3.py` (Workstream D)
