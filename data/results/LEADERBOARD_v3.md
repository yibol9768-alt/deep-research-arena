# Deep Research Arena — v3 Leaderboard

*Auto-generated from 13 runs (3 agents × 4 tasks) and 16 pairwise battles.*

## Headline — Composite-Elo (synthesised from per-task composite)

| Rank | Agent | Elo | W | L | D | Battles |
|---:|---|---:|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1036.3** | 5 | 2 | 5 | 12 |
| 2 | deerflow-glm46 | **989.9** | 3 | 4 | 2 | 9 |
| 3 | react-glm5 | **973.8** | 3 | 5 | 1 | 9 |

## Composite-Elo vs Judge-Elo (side-by-side)

| Agent | Composite-Elo | Judge-Elo (all judges) | Δ (Judge − Comp) |
|---|---:|---:|---:|
| react-qwen35plus | 1036.3 | 1050.8 | +14.5 |
| react-glm5 | 973.8 | 1014.2 | +40.4 |
| deerflow-glm46 | 989.9 | 935.1 | -54.8 |

## Judge-Elo breakdown (per judge model)

### Judge: `glm-5`  (12 battles)
| Rank | Agent | Elo | W | L | D | Battles |
|---:|---|---:|---:|---:|---:|---:|
| 1 | react-qwen35plus | **1050.8** | 6 | 2 | 0 | 8 |
| 2 | react-glm5 | **1014.2** | 4 | 3 | 1 | 8 |
| 3 | deerflow-glm46 | **935.1** | 1 | 6 | 1 | 8 |


## Per-pillar Elo (composite pillars broken out)

| Agent | chec | cita | effi | fact | llm_ | mark |
|---|---:|---:|---:|---:|---:|---:|
| deerflow-glm46 | 990 | 936 | 1112 | 963 | 940 | 975 |
| react-glm5 | 949 | 1051 | 949 | 1036 | 976 | 989 |
| react-qwen35plus | 1060 | 1013 | 939 | 1001 | 1083 | 1036 |

---

### Interpretation notes

- **Composite-Elo** uses the 6-pillar composite score as the battle outcome
  signal. Fast to produce but biased by pillar weight choices.
- **Judge-Elo** uses LLM pairwise judgements (position-swapped). Closer to
  Chatbot Arena methodology; susceptible to judge self-preference unless
  dual-judged.
- **Δ(Judge − Comp)** surfaces agents that score well on the pillar formula
  but lose head-to-head judgement, or vice versa. A large |Δ| indicates
  the composite weights may not reflect perceived research quality.
