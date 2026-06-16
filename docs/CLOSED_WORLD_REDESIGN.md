# Deep Research Arena: Closed-World Redesign (master blueprint)

> Status: design v1 for review. Author: Claude (architecture / spec / acceptance).
> Date: 2026-06-15. This is the single authoritative "what we change and why" for
> the redesign that pivots the benchmark onto its frozen-sandbox / closed-world
> advantage. We intend to change essentially all of the eval content (questions,
> goldens, grounding metric, scoring weights) along the lines below.
>
> Relationship to existing docs:
> - Builds on and cites: `GROUNDING_GATE_ANALYSIS.md`, `EVAL_SET_REMEDIATION.md`,
>   `FRAMEWORK_ROOT_CAUSE.md`, `DATASET_METHODOLOGY.md`, `JUDGE_HUMAN_KAPPA.md`.
> - Refocuses / supersedes: `EVAL_REDESIGN_DESIGN.md`. That draft tried to fix
>   scoring by making the pure-LLM judge better. The thesis here is the opposite:
>   for the objective layer you do not need a better judge, you need the DB. The
>   LLM judge is demoted to the small subjective slice where its fair-to-negative
>   agreement does the least damage.

---

## 1. TL;DR (the pivot in one page)

We are competing in a crowded field (ResearchRubrics, DRACO, DeepResearch Bench,
LiveResearchBench, ReportBench, ...). On the axis we were about to "fix" (realistic
prompts plus expert weighted rubrics plus LLM-judge grounding), improving makes us
converge with that field, not differentiate from it. That axis is a dead end for
novelty.

Our one asset nobody else has is the frozen, offline, self-hosted sandbox web
(Magento shopping `:7770`, Postmill forum `:9999`, Kiwix Wikipedia `:8090`). A
closed world buys three things the entire live-web cohort structurally cannot have:

1. Complete ground truth, computed from the DB (not scraped, not pooled).
2. A reproducible retrieval environment (re-runnable score-identically).
3. Decidable anti-fabrication (reachability is an HTTP/DB fact; quote-match against
   served HTML is exact).

Our own data already points here. `GROUNDING_GATE_ANALYSIS.md` showed that
`quote_match` (a decidable check against the frozen sandbox) is the only signal
that separates honest agents from fabricators, while `curated_must_cite_recall`
(a keyword-crawl proxy) barely separates them at all. The redesign simply takes
the thing that already works (decidable verification against the frozen world) and
makes it the whole objective layer, instead of one noisy half.

The redesign in five moves:

- Questions: strip the prescriptive spec out of the prompt; make the prompt a
  natural research question; move all requirements into the answer key.
- Golden: stop scraping the sandbox with keywords. Derive ground truth from the
  DB. A closed world has a complete, clean, queryable answer set.
- Grounding: replace must-cite-URL recall with a decidable, claim-level,
  anti-fabrication-first metric (reachability gate plus claim support), and fix the
  dead-URL bug that DeepResearch Bench's own FACT implementation has.
- Completeness: because we know the full relevant set from the DB, we can measure
  true completeness (real recall), which no live-web benchmark can do. This is the
  headline novel contribution.
- Subjective quality: keep a thin, openly-borrowed rubric layer (ResearchRubrics /
  RACE style) for synthesis and insight only. Truth-gated Elo math is unchanged.

One-line positioning: the only deep-research benchmark where the retrieval world is
frozen and the ground truth is DB-complete, so grounding and completeness are
decidable rather than estimated.

---

## 2. Diagnosis: why we change all of it

Every claim below is verified against code or against our own prior analysis docs.

### 2.1 The question is a scraping spec, not a research question

