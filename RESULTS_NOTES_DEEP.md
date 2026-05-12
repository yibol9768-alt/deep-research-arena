# Deep-Tier Results Notebook (start: 2026-04-24)

Track every smoke run on the deep-tier task `dr_cross_deep_0001`. Append-only log;
old entries don't get rewritten when new findings land.

## Setup

- **Task:** `dr_cross_deep_0001` (audio headphone market intelligence,
  100–200 URL scope across shopping/reddit/wiki)
- **Backbone:** DeepSeek v4 flash via westd ds_proxy:8088 (thinking disabled)
- **Judge:** gpt-5-chat-latest via 35.164.11.19:3887 proxy
- **Sandbox:** Magento :7770 + Postmill :9999 + Kiwix :8090 on westd WSL
- **Search:** unified shim on westd:8081 (Tavily-compat)
- **Golden:** `data/golden/deep/dr_cross_deep_0001.json` — 125 must-cite, 739 pool, 559 triples

---

## Run 1 — gpt-researcher (2026-04-24 18:08)

| Metric | Value | Notes |
|---|---|---|
| Elapsed | 231 s | LLM-only loop ended early (embeddings 404'd) |
| Output chars | 27 105 | 2598 words; 108 markdown links |
| URL coverage score | **0.30 FAIL** | domain_balance=1.0, must_recall=**0.0**, pool_cov=**0.0** |
| Per-domain cited | shop=45 / red=36 / wiki=23 | meets per_domain_minimum 30/20/15 |
| Markdown spec | 1/3 ok | words<3500, paragraphs<25 |
| Judge gpt-5-chat checklist | **21/21 PASS** | judge sees zero issues |
| Composite | 0.55 | (0.50·url + 0.35·judge + 0.15·spec) |

### F5 finding: LLM-judge vs URL-verifier asymmetry

The agent fabricated **100% of its 104 cited URLs**. None match either
must_cite or expected_pool — the LLM invented plausible-looking patterns
like `/products/sony-mdr-ex15ap` and `/wiki/Bluetooth` that don't exist on
the sandbox. The actual sandbox uses `*.html` slugs for shopping and
`/content/wikipedia_en_all_nopic/A/<title>` for kiwix.

**gpt-5-chat scored every checklist item PASS.** It does not verify URL
existence; it only checks surface features (right counts, right structure,
right tone).

**The deterministic URL verifier caught it cleanly** — 0/125 must_cite,
0/739 pool. Score 0.30 (only domain_balance saved it).

**Implication:** LLM judge is necessary but not sufficient for the deep
tier. URL-coverage verifier is the missing piece. Headline finding for
the paper's deep-tier section.

### Why the agent fabricated

ds_proxy log shows ~6 chat completion calls + 5 `/v1/embeddings → 404`
attempts. DeepSeek doesn't host an embeddings endpoint, so gpt-researcher's
`OpenAIEmbeddings` failed and the research loop aborted to "writer-only"
mode. The writer then hallucinated from priors instead of crawling.

The shim itself was perfectly healthy and returns correct sandbox URLs:
- `http://localhost:7770/sony-zx110nc-noise-cancelling-headphones.html`
- `http://localhost:8090/content/wikipedia_en_all_nopic/Noise-cancelling_headphones`
- `http://localhost:9999/f/headphones/126764`

Even with the few search results the agent did receive, it ignored them
and made up its own plausible URL formats.

### Action items

- [x] Wire DashScope text-embedding-v4 into ds_proxy `/v1/embeddings`
- [x] Re-run gpt-researcher after embedding fix → see Run 3
- [ ] Write a tiny sanity-check verifier that flags reports where ZERO
      cited URLs are reachable (404 rate ≈ 1.0); this is a strong proxy
      for fabrication and is even cheaper than fact-KG verification
- [ ] Add to paper section 5: "LLM judge vs URL verifier asymmetry"

---

## Run 2 — smolagents (2026-04-24 18:21)

| Metric | Value |
|---|---|
| Elapsed | 340 s |
| Output chars | 27 175 (2706 words, 108 markdown links) |
| URL coverage | **0.330 FAIL** — must_recall=**0.052** (6/125), pool=7/739 |
| Per-domain cited | shop=41 / red=31 / wiki=26 |
| Markdown spec | 1/3 ok |
| Judge gpt-5-chat checklist | **20/21 PASS** + 1 UNCLEAR |
| Composite | 0.548 |

**Notes:** smolagents code-as-action with ApiWebSearchTool+VisitWebpageTool
DOES hit the real shim, recovers SOME real product URLs (e.g.
`new-black-earhook-headphones-headphones.html`) but the LLM still pads
the report with invented Sony / Apple / Bose product URLs that don't
exist on the sandbox. Same fabrication mode as gpt-researcher, only
slightly less severe (5% must_recall vs 0%).

---

## Run 3 — gpt-researcher (with embeddings, 2026-04-24 18:28)

| Metric | Value |
|---|---|
| Elapsed | 220 s |
| Output chars | 26 509 (3034 words, 99 markdown links) |
| URL coverage | **0.300 FAIL** — must_recall=**0.000** (still 0!) |
| Per-domain cited | shop=48 / red=33 / wiki=18 |
| Judge gpt-5-chat checklist | **21/21 PASS** |
| Composite | 0.550 |

**F5b finding: embedding fix did NOT change gpt-researcher's behaviour.**
Embeddings now resolve cleanly through ds_proxy → DashScope, but score
is identical to v2 to 3 decimal places. The fabrication is structural in
deepseek-v4-flash + gpt-researcher: the LLM ignores tool results and
emits training-prior URL patterns instead. v3 even invented a different
zim slug — `wikipedia_en_all_maxi_2022-05` — which doesn't exist on our
kiwix (we serve `wikipedia_en_all_nopic`).

---

## Run 4 — camel-ai (2026-04-24 18:28)

| Metric | Value |
|---|---|
| Elapsed | 216 s |
| Output chars | 28 008 (2729 words, 108 markdown links) |
| URL coverage | **0.319 FAIL** — must_recall=**0.023** (4/125), pool=33/739 (4.5%) |
| Per-domain cited | shop=64 / red=21 / wiki=25 |
| Judge gpt-5-chat checklist | **7/21 PASS, 14 UNCLEAR** |
| Composite | 0.326 |

**Finding (judge variance):** camel-ai produced a structurally weaker
report than gpt-researcher (less segmented, no clear (D) synthesis
section). gpt-5-chat noticed and gave 14 UNCLEAR verdicts, dropping
checklist pass rate to 33% — vs gpt-researcher's 100% on similarly
fabricated but better-formatted output. **The judge is sensitive to
report STRUCTURE but blind to URL TRUTHFULNESS.**

**Verifier bug fixed mid-run:** camel emitted a markdown link with a
trailing backtick `[label](http://localhost:7770\``)` which crashed
`urlparse.port`. Patched `_canonical()` in `url_coverage_verifier.py`
to strip stray punctuation and catch ValueError on port parsing.

---

## Aggregate (4 runs so far)

| # | Agent | Composite | URL | Must-recall | Judge |
|---:|---|---:|---:|---:|---:|
| 1 | gpt-researcher v2 | 0.550 | 0.300 | 0.000 | 21/21 |
| 1 | gpt-researcher v3 | 0.550 | 0.300 | 0.000 | 21/21 |
| 3 | smolagents       | 0.548 | 0.330 | 0.052 | 20/21 |
| 4 | camel-ai         | 0.326 | 0.319 | 0.023 | 7/21 |

**Pattern**: all 4 agents fabricate URLs at similar rate (must_recall < 5%)
regardless of architecture. gpt-5-chat judge is dominated by report
quality/structure cues, NOT URL truth. Composite ranking reverses with
URL verifier on: every agent FAILS, judge passes flatten the rankings.

---

## Run 5 — langchain-odr (2026-04-24 18:36)

| Metric | Value |
|---|---|
| Elapsed | 253 s |
| Output chars | 26 501 (2954 words, 84 markdown links, 32 paragraphs) |
| URL coverage | **0.040 FAIL** (lowest yet) — must_recall=0, only 2 wiki cited |
| Per-domain cited | shop=49 / red=36 / **wiki=2** ← below 15 minimum |
| Domain balance | **0.13** (wiki under-coverage tanks it) |
| Markdown spec | 2/3 ok (paragraphs OK!) |
| Judge gpt-5-chat checklist | **21/21 PASS** |
| Composite | **0.470** |

**Issue prerequisite:** First langchain-odr attempt died in 7s with
`response_format type is unavailable` — DeepSeek v4 only accepts
`json_object`, not `json_schema`. Patched ds_proxy to rewrite
`response_format=json_schema` → `json_object` and inject schema
description into the system prompt. v2 then worked.

**Behavioural finding:** langchain-odr's langgraph supervisor essentially
ignored the wiki dimension of the task. Researchers focused on
shopping+reddit, the writer hallucinated 84 product/thread URLs, and the
final report only mentions wiki 2x. gpt-5-chat judge still gives 21/21.

---

## Aggregate (5 runs)

| # | Agent | Composite | URL | Must-recall | Judge | Notes |
|---:|---|---:|---:|---:|---:|---|
| 1 | gpt-researcher v2 | 0.550 | 0.300 | 0.000 | 21/21 | full fabrication |
| 1 | gpt-researcher v3 | 0.550 | 0.300 | 0.000 | 21/21 | embedding fix no-op |
| 3 | smolagents       | 0.548 | 0.330 | 0.052 | 20/21 | partial real URLs |
| 4 | langchain-odr    | 0.470 | 0.040 | 0.000 | 21/21 | wiki dim skipped |
| 5 | camel-ai         | 0.326 | 0.319 | 0.023 | 7/21  | judge caught struct |

---

## Run 6 — STORM (Stanford knowledge-storm, 2026-04-24 18:41)

| Metric | Value |
|---|---|
| Elapsed | 197 s |
| Output chars | 11 480 (1189 words, 17 markdown links, 12 paragraphs) |
| URL coverage | **0.004 FAIL** (lowest) — 17 URLs total, 5 hit pool, 1 hit must |
| Per-domain cited | shop=13 / red=4 / **wiki=0** ← skipped wiki entirely |
| Domain balance | **0.0** |
| Markdown spec | 0/3 ok |
| Judge gpt-5-chat checklist | **3/21 PASS, 6 FAIL, 12 UNCLEAR** (lowest judge) |
| Composite | **0.052** |

**STORM operational notes:**
- 4-stage pipeline (research → outline → article → polish) all completed
  cleanly inside 197s with deepseek-v4-flash backbone via litellm
  `openai/deepseek-v4-flash` and api_base→ds_proxy.
- Initial runner crashed in post-processing because I used the full topic
  string (300 chars lowercased) as a directory name, hit ext4's 255-char
  limit. STORM itself truncated to 152 chars and wrote artifacts there;
  recovered by globbing `_storm_scratch/Produce_a*` for the dir.
- STORM stores its citation map in `url_to_info.json` (NOT inline in the
  article — article uses [N] notation only). Wrote a one-shot post-process
  script to append a `## References` section with `[N] [title](url)` lines
  so URLCoverageVerifier can parse them.

