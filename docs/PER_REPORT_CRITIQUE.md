# Per-Report Critique: dr_cross_deep_0001 through dr_cross_deep_0005

This document critiques each actual agent report for the five "deep" cross-site
tasks, with quoted evidence. The single most important axis is GROUNDING: every
cited URL was probed live by the harness (`url_reachability` in the
`.score.json`), so we can state, per report, what fraction of citations are real
sandbox pages (HTTP 200) versus fabricated (HTTP 4xx). That probe is the
ground truth used throughout below.

## Preliminaries: what each task actually asked for

The report filenames say `dr_cross_deep_000X`, but the topics do NOT match the
`dr_cross_v3_000X` catalog. The real deep-task topics (recovered from the report
H1s and the storm runner-error filenames) are:

- **0001** Consumer-grade audio headphones. Three sources: shopping (One Stop
  Market `:7770`) + Reddit/Postmill (`:9999`) + Wikipedia/Kiwix (`:8090`).
  Sections expected: (A) product landscape, (B) community sentiment,
  (C) technical grounding, (D) cross-source synthesis. Score minimums confirm a
  3-source task: shopping >=30, reddit >=20, wikipedia >=15 cited URLs.
- **0002** Home coffee brewing equipment. Same 3-source A/B/C/D shape.
- **0003** Home-fitness equipment, three paths (P1 dumbbells+bench, P2
  barbell+plates+rack, P3 bodyweight+bands+pull-up bar) under $300, compared
  across 5 use cases. Decision-matrix shape, 3 sources.
- **0004** Photography starter stacks under $800 (S1 mirrorless, S2 used DSLR,
  S3 smartphone+lens-kit), compared across 5 use cases. Decision-matrix shape.
- **0005** Indoor & balcony gardening, 3-source market-intelligence shape.

Correct sandbox URL shapes (verified against `data/golden/`):
- shopping: `http://localhost:7770/<descriptive-slug>.html`
  (e.g. `/new-black-earhook-headphones-headphones.html`)
- reddit: `http://localhost:9999/f/<forum>/<numeric-id>/<slug>`
  (e.g. `/f/technology/48700/google-has-to-pay-...`)
- wikipedia: `http://localhost:8090/content/wikipedia_en_all_nopic/<Article>`
  (the `/A/` infix variant also resolves)
- gitlab: `http://localhost:8023/<namespace>/<project>`

Anything of the form `/products/1`, `/products/<made-up-slug>`,
`/product/<slug>`, `/threads/5`, `/f/headphones/456` (bare numeric, no slug),
or `/wiki/<Article>` (no `/content/...`) is FABRICATED and 404s on probe.

---

# camel-ai

