# Deep Research Arena — FINAL Leaderboard (paper-ready)

*52 runs across 13 agents × 4 tasks.  **Dual-judge setup** (different-family from agent, per Wataoka 2024 NeurIPS): GLM-agent runs are judged by DeepSeek V3.2; `-ds` suffix agents (DeepSeek agent) are judged by GLM-4.5. Both directions of the role-swap are included to show how judge identity shapes the ranking.  Composite weights: v3.1 (cite 0.25 / evidence_density 0.20 / llm_judge 0.20 / checklist 0.20 / fact_kg 0.05 / structure 0.05 / efficiency 0.05).*

## Headline — Composite-Elo with 95% bootstrap CI

Bootstrap over N=1000 resamples of the synthesised battle set (C(13,2) × 4 tasks = 312 battles). Reports point estimate plus 95% percentile interval.

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1295.1** | [1224, 1360] ±68 | 43 | 4 | 1 | 48 |
| 2 | gpt-researcher | **1278.5** | [1197, 1347] ±75 | 42 | 5 | 1 | 48 |
| 3 | react-glm5 | **1261.6** | [1188, 1332] ±72 | 41 | 6 | 1 | 48 |
| 4 | deerflow-glm46-shim | **1161.6** | [1080, 1240] ±80 | 35 | 13 | 0 | 48 |
| 5 | camel-ai | **1121.2** | [1039, 1190] ±76 | 31 | 15 | 2 | 48 |
| 6 | deerflow-glm46-new | **1095.1** | [1022, 1171] ±74 | 30 | 17 | 1 | 48 |
| 7 | deerflow-glm46 | **999.0** | [928, 1073] ±73 | 24 | 24 | 0 | 48 |
| 8 | camel-ai-ds | **974.8** | [900, 1048] ±74 | 22 | 26 | 0 | 48 |
| 9 | smolagents | **882.0** | [816, 959] ±72 | 16 | 32 | 0 | 48 |
| 10 | odr-ds | **780.2** | [719, 866] ±73 | 9 | 38 | 1 | 48 |
| 11 | smolagents-ds | **730.6** | [655, 805] ±75 | 6 | 42 | 0 | 48 |
| 12 | deerflow-ds | **729.8** | [668, 798] ±65 | 5 | 41 | 2 | 48 |
| 13 | gpt-researcher-ds | **690.5** | [626, 760] ±67 | 3 | 44 | 1 | 48 |

## Rank significance (permutation test, N=1000)

*p < 0.05 means the adjacent rank gap is unlikely under the null hypothesis that the battle outcomes are random.*

| Higher | Lower | Gap (Elo) | p-value | Significant? |
|---|---|---:|---:|---|
| react-qwen35plus | gpt-researcher | 16.6 | 0.801 | ❌ |
| gpt-researcher | react-glm5 | 16.9 | 0.786 | ❌ |
| react-glm5 | deerflow-glm46-shim | 100.0 | 0.127 | ❌ |
| deerflow-glm46-shim | camel-ai | 40.4 | 0.537 | ❌ |
| camel-ai | deerflow-glm46-new | 26.1 | 0.685 | ❌ |
| deerflow-glm46-new | deerflow-glm46 | 96.1 | 0.147 | ❌ |
| deerflow-glm46 | camel-ai-ds | 24.2 | 0.714 | ❌ |
| camel-ai-ds | smolagents | 92.8 | 0.139 | ❌ |
| smolagents | odr-ds | 101.8 | 0.103 | ❌ |
| odr-ds | smolagents-ds | 49.6 | 0.435 | ❌ |
| smolagents-ds | deerflow-ds | 0.8 | 0.992 | ❌ |
| deerflow-ds | gpt-researcher-ds | 39.3 | 0.545 | ❌ |

## Per-pillar Elo (which agent is best at what)

