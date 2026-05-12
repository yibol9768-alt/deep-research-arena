# v4 Verifier Run Report

Sample size: 19 runs across 8 agents.

v4 composite weights:

```
  url_coverage               0.1
  spec                       0.05
  checklist                  0.1
  citation_alignment         0.1
  quote_match                0.05
  factual_exactness          0.13
  internal_consistency       0.13
  perspective_balance        0.08
  source_diversity           0.06
  analysis_depth             0.1
  presentation               0.1
```

## Per-agent mean scores

| Agent | n | v2 mean | v4 mean | Δ (v4-v2) | source_div | persp_bal | factual_ex | intl_cons |
|-------|---|---------|---------|-----------|------------|-----------|------------|-----------|
| ii-researcher | 1 | 0.237 | 0.505 | 0.268 | 0.590 | 0.350 | 0.400 | 0.917 |
| deerflow | 3 | 0.114 | 0.347 | 0.234 | 0.591 | 0.072 | 0.676 | 1.000 |
| storm | 2 | 0.119 | 0.267 | 0.148 | 0.262 | 0.500 | 0.000 | 0.750 |
| smolagents | 3 | 0.027 | 0.075 | 0.048 | 0.045 | 1.000 | 0.159 | 1.000 |
| gpt-researcher | 2 | 0.007 | 0.006 | -0.001 | 0.756 | 0.025 | 0.060 | 0.950 |
| flowsearcher-ds | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| ldr | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.333 | 0.300 | 1.000 |
| langchain-odr | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.133 | 0.000 | 0.667 |

## v2 vs v4 rank changes

| Agent | v2 rank | v4 rank | Δ |
|-------|---------|---------|---|
| deerflow | 3 | 2 | +1 |
| storm | 2 | 3 | -1 |
| flowsearcher-ds | 6 | 6 | 0 |
| smolagents | 4 | 4 | 0 |
| ldr | 7 | 7 | 0 |
| gpt-researcher | 5 | 5 | 0 |
| ii-researcher | 1 | 1 | 0 |
| langchain-odr | 8 | 8 | 0 |

## Where v4 disagrees most with v2 (top |Δ| at row level)

These rows are where the v4 composite differs most from v2 on the same report. Positive Δ means v4 rates higher than v2 (likely the report has good multi-perspective / diverse sourcing despite middling URL coverage); negative Δ means v4 rates lower (likely URL-true but factually wrong / one-sided / self-contradicting).

| Agent × Task | v2 | v4 | Δ | sd | pb | fe | ic |
|---|---|---|---|---|---|---|---|
| deerflow × dr_cross_deep_0006 | 0.09 | 0.57 | +0.48 | 0.39 | 0.05 | 1.00 | 1.00 |
| ii-researcher × dr_cross_deep_0006 | 0.24 | 0.51 | +0.27 | 0.59 | 0.35 | 0.40 | 0.92 |
| storm × dr_cross_deep_0006 | 0.11 | 0.29 | +0.18 | 0.43 | 1.00 | 0.00 | 0.50 |
| deerflow × dr_cross_deep_0002 | 0.05 | 0.20 | +0.15 | 0.58 | 0.10 | 0.50 | 1.00 |
| smolagents × dr_cross_deep_0015 | 0.08 | 0.23 | +0.14 | 0.14 | 1.00 | 0.36 | 1.00 |
| storm × dr_cross_deep_0002 | 0.12 | 0.24 | +0.12 | 0.10 | 0.00 | 0.00 | 1.00 |
| deerflow × dr_cross_deep_0015 | 0.20 | 0.27 | +0.07 | 0.80 | 0.07 | 0.53 | 1.00 |
| gpt-researcher × dr_cross_deep_0002 | 0.01 | 0.01 | -0.00 | 0.68 | 0.05 | 0.12 | 1.00 |
| flowsearcher-ds × dr_cross_deep_0002 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| flowsearcher-ds × dr_cross_deep_0015 | 0.00 | 0.00 | +0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| smolagents × dr_cross_deep_0002 | 0.00 | 0.00 | +0.00 | 0.00 | 1.00 | 0.00 | 1.00 |
| smolagents × dr_cross_deep_0006 | 0.00 | 0.00 | +0.00 | 0.00 | 1.00 | 0.12 | 1.00 |

## Verdict — does v4 actually distinguish good DR from bad?

* v2 leader: **ii-researcher** | v4 leader: **ii-researcher** (same).
* v2 tail: **langchain-odr** | v4 tail: **langchain-odr** (same).
* 0 agent(s) moved by ≥ 2 ranks between v2 and v4: (none).

## Pillar coverage diagnostics

* source_diversity   covered: 19 / 19
* perspective_balance covered: 19 / 19
* factual_exactness   covered: 19 / 19
* internal_consistency covered: 19 / 19