`data/tasks/deep_research/cross_site_deep/dr_cross_deep_0001.json` `intent` dictates:
the number of dimensions ("THREE"), exact keyword sets, hard counts (>=120 URLs,
>=60 citations, >=40 products, >=6 brands, >=30 threads, >=25 wiki articles), a
mandatory wiki-article list, the structure of every synthesis subsection, and
`min_words 3500`. In the ResearchRubrics complexity taxonomy this is
Exploration=Low (fully specified equals lowest difficulty). The constraints also
leak from `intent` into `checklists_deep.json` ("at least 40 products?", "exactly
10 items?") and into the golden, so the same rigid quota appears in all three. The
task measures compliance with a checklist, not research.

### 2.2 The golden is a noisy keyword crawl, weighted by the wrong thing

`scripts/build_deep_golden.py`:

- Crawls the sandbox using a keyword list (`_DEFAULT_TOPIC`) that is the same list
  baked into the task intent. The answer key and the question share a keyword
  source, which is circular.
- `must_cite_urls` is every product the crawl found. Weight is assigned by metadata
  completeness, not relevance: price plus rating plus review_count yields weight
  1.0; price only yields 0.5. Topical importance is never considered.
- The relevance filter `_is_product_relevant` is keyword-based and leaks. Even the
  cleaned `data/golden/deep_clean/dr_cross_deep_0001.json` still lists an ear-piercing
  gun (`2-pack-ear-piercing-gun-...`, weight 1.0) and a bluetooth speaker
  (`60w-portable-bluetooth-speaker-...`) as must-cite, pulled in by "ear" / "audio"
  / "wireless". An honest report that omits the ear-piercing gun loses recall.
- "Adaptive compensation" pads reddit and wiki targets to hit an arbitrary total of
  120, so the golden size is driven by a quota, not by what is actually relevant.

`src/verifiers/golden_curate.py` admits the result: the full must-cite recall is
"structurally unreachable", so it derives a top-K=12 at scoring time. But the top-K
is chosen by the same metadata-completeness heuristic, so the relevance blindness is
inherited.

### 2.3 The grounding signal is mostly dead, and our own analysis proves it

`scripts/build_real_leaderboard.py:79` defines the grounding number that gates the
Elo:

```
GROUNDING = 0.5 * curated_must_cite_recall + 0.5 * quote_match_score
```

`GROUNDING_GATE_ANALYSIS.md` (2026-06-03), on cleaned goldens, measured each half:

| agent | curated_recall | quote_match | cohort |
|---|--:|--:|---|
| claude-code | 0.117 | 0.860 | honest |
| camel-ai | 0.118 | 0.776 | honest |
| smolagents | 0.250 | 0.583 | honest |
| gpt-researcher | 0.076 | 0.002 | fabricator |
| langchain-odr | 0.069 | 0.001 | fabricator |

Two conclusions, both already the repo's own:

1. `quote_match` is the discriminator. Fabricators score about 0 (you cannot quote
   a page you never fetched); honest agents score 0.58 to 0.86. It works because it
   is decidable against the frozen sandbox.
2. `curated_must_cite_recall` barely separates the cohorts (honest 0.12 to 0.25 vs
   fabricator 0.07 to 0.08; the strongest honest agent has almost the same recall as
   a fabricator). It is a keyword-crawl proxy, so it carries almost no signal.

So half the grounding gate is noise. `reference_reports/manifest.json` confirms it
at the floor: even the best report selected per task reaches only 0 to 13 percent
must-cite recall.

### 2.4 The LLM judge layer is fair-to-negative, and the deterministic signals are benched

From `EVAL_REDESIGN_DESIGN.md` and `JUDGE_HUMAN_KAPPA.md` (n=80): depth kappa 0.246,
style 0.329, rigor -0.272 (worse than chance), checklist 0.133 (near random). The
deterministic sandbox signals that would actually be reliable (`FactKGVerifier`,
`claim_nli`, `factual_exactness`, `citation`/ALCE) are excluded from the reward
weights. We are leaning on the noisy subjective judges and benching the decidable
ones. That is exactly backwards for a closed world.

### 2.5 The meta-error that unifies all of the above

We have a closed, queryable world and we are treating it like the open web. We scrape
it with keywords, we score recall against the crawl, and we lean on probabilistic LLM
judges. Every problem in 2.1 to 2.4 is a live-web technique misapplied to a sandbox
that does not have the live-web problem.

---

## 3. The strategic question: overlap vs moat

The honest framing of "do we still need to do this":

- On the QA / golden / rubric design axis: overlap with the field is high, and
  "fixing" us along best-practice lines (natural prompts, expert weighted rubrics,
  LLM-judge support) makes the overlap worse. Do not lead here.
- On the closed-world axis: no one is here. The live-web cohort (DeepResearch Bench,
  ResearchRubrics, DRACO, GAIA, BrowseComp) shares one unfixable weakness: their
  ground truth is incomplete and non-reproducible. The whole apparatus of TREC
  pooling, bpref, and NLI judges exists to cope with not knowing the full truth. A
  closed world dissolves that problem instead of coping with it.

Nearest neighbors and the fence:

| neighbor | has | does not have (our wedge) |
|---|---|---|
| WebArena (same sandbox) | frozen, interactive, structured | measures action completion, not report grounding |
| BrowseComp-Plus | frozen corpus, reproducible | flat doc corpus plus short answers, no structured cross-site |
| DeepResearchGym / DRBench-enterprise | reproducible / private closed corpus | not interactive structured multi-site, no DB-complete truth |

Our unique intersection: frozen plus interactive plus typed multi-site plus
DB-complete ground truth plus long-form report grounding. None of the three sit in
it. Note the closed-corpus direction is itself getting crowded, so "frozen corpus"
alone is not the moat. The moat is the DB-complete, queryable, cross-site truth that
lets us compute grounding and completeness exactly.

The empirical anchor for the whole grounding pivot: exact-match against a gold
string/URL correlates with true attribution at only r approx 0.45, whereas
NLI-based "is the claim entailed by some cited source" correlates at r approx 0.96
(AutoAIS, arXiv 2212.08037). Matching specific gold URLs is a weak proxy for what we
care about. Our closed world lets us do the strong version exactly.

---

## 4. The closed-world doctrine (design principles)

1. Split every task into an objective layer and a subjective layer. The objective
   layer is DB-decidable (facts that exist in the sandbox DB, citations that resolve
   and support). The subjective layer is synthesis quality. Score them separately;
   never blend a decidable number with a judge guess into one opaque pillar.
2. The objective layer is the contribution. It is what only a closed world can do.
   Make it exact, deterministic, and reproducible.
3. The subjective layer is borrowed and small. Use a standard rubric (ResearchRubrics
   / RACE), acknowledge it as standard, and keep the noisy judge away from anything
   we can decide instead.
4. Prefer decidable over estimated everywhere. If the DB can answer it, do not ask an
   LLM. If reachability can be checked, do not infer it.
5. Anti-fabrication is enforced multiplicatively, not additively. A fluent report
   built on unreachable or fabricated sources must be crushed, not averaged.
6. Do not import live-web crutches (TREC pooling, bpref). They solve incompleteness,
   which we do not have.
7. Keep truth-gated Elo. We change what feeds the gate, not the Elo math.

---

## 5. Redesign part 1: Questions

### 5.1 What the literature converges on

Across GAIA, BrowseComp(-Plus), HLE, FanOutQA, WebWalkerQA, Mind2Web(2), SealQA,
DeepResearch Bench, and DRACO, the consistent recipe is:

- Separate the prompt from the rubric. The agent sees a natural query; the grader
  uses a per-task rubric or answer key the agent never sees. The cure for an
  over-specified prompt is to move the specification into the answer key.
- Make difficulty come from the world, not the wording. No strong benchmark tells the
  model "use 10 sources" or "write 3500 words". Hardness is structural (multi-hop
  aggregation, conflicting evidence, large search space).
- Gradeability comes from the answer, not the prompt. Pin only the answer's surface
  form when exact-match needs it; push generic output formatting into a shared system
  prompt.
- Enforce unambiguity at construction time, by people, not by prompt verbosity (GAIA:
  two fresh annotators must reproduce the answer; SealQA: "on what date" not "when";
  Mind2Web 2: ban subjective words like "good"/"better" and unverifiable global
  qualifiers like "cheapest"/"top-k").
- Realism comes from provenance (sample real queries, then author to that
  distribution), not from a longer brief.

### 5.2 Concrete changes to our tasks

Edit `data/tasks/deep_research/cross_site_deep/*.json` and the
`configs/deep_topics/*.yaml` generators:

Delete from `intent` and from the task schema:
- `markdown_spec.min_words / min_citations / min_pages_browsed`
- `citation_policy.per_domain_minimum` and the keyword sets
- the mandated wiki-article list and the fixed synthesis subsection structure
- all hard quotas (>=40 products, >=6 brands, >=30 threads, exactly 10 items)

Keep:
- `sites` (cross-site spread is the structural difficulty)
- `start_url`
- the minimal requirement that the answer is a markdown report
- a per-task (Breadth, Depth, Exploration) difficulty label, so under-specification
  becomes a difficulty dimension rather than a defect

Move every deleted requirement into the answer key (sections 6 to 9): the facts go
into the DB-derived golden, the synthesis requirements go into the rubric.

### 5.3 Before / after example (dr_cross_deep_0001, headphones)

Before (excerpt): "Produce a comprehensive market-intelligence report ... spanning
THREE dimensions ... AT LEAST 120 distinct source URLs ... >=40 product pages
spanning >=6 brands and >=3 price tiers ... For EACH product record: exact
product_url, price, star rating ... (D) CROSS-SOURCE SYNTHESIS: 1. List >=5 product
feature claims that ... 4. final TOP-10 list where each pick has (product URL + >=2
reddit URL + >=1 wiki URL)..."

After (natural user voice): "I'm trying to pick noise-cancelling headphones for
commuting and working from home. Which options do people actually recommend, how do
they compare on the things that matter (noise cancelling, battery, comfort, price),
and where do the marketing claims not hold up against what is technically true? Give
me a shortlist I can trust, and back it with what you found."

The cross-site synthesis (shopping facts plus reddit sentiment plus wiki grounding of
claims) becomes implicit and necessary instead of dictated. Difficulty is unchanged
(information is still dispersed across three corpora); it is now a research question
rather than a scraping job.

### 5.4 Construction-time gates (replace prompt verbosity)

For each task, before it ships:
- Unambiguity: two independent solvers (human or a strong agent) reproduce the same
  shortlist / facts from the DB-derived key.
- No single-page shortcut: the answer must require cross-site or multi-page
  aggregation (we already have this structurally).
- Contamination: keep the `CONTAMINATION_REPORT.md` check.
- Saturation (from DRACO): if a frontier agent scores above about 90 percent, the
  task or its key is too easy; revise.

---

## 6. Redesign part 2: Golden derived from the DB

This is the core move. Stop treating the sandbox as the open web.

### 6.1 The principle

The sandbox is a closed world. The Magento DB, the Postmill DB, and the fixed Kiwix
ZIM are the complete, authoritative source of truth. For any task whose relevance
criterion is DB-expressible, the complete relevant set is a query, not a crawl. There
is no ear-piercing gun in `SELECT ... WHERE category = headphones`.

### 6.2 We already have the DB infrastructure

`src/golden/db_connect.py` (`DBRunner`), `src/golden/db_schema_map.py` (`PREDICATES`
with SQL templates for Magento and Postmill, `site_of`), and `src/golden/db_verifier.py`
(`get_store`, `store.verify`) already query the sandbox DBs to verify triples.
`fact_kg_verifier.py` already calls `get_store(...).verify(subject, predicate, object)`.
Deriving a golden adds an enumeration path (SELECT the relevant set) on top of the
existing verification path. This is a smaller lift than the current scraper.

### 6.3 What the DB-derived golden contains, per task

Replace the scraped `must_cite_urls` plus free-text `why` with a clean, typed key:

- `relevant_set`: the complete set of sandbox entities (products, threads, articles)
  that satisfy the task's relevance predicate, each with its canonical sandbox URL
  and the DB-true facts (price, rating, review_count, thread net_score,
  comment_count, wiki defining sentence). This is the completeness denominator
  (section 8) and it is exact.
- `fact_nuggets`: atomic, self-contained claims a good answer should convey, derived
  from the DB rows (for example "AKG K72 is priced at 53.99" or "active noise control
  works by emitting an anti-phase wave"). Each carries an importance weight (vital /
  useful) so missing a core fact costs more than missing trivia. This replaces the
  current `triples` and is scored by semantic coverage, not URL match (section 7).
- No `must_cite_urls`. There is no "cite this exact URL" requirement anywhere in the
  design. URLs matter only insofar as a claim's cited source must resolve and support
  it (section 7).

### 6.4 Why this fixes 2.2 at the root

- Contamination: the DB query is clean; keyword collisions cannot enter.
- Weighting: importance comes from the relevance predicate and a small annotation
  pass, not from whether a row happens to have a review count.
- Circularity: the key is derived from the DB, not from the task's own keyword list.
- Quota padding: the relevant set is whatever the DB returns; no adaptive padding.

### 6.5 Annotation and quality control

- Draft the relevance predicate and fact_nuggets with an LLM from the DB rows, then
  have a human verify and set vital/useful weights (the AutoNuggetizer semi-manual
  pattern, about 1 hour per task; ResearchRubrics is full-human for its highest-stakes
  key). The DB rows make this fast and unambiguous.
- Prefer binary or graded-binary importance over scalar (ResearchRubrics: binary
  agreement 0.73 to 0.76 vs ternary 0.53 to 0.57).

---

## 7. Redesign part 3: Grounding metric (decidable, anti-fabrication-first)

Replace the `curated_must_cite_recall` half of the gate with a decidable, claim-level
grounding metric synthesized from ALCE (load-bearing citation precision), SAFE
(F1@K recall, anti-brevity), DR Tulu (R_fmt reachability, NeedCite missing-citation
penalty), and TREC (first-citation-only anti-stuffing), while fixing the dead-URL bug
in DeepResearch Bench's FACT.

The bug to fix and own: FACT's released code (DeepResearch Bench, `utils/stat.py`)
drops "unknown" / dead URLs from both the numerator and the denominator, so a 404 /
fabricated citation is cost-free. For a "fluency is not grounding" benchmark this is
exactly the wrong default. In our closed world reachability is decidable, so we make
unreachable a failure, not an exclusion.

### 7.1 The metric

Stage 0, decompose. Extract atomic claims `K` from the report (FActScore / SAFE
style, revised self-contained). Mark the subset `K_req` that requires a citation
(non-trivial factual claims; a NeedCite classifier excludes common knowledge, as in
DR Tulu). We already have `claim_nli.py` and `triple_extractor.py` to build on.

Stage 1, reachability gate (the part FACT omits). For every cited source `u`, resolve
it in the sandbox. `reachable(u) = 1` if it serves non-empty content, else 0. A claim
whose only citations are unreachable is treated as uncited, and each dead citation is
a precision hit. Reuse `url_reachability_verifier.py`.

Stage 2, support check (claim level). For claim `k` and its reachable cited content,
`supp(k)` in {1.0 full, 0.5 partial, 0.0 none} (TREC rubric). Require an extractive
quote span for full support (our existing `quote_match_verifier.py` plus
`citation_nli.py` provide this). The quote anchor suppresses the judge's
parametric-knowledge leakage.

Stage 3, citation precision (ALCE load-bearing, stuffing-proof). A citation `u` of
`k` is valid iff it is reachable and load-bearing (it independently supports `k`, or
removing it drops support). `CitePrec(k) = valid citations / total citations of k`.
`ReachRate = reachable citations / all citations in the report`.

Stage 4, grounding recall with saturation (SAFE, anti-brevity).
`G = sum over k in K_req of supp(k)`. With target depth `K*` (expected number of
grounded claims for a good answer), `GroundRecall = min(G / K*, 1)`. Abstaining or
thin reports cap recall.

Stage 5, grounding precision. `GroundPrec = sum over k in K_req of supp(k) * CitePrec(k)
/ |K_req|`. Irrelevant claims dropped first (SAFE relevance gate).

Stage 6, headline (gated F1).
```
GroundF1 = 2 * GroundPrec * GroundRecall / (GroundPrec + GroundRecall)   (0 if G = 0)
GROUNDING = ReachRate^gamma * GroundF1                                    (gamma >= 1)
```
The `ReachRate^gamma` multiplicative gate is the anti-fabrication enforcer: a fluent
report citing mostly unreachable sources has low ReachRate, which crushes the score
regardless of the few reachable claims. This is the same intuition as truth-gated
Elo; gamma > 1 makes fabrication super-linearly costly. `quote_match`, the signal our
gate analysis already validated, is now the kernel of `supp(k)` rather than a separate
additive half.

Also add the DR Tulu missing-citation penalty: a `NeedCite=1` claim that is uncited
scores recall 0 for that claim. Without it, an agent games by simply not citing shaky
claims (FACT never extracts uncited claims, so they are invisible).

### 7.2 Why each required property holds

- Rewards reachable-supported claims: `supp(k)` is computed only over reachable cited
  content.
- Penalizes fabricated / unreachable / irrelevant: unreachable fails Stage 1 and the
  gate; real-but-irrelevant citations fail the ALCE load-bearing test; irrelevant
  claims are dropped (SAFE).
- Stuffing-proof: precision divides by total citations and non-load-bearing citations
  are dead weight (ALCE); recall saturates at K* (SAFE); optionally grade only the
  first reachable citation per claim (TREC).
- Claim granularity: everything is per-claim, never whole-report.

---

## 8. Redesign part 4: Completeness metric (the closed-world superpower)

This is the headline novel contribution and it is impossible on the live web.

Because `relevant_set` (section 6.3) is the complete DB-derived set, we can measure
true completeness: of the entities that genuinely satisfy the task, how many did the
report actually surface and use correctly?

```
Completeness = (relevant entities correctly surfaced in the report) / |relevant_set|
```

"Correctly surfaced" means the entity appears with a DB-true fact (not invented), so
completeness composes with grounding (a hallucinated entity does not count). Optionally
weight by entity importance (vital products count more), giving a graded completeness
analogous to nDCG but with an exact denominator.

Why this is unique: live-web benchmarks cannot compute the denominator (they do not
know the full relevant set), which is the entire reason TREC invented pooling and
bpref. We have the denominator for free. We therefore do not build pooling or bpref;
we report exact completeness instead of an incompleteness-robust estimate.

Honesty bound: completeness is exact only when the task's relevance criterion is
DB-expressible. For fuzzier, open-ended synthesis, completeness falls back to the
rubric (section 9). The clean split is: DB-expressible facts go to the objective
layer; everything else goes to the subjective layer.

---

## 9. Redesign part 5: subjective rubric layer (borrowed, small)

Facts and sources are objective; analysis quality is not. Add a thin, openly-standard
rubric per task for synthesis, insight, instruction-following, and readability.

- Atomic binary criteria `{criterion, weight, axis}`, weights in [-5, +5] including
  negative penalty criteria (verbosity, irrelevance, fabrication). Prefer binary over
  Likert (ResearchRubrics agreement gain about 20 points).
- Score `sum(weight * met) / sum(positive weights)`, negative weights excluded from
  the denominator.
- We already have the machinery: `checklist_verifier.py` `_verify_snapshot` accepts
  `{criterion, weight}` items and grades FULL/PARTIAL/NONE with n-sample median and a
  weighted score. So this layer is mostly a data change: rewrite
  `checklists_deep.json` from quota yes/no items into RR/DRACO-style weighted criteria.
- Optionally reference-anchored (RACE): score the target and a strong reference report
  against the same criteria and report the ratio `S_tgt / (S_tgt + S_ref)` to
  neutralize judge-scale drift. We currently have no gold report text on disk; if we
  add one per task it serves only as a comparative anchor, never as a string to match.
- Counter the judge's lean: judges over-grant support (TREC kappa 0.27 to 0.29; GPT-4
  about 45 F1 on contradiction; AttributionBench ceiling about 80 F1). Use the
  existing 3-judge jury with strict tie-breaking, diversify judge model families, and
  treat subjective scores as rankings, not absolute values.

