# Deep Research Task v3 — Spec

> Replaces v2 (which forced rigid JSON output and admitted single-page
> aggregation tasks). v3 demands real **multi-page research** producing
> a **long-form markdown report**, scored by a hybrid **KG-grounded
> objective layer + DRACO rubric subjective layer**.

## What counts as a v3 deep-research task

Every v3 task **must** satisfy ALL of:

1. **Multi-page browsing** — solving requires the agent to visit ≥ 3
   distinct pages (not just one listing page). Examples: a category
   listing + N product detail pages; multiple forums + multiple
   submissions.

2. **Multi-entity synthesis** — the answer must integrate facts about
   ≥ 5 distinct entities (products, posts, users, reviews) — not a
   single fact lookup or a single-list top-N.

3. **Argued conclusion** — the report must contain a "why" paragraph
   that motivates the final claim with the gathered evidence. A bare
   list of facts is not enough.

4. **Markdown long-form output** — agent emits a markdown report that
   meets the task's `markdown_spec`:
   - `min_words` (default 500)
   - `max_words` (default 4000)
   - `min_paragraphs` (default 3)
   - `min_citations` (default 5 inline `[text](url)` markdown links)
   - `min_pages_browsed` (default 3 — verified via the runner's tool log)

5. **Sandboxed citations** — every cited URL is on the local sandbox
   (`http://localhost:7770/...` for shopping, `:9999/...` for reddit).
   No open-web URLs.

## Task file shape (v3)

`data/tasks/deep_research/<site>/dr_<site>_v3_<NNNN>.json`:

```jsonc
{
  "schema_version": "3.0.0",
  "task_id": "dr_shop_v3_0001",
  "sites": ["shopping"],
  "intent": "Compare three headphone form-factors (over-ear, on-ear, earbud) ...",
  "start_url": "__SHOPPING__/",
  "storage_state": null,
  "require_login": false,

  "markdown_spec": {
    "min_words": 600,
    "max_words": 2500,
    "min_paragraphs": 4,
    "min_citations": 6,
    "min_pages_browsed": 5
  },

  "citation_policy": {
    "required_for": [],
    "must_be_in_domain": ["__SHOPPING__"],
    "min_distinct_sources": 5
  },

  "golden": {
    "triples_path": "data/golden/dr_shop_v3_0001.json",
    "expected_predicates": ["price", "rating", "review_count", "category"]
  },

  "coverage_checklist_path": "data/tasks/deep_research/shopping/checklists_v3.json",

  "difficulty": 3,
  "expected_steps": 12,
  "author_notes": "Requires browsing the catalog landing + 3 sub-categories + ≥3 product pages."
}
```

## Golden answer (Layer 1)

The task's Oracle (in `envs/<site>/oracle_dr_v3/`) writes both:

1. **A reference markdown report** — what a "top-quality" researcher
   would write. Used by the rubric judge as a reference, and as a
   sanity check for fact_kg_verifier (recall ≥ 0.8 on the oracle's
   own report).

2. **A KG triples JSON** at `golden.triples_path`:

   ```json
   [
     {"subject": "Harphonic E7", "predicate": "price",  "object": "34.99"},
     {"subject": "Harphonic E7", "predicate": "rating", "object": "4.3"},
     {"subject": "Harphonic E7", "predicate": "review_count", "object": "12"},
     {"subject": "TECNO N1",     "predicate": "price",  "object": "39.99"},
     ...
   ]
   ```

   The `fact_kg_verifier` matches an agent's claim triples against this
   golden set; the Magento/Postmill DB serves as the authoritative
   source for any predicate listed in `golden.expected_predicates`.

## Coverage checklist (Layer 2 subjective)

`data/tasks/deep_research/<site>/checklists_v3.json` contains, per
task_id, a list of ~15 binary criteria following DRACO's principles:

- **Dimension separation** — a criterion lives in exactly one of the
  4 dimensions (Comprehensiveness / Insight / Citation Quality / Readability).
- **Binary** — judge outputs PASS/FAIL only; no Likert scale.
- **Includes negative criteria** (penalize errors), e.g.
  "Report does NOT include products outside the requested category".
- **Independence** — pairwise Spearman ρ < 0.7 across criteria
  (sanity-check after authoring).

## Scoring (Composite v3)

| Pillar | Weight | Implementation |
|---|---:|---|
| Markdown structure | 0.10 | `MarkdownReportVerifier` — checks `markdown_spec` lower bounds |
| Citation (ALCE F1) | 0.15 | `CitationVerifier` (reused from v2, prose mode) |
| **Fact KG** | **0.30** | `FactKGVerifier` — claims → triples → Magento/Postmill DB lookup |
| LLM Judge (4-dim) | 0.20 | `LLMJudgeVerifier` (reused from v2) |
| **Coverage Checklist** | **0.20** | `ChecklistVerifier` with ~15 binary criteria/task, 3-sample mean |
| Efficiency | 0.05 | `EfficiencyMetrics` |

`Composite = Σ pillar.score × pillar.weight ∈ [0, 1]`

## Anti-patterns (don't ship a task that does these)

- ❌ Task answerable from a single listing page → not v3, that's v2 fluff
- ❌ Task whose answer changes between container resets → can't have stable golden
- ❌ Task requiring login but no `storage_state` configured
- ❌ Citations pointing outside the sandbox (open web)
- ❌ "Write a 200-word summary about X" — unscoreable subjective ask
- ❌ Reference report longer than `max_words` cap → indicates the
  task is too broad, split it
