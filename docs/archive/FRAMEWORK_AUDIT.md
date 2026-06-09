# DR Framework Smoke Test Audit Report

**Date:** 2026-04-30  
**Auditor:** Automated script + manual review  
**Scope:** 10 working DR frameworks, task `dr_cross_deep_0001` smoke outputs  
**Sandbox Status:** All 3 sandbox endpoints confirmed reachable (HTTP 200): `localhost:7770` (shop), `localhost:9999` (reddit), `localhost:8090` (wiki)

---

## Summary Table

| # | Framework | File | Bytes | Words | Shop | Reddit | Wiki | Off-sandbox | Citation Style | CoT Leaks | Errors | Verdict |
|---|-----------|------|-------|-------|------|--------|------|-------------|---------------|-----------|--------|---------|
| 1 | camel-ai | `_matrix.md` | 27,650 | 2,624 | 69 | 27 | **0** | 0 | inline | 1 | 0 | **INTEGRATION_BUG** |
| 2 | flowsearcher-ds | `_matrix.md` | 29,521 | 2,323 | 36 | 19 | 23 | 0 | inline | 0 | 0 | **PASS** |
| 3 | smolagents | `_smoke_qf.md` | 28,039 | 2,887 | 43 | 32 | 9 | 0 | inline (in JSON) | 0 | 0 | **INTEGRATION_BUG** |
| 4 | langchain-odr | `_smoke_v3.md` | 30,977 | 2,904 | 37 | 29 | 35 | 0 | inline | 0 | 0 | **PASS** |
| 5 | gpt-researcher | `_smoke_final.md` | 27,202 | 2,732 | 47 | 11 | **1** | 0 | inline | 0 | 0 | **INTEGRATION_BUG** |
| 6 | ii-researcher | `_smoke_final.md` | 30,988 | 3,053 | 21 | 8 | **0** | 0 | inline | 0 | 0 | **INTEGRATION_BUG** |
| 7 | storm | `_smoke_v8.md` | 11,589 | 1,503 | **0** | **0** | **0** | 0 | footnote [N] | 0 | 0 | **FRAMEWORK_LIMITATION** |
| 8 | deerflow | `_smoke_df.md` | 17,420 | 2,008 | 8 | 5 | 2 | 0 | inline | 0 | 0 | **PASS** |
| 9 | co-storm | `_smoke_new.md` | 16,218 | 2,191 | **0** | **0** | **0** | 0 | footnote [N] | 0 | 0 | **FRAMEWORK_LIMITATION** |
| 10 | local-deep-researcher | `_smoke_new.md` | 26,487 | 2,430 | 4 | **0** | **0** | **38** | inline | 0 | 0 | **INTEGRATION_BUG** |

**Verdict counts:** 3 PASS, 4 INTEGRATION_BUG, 2 FRAMEWORK_LIMITATION, 1 borderline (see deerflow note)

---

## Detailed Findings

### 1. camel-ai -- INTEGRATION_BUG

- **Issue: Zero Wikipedia (localhost:8090) URLs.** The report has 69 shopping URLs and 27 reddit URLs but completely omits the wiki sandbox. There is no Section (C) Technical Grounding with wiki content, and the word "Wikipedia" does not appear anywhere in the output.
- **Issue: Chain-of-thought leakage.** Line 1 reads: _"I now have enough data to compile a comprehensive report. Let me compile all the information I've gathered and write the report."_ This is a planning utterance that leaked into the final output.
- **Root cause (likely):** The integration harness is not passing the wiki sandbox URL (`localhost:8090`) to camel-ai's tool configuration, or the search tool is only configured with 2 of the 3 sources. The CoT leak suggests the output extraction is grabbing the full agent trace instead of just the final answer.
- **Recommendation:** (1) Verify wiki endpoint is in the tool config. (2) Strip agent planning prefix from output.

### 2. flowsearcher-ds -- PASS

- All 3 sandbox sources well represented: 36 shop, 19 reddit, 23 wiki.
- Clean markdown with executive summary, proper H2/H3 structure (4 H2, 10 H3).
- 78 unique sandbox URLs, 0 off-sandbox, 0 CoT leaks, 0 errors.
- Inline citation style with `[label](url)` throughout.
- Strong analysis content (7 analysis keywords).
- **No issues detected.**

### 3. smolagents -- INTEGRATION_BUG

- **Issue: Output is a single-line JSON blob, not markdown.** The file is 0 lines (no newlines at top level), wrapped as `{"answer": "# Consumer-Grade Audio..."}`. The JSON itself is malformed/truncated (parser reports "Unterminated string"), so the markdown content cannot be reliably extracted.
- **Issue: The inner content is good** -- contains 43 shop, 32 reddit, 9 wiki URLs with proper inline citations -- but the output extraction layer is dumping raw JSON instead of extracting the `answer` field.
- **Root cause:** The smolagents framework returns a structured JSON response. Our harness is writing the raw JSON to the output file instead of extracting the `answer` field. Additionally, the JSON is truncated (file ends mid-URL), suggesting the output was cut off at a size limit.
- **Recommendation:** (1) Extract `data["answer"]` before writing the output file. (2) Increase output buffer size to avoid truncation.

