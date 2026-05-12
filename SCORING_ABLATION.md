# Scoring Ablation Study

*150 score files, 5 agents, 30 tasks.*

## 1. Baseline V2 Ranking

| Rank | Agent | Mean V2 |
|---:|---|---:|
| 1 | camel-ai | 0.1384 |
| 2 | smolagents | 0.0888 |
| 3 | gpt-researcher | 0.0038 |
| 4 | langchain-odr | 0.0005 |
| 5 | storm | 0.0000 |

## 2. Leave-One-Out Ablation

Drop each dimension (set to 0), recompute V2, check rank change.

| Dropped Dim | Ranking | Kendall τ vs Baseline | Rank Changes |
|---|---|---:|---|
| url_cov | camel-ai > smolagents > gpt-researcher > langchain-odr > storm | 1.00 | none |
| judge | camel-ai > smolagents > gpt-researcher > langchain-odr > storm | 1.00 | none |
| spec | camel-ai > smolagents > gpt-researcher > langchain-odr > storm | 1.00 | none |
| reach | camel-ai > gpt-researcher > langchain-odr > smolagents > storm | 0.60 | gpt-researcher: 3→2; langchain-odr: 4→3; smolagents: 2→4 |
| quote | camel-ai > smolagents > gpt-researcher > langchain-odr > storm | 1.00 | none |
| nli | camel-ai > smolagents > gpt-researcher > langchain-odr > storm | 1.00 | none |

## 3. Inter-Dimension Correlation Matrix

### Pearson r

| | url_cov | judge | spec | reach | quote | nli |
|---|---:|---:|---:|---:|---:|---:|
| url_cov | 1.00 | 0.13 | 0.54 | 0.16 | 0.16 | nan |
| judge | 0.13 | 1.00 | 0.25 | -0.09 | -0.09 | nan |
| spec | 0.54 | 0.25 | 1.00 | 0.33 | 0.31 | nan |
| reach | 0.16 | -0.09 | 0.33 | 1.00 | 0.98 | nan |
| quote | 0.16 | -0.09 | 0.31 | 0.98 | 1.00 | nan |
| nli | nan | nan | nan | nan | nan | 1.00 |

### Spearman ρ

| | url_cov | judge | spec | reach | quote | nli |
|---|---:|---:|---:|---:|---:|---:|
| url_cov | 1.00 | 0.22 | 0.60 | 0.48 | 0.33 | nan |
| judge | 0.22 | 1.00 | 0.30 | 0.06 | -0.02 | nan |
| spec | 0.60 | 0.30 | 1.00 | 0.41 | 0.31 | nan |
| reach | 0.48 | 0.06 | 0.41 | 1.00 | 0.91 | nan |
| quote | 0.33 | -0.02 | 0.31 | 0.91 | 1.00 | nan |
| nli | nan | nan | nan | nan | nan | 1.00 |

### Highly correlated pairs (|Spearman ρ| > 0.7)

- **reach** ↔ **quote**: ρ = 0.914

## 4. Weight Sensitivity Analysis

Sweep each quality weight from 50% to 150% of default (renormalized). Measure Kendall τ stability of agent ranking.

| Dim | Default W | 0.5× | 0.75× | 1.0× | 1.25× | 1.5× | Min τ |
|---|---:|---:|---:|---:|---:|---:|---:|
| url_cov | 0.40 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| judge | 0.40 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| spec | 0.20 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### Truth gate removal test

What happens if we drop the reachability gate entirely?

(Leaderboard v1 = 0.4·url_cov + 0.4·judge + 0.2·spec, **no** reachability gate)

- V2 ranking (reach-gated): camel-ai > smolagents > gpt-researcher > langchain-odr > storm
- V1 ranking (additive, no gate): gpt-researcher > camel-ai > langchain-odr > smolagents > storm
- Kendall τ = **0.40** — partially changed
- Rank changes: camel-ai: 1→2; gpt-researcher: 3→1; langchain-odr: 4→3; smolagents: 2→4

## 5. Per-Agent Dimension Profiles

Mean score per dimension per agent.

| Agent | url_cov | judge | spec | reach | quote | nli |
|---|---:|---:|---:|---:|---:|---:|
| camel-ai | 0.140 | 0.519 | 0.700 | 0.807 | 0.751 | 0.000 |
| gpt-researcher | 0.201 | 0.613 | 0.656 | 0.031 | 0.001 | 0.000 |
| langchain-odr | 0.067 | 0.484 | 0.489 | 0.004 | 0.001 | 0.000 |
| smolagents | 0.112 | 0.441 | 0.333 | 0.649 | 0.576 | 0.000 |
| storm | 0.000 | 0.379 | 0.000 | 0.000 | 0.000 | 0.000 |

## 6. Dimension Discriminative Power

Inter-agent variance vs intra-agent variance (F-ratio, higher = more discriminative).

| Dimension | Inter-agent var | Intra-agent var | F-ratio |
|---|---:|---:|---:|
| url_cov | 0.1383 | 0.0094 | 14.68 |
| judge | 0.1831 | 0.0794 | 2.30 |
| spec | 1.9281 | 0.0394 | 48.98 |
| reach | 3.7701 | 0.0467 | 80.77 |
| quote | 3.2565 | 0.0407 | 80.09 |
| nli | 0.0000 | 0.0000 | inf |

## 7. Summary & Recommendations

- **F1: Truth gate is decisive.** Removing reachability gate changes ranking substantially (τ=0.40), confirming that URL truthfulness is the primary discriminator. Agents with fluent but fabricated URLs rise; grounded agents fall.
- **Redundancy warning:** reach and quote are highly correlated (ρ=0.914). Consider merging or dropping one.
- **Low variance:** nli (σ=0.000) barely varies across runs — it contributes weight but little discrimination.
- **Sensitive dimension:** dropping reach changes ranking (τ=0.60).
