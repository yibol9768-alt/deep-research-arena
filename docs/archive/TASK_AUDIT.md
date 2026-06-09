# Deep-Tier Task Audit: Paper-Readiness Assessment

**Date**: 2026-04-30
**Scope**: 30 tasks in `data/tasks/deep_research/cross_site_deep/`
**Benchmark**: field standard = 100 tasks (DRACO, LiveResearchBench, DeepResearch Bench)

---

## 1. Summary Table: All 30 Tasks

| # | task_id | Domain | Intent Type | n_must_cite | shop | reddit | wiki | pool | Issues |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 01 | dr_cross_deep_0001 | Consumer | Recommendation | 121 | 56 | 40 | 25 | 724 | Missing `domain`/`intent_type` fields; anchor (old-style TOP-10 synthesis) |
| 02 | dr_cross_deep_0002 | Consumer | Recommendation | 120 | 60 | 40 | 20 | 521 | Missing fields; anchor |
| 03 | dr_cross_deep_0003 | Consumer | Comparison | 127 | 60 | 40 | 27 | 724 | Missing fields |
| 04 | dr_cross_deep_0004 | Consumer | Comparison | 128 | 60 | 40 | 28 | 852 | Missing fields |
| 05 | dr_cross_deep_0005 | Consumer | Recommendation | 123 | 60 | 40 | 23 | 797 | Missing fields; anchor |
| 06 | dr_cross_deep_0006 | Consumer | Debunking | 126 | 60 | 40 | 26 | 823 | Missing fields |
| 07 | dr_cross_deep_0007 | Consumer | Debunking | 130 | 60 | 40 | 30 | 744 | Missing fields |
| 08 | dr_cross_deep_0008 | Consumer | Debunking | 129 | 60 | 40 | 29 | 798 | Missing fields |
| 09 | dr_cross_deep_0009 | Consumer | Causal | 128 | 60 | 40 | 28 | 728 | Missing fields |
| 10 | dr_cross_deep_0010 | Consumer | Timeline | 124 | 60 | 40 | 24 | 609 | Missing fields |
| 11 | dr_cross_deep_0011 | Consumer | Debunking | 129 | 60 | 40 | 29 | 896 | Missing fields |
| 12 | dr_cross_deep_0012 | Consumer | Enumeration | 128 | 60 | 40 | 28 | 779 | Missing fields |
| 13 | dr_cross_deep_0013 | Finance | Comparison | 127 | 60 | 40 | 27 | 754 | Missing fields; **JUNK shopping URLs** |
| 14 | dr_cross_deep_0014 | Finance | Recommendation | 126 | 60 | 40 | 26 | 692 | Missing fields; **JUNK shopping URLs** |
| 15 | dr_cross_deep_0015 | Finance | Debunking | 124 | 60 | 40 | 24 | 672 | Missing fields; **JUNK shopping URLs** |
| 16 | dr_cross_deep_0016 | Law | Comparison | 123 | 60 | 40 | 23 | 768 | Missing fields; **JUNK shopping URLs** |
| 17 | dr_cross_deep_0017 | Law | Enumeration | 123 | 60 | 40 | 23 | 706 | Missing fields; **JUNK shopping URLs** |
| 18 | dr_cross_deep_0018 | Law | Enumeration | 128 | 60 | 40 | 28 | 610 | Missing fields; **JUNK shopping URLs** |
| 19 | dr_cross_deep_0019 | Travel | Comparison | 124 | 60 | 40 | 24 | 726 | Missing fields; **JUNK shopping URLs** |
| 20 | dr_cross_deep_0020 | Travel | Debunking | 127 | 60 | 40 | 27 | 782 | Missing fields; **JUNK shopping URLs** |
| 21 | dr_cross_deep_0021 | Travel | Comparison | 127 | 60 | 40 | 27 | 636 | Missing fields; **JUNK shopping URLs** |
| 22 | dr_cross_deep_0022 | Education | Comparison | 125 | 60 | 40 | 25 | 810 | Missing fields; **JUNK shopping URLs** |
| 23 | dr_cross_deep_0023 | Education | Causal | 126 | 60 | 40 | 26 | 702 | Missing fields; **JUNK shopping URLs** |
| 24 | dr_cross_deep_0024 | Education | Enumeration | 126 | 60 | 40 | 26 | 619 | Missing fields; **JUNK shopping URLs** |
| 25 | dr_cross_deep_0025 | Entertainment | Comparison | 127 | 60 | 40 | 27 | 831 | Missing fields; **JUNK shopping URLs** |
| 26 | dr_cross_deep_0026 | Entertainment | Timeline | 128 | 60 | 40 | 28 | 520 | Missing fields; **JUNK shopping URLs**; shop_min=30 (anomaly) |
| 27 | dr_cross_deep_0027 | Entertainment | Causal | 128 | 60 | 40 | 28 | 662 | Missing fields; **JUNK shopping URLs** |
| 28 | dr_cross_deep_0028 | Science | Debunking | 127 | 60 | 40 | 27 | 586 | Missing fields; **JUNK shopping URLs** |
| 29 | dr_cross_deep_0029 | Science | Enumeration | 130 | 60 | 40 | 30 | 714 | Missing fields; **JUNK shopping URLs** |
| 30 | dr_cross_deep_0030 | Science | Causal | 129 | 60 | 40 | 29 | 563 | Missing fields; **JUNK shopping URLs** |

