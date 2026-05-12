# Deep-Tier Leaderboard — V1 (12 task × 5 OSS DR agents)

*Built from 150 run-score files in `data/results/deep/*_matrix.score.json`. Backbone = DeepSeek-V4-flash (thinking off via westd ds_proxy:8088). Sandbox = Magento + Postmill + Kiwix on westd. Score files produced by `score_deep_answer.py`.*

## Composite_v2_truthful (multiplicative, primary)

*`composite_v2 = reachability · (0.40·url_coverage + 0.40·judge_pass + 0.20·spec)`. Reachability gate kills any agent with fabricated URLs regardless of fluency. **This is the headline ranking.***

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | camel-ai | **1311.2** | [1240, 1396] ±78 | 104 | 11 | 5 | 120 |
| 2 | smolagents | **1186.9** | [1114, 1272] ±79 | 83 | 24 | 13 | 120 |
| 3 | gpt-researcher | **944.7** | [880, 1012] ±66 | 36 | 52 | 32 | 120 |
| 4 | langchain-odr | **794.6** | [747, 838] ±46 | 3 | 66 | 51 | 120 |
| 5 | storm | **762.7** | [711, 802] ±46 | 0 | 73 | 47 | 120 |

### Rank significance (permutation, N=1000)

| Higher | Lower | Gap (Elo) | p-value | Significant? |
|---|---|---:|---:|---|
| camel-ai | smolagents | 124.3 | 0.046 | ✅ |
| smolagents | gpt-researcher | 242.2 | 0.0 | ✅ |
| gpt-researcher | langchain-odr | 150.1 | 0.016 | ✅ |
| langchain-odr | storm | 31.9 | 0.631 | ❌ |

## Composite_v1 (additive, legacy) — for F6 reversal comparison

*Same quality formula, **without** reachability gate. Used to demonstrate the F6 finding: ranking inverts under truthfulness gate.*

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | gpt-researcher | **1212.3** | [1134, 1304] ±85 | 92 | 22 | 6 | 120 |
| 2 | camel-ai | **1144.1** | [1050, 1247] ±99 | 83 | 32 | 5 | 120 |
| 3 | smolagents | **994.8** | [890, 1074] ±92 | 55 | 63 | 2 | 120 |
| 4 | langchain-odr | **951.3** | [858, 1039] ±91 | 48 | 68 | 4 | 120 |
| 5 | storm | **697.6** | [618, 782] ±82 | 12 | 105 | 3 | 120 |

## Per-pillar Elo

| Agent | chec | quot | reac | spec | url_ |
|---|---:|---:|---:|---:|---:|
| camel-ai | 1093 | 1308 | 1290 | 1205 | 1134 |
| gpt-researcher | 1079 | 835 | 930 | 1171 | 1179 |
| langchain-odr | 947 | 826 | 803 | 1042 | 896 |
| smolagents | 1075 | 1213 | 1216 | 946 | 1068 |
| storm | 806 | 818 | 760 | 636 | 722 |

## Raw composite_v2 by (agent, task)

| Agent | 0001 | 0002 | 0003 | 0004 | 0005 | 0006 | 0007 | 0008 | 0009 | 0010 | 0011 | 0012 | 0013 | 0014 | 0015 | 0016 | 0017 | 0018 | 0019 | 0020 | 0021 | 0022 | 0023 | 0024 | 0025 | 0026 | 0027 | 0028 | 0029 | 0030 | mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| camel-ai | 0.219 | 0.322 | 0.000 | 0.463 | 0.176 | 0.493 | 0.421 | 0.637 | 0.308 | 0.485 | 0.417 | 0.000 | 0.270 | 0.252 | 0.529 | 0.401 | 0.352 | 0.130 | 0.197 | 0.454 | 0.309 | 0.203 | 0.337 | 0.322 | 0.309 | 0.297 | 0.289 | 0.402 | 0.612 | 0.363 | **0.332** |
| gpt-researcher | 0.012 | 0.009 | 0.013 | 0.017 | 0.008 | 0.000 | 0.013 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 0.021 | 0.000 | 0.000 | 0.012 | 0.012 | 0.000 | 0.058 | 0.051 | 0.000 | 0.000 | 0.011 | 0.086 | 0.000 | 0.000 | 0.014 | 0.017 | 0.024 | 0.000 | **0.013** |
| langchain-odr | 0.014 | 0.005 | 0.000 | 0.000 | 0.013 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.010 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.001** |
| smolagents | 0.027 | 0.458 | 0.384 | 0.000 | 0.407 | 0.048 | 0.000 | 0.000 | 0.269 | 0.526 | 0.127 | 0.236 | 0.267 | 0.341 | 0.065 | 0.366 | 0.325 | 0.204 | 0.363 | 0.314 | 0.182 | 0.000 | 0.112 | 0.066 | 0.218 | 0.345 | 0.215 | 0.000 | 0.374 | 0.295 | **0.218** |
| storm | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.000** |

