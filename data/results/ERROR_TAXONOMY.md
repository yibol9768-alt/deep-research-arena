# Error Taxonomy — Per-Agent Failure Distribution

**105** runs scanned (heuristic, no LLM calls).

## Totals by primary class

- **ok**: 57 runs
- **hallucination_url**: 34 runs
- **timeout_or_empty**: 14 runs

## Per-agent primary class distribution

| Agent | ok | tool_misuse | hallucination_url | format_error | timeout_or_empty | total |
|---|---:|---:|---:|---:|---:|---:|
| camel-ai | 3 | 0 | 1 | 0 | 0 | 4 |
| camel-ai-ds | 8 | 0 | 0 | 0 | 0 | 8 |
| deerflow-ds | 3 | 0 | 1 | 0 | 0 | 4 |
| deerflow-glm46 | 4 | 0 | 0 | 0 | 0 | 4 |
| deerflow-glm46-new | 4 | 0 | 0 | 0 | 0 | 4 |
| deerflow-glm46-shim | 4 | 0 | 0 | 0 | 0 | 4 |
| gpt-researcher | 4 | 0 | 4 | 0 | 0 | 8 |
| gpt-researcher-ds | 0 | 0 | 8 | 0 | 0 | 8 |
| gpt5chat | 16 | 0 | 0 | 0 | 0 | 16 |
| odr-ds | 0 | 0 | 8 | 0 | 0 | 8 |
| react-glm45 | 0 | 0 | 0 | 0 | 3 | 3 |
| react-glm46 | 1 | 0 | 0 | 0 | 3 | 4 |
| react-glm5 | 4 | 0 | 0 | 0 | 1 | 5 |
| react-glm51 | 2 | 0 | 0 | 0 | 5 | 7 |
| react-qwen35plus | 4 | 0 | 0 | 0 | 2 | 6 |
| smolagents | 0 | 0 | 4 | 0 | 0 | 4 |
| smolagents-ds | 0 | 0 | 8 | 0 | 0 | 8 |

## Top secondary flags per agent

- **camel-ai**: zero_wiki_cites(4), only_one_source_host(2), no_inline_cites(1)
- **camel-ai-ds**: zero_wiki_cites(4), only_one_source_host(4)
- **deerflow-ds**: zero_wiki_cites(4)
- **deerflow-glm46**: zero_wiki_cites(4), very_long_report(3)
- **deerflow-glm46-new**: zero_wiki_cites(4), only_one_source_host(1)
- **deerflow-glm46-shim**: zero_wiki_cites(4)
- **gpt-researcher**: zero_wiki_cites(8)
- **gpt-researcher-ds**: zero_wiki_cites(8), only_one_source_host(2)
- **gpt5chat**: zero_wiki_cites(8), only_one_source_host(4)
- **odr-ds**: no_inline_cites(8), zero_wiki_cites(8)
- **react-glm45**: no_inline_cites(3), zero_wiki_cites(3), very_short_report(3)
- **react-glm46**: zero_wiki_cites(4), no_inline_cites(3), very_short_report(3)
- **react-glm5**: zero_wiki_cites(5), only_one_source_host(1), no_inline_cites(1), very_short_report(1)
- **react-glm51**: zero_wiki_cites(7), no_inline_cites(5), very_short_report(5)
- **react-qwen35plus**: zero_wiki_cites(6), no_inline_cites(2), very_short_report(2)
- **smolagents**: zero_wiki_cites(4), no_inline_cites(3)
- **smolagents-ds**: zero_wiki_cites(8), no_inline_cites(7), very_short_report(4)

## What this tells us

- `hallucination_url` rate ≥ 50% on an agent → that agent is NOT graded fairly by our citation pillar (it's gaming URLs).
- `format_error` rate > 20% → runner issue (e.g. JSON wrap unwrapping failed — check the runner code, not the agent).
- `tool_misuse` rate high → prompting issue — try a more explicit ReAct template.
- `zero_wiki_cites` dominant across agents → shim indexing bug or agents don't know to query wikipedia. Good signal post-#52.
