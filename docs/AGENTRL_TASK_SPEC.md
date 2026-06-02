# AgentRL-Suitable Task Spec

- Generated: 2026-06-02
- Scope: the RL training task set under `data/tasks/deep_research/rl/`
- Reward path: `ArenaEvaluator.evaluate_rollout` -> `composite_v3_rl` with `WEIGHTS_RL`
- Mode used for authoring and validation: `fast` (deterministic, no torch, no LLM, no GPU)
- This is a TRAINING-ONLY task set. It is NOT deployed to the public arena. The live
  leaderboard still scores against the V2 5-pillar composite.

This document specifies what makes a Deep Research Arena task usable as an AgentRL
(GRPO) training environment, the numeric budget every threshold must fit, how the RL
reward elicits a graded reward curve, how to validate a candidate task, and why the
existing 124 arena tasks cannot be used for RL.

## 1. Why the arena 124 tasks are unsuitable for RL

The arena tasks (`data/tasks/deep_research/cross_site_deep*/`) are graded for a frontier
agent with a large tool budget. A representative arena task sets:

| floor                          | arena value |
| ------------------------------ | ----------- |
| markdown_spec.min_words        | 3500-8000   |
| markdown_spec.min_paragraphs   | 25          |
| markdown_spec.min_citations    | 60          |
| markdown_spec.min_pages_browsed | 120        |
| url_coverage.min_unique_urls_browsed | 100   |
| url_coverage.min_unique_urls_cited   | 60    |
| url_coverage.min_must_cite_recall    | 0.45  |

The RL policy is a Qwen3-4B rollout with a hard budget of max 8 tool calls,
ctx 6144, max_new_tokens about 600. A tool call is one ResearchEnv action
(search / open / read / cite / finalize). A competent episode realistically issues
about 3 distinct searches, opens and reads 3-4 distinct pages (each open and each read
is a separate call, so reading 3-4 pages already consumes about 6-8 of the 8 calls), and
emits one finalize of about 300-500 words.

That episode physically cannot produce 3500+ words, 60+ citations, 120 browsed pages, or
100 unique browsed URLs. Every plausible rollout therefore fails every hard floor.
When every member of a GRPO group fails the floors, the reward collapses to a constant
(near zero) for all of them. A constant reward means zero reward variance inside the
group, which means the GRPO advantage (reward minus group mean) is zero for every sample,
which means no learning gradient. The model gets no signal about which of its attempts was
better. This is the floored-reward / zero-variance failure mode, and it is structural: it
holds for any 4B policy under this budget regardless of how the policy is initialized.

The fix is not to lower a few numbers on the arena tasks. The arena tasks exist to pull
apart the TOP of a frontier leaderboard, and their floors are load-bearing for that goal.
The fix is a SEPARATE, budget-feasible task set whose floors all sit at or below what an
8-call episode produces, so that a competent rollout clears the floors with headroom while
a shallow or fabricated rollout does not. That separation, not the absolute score, is the
training signal.

## 2. The RL reward and how it produces a graded curve

In the RL path the evaluator is built exactly as the trainer builds it:

```
ev = ArenaEvaluator(task_id, mode="fast")
ev._task_config = <task config dict>
ev._rl_strict   = True            # weights default to WEIGHTS_RL
result = ev.evaluate_rollout(rollout)
composite = result.composite      # composite_v3_rl
```

`WEIGHTS_RL` carries ten dimensions, but in `fast` mode the four judge dimensions
(checklist .16, depth .12, rigor .09, style .06) are set to a neutral 0.5 and then DROPPED
and renormalized, because there is no LLM judge offline. What remains is the deterministic
spine, renormalized to sum to 1:

| dimension          | raw weight | verifier |
| ------------------ | ---------- | -------- |
| coverage           | .18 | `src/verifiers/url_coverage_verifier.py` |
| source_diversity   | .10 | `src/verifiers/source_diversity_verifier.py` |
| longform_quality   | .10 | `src/verifiers/longform_quality_verifier.py` |
| perspective_balance | .08 | `src/verifiers/perspective_balance_verifier.py` |
| spec               | .06 | `src/verifiers/markdown_report_verifier.py` |
| bilingual          | .05 | `src/verifiers/bilingual_quality_verifier.py` |

The fast composite is `reach_soft * Q` over that renormalized spine, where `Q` is the
weighted quality and `reach_soft` is the soft-floor reach term.

### Grounding gate (`_rl_strict = True`)

The grounding gate removes the perverse incentive to fabricate citations:

