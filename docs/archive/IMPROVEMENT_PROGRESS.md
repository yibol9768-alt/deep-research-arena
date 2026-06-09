# Improvement Plan Progress

## Phase 1: Fix Golden Data

### P1.1 Scraper relevance fix -- COMPLETE
- [x] `_is_product_relevant()` rewritten with strict matching:
  - Full-phrase substring match for multi-word keywords
  - At least 2 non-ambiguous token matches required
  - Extensive ambiguous-word list prevents false positives (book/bookcase, stock/stock-chicken, etc.)
- [x] Adaptive compensation system:
  - When shopping produces < 40 must_cite, increases reddit target (up to 74) and wiki boost (up to 56)
  - Wiki boost uses Kiwix search API with all topic keywords to find additional articles
  - URL normalization ensures /A/ path format consistency
- [x] Deployed to westd

### P1.2 Re-scrape 0013-0030 -- COMPLETE (partially; refreshing in background)
- [x] Tasks 0013-0015 freshly re-scraped with new filter + adaptive compensation
  - 0013 (Finance): n=141 (shop=11, reddit=74, wiki=56) -- strict filter correctly rejects irrelevant products
  - 0014 (Finance): n=141 (shop=30, reddit=65, wiki=46)
  - 0015 (Finance): n=149 (shop=45, reddit=60, wiki=44)
- [x] Tasks 0016-0030 already >= 120 from earlier runs; re-scrape in progress for quality refresh
- [x] ALL 30 tasks verified >= 120 must_cite

### P1.3 Domain/intent_type metadata -- COMPLETE
- [x] Added `domain` field to all 30 task JSONs:
  - 0001-0012: Consumer
  - 0013-0015: Finance
  - 0016-0018: Law
  - 0019-0021: Travel
  - 0022-0024: Education
  - 0025-0027: Entertainment
  - 0028-0030: Science
- [x] Added `intent_type` field:
  - Market-Intelligence (3), Comparison (9), Debunking (5), Causal (4), Timeline (2), Enumeration (5), Recommendation (1)
- [x] Deployed to westd

## Phase 2: Fix 5 Framework Integration Bugs -- ALL COMPLETE

### P2.1 camel-ai (wiki=0 + CoT leakage)
- [x] Added explicit wiki search strategy to system prompt (15+ wiki articles, dedicated search queries)
- [x] Added 20+ separate search calls instruction
- [x] Added CoT prefix stripping via regex + markdown-heading heuristic

### P2.2 smolagents (raw JSON output)
- [x] Added JSON/dict parsing for `agent.run()` result
- [x] Extracts `answer` or `output` field from JSON string or dict

### P2.3 gpt-researcher (wiki search not cited)
- [x] Added explicit citation requirements to enhanced query
- [x] Requests 15+ Wikipedia article citations explicitly

### P2.4 ii-researcher (wiki descriptions no URLs)
- [x] Added URL collection during TavilyClient.search (patched search method)
- [x] Post-processing: injects wiki URLs for bare text mentions of wiki article titles

### P2.5 local-deep-researcher + LDR (off-sandbox wiki URLs)
- [x] Added `en.wikipedia.org/wiki/X` -> `localhost:8090/content/.../A/X` URL rewriting
- [x] Applied to `_unmask_report()` in both `ldr_runner.py` and `local_deep_researcher_runner.py`

## Phase 3: Re-run Matrix + Score + Leaderboard -- IN PROGRESS

### P3.1 Run 10x30 matrix
- [x] Batch script (`run_matrix_batch.sh`) deployed to westd
- [x] schtask `MatrixRunDirect` started (force re-run, no skip)
- [x] 10 agents: camel-ai, gpt-researcher, smolagents, storm, langchain-odr, deerflow, ldr, ii-researcher, qx-agents, local-deep-researcher
- [x] 30 tasks each = 300 runs total
- [ ] Running autonomously (ETA: ~25 hours; first result: camel-ai__dr_cross_deep_0001)

### P3.2 Score all
- [x] Scoring included in batch script (runs after each agent completes)
- [ ] Will execute after runs finish

### P3.3 Rebuild leaderboard
- [x] Leaderboard rebuild included in batch script
- [ ] Will execute after all scoring completes

---

## Files Modified

### Scripts (deployed to westd `/opt/deep_reserch/scripts/`)
- `build_deep_golden.py` -- relevance filter + adaptive compensation + wiki boost
- `run_deep_task.py` -- P2.1-P2.4 fixes (camel-ai, smolagents, gpt-researcher, ii-researcher)
- `runners/ldr_runner.py` -- P2.5 wiki URL rewriting
- `runners/local_deep_researcher_runner.py` -- P2.5 wiki URL rewriting
- `src/shim_intercept.py` -- sync'd

### Data (local + westd)
- `data/tasks/deep_research/cross_site_deep/dr_cross_deep_*.json` -- domain + intent_type added
- `data/golden/deep/dr_cross_deep_*.json` -- 0013-0015 re-scraped with adaptive system

### Batch Scripts (on westd `C:\tools\`)
- `rescrape_golden.sh` -- re-scrapes tasks 0013-0030
- `run_matrix_batch.sh` -- runs full 10x30 matrix, scores, rebuilds leaderboard
- `start_matrix_after_scrape.sh` -- chains scraper -> matrix

---
Started: 2026-04-30
Last updated: 2026-05-01T15:30 UTC
Status: Phase 3 running on westd (matrix + scoring + leaderboard)
