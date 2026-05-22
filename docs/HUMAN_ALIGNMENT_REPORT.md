# Human Alignment Report

_Generated: 2026-05-22T05:30:56.121073+00:00_
_Composite source: `src.scoring.leaderboard_composites.composite_v3`_
_Dim-score source: `(synthetic --dry-run)`_
_Prefs: 500 rows, 8 agents in common_

## Correlation summary

| metric | value |
|--------|-------|
| Spearman rho     | 0.6429 |
| Pearson r        | 0.7340 |
| Kendall tau      | 0.5714 |

Target: Spearman >= 0.85. 
If Spearman < 0.75, refit weights with `python scripts/fit_weights_v3.py`.

## Per-agent table

| agent | n_battles | human_winrate | composite_v3 |
|-------|-----------|---------------|--------------|
| `agent_04` | 126 | 0.746 | 0.6968 |
| `agent_03` | 130 | 0.700 | 0.6158 |
| `agent_06` | 148 | 0.514 | 0.4454 |
| `agent_07` | 114 | 0.509 | 0.7220 |
| `agent_00` | 111 | 0.459 | 0.5827 |
| `agent_05` | 120 | 0.442 | 0.5624 |
| `agent_01` | 127 | 0.409 | 0.5453 |
| `agent_02` | 124 | 0.202 | 0.3518 |

## Top 10 biggest disagreements

Pairs where the model picked the opposite winner from the human.

| task | agent_a | agent_b | human | model | composite gap |
|------|---------|---------|-------|-------|---------------|
| `synthetic` | `agent_07` | `agent_02` | b | a | 0.3702 |
| `synthetic` | `agent_07` | `agent_02` | b | a | 0.3702 |
| `synthetic` | `agent_02` | `agent_04` | a | b | 0.3450 |
| `synthetic` | `agent_02` | `agent_04` | a | b | 0.3450 |
| `synthetic` | `agent_02` | `agent_04` | a | b | 0.3450 |
| `synthetic` | `agent_07` | `agent_06` | b | a | 0.2765 |
| `synthetic` | `agent_07` | `agent_06` | b | a | 0.2765 |
| `synthetic` | `agent_07` | `agent_06` | b | a | 0.2765 |
| `synthetic` | `agent_07` | `agent_06` | b | a | 0.2765 |
| `synthetic` | `agent_07` | `agent_06` | b | a | 0.2765 |

