# Top-Player Separability Report

- **Source**: `/root/Desktop/lyb/deep_reserch-wt-separability/data/results/deep_v3/leaderboard_deep.json`
- **Elo table key**: `elo_v2_ci`
- **Pairs evaluated**: 105
- **Non-overlapping CI pairs**: 66
- **Separability**: **62.86%** (target >= 65.0% — BELOW TARGET, -2.14 pp vs target)

## Reference points

| Benchmark | Separability % |
|---|---:|
| MT-Bench (Zheng et al. 2023) | 22.6 |
| Chatbot Arena (general) | ~70 |
| Arena-Hard-Auto (Li et al. 2024) | 87.4 |
| **Deep Research Arena (this run)** | **62.86** |
| **Target after v2 + densify** | **>= 65.0** |

## Per-pair CI overlap

Sorted by |Elo gap| descending. `overlap=False` rows are the separable pairs — those that survive bootstrap noise.

| Pair | A Elo | A CI | B Elo | B CI | |gap| | Overlap? |
|---|---:|---|---:|---|---:|:---:|
| claude-code vs ldr | 1352.9 | [1282.5, 1400.4] | 705.9 | [649.6, 764.7] | 647.0 | **no** |
| claude-code vs langchain-odr | 1352.9 | [1282.5, 1400.4] | 795.8 | [725.3, 860.4] | 557.1 | **no** |
| ldr vs opencode | 705.9 | [649.6, 764.7] | 1250.6 | [1180.9, 1319.2] | 544.7 | **no** |
| claude-code vs dzhng | 1352.9 | [1282.5, 1400.4] | 822.5 | [767.0, 884.5] | 530.4 | **no** |
| claude-code vs co-storm | 1352.9 | [1282.5, 1400.4] | 822.7 | [767.2, 890.7] | 530.2 | **no** |
| claude-code vs gpt-researcher | 1352.9 | [1282.5, 1400.4] | 846.3 | [762.2, 923.9] | 506.6 | **no** |
| camel-ai vs ldr | 1188.0 | [1110.7, 1262.3] | 705.9 | [649.6, 764.7] | 482.1 | **no** |
| claude-code vs flowsearcher-ds | 1352.9 | [1282.5, 1400.4] | 893.4 | [811.9, 988.1] | 459.5 | **no** |
| langchain-odr vs opencode | 795.8 | [725.3, 860.4] | 1250.6 | [1180.9, 1319.2] | 454.8 | **no** |
| dzhng vs opencode | 822.5 | [767.0, 884.5] | 1250.6 | [1180.9, 1319.2] | 428.1 | **no** |
| co-storm vs opencode | 822.7 | [767.2, 890.7] | 1250.6 | [1180.9, 1319.2] | 427.9 | **no** |
| gpt-researcher vs opencode | 846.3 | [762.2, 923.9] | 1250.6 | [1180.9, 1319.2] | 404.3 | **no** |
| ldr vs tongyi-dr | 705.9 | [649.6, 764.7] | 1101.4 | [1026.1, 1167.9] | 395.5 | **no** |
| camel-ai vs langchain-odr | 1188.0 | [1110.7, 1262.3] | 795.8 | [725.3, 860.4] | 392.2 | **no** |
| ldr vs storm | 705.9 | [649.6, 764.7] | 1083.0 | [993.5, 1182.9] | 377.1 | **no** |
| camel-ai vs dzhng | 1188.0 | [1110.7, 1262.3] | 822.5 | [767.0, 884.5] | 365.5 | **no** |
| camel-ai vs co-storm | 1188.0 | [1110.7, 1262.3] | 822.7 | [767.2, 890.7] | 365.3 | **no** |
| deerflow vs ldr | 1068.8 | [980.0, 1154.7] | 705.9 | [649.6, 764.7] | 362.9 | **no** |
| flowsearcher-ds vs opencode | 893.4 | [811.9, 988.1] | 1250.6 | [1180.9, 1319.2] | 357.2 | **no** |
| ldr vs smolagents | 705.9 | [649.6, 764.7] | 1061.4 | [976.1, 1155.7] | 355.5 | **no** |
| claude-code vs local-deep-researcher | 1352.9 | [1282.5, 1400.4] | 1000.4 | [929.1, 1070.2] | 352.5 | **no** |
| claude-code vs ii-researcher | 1352.9 | [1282.5, 1400.4] | 1006.9 | [909.1, 1094.5] | 346.0 | **no** |
| camel-ai vs gpt-researcher | 1188.0 | [1110.7, 1262.3] | 846.3 | [762.2, 923.9] | 341.7 | **no** |
| langchain-odr vs tongyi-dr | 795.8 | [725.3, 860.4] | 1101.4 | [1026.1, 1167.9] | 305.6 | **no** |
| ii-researcher vs ldr | 1006.9 | [909.1, 1094.5] | 705.9 | [649.6, 764.7] | 301.0 | **no** |
| camel-ai vs flowsearcher-ds | 1188.0 | [1110.7, 1262.3] | 893.4 | [811.9, 988.1] | 294.6 | **no** |
| ldr vs local-deep-researcher | 705.9 | [649.6, 764.7] | 1000.4 | [929.1, 1070.2] | 294.5 | **no** |
| claude-code vs smolagents | 1352.9 | [1282.5, 1400.4] | 1061.4 | [976.1, 1155.7] | 291.5 | **no** |
| langchain-odr vs storm | 795.8 | [725.3, 860.4] | 1083.0 | [993.5, 1182.9] | 287.2 | **no** |
| claude-code vs deerflow | 1352.9 | [1282.5, 1400.4] | 1068.8 | [980.0, 1154.7] | 284.1 | **no** |
| dzhng vs tongyi-dr | 822.5 | [767.0, 884.5] | 1101.4 | [1026.1, 1167.9] | 278.9 | **no** |
| co-storm vs tongyi-dr | 822.7 | [767.2, 890.7] | 1101.4 | [1026.1, 1167.9] | 278.7 | **no** |
| deerflow vs langchain-odr | 1068.8 | [980.0, 1154.7] | 795.8 | [725.3, 860.4] | 273.0 | **no** |
| claude-code vs storm | 1352.9 | [1282.5, 1400.4] | 1083.0 | [993.5, 1182.9] | 269.9 | **no** |
| langchain-odr vs smolagents | 795.8 | [725.3, 860.4] | 1061.4 | [976.1, 1155.7] | 265.6 | **no** |
| dzhng vs storm | 822.5 | [767.0, 884.5] | 1083.0 | [993.5, 1182.9] | 260.5 | **no** |
| co-storm vs storm | 822.7 | [767.2, 890.7] | 1083.0 | [993.5, 1182.9] | 260.3 | **no** |
| gpt-researcher vs tongyi-dr | 846.3 | [762.2, 923.9] | 1101.4 | [1026.1, 1167.9] | 255.1 | **no** |
| claude-code vs tongyi-dr | 1352.9 | [1282.5, 1400.4] | 1101.4 | [1026.1, 1167.9] | 251.5 | **no** |
| local-deep-researcher vs opencode | 1000.4 | [929.1, 1070.2] | 1250.6 | [1180.9, 1319.2] | 250.2 | **no** |
| deerflow vs dzhng | 1068.8 | [980.0, 1154.7] | 822.5 | [767.0, 884.5] | 246.3 | **no** |
| co-storm vs deerflow | 822.7 | [767.2, 890.7] | 1068.8 | [980.0, 1154.7] | 246.1 | **no** |
| ii-researcher vs opencode | 1006.9 | [909.1, 1094.5] | 1250.6 | [1180.9, 1319.2] | 243.7 | **no** |
| dzhng vs smolagents | 822.5 | [767.0, 884.5] | 1061.4 | [976.1, 1155.7] | 238.9 | **no** |
| co-storm vs smolagents | 822.7 | [767.2, 890.7] | 1061.4 | [976.1, 1155.7] | 238.7 | **no** |
| gpt-researcher vs storm | 846.3 | [762.2, 923.9] | 1083.0 | [993.5, 1182.9] | 236.7 | **no** |
| deerflow vs gpt-researcher | 1068.8 | [980.0, 1154.7] | 846.3 | [762.2, 923.9] | 222.5 | **no** |
| gpt-researcher vs smolagents | 846.3 | [762.2, 923.9] | 1061.4 | [976.1, 1155.7] | 215.1 | **no** |
| ii-researcher vs langchain-odr | 1006.9 | [909.1, 1094.5] | 795.8 | [725.3, 860.4] | 211.1 | **no** |
| flowsearcher-ds vs tongyi-dr | 893.4 | [811.9, 988.1] | 1101.4 | [1026.1, 1167.9] | 208.0 | **no** |
| langchain-odr vs local-deep-researcher | 795.8 | [725.3, 860.4] | 1000.4 | [929.1, 1070.2] | 204.6 | **no** |
| flowsearcher-ds vs storm | 893.4 | [811.9, 988.1] | 1083.0 | [993.5, 1182.9] | 189.6 | **no** |
| opencode vs smolagents | 1250.6 | [1180.9, 1319.2] | 1061.4 | [976.1, 1155.7] | 189.2 | **no** |
| camel-ai vs local-deep-researcher | 1188.0 | [1110.7, 1262.3] | 1000.4 | [929.1, 1070.2] | 187.6 | **no** |
| flowsearcher-ds vs ldr | 893.4 | [811.9, 988.1] | 705.9 | [649.6, 764.7] | 187.5 | **no** |
| dzhng vs ii-researcher | 822.5 | [767.0, 884.5] | 1006.9 | [909.1, 1094.5] | 184.4 | **no** |
| co-storm vs ii-researcher | 822.7 | [767.2, 890.7] | 1006.9 | [909.1, 1094.5] | 184.2 | **no** |
| deerflow vs opencode | 1068.8 | [980.0, 1154.7] | 1250.6 | [1180.9, 1319.2] | 181.8 | **no** |
| camel-ai vs ii-researcher | 1188.0 | [1110.7, 1262.3] | 1006.9 | [909.1, 1094.5] | 181.1 | **no** |
| dzhng vs local-deep-researcher | 822.5 | [767.0, 884.5] | 1000.4 | [929.1, 1070.2] | 177.9 | **no** |
| co-storm vs local-deep-researcher | 822.7 | [767.2, 890.7] | 1000.4 | [929.1, 1070.2] | 177.7 | **no** |
| deerflow vs flowsearcher-ds | 1068.8 | [980.0, 1154.7] | 893.4 | [811.9, 988.1] | 175.4 | yes |
| flowsearcher-ds vs smolagents | 893.4 | [811.9, 988.1] | 1061.4 | [976.1, 1155.7] | 168.0 | yes |
| opencode vs storm | 1250.6 | [1180.9, 1319.2] | 1083.0 | [993.5, 1182.9] | 167.6 | yes |
| camel-ai vs claude-code | 1188.0 | [1110.7, 1262.3] | 1352.9 | [1282.5, 1400.4] | 164.9 | **no** |
| gpt-researcher vs ii-researcher | 846.3 | [762.2, 923.9] | 1006.9 | [909.1, 1094.5] | 160.6 | yes |
| gpt-researcher vs local-deep-researcher | 846.3 | [762.2, 923.9] | 1000.4 | [929.1, 1070.2] | 154.1 | **no** |
| opencode vs tongyi-dr | 1250.6 | [1180.9, 1319.2] | 1101.4 | [1026.1, 1167.9] | 149.2 | **no** |
| gpt-researcher vs ldr | 846.3 | [762.2, 923.9] | 705.9 | [649.6, 764.7] | 140.4 | yes |
| camel-ai vs smolagents | 1188.0 | [1110.7, 1262.3] | 1061.4 | [976.1, 1155.7] | 126.6 | yes |
| camel-ai vs deerflow | 1188.0 | [1110.7, 1262.3] | 1068.8 | [980.0, 1154.7] | 119.2 | yes |
| co-storm vs ldr | 822.7 | [767.2, 890.7] | 705.9 | [649.6, 764.7] | 116.8 | **no** |
| dzhng vs ldr | 822.5 | [767.0, 884.5] | 705.9 | [649.6, 764.7] | 116.6 | **no** |
| flowsearcher-ds vs ii-researcher | 893.4 | [811.9, 988.1] | 1006.9 | [909.1, 1094.5] | 113.5 | yes |
| flowsearcher-ds vs local-deep-researcher | 893.4 | [811.9, 988.1] | 1000.4 | [929.1, 1070.2] | 107.0 | yes |
| camel-ai vs storm | 1188.0 | [1110.7, 1262.3] | 1083.0 | [993.5, 1182.9] | 105.0 | yes |
| claude-code vs opencode | 1352.9 | [1282.5, 1400.4] | 1250.6 | [1180.9, 1319.2] | 102.3 | yes |
| local-deep-researcher vs tongyi-dr | 1000.4 | [929.1, 1070.2] | 1101.4 | [1026.1, 1167.9] | 101.0 | yes |
| flowsearcher-ds vs langchain-odr | 893.4 | [811.9, 988.1] | 795.8 | [725.3, 860.4] | 97.6 | yes |
| ii-researcher vs tongyi-dr | 1006.9 | [909.1, 1094.5] | 1101.4 | [1026.1, 1167.9] | 94.5 | yes |
| langchain-odr vs ldr | 795.8 | [725.3, 860.4] | 705.9 | [649.6, 764.7] | 89.9 | yes |
| camel-ai vs tongyi-dr | 1188.0 | [1110.7, 1262.3] | 1101.4 | [1026.1, 1167.9] | 86.6 | yes |
| local-deep-researcher vs storm | 1000.4 | [929.1, 1070.2] | 1083.0 | [993.5, 1182.9] | 82.6 | yes |
| ii-researcher vs storm | 1006.9 | [909.1, 1094.5] | 1083.0 | [993.5, 1182.9] | 76.1 | yes |
| dzhng vs flowsearcher-ds | 822.5 | [767.0, 884.5] | 893.4 | [811.9, 988.1] | 70.9 | yes |
| co-storm vs flowsearcher-ds | 822.7 | [767.2, 890.7] | 893.4 | [811.9, 988.1] | 70.7 | yes |
| deerflow vs local-deep-researcher | 1068.8 | [980.0, 1154.7] | 1000.4 | [929.1, 1070.2] | 68.4 | yes |
| camel-ai vs opencode | 1188.0 | [1110.7, 1262.3] | 1250.6 | [1180.9, 1319.2] | 62.6 | yes |
| deerflow vs ii-researcher | 1068.8 | [980.0, 1154.7] | 1006.9 | [909.1, 1094.5] | 61.9 | yes |
| local-deep-researcher vs smolagents | 1000.4 | [929.1, 1070.2] | 1061.4 | [976.1, 1155.7] | 61.0 | yes |
| ii-researcher vs smolagents | 1006.9 | [909.1, 1094.5] | 1061.4 | [976.1, 1155.7] | 54.5 | yes |
| gpt-researcher vs langchain-odr | 846.3 | [762.2, 923.9] | 795.8 | [725.3, 860.4] | 50.5 | yes |
| flowsearcher-ds vs gpt-researcher | 893.4 | [811.9, 988.1] | 846.3 | [762.2, 923.9] | 47.1 | yes |
| smolagents vs tongyi-dr | 1061.4 | [976.1, 1155.7] | 1101.4 | [1026.1, 1167.9] | 40.0 | yes |
| deerflow vs tongyi-dr | 1068.8 | [980.0, 1154.7] | 1101.4 | [1026.1, 1167.9] | 32.6 | yes |
| co-storm vs langchain-odr | 822.7 | [767.2, 890.7] | 795.8 | [725.3, 860.4] | 26.9 | yes |
| dzhng vs langchain-odr | 822.5 | [767.0, 884.5] | 795.8 | [725.3, 860.4] | 26.7 | yes |
| dzhng vs gpt-researcher | 822.5 | [767.0, 884.5] | 846.3 | [762.2, 923.9] | 23.8 | yes |
| co-storm vs gpt-researcher | 822.7 | [767.2, 890.7] | 846.3 | [762.2, 923.9] | 23.6 | yes |
| smolagents vs storm | 1061.4 | [976.1, 1155.7] | 1083.0 | [993.5, 1182.9] | 21.6 | yes |
| storm vs tongyi-dr | 1083.0 | [993.5, 1182.9] | 1101.4 | [1026.1, 1167.9] | 18.4 | yes |
| deerflow vs storm | 1068.8 | [980.0, 1154.7] | 1083.0 | [993.5, 1182.9] | 14.2 | yes |
| deerflow vs smolagents | 1068.8 | [980.0, 1154.7] | 1061.4 | [976.1, 1155.7] | 7.4 | yes |
| ii-researcher vs local-deep-researcher | 1006.9 | [909.1, 1094.5] | 1000.4 | [929.1, 1070.2] | 6.5 | yes |
| co-storm vs dzhng | 822.7 | [767.2, 890.7] | 822.5 | [767.0, 884.5] | 0.2 | yes |

## How to read this

An `overlap=no` row means the bootstrap 95% Elo CIs of the two agents do not overlap, so the benchmark distinguishes them with high confidence. The separability % is the fraction of all C(n, 2) agent pairs in that state.

The three levers we are pulling to lift this number:

1. **Adversarial tasks** (v2 — 20 specs in `configs/deep_topics/V2_ADVERSARIAL_TASKS.json`) — splits the top cluster by stressing depth / rigor / coverage individually.
2. **Top-pair densification** (`scripts/run_pairwise_battles.py --strategy top-pair-densify`) — shrinks bootstrap CIs by adding battles where the gap is smallest.
3. **Composite dynamic-range widening** (Workstream A's v3 composite) — undoes the saturation that pins top agents to the same per-pillar Elo.

See `docs/SEPARABILITY_PLAN.md` for the staged validation protocol.
