# IRT Calibration — 2-PL Item Analysis

**n_agents** = 14    **n_tasks** = 8    **observations** = 80

Note: with n_tasks this small, IRT estimates are directional only. Treat flags as hypotheses to investigate, not verdicts.

## Agent ability (θ, higher = better)

| Agent | θ |
|---|---:|
| deerflow-glm46-new | +2.03 |
| deerflow-glm46-shim | +2.01 |
| react-qwen35plus | +1.97 |
| react-glm5 | +1.97 |
| gpt-researcher | +0.23 |
| camel-ai | +0.10 |
| camel-ai-ds | +0.03 |
| gpt5chat | +0.01 |
| deerflow-glm46 | -0.01 |
| deerflow-ds | -0.18 |
| smolagents | -0.19 |
| gpt-researcher-ds | -0.32 |
| odr-ds | -0.95 |
| smolagents-ds | -3.72 |

## Task calibration

| Task | Discrimination (a) | Difficulty (b) | Flag |
|---|---:|---:|:---:|
| dr_cross_v3_0001 | +5.00 | -0.03 | **OK** |
| dr_cross_v3_0005 | +5.00 | -0.03 | **OK** |
| dr_cross_v3_0006 | +5.00 | -0.04 | **OK** |
| dr_cross_v3_0007 | +5.00 | -0.03 | **OK** |
| dr_cross_v3_0105 | +0.03 | -5.00 | **LOW_DISCRIM** |
| dr_cross_v3_0088 | -0.04 | +5.00 | **LOW_DISCRIM** |
| dr_cross_v3_0095 | -1.34 | +1.16 | **INVERTED** |
| dr_cross_v3_0100 | -3.60 | +0.60 | **INVERTED** |

## Interpretation

- **θ (theta)**: agent ability on this test-set scale. θ≈0 means average, θ > 1 means clearly above-average across all tasks jointly.
- **a (discrimination)**: how strongly the task separates good from bad agents. a<0.5 = task doesn't inform the ranking, consider dropping.
- **b (difficulty)**: the θ value at which agents flip from mostly-fail to mostly-succeed. b < -2 = trivial; b > 2 = saturated-hard. Mid-range b (−1..+1) is ideal.

## Flags

- **OK**: mid-range b, healthy a. Keep.
- **LOW_DISCRIM**: |a|<0.5, task doesn't separate agents. Rewrite or drop.
- **SATURATED**: |b|>2.5, everyone succeeds or fails. No signal.
- **INVERTED**: a<0, worse agents score higher — suspicious scorer bug (e.g. length-rewarding pillar pulls longer bad reports above shorter good ones).
