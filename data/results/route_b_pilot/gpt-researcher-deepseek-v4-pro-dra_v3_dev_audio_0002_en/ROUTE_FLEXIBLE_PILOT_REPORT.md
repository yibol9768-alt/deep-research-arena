# Route-flexible rubric pilot: `dra_v3_dev_audio_0002`

## Status

This is a development-only, single-task pilot. It must not enter the formal leaderboard.
The semantic judgments in this run were manually adjudicated after the configured model
services failed (DeepSeek V4 Pro returned an upstream 502; GPT-5.6 Luna returned 402).
The deterministic citation, registry, observation-ledger, route, dependency, and score
replay remained automatic.

## Question under test

Can the benchmark reward a report that satisfies the research requirements through valid
alternative evidence, without requiring it to reproduce the evidence graph's original
source IDs or its original product conclusion?

## Rubric change

The evidence graph is treated as a **witness graph**, not a unique answer route.

- Runtime evidence acceptance is based on claim support, source role, URL registry status,
  this-run observation, and local citation binding. `known_witnesses` are audit aids only.
- Obligations accept an OR of valid routes, where each route is an AND of necessary targets.
- The Hi-Res branch closes when both audited listings make no such claim; LDAC research is
  not mandatory in that branch.
- The forum branch accepts a replayable, bounded negative search. It does not require two
  preselected forum pages and does not license a corpus-wide absence claim.
- The final recommendation is open-ended. It must be consistent with evidence and user
  constraints; the rubric does not whitelist Soundcore or Ortizan.
- Content completion, evidence-grounded completion, full pass, and URL integrity are
  reported separately.

## Result

| Measure | Result |
|---|---:|
| Legacy fixed-route partial completion | 0/15 (0.0%) |
| Route-flexible report-content completion | 5/9 (55.6%) |
| Route-flexible grounded-obligation completion | 1/9 (11.1%) |
| Full pass | 0 |
| Cited URLs | 1 |
| Fabricated URLs | 0 |
| Cited but unobserved URLs | 0 |

The new result does not turn a weak report into a pass. It recovers the useful distinction
that the legacy score lost: the report discussed five required research dimensions, but
only the Ortizan listing audit formed a complete, locally cited, observed, page-supported
evidence chain.

## Obligation audit

| Obligation | Content | Grounded | Main reason |
|---|:---:|:---:|---|
| Flare 2 listing audit | Fail | Fail | Calls 20 W continuous and omits the missing THD+N test condition. |
| Ortizan listing audit | Pass | Pass | The cited, observed product page supports the bounded listing audit. |
| Watt/distortion synthesis | Fail | Fail | Infers cleaner high-volume performance from an underspecified THD+N claim. |
| 360-degree/passive-radiator audit | Pass | Fail | Analysis is bounded, but the Flare evidence has no valid local citation. |
| IPX7 scope | Pass | Fail | The conceptual boundary is discussed, but required evidence is not fully cited. |
| Battery caveats | Pass | Fail | Both caveats are discussed; the Flare claim is not locally supported by a cited page. |
| Hi-Res audit | Pass | Fail | Correctly takes the no-claim branch, but the Flare negative finding is uncited. |
| Forum/same-model validation scope | Fail | Fail | Says no such content exists in the sandbox; the trace only supports a bounded search-result claim. |
| Recommendation | Fail | Fail | The recommendation is explicit, but its decisive THD rationale is unsupported and depends on failed obligations. |

## Interpretation

Two failures are now distinguishable:

1. **Rubric-route failure in the legacy scorer.** A semantically relevant report received
   zero because the scorer required the reference graph's exact route.
2. **Report grounding and reasoning failure.** The route-flexible scorer still rejects the
   report because most useful claims lack locally bound evidence, and several conclusions
   overstate what the captured pages establish.

The irrelevant pages returned by search affect research efficiency and the strength of a
negative-search certificate; they are not themselves counted as fabricated citations or
automatic task failure. This keeps retrieval/API quality separate from report truthfulness.

## What this pilot establishes

- An alternative registered and observed source can satisfy a target even when it is not a
  `known_witness`.
- A valid alternative branch can pass when the graph's first branch fails.
- Correct discussion without citation contributes to content completion but not grounded
  completion.
- URL fabrication remains an independently visible diagnostic instead of erasing all
  partial information.

## Remaining release gate

Before applying this design to all 56 tasks, the same report should be judged by at least
two independent model/human adjudicators, and adversarial fixtures should verify source
substitution, citation misbinding, unsupported inference, conditional branch closure, and
open-ended recommendation consistency. The current manual judgment artifact is deliberately
stamped `formal_eligible: false`.