---

## 2. Critical Findings

### CRITICAL-1: Tasks 0013-0030 have irrelevant shopping golden URLs

This is the single biggest problem. All 18 non-consumer tasks (Finance, Law, Travel, Education, Entertainment, Science) contain 60 shopping must-cite URLs each that are **completely unrelated to the task topic**. Examples:

- **Finance ETF task (0013)**: golden shopping includes "mini gold coin cookies", "cable covers", "bonsai trees", "PS3 charging cables"
- **Law tenant rights task (0016)**: golden shopping includes "beard shaping combs", "projectors", "shelving units"
- **CRISPR debunking task (0028)**: golden shopping includes "castor oil", "lazy susan organizers", "hair masks"

The scraper (`build_deep_golden.py`) appears to have filled the shopping slot with random products from the Magento store rather than topic-relevant products. The YAML configs for these tasks define reasonable `shopping_keywords` (e.g., "personal finance book", "CRISPR book"), but the golden scraper did not filter by keyword relevance -- it just grabbed 60 random product pages to meet the >=60 count target.

**Root cause**: `scripts/build_deep_golden.py` function `scrape_shopping()` uses Magento's full-text search which returns results for almost any keyword (e.g. "personal finance book" returns random products matching any of those words). The scraper then takes the first 60 products without any relevance filtering. For Consumer-domain tasks (headphones, cookware, etc.) this works because the Magento store has many relevant products. For Finance/Law/Science tasks, the keywords return noise.

The scraper logged `discovered=200-300` products for every task, creating the illusion that products were found, when in fact the Magento search was returning off-topic results.

**Impact**: The must-cite shopping URLs are meaningless. Agents cannot meaningfully cite "bonsai tree" pages in a finance report. The `must_cite_recall` metric is broken for these tasks because it rewards citing irrelevant products. The entire url_coverage score dimension is corrupted for tasks 13-30.

**Fix required**:
1. Add a relevance filter to `scrape_shopping()` -- e.g., require that the product title contains at least one shopping keyword, or use TF-IDF/embedding similarity
2. Re-scrape all 18 tasks with the filtered scraper
3. Accept that the shopping pool will be smaller for non-consumer domains (10-30 relevant products vs 60 junk)
4. Adjust `per_domain_minimum.__SHOPPING__` to match actual available relevant products per task
5. If fewer than 10 relevant products exist for a task's keywords, expand the keyword list to adjacent categories (e.g. Finance: add "office supplies", "desk accessories", "monitor")

### CRITICAL-2: Tasks 0013-0030 results are severely depressed

The 90 runs (5 agents x 18 tasks) produced extremely low `composite_v2_truthful` scores. Looking at the raw leaderboard matrix:
- camel-ai mean on tasks 13-30: ~0.047 (vs ~0.030 on tasks 1-12)
- smolagents mean on tasks 13-30: ~0.033 (vs ~0.035 on tasks 1-12)
- gpt-researcher/langchain-odr/storm: near zero on both sets

The scores are not literally zero but the `must_cite_recall` component is broken because the golden shopping URLs are irrelevant junk. The agents are being penalized for NOT citing random bonsai trees and cable covers in their finance/law/science reports. The Elo ranking is dominated by 180 near-tie battles from tasks 13-30 (3 agents all scoring ~0), which inflates the battle count but adds no discriminative signal.

**Impact on current leaderboard**: The headline rankings may still be approximately correct (camel-ai > smolagents > rest) because the same agents tend to perform best on both task sets, but the Elo CIs are artificially tight (false precision from junk battles) and the per-task analysis is unreliable for tasks 13-30.

### CRITICAL-3: All 30 task JSON files are missing `domain` and `intent_type` fields