---

## 10. Scoring integration (truth-gated Elo unchanged)

The Elo math does not change. We change what feeds the gate and we re-balance the
composite toward the decidable signals.

Grounding gate, in `scripts/build_real_leaderboard.py` (`_fallback_grounding` /
`grounding_for`) and `src/scoring/simple_score.py`:
```
before: 0.5 * curated_must_cite_recall + 0.5 * quote_match_score
after:  ReachRate^gamma * GroundF1        (section 7; quote_match is now its kernel)
```

Composite, conceptually:
```
objective (decidable, the contribution):
    GROUNDING       (section 7)
    Completeness    (section 8)
subjective (borrowed, small):
    rubric quality  (section 9)
headline = judge_Elo * grounding_gate     (unchanged; gate now = the section-7 number)
```

Promote the deterministic verifiers currently benched (`fact_kg`, `claim_nli`,
`citation`/ALCE, `factual_exactness`) into the objective layer; demote the
fair-to-negative scalar judges (rigor especially, kappa -0.272) out of anything
load-bearing.

---

## 11. What to drop

- Must-cite-URL recall, in every form (curated, full, pool_coverage as a grounding
  signal). It is the r approx 0.45 proxy and our own gate analysis shows it barely
  separates cohorts.
- TREC pooling and bpref. They solve incompleteness, which a closed world does not
  have. Building them would import a live-web solution into a problem we do not have.
