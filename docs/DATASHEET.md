# Datasheet: Deep Research Arena cross-site benchmark

Datasheets-for-Datasets style record (Gebru et al. 2021) for the deep-tier
cross-site research benchmark: the task set under
`data/tasks/deep_research/cross_site_deep/` and the golden references under
`data/golden/deep/` (and the curated subset `data/golden/deep_clean/`).

Reproducibility fingerprint for everything described here lives in
`data/results/benchmark_manifest.json` (regenerate with
`python3 scripts/benchmark_manifest.py`). The scoring methodology that consumes
this dataset is documented in `docs/EVAL_FACTSHEET.md`.

Snapshot at time of writing: 100 task specs, 100 golden references in
`data/golden/deep/`, 49 curated references in `data/golden/deep_clean/`.

---

## Motivation

- **Why does the dataset exist?** To evaluate "deep research" agents (multi-step
  web-research systems that read many sources and write a long, cited report) on
  a frozen, fully reproducible corpus instead of the open web. The open web
  makes results irreproducible (link rot, paywalls, captchas, ranking drift) and
  makes "did the agent fabricate this?" unanswerable. A closed sandbox lets us
  ask a hard, checkable question: did every cited URL actually exist and actually
  get fetched, and does it support the claim attached to it?
- **What gap does it fill?** Existing closed sandboxes (WebArena and its kin)
  test short transactional tasks ("add this item to the cart"). This dataset
  raises the bar to long-horizon, cross-source synthesis: each task forces the
  agent to combine a shopping catalog, a community forum, and an encyclopedia,
  then reconcile contradictions between them. The unit of evaluation is a full
  report, not a single action.
- **Who created it and for whom?** Built by the Deep Research Arena project for
  its own leaderboard and for RL training-environment work. Intended audience:
  researchers comparing deep-research agents and anyone who wants a grounded,
  fabrication-detecting eval rather than an open-web vibe check.

---

## Composition

### The 3 closed sandbox sources

Every task draws from exactly three WebArena-derived, version-pinned, fully
offline services. No external API is contacted during a task run.

| Source | Service | Role in a task | Typical URL pattern | Approx. scale |
| --- | --- | --- | --- | --- |
| `shopping` | Magento "One Stop Market" | Product landscape: prices, ratings, review counts, marketing feature-claims | `http://localhost:7770/<slug>.html` | ~2,000 product pages |
| `reddit` | Postmill (reddit clone) | Community sentiment: forum threads, scores, comment counts, top-voted takes | `http://localhost:9999/f/<forum>/<id>/<slug>` | tens of subforums x many threads |
| `wikipedia` | Kiwix `wikipedia_en_all_nopic` | Technical grounding: definitions/explanations of the feature-claims | `http://localhost:8090/content/wikipedia_en_all_nopic/A/<title>` | full English Wikipedia (millions of articles) |

The deep tier requires all three sources in a single report; the cross-source
synthesis section is where the difficulty lives (find product claims that lack
or contradict Wikipedia backing, rank brands by forum sentiment, etc.).

