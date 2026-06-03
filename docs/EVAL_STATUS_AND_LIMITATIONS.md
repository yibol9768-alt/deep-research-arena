# Eval status, what is validated, and known limitations (2026-06-02)

This records the trustworthy state of the Deep Research eval after the
scoring redesign + forensic audit + fixes, so the eval's validity scope is
explicit and honest.

## What is DONE and validated

- **Scoring redesigned** to the field-consensus shape: two orthogonal numbers
  (GROUNDING = citation precision with proof-of-fetch x curated must-cite
  recall; QUALITY = length-controlled pairwise Bradley-Terry Elo, DeepSeek-lite
  cross-family judge, position-swap) + a truth-gate. Deployed live.
- **Judge human-alignment validated without human labels** (lite DeepSeek):
  synthetic-gold perturbation discrimination **0.906** (re-confirmed on FULL
  reports after the window fix), LLMBar borrowed-human-label agreement **0.817**
  (0.925 decisive), grounding-signal correlation rho ~0.5. See
  `docs/JUDGE_ALIGNMENT_VALIDATION.md`.
- **Eval-validity bugs fixed** (committed): pairwise judge window 5000 -> 12000
  with head+conclusion truncation; curated top-12 must-cite (the old 121-URL
  whole-crawl gold was structurally unreachable); invalid-run exclusion (capture
  stubs no longer scored as real low scores); Kiwix `/wiki/` canonicalization in
  proof-of-fetch; forum search now requires genuine topical overlap.
- **Full offline test suite GREEN: 332 passed, 6 skipped** (the 6 are live
  sandbox / live DB / optional mcp gates).
- **Per-framework and per-report forensic critiques**: `docs/FRAMEWORK_WEAKNESS_
  ANALYSIS.md`, `docs/FRAMEWORK_ROOT_CAUSE.md`, `docs/PER_REPORT_CRITIQUE.md`.

## Framework testing: what is and is not trustworthy

| framework | runs | status |
| --- | --- | --- |
| claude-code | 5 tasks | trustworthy, grounded, ranked #1 |
| camel-ai | 57 tasks | trustworthy, grounded, ranked #2 |
| smolagents | 31 tasks | trustworthy but BIMODAL (best-grounded on 0005, fabricated on 0001, empty 0004); borderline-gated 0.29 |
| gpt-researcher | 32 tasks | trustworthy run, but the agent fabricates URLs -> gated (correct) |
| langchain-odr | 31 tasks | same as gpt-researcher: fabricates -> gated |
| flowsearcher-ds | 48 tasks | partial (about a third of runs are capture failures) |
| storm | 31 tasks (historical stubs) | RESOLVED on re-run: produces a REAL grounded report (task 0002: 13,978 chars, 31 real Magento URLs with accurate prices). History was missing-venv + a since-resolved LLM-balance issue, NOT a broken agent. |
| qx-agents | 30 tasks (historical stubs) | RE-RUN: installs + starts but cannot complete with deepseek-v4-flash (KnowledgeGapOutput structured-output schema mismatch, no retry -> abort). Lite-model-incompatible, not an infra bug. |
| ii-researcher | 30 tasks (historical stubs) | RESOLVED on re-run: produces a REAL grounded report (task 0002: 29,617 chars, 18 real sandbox URLs). History was missing-venv, NOT a broken agent. |
| ldr | 30 tasks | runs, but produces tiny shallow reports |
| deerflow | 30 tasks | runs, fluent but under-cited + cites off-sandbox URLs |

"Tested completely" is bounded by three real blockers, all documented:
1. **Runner/capture bugs** (qx-agents OS venv path, storm article-gen, ii crash):
   code fixed where the active path was wrong; full re-validation needs a re-run.
2. **my5090 box is a stripped tarball with no framework venvs**, so only
   flowsearcher-ds can be re-run there without reinstalling per-framework venvs.
3. **Corpus-task mismatch** (below).

## Known limitation: corpus-task mismatch (tasks 0002-0005)

The Postmill forum corpus is tech-only (`technology, headphones, LifeProTips,
personalfinance, gaming, videogames, news, science, askreddit`). Tasks 0002
(coffee), 0003 (fitness), 0004 (photography), 0005 (gardening) have NO matching
forum content. Consequences:
- Agents' generic search terms lexically match headphones/tech threads, so
  off-topic forum posts get cited in (e.g.) a coffee report.
- The golden for those tasks, built by crawling the same forum, is itself
  contaminated with off-topic forum URLs.

**Decision taken (researcher call, option 3 short-term):**
- The forum search now requires genuine topical overlap (no zero-overlap
  injection), reducing off-topic forum citations for future runs.
- Curated must-cite (top-K by weight) for coffee/fitness/etc. tasks targets the
  PRODUCTS that actually exist in the corpus, not the absent forum threads, so
  grounding recall no longer demands non-existent forum content.
- Net: task 0001 (headphones, fully corpus-covered) is the most trustworthy
  grounded comparison. Tasks 0002-0005 are valid for the shopping+wiki sources
  but their forum dimension is unreliable.

**Mid-term fix (sandbox-gated, needs my5090):** seed coffee/fitness/photography/
gardening forum content into Postmill (option 1), then re-crawl golden and re-run
agents. This is the path to making 0002-0005 fully valid.

## Re-run resolution (2026-06-02, my5090 sandbox)

The box's real working repo is **`/opt/deep_reserch`** (all framework sources under
`third_party/` + prebuilt per-framework venvs `.venv-storm`/`.venv-qx`/`.venv-ii`),
NOT the stripped `/root/deep_reserch` tarball. Running from `/opt` with the
sandbox + shim + ds_proxy up: STORM and ii-researcher both produce REAL,
sandbox-grounded reports on task 0002 (pulled to `data/results/deep/*__rerun0602.md`).
So their historical "runner-broken" status was an environment artifact, now
resolved. qx-agents alone genuinely cannot complete with the lite DeepSeek
backbone (structured-output incompatibility). Their curated must-cite recall is
low (storm 0.00, ii 0.083) like every other framework, i.e. they cite real
products but not the specific curated key set; full grounding (quote_match) needs
a box-side re-score. A multi-task re-run on `/opt` would let them join the ranked
leaderboard properly.

## What full completion still requires (all sandbox-gated)

1. Seed matching forum corpus for 0002-0005, re-crawl golden, re-run agents.
2. Reinstall per-framework venvs on the box and re-run storm/qx-agents/
   ii-researcher (after their runner fixes) on a stable sandbox.
3. Re-base the leaderboard on the re-run, corpus-aligned data.
4. (Optional) a small real human-preference set to certify alignment on
   strong-vs-strong full-report pairs beyond the LLM-only proxies.

Everything offline-doable for trustworthy scoring + validated alignment is DONE
and deployed; the remaining items are infrastructure runs on the my5090 sandbox.