- The keyword crawler `build_deep_golden.py` as the golden source (keep it only as an
  optional candidate-pool helper, never as ground truth).
- Adaptive compensation / the 120-URL quota.
- The rigid quotas in `intent` and `checklists_deep.json`.
- The pure-LLM-perfect-scoring premise of `EVAL_REDESIGN_DESIGN.md` for the objective
  layer.

---

## 12. Migration plan (phased, file-level)

P0, lowest risk, highest value (fix the dead grounding signal and the contamination):

| change | files |
|---|---|
| Swap grounding gate to `ReachRate^gamma * GroundF1`; fix dead-URL = failure | `scripts/build_real_leaderboard.py`, `src/scoring/simple_score.py` |
| Assemble the section-7 metric from existing parts | `url_reachability_verifier.py`, `citation_nli.py`, `claim_nli.py`, `quote_match_verifier.py` (new orchestrator e.g. `src/verifiers/grounding_verifier.py`) |
| One-time golden de-contamination pass (drop off-topic must-cite / triples) | `data/golden/deep_clean/*`, `src/verifiers/golden_curate.py` |

P1 (the closed-world rebuild and de-specified questions):

| change | files |
|---|---|
| DB-derived golden: add enumeration path; emit `relevant_set` + `fact_nuggets` | `src/golden/db_*`, new `scripts/build_db_golden.py` to replace `build_deep_golden.py` |
| Completeness verifier against `relevant_set` | new `src/verifiers/completeness_verifier.py` |
| Rewrite `fact_kg_verifier` recall to semantic nugget coverage | `src/verifiers/fact_kg_verifier.py` |
| De-specify task intents; add (Breadth, Depth, Exploration) labels | `data/tasks/deep_research/cross_site_deep/*.json`, `configs/deep_topics/*.yaml` |
| Rewrite checklists into weighted rubric criteria (data change) | `data/tasks/deep_research/cross_site_deep/checklists_deep.json` |

