# Deep Research Arena — FINAL Leaderboard (paper-ready)

*80 runs across 14 agents × 8 tasks.  **Dual-judge setup** (different-family from agent, per Wataoka 2024 NeurIPS): GLM-agent runs are judged by DeepSeek V3.2; `-ds` suffix agents (DeepSeek agent) are judged by GLM-4.5. Both directions of the role-swap are included to show how judge identity shapes the ranking.  Composite weights: v3.1 (cite 0.25 / evidence_density 0.20 / llm_judge 0.20 / checklist 0.20 / fact_kg 0.05 / structure 0.05 / efficiency 0.05).*

## Headline — Composite-Elo with 95% bootstrap CI

Bootstrap over N=1000 resamples of the synthesised battle set (C(14,2) × 8 tasks = 728 battles). Reports point estimate plus 95% percentile interval.

| Rank | Agent | Elo | 95% CI | W | L | D | Battles |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1313.6** | [1237, 1379] ±71 | 47 | 4 | 1 | 52 |
| 2 | react-glm5 | **1277.5** | [1203, 1351] ±74 | 45 | 6 | 1 | 52 |
| 3 | gpt-researcher | **1242.7** | [1150, 1329] ±90 | 57 | 9 | 6 | 72 |
| 4 | deerflow-glm46-shim | **1179.1** | [1105, 1252] ±74 | 39 | 13 | 0 | 52 |
| 5 | camel-ai | **1115.7** | [1037, 1198] ±80 | 33 | 16 | 3 | 52 |
| 6 | deerflow-glm46-new | **1108.2** | [1034, 1178] ±72 | 33 | 17 | 2 | 52 |
| 7 | deerflow-glm46 | **999.2** | [924, 1079] ±77 | 26 | 26 | 0 | 52 |
| 8 | gpt5chat | **967.6** | [884, 1050] ±83 | 31 | 32 | 9 | 72 |
| 9 | camel-ai-ds | **879.9** | [795, 969] ±87 | 25 | 43 | 4 | 72 |
| 10 | smolagents | **877.0** | [796, 945] ±74 | 17 | 35 | 0 | 52 |
| 11 | smolagents-ds | **806.8** | [707, 890] ±92 | 16 | 50 | 6 | 72 |
| 12 | odr-ds | **766.8** | [699, 866] ±84 | 15 | 52 | 5 | 72 |
| 13 | gpt-researcher-ds | **750.3** | [670, 843] ±86 | 13 | 54 | 5 | 72 |
| 14 | deerflow-ds | **715.8** | [644, 792] ±74 | 5 | 45 | 2 | 52 |

## Rank significance (permutation test, N=1000)

*p < 0.05 means the adjacent rank gap is unlikely under the null hypothesis that the battle outcomes are random.*

| Higher | Lower | Gap (Elo) | p-value | Significant? |
|---|---|---:|---:|---|
| react-qwen35plus | react-glm5 | 36.1 | 0.576 | ❌ |
| react-glm5 | gpt-researcher | 34.8 | 0.603 | ❌ |
| gpt-researcher | deerflow-glm46-shim | 63.6 | 0.307 | ❌ |
| deerflow-glm46-shim | camel-ai | 63.4 | 0.298 | ❌ |
| camel-ai | deerflow-glm46-new | 7.5 | 0.899 | ❌ |
| deerflow-glm46-new | deerflow-glm46 | 109.0 | 0.074 | ❌ |
| deerflow-glm46 | gpt5chat | 31.6 | 0.615 | ❌ |
| gpt5chat | camel-ai-ds | 87.7 | 0.188 | ❌ |
| camel-ai-ds | smolagents | 2.9 | 0.96 | ❌ |
| smolagents | smolagents-ds | 70.2 | 0.262 | ❌ |
| smolagents-ds | odr-ds | 40.0 | 0.571 | ❌ |
| odr-ds | gpt-researcher-ds | 16.5 | 0.788 | ❌ |
| gpt-researcher-ds | deerflow-ds | 34.5 | 0.598 | ❌ |

## Per-pillar Elo (which agent is best at what)

| Agent | chec | cita | effi | evid | fact | llm_ | mark |
|---|---:|---:|---:|---:|---:|---:|---:|
| camel-ai | 1023 | 1098 | 1000 | 1187 | 1013 | 949 | 1083 |
| camel-ai-ds | 1095 | 1141 | 1000 | 800 | 1023 | 770 | 1140 |
| deerflow-ds | 977 | 882 | 1000 | 776 | 960 | 748 | 817 |
| deerflow-glm46 | 818 | 991 | 1000 | 1029 | 958 | 1012 | 1072 |
| deerflow-glm46-new | 788 | 1042 | 1000 | 1122 | 1072 | 876 | 1172 |
| deerflow-glm46-shim | 754 | 1189 | 1000 | 1256 | 958 | 995 | 1171 |
| gpt-researcher | 928 | 1115 | 1000 | 1232 | 1014 | 977 | 1139 |
| gpt-researcher-ds | 999 | 785 | 1000 | 796 | 962 | 978 | 866 |
| gpt5chat | 1145 | 1081 | 1000 | 798 | 964 | 986 | 1071 |
| odr-ds | 1174 | 788 | 1000 | 799 | 961 | 907 | 868 |
| react-glm5 | 1008 | 1165 | 1000 | 1196 | 1138 | 1098 | 1080 |
| react-qwen35plus | 1119 | 1196 | 1000 | 1234 | 1055 | 1208 | 1169 |
| smolagents | 1180 | 731 | 1000 | 976 | 959 | 1310 | 775 |
| smolagents-ds | 993 | 795 | 1000 | 798 | 964 | 1186 | 576 |

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
