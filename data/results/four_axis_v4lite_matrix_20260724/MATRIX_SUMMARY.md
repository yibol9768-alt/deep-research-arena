# Same-task v4lite harness matrix

All semantic decisions were made by `deepseek-v4-flash`; manual claim decisions: 0. Scores are diagnostic, not formal leaderboard results.

| Harness | Run | Truth | P | Fact (resolution) | Evidence (P/R) | Completeness | Rubric | Full/snippet pages | Citations observed/total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gpt-researcher | audit-warning | 0.841 | 1.000 | 1.000 (0.633) | 0.474 (0.682/0.363) | 1.000 | 0.889 | 0/20 | 10/10 |
| opencode | clean | 0.741 | 1.000 | 0.966 (0.504) | 0.000 (0.000/0.000) | 1.000 | 1.000 | 0/95 | 2/2 |
| claude-code | audit-warning | 0.704 | 1.000 | 0.821 (0.341) | 0.048 (1.000/0.024) | 0.946 | 1.000 | 2/57 | 2/4 |
| storm | clean | 0.698 | 1.000 | 1.000 (0.630) | 0.238 (0.327/0.188) | 0.833 | 0.722 | 0/48 | 11/11 |
| ii-researcher | clean | 0.665 | 1.000 | 1.000 (0.403) | 0.080 (1.000/0.042) | 0.804 | 0.778 | 27/0 | 3/3 |
| ldr | clean | 0.626 | 1.000 | 0.768 (0.640) | 0.707 (0.856/0.602) | 0.679 | 0.350 | 40/0 | 31/31 |
| langchain-odr | audit-warning | 0.561 | 0.833 | 0.911 (0.596) | 0.197 (0.378/0.133) | 0.807 | 0.778 | 206/0 | 5/5 |
| camel-ai | clean | 0.000 | 0.000 | 0.750 (0.145) | 0.000 (0.000/0.000) | 0.719 | 0.444 | 0/14 | 0/1 |
| deerflow | clean | 0.000 | 0.000 | 1.000 (0.472) | 0.000 (0.000/0.000) | 0.798 | 0.500 | 2/67 | 0/2 |
| miroflow | clean | 0.000 | 0.000 | 0.929 (0.571) | 0.000 (0.000/0.000) | 0.629 | 0.889 | 4/193 | 0/0 |
| qx-agents | non-delivery | 0.000 | 0.000 | 0.000 (—) | 0.000 (0.000/0.000) | 0.000 | 0.000 | 0/58 | —/— |
| smolagents | clean | 0.000 | 0.000 | 0.667 (0.290) | 0.000 (0.000/0.000) | 0.722 | 0.889 | 0/0 | 0/0 |
