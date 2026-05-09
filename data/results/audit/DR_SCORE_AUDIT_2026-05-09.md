# Deep-Research score audit (2026-05-09)

Source directory: `data\results\deep_v3` (rank order from leaderboard: camel-ai, flowsearcher-ds, smolagents, ldr, gpt-researcher, deerflow, ii-researcher, langchain-odr, storm)

## Summary

- Total score files: **344**
- Kept after degenerate filter: **283**
- Dropped: **61**
- Agents in Elo: camel-ai, deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, smolagents, storm
- Agents excluded: qx-agents
- Verdict: **FAIL**

## Table A: per-agent summary

| agent | files | kept | dropped | mean v2 | median v2 | mean v1 | mean answer_chars | n(reach=0) | n(reach=1) | n(checklist judge_err) | drop reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| camel-ai | 56 | 56 | 0 | 0.410 | 0.407 | 0.458 | 29210 | 1 | 15 | 0 | 0 short, 0 infra, 0 judge_err |
| flowsearcher-ds | 48 | 30 | 18 | 0.296 | 0.277 | 0.383 | 19426 | 18 | 3 | 18 | 18 short, 0 infra, 0 judge_err |
| smolagents | 30 | 30 | 0 | 0.226 | 0.225 | 0.294 | 15903 | 3 | 9 | 0 | 0 short, 0 infra, 0 judge_err |
| ldr | 30 | 30 | 0 | 0.029 | 0.023 | 0.044 | 1671 | 10 | 19 | 0 | 0 short, 0 infra, 0 judge_err |
| gpt-researcher | 30 | 30 | 0 | 0.013 | 0.009 | 0.388 | 25740 | 14 | 0 | 0 | 0 short, 0 infra, 0 judge_err |
| deerflow | 30 | 30 | 0 | 0.023 | 0.000 | 0.194 | 24109 | 22 | 1 | 0 | 0 short, 0 infra, 0 judge_err |
| ii-researcher | 30 | 30 | 0 | 0.001 | 0.000 | 0.196 | 5658 | 28 | 0 | 0 | 0 short, 0 infra, 0 judge_err |
| langchain-odr | 30 | 30 | 0 | 0.001 | 0.000 | 0.269 | 26951 | 26 | 0 | 0 | 0 short, 0 infra, 0 judge_err |
| storm | 30 | 17 | 13 | 0.000 | 0.000 | 0.129 | 124 | 30 | 0 | 0 | 13 short, 0 infra, 0 judge_err |
| qx-agents | 30 | 0 | 30 | — | — | — | 367 | 30 | 0 | 30 | 30 short, 0 infra, 0 judge_err |


## Table B: per-task coverage

| task | agents_scored | agents_kept | agents_missing | golden_must_cite | golden_n_sources | status |
|---|---:|---:|---|---:|---:|:---:|
| dr_cross_deep_0001 | 10 | 8 | — | 121 | 3 | OK |
| dr_cross_deep_0002 | 10 | 8 | — | 120 | 3 | OK |
| dr_cross_deep_0003 | 10 | 8 | — | 127 | 3 | OK |
| dr_cross_deep_0004 | 10 | 8 | — | 128 | 3 | OK |
| dr_cross_deep_0005 | 10 | 8 | — | 123 | 3 | OK |
| dr_cross_deep_0006 | 10 | 8 | — | 126 | 3 | OK |
| dr_cross_deep_0007 | 10 | 8 | — | 130 | 3 | OK |
| dr_cross_deep_0008 | 10 | 8 | — | 129 | 3 | OK |
| dr_cross_deep_0009 | 10 | 8 | — | 128 | 3 | OK |
| dr_cross_deep_0010 | 10 | 8 | — | 124 | 3 | OK |
| dr_cross_deep_0011 | 10 | 8 | — | 129 | 3 | OK |
| dr_cross_deep_0012 | 10 | 8 | — | 128 | 3 | OK |
| dr_cross_deep_0013 | 10 | 9 | — | 141 | 3 | OK |
| dr_cross_deep_0014 | 10 | 9 | — | 141 | 3 | OK |
| dr_cross_deep_0015 | 10 | 9 | — | 149 | 3 | OK |
| dr_cross_deep_0016 | 10 | 9 | — | 123 | 3 | OK |
| dr_cross_deep_0017 | 10 | 9 | — | 123 | 3 | OK |
| dr_cross_deep_0018 | 10 | 9 | — | 128 | 3 | OK |
| dr_cross_deep_0019 | 10 | 9 | — | 124 | 3 | OK |
| dr_cross_deep_0020 | 10 | 9 | — | 127 | 3 | OK |
| dr_cross_deep_0021 | 10 | 9 | — | 127 | 3 | OK |
| dr_cross_deep_0022 | 10 | 9 | — | 125 | 3 | OK |
| dr_cross_deep_0023 | 10 | 9 | — | 126 | 3 | OK |
| dr_cross_deep_0024 | 10 | 8 | — | 126 | 3 | OK |
| dr_cross_deep_0025 | 10 | 9 | — | 127 | 3 | OK |
| dr_cross_deep_0026 | 10 | 9 | — | 128 | 3 | OK |
| dr_cross_deep_0027 | 10 | 9 | — | 128 | 3 | OK |
| dr_cross_deep_0028 | 10 | 9 | — | 127 | 3 | OK |
| dr_cross_deep_0029 | 10 | 9 | — | 130 | 3 | OK |
| dr_cross_deep_0030 | 10 | 9 | — | 129 | 3 | OK |
| dr_cross_deep_0031 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 120 | 3 | WARN |
| dr_cross_deep_0032 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 133 | 3 | WARN |
| dr_cross_deep_0033 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 144 | 3 | WARN |
| dr_cross_deep_0034 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 149 | 3 | WARN |
| dr_cross_deep_0035 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 143 | 3 | WARN |
| dr_cross_deep_0036 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 149 | 3 | WARN |
| dr_cross_deep_0037 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 129 | 3 | WARN |
| dr_cross_deep_0038 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 140 | 3 | WARN |
| dr_cross_deep_0039 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 138 | 3 | WARN |
| dr_cross_deep_0040 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 129 | 3 | WARN |
| dr_cross_deep_0041 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 140 | 3 | WARN |
| dr_cross_deep_0042 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 126 | 3 | WARN |
| dr_cross_deep_0043 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 144 | 3 | WARN |
| dr_cross_deep_0044 | 1 | 0 | camel-ai, deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 128 | 3 | WARN |
| dr_cross_deep_0045 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 136 | 3 | WARN |
| dr_cross_deep_0046 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 144 | 3 | WARN |
| dr_cross_deep_0047 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 141 | 3 | WARN |
| dr_cross_deep_0048 | 2 | 1 | deerflow, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 145 | 3 | WARN |
| dr_cross_deep_0049 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 142 | 3 | WARN |
| dr_cross_deep_0050 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 130 | 3 | WARN |
| dr_cross_deep_0051 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 143 | 3 | WARN |
| dr_cross_deep_0052 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 141 | 3 | WARN |
| dr_cross_deep_0053 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 132 | 3 | WARN |
| dr_cross_deep_0054 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 133 | 3 | WARN |
| dr_cross_deep_0055 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 127 | 3 | WARN |
| dr_cross_deep_0056 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 134 | 3 | WARN |
| dr_cross_deep_0057 | 1 | 1 | deerflow, flowsearcher-ds, gpt-researcher, ii-researcher, langchain-odr, ldr, qx-agents, smolagents, storm | 139 | 3 | WARN |


