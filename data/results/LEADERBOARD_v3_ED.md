# Deep Research Arena — v3.1 Leaderboard

*32 runs, 16 battles.  Composite v3.1 aligned with DeepResearch Bench (ICLR 2026) FACT methodology — `fact_kg` recall (auto-scraped category top-N oracle) demoted from 0.30 → 0.05, `citation` (ALCE-style URL-supports-claim) 0.15 → 0.25, `evidence_density` (Effective Primary-Source Citations) 0.00 → 0.20.*

**Known caveat**: golden triples for tasks 0005/0006/0007 contain category top-N items that violate task intent (e.g. a $607 printer in a $500 budget task). `fact_kg` pillar therefore carries minimal weight until oracle is rebuilt.

## Weights (v3.1)

| Pillar | Weight | Rationale |
|---|---:|---|
| markdown_structure | 0.05 | Words/paras/citations threshold (trivially met) |
| citation | 0.25 | ALCE F1 — URL supports claim |
| fact_kg | 0.05 | Demoted (oracle quality bug) |
| llm_judge | 0.20 | RACE 4-dim (Comp/Depth/IF/Readability) |
| checklist | 0.20 | DRACO-style per-task rubric |
| evidence_density | 0.20 | Effective Primary-Source Citations (new) |
| efficiency | 0.05 | Tokens/time/cost |

## Headline — Composite-Elo v3.1

| Rank | Agent | Elo | W | L | D | Battles |
|---:|---|---:|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1174.0** | 23 | 4 | 1 | 28 |
| 2 | gpt-researcher | **1157.5** | 22 | 5 | 1 | 28 |
| 3 | react-glm5 | **1136.7** | 21 | 6 | 1 | 28 |
| 4 | deerflow-glm46-shim | **1018.5** | 15 | 13 | 0 | 28 |
| 5 | camel-ai | **983.1** | 12 | 14 | 2 | 28 |
| 6 | deerflow-glm46-new | **938.8** | 10 | 17 | 1 | 28 |
| 7 | deerflow-glm46 | **854.1** | 6 | 22 | 0 | 28 |
| 8 | smolagents | **737.2** | 0 | 28 | 0 | 28 |

## Composite-Elo v3.1 vs Judge-Elo

| Agent | Composite-Elo (v3.1) | Judge-Elo | Δ (Judge − Comp) |
|---|---:|---:|---:|
| react-qwen35plus | 1174.0 | 1050.8 | -123.2 |
| gpt-researcher | 1157.5 | — | — |
| react-glm5 | 1136.7 | 1014.2 | -122.5 |
| deerflow-glm46-shim | 1018.5 | — | — |
| camel-ai | 983.1 | — | — |
| deerflow-glm46-new | 938.8 | — | — |
| deerflow-glm46 | 854.1 | 935.1 | +81.0 |
| smolagents | 737.2 | — | — |

## Per-pillar Elo (now includes `evidence_density`)

| Agent | chec | cita | effi | evid | fact | llm_ | mark |
|---|---:|---:|---:|---:|---:|---:|---:|
| camel-ai | 1037 | 1032 | 1000 | 1030 | 980 | 898 | 991 |
| deerflow-glm46 | 886 | 891 | 1000 | 814 | 949 | 954 | 968 |
| deerflow-glm46-new | 892 | 945 | 1000 | 946 | 1053 | 900 | 1070 |
| deerflow-glm46-shim | 838 | 1108 | 1000 | 1112 | 953 | 928 | 1071 |
| gpt-researcher | 990 | 1071 | 1000 | 1236 | 1000 | 910 | 1071 |
| react-glm5 | 1062 | 1083 | 1000 | 1044 | 1092 | 1037 | 992 |
| react-qwen35plus | 1116 | 1118 | 1000 | 1082 | 1023 | 1134 | 1072 |
| smolagents | 1180 | 752 | 1000 | 737 | 950 | 1240 | 764 |