## Raw composite_v1 by (agent, task)

| Agent | 0001 | 0002 | 0003 | 0004 | 0005 | 0006 | 0007 | 0008 | 0009 | 0010 | 0011 | 0012 | 0013 | 0014 | 0015 | 0016 | 0017 | 0018 | 0019 | 0020 | 0021 | 0022 | 0023 | 0024 | 0025 | 0026 | 0027 | 0028 | 0029 | 0030 | mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| camel-ai | 0.219 | 0.478 | 0.425 | 0.502 | 0.176 | 0.538 | 0.443 | 0.691 | 0.388 | 0.559 | 0.577 | 0.133 | 0.411 | 0.252 | 0.545 | 0.406 | 0.352 | 0.353 | 0.197 | 0.507 | 0.309 | 0.597 | 0.342 | 0.645 | 0.349 | 0.317 | 0.304 | 0.408 | 0.620 | 0.371 | **0.414** |
| gpt-researcher | 0.434 | 0.330 | 0.425 | 0.404 | 0.218 | 0.406 | 0.271 | 0.325 | 0.387 | 0.346 | 0.239 | 0.334 | 0.596 | 0.406 | 0.543 | 0.425 | 0.400 | 0.428 | 0.405 | 0.473 | 0.305 | 0.444 | 0.330 | 0.545 | 0.402 | 0.319 | 0.387 | 0.444 | 0.539 | 0.406 | **0.397** |
| langchain-odr | 0.434 | 0.143 | 0.067 | 0.133 | 0.377 | 0.172 | 0.219 | 0.067 | 0.000 | 0.219 | 0.133 | 0.286 | 0.076 | 0.229 | 0.353 | 0.415 | 0.229 | 0.219 | 0.267 | 0.276 | 0.339 | 0.324 | 0.210 | 0.692 | 0.343 | 0.229 | 0.331 | 0.200 | 0.257 | 0.362 | **0.253** |
| smolagents | 0.368 | 0.458 | 0.559 | 0.000 | 0.410 | 0.173 | 0.165 | 0.133 | 0.269 | 0.605 | 0.424 | 0.321 | 0.267 | 0.355 | 0.233 | 0.366 | 0.332 | 0.324 | 0.374 | 0.314 | 0.182 | 0.076 | 0.198 | 0.153 | 0.267 | 0.354 | 0.230 | 0.152 | 0.374 | 0.295 | **0.291** |
| storm | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.076 | 0.324 | 0.019 | 0.381 | 0.038 | 0.019 | 0.038 | 0.095 | 0.400 | 0.038 | 0.019 | 0.000 | 0.038 | 0.019 | 0.133 | 0.038 | 0.400 | 0.400 | **0.083** |

## Inputs

- 150 score files
- 5 agents: camel-ai, gpt-researcher, langchain-odr, smolagents, storm
- 30 tasks: dr_cross_deep_0001, dr_cross_deep_0002, dr_cross_deep_0003, dr_cross_deep_0004, dr_cross_deep_0005, dr_cross_deep_0006, dr_cross_deep_0007, dr_cross_deep_0008, dr_cross_deep_0009, dr_cross_deep_0010, dr_cross_deep_0011, dr_cross_deep_0012, dr_cross_deep_0013, dr_cross_deep_0014, dr_cross_deep_0015, dr_cross_deep_0016, dr_cross_deep_0017, dr_cross_deep_0018, dr_cross_deep_0019, dr_cross_deep_0020, dr_cross_deep_0021, dr_cross_deep_0022, dr_cross_deep_0023, dr_cross_deep_0024, dr_cross_deep_0025, dr_cross_deep_0026, dr_cross_deep_0027, dr_cross_deep_0028, dr_cross_deep_0029, dr_cross_deep_0030
- battles synthesised from composite (tie_eps = 0.005)

## Caveats

1. Battles synthesised from composite, not real LLM-judge head-to-head — see `data/results/audit/HUMAN_URL_AUDIT.md` for human-graded URL truthfulness ground truth (separate axis).
2. claim_nli pillar dropped per 2026-04-27 user decision; quote_match pillar retained as deterministic add-on.
3. Tasks 0001/0002/0005 are Recommendation anchors; tasks 0003/0004/0006-0012 are V1 (Comparison/Debunking/Causal/Timeline/Enumeration) — task type may interact with agent-architecture suitability, see paper §5.