## Table C: anomalies

| agent | task | composite_v2 | reason |
|---|---|---:|---|
| deerflow | dr_cross_deep_0001 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0002 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0003 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0004 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0005 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0006 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0007 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0008 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0009 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0010 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0012 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0013 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0014 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0015 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0016 | 0.186 | composite_v2 outlier: |c - median| = 0.186 > 3*sd (0.047) |
| deerflow | dr_cross_deep_0017 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0019 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0023 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0024 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0028 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| deerflow | dr_cross_deep_0030 | 0.000 | composite_v2=0.000 repeats across 22 tasks for deerflow (template/cache tell) |
| gpt-researcher | dr_cross_deep_0001 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0006 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0008 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0009 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0010 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0011 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0014 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0015 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0018 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0022 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0024 | 0.086 | composite_v2 outlier: |c - median| = 0.077 > 3*sd (0.019) |
| gpt-researcher | dr_cross_deep_0025 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| gpt-researcher | dr_cross_deep_0030 | 0.000 | composite_v2=0.000 repeats across 14 tasks for gpt-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0002 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0003 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0004 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0005 | 0.020 | composite_v2 outlier: |c - median| = 0.020 > 3*sd (0.004) |
| ii-researcher | dr_cross_deep_0006 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0007 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0008 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0009 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0010 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0011 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0012 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0013 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0014 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0015 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0016 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0017 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0018 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0019 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0020 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0022 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0023 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0024 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0025 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0027 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0028 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0029 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| ii-researcher | dr_cross_deep_0030 | 0.000 | composite_v2=0.000 repeats across 28 tasks for ii-researcher (template/cache tell) |
| langchain-odr | dr_cross_deep_0001 | 0.014 | composite_v2 outlier: |c - median| = 0.014 > 3*sd (0.004) |
| langchain-odr | dr_cross_deep_0003 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0004 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0005 | 0.014 | composite_v2 outlier: |c - median| = 0.014 > 3*sd (0.004) |
| langchain-odr | dr_cross_deep_0006 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0007 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0008 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0009 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0010 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0011 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0012 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0013 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0014 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0015 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0017 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0018 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0019 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0020 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0022 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0023 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0024 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0025 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0027 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0028 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0029 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| langchain-odr | dr_cross_deep_0030 | 0.000 | composite_v2=0.000 repeats across 26 tasks for langchain-odr (template/cache tell) |
| ldr | dr_cross_deep_0001 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0002 | 0.042 | composite_v2=0.042 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0003 | 0.080 | composite_v2=0.080 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0004 | 0.080 | composite_v2=0.080 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0005 | 0.042 | composite_v2=0.042 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0006 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0007 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0008 | 0.080 | composite_v2=0.080 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0009 | 0.042 | composite_v2=0.042 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0010 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0011 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0012 | 0.080 | composite_v2=0.080 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0015 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0016 | 0.080 | composite_v2=0.080 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0017 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0018 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0019 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0020 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0022 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0023 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0024 | 0.042 | composite_v2=0.042 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0025 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0027 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0028 | 0.042 | composite_v2=0.042 repeats across 5 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0029 | 0.000 | composite_v2=0.000 repeats across 10 tasks for ldr (template/cache tell) |
| ldr | dr_cross_deep_0030 | 0.023 | composite_v2=0.023 repeats across 8 tasks for ldr (template/cache tell) |
| storm | dr_cross_deep_0013 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0014 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0015 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0016 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0017 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0018 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0019 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0020 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0021 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0022 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0023 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0025 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0026 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0027 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0028 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0029 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |
| storm | dr_cross_deep_0030 | 0.000 | composite_v2=0.000 repeats across 17 tasks for storm (template/cache tell) |