No task file has explicit `domain` or `intent_type` metadata. These must be inferred from the YAML topic names. This is not a scoring issue but is a metadata gap that makes automated analysis harder and is poor practice for a published benchmark.

---

## 3. Domain Coverage Analysis

### Current distribution (30 tasks):

| Domain | Count | % |
|---|---:|---:|
| Consumer | 12 | 40% |
| Finance | 3 | 10% |
| Law | 3 | 10% |
| Travel | 3 | 10% |
| Education | 3 | 10% |
| Entertainment | 3 | 10% |
| Science | 3 | 10% |

### Missing domains (found in peer benchmarks):

| Missing Domain | DRACO? | DRBench? | Why needed |
|---|---|---|---|
| Health/Medicine | Yes | Yes (4 tasks) | Drug interactions, treatment comparisons, clinical guidelines |
| Technology/Engineering | Yes | Yes | Software ecosystems, hardware specs, protocol comparisons |
| Environment/Climate | Yes | Yes | Climate data, energy policy, sustainability claims |
| Business/Management | Partial | Yes | Market analysis, management frameworks, industry trends |
| Politics/Society | Partial | Yes | Policy comparison, fact-checking political claims |

### Gap: Consumer over-representation

Consumer tasks are 40% of the dataset (12/30) but represent only one type of sandbox interaction (product browsing). Field standard (DRBench with 22 fields) suggests no domain should exceed 15%. To reach 100 tasks:
- Consumer: keep 12 (cap at 12%)
- Finance/Law/Travel/Education/Entertainment/Science: expand each to 8-10
- Add Health, Technology, Environment, Business, Politics: 8-10 each

---

## 4. Intent Type Balance

### Current distribution:

| Intent Type | Count | % | Target for 100 tasks |
|---|---:|---:|---:|
| Comparison | 8 | 27% | 20 (20%) |
| Debunking | 7 | 23% | 18 (18%) |
| Enumeration | 5 | 17% | 18 (18%) |
| Recommendation | 4 | 13% | 16 (16%) |
| Causal | 4 | 13% | 16 (16%) |
| Timeline | 2 | 7% | 12 (12%) |

### Issues:
- **Timeline is under-represented** (only 2 tasks, 7%). Need at least 10 more for 100-task set.
- **Comparison is slightly over-represented** but acceptable.
- The mix is reasonably balanced for intent-type-level analysis at n=30, but statistical power per intent type requires n>=12 each for meaningful sub-group comparisons.

---

## 5. Golden URL Pool Quality

### n_must_cite: All 30 tasks meet the >=120 threshold

- Range: 120-130 (tight band)
- Lowest: dr_cross_deep_0002 (120)
- Highest: dr_cross_deep_0007, dr_cross_deep_0029 (130)

### Domain breakdown per golden file:

- **Tasks 0001-0012 (Consumer)**: shop=56-60, reddit=40, wiki=20-30. Shopping URLs are topically relevant (headphones, fitness gear, cookware, etc.).
- **Tasks 0013-0030 (non-Consumer)**: shop=60, reddit=40, wiki=23-30. **Shopping URLs are NOT topically relevant** (random products). See CRITICAL-1.

### Pool sizes (expected_pool_urls):

- Range: 520-896
- Smallest: 0026 (520, board games), 0030 (563, mRNA)
- Largest: 0011 (896, sleep aids)
- Adequate for all tasks.

### Domain balance issue:

Tasks 0001-0012 use `per_domain_minimum: {shop: 30, reddit: 20, wiki: 15}` (shopping-heavy).
Tasks 0013-0030 use `per_domain_minimum: {shop: 10, reddit: 30, wiki: 25}` (reddit/wiki-heavy).
Exception: Task 0026 uses `{shop: 30, reddit: 20, wiki: 15}` despite being Entertainment domain -- an inconsistency.

This split is defensible (consumer tasks are product-centric; knowledge tasks are discussion/reference-centric) but should be explicitly justified in the paper's methodology section.

---

## 6. Checklist Quality

### Checklist type distribution:

| Type | Tasks | IDs |
|---|---|---|
| Generic (template-cloned) | 3 | 0001, 0002, 0005 (anchors) |
| Task-specific (21 items) | 27 | 0003-0004, 0006-0030 |

### Assessment:
- **Anchors (0001, 0002, 0005)**: Use the old generic checklist ("Does the report enumerate at least 40 distinct product pages..."). These are intentionally preserved as anchors for cross-version stability.
- **Tasks 0003-0012**: Fully task-specific, well-crafted per the V1_TASK_DESIGN_GRID. Each item tests a concrete, verifiable aspect of the expected output (e.g., "Are exactly 3 paths defined and labelled P1/P2/P3?").
- **Tasks 0013-0030**: Also task-specific and well-crafted. Quality is comparable to 0003-0012.

