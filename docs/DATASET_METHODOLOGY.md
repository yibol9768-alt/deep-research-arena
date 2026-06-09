# Deep-Tier Task Construction Methodology

*For paper section 3. Every decision defended here is intended to be machine-reproducible, and every agent run against this dataset can be cross-checked against the artefacts described below.*

---

## 1. Why a deep tier

The existing Deep Research benchmarks (DeepResearch Bench, DRACO,
BrowseComp-Plus) score agents on single-site or shallow cross-site
questions — typical ground truth sets range from 3 to 20 citations.
Under such scopes, any agent that emits a plausibly-structured
markdown report with N citations — real or invented — scores well
under LLM-judge composites because the judge cannot verify URLs.

Our **shallow tier** (87 × cross-site tasks in
`data/tasks/deep_research/cross_site`) exhibits the same weakness:
every agent in our 2026-04 arena passes the citation threshold with
a ≥ 95 % judge-rated success rate even when we later discover its
URLs are 404 on the sandbox.

The **deep tier** imposes a scope no agent can satisfy by
hallucinating: each task requires ≥ 100 distinct, URL-resolvable
citations spanning three orthogonal source types. At this breadth
the LLM's training-prior URL patterns stop matching reality, and
the gap between "fluent report" and "grounded research" becomes
measurable.

## 2. Task design constraints

A deep-tier task MUST satisfy all of:

| # | Constraint | Verifier |
|---|---|---|
| C1 | ≥ 120 sandbox URLs touched during research | trace inspection (future) |
| C2 | ≥ 60 URLs cited as markdown links in final report | `markdown_spec.min_citations` |
| C3 | Citations span ≥ 3 distinct sandbox domains | `url_coverage.per_domain_minimum` |
| C4 | Every cited URL returns HTTP 200 on the sandbox | `URLReachabilityVerifier` |
| C5 | ≥ 50 % of a curated must-cite pool appears in the report | `URLCoverageVerifier.must_cite_recall` |
| C6 | Report is 3500–8000 words, ≥ 25 paragraphs | `markdown_spec.min_words` |
| C7 | Synthesis section surfaces ≥ 5 cross-source contradictions or rankings | checklist judge |

C4 is the binding constraint. C1–C3 + C6 are *structural* — they can
be gamed by fluent fabrication. C4 cannot be gamed: a citation either
resolves on the sandbox or does not.

## 3. Three-dimensional task template

Every deep task is constructed from three orthogonal data
sources of the sandbox:

| Dim | Sandbox source | Typical URL pattern | Count in sandbox |
|---|---|---|---|
| A. **Product landscape** | Magento shopping | `http://localhost:7770/<slug>.html` | ≈ 2 000 items |
| B. **Community sentiment** | Postmill reddit clone | `http://localhost:9999/f/<forum>/<id>/<slug>` | 30+ subforums × N threads |
| C. **Technical grounding** | Kiwix Wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/<title>` | ≈ 6 M articles |

The task prompt requires the agent to **triangulate** between the
three: a claim made in (A) must be supported by (C), questioned or
endorsed by (B), and the synthesis must surface cross-source
contradictions.

A shallow-tier task typically uses one dimension (e.g. shopping
search) or two (shopping + reddit). The deep tier requires all three
for every task.

## 4. Scraping protocol

Given a topic (e.g. `audio_headphones`), the scraper enumerates:

```
shopping:
  - catalogsearch/result/?q=<kw>&p=1..3  for each kw in KEYWORDS
  - extract product URLs from .product-item-link
  - per product page: parse price / rating / review_count + feature claims

reddit:
  - /f/<forum>  for each forum in FORUMS (list + pagination)
  - extract thread URLs matching keyword filter
  - /search?q=<kw> fallback for recall
  - per thread: parse score / comment_count / classification

wiki:
  - for each mandatory term in WIKI_MANDATORY and extra terms in WIKI_EXTRA,
    try /content/<zim>/A/<slug> with slug variants (exact / sans parens / underscored)
  - parse first paragraph as defining statement
