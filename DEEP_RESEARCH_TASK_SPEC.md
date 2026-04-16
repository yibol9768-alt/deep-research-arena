# Deep Research Task Spec

What separates a **deep research task** from a plain WebArena UI task.

## 1. Minimum criteria

A task is "deep research" iff it satisfies all four:

1. **Multi-step retrieval** — agent must visit ≥ 3 distinct pages / fire ≥ 3 search queries.
   (Single-page lookup → not deep research.)
2. **Cross-source synthesis** — the answer must integrate data from ≥ 2 independent
   items (products, reviews, listings, categories). Not a single fact lookup.
3. **Structured report output** — agent returns a JSON object whose schema is defined
   in the task file. No free-form prose as the only answer.
4. **Citations** — every non-trivial fact in the report carries a source URL inside the
   sandboxed environment, verifiable via `citation_verifier`.

## 2. Shape of a task file

Extends the existing WebArena-style JSON with three new sections. File lives at
`data/tasks/deep_research/<site>/<task_id>.json`:

```jsonc
{
  "task_id": "dr_shop_0001",
  "sites": ["shopping"],
  "intent": "Compare the three highest-rated blue winter jackets under $150 ...",
  "start_url": "__SHOPPING__/",
  "storage_state": null,

  // NEW: expected output schema
  "report_schema": {
    "type": "object",
    "properties": {
      "products": {
        "type": "array",
        "minItems": 3, "maxItems": 3,
        "items": {
          "type": "object",
          "required": ["name", "price", "rating", "product_url"],
          "properties": {
            "name":        {"type": "string"},
            "price":       {"type": "number"},
            "rating":      {"type": "number", "minimum": 0, "maximum": 5},
            "product_url": {"type": "string", "format": "uri"}
          }
        }
      },
      "recommendation": {"type": "string"}
    },
    "required": ["products", "recommendation"]
  },

  // NEW: citation requirements
  "citation_policy": {
    "required_for": ["products[*].price", "products[*].rating"],
    "must_be_in_domain": ["__SHOPPING__"],
    "min_distinct_sources": 3
  },

  // NEW: deterministic verification
  "eval": {
    "eval_types": ["report_match", "citation_check"],
    "report_expected": {
      "products": [
        {"name_contains": ["Navy", "Jacket"], "price_range": [50, 150], "rating_min": 4.0}
      ]
    },
    "source_count_min": 3
  }
}
```

## 3. Rules the author must enforce

- **Deterministic answer** — there is a *unique*, *canonical* output (modulo ordering
  of equal items). If two valid answers exist, disambiguate via the task statement.
- **Verifiable without LLM judge** — every field in `report_schema` must be checkable
  by regex / numeric range / URL reachability. No "write a 200-word summary" fields.
- **Solvable by a human in ≤ 15 minutes** — measured during Oracle writing.
- **Non-trivial for an LLM** — expected SOTA ≤ 60% first-try success. If a naive
  zero-shot agent hits 90%+, the task is too easy; add constraints.
- **Scoped to the sandbox** — all required information must live inside one or more
  of our hosted sites. No external web needed.

## 4. Difficulty ladder (shopping, Stage B)

| # | Task sketch                                                | Expected steps | Primary difficulty                  |
|---|------------------------------------------------------------|----------------|-------------------------------------|
| 1 | Top-3 highest-rated blue winter jackets under $150         |  6–10          | Faceted search + ranking            |
| 2 | Bestseller vs. highest-rated differences in `Home & Kitchen` | 10–15        | Two-list intersection analysis      |
| 3 | Top-3 complaints in 1-star reviews of product X            | 10–20          | Review aggregation + clustering     |
| 4 | Price gradient of brand X across 4 categories              | 12–18          | Cross-category filter + arithmetic  |
| 5 | Optimal product under 5 combined constraints + rationale   | 15–25          | Multi-constraint optimization       |

Each is fully specified in `data/tasks/deep_research/shopping/dr_shop_000X.json`.

## 5. Verifier chain

`eval_types` on a deep research task uses two new verifier kinds:

- `report_match` — runs against `report_schema` + `report_expected`:
  - JSON Schema validation (structure + types)
  - Field-level constraints: `name_contains`, `price_range`, `rating_min`, `url_regex`
  - Set comparison for list fields (as multiset, order-insensitive unless specified)
- `citation_check` — runs against `citation_policy`:
  - Every required field has a non-empty `_source` sibling or a `citations` block
  - Each citation URL is reachable (HTTP 200) within the sandbox
  - Each citation URL's page actually contains the claimed value (text match)
  - Distinct-source count meets `min_distinct_sources`

Both verifiers return 0/1 scores; runner multiplies them (WebArena convention).

## 6. Oracle writing protocol

For every task file we ship, we also ship `envs/<site>/oracle/<task_id>_oracle.py`
with a hand-written Playwright solution that:

1. Navigates and collects exactly the ground-truth answer.
2. Returns a JSON string matching `report_schema` — including citations.
3. Must score 1.0 against both `report_match` and `citation_check`.

This gates task quality: if the author can't write an Oracle that passes, the task
is under-specified.

## 7. Anti-patterns

- ❌ Pure UI mechanics ("click 'add to cart'") — that's WebArena, not DR.
- ❌ LLM-as-judge scoring — breaks determinism.
- ❌ "Write a summary of" / "explain" — unscoreable prose.
- ❌ Citations pointing outside the sandbox.
- ❌ Ground truth that changes between container resets (reset.sh must yield byte-identical answers).