### Issue:
All checklists are 21 items. This is by design (standardized for judge_pass_rate calculation) but means no task has more or fewer requirements. For a paper, this should be stated as a design choice.

---

## 7. Task Intent Quality (Spot Checks)

### Well-written intents (good):
- **0003 (Home Fitness Comparison)**: Clear 3-path x 5-use-case matrix structure. Specific budget constraint ($300). Explicit per-cell evidence requirements. Excellent.
- **0006 (Cookware Debunking)**: 5 specific claims with concrete marketing language. Verdict taxonomy is clear. Triple-evidence requirement per claim. Excellent.
- **0009 (EV Winter Range Causal)**: 4-layer causal chain structure. Specific physics/chemistry grounding required. Well-structured.
- **0028 (CRISPR Debunking)**: 5 specific claims, good mix of He Jiankui ethics + technical off-target + regulatory topics.

### Issues found:
- **0001, 0002, 0005 (Anchors)**: Intent is a "market-intelligence report" template with generic structure (product landscape + community sentiment + technical grounding + cross-source synthesis). While functional, these are less demanding than the V1 task-specific intents. The TOP-10 output requirement is a ranking task that may not test cross-source synthesis as deeply.

### Synthesis requirements (Section D):
- **0003-0012**: All require genuine cross-source analysis (verdict tables with triple evidence, comparison matrices with per-cell citations from all 3 sources, causal chains with layered evidence). Strong.
- **0013-0030**: Same quality of synthesis requirements. Each task demands structured cross-source output (matrices, verdict tables, causal layers, catalogs).

---

## 8. Recommendations

### Priority 1 (Blocking for paper): Fix CRITICAL-1 -- Re-scrape tasks 0013-0030

The 18 non-consumer task golden files must be re-scraped with topic-relevant shopping URLs. Steps:
1. For each task, verify the YAML `shopping_keywords` actually return relevant products on the sandbox Magento store
2. Modify `build_deep_golden.py` to filter shopping results by keyword relevance (not just grab random products)
3. Accept smaller shopping pools for non-consumer domains: 10-25 topic-relevant products instead of 60 random ones
4. Re-scrape all 18 golden files on westd
5. Adjust `per_domain_minimum.__SHOPPING__` to match actual available products per task

### Priority 2 (Blocking for paper): Re-run tasks 0013-0030

After fixing the golden files, re-run all 5 agents x 18 tasks = 90 runs. Current results are all zeroed out and unusable.

### Priority 3 (Paper quality): Add `domain` and `intent_type` fields to all 30 task JSONs

Add explicit metadata fields. This is a simple patch:

```python
domain_map = {
    1: "Consumer", 2: "Consumer", 3: "Consumer", 4: "Consumer",
    5: "Consumer", 6: "Consumer", 7: "Consumer", 8: "Consumer",
    9: "Consumer", 10: "Consumer", 11: "Consumer", 12: "Consumer",
    13: "Finance", 14: "Finance", 15: "Finance",
    16: "Law", 17: "Law", 18: "Law",
    19: "Travel", 20: "Travel", 21: "Travel",
    22: "Education", 23: "Education", 24: "Education",
    25: "Entertainment", 26: "Entertainment", 27: "Entertainment",
    28: "Science", 29: "Science", 30: "Science",
}
intent_map = {
    1: "Recommendation", 2: "Recommendation", 3: "Comparison",
    4: "Comparison", 5: "Recommendation", 6: "Debunking",
    7: "Debunking", 8: "Debunking", 9: "Causal",
    10: "Timeline", 11: "Debunking", 12: "Enumeration",
    13: "Comparison", 14: "Recommendation", 15: "Debunking",
    16: "Comparison", 17: "Enumeration", 18: "Enumeration",
    19: "Comparison", 20: "Debunking", 21: "Comparison",
    22: "Comparison", 23: "Causal", 24: "Enumeration",
    25: "Comparison", 26: "Timeline", 27: "Causal",
    28: "Debunking", 29: "Enumeration", 30: "Causal",
}
```

### Priority 4 (Paper quality): Fix task 0026 `per_domain_minimum` anomaly

Task 0026 (board game timeline, Entertainment) uses `shop_min=30` while all other non-consumer tasks use `shop_min=10`. This is inconsistent. Should be `{shop: 10, reddit: 30, wiki: 25}` to match sister tasks, unless board games are genuinely product-heavy (which they are -- the sandbox likely has board game products).

