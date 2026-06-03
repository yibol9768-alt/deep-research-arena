# Per-framework weakness analysis (all 11 frameworks, deep_v3 scored data)

Source: `data/results/deep_v3/*.score.json` (per-task pillar scores). Means across each
framework's tasks. Pillars: chars (length), cites (cited_unique), mcr (must_cite_recall),
cov (url_coverage), reach (url_reachability), quote (quote_match), depth (analysis_depth),
pres (presentation). Note: markdown_spec / checklist / claim_nli were not populated in this
rescore batch (all 0), so they are excluded.

| framework | n | chars(med) | cites | mcr | cov | reach | quote | depth | pres | capture-fail | class |
| --- | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: | --- |
| claude-code | 5 | 45,987 | 114 | 0.028 | 0.27 | 0.96 | 0.86 | 0.65 | 0.67 | 0/5 | grounded+deep (top) |
| camel-ai | 57 | 29,502 | 57 | 0.033 | 0.14 | 0.91 | 0.78 | 0.59 | 0.64 | 0/57 | grounded+robust |
| smolagents | 31 | 15,050 | 48 | 0.055 | 0.12 | 0.70 | 0.62 | 0.40 | 0.56 | 1/31 | grounded mid |
| flowsearcher-ds | 48 | 28,580 | 33 | 0.007 | 0.06 | 0.50 | 0.45 | 0.32 | 0.45 | 18/48 | partial grounding |
| gpt-researcher | 32 | 27,827 | 65 | 0.000 | 0.20 | 0.03 | 0.00 | 0.00 | 0.71 | 1/32 | fluent hallucinator |
| langchain-odr | 31 | 28,322 | 43 | 0.000 | 0.07 | 0.01 | 0.00 | 0.39 | 0.71 | 4/31 | fluent hallucinator |
| deerflow | 30 | 25,302 | 14 | 0.000 | 0.01 | 0.16 | 0.02 | 0.00 | 0.58 | 0/30 | fluent, under-cited |
| ldr | 30 | 1,460 | 2 | 0.000 | 0.01 | 0.65 | 0.00 | 0.01 | 0.23 | 19/30 | tiny/shallow |
| ii-researcher | 30 | 74 | 13 | 0.000 | 0.03 | 0.00 | 0.00 | 0.05 | 0.30 | 23/30 | mostly runner-broken |
| storm | 31 | 20 | 1 | 0.000 | 0.00 | 0.03 | 0.03 | 0.00 | 0.11 | 30/31 | runner-broken (our bug) |
| qx-agents | 30 | 367 | 0 | 0.000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.20 | 30/30 | runner-broken (our bug) |

"capture-fail" = runs with < 1500 chars or a degenerate/skip marker (a proxy for runner/capture failure).

## Per framework

### Top tier (genuinely grounded + analytical)
- **claude-code** -- best grounding (reach 0.96, quote 0.86), deepest analysis (0.65), best coverage (0.27), longest (46k). Weaknesses: (1) only 5 tasks run, so its standing is under-sampled; (2) must_cite_recall 0.028 -- it over-cites (114 urls) but still misses the specific golden must-cite facts; (3) very long (up to 72k chars) risks verbosity.
- **camel-ai** -- the most robust real agent (57 tasks, 0 capture failures), strong grounding (reach 0.91, quote 0.78), solid analysis (0.59). Weaknesses: (1) must_cite_recall 0.033 -- cites real pages but not the required golden ones; (2) coverage 0.14; (3) analysis good but not deep synthesis.
- **smolagents** -- grounded (reach 0.70, quote 0.62), the BEST must_cite_recall of the field (0.055, still low in absolute terms). Weaknesses: (1) shortest of the working agents (15k median) -> less comprehensive; (2) moderate depth (0.40); (3) coverage 0.12.

### Fluent hallucinators (long, well-presented, but citations do not resolve)
- **gpt-researcher** -- highest presentation (0.71), most citations (65), but reach 0.03 / quote 0.00: it FABRICATES sequential URLs (`/products/1..50`) because its vector-store writer drops the real retrieved URLs. Weakness: ungrounded despite fluency; confident fabrication. (Partly addressed by feeding its writer the verbatim URL list; needs a sandbox re-run.)
- **langchain-odr** -- fluent (pres 0.71), some analysis (depth 0.39), but reach 0.01 / quote 0.00: same fabrication class. Weakness: zero grounding under a polished surface.
- **deerflow** -- long (25k) and presentable (0.58) but UNDER-cites massively (14 urls), reach 0.16 / quote 0.02, depth ~0. Weakness: long enumerative prose with almost no grounding and no synthesis.

### Partial / mediocre
- **flowsearcher-ds** -- about half its citations resolve (reach 0.50, quote 0.45), moderate depth (0.32). Weaknesses: (1) ~half its cited URLs do not resolve; (2) ~38% of runs failed to capture; (3) low must_cite_recall (0.007).
- **ldr** (local-deep-researcher) -- consistently TINY reports (1.5k median, max 5.8k), 2 citations, depth ~0; the 65% reach is over only 2 urls. Weakness: barely researches -- shallow by design or truncated; near-degenerate output.

### Runner / capture broken (LOW SCORE IS OUR HARNESS, NOT THE AGENT)
- **qx-agents** -- every one of 30 reports is an IDENTICAL 367-char stub. This is a deterministic runner/capture bug; the score is meaningless and must not be read as agent quality.
- **storm** -- 30/31 reports are the 20-char `(empty storm output)` placeholder; the runner pointed STORM at open-web Tavily with a fake key (fixed). Not STORM's real capability.
- **ii-researcher** -- 23/30 reports are 74-char stubs (capture failure); only a handful are real. Mostly a runner problem.

## Cross-cutting findings (about the field AND our eval)
1. **must_cite_recall is near-zero for EVERY framework (max 0.055).** No agent reliably finds the SPECIFIC golden must-cite sources. This is either a real universal weakness (poor targeted retrieval) OR our golden must-cite set is too strict/narrow. This needs a check: if even the best-grounded agents (camel-ai quote 0.78) hit only 3% of must-cite, the golden set may be over-specified.
2. **The fluent-hallucinator failure mode is common (3 of 11).** Long, polished, heavily-cited reports whose citations are fabricated or unresolvable. This is exactly what the grounding truth-gate exists to catch, and why ranking on fluency alone is unsafe.
3. **Runner/capture failures pollute the historical data.** qx-agents (100%), storm (97%), ii-researcher (77%), flowsearcher (38%) of runs are harness failures, not agent quality. The `invalid_runs` exclusion (BUG C fix) handles this going forward, but the historical deep_v3 numbers for these agents are not trustworthy and should be re-run on the now-working sandbox before any conclusion.
4. **Analytical depth is mediocre across the board** (best 0.65; most < 0.40). Even grounded agents mostly enumerate rather than synthesize/reconcile sources.
5. **No framework is both grounded AND comprehensive** (coverage maxes at 0.27).

## What this implies for our eval
- Exclude invalid_runs from the leaderboard (done) and RE-RUN the capture-broken agents (qx-agents, storm, ii-researcher) on the stable sandbox before ranking them.
- Audit the golden must-cite set: a 0.055 ceiling across all agents is suspicious and may indicate the must-cite URLs are too specific or stale.
- The grounding gate is doing real work: it correctly separates camel-ai/claude-code/smolagents (grounded) from gpt-researcher/langchain-odr/deerflow (fluent but ungrounded).