- A no-fetch rollout earns `s_ground = 0`. There is no text-only proxy reward.
- A rollout that cites URLs it never fetched (`n_cited > 0` but `n_resolved == 0`)
  nullifies to `composite = 0.0` exactly.

So a task only rewards prose whose citations point at pages the policy actually fetched.
This requires the cited URLs to be sandbox-local (so `extract_citations` counts them) and
the golden must-cite pages to be real, fetchable sandbox pages.

### What moves each dimension on budget content

- coverage = weighted (must_cite_recall .55 + pool_coverage .15 + domain_balance .30).
  Continuous. must_cite_recall rises as the rollout cites more of the small golden seed;
  domain_balance rises as citations spread across the declared sandbox domains.
- source_diversity = domain entropy and top1 share across cited URLs. Needs at least two
  host:port domains; a single-domain report scores 0 here.
- longform_quality = length_fit + section_structure + citation_density, a blend of four
  continuous subscores. Padding alone does not score high.
- perspective_balance = deterministic tier_a rate, the fraction of evaluated entities that
  carry BOTH a positive and a concrete negative near the entity. A one-sided report (no
  con) collapses this dimension to 0; a balanced report scores 1.
- spec = mean of 5 boolean floors (word count, paragraphs, citations, pages_browsed,
  in-domain citations). Five-step graded, near-saturated, must not be the only mover.
- bilingual = 0.50 language_match + 0.25 terminology + 0.25 deterministic_fluency. Only
  carries signal when the task language is zh. For en tasks it saturates near 1.0.

The evaluator injects `task_config['pages_browsed'] = rollout.pages_browsed =
len(fetched_urls)`, so `markdown_spec.min_pages_browsed` is gated against the number of
distinct pages the episode actually read.

## 3. Numeric criteria (budget-tied)

Every HARD floor must be reachable inside the 8-tool-call budget. Feasible ranges:

| field | easy / bilingual | medium | harder |
| ----- | ---------------- | ------ | ------ |
| markdown_spec.min_words | 280-320 | 380-420 | 430-470 |
| markdown_spec.min_paragraphs | 3 | 4 | 4 |
| markdown_spec.min_citations | 3 | 4 | 4-5 |
| markdown_spec.min_pages_browsed | 3 | 4 | 4 (never > 5) |
| url_coverage.min_unique_urls_browsed | 3 | 4 | 4 |
| url_coverage.min_unique_urls_cited | 3 | 4 | 4 |
| url_coverage.min_must_cite_recall | <= 0.34 | <= 0.34 | <= 0.34 |
| url_coverage.min_expected_pool_coverage | 0.0 | 0.0 | 0.0 |
| url_coverage.min_domain_balance | <= 0.6 | <= 0.6 | <= 0.6 |
| citation_policy.per_domain_minimum sum | 2-3 | 3 | 3 |
| search.target_distinct_queries | 3 | 3-4 | 4 |

`min_pages_browsed` must be at or below the number of distinct reads an 8-call episode can
do (4 to 5). `min_must_cite_recall <= 0.34` means citing 1-2 of a 3-5 entry golden seed
already clears the floor, leaving recall headroom for the gradient.

### The seven authored criteria

1. budget_feasible_thresholds: every hard floor at or below 8-call episode output.
2. reward_headroom_competent_above_floor: a competent budget-fitting rollout scores well
   above the no-op / shallow floor. Target competent FAST composite 0.60-0.80, shallow /
   one-sided / single-domain 0.45-0.65, no-fetch / fabricated 0.0. Competent-minus-shallow
   gap at least 0.10 composite.
3. gradient_variance_for_grpo: within a GRPO group the reward std must be greater than 0;
   good > mediocre > shallow > fabricated must be real and graded. Per-dim, coverage must
   span about 0.2-1.0 across rollouts and perspective_balance must be 0 for a one-sided
   report and 1 for a balanced one. No single dim may saturate to a constant.
4. no_perverse_incentive_grounding_gate: with `_rl_strict = True`, no-fetch scores
   `s_ground = 0` and cite-without-fetch nullifies to 0.0 exactly. Citations restricted to
   the three sandbox aliases. No reward path gives credit for prose without fetch.
5. genuinely_agentic_multi_page: solving requires search -> open -> read multiple distinct
   pages -> cite -> synthesize. Enforced jointly by min_pages_browsed >= 3, at least two
   distinct domains in `per_domain_minimum`, and source_diversity needing >= 2 balanced
   domains. `search.target_distinct_queries` seeds the process bonus.
6. graded_not_binary: no dimension is a single pass/fail switch that flips the whole reward.
   coverage, longform_quality, and source_diversity are continuous blends; perspective_balance
   is the tier_a rate over evaluated entities; spec is a 5-step mean. Avoid tasks where only
   spec moves.
