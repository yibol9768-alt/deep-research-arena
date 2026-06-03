# Why agents score high or low (real 12-task run, 145 battles)

Source: `data/results/real/leaderboard_real_full.json` + per-pillar `data/results/deep_v3/*.score.json`.
Scoring = two numbers + a gate: GROUNDING (citation precision with proof-of-fetch x must-cite recall) and QUALITY (length-controlled pairwise Bradley-Terry Elo, DeepSeek lite judge). A report must clear the grounding floor (0.30) to be ranked.

| agent | quality Elo | grounding | quote-match | must-cite recall | avg chars | W/L/D | verdict |
| ----- | ----------- | --------- | ----------- | ---------------- | --------- | ----- | ------- |
| gpt-researcher | 1320 (highest) | 0.00 | 0.00 | 0.000 | 25.7k | 34/5/14 | fluent hallucinator: most-preferred prose but citations match no fetched page; grounding 0 -> GATED |
| langchain-odr | 1206 | 0.00 | 0.00 | 0.000 | 27.0k | 26/13/14 | same: fluent, zero grounding -> GATED |
| claude-code | 1167 | 0.44 (highest) | 0.86 (highest) | 0.028 | 50.6k | 11/8/6 | grounded AND high quality -> legitimate #1 |
| smolagents | 1165 | 0.33 | 0.63 | 0.055 (highest) | 15.9k | 22/15/16 | enough grounding + best must-cite recall -> #2 |
| camel-ai | 1123 | 0.40 | 0.78 | 0.033 | 29.2k | 20/19/14 | steady grounding -> #3 |
| storm | 19 (lowest) | 0.00 | 0.00 | 0 | 123 chars | 0/53/0 | near-empty reports (123 chars, 0 citations) -> bottom |

## The story
- The raw QUALITY ranking would put gpt-researcher and langchain-odr on top: they write the prose the judge most prefers (gpt-researcher won 34 of 53 battles). But their `quote_match` is 0.00, meaning the pages they cite do not support their claims (fabricated or non-grounded citations). The truth-gate correctly removes both, which is the entire point of the design: fluency must not beat grounding.
- claude-code is the legitimate #1 because it is the only agent that is both well-grounded (quote_match 0.86, the highest) and high quality. Its earlier #1 on the public site was a synthetic placeholder; now it earns the rank.
- smolagents and camel-ai are genuine mid-tier grounded reporters.
- storm collapses because its reports are essentially empty (123 chars, 0 citations, lost every battle).

## Implication for fairness
The old composite rewarded citation VOLUME and reachable-but-non-golden URLs, which let fluent-but-ungrounded agents and even synthetic placeholders top the board. The new two-number-plus-gate scheme ranks on grounded quality, so the ordering now matches what a human reviewer would call fair: a report that cites nothing verifiable does not win, no matter how fluent.
