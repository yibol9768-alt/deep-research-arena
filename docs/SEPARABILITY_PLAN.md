# Top-Player Separability Plan

**Owner**: Workstream B (separability).
**Created**: 2026-05-21.
**Current**: 62.86% pairwise CI-separability on the v2/v3 30-task pool
(105 agent pairs, 66 non-overlapping). See
`docs/SEPARABILITY_REPORT.md` for the per-pair breakdown.
**Target**: >= 65% (intermediate) -> 87% (Arena-Hard parity).

## 1. Why the top players cluster

Three compounding causes on the 30-task v2 leaderboard:

1. **Small task pool** — 30 tasks puts the bootstrap Elo CI half-width at
   ~60-95 Elo for top agents (camel-ai +-75, smolagents +-90,
   ii-researcher +-93). The rank-1 vs rank-2 gap (102 Elo claude-code vs
   opencode) is dwarfed by either agent's CI.
2. **Composite saturation** — every top agent scores >= 1130 on every
   pillar (checklist / quote_match / reachability / spec / url_coverage).
   There is no headroom for a "good" agent to pull away from a "great"
   one because the v2 composite caps out.
3. **Pillar correlation** — `reachability` and `quote_match` correlate
   at Spearman rho=0.91. Two near-redundant pillars contribute only one
   pillar's worth of discrimination.

The Arena-Hard paper (Li et al. 2024) shows that benchmark separability
is gated by **prompt difficulty / discriminability**, not by judge
quality. MT-Bench's 22.6% separability is bottlenecked by its prompts;
Arena-Hard's 87.4% comes from BenchBuilder pre-filtering.

## 2. Three levers, three expected gains

| Lever | Deliverable | Expected delta on separability | Risk |
|---|---|---:|---|
| **Adversarial tasks (v2)** | 20 specs in `configs/deep_topics/V2_ADVERSARIAL_TASKS.json` + emitted task JSONs under `data/tasks/deep_research/cross_site_deep_v2/` | +10 to +18 pp | Tasks may not actually discriminate -> pre-screen pilot in section 3 mitigates |
| **Top-pair densification** | `scripts/run_pairwise_battles.py --strategy top-pair-densify --top-n 3 --n-per-pair N` | +5 to +10 pp (mostly tightens CIs in the top cluster) | Single-judge variance still applies; pair with dual-judge protocol |
| **Composite v3 dynamic range** | Workstream A's v3 composite + new pillars (depth / rigor / style verifiers) | +5 to +10 pp | Owned by Workstream A; we depend on their pillar uncorrelatedness |

Stacked, the three levers should clear 65% comfortably and push toward
80%. The plan is to ship them in sequence, measure after each, and stop
when the increment per additional task plateaus.

## 3. Validation protocol

### 3.1 Pre-screen pilot (before any full-matrix run)

Per `V1_TASK_DESIGN_GRID.md` section 5.4: 3 agents x 5 tasks per family
= 45 runs total on westd. Pick **one expected winner**, **one middle**,
**one loser** per family. Score with v2_truthful. Keep tasks whose
3-agent score variance is in the top 50% of candidates; drop the rest.
Approx 4-5 survivors per family => 12-15 promoted tasks total.

### 3.2 Promotion criterion

A v2 task is promoted into the leaderboard pool iff:
- Variance across the 3 pilot agents > median(candidate variance), AND
- At least one pilot pair has its v2_truthful gap >= 0.15 (vs <= 0.05 in
  the v1 saturation regime).

### 3.3 Full-matrix run

After promotion, run the surviving v2 tasks across all 13 agents
(160-200 new task-agent runs). This roughly doubles the pool, halving
the bootstrap CI half-widths in the bottom and middle clusters. The top
cluster also tightens but more slowly.

### 3.4 Top-pair densification

Concurrent with the v2 full-matrix run, target the top 3 agents with
`run_pairwise_battles.py --strategy top-pair-densify --n-per-pair 20`.
This adds 60 dual-judge battles inside the top cluster — the only
region where Elo CI tightening still matters at this stage.

### 3.5 Re-measure

After each milestone, run `scripts/report_separability.py`. The
acceptance criterion for promoting v2 to the public site is the
separability % crossing 65% AND the rank-1 vs rank-2 permutation p-value
dropping below 0.05.

## 4. Failure modes and rollback

- **v2 tasks don't discriminate**: pre-screen catches this. We drop the
  task and don't promote.
- **v2 tasks flip the leaderboard in unexpected directions**: report the
  flip, do not retro-edit specs. Pre-registration is exactly to keep us
  honest here.
- **Top-pair densification creates a single-judge artefact**: every
  densified battle MUST use both judges in the dual-family protocol
  (DeepSeek judges GLM and vice versa). Self-judging is excluded.
- **Composite v3 changes the leaderboard out from under us**: that is
  Workstream A's call and they own the cutover; we read whatever
  composite the published leaderboard uses.

## 5. Open questions for the parent session

1. **Pool budget**: the pre-screen pilot is 45 westd runs; promoting v2
   adds another 160-200. Confirm the total westd compute budget can
   absorb ~250 fresh runs on top of the existing 30-task baseline.
2. **Anchor preservation**: v1 anchor tasks (0001, 0002, 0005) are
   designed as Recommendation-pattern controls. Should they remain in
   the leaderboard composite alongside the v2 adversarial tasks, or
   should we publish a v2-only board separately? Recommend the former
   for continuity.
3. **Composite weighting**: when both v1 (30 tasks) and v2 (12-15 tasks)
   contribute to a single Elo, do we weight by task count or by family?
   Workstream A's composite v3 work should anchor this.