**Which sources actually earn a grounding score (be honest, not "three-source
scoring").** The task spans all three corpora, but the decidable axes credit
them asymmetrically: `fact` support is **shopping only**, `completeness` scores
the **shopping + Wikipedia** ranked vital pool plus **one virtual forum slot**
for tasks that declare community sources, and `reach` / proof-of-fetch are
source-agnostic. The forum is therefore a **provenance dimension** (citations
classify as searched / linked / guessed and a single virtual completeness slot
can be covered by a quoted, task-relevant allowed-forum thread), **not** a
source of decidable vital nuggets: the answer keys carry **zero forum vital
nuggets** today. Building real forum vital nuggets — decidable predicates such
as `thread_score` and `comment_count` on top-voted threads — is a scheduled
**v2.1 dataset task**; until it ships, treat the forum dimension as provenance
and virtual-slot coverage, and do not read the truth number as crediting three
sources equally.

### What each instance is

- **Task spec** (`data/tasks/.../dr_cross_deep_NNNN.json`): a JSON object with
  `schema_version`, `task_id`, `sites` (the 3 sources), `difficulty`,
  `expected_steps`, a long natural-language `intent`, `markdown_spec`,
  `citation_policy`, `url_coverage` / `url_reachability` requirements, an
  embedded `golden` stub, `synthesis_requirements`, a `coverage_checklist_path`
  pointer, and `domain` / `intent_type` tags.
- **Coverage checklists** (`checklists_deep.json`): per-task binary verifier
  questions (a coverage rubric), referenced by tasks via
  `coverage_checklist_path`. It is a single shared file, not one-per-task.
- **Golden reference** (`data/golden/deep/dr_cross_deep_NNNN.json`): the curated
  ground truth for grounding scoring. Keys: `task_id`, `generated_at`,
  `must_cite_urls` (the facts a strong report should cite), `expected_pool_urls`
  (the broader reachable pool, ~700-800 URLs), `triples` (subject-relation-object
  facts), and `metadata`. The ranked `triples` become the per-task **vital
  pool** that the `completeness` axis scores against. Each pool holds ~14-17
  vital nuggets, all below the `K*=20` saturation cap, so the axis is in
  practice a **census**: covering every vital fact a task offers is what scores
  `completeness = 1.0`, and the marginal value of one nugget floats per task at
  `1/|pool|` (1/14 to 1/17). `K*` is retained only as an upper cap on the
  denominator and does not bind at current pool sizes.
- **Curated golden** (`data/golden/deep_clean/`): a cleaned, smaller-must-cite
  subset (49 of the 100 tasks at snapshot). The original whole-crawl
  `must_cite_urls` (often ~120 URLs/task) was structurally unreachable as a
  recall target; the curated set narrows must-cite to a top-K of high-weight
  facts that actually exist in the corpus, so recall is achievable.

### Counts and labels

- 100 task specs; tagged across domains (Consumer, Finance, Law, Travel,
  Education, Entertainment, Science, and a large untagged remainder).
- 100 golden references in `data/golden/deep/`; 49 in `data/golden/deep_clean/`.
- No human preference labels are included. Golden facts are
  programmatically crawled then hand-reviewed; they are NOT human-written
  reference reports.

### Relationships, splits, noise

- There is no train/test split shipped here; the corpus is an evaluation set.
- Tasks 0002-0005 are known to be partially noisy on their forum dimension (see
  the coverage limitation below). Golden files for those tasks inherit that
  noise because the golden was crawled from the same forum.
- `data/golden/deep/` also contains derivation artifacts (`*.bak`,
  `*.cleaned.json`, `*.quotes*.json`, `*.uncleaned.*`, macOS `._*` forks). These
  are NOT eval inputs and are deliberately excluded from the manifest hash.

---

## Collection process

- **Acquisition.** Golden references are generated on the sandbox by
  `scripts/build_deep_golden.py` from a per-topic config
  (`configs/deep_topics/T.yaml`) declaring shopping keywords, reddit forums, and
  mandatory/extra Wikipedia articles. The builder crawls the three frozen
  services and records the URLs, metadata, and triples that a strong report
  should cover. This is direct observation of the sandbox, not a sample of human
  judgments.
- **Who/what collected it.** Automated crawler over the pinned containers, then
  human review of each task's `metadata.summary` against acceptance thresholds
  (n_must_cite, per-domain minimums, `partial` flag false).
- **Timeframe / drift.** The sandbox state is frozen and version-pinned (see
  `HANDOFF.md`); a given golden file is a snapshot of that frozen state. There is
  no live-web drift because no external service is contacted.

---

## Preprocessing / cleaning / labeling

- **Curation pass.** The raw whole-crawl `must_cite_urls` were too large and
  partly unreachable to serve as a recall target. `data/golden/deep_clean/`
  holds a curated top-K must-cite per task (high-weight facts present in the
  corpus). Recall in the grounding score is computed against this curated set,
  not the full crawl.
- **Forum topical filter.** Forum search was changed to require genuine topical
  overlap (no zero-overlap injection), reducing off-topic forum citations for
  future runs.
- **URL canonicalization.** Cited URLs and golden URLs are canonicalized through
  one shared function (`src/verifiers/citation_format.canonicalize_url`,
  including Kiwix `/wiki/` handling) so proof-of-fetch and must-cite matching
  agree with the rest of the citation stack.
- **Raw vs. processed.** Raw crawl variants (`*.uncleaned.bak`, `*.bak`,
  `*.quotes*.json`) are retained on disk for provenance but are not consumed by
  the scorer and are excluded from the manifest hash.

---

## Coverage limitation: the Postmill forum is tech-only

The Postmill forum corpus is **technology-only**. Its subforums are
approximately `technology, headphones, LifeProTips, personalfinance, gaming,
videogames, news, science, askreddit`. There is no broad-topic forum content.

Consequences, stated plainly:

- Tasks whose topic is NOT tech (task 0002 coffee, 0003 fitness, 0004
  photography, 0005 gardening) have **no matching forum threads**. An agent's
  generic search terms then lexically match tech/headphones threads, so
  off-topic forum posts can get cited in, say, a coffee report.
- The golden for those tasks, built by crawling the same forum, is itself
  contaminated with off-topic forum URLs.
- **Task 0001 (consumer-grade audio headphones) is fully corpus-covered and is
  the most trustworthy grounded comparison.** Tasks 0002-0005 are valid for the
  shopping + Wikipedia sources but their forum dimension is unreliable.

The mitigation (require genuine topical overlap; curate must-cite toward
products that actually exist rather than absent forum threads) reduces but does
not eliminate this. The full fix (seed matching forum content, re-crawl golden,
re-run agents) is sandbox-gated and not yet done.

---

## Recommended uses

- **Good fit.** Benchmarking deep-research agents on grounded, cross-source
  synthesis with fabrication detection; comparing agents under the
  two-numbers-plus-gate scoring in `docs/EVAL_FACTSHEET.md`; as an RL training
  environment with a non-binary grounding reward.
- **Use task 0001 first** when you want the cleanest grounded comparison; treat
  the forum dimension of 0002-0005 as provisional.

### Caveat: corpus-task mismatch

Do NOT read a low grounding score on tasks 0002-0005 as "the agent failed to
ground its forum claims." For those tasks the required forum content does not
exist in the corpus, so the forum sub-score conflates agent behavior with a
dataset gap. Restrict forum-dimension conclusions to task 0001 (and any future
tasks whose topic the forum actually covers) until the matching forum corpus is
seeded.

### Other limitations to keep in mind

- **Sandbox vs. open web.** Results are reproducible precisely because the
  corpus is closed; they do not directly measure open-web research skills (link
  rot, captcha, ranking, selection bias).
- **Golden pool incompleteness.** The expected pool (~700-800 URLs/task) is a
  subset of the ~20,000 reachable sandbox pages. A cited URL outside the pool is
  checked for reachability (HTTP 200) rather than auto-counted as fabrication.
- **Domain skew.** The topic mix is consumer-goods / technology heavy; broad
  domain diversity (biomedical, legal, policy) is limited.
- **No human reference reports.** Golden is crawled facts plus must-cite URLs,
  not human-written gold reports, and there are no shipped human preference
  labels.
- **Citation-locality binds writing style, not just facts (a deliberate cost).**
  Fact recall and completeness credit a claim only when its citation sits in the
  *same sentence* (structured facts) or on the *same Markdown line* (vital
  nuggets) as the claim. This is the strongest defence against "citation
  dumping" (stating many claims, then listing sources at the end to launder
  coverage), and the oracle report shows the requirement is achievable. But it
  is a real cost paid by an argumentative writing style that states two or three
  sentences and then gives one citation at the paragraph end: such a report is
  systematically marked down on fact recall / completeness even when every claim
  is true and sourced. The maintainer kept the sentence/line binding (ruling #4)
  because paragraph-level windows reopen the laundering loophole; the stylistic
  penalty is disclosed here rather than removed. Read a low fact-recall or
  completeness score together with the report's citation *placement*, not only
  its factual content.

---

## Distribution and maintenance

- Distributed inside the repository under `data/tasks/` and `data/golden/`,
  version-controlled. Sandbox containers are pinned separately (see
  `HANDOFF.md`).
- Growth protocol (add a topic config, build golden on the sandbox, hand-review
  thresholds, write the task + checklist) is documented in
  `DATASET_METHODOLOGY.md` section 9.
- Integrity: regenerate `data/results/benchmark_manifest.json` with
  `python3 scripts/benchmark_manifest.py` and diff the `task_set_hash` /
  `golden_hash` against a published manifest to confirm byte-identical inputs.