7. golden_light_seed: golden is a SMALL must-cite seed (3-6 high-confidence canonical
   sandbox pages, weights all 1.0) so partial recall is the norm and full recall is reachable
   in <= 4 cited pages. `expected_pool_urls` equals the seed; pool coverage is not gated.
   Golden lives at `data/golden/rl/<task_id>.json`. Every seed URL must be a real fetchable
   sandbox page (confirm at first sandbox run).

### Curriculum spread

The set spans an easy-to-harder gradient so RL sees a learnable curriculum. Difficulty
comes from agentic load (more distinct pages and domains, pros-and-cons, contradiction
reconciliation), NOT from raising unreachable quality floors.

- 2 EASY (difficulty 1): 280-320 words, 3 cites, 3 pages, 2-3 domains.
- 2 MEDIUM (difficulty 2): 380-420 words, 4 cites, 4 pages, 3 domains, pros AND cons.
- 1 HARDER (difficulty 3): 430-470 words, 4-5 cites, 4 pages, 3 domains, reconcile
  contradictory sources.
- 1 BILINGUAL (difficulty 2): zh output over English sources, about 400 CJK chars, 3 cites,
  3 pages, 2 domains.

### Bilingual coverage

At least one task sets `language = "zh"` so the bilingual dim (weight .05) carries real
signal. The Wikipedia/Kiwix grounding corpus is English-only, so the zh task keeps ENGLISH
sandbox citations (the URLs are English) but a CHINESE prose body. Target about 400 CJK
chars (>= `BILINGUAL_MIN_CJK_CHARS = 80` and well above the 30-CJK-word degenerate floor),
cjk_ratio of visible prose >= 0.20, and Chinese punctuation (。，；) to avoid the
zh-without-zh-punct fluency penalty. For en tasks `language = "en"` makes bilingual
saturate near 1.0, which is low signal and is fine.

## 4. How to validate a task

The offline validator loads a task JSON exactly as `scripts/train_grpo_pilot.py` loads it,
drives the same RL reward path (`ArenaEvaluator(..., mode="fast")`, `_task_config = cfg`,
`_rl_strict = True`, default `WEIGHTS_RL`), parametrically synthesizes five graded rollouts
tailored to that task's golden seed, domains, checklist keywords and `markdown_spec`, scores
each through `evaluate_rollout`, and emits a PASS/FAIL readiness verdict. No sandbox, GPU,
network or LLM is needed.

Command:

```
python3 scripts/rl_task_validate.py data/tasks/deep_research/rl/<task_id>.json
python3 scripts/rl_task_validate.py data/tasks/deep_research/rl/<task_id>.json --json
```

Exit 0 means READY (all checks pass), exit 1 means not ready.

The five synthetic variants are `competent`, `mediocre`, `shallow`, `one_sided`,
`fabricated`. The six readiness checks are:

- headroom: competent composite >= 0.45.
- gradient: competent > mediocre > shallow, each gap >= 0.04.
- balance_bites: one_sided composite < competent.
- no_perverse: fabricated == 0.0 (nullified) AND shallow > 0.0.
- variance: population std of the 5 composites > 0.05.
- feasible: every numeric threshold fits the 8-tool-call budget (pages <= 6,
  citations <= 6, words <= 900, recall <= 0.5, per-domain mins sum <= 6).

Authoring note: the validator's `mediocre` variant drops the last declared domain. With
only two declared domains, `mediocre` collapses to a single domain while a single-domain
`shallow` can accidentally restore both, inverting the required competent > mediocre >
shallow order. Declaring three sandbox domains (and splitting `citation_policy.per_domain_minimum`
from `url_coverage.per_domain_minimum` where needed) keeps the gradient clean. This is a
genuine scope expansion that makes the task MORE agentic, not a threshold weakening.

## 5. Reference reward curve

The proven offline harness `scripts/tier0_probe.py` builds graded variants
(A_excellent .. G_padded_thin) and prints the FAST curve used as the design target:

```
A_excellent 0.96 > B_good 0.77 > F_one_sided 0.64 > C_shallow 0.60
            > E_single_domain 0.59 > G_padded_thin 0.46 > D_fabricated 0.00 (nullified)
```

The RL tasks reproduce that shape on budget content: competent about 0.74-0.81,
one_sided about 0.61-0.72, mediocre about 0.45-0.65, shallow about 0.40-0.47, fabricated
0.0. See `data/tasks/deep_research/rl/MANIFEST.md` for the per-task numbers.