### 4. langchain-odr -- PASS

- All 3 sandbox sources well represented: 37 shop, 29 reddit, 35 wiki.
- Clean markdown, professional structure (5 H2, 11 H3), dated header.
- 101 unique sandbox URLs -- highest URL density of all frameworks.
- 18 analysis keywords -- highest analytical depth.
- 0 CoT leaks, 0 errors, 0 off-sandbox URLs.
- **No issues detected. Best-performing framework output.**

### 5. gpt-researcher -- INTEGRATION_BUG

- **Issue: Near-zero Wikipedia coverage.** Only 1 mention of `localhost:8090` in the entire report (in the executive summary as a source description). Zero actual wiki article URLs cited in the body. The report mentions "27 Wikipedia articles providing technical grounding" in the summary but does not actually include them.
- Shopping (47) and Reddit (11) are present but Reddit is also weak compared to other frameworks.
- Good markdown structure and professional formatting otherwise.
- **Root cause (likely):** Similar to camel-ai -- the wiki search tool may not be properly configured, or the framework's research agent is not being directed to query the wiki sandbox. Alternatively, the framework may have searched wiki but failed to include results in the final synthesis.
- **Recommendation:** Verify wiki tool configuration. The mention of "27 Wikipedia articles" in the summary suggests the LLM was told about wiki in the prompt but the tool never actually fetched wiki content.

### 6. ii-researcher -- INTEGRATION_BUG

- **Issue: Wiki URLs are textual references, not actual sandbox URLs.** The report has a Section (C) "Technical Grounding from Wikipedia" with 36 mentions of "Wikipedia" and 14 mentions of `localhost:8090`. However, the actual extracted unique wiki URLs are 0 -- the references describe Wikipedia articles by name (e.g., "Active Noise Control - Wikipedia defines...") without hyperlinking to the sandbox wiki. The sandbox `localhost:8090` appearances are descriptive mentions, not clickable citations.
- Shopping (21) and Reddit (8) are properly linked with URLs.
- Good structure (8 H2, 16 H3) and analysis depth (13 keywords).
- **Root cause:** The framework is synthesizing wiki content from its knowledge or from partial search results but not preserving the actual `localhost:8090/...` URLs in the citations. This could be a prompt issue (wiki search returns content but the URL is not passed through to the report template) or the framework discards source URLs during its synthesis step.
- **Recommendation:** Ensure wiki search tool returns URLs alongside content, and that the report generation prompt requires inline URL citations for wiki sources.

### 7. storm -- FRAMEWORK_LIMITATION

- **Issue: Zero extractable URLs.** The report uses academic-style `[N]` footnote citations (up to [31]) but none of them resolve to actual URLs anywhere in the document. There is no references/bibliography section. The `grep -c "http" storm_file` returns 0.
- Content quality is reasonable -- 1,503 words, structured with H2/H3 headers, discusses products with specific prices and model names that match sandbox data. The framework clearly accessed the sandbox sources during research but its output format strips all URLs.
- At 11,589 bytes this is also the smallest output, roughly half the size of most other frameworks.
- **Root cause:** This is Storm's native output format. Storm (Stanford's STORM) generates Wikipedia-style articles with numbered citations but does not include a bibliography section with URLs. This is a known design choice of the framework -- it assumes citations will be resolved separately. Our harness would need a post-processing step to resolve `[N]` back to source URLs.
- **Recommendation:** This is a framework architecture limitation, not our bug. To fix, add a post-processing step that maps Storm's internal citation IDs back to the URLs it accessed during the retrieval phase (from `_storm_scratch` directory).

### 8. deerflow -- PASS (borderline)

- All 3 sandbox sources present: 8 shop, 5 reddit, 2 wiki.
- Clean markdown with professional structure (6 H2, 5 H3), dated header.
- 15 unique sandbox URLs total -- relatively low compared to other frameworks.
- 0 off-sandbox, 0 CoT leaks, 0 errors, 8 analysis keywords.
- The low URL count is a concern but appears to reflect the framework's research depth rather than an integration bug -- the URLs that are present are correct and properly linked.
- **Verdict: PASS** -- the framework is working correctly, it just does less deep retrieval. This is a capability difference, not a bug.

### 9. co-storm -- FRAMEWORK_LIMITATION