```

All fetches are retried up to 3 times with exponential back-off.
Parse failures are logged but non-fatal; the resulting golden is
stamped with `metadata.partial = true` if any section misses quota.

Empirically, one topic × 9 keywords × 7 forums × 27 wiki terms
generates **≈ 700–800 pool URLs, 120+ must-cite URLs, 500+ fact
triples** in 30–45 minutes of sandbox-local traffic.

## 5. Golden construction

The scraper emits a JSON file with the following top-level keys:

```jsonc
{
  "task_id": "dr_cross_deep_<NNNN>",
  "generated_at": "<ISO timestamp>",
  "must_cite_urls": [                         // weighted targets the agent SHOULD cite
    {"url": "...", "category": "shopping_product", "weight": 1.0, "why": "..."},
    ...
  ],
  "expected_pool_urls": [                     // broader URL pool; citation counted if any hit
    {"url": "...", "category": "..."},
    ...
  ],
  "triples": [                                // fact triples for fact-KG verifier
    {"subject": "...", "predicate": "price", "object": "41.88", "source_url": "..."},
    ...
  ],
  "metadata": {
    "shopping": {"products_discovered": N, ...},
    "reddit":   {"threads_discovered": N, "forum_coverage": {...}},
    "wiki":     {"articles_found": N, ...},
    "summary":  {"n_must_cite": ..., "n_expected_pool": ..., "n_triples": ...}
  }
}
```

**Weight assignment** for `must_cite_urls`:
- `weight = 1.0` — "gold" entry (shopping product with full price + rating + review_count, or mandatory wiki article)
- `weight = 0.8` — shopping product with price + one of (rating, review_count)
- `weight = 0.7` — non-mandatory wiki article
- `weight = 0.6` — reddit thread with partial metadata
- `weight = 0.5` — shopping product with price only

Weighted recall in the URL coverage verifier gives proportional credit
so that agents are not penalised for failing to cite sparse low-weight
URLs they could not discover.

## 6. Difficulty calibration

A topic's difficulty is set by tuning four knobs:

| Knob | Easy | Medium | Hard |
|---|---|---|---|
| Product count target | 20 | 40 | 60+ |
| Sub-forum count | 2 | 4 | 6+ |
| Wiki mandatory terms | 5 | 9 | 15+ |
| Synthesis findings required | 2 | 5 | 8+ |

For the v1 release we target **all topics at Medium** to eliminate
difficulty as a confound variable when comparing agents. A future
difficulty-ablation will sample from all three tiers.

## 7. Verifier suite (paper section 4 source)

The composite score is the **product of a truthfulness gate and a
quality aggregate**:

```
quality       = 0.40 · url_coverage + 0.40 · judge_pass_rate + 0.20 · spec_pass
composite     = reachability · quality
```

Components:

| Metric | Source | Description |
|---|---|---|
| `reachability` | `URLReachabilityVerifier` | fraction of cited sandbox URLs that return HTTP 200 |
| `url_coverage` | `URLCoverageVerifier` | weighted must-cite recall × domain balance (anchored to golden pool) |
| `judge_pass_rate` | gpt-5-chat checklist | PASS fraction over 21 task-specific items |
| `spec_pass` | deterministic | 3-way count: words / citations / paragraphs in range |

The multiplicative form forces any agent with reachability ≈ 0
to composite ≈ 0 regardless of fluency, resolving F6's "quantity
rewards fabrication" failure of the legacy additive composite.

## 8. Reproducibility guarantees

- **Sandbox state is frozen**: the Magento, Postmill, and Kiwix
  containers on the evaluation machine are version-pinned (see
  HANDOFF.md). No external API is contacted during a task run.
- **Golden files are version-controlled** under
  `data/golden/deep/*.json`, checksummed per task.
- **Verifier outputs are deterministic** (URL coverage, reachability,
  markdown spec). The LLM-judge component is explicitly noted as
  non-deterministic and always reported with its judge identity
  (`judge_identity()` stamps the model id into every score file).
- **Agent runs log** `elapsed_seconds`, token usage (via ds_proxy
  log), and final report chars so cost-corrected metrics can be
  reconstructed.

## 9. Dataset growth protocol

Adding a new topic `T`:

1. Create `configs/deep_topics/T.yaml` declaring `shopping_keywords`,
   `reddit_forums`, `wiki_mandatory`, `wiki_extra`.
2. Run `python3 scripts/build_deep_golden.py --topic-config
   configs/deep_topics/T.yaml --task-id dr_cross_deep_<NN>
   --out data/golden/deep/dr_cross_deep_<NN>.json` on the sandbox.
3. Hand-review the generated `metadata.summary`:
   - `n_must_cite` ≥ 100
   - shopping/reddit/wiki each ≥ `per_domain_minimum`
   - `partial` flag is false (else tune keywords and re-scrape)
4. Write `data/tasks/deep_research/cross_site_deep/dr_cross_deep_<NN>.json`
   by copying the v1 template and editing intent/target counts.
5. Write `checklists_deep[<task_id>]` in `checklists_deep.json` —
   21 binary verifier questions driven by the task-specific dimensions.
6. Commit both files. The new task is live.

## 10. Known limitations

- **Sandbox vs open web**: deep-tier agents are evaluated on a
  reproducible closed sandbox. Real-world deep research requires
  open-web crawling which introduces selection bias, link rot, and
  captcha. A future work cohort will mirror selected tasks to
  Wayback Machine snapshots.
- **Golden pool incompleteness**: the 700-800 URL pool per task is
  a subset of the ~20 000 reachable sandbox pages. A cited URL not
  in the pool is checked via reachability (HTTP 200) rather than
  counted as fabrication.
- **Judge self-preference**: the agent and judge are intentionally
  cross-family (DeepSeek agent, GPT-5-chat judge). Single-family
  cross-checking is left to future work.
- **Topic domain bias**: initial 10 topics are all consumer
  goods / technology. Domain diversity (biomedical, legal, policy)
  is planned for v2.
