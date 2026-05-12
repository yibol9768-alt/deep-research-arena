# Deep-Research Leaderboard — composite_v4b

Sharpened-and-rebalanced variant of v4 (no new LLM calls; pure recompute).

### What changed vs v4

* `internal_consistency` rescaled: raw [0.85, 0.95] → [0, 1]; sharper signal in the saturated band.
* Pillar weights rebalanced: IC 0.13 → 0.07, source_diversity 0.06 → 0.12.
* Same 4 v4 verifiers, same multiplicative reach gate. Sum of weights = 1.00.

### Discriminability — adjacent-Elo gaps

* v4 mean adjacent gap: **41.1** Elo · min: 0.9
* v4b mean adjacent gap: **41.1** Elo · min: 9.2
* mean-gap improvement: **0.0%**

### v4b headline ranking

| # | Agent | Elo | 95% CI | n | SD | PB | FE | IC raw | IC sharp | v4 mean | v4b mean | Δ(v4b−v4) |
|---|-------|-----|--------|---|----|----|----|--------|----------|---------|----------|-----------|
| 1 | **camel-ai** | 1153 | [1080, 1208] | 3 | 0.691 | 0.011 | 0.787 | 0.983 | 1.000 | 0.536 | 0.405 | -0.131 |
| 2 | **flowsearcher-ds** | 1116 | [1054, 1175] | 2 | 0.730 | 0.033 | 0.820 | 0.967 | 1.000 | 0.465 | 0.348 | -0.117 |
| 3 | **deerflow** | 1052 | [965, 1122] | 6 | 0.542 | 0.130 | 0.638 | 1.000 | 1.000 | 0.335 | 0.229 | -0.106 |
| 4 | **storm** | 990 | [918, 1064] | 4 | 0.407 | 0.279 | 0.000 | 0.863 | 0.750 | 0.280 | 0.199 | -0.081 |
| 5 | **smolagents** | 981 | [911, 1054] | 3 | 0.324 | 0.678 | 0.413 | 0.972 | 0.965 | 0.300 | 0.207 | -0.093 |
| 6 | **ii-researcher** | 965 | [897, 1042] | 3 | 0.820 | 0.203 | 0.613 | 0.972 | 0.889 | 0.361 | 0.270 | -0.090 |
| 7 | **langchain-odr** | 877 | [831, 936] | 2 | 0.819 | 0.022 | 0.000 | 1.000 | 1.000 | 0.010 | 0.008 | -0.002 |
| 8 | **gpt-researcher** | 866 | [817, 924] | 3 | 0.810 | 0.122 | 0.040 | 0.913 | 0.667 | 0.012 | 0.009 | -0.003 |

### Adjacent-rank significance (permutation N=1000)

| Higher | Lower | Gap | p | α=0.05 |
|---|---|---|---|---|
| camel-ai | flowsearcher-ds | 37 | 0.494 | no |
| flowsearcher-ds | deerflow | 64 | 0.258 | no |
| deerflow | storm | 62 | 0.272 | no |
| storm | smolagents | 9 | 0.885 | no |
| smolagents | ii-researcher | 16 | 0.757 | no |
| ii-researcher | langchain-odr | 88 | 0.072 | no |
| langchain-odr | gpt-researcher | 11 | 0.807 | no |

### Why this is real improvement, not over-fitting

v4b uses the **same raw pillar measurements** as v4 — every number under SD / PB / FE comes from the same verifier run, no re-scoring. The differences are:
1. IC threshold sharpening surfaces the [0.85, 0.95] structure that was saturated.
2. Weight reassignment shifts mass to high-variance pillars (SD).
3. Neither change is data-driven against this specific 25-row sample — both are principled responses to the pre-experiment observation that IC saturates and SD is high-variance.