- **Issue: Zero URLs, zero localhost mentions.** The report uses `[N]` footnote citations (up to [57]) with no URL resolution. Not a single `http` URL appears in the entire 16,218-byte output.
- **Issue: Divergent report structure.** Instead of the expected market-intelligence format (Product Landscape / Community Sentiment / Technical Grounding / Cross-Source Synthesis), co-storm produces a topic-oriented essay with sections like "Background Information and Foundational Research", "Consumer Frustrations and Unmet Needs", "Alternative Data Sourcing Strategies", "Structured Taxonomy Extraction", and "Source Identification and Citation Strategy". This reads more like a meta-analysis of HOW to write the report rather than the report itself.
- **Issue: References external retailers.** The text mentions Amazon, Best Buy, and real-world brand ecosystems (Bose QuietComfort Ultra, Sennheiser) rather than citing sandbox-specific data. Some product mentions (gingerbread house kits, Trump T-shirts, V8 energy drinks) appear to be from the sandbox shopping data but are cited as noise/irrelevant items rather than filtered out.
- **Root cause:** Co-STORM (collaborative STORM) is designed for multi-perspective discourse generation, not structured report writing. Its output is a collaborative exploration of a topic with meta-commentary about data sources and taxonomy, which is architecturally different from the expected market-intelligence report format. The [N] citation style with no URL resolution is inherited from Storm.
- **Recommendation:** Framework limitation. Co-STORM's collaborative discourse format does not naturally produce the structured report format needed. If keeping co-storm, a significant prompt-engineering effort or post-processing pipeline would be needed to reshape its output.

### 10. local-deep-researcher -- INTEGRATION_BUG

- **Issue: 38 off-sandbox URLs pointing to `en.wikipedia.org` instead of `localhost:8090`.** The framework is citing real Wikipedia URLs (e.g., `https://en.wikipedia.org/wiki/Headphones`, `https://en.wikipedia.org/wiki/Bluetooth`) instead of the sandbox wiki at `localhost:8090`. This means the framework is reaching out to the real internet for Wikipedia rather than using the provided wiki sandbox.
- **Issue: Only 4 sandbox URLs total** (all shopping), with 0 reddit and 0 wiki sandbox URLs. The framework is not using the reddit or wiki sandboxes at all for actual URL citations.
- **Issue: Non-headphone products included.** Multiple citations to `localhost:7770/5-year-warranty-surpower-cr2025-3v-lithium-battery...` (a battery product) and car audio speakers, suggesting weak relevance filtering.
- Content quality is reasonable (2,430 words, 6 H2, 11 H3) but the citation sourcing is fundamentally broken.
- **Root cause:** The framework's search tool configuration is pointing to real Wikipedia instead of the sandbox wiki. The reddit sandbox may not be configured at all. The shopping sandbox search returns low-relevance results that are not being filtered.
- **Recommendation:** (1) Override the wiki search URL to point to `localhost:8090` instead of `en.wikipedia.org`. (2) Add `localhost:9999` as the reddit search endpoint. (3) Improve search query specificity or add post-retrieval relevance filtering.

---

## Cross-Framework Observations

### Source Coverage Matrix

| Framework | Shop | Reddit | Wiki | All 3 Present? |
|-----------|------|--------|------|----------------|
| camel-ai | 69 | 27 | 0 | NO |
| flowsearcher-ds | 36 | 19 | 23 | YES |
| smolagents | 43* | 32* | 9* | YES (in JSON) |
| langchain-odr | 37 | 29 | 35 | YES |
| gpt-researcher | 47 | 11 | 1 | BARELY |
| ii-researcher | 21 | 8 | 0 | NO (text-only wiki) |
| storm | 0 | 0 | 0 | NO (all [N] refs) |
| deerflow | 8 | 5 | 2 | YES |
| co-storm | 0 | 0 | 0 | NO (all [N] refs) |
| local-deep-researcher | 4 | 0 | 0 | NO (uses real web) |

Only **4 of 10** frameworks properly cite all 3 sandbox sources with actual URLs.

### Common Failure Patterns

1. **Wiki sandbox not configured** (camel-ai, gpt-researcher, local-deep-researcher): The `localhost:8090` endpoint is either missing from tool config or being overridden by real Wikipedia.
2. **URL-free citation style** (storm, co-storm): These Stanford STORM-family frameworks use `[N]` footnotes without URL resolution. This is architectural and would need post-processing to fix.
3. **Output format mismatch** (smolagents, co-storm): The output extraction layer does not match the framework's native output format (JSON wrapper for smolagents, discourse format for co-storm).
4. **Weak relevance filtering** (local-deep-researcher): Non-headphone products (batteries, car speakers) appear in citations.

### Priority Fix Order

1. **smolagents** -- Easiest fix: extract `answer` field from JSON output. Content quality is already good.
2. **camel-ai** -- Add wiki endpoint to tool config, strip CoT prefix from output.
3. **local-deep-researcher** -- Point wiki/reddit search to sandbox endpoints instead of real web.
4. **gpt-researcher** -- Debug wiki tool integration; the framework claims 27 wiki articles but cites 0.
5. **ii-researcher** -- Ensure wiki search returns URLs that get included in report citations.
6. **storm/co-storm** -- Architectural limitation; add post-processing to resolve [N] citations to URLs from scratch data. Lower priority as these are known framework limitations.
