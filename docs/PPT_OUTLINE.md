# Deep-Research Arena: Slide Outline

Target: 17 slides. Each slide has a one-sentence headline, 2-4 talking points, and a visual cue. The deck is meant to stand alone if read straight through.

---

## Slide 1: Title

Deep-Research Arena: A Sandbox Benchmark for Open-Source DR Agents

- 13 frameworks, 57 cross-site tasks, one sealed local sandbox.
- Truthfulness-gated scoring on 7 pillars, ranked by Bradley-Terry Elo.
- Backbone: DeepSeek V4-flash. Public leaderboard + repo.

Visual: project logo or screenshot of the live leaderboard top-3 row.

---

## Slide 2: The problem with live-internet DR benchmarks

Real-internet evaluation drifts and cannot be ground-truthed.

- A page that supports a claim today may 404 tomorrow.
- Two researchers running "the same" benchmark a month apart get different numbers.
- Scoring URL truthfulness on the live web is borderline impossible at scale.
- GAIA / BrowseComp test product capability; we want a science-grade signal.

Visual: split image. Left: live web URLs going stale (404 / changed-content icons). Right: sealed sandbox icon (locked box).

---

## Slide 3: Our answer, sealed sandbox

Trade live-web realism for ground truth and reproducibility.

- Three local services pretend to be Amazon, Reddit, Wikipedia.
- Frozen golden URL pools, scraped once, never regenerated.
- Every cited URL is checkable in O(1): in-pool, reachable, page contains the quote.
- Anyone with the sandbox snapshot reproduces the leaderboard exactly.

Visual: diagram of agent --> shim --> three sandbox boxes (Magento / Postmill / Kiwix) plus the LLM proxy.

---

## Slide 4: The sandbox, in numbers

Three corpora, one search shim, ~120 must-cite URLs per task.

- Magento on `:7770`, ~2000 product pages.
- Postmill on `:9999`, forum threads with comments and tags.
- Kiwix on `:8090`, an offline Wikipedia ZIM.
- Search shim on `:8081` is Tavily-compatible and indexes all three.

Visual: table with the four services and their URLs, plus a sample task prompt below.

---

## Slide 5: Tasks

57 cross-site research prompts, each demanding 120+ distinct URLs across all three sources.

- Six task types: recommendation, comparison, debunking, causal, timeline, enumeration.
- One-paragraph prompt in, one markdown report out.
- 21-item task-specific checklist scored by an LLM judge per task.
- 100 designed, 57 scored, the rest queued.

Visual: a single anonymized task prompt rendered as a doc, with annotated pillars (must-cite count, checklist length).

---

## Slide 6: The 7 scoring pillars

Five deterministic pillars, two LLM-judged, one composite headline.

- URL coverage (recall against pool), URL reachability (HTTP probe), Quote match (fuzzy text), Citation alignment (ALCE-style), Spec compliance (word/citation/paragraph counts).
- Checklist judge (21 yes/no), Analysis depth + Presentation rubrics.
- Two LLM-judged pillars only feed `composite_v3`; headline is `composite_v2`.

Visual: 7-column bar diagram, each column color-coded deterministic vs LLM-judged.

---

## Slide 7: The truthfulness gate

`composite_v2 = truth_gate · quality`, multiplicatively.

- `composite_v2 = reachability · qm_factor · nli_factor · (0.40·URL_coverage + 0.40·judge + 0.20·spec)`.
- Reachability = 0 zeros the entire score, regardless of fluency.
- Quote-match enters as `0.5 + 0.5·quote_match`, so unverifiable quotes scale the score by half.
- The gate is the headline design choice, and what makes the ranking honest.

Visual: equation displayed large; below, two side-by-side mini-reports (one with fabricated URLs, one with real URLs) and their resulting scores.

---

## Slide 8: From scores to ranks: Bradley-Terry Elo

Pairwise battles cancel per-task baseline difficulty.

- For every task where two agents both score, the higher composite wins; ties under epsilon are draws.
- Battle matrix fits a Bradley-Terry model (the chess Elo model).
- 95% bootstrap CI per agent (1000 resamples).
- Permutation tests give p-values for adjacent rank gaps.

Visual: minimal cartoon of one task = many battles, then a battle matrix --> single Elo number plus CI bar.

---

## Slide 9: Headline leaderboard

Three clusters separated by a 350-Elo cliff.

- Top cluster (~1300-1500): camel-ai, flowsearcher-ds, smolagents.
- Middle cluster (~820-945): ldr, gpt-researcher, deerflow.
- Bottom cluster (~720): ii-researcher, langchain-odr, storm.
- Only the top-vs-middle gap is statistically significant under permutation.

Visual: full 9-row leaderboard table (Rank, Agent, Elo, CI, W/L/D), with the three clusters color-banded.

---

## Slide 10: Top cluster: why these win

