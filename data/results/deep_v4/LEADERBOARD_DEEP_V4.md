# Deep-Research Leaderboard — composite_v4

Reach-gated 11-dimension composite that adds four new pillars (atomic factuality, intra-document consistency, perspective balance, source diversity) on top of the original v2 verifiers.


* Source: `data/results/deep_v4/*.v4.json`
* Total rows on disk: **44**
* Real (non-degenerate) rows: **26**

## Headline ranking (composite_v4)

| # | Agent | Elo | 95% CI | n | source_div | persp_bal | factual_ex | intl_cons | v2 mean | v4 mean | Δ |
|---|-------|-----|--------|---|------------|-----------|------------|-----------|---------|---------|---|
| 1 | **camel-ai** | 1153 | [1081, 1207] | 3 | 0.691 | 0.011 | 0.787 | 0.983 | 0.432 | 0.536 | 0.104 |
| 2 | **flowsearcher-ds** | 1116 | [1052, 1176] | 2 | 0.730 | 0.033 | 0.820 | 0.967 | 0.300 | 0.465 | 0.165 |
| 3 | **deerflow** | 1042 | [953, 1114] | 6 | 0.542 | 0.130 | 0.638 | 1.000 | 0.118 | 0.335 | 0.217 |
| 4 | **smolagents** | 1003 | [931, 1079] | 3 | 0.324 | 0.678 | 0.413 | 0.972 | 0.158 | 0.300 | 0.142 |
| 5 | **storm** | 1002 | [920, 1079] | 4 | 0.407 | 0.279 | 0.000 | 0.863 | 0.170 | 0.280 | 0.110 |
| 6 | **ii-researcher** | 940 | [877, 1014] | 3 | 0.820 | 0.203 | 0.613 | 0.972 | 0.228 | 0.361 | 0.133 |
| 7 | **langchain-odr** | 877 | [831, 936] | 2 | 0.819 | 0.022 | 0.000 | 1.000 | 0.012 | 0.010 | -0.002 |
| 8 | **gpt-researcher** | 865 | [816, 924] | 3 | 0.810 | 0.122 | 0.040 | 0.913 | 0.015 | 0.012 | -0.004 |

## Adjacent-rank significance (permutation N=1000)

| Higher | Lower | Gap | p-value | α=0.05 |
|--------|-------|-----|---------|--------|
| camel-ai | flowsearcher-ds | 37 | 0.494 | no |
| flowsearcher-ds | deerflow | 75 | 0.177 | no |
| deerflow | smolagents | 38 | 0.525 | no |
| smolagents | storm | 1 | 0.987 | no |
| storm | ii-researcher | 63 | 0.262 | no |
| ii-researcher | langchain-odr | 62 | 0.212 | no |
| langchain-odr | gpt-researcher | 12 | 0.792 | no |

## Top |v4 − v2| rows (where new pillars rewrote the verdict)

Positive Δ = v4 rates higher (multi-perspective / good sourcing despite middling URL coverage). Negative Δ = v4 rates lower (URL-true but factually wrong / one-sided / self-contradicting).

| Agent × Task | v2 | v4 | Δ | sd | pb | fe | ic |
|---|---|---|---|---|---|---|---|
| deerflow × dr_cross_deep_0006 | 0.09 | 0.57 | +0.48 | 0.39 | 0.05 | 1.00 | 1.00 |
| deerflow × dr_cross_deep_0001 | 0.07 | 0.37 | +0.30 | 0.74 | 0.12 | 0.80 | 1.00 |
| ii-researcher × dr_cross_deep_0006 | 0.24 | 0.51 | +0.27 | 0.59 | 0.35 | 0.40 | 0.92 |
| flowsearcher-ds × dr_cross_deep_0010 | 0.23 | 0.50 | +0.27 | 0.65 | 0.03 | 0.84 | 0.97 |
| storm × dr_cross_deep_0006 | 0.11 | 0.29 | +0.18 | 0.43 | 1.00 | 0.00 | 0.50 |
| camel-ai × dr_cross_deep_0010 | 0.23 | 0.41 | +0.17 | 0.81 | 0.00 | 0.72 | 0.95 |
| smolagents × dr_cross_deep_0010 | 0.21 | 0.36 | +0.16 | 0.59 | 0.03 | 0.88 | 0.97 |
| deerflow × dr_cross_deep_0010 | 0.23 | 0.38 | +0.15 | 0.36 | 0.07 | 1.00 | 1.00 |
| deerflow × dr_cross_deep_0002 | 0.05 | 0.20 | +0.15 | 0.58 | 0.10 | 0.50 | 1.00 |
| deerflow × dr_cross_deep_0005 | 0.06 | 0.21 | +0.15 | 0.38 | 0.37 | 0.00 | 1.00 |
| smolagents × dr_cross_deep_0015 | 0.08 | 0.23 | +0.14 | 0.14 | 1.00 | 0.36 | 1.00 |
| smolagents × dr_cross_deep_0005 | 0.18 | 0.31 | +0.13 | 0.25 | 1.00 | 0.00 | 0.94 |
| ii-researcher × dr_cross_deep_0010 | 0.17 | 0.29 | +0.12 | 0.95 | 0.04 | 0.72 | 1.00 |
| storm × dr_cross_deep_0002 | 0.12 | 0.24 | +0.12 | 0.10 | 0.00 | 0.00 | 1.00 |
| storm × dr_cross_deep_0005 | 0.17 | 0.28 | +0.11 | 0.64 | 0.08 | 0.00 | 0.95 |

## Pillar coverage diagnostics

* `source_diversity`: present=44, scored=44, of 44
* `perspective_balance`: present=44, scored=44, of 44
* `factual_exactness`: present=44, scored=44, of 44
* `internal_consistency`: present=44, scored=44, of 44
