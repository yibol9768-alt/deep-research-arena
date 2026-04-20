# IRT Calibration — 2-PL Item Analysis

**n_agents** = 13    **n_tasks** = 4    **observations** = 52

Note: with n_tasks this small, IRT estimates are directional only. Treat flags as hypotheses to investigate, not verdicts.

## Agent ability (θ, higher = better)

| Agent | θ |
|---|---:|
| react-qwen35plus | +0.87 |
| deerflow-glm46-shim | +0.79 |
| react-glm5 | +0.74 |
| deerflow-glm46-new | +0.58 |
| gpt-researcher | +0.58 |
| deerflow-glm46 | +0.37 |
| camel-ai | +0.36 |
| camel-ai-ds | +0.34 |
| smolagents-ds | -0.18 |
| odr-ds | -0.34 |
| deerflow-ds | -1.60 |
| smolagents | -2.17 |
| gpt-researcher-ds | -3.10 |

## Task calibration

| Task | Discrimination (a) | Difficulty (b) | Flag |
|---|---:|---:|:---:|
| dr_cross_v3_0001 | +5.00 | -0.33 | **OK** |
| dr_cross_v3_0005 | +5.00 | -0.35 | **OK** |
| dr_cross_v3_0006 | +5.00 | -0.34 | **OK** |
| dr_cross_v3_0007 | +5.00 | -0.35 | **OK** |

## Interpretation

- **θ (theta)**: agent ability on this test-set scale. θ≈0 means average, θ > 1 means clearly above-average across all tasks jointly.
- **a (discrimination)**: how strongly the task separates good from bad agents. a<0.5 = task doesn't inform the ranking, consider dropping.
- **b (difficulty)**: the θ value at which agents flip from mostly-fail to mostly-succeed. b < -2 = trivial; b > 2 = saturated-hard. Mid-range b (−1..+1) is ideal.

## Flags

- **OK**: mid-range b, healthy a. Keep.
- **LOW_DISCRIM**: |a|<0.5, task doesn't separate agents. Rewrite or drop.
- **SATURATED**: |b|>2.5, everyone succeeds or fails. No signal.
- **INVERTED**: a<0, worse agents score higher — suspicious scorer bug (e.g. length-rewarding pillar pulls longer bad reports above shorter good ones).