P2 (optional polish):

| change | files |
|---|---|
| Reference report per task as a RACE anchor (not a gold string) | `data/reference_reports/*` |
| Construction-time gates as a CI check (unambiguity, saturation) | new `scripts/validate_task.py` |

Each phase: run the focused verifier tests (`tests/test_rubrics.py`,
`tests/test_golden_curate.py`, and new tests for the grounding/completeness verifiers),
then rebuild the board and confirm the honest-vs-fabricator separation is preserved or
improved (this is the acceptance bar inherited from `GROUNDING_GATE_ANALYSIS.md`).

---

## 13. Risks and defenses

1. Realism. A frozen Magento/Postmill/Kiwix sandbox is not the real web; reviewers
   will say so. Defense: own the trade-off explicitly (the WebArena / BrowseComp-Plus
   stance): we trade realism for control and decidability, which is the right trade
   for measuring grounding. State it in the paper, do not hide it.
2. The sandbox is borrowed from WebArena. "We have a sandbox" is not novel. Defense:
   the novelty is the first DB-grounded deep-research-report evaluation on a frozen
   sandbox, turning an action environment into a grounding/completeness instrument
   with closed-world answer keys. WebArena checks state changes; we check report
   grounding against DB-complete truth.
3. The closed-corpus direction is getting crowded (BrowseComp-Plus, DeepResearchGym,
   DRBench-enterprise). Defense: frozen corpus is not the moat; DB-complete,
   queryable, cross-site structured truth is. Fence the three neighbors (section 3).
4. Judge error floor (about 15 to 25 percent) on the subjective layer. Defense: keep
   the subjective layer small, multi-judge, diversified, and reported as a ranking.
   The objective layer carries the weight and is decidable.
5. Sandbox staleness / non-durable corpus (memory: `reset.sh` wipes the seed). Defense:
   pin and version the DB snapshot; derive goldens from the pinned snapshot; record the
   snapshot hash with each board.

---

## 14. Paper alignment ("Fluency Is Not Grounding")

The closed-world pivot sharpens the `paper_iclr` thesis from an argument into a proof.
On the live web you can only argue that fluent reports are not grounded. In a closed
world you know the true facts (DB) and you know which URLs are real (reachability), so
"fluency is not grounding" becomes a measured, reproducible fact. New claims this
unlocks:

- First decidable grounding metric for long-form deep research (no NLI-judge error
  floor on the reachability part; exact quote-match).
- First true completeness metric for deep research (exact denominator from the DB),
  versus the field's pooled / bpref estimates.
- A concrete methodological correction over the current SOTA implementation: FACT's
  dead-URL-is-free bug, which we fix and can demonstrate.

The instrument-to-finding-to-fix story in the existing outline still holds; the
instrument is now sharper and the finding is now provable.

---

## 15. Open decisions for you

1. K* (grounding recall saturation) and gamma (reachability gate exponent): start
   K* per-task = size of fact_nuggets vital subset, gamma = 1, then tune so
   honest-vs-fabricator separation is maximized.
2. Nugget importance: how many annotators / judges vote vital vs useful (1 LLM draft
   plus 1 human, or a 3-vote panel?).
3. DB enumeration scope: which relevance predicates per domain (price/category/rating
   for shopping; forum/score for reddit; topic for wiki).