camel-ai, flowsearcher-ds, smolagents treat citations as contracts.

- Explicit URL-dedup and citation-validation passes inside the agent loop.
- Disciplined per-source URL budgets (don't blow the whole budget on Wikipedia).
- camel-ai #1 (1481 Elo); the gap to flowsearcher-ds is not significant (p=0.31).
- smolagents is a generic agent, not DR-specialist; the architecture matters more than the label.

Visual: side-by-side excerpt from a top-agent report and a middle-cluster report, with citations highlighted.

---

## Slide 11: Middle cluster: almost-worked

Each middle-cluster agent fails truthfulness in a recognizable way.

- ldr lower-cases Kiwix paths; Kiwix is case-sensitive on article names. Reachability ~0.
- gpt-researcher templates Magento slugs (`/products/<kebab>`), but real slugs include numeric suffixes.
- deerflow truncates citation tables, passing spec but under-citing badly.
- All three look fluent; all three are wrong in places that matter.

Visual: three mini-callouts, one per agent, showing the exact malformed URL pattern next to a working one.

---

## Slide 12: Bottom cluster: structural failures

ii-researcher quits early, langchain-odr fabricates external URLs, storm under-cites.

- ii-researcher's chain-of-search loop terminates after ~3 turns.
- langchain-odr emits real-Wikipedia and real-Reddit URLs when its retrieval cache misses; not in the sandbox at all.
- storm's bibliography integration was buggy on our side until late, see next slide.
- Bottom cluster Elo CIs overlap; the rank order within is not meaningful.

Visual: bar of citation counts per agent, color-coded reachable vs not reachable.

---

## Slide 13: Finding 1: reach gate inverts the ranking

Drop the gate, and fluent fabricators climb to the top.

- `composite_v1` (no gate): gpt-researcher #1, camel-ai #3, ldr last (Elo 520).
- `composite_v2` (with gate): camel-ai #1, gpt-researcher #5.
- The gate is the single most consequential design choice in the benchmark.
- Punchline: a fluent fabricator is worse than a clunky truth-teller, because fluent fabrications are more likely to be believed.

Visual: two stacked rank tables side by side (v1 and v2), with arrows showing the rank changes per agent.

---

## Slide 14: Finding 2: bugs we caught and fixed

Four bugs found mid-run, fixed, and the runs re-scored.

- Kiwix URL alias bug: golden pool stored canonical form, agents emitted Kiwix-prefix variant. Patched canonicaliser; 64 historical pairs re-scored.
- storm bibliography bug: our runner read polished article but never merged `url_to_info.json` URL table. Fix moved storm from "always zero" to mid-tier.
- qx-agents pydantic + IndexError under DeepSeek: framework-side, accepted as broken-by-framework, filtered from Elo.
- GPU loss mid-run (5090 became unresponsive); migrated to DeepSeek API in parallel, no data loss.

Visual: a 4-row checklist with bug, root cause, fix, and downstream effect.

---

## Slide 15: Finding 3: what surprised us

The most-starred frameworks are mid-cluster; the cheapest pillars do most of the work.

- gpt-researcher and langchain-odr (large GitHub footprints) bottom out on truthfulness, not on prose.
- smolagents (generic, not DR-specialist) outperforms most DR-specialists.
- We dropped claim_nli from the headline composite (NLI-judge reliability concerns); reachability + quote-match alone already invert the ranking.
- Cheapest pillars (HTTP-probe and fuzzy quote match) carry the signal; expensive LLM-judge pillars confirm but don't change ranks.

Visual: scatter of Elo vs GitHub stars, with the diagonal "expectation line" annotated.

---

## Slide 16: What's next

Multi-LLM, more tasks, more frameworks, human baseline.

- Multi-LLM extension: same agents on GPT-5 / Claude / Gemini / Qwen. "Compare across LLMs" page is the entry point.
- More tasks: 100 designed, 57 scored. Expanding to 100 tightens Elo CIs from ~+/-80 to ~+/-60.
- More frameworks: open Contribute page, runner module + venv = on the leaderboard.
- Human baseline under the same sandbox constraints to anchor the agent-vs-human gap.

Visual: roadmap timeline with 4 milestones, each with a target completion quarter.

---

## Slide 17: Reproducibility and how to contribute

Deterministic scorer, frozen golden pool, single command to reproduce.

- `bash scripts/parallel_bulk_launch.sh 6` reproduces the full benchmark.
- Repo: `https://github.com/yibol9768-alt/deep-research-arena`.
- Live leaderboard: `http://172.30.52.43:8000/`. Method page: `/how-it-works`. Audit page: `/audit`.
- Add your framework: drop a runner in `scripts/runners/`, a venv on the eval host, open a PR.

Visual: QR code to the live leaderboard, GitHub URL, and a single-line install command displayed prominently.