| Agent | chec | cita | effi | evid | fact | llm_ | mark |
|---|---:|---:|---:|---:|---:|---:|---:|
| camel-ai | 1024 | 1099 | 1000 | 1180 | 1000 | 968 | 1079 |
| camel-ai-ds | 1120 | 1204 | 1000 | 760 | 1031 | 802 | 1171 |
| deerflow-ds | 996 | 900 | 1000 | 763 | 956 | 763 | 822 |
| deerflow-glm46 | 828 | 998 | 1000 | 1000 | 955 | 1013 | 1075 |
| deerflow-glm46-new | 804 | 1057 | 1000 | 1104 | 1071 | 880 | 1174 |
| deerflow-glm46-shim | 774 | 1204 | 1000 | 1236 | 954 | 1005 | 1174 |
| gpt-researcher | 907 | 1169 | 1000 | 1341 | 1022 | 962 | 1174 |
| gpt-researcher-ds | 1005 | 745 | 1000 | 762 | 962 | 988 | 826 |
| odr-ds | 1224 | 742 | 1000 | 760 | 960 | 934 | 824 |
| react-glm5 | 1010 | 1180 | 1000 | 1182 | 1130 | 1089 | 1080 |
| react-qwen35plus | 1128 | 1214 | 1000 | 1213 | 1048 | 1200 | 1173 |
| smolagents | 1203 | 744 | 1000 | 938 | 957 | 1296 | 786 |
| smolagents-ds | 977 | 743 | 1000 | 762 | 954 | 1099 | 642 |

## Real pairwise LLM-judge Elo (reference)

*From live head-to-head battles (position-swap for bias), judge = DeepSeek V3.2. Under-populated: only 12 battles, CIs very wide. Included for comparison with composite.*

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1050.8** | [983, 1110] ±64 | 6 | 2 | 0 | 8 |
| 2 | react-glm5 | **1014.2** | [952, 1074] ±61 | 4 | 3 | 1 | 8 |
| 3 | deerflow-glm46 | **935.1** | [888, 997] ±54 | 1 | 6 | 1 | 8 |

## Caveats (for reviewers)

1. **Sample size**: real LLM-judge battles N=12 → CI half-widths ~60 Elo. Synthesized battles N=112 (C(8,2)×4) but still underpowered for tight ordering — see permutation p-values above.
2. **Oracle v2 (filtered) available**: intent-aware rebuild ran on 4 scored tasks (budget + category filter, rejects 'Magic Home Nightstand in kitchen build'). `fact_kg` remains at 0.05 weight until all scores re-run with the filtered oracle.
3. **Citation metric**: default is ALCE substring. `CITATION_MODE=entailment` switches to claim-level NLI via DeepSeek (results not yet in headline, pending rescore).
4. **Task domain**: benchmark now has 107 tasks across consumer/UGC (0001-0087) + scholarly/policy (0088-0107; medicine, economics, history, AI ethics, urban planning). Only 4 consumer tasks have been run so far — expanding the run set to cover the scholarly tier is next.
5. **Framework incompatibilities documented**: (a) smolagents+GLM-4.7 emits `</code>` instead of the trained `<end_code>` sentinel, so its CodeAgent parser fails every step — the final report is a zero-tool-call hallucination. (b) LangChain open_deep_research and dzhng/deep-research both rely on structured-JSON output; GLM-4.7 via OpenAI-compat returns free text that fails zod/pydantic parsing. After the DeepSeek-agent swap these two frameworks also unlock, see `odr-ds`.
6. **Agent role-swap (Phase 9, 2026-04-19)**: switched agents from GLM-4.7 to DeepSeek V3.2 and judge from DeepSeek to GLM-4.5 to unblock frameworks that require JSON-mode and to surface judge-identity effects. Observations: (a) DeepSeek agents consistently score lower than GLM agents under the same framework (e.g. camel-ai 1121 vs camel-ai-ds 975, gpt-researcher 1279 vs gpt-researcher-ds 691) — DeepSeek reports tend to cite hallucinated URLs (`onestopmarket.com/...`) instead of real sandbox URLs (`localhost:7770/...`), crushing the citation pillar. (b) dzhng-ds and react-ds remain blocked (tool-call format and Anthropic-compat issues respectively).