4. Number of tasks to rebuild first (suggest 10 to 20 cross-site tasks as the closed-
   world pilot, mirroring DeepResearch Bench's 100-to-10 compression discipline).
5. Realism framing for the paper: how hard to lean on "control over realism".
6. Whether to keep any backward-compatible board on the old metric during migration.

---

## Appendix A: current-state file inventory and its fate

| file | today | fate |
|---|---|---|
| `data/tasks/.../cross_site_deep/*.json` | over-specified intents | de-specify, add difficulty labels |
| `configs/deep_topics/*.yaml` | keyword/quota generator | becomes DB relevance-predicate config |
| `scripts/build_deep_golden.py` | keyword crawler -> must_cite + triples | demote to optional candidate-pool helper |
| `src/golden/db_*` | verify single triples vs DB | add enumeration; source of the golden |
| `data/golden/deep_clean/*` | scraped, still contaminated | regenerate from DB (relevant_set + fact_nuggets) |
| `src/verifiers/golden_curate.py` | top-K band-aid | retire (no must-cite set to curate) |
| `src/verifiers/url_coverage_verifier.py` | must-cite recall headline | retire / replace with completeness verifier |
| `src/verifiers/fact_kg_verifier.py` | substring recall vs triples | semantic nugget coverage |
| new `src/verifiers/grounding_verifier.py` | none | section-7 decidable grounding |
| new `src/verifiers/completeness_verifier.py` | none | section-8 closed-world completeness |
| `src/verifiers/checklist_verifier.py` | DRACO-style, has weighted snapshot path | keep; feed weighted rubric data |
| `data/tasks/.../checklists_deep.json` | quota yes/no | weighted rubric criteria |
| `scripts/build_real_leaderboard.py` | gate = 0.5 recall + 0.5 quote | gate = ReachRate^gamma * GroundF1 |
| `src/scoring/simple_score.py` | grounding_score | implement the section-7 number |

## Appendix B: literature pointers (the one actionable thing from each)

- AutoAIS, arXiv 2212.08037: exact-match vs attribution r 0.45; NLI vs attribution
  r 0.96. The reason to drop URL-match grounding.
- ALCE, arXiv 2305.14627: load-bearing citation precision (penalize non-necessary
  citations). Anti-stuffing.
- FActScore, arXiv 2305.14251: atomic-fact precision; gameable by abstaining.
- SAFE / LongFact, arXiv 2403.18802: F1@K, R_K = min(S/K, 1). The anti-brevity fix.
- DeepResearch Bench (FACT), arXiv 2506.11763: re-fetch cited URLs; but code drops
  dead URLs from numerator and denominator (the bug we fix).
- DR Tulu, arXiv 2511.19399: R_fmt reachability fraction; NeedCite missing-citation
  penalty.
- TREC RAG / AutoNuggetizer, arXiv 2411.09607, 2504.15205: vital/useful nuggets;
  first-citation-only anti-stuffing; judge leniency kappa 0.27 to 0.29.
- ResearchRubrics, arXiv 2511.07685: weighted human rubric; binary beats ternary by
  about 20 points; no LLM seeding.
- DRACO, arXiv 2602.11685: real-query provenance; saturation test (above 90 percent
  equals too easy); weighted negative criteria.
- GAIA, arXiv 2311.12983: short verifiable answers; two-annotator unambiguity; do not
  fix the source list.
- BrowseComp(-Plus), arXiv 2504.12516 / 2508.06600: inverted construction; frozen
  corpus for reproducibility.
- WebArena, arXiv 2307.13854: abstract high-level intents; functional state eval (the
  sandbox we repurpose).
- Mind2Web 2, arXiv 2506.21506: ban subjective words and unverifiable qualifiers;
  judge tree.

---

## 17. Implementation progress log (2026-06-15)

Live record of what has been built and what was learned while executing this plan.
Append new findings here.

### Delivered (code + tests, all offline, NO paid API)
- `src/scoring/closed_world_grounding.py` -- pure section-7 metric
  (ReachRate**gamma * GroundF1@K*; dead-URL penalized = FACT bug fixed; ALCE
  load-bearing precision; SAFE F1@K; NeedCite). Tests
  `tests/test_closed_world_grounding.py` (10).
- `src/verifiers/grounding_verifier.py` -- orchestrator. Claim split, sandbox
  fetch (injectable), support via deterministic token-overlap by default or the
  self-hosted vLLM judge (`use_llm=True`, with deterministic fallback);
  load-bearing kept on cheap token-overlap so LLM calls are ~1 per claim. Tests
  `tests/test_grounding_verifier.py` (6).
- `src/verifiers/completeness_verifier.py` -- section-8 exact completeness vs the
  DB-derived relevant_set. Tests `tests/test_completeness.py` (6).
- `src/scoring/local_llm.py` -- stdlib OpenAI-compatible client for the my5090
  vLLM (support_level / needs_citation / available); single judge model = Qwen3-8B.
- `scripts/score_closed_world.py` -- batch/single scorer; merges the `grounding`
  (+ `completeness`) pillar into each report's `.score.json`. Includes a sandbox
  port-remap fetcher (CW_SANDBOX_REMAP) and configurable fetch timeout/retries.
- `scripts/build_real_leaderboard.py` -- gate swap: `grounding_for` now prefers
  the decidable closed-world `grounding` pillar, falling back to the legacy
  additive `0.5*must_cite_recall + 0.5*quote_match` only when it is absent.
- Total: 22 offline tests green.

### Local LLM (judge) -- see memory my5090-vllm-serve
vLLM 0.23.0 in `/root/vllm-venv` on my5090 (torch 2.11+cu130, sees 5090 sm_120).
Serving Qwen3-8B from `/mnt/e/models/Qwen3-8B` on 127.0.0.1:8000. Two WSL
workarounds REQUIRED: `VLLM_USE_V2_MODEL_RUNNER=0` (no UVA on WSL) and
`VLLM_USE_FLASHINFER_SAMPLER=0` (no nvcc for FlashInfer JIT). Per the directive we
run EVERYTHING on 8B first; judge = same one model; swap later.

### Box sandbox state (FINDING -- needs attention for a fair full run)
On my5090 WSL the sandbox ports differ from the canonical ones the reports cite:
- shopping: served on **17770** (reports cite 7770) -> handled by CW_SANDBOX_REMAP
  `localhost:7770=localhost:17770`.
- wiki: **8090** (matches).
- reddit: **9999 currently DOWN** (curl 000); gateway 8081 down. Bring-up scripts
  exist at `/root/start_shim.sh`, `/root/start_ds_proxy.sh`,
  `/root/start_wiki_overlay.sh`. Reddit must be revived for fair scoring, else
  reddit citations are (correctly) counted unreachable and drag reach_rate.

### Pipeline VALIDATED end-to-end (2-report pilot, 8B judge, on box)
`bash /root/run_cw.sh --batch data/results/deep --use-llm --limit 2`:
- camel-ai dr_cross_deep_0001: grounding 0.356, reach 0.72, 44 required claims, 96 cited.
- camel-ai dr_cross_deep_0002: grounding 0.172, reach 0.46, 69 required claims, 105 cited.
Sensible and decidable: reach<1 reflects the down reddit; more reddit citations ->
lower reach -> lower grounding (the dead-URL penalty working on real data).

### Box durability (BLOCKER for the full batch)
my5090 kills SSH-detached jobs ~13s after the launching ssh closes (memory
my5090-detached-proc-kill); vLLM and a probe were killed mid-session by tunnel
blips. The full batch must run inside ONE held ssh session that starts vLLM, waits
for ready, then runs the batch (and ideally a heartbeat/watchdog). Batch results
merge per-report into `.score.json` so a restart resumes without data loss.

### KEY VALIDATION: the metric catches fabrication decidably (the thesis, live)
In the full 8B run, camel-ai's dr_cross_deep_0003 report scored grounding 0.000,
reach 0.00 across 180 citations. Inspection showed the citations are FABRICATED URL
schemes that do not exist on the sandbox: `http://localhost:7770/products/<slug>`,
`http://localhost:8090/articles/<slug>`, `http://localhost:9999/threads/<slug>`
(the real schemes are `/<slug>.html`, `/content/<zim>/A/<title>`, `/f/<forum>/<id>`).
A fluent, well-structured report built on hallucinated sources is crushed to 0 by
the reachability gate, while the same agent's genuinely-grounded reports score 0.72
to 0.87. This is "Fluency Is Not Grounding" measured, not argued -- exactly what a
closed world buys. (On the live web FACT's dead-URL-excluded bug would have scored
these fabrications as cost-free.)

### Remaining plan items (status)
- [x] P0 gate swap; section-7 grounding metric; section-8 completeness verifier.
- [x] ~~P0 golden de-contamination~~ -> OBSOLETED by the DB-derived golden: DB
  enumeration with precise LIKE keywords cannot admit keyword-collision noise
  (no ear-piercing gun in `WHERE name LIKE '%headphones%'`), so cleaning the old
  scraped golden is unnecessary; it is retired.
- [x] P1 `scripts/build_db_golden.py` (DB-derived relevant_set + weighted
  fact_nuggets via DBRunner). Runs on the box; DB (Magento/Postmill containers)
  must be queryable -- pending a confirmed live DB.
- [x] P1 `fact_kg_verifier` -> prefers DB-golden fact_nuggets, importance-weighted
  recall (vital 1.0 / useful 0.5).
- [x] P1 de-specify pilot task `dr_cw_pilot_0001.json` (natural intent, difficulty
  axes, no quotas in the prompt) + weighted rubric `rubrics_cw.json` (RR/DRACO
  style, [-5,5], negative penalty criteria); wired into checklist_verifier via
  `rubric_path` -> graded `_verify_snapshot`.
- [x] Full 8B run over all 24 box reports DONE (held-session `/root/run_all_cw.sh`;
  grounding merged into each `.score.json`; 25 local tests + the run green).
- [x] Container reachability ROOT CAUSE + FIX (2026-06-15): all 5 sandbox
  containers (dr_sandbox_shopping:17770, reddit:9999, wiki:8090, gateway:8081,
  ds_proxy) were Up+healthy in docker, but `localhost:9999`/`:8081` returned 000
  from the Ubuntu WSL distro while `:17770`/`:8090` worked. Cause: the containers
  run in the `docker-desktop` WSL distro and cross-distro port forwarding to the
  Ubuntu distro is provided by the Docker Desktop Windows app's proxy; with Docker
  Desktop closed the proxy was partial, so some published ports did not forward.
  Fix: reopen Docker Desktop -> all ports reachable (17770/9999/8090 = 200;
  reddit /f/technology = 200; 8081 root 404 is expected). DB now queryable:
  802 products LIKE '%headphones%', 243 reddit threads. Also fixed `db_connect.py`:
  wrong container names (webarena_* -> dr_sandbox_*) and the Postmill psql call
  (BusyBox `su - postgres -c ...` -> `psql -U postgres`).
- [x] FAIR RERUN (reddit up) DONE: grounding re-scored (overwrite) + board rebuilt
  on 8B, judge_error_fraction 0.0. Honest grounding rose (claude-code 0.238->0.378
  etc.); fabricators stayed ~0. See the board table above.
- [x] build_db_golden RUN on the live DB (from workstation, WESTD_SSH_HOST=my5090):
  dr_cw_pilot_0001 -> 982 clean entities (635 products + 347 threads), 1237 nuggets
  (857 vital), zero keyword-collision contamination.

### REAL ACTIVE TASKS MIGRATED (not just the pilot) -- the two asks, realized
Both headline asks are now applied to the 4 scored tasks (dr_cross_deep_0001-0004),
not only a pilot template:

1. DB-derived golden (the novelty): `scripts/build_db_golden.py` run for all four
   with their topic configs -> clean relevant_set + weighted nuggets
   (0001 headphones 1156 entities, 0002 coffee 390, 0003 fitness 157, 0004 photo
   1755). Zero contamination (DB LIKE on specific keywords, not the old crawl).
2. De-specified intents (`scripts/despecify_tasks.py`): the over-specified
   "scraping spec" prompts are replaced by natural user questions; the quotas /
   keyword lists / mandated sections are gone. intent length 2773->411 (0001),
   2734->317 (0002), 1506->338 (0003), 1611->344 (0004); original kept as
   intent_v1_legacy; tasks now carry difficulty axes + completeness/grounding config.

Completeness (CompletenessVerifier) now uses completeness@K (top-K by importance,
default K=40) so the denominator is a realistic target rather than the whole
catalog. Per-agent completeness@40 over the 4 tasks: claude-code 0.087 >
camel-ai 0.056 > smolagents 0.019 > gpt-researcher / langchain-odr / storm 0.000.
It orders honest > fabricator correctly; absolute values are modest because the
denominator is the EXACT DB-complete relevant set (the closed-world novelty: no
live-web benchmark can even compute this denominator).

HONEST CAVEATS (open tuning, not blockers):
- The relevance predicate is broad for some topics (0001/0004) -> large relevant_set.
  Scope it per task (e.g. price/category filters) for a sharper completeness scale.
- The scored reports were generated against the OLD over-specified prompts; a fully
  clean evaluation of the de-specified questions needs RE-RUNNING the agents on the
  new natural prompts (agent-harness / Codex lane). Grounding + completeness are
  largely prompt-independent (they check cited-source support and DB-topic coverage),
  so the current numbers are meaningful, but a fresh agent run closes the loop.

### FINAL EVERYTHING-RUN on the de-specified tasks (2026-06-15, all 8B, zero API)
One clean end-to-end pass over the 4 de-specified tasks x 6 agents: grounding +
completeness@40 (DB goldens) + truth-gated Elo board (judge Qwen3-8B,
judge_error_fraction 0.0, 36 battles, 26 dropped for a gated side). (The held
session was killed twice by vicp-tunnel blips; it is resumable and finished on the
third launch -- box-durability caveat stands.)

| agent | quality_elo | grounding | completeness@40 | gated? |
|---|--:|--:|--:|---|
| langchain-odr  | 1155.8 | 0.000  | 0.000 | GATED (fabricator) |
| gpt-researcher | 1090.5 | 0.0002 | 0.000 | GATED (fabricator) |
| claude-code    | 1008.9 | 0.375  | 0.087 | no -> truth-gated #1 |
| camel-ai       |  907.0 | 0.271  | 0.056 | no |
| smolagents     |  837.8 | 0.231  | 0.019 | no |

Effect, on the redesigned benchmark (natural prompts + DB-complete truth): the two
top quality-Elo agents are fluent fabricators, gated out by the decidable grounding;
claude-code wins the truth-gated board and also leads on the DB-completeness
dimension. Grounding is essentially unchanged from the old-intent board
(claude-code 0.375 vs 0.378) because grounding is prompt-independent and the
gate dominates -- de-specification fixed the benchmark DEFINITION (the prompt is now
a real research question) without perturbing the truth-gated outcome.
- [x] Full Elo board rebuilt with the new gate, judge = Qwen3-8B
  (`data/results/deep/leaderboard_cw.json`; grounding source confirmed
  `closed_world`). Required a judge-routing fix: judge_client sent Qwen3
  `enable_thinking` as a top-level body field, which vLLM rejects -> every battle
  errored; fixed to `chat_template_kwargs={"enable_thinking": false}` for the
  local OpenAI endpoint (DashScope still gets the top-level field).

### FULL TRUTH-GATED BOARD (8B quality judge x closed-world grounding gate)
FAIR run (reddit UP after the Docker Desktop fix), 36 pairwise battles,
grounding_floor 0.05, grounding source = closed_world, judge_error_fraction = 0.0:

| agent | quality_elo | grounding (fair) | gated? |
|---|--:|--:|---|
| gpt-researcher | 1136.3 | 0.0002 | GATED (fabricator) |
| langchain-odr  | 1136.3 | 0.000  | GATED (fabricator) |
| claude-code    | 1029.3 | 0.378  | no -> truth-gated #1 |
| smolagents     |  863.9 | 0.231  | no |
| camel-ai       |  834.1 | 0.271  | no |

Truth-gated quality ranking (ungated only): claude-code > camel-ai > smolagents.

THE THESIS, MEASURED: the two HIGHEST quality-Elo agents (gpt-researcher,
langchain-odr, both ~1136) are fluent fabricators; the closed-world grounding gate
excludes them (26 of 36 battles dropped for touching a gated side), so the honest
agents win the truth-gated board. A naive fluency/quality leaderboard would have
crowned a fabricator. storm excluded as invalid-capture (empty/stub); smolagents
0004 excluded (28 words).

Fairness lift from reviving reddit (grounding, reddit-down -> reddit-up):
claude-code 0.238 -> 0.378, camel-ai 0.198 -> 0.271, smolagents 0.083 -> 0.174
(per-agent mean over 4 tasks); fabricators stay ~0.000 (they fabricate regardless).
This confirms the metric rewards reachable+supported citations and cannot be helped
by reddit coming back if the citations were fabricated to begin with.

### FULL 8B RUN RESULTS (24 reports, all 6 box agents, judge = Qwen3-8B)
Per-agent mean closed-world grounding (ReachRate*GroundF1@K*, gamma=1):

| agent | mean grounding | reach | reading |
|---|--:|--:|---|
| claude-code    | 0.238 | ~0.66 | honest: cites reachable sandbox sources, claims supported |
| camel-ai       | 0.198 | ~0.50 | honest |
| smolagents     | 0.083 | mixed | partly grounded (0.62 on one task, ~0.05 on others) |
| gpt-researcher | 0.000 | 0.02  | FABRICATES URLs (98% unreachable) -> crushed to 0 |
| langchain-odr  | 0.000 | 0.02  | FABRICATES URLs -> crushed to 0 |
| storm          | 0.000 | n/a   | no extractable sandbox citations |

The decidable gate cleanly separates honest agents (0.2+) from fabricators (0.000):
the thesis, measured on real reports with the local 8B judge, no API. Caveats: (1)
reddit (9999) is down, so reddit citations count unreachable and depress even honest
scores (a fair rerun with reddit up will raise claude-code / camel-ai); (2) these are
the grounding-gate values, not yet multiplied into the Elo board. Compare to the old
gate where curated_must_cite_recall barely separated cohorts (0.12-0.25 honest vs
0.07-0.08 fabricator, GROUNDING_GATE_ANALYSIS.md): the closed-world grounding makes
the honest/fabricator gap an order of magnitude cleaner.