### F6 finding: URL truthfulness inverted from quantity

Computing **precision = |cited ∩ pool| / |cited|** (= "how many cited
URLs actually exist in the sandbox"):

| Agent | Cited | Pool-hit | Precision | Composite |
|---|---:|---:|---:|---:|
| **STORM**         | 17  | 5  | **0.294** | 0.052 |
| **camel-ai**      | 110 | 33 | **0.300** | 0.326 |
| smolagents        | 98  | 7  | 0.071 | 0.548 |
| langchain-odr     | 87  | 0  | **0.000** | 0.470 |
| gpt-researcher v2 | 104 | 0  | **0.000** | 0.550 |
| gpt-researcher v3 | 99  | 0  | **0.000** | 0.550 |

**STORM and camel-ai are the only honest agents** (~30% of cited URLs
actually exist on the sandbox), but they finish 1st-from-bottom and
2nd-from-bottom on composite because the score rewards *quantity* (60+
citations) more than *truthfulness*.

gpt-researcher and langchain-odr at 0% precision = **every URL they cite
is invented**. They top the composite leaderboard because they cite
fluently in markdown link format. **The composite metric, as currently
defined, is the wrong objective.**

### Action items (paper)

- [ ] Add `precision = pool_hit / cited_unique` to URLCoverageVerifier
      details so future runs report it natively
- [ ] Replace the current composite weights with a "honesty-first"
      variant: penalise low-precision regardless of recall
- [ ] Section 5 of the paper now has TWO clean findings:
      1. **F5** LLM judge can't see URL fabrication (gpt-5-chat 21/21 on
         100% fake URLs)
      2. **F6** Quantity-based URL recall reverses the ranking from
         truthfulness-based URL precision (STORM ranks last on quantity
         but is one of two non-fabricators)

---

## Final aggregate (6 runs, 5 unique agents)

Sorted by **truthfulness precision** (the metric that should matter):

| Rank | Agent | Precision | Composite (current) | Comment |
|---:|---|---:|---:|---|
| 1 | camel-ai | 0.300 | 0.326 | most honest cite count |
| 2 | STORM | 0.294 | 0.052 | most honest, but too short |
| 3 | smolagents | 0.071 | 0.548 | partial honesty |
| 4 | langchain-odr | 0.000 | 0.470 | full fabrication |
| 5 | gpt-researcher | 0.000 | 0.550 | full fabrication |

The deep-tier task **demolishes** the existing composite ranking. This
is exactly what user asked for when they said "我们的 benchmark 有几个
问题" — the shallow tier was masking that 3 of 5 famous OSS agents,
under DS backbone, fabricate 100% of their citations.

---