## 0001 — Headphones (27,333 chars / ~2,624 words)
**Grounding: EXCELLENT.** 96/96 cited URLs returned HTTP 200; quote_match 0.97;
claim_nli 0.625 (the highest NLI of any 0001 report). Every shopping slug is a
real catalog page, e.g. `http://localhost:7770/sony-zx110nc-noise-cancelling-headphones.html`
($44.99, 4.2/5) and `.../razer-opus-active-noise-cancelling-anc-wireless-headphones-thx-audio-tuning-...html`
($39.86, 3.2/5). Reddit links are real Postmill threads, e.g.
`http://localhost:9999/f/headphones/126745` ("Short reviews of all headphones I've
ever owned").

**Analytical depth: SHALLOW / pure enumeration.** Section (A) is a brand-by-brand
mega-table of ~50 products; section (B) lists ~35 threads. The single biggest
problem is that almost every Reddit row has empty metrics: "Score | Comments"
columns are all `—`, e.g. the FIIO FT3 thread row reads
"| [FIIO FT3](...126750) | — | — | ...". The report never actually extracted the
score/comment_count the task wants.

**Coverage: INCOMPLETE — no synthesis, no Wikipedia.** The file ends mid-document
at "The AskReddit forum did not yield headphone-specific threads" (line 170).
There is NO section (C) technical grounding and NO section (D) cross-source
synthesis. The promised "comprehensive market-intelligence report" is two raw
catalogs with no verdict.

**Specific flaws:** Opening line hallucinates scope: "research across all three
sandbox sources" and "(`http://localhost:8090`)"-style claims never materialize.
Several threads are tagged with implausible classifications (a stickied "Help
Desk" labeled `purchase_advice`; the AI-pause thread shoehorned into a headphone
report as `technical_question`).

**Did well:** Real, verifiable product data with accurate prices/ratings; broad
brand and price-tier coverage; honest about the empty AskReddit result.

**Verdict:** Well-grounded data dump that stops before any analysis — no synthesis, no Wikipedia, blank Reddit metrics.

## 0002 — Coffee (~2,831 words)
**Grounding: MIXED.** 62/92 reachable (reach 0.67), quote 0.59. Shopping slugs are
real, but ~30 citations 4xx — driven by off-topic Reddit links left over from the
headphones run: in a COFFEE report it cites `http://localhost:9999/f/headphones/126750`
and `http://localhost:9999/f/gaming/126440`, which are real pages but irrelevant,
plus several forum IDs that do not resolve.
**Depth/Coverage:** Has A.1–A.6 product catalog, a Reddit section, and a Wikipedia
section (unlike its 0001), so structurally more complete. Still enumeration-heavy.
**Verdict:** Real coffee products, but Reddit evidence is partly recycled/off-topic, dragging grounding to 67%.

## 0003 — Home-fitness paths (~2,650 words)
**Grounding: TOTAL FAILURE.** 0/141 URLs reachable (reach 0.00, quote 0.00). Every
shopping link is fabricated, e.g. `http://localhost:7770/products/bowflex-selecttech-552`,
`.../products/cap-barbell-olympic-bar`, `.../products/flybird-adjustable-bench-f1` —
the `/products/<invented-slug>` form that does not exist in the sandbox.
**Verdict:** Confidently written path comparison built entirely on hallucinated product URLs — zero real sources.

## 0004 — Photography stacks (~2,430 words)
**Grounding: GOOD.** 48/52 reachable (reach 0.92), quote 0.85. Real camera-accessory
slugs, e.g. `.../canon-eos-m50-mark-ii-mirrorless-digital-camera-with-15-45mm-lens-black-pixibytes-basic-bundle.html`
and `.../camdesign-hd-cell-phone-camera-lens-12x-optical-zoom-telephoto-lens-clip-on-smartphone-lens-...html`.
**Depth: GENUINE.** Best analytical section of any camel report: a 3x5 use-case
matrix plus "5 Hidden Costs the Marketing Claim Hides" (e.g. "Hidden Cost #2: '4K
Video' on Budget Cameras", "#4: '12x Optical Zoom' Clip-On Lens Quality"), which
is real critique rather than listing.
**Verdict:** Strong, well-grounded comparison; minor 4xx from a few stretch citations.

## 0005 — Gardening (~1,760 words)
**Grounding: PERFECT but NARROW.** 55/55 reachable, quote 1.00, must_hit 6,
pool_hit 41 — every URL is a real shopping page.
**Coverage: SEVERELY INCOMPLETE.** This is the shortest grounded report and it
contains ZERO Reddit and ZERO Wikipedia citations (grep of `localhost:9999` and
`localhost:8090` = 0). Sections run A.1 "Live Indoor Plants" through A.7 "Garden
Tools" and then simply stop. Two of the three mandated sources, and the entire
synthesis, are missing.
**Verdict:** Flawless shopping grounding wasted on a single-source product list — no community, no Wikipedia, no synthesis.

---

# claude-code

## 0001 — Headphones (~5,519 words, 505 lines)
**Grounding: STRONG.** 144/155 reachable (reach 0.96), only 6 4xx; quote 0.70. All
three source types use correct shapes: shopping `.html` slugs, real Postmill
`/f/headphones/<id>`, and correct Kiwix
`http://localhost:8090/content/wikipedia_en_all_nopic/Active_noise_control`. The
few 4xx are over-reach (e.g. a Focal Bathys it discusses but could not pin to a
catalog page).

**Analytical depth: GENUINE SYNTHESIS — best of the cohort.** Section (D) does
exactly what the task asks: it reconciles marketing claims against Wikipedia and
ratings against Reddit. Best example (D1, claim 1): the Srhythm NC35 at $21.93
"Claims 'World-Class ANC Earbuds'" is checked against the ANC article and judged
"likely passive sound isolation, not active noise cancellation," reasoning from
the cost of "microphones, amplifiers, and phase-cancellation circuitry." It also
finds real internal store contradictions, e.g. "Skullcandy ... [Crusher Evo]
4.2/5 ... but [Sesh Evo] gets only 2.1/5 — a massive quality gap within the same
product line."

**Shallow counter-example:** Section (A) is still a very long brand-by-brand
enumeration (A1–A13), and the report duplicates content — Turtle Beach appears
twice (an "A8" block at lines 88-95 AND again at lines 125-132), and several
"already listed above" style repeats inflate length.

**Coverage:** All four sections present and all three sources well represented;
this is the most complete 0001 report.

**Specific flaws:** Header asserts "Date: 2026-05-15" (fabricated date); some
Reddit metrics are invented with false precision (a thread given "Score: 42 |
9 cmts" that the harness could not corroborate, contributing claim_nli 0.0). At
5,519 words it is padded well past the comfortable range, with a 130-item URL
index appended.

**Verdict:** The strongest report overall, but bloated and padded with duplicated tables and some unverifiable Reddit metrics.

## 0002 — Coffee (~3,909 words)
**Grounding: PERFECT.** 123/123 reachable, quote 0.96. Includes comment-level
permalinks that resolve, e.g.
`http://localhost:9999/f/BuyItForLife/118320/-/comment/2372219`.
**Depth: EXCELLENT.** Section D1 is model contradiction-resolution: the "Puerto
Rican Artists Edition Espresso Maker" is shown to be a moka pot, citing the Moka
pot article — "produces coffee at around 1.5 bar ... far below the 9 bar minimum
for true espresso." D3 surfaces real rating-vs-sentiment divergences (e.g. Keurig
sampler 4.4/5 on store vs BIFL threads seeking alternatives to pods).
**Verdict:** Fully grounded and genuinely synthetic; the benchmark for what these tasks want.

## 0003 — Home-fitness paths (~2,954 words)
**Grounding: STRONG.** 107/118 reachable (0.91), quote 0.82, correct Kiwix and
Postmill shapes.
**Depth: EXCELLENT and task-shaped.** Unlike the generic A/B/C/D template, it
adopts the actual task structure: a UC1–UC5 x P1–P3 decision matrix with per-cell
reasoning grounded in exercise-science articles (`/Progressive_overload`,
`/High-intensity_interval_training`, `/Calisthenics`) plus Postmill threads.
**Flaw:** The real equipment (dumbbells/barbells) is not in the sandbox catalog,
so its shopping citations are tangential filler — "Whey Protein Powder", "Gym
Motivation Posters" ($6.99), "Body Glide Anti-Chafe Balm" — used as stand-ins.
**Verdict:** Excellent reasoning and structure; shopping evidence is thin/tangential because the actual gear is not in-catalog.

## 0004 — Photography stacks (~4,060 words)
**Grounding: STRONG.** 101/104 reachable (0.97), quote 0.90. Real camera/accessory
slugs and correct Kiwix links.
**Depth: GENUINE.** Same task-appropriate 3x5 matrix (UC1 Family/Portrait …
UC5 Growth Path) with stack-by-stack reasoning.
**Flaw:** Long; like 0003 it pads with tangential shopping items where dedicated
bodies/lenses are not in-catalog.
**Verdict:** Well-grounded, well-structured comparison; somewhat verbose.

## 0005 — Gardening (~3,894 words)
**Grounding: STRONG.** 67/68 reachable (0.99), quote 0.92. Note must_hit 0 /
pool_hit 4 — it cites real, reachable pages but few of the specific "golden"
products, i.e. it picked different (still valid) items.
**Coverage: COMPLETE.** Has Part A (A.1–A.9 product groups), Part B community
sentiment with a thread catalog, and Part C technical grounding — all three
sources, unlike camel's 0005.
**Verdict:** Complete and grounded; main weakness is length and missing the specific golden products.

---

# gpt-researcher

## 0001 — Headphones (~3,576 words)
**Grounding: NEAR-TOTAL FABRICATION.** Only 3/110 cited URLs reachable (reach
0.027); quote 0.00; claim_nli 0.00; must_hit 0; pool_hit 0. EVERY shopping link
is sequential and invented: "Sony WH-1000XM5 - [Product Page](http://localhost:7770/products/1)",
"[Product Page](http://localhost:7770/products/2)" … through `/products/47`.
EVERY Reddit link is `http://localhost:9999/threads/1` … `/threads/35`. Wikipedia
uses the wrong shape `http://localhost:8090/wiki/Active_noise_control` (real is
`/content/wikipedia_en_all_nopic/...`).
**Hallucinated facts:** The products are real-world catalog inventions absent from
the sandbox, complete with fake review counts — "Sony WH-1000XM5 ... 4.7/5 (2,847
reviews)", "Panasonic RP-HJE125 ... (12,345 reviews)". The Reddit "threads"
include invented titles and scores ("Score: 245, Comments: 89").
**Other flaws:** The file is truncated mid-sentence in section (D): "...
Bluetooth codecs like LDAC can" — no conclusion. Despite this it is fluent and
superficially authoritative, which is the danger.
**Verdict:** Polished prose over 100% fabricated sources — the model invented an entire sandbox.

## 0002 — Coffee (~3,265 words)
**Grounding: FABRICATED.** 3/105 reachable. Same pattern:
`http://localhost:7770/products/aeropress-go`, `.../products/aeropress-original`.
**Verdict:** Same `/products/<slug>` hallucination machine, new topic.

## 0003 — Home-fitness (~2,813 words)
**Grounding: FABRICATED.** 3/96 reachable. `.../products/bowflex-selecttech-552`,
`.../products/cap-barbell-150lb-set`.
**Verdict:** Fabricated throughout.

## 0004 — Photography (~2,491 words)
**Grounding: FABRICATED + MALFORMED.** 3/70 reachable, and the markdown is broken:
links render as `http://localhost:7770/product/dji-osmo-mobile](http://localhost:7770/product/dji-osmo-mobile`
and `.../product/iphone-14\`` — nested/duplicated brackets and stray backticks.
**Verdict:** Fabricated and technically malformed citations.

## 0005 — Gardening (~2,436 words)
**Grounding: FABRICATED + MALFORMED.** 3/80 reachable; same broken-link artifacts,
e.g. `.../products/fertilizer-bloom-booster](http://localhost:7770/products/fertilizer-bloom-booster`.
**Verdict:** Fabricated; identical failure mode across all five tasks.

**gpt-researcher cross-task summary:** This agent never reached the sandbox on any
of the five tasks (always exactly 3 incidental hits). It is the most dangerous
profile in the cohort: long, confident, well-formatted reports that are ~97%
hallucinated URLs and invented product/forum data.

---

# langchain-odr

## 0001 — Headphones (~3,640 words)
**Grounding: NEAR-TOTAL FABRICATION.** 3/91 reachable (reach 0.033), quote 0.00.
Shopping links invent a `/product/<slug>` namespace that does not exist:
`http://localhost:7770/product/sony-mdr-zx110`, `.../product/sony-wh-1000xm5`,
`.../product/apple-airpods-max`. Reddit links are bare sequential numerics with no
slug: `http://localhost:9999/f/gadgets/123`, `/f/headphones/456`, `/f/gadgets/789`
— the real Postmill requires `/f/<forum>/<id>/<slug>`.
**Hallucinated facts:** Real-world products with invented review counts
("Audio-Technica ATH-M50x ... 4.8 | 22,345 [reviews]"), and a `/f/gadgets` forum
that is not even part of this run.
**Structural flaw:** Visible duplication — Price Tier 3 and Tier 4 repeat the same
items with the literal note "Already listed in mid-range, also premium price
point" / "Already listed above" used five times; the brand list is numbered 1–9
under a heading that says "Eight brands."
**Verdict:** Fabricated `/product/` and slugless-Reddit URLs, padded with duplicate tiers.

## 0002 — Coffee (~3,371 words)
**Grounding: FABRICATED.** 2/58 reachable (reach 0.03), quote 0.02.
**Verdict:** Fabricated.

## 0003 — Home-fitness (~3,255 words)
**Grounding: WORST CASE — ZERO sandbox URLs and an admission.** It cites NO
`localhost` URLs at all and openly states: "Due to technical limitations
accessing the designated sandbox servers (localhost:7770, localhost:9999,
localhost:8090), this analysis draws on established fitness industry knowledge ...
peer-reviewed exercise science principles." So it abandoned the task and wrote a
generic essay.
**Verdict:** Candidly off-task — admits it never reached the sandbox and cites nothing from it.

## 0004 — Photography (~4,315 words)
**Grounding: FABRICATED.** 0/16 reachable. The only sandbox-shaped links are bare
Wikipedia titles with the wrong path and no `/content/` prefix:
`http://localhost:8090/Aperture`, `.../Bokeh`, `.../Depth-of-field`,
`.../Exposure-(photography` (note the unclosed paren). Only 16 URLs in a
4,315-word report — heavy unsourced prose.
**Verdict:** Longest report in the set, almost entirely unsourced; the handful of links are malformed wiki paths.

## 0005 — Gardening (~3,666 words)
**Grounding: FABRICATED.** 3/89 reachable. `/products/<slug>` inventions again:
`.../products/full-spectrum-led-panel-200w`, `.../products/fabric-grow-bag-set-5pk`.
**Verdict:** Fabricated.

**langchain-odr cross-task summary:** Like gpt-researcher, it essentially never
reaches the sandbox (0–3 hits per task). Distinctive tells: a `/product/`
(singular) namespace, slugless `/f/<forum>/<number>` Reddit links, bare-title
Wikipedia paths, conspicuous duplicate-tier padding, and on 0003 an explicit
confession of failure.

---

# smolagents

## 0001 — Headphones (~3,191 words)
**Grounding: MOSTLY FABRICATED (with a tell-tale twist).** 8/108 reachable (reach
0.074), quote 0.037. Unlike gpt-researcher/langchain, smolagents generated URLs in
the CORRECT shopping shape — full descriptive `.html` slugs — and a handful are
genuinely real (`/new-black-earhook-headphones-headphones.html`,
`/bulk-headphones-kids-headphones-5pack-ymj-...html`,
`/munskt-color-headphones-...html`, `/jbl-quantum-100-...`). But the large
majority are plausible-looking guesses that 404, e.g.
`/anker-soundcore-life-q20-wireless-bluetooth-headphones-noise-cancelling-40h-playback.html`,
`/beats-flex-wireless-earphones-neckbuds-built-in-mic-magnetic-earbuds.html`. Its
Reddit links use a different wrong shape, `http://localhost:9999/t/106m8r2`
(base-36, no `/f/<forum>/`), and Wikipedia uses the wrong `/wiki/` prefix.
**Depth:** Section (D) is well organized — feature-claim-vs-Wikipedia table, brand
ranking, divergences — arguably cleaner prose than the grounded reports, but it is
all built on invented citations (the "EQ can tune any headphone" thread at
`/t/112jrdo` with "Score 23 | 36" is fabricated).
**Verdict:** Convincing slug-shaped guesses that mostly 404 — fabrication dressed in the correct URL format.

## 0002 — Coffee (~2,651 words)
**Grounding: PERFECT.** 63/63 reachable, quote 0.97, must_hit 12, pool_hit 32 —
the agent actually browsed this time.
**Structural oddity:** The Executive Summary is placed LAST (line 193, after
section D) rather than up top.
**Verdict:** Fully grounded and well-structured aside from the misplaced executive summary.

## 0003 — Home-fitness paths (~3,135 words)
**Grounding: MOSTLY GOOD.** 55/80 reachable (0.69), quote 0.77, must_hit 16
(highest of the 0003 reports). 25 4xx from over-reached shopping items.
**Depth: GOOD and task-shaped.** Uses the real decision-matrix structure (UC1–UC5
with per-path Best/Acceptable/Poor ratings) and a clear "When to Pick Which Path"
section.
**Verdict:** Genuinely grounded path comparison; some shopping links over-reach into 404s.

## 0004 — Photography (28 words) — HARNESS/RUNNER STUB, NOT A REAL REPORT
The entire file is a skeleton: "# Photography Starter Stack Comparison Report ...
## Executive Summary  This report compares three photography starter stacks...
[Full report content with all citations]". The literal placeholder
"[Full report content with all citations]" was emitted instead of a report. Score
is all zeros. This is a generation/runner failure, not a substantive report, and
should be flagged as a stub rather than scored as a bad report.
**Verdict:** Empty placeholder skeleton — runner/generation failure, not a real report.

## 0005 — Gardening (~2,877 words)
**Grounding: BEST IN COHORT.** 109/110 reachable (0.99), quote 0.98, must_hit 30,
pool_hit 77 — by these numbers the most thoroughly grounded report of all 25.
Wikipedia links use the valid `/content/wikipedia_en_all_nopic/A/<Article>`
variant (e.g. `/A/Vermicompost`, `/A/Perlite`, `/A/Chlorophyll`). Broad botany
grounding.
**Verdict:** Exceptionally well-grounded; smolagents' single best result.

**smolagents cross-task summary:** Wildly inconsistent. When it browses (0002,
0005, mostly 0003) it produces the best-grounded reports in the set; when it does
not (0001) it fabricates URLs that are formatted correctly enough to look real;
and 0004 is an empty stub.

---

# storm — ALL FIVE ARE HARNESS STUBS, NOT REPORTS

None of storm's five outputs is a real report; do not read these as low-quality
writing — they are capture failures in our harness:

- 0001: literally `(empty storm output)` (3 words).
- 0002: `(empty storm output)`.
- 0005: `(empty storm output)`.
- 0003: `(runner error: OSError: [Errno 36] File name too long: '/opt/deep_reserch/data/results/deep/_storm_scratch/produce_a_comparison_report_on_three_home-fitness_equipment_paths_under_a_fixed_$300_starter_budget_...')`.
- 0004: same `OSError: [Errno 36] File name too long` for the photography prompt.

The 0003/0004 errors are useful: they leak the real task prompts (confirming
home-fitness and photography topics) and reveal the bug — storm names a scratch
directory after the full prompt text, exceeding the filesystem's 255-char limit.
This is OUR runner's fault, not the model's; storm should be excluded from quality
comparisons on these tasks (or rerun with a hashed scratch path).
**Verdict:** Not assessable — empty captures and a filename-length runner crash.

---

# Cross-report patterns

1. **A clean grounding split, confirmed by live probing.** Three agents
   essentially never reach the sandbox: **gpt-researcher** (3 reachable URLs on
   every single task) and **langchain-odr** (0–3 per task) fabricate uniformly;
   **smolagents** fabricated 0001 but browsed for real on 0002/0003/0005. The two
   consistently grounded agents are **claude-code** (0.91–1.00 reachable on all
   five) and **camel-ai** (grounded on four; total fabrication on 0003 only).

2. **Distinct fabrication fingerprints.** gpt-researcher invents sequential
   `/products/N` and `/threads/N`; langchain-odr invents a `/product/<slug>`
   namespace plus slugless `/f/<forum>/<number>` Reddit links and bare-title
   `:8090/<Article>` wiki paths; smolagents invents correctly-shaped `.html`
   slugs (hardest to catch by eye) and `:9999/t/<base36>` Reddit links. camel-ai's
   one failure (0003) uses gpt-researcher-style `/products/<slug>`.

3. **Hallucinated review counts are a giveaway.** Fabricated reports cite
   implausibly large review counts ("2,847 reviews", "12,345 reviews", "22,345
   reviews") that the real low-traffic sandbox catalog never has. Grounded reports
   show small or blank review counts.

4. **Wikipedia path shape is a fast fabrication detector.** Real:
   `/content/wikipedia_en_all_nopic/<Article>` (claude-code, camel where present,
   smolagents 0005). Fake: `/wiki/<Article>` (gpt-researcher, smolagents 0001) or
   bare `/<Article>` (langchain 0004).

5. **Enumeration vs synthesis is orthogonal to grounding.** Grounded reports can
   still be shallow: camel-ai 0001 and 0005 are pure product tables with no
   synthesis (and 0005 omits Reddit + Wikipedia entirely). Conversely
   fabricated reports (smolagents 0001, gpt-researcher 0001) contain slick
   "synthesis" sections — but synthesizing invented data is worthless. The only
   reports that combine real grounding with genuine cross-source reasoning are
   **claude-code 0002/0003/0004** and **camel-ai 0004**.

6. **Truncation and length problems.** gpt-researcher 0001 cuts off mid-sentence
   in section D; camel-ai 0001 stops before sections C and D exist. On the other
   end, claude-code routinely runs 3,900–5,500 words with duplicated tables
   (Turtle Beach listed twice in 0001) and 100+ item URL indexes.

7. **Two genuine harness artifacts to exclude, not penalize.** All five **storm**
   outputs (empty captures / filename-too-long OSError) and **smolagents 0004**
   (the `[Full report content with all citations]` placeholder skeleton) are
   generation/runner failures, not substantive reports.

8. **A shared hidden A/B/C/D template.** Every real 0001/0002/0005 report
   (across agents) uses the identical "(A) Product Landscape / (B) Community
   Sentiment / (C) Technical Grounding / (D) Cross-Source Synthesis" scaffold,
   indicating a strong common system prompt; the better agents (claude-code,
   smolagents) deviate appropriately to the decision-matrix shape on the
   comparison tasks 0003/0004, while weaker agents force the generic template
   regardless of topic.
