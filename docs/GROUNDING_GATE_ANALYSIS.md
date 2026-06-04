# Grounding Gate: should it be re-weighted toward must-cite recall? (eval problem #9)

Date: 2026-06-03. Reproduce: `python3 scripts/analyze_grounding_gate.py`.

## Question

Eval problem #9 asked whether the grounding gate is "quote-fidelity-dominated"
and should be re-weighted toward curated must-cite recall, now that the goldens
are cleaned (off-topic must_cite removed; see EVAL_SET_REMEDIATION.md). The gate
composite is `w_r * curated_recall + (1 - w_r) * quote_match`, floor 0.30.

## Evidence (cleaned goldens + per-task source allow-list)

| agent | n | curated_recall | quote_match | cohort |
|---|--:|--:|--:|---|
| claude-code | 5 | 0.117 | 0.860 | honest |
| camel-ai | 12 | 0.118 | 0.776 | honest |
| smolagents | 12 | 0.250 | 0.583 | honest |
| gpt-researcher | 12 | 0.076 | 0.002 | fabricator |
| langchain-odr | 12 | 0.069 | 0.001 | fabricator |

Honest-vs-fabricator separation (min honest composite minus max fabricator
composite) as the recall weight rises:

| recall_w | separation | min honest | max fabricator | gate |
|--:|--:|--:|--:|---|
| 0.3 | +0.459 | 0.483 | 0.024 | holds |
| 0.5 | +0.377 | 0.416 | 0.039 | holds |
| 0.6 | +0.335 | 0.381 | 0.046 | holds |
| 0.7 | +0.261 | 0.315 | 0.054 | holds |
| 0.8 | +0.188 | 0.250 | 0.061 | AT RISK (min honest below floor) |

## Finding: the premise is not supported; do NOT re-weight toward recall

- `quote_match` is the discriminator the gate depends on: fabricators score ~0
  (they cannot quote pages they never fetched), honest agents score 0.58 to
  0.86. This is the project's validated truth-gate signal (reach/quote F approx
  80 versus writing-quality F approx 2.3).
- `curated_recall` barely separates the cohorts: honest 0.12 to 0.25 versus
  fabricator 0.07 to 0.08. claude-code (the strongest agent) has almost the same
  recall as a fabricator. Recall measures coverage of the curated top-K
  high-weight must-cite, which honest reports legitimately skip.
- Therefore weighting toward recall SHRINKS the gate margin (0.377 to 0.261 at
  recall_w=0.7) and breaks it at recall_w=0.8 (min honest 0.250 falls below the
  0.30 floor). It would let fabricators drift up and push honest agents down.

The gate is correctly fidelity-dominated. The actual recall-fairness concern
behind #9 (honest agents penalized against keyword-collision must_cite) was
fixed at the source by the golden cleaning (#1): cleaning RAISED honest agents'
recall (coffee task claude-code 0.17 to 0.25, camel-ai 0.17 to 0.33) because
they are now credited for citing genuinely relevant pages. We keep the additive
`0.5 * curated_recall + 0.5 * quote_match`: it preserves a clean +0.377 margin
and credits coverage without letting low recall sink an otherwise faithful
report.

## Caveats and follow-ups

- Local sample is small (5 to 12 reports per agent, tasks 0001 to 0012). The
  qualitative result (quote separates, recall does not) is robust, but the exact
  margins should be re-confirmed on the full 75-task box re-run (#11).
- `curated_recall@12` has low discrimination because the curated set is
  weight-sorted toward high-price products. A weight-agnostic or smaller-k
  curation could make recall a better secondary signal; that is a separate
  refinement to validate on the box, not a reason to up-weight recall now.
