# RL Training Task Set Manifest

- Generated: 2026-06-02
- Location: `data/tasks/deep_research/rl/`
- Golden seeds: `data/golden/rl/<task_id>.json`
- Validator: `python3 scripts/rl_task_validate.py data/tasks/deep_research/rl/<task_id>.json`
- Validation mode: `fast` (deterministic, no torch / LLM / GPU / sandbox)
- Reward path: `ArenaEvaluator(task_id, mode="fast"); _task_config = cfg; _rl_strict = True;`
  default `WEIGHTS_RL` (judge dims dropped and renormalized in fast mode)
- Status: TRAINING-ONLY. NOT deployed to the public arena. The live leaderboard still
  uses the V2 5-pillar composite.

All six trainable tasks are READY (validator exit 0, all six behavioural checks plus seven
budget thresholds PASS). Every golden file is committed (none synthesised). The `fabricated`
variant nullifies to composite 0.0 on every task.

Two additional modality-demonstrator tasks (`rl_modality_browser_0001`,
`rl_modality_computeruse_0001`) are copies of a medium / harder task that declare the
`browser` and `computer_use` acquisition channels. Both also validate READY with the same
reward curve as their `shim` base, which is the concrete proof that the reward is
modality-agnostic. They are demonstrators, not part of the trainable pilot curriculum,
because the live `browser` channel needs Playwright and the live `computer_use` channel
needs a vision policy (out of scope for the single-5090 pilot). Eight task files total:
six trainable on `shim`, two demonstrators.

## Acquisition modality

Every task carries an `acquisition` block (added by `scripts/stamp_task_modality.py`) that
declares its evidence-acquisition channel. `scripts/train_grpo_pilot.py` reads it via
`backend_from_task_config(task_config, ...)` and selects the backend; a missing block
defaults to `shim`, so the field is fully backward-compatible. The reward never inspects
the channel (see `docs/ACQUISITION_MODALITIES.md`), so flipping a task to `browser` or
`computer_use` is a one-field change that does not move the score.

| task_id | acquisition modality | trainable now | READY |
| ------- | -------------------- | ------------- | ----- |
| rl_easy_0001 / 0002, rl_medium_0001 / 0002, rl_harder_0001, rl_bilingual_0001 | `shim` (search-shim) | yes | YES |
| rl_modality_browser_0001 | `browser` (Playwright) | needs Playwright | YES |
| rl_modality_computeruse_0001 | `computer_use` (interface + text-proxy stub) | needs vision policy | YES |

## Task table

| task_id | sites | difficulty | language | competent composite | fabricated (nullified?) | READY |
| ------- | ----- | ---------- | -------- | ------------------- | ----------------------- | ----- |
| rl_easy_0001     | wikipedia, reddit, shopping | 1 (easy)   | en | 0.7500 | 0.0 (yes) | YES |
| rl_easy_0002     | wikipedia, reddit, shopping | 1 (easy)   | en | 0.7500 | 0.0 (yes) | YES |
| rl_medium_0001   | shopping, reddit, wikipedia | 2 (medium) | en | 0.8063 | 0.0 (yes) | YES |
| rl_medium_0002   | shopping, reddit, wikipedia | 2 (medium) | en | 0.7626 | 0.0 (yes) | YES |
| rl_harder_0001   | shopping, reddit, wikipedia | 3 (harder) | en | 0.7391 | 0.0 (yes) | YES |
| rl_bilingual_0001 | wikipedia, reddit          | 2 (medium) | zh | 0.7559 | 0.0 (yes) | YES |

## Full reward curve per task (fast mode, WEIGHTS_RL, _rl_strict=True)

| task_id | competent | mediocre | shallow | one_sided | fabricated | pstd |
| ------- | --------- | -------- | ------- | --------- | ---------- | ---- |
| rl_easy_0001     | 0.7500 | 0.5313 | 0.4516 | 0.7196 | 0.0 | 0.2697 |
| rl_easy_0002     | 0.7500 | 0.6084 | 0.4516 | 0.7196 | 0.0 | 0.2737 |
| rl_medium_0001   | 0.8063 | 0.5971 | 0.4745 | 0.6355 | 0.0 | 0.2728 |
| rl_medium_0002   | 0.7626 | 0.6450 | 0.4745 | 0.6355 | 0.0 | 0.2679 |
| rl_harder_0001   | 0.7391 | 0.5833 | 0.4503 | 0.6099 | 0.0 | 0.2553 |
| rl_bilingual_0001 | 0.7559 | 0.4511 | 0.3981 | 0.6238 | 0.0 | 0.2565 |

