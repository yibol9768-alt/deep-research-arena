# GLM-5.1 ReAct Baseline — Stage B (shopping)

**Date**: 2026-04-16
**Model**: `glm-5.1` via `https://open.bigmodel.cn/api/anthropic`
**Agent**: `src/agents/glm_react_agent.py` (8 tools, MAX_STEPS=20)
**Environment**: webarena shopping @ `http://localhost:7770` (SSH tunnel to westd/WSL)

## Summary

| Task         | report_match | citation_check | Overall | Time   |
|--------------|:-----------:|:--------------:|:-------:|--------|
| dr_shop_0001 | ✓            | ✗              | FAIL    | 101.5s |
| dr_shop_0002 | ✓            | ✗              | FAIL    | 169.3s |
| dr_shop_0003 | ✗ (no answer)| —              | FAIL    | 127.7s |
| dr_shop_0004 | ✗ (no answer)| ✗              | FAIL    | 159.7s |
| dr_shop_0005 | ✓            | ✗              | FAIL    | 111.8s |

**Overall**: 0/5 pass end-to-end. report_match: **3/5**, citation_check: **0/5**.

## Failure modes

1. **Citation omission (5/5)** — Agent returns structurally correct JSON but
   never populates `citations`. It treats citations as optional even though
   the task spec states they're required. System-prompt reminder needed.
2. **Tool-budget exhaustion (2/5)** — On tasks 3 (reviews aggregation) and 4
   (two-product enrichment), the agent spends all 20 tool steps exploring
   and never calls `finish`. Likely cause: per-tool-response truncation
   (8KB cap) forces repeated re-scrapes.

## Interpretation vs. Stage B exit criteria

Exit criterion (ROADMAP.md §Stage B):
> at least 3 of 5 Oracle PASS, **AND** LLM agent scores < 60%.

- Oracle: **5/5 pass** (after fixing verifier null-constraint bug). ✓
- LLM agent: **0/5 pass** (0% ≪ 60%). ✓ (below the ceiling, meaning tasks
  are non-trivial; but 0% is maybe *too* hard for a "first-try" agent —
  the citation gap is a single failure mode, not 5 distinct difficulties).

**Verdict**: Stage B assumption holds with caveats. The "real website +
deep-research task + deterministic eval" stack functions end-to-end. The
current tasks test one main dimension (citation discipline) more than
they test depth of research. Next iteration should make task 1 solvable
by a smart agent so the scoring differentiates more sharply.

## Next actions (not yet started)

- Tighten `_SYSTEM_PROMPT` to REQUIRE a `citations` array and re-run.
- Bump MAX_STEPS to 30 on complex tasks (or give agent a `summarize` tool).
- Write a second baseline with `claude-sonnet-4-6` as a ceiling benchmark.
- Design 2–3 more tasks that require cross-category reasoning (not just
  "sort by X then take top 3").
- Then — and only then — start Stage C (reddit/gitlab/map/wiki).