### Priority 5 (Scaling to 100): Plan 70 new tasks

To reach the field standard of 100 tasks with the recommended 12-domain distribution:

| Domain | Current | Target | New needed | Shopping strategy |
|---|---:|---:|---:|---|
| Consumer | 12 | 12 | 0 | Direct product search (strong) |
| Finance | 3 | 8 | 5 | Books, calculators, planners |
| Law | 3 | 8 | 5 | Law books, office supplies |
| Travel | 3 | 8 | 5 | Luggage, travel gear, guides |
| Education | 3 | 8 | 5 | Textbooks, study aids, laptops |
| Entertainment | 3 | 8 | 5 | Board games, streaming devices, AV equipment |
| Science | 3 | 8 | 5 | Science books, lab equipment, microscopes |
| Health/Medicine | 0 | 10 | 10 | Supplements, medical devices, health books |
| Technology | 0 | 10 | 10 | Software books, dev tools, networking gear |
| Environment | 0 | 8 | 8 | Solar panels, eco products, gardening |
| Business | 0 | 6 | 6 | Business books, office equipment |
| Politics/Society | 0 | 6 | 6 | Policy books, news media subscriptions |
| **Total** | **30** | **100** | **70** | |

Intent type targets for 100 tasks:
- Comparison: 20 (currently 8, need 12 more)
- Debunking: 18 (currently 7, need 11 more)
- Enumeration: 18 (currently 5, need 13 more)
- Recommendation: 16 (currently 4, need 12 more)
- Causal: 16 (currently 4, need 12 more)
- Timeline: 12 (currently 2, need 10 more)

### Priority 6 (Paper quality): Validate sandbox has content for new domains

Before generating 70 new tasks, must verify:
1. Magento store has sufficient products for each new domain's shopping keywords
2. Postmill has sufficient forum threads for each new domain's reddit keywords
3. Kiwix Wikipedia has all mandatory wiki articles for each new domain

Use `scripts/validate_yaml_batch.py` for this.

---

## 9. Tasks That Should Be Revised

### Revision needed (before next run):

| Task | Issue | Proposed fix |
|---|---|---|
| 0001 | Generic intent (anchor); no `domain`/`intent_type` | Add metadata fields; keep intent as anchor |
| 0002 | Generic intent (anchor); no `domain`/`intent_type` | Add metadata fields; keep intent as anchor |
| 0005 | Generic intent (anchor); no `domain`/`intent_type` | Add metadata fields; keep intent as anchor |
| 0013-0030 | Golden shopping URLs are irrelevant junk | Re-scrape golden with filtered products |
| 0026 | shop_min=30 inconsistent with non-consumer policy | Change to shop_min=10 (or justify if board games are product-heavy) |

### No revision needed:

Tasks 0003, 0004, 0006-0012: These are well-designed with task-specific intents, relevant golden URLs, task-specific checklists, and successful runs with meaningful scores.

---

## 10. Priority Execution Plan

| Step | Description | Effort | Blocking? |
|---:|---|---|---|
| 1 | Add `domain` + `intent_type` fields to all 30 task JSONs | 30 min | No |
| 2 | Audit sandbox Magento store: what products exist for finance/law/travel/etc. keywords | 1 hr | Yes (blocks step 3) |
| 3 | Fix `build_deep_golden.py` to filter shopping by keyword relevance | 2 hr | Yes (blocks step 4) |
| 4 | Re-scrape golden for tasks 0013-0030 on westd | 2 hr (automated) | Yes (blocks step 5) |
| 5 | Re-run 5 agents x 18 tasks = 90 runs on westd | 12-18 hr (automated) | Yes (blocks step 6) |
| 6 | Re-score and rebuild leaderboard | 2 hr (automated) | Yes (for paper) |
| 7 | Generate YAML configs for 70 new tasks (5 domains x ~14 tasks) | 4-6 hr | No (parallel) |
| 8 | Validate sandbox coverage for new task YAMLs | 2 hr | Yes (blocks step 9) |
| 9 | Scrape golden + generate task JSONs for 70 new tasks | 6-8 hr (automated) | For 100-task paper |
| 10 | Run 5 agents x 70 new tasks = 350 runs | 48-72 hr (automated) | For 100-task paper |

**Minimum viable for paper with 30 tasks**: Steps 1-6 (~20 hr, mostly automated).
**Full 100-task paper**: Steps 1-10 (~100 hr total, mostly automated).