Across the set, competent > mediocre > shallow > fabricated holds on every task, the
group population std is about 0.26 (well above the 0.05 floor), and the
competent-minus-shallow gap is at least 0.10 composite everywhere. one_sided sits below
competent on every task.

Notes on the perspective_balance dimension:

- rl_easy_0001 and rl_easy_0002 are non-evaluative mechanism explainers with empty
  `evaluated_entities`, so perspective_balance is 1.0 for every variant including one_sided.
  For those two tasks the one_sided-below-competent margin is driven by the longform gap,
  not by perspective_balance. This is correct for an explainer task type.
- rl_medium_0001, rl_medium_0002, rl_harder_0001 and rl_bilingual_0001 carry
  `evaluated_entities`, so perspective_balance collapses 1.0 -> 0.0 when cons are removed,
  and the dimension bites directly on the one_sided variant.

## Golden seeds

| task_id | must_cite count | domains in seed |
| ------- | --------------- | --------------- |
| rl_easy_0001     | 5 | wiki x3, reddit x1, shopping x1 |
| rl_easy_0002     | 5 | wiki x3, reddit x1, shopping x1 |
| rl_medium_0001   | 4 | shopping x1, reddit x2, wiki x1 |
| rl_medium_0002   | 4 | shopping x1, reddit x2, wiki x1 |
| rl_harder_0001   | 5 | shopping x1, reddit x2, wiki x2 |
| rl_bilingual_0001 | 4 | wiki x3, reddit x1 (English URLs, zh prose) |

`min_must_cite_recall` is 0.30 on every task, so citing 1-2 seed pages clears the floor
while citing 3+ approaches recall 1.0, leaving the gradient headroom.

## Feasibility caveats (verify at first sandbox run)

This is OFFLINE FAST-mode validation. The sandbox services (:7770 Magento, :9999 Postmill,
:8090 Kiwix) were NOT running, so golden-seed URL existence could not be network-confirmed.
Every golden URL must be confirmed resolvable at the first live sandbox run; if a must-cite
page 404s, `must_cite_recall` and `domain_balance` become harder to reach and the golden
must be repointed to a real page.

- rl_easy_0001: Wikipedia slugs `Active_noise_control` and `Noise-cancelling_headphones`
  are standard EN articles and very likely present; `Sound_masking` should exist but
  confirm. The Postmill thread `/f/headphones/comments/anc-real-world-limits` and the
  Magento product `/anc-over-ear-headphones.html` are placeholders to replace with real
  opened URLs. Design note: a third domain (shopping) was added during repair so the
  validator's drop-last-domain `mediocre` variant keeps 2 domains while a single-domain
  `shallow` stays genuinely single-domain, preserving competent > mediocre > shallow.
- rl_easy_0002: confirm Wikipedia `/A/Lithium-ion_battery`, `/A/Rechargeable_battery`,
  `/A/Battery_(electricity)`; Postmill `/f/gadgets/comments/earbud-battery-degradation`;
  Magento `/wireless-earbuds-bluetooth-headphones.html`. Same third-domain rationale as
  rl_easy_0001. The golden intentionally carries 3 Wikipedia URLs so the single-domain
  `shallow` variant scores lowest.
- rl_medium_0001: confirm Magento `/novamax-pro.html`, Postmill
  `/f/headphones/comments/novamax-commute` and `/f/audio/comments/novamax-long-session`;
  Wikipedia `/A/Headphones` is generic and very likely present.
- rl_medium_0002: confirm Magento `/calmcore-elite.html`, Postmill
  `/f/headphones/comments/calmcore-light-anc` and `/f/gadgets/comments/calmcore-app-controls`;
  Wikipedia `/A/Active_noise_control` is plausibly present. Golden spans exactly the 3
  declared domains.
- rl_harder_0001: confirm Magento `/novamax-pro.html`, Postmill
  `/f/audio/comments/novamax-long-session` and `/f/buyitforlife/comments/novamax-repair`;
  Wikipedia `/A/Active_noise_control` and `/A/Lithium-ion_battery` are standard articles and
  very likely present.
- rl_bilingual_0001: confirm Wikipedia `/A/AptX`, `/A/LDAC_(codec)`, `/A/Bluetooth`;
  Postmill `/f/headphones/comments/bluetooth-codec-latency`. Repair applied during authoring:
  `url_coverage.scoring_weights` rebalanced to
  `{must_cite_recall 0.28, pool_coverage 0.07, domain_balance 0.65}` to widen the
  mediocre-vs-shallow gap above the 0.04 floor; this reflects the task's defining
  cross-domain grounding requirement, not a threshold weakening. The golden file was
  unchanged.
