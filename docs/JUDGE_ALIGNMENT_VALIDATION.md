# Judge Alignment Validation (label-free)

How well does the Deep Research pairwise judge track human judgment?

**Honest framing.** We have NO local human preference labels and only a lite
judge model (`deepseek-v4-flash`; project policy forbids calling the pro tier).
We therefore validate the judge WITHOUT collecting human labels, using three
complementary label-free methods:

1. Synthetic-gold discrimination (primary): does the judge prefer a real report
   over a programmatically degraded copy of itself? Any human prefers the
   original, so this is an unambiguous human-agreement proxy.
2. Grounding correlation: does the judge's quality ranking move with the
   deterministic grounding signals already computed offline (must-cite recall,
   quote match)? A judge that rates ungrounded reports highly is broken.
3. Public judge-benchmark agreement (borrowed human labels): on LLMBar Natural,
   where the preferred output is human-labeled, does our judge pick the
   human-preferred answer?

All numbers below are REAL measured runs of the lite judge sourced from
`/root/.config/dra/judge.env` (`deepseek-v4-flash`, `n_samples=3`,
position-swap debiasing on). Reproduce with:

```bash
set -a; . /root/.config/dra/judge.env; set +a
python3 scripts/judge_meta_eval.py --run synth grounding llmbar --limit 8 --llmbar-pairs 60
```

Raw results: `data/judge_gold/meta_eval_results.json`.

---

## 1. Synthetic-gold perturbation accuracy (PRIMARY)

We took 8 strong real reports from `data/results/deep/` (claude-code and
camel-ai, the larger / better-grounded ones), clipped each to the
judge-visible window (the judge only ever reads the first ~5000 chars per
report; see note below), then built four degraded variants and asked the judge
to pick between original and degraded. The judge should prefer the ORIGINAL.

| Perturbation | What it does | Accuracy (orig preferred) | Ties |
|---|---|---|---|
| drop_citations | strips ~70% of markdown citations, leaving prose ungrounded | 0.750 (6/8) | 2 |
| inject_false_claims | inserts 2-3 unsupported / false claims near the top | 1.000 (8/8) | 0 |
| truncate | cuts to ~40% of the visible report, dropping later analysis | 1.000 (8/8) | 0 |
| shuffle_paragraphs | scrambles paragraph order, destroying logical flow | 0.875 (7/8) | 1 |
| **Overall** | | **0.906 (29/32)** | 3 |

Overall accuracy **0.906** clears the > 0.8 target. Crucially, the judge never
preferred a degraded variant: all 3 non-wins were TIEs, concentrated in the two
subtler perturbations (citation drop and paragraph shuffle, which leave the
factual content intact). This is exactly the failure mode a human would also
find borderline.

### Methodological note (important): the 5000-char judge window

The pairwise judge truncates each report to its first ~5000 chars
(`pairwise_judge._judge_once`: `(ans or '')[:5000]`). An initial run that
perturbed the FULL report scored only 0.281 overall, with truncate at 0.0 and
inject-false-claims at 0.125. Inspection showed these were not the judge
preferring worse reports; they were near-universal TIEs because the
perturbation landed BEYOND the 5000-char window (e.g. truncating a 72k-char
report to 40% still leaves the first 5000 chars byte-identical, so the judge
saw two identical inputs). The harness now clips each report to the
judge-visible window FIRST, then degrades within it, which is the fair test of
the judge as actually deployed. The 0.906 figure is from that corrected run;
the diagnostic appears in `data/judge_gold/meta_eval_synth_v2.json`.

This is itself a useful finding for the eval pipeline: any property that lives
only in the back half of a long report is invisible to the current pairwise
judge. Raising the per-report char budget (or using the existing
`smart_truncate` head+tail helper for pairwise inputs too) would let the judge
see conclusions and late-appearing claims.

> Update (2026-06-09): the recommendation above was implemented. The pairwise
> judge no longer uses the 5000-char head-only clip. `pairwise_judge` now reads
> `PAIRWISE_REPORT_CAP` (default 12000) and applies head+tail truncation, so
> conclusions and late claims are visible. The 0.906 / accuracy numbers in this
> section are from the older 5000-char head-only window and should be re-run
> under the 12000 head+tail cap before being cited as current. Section 1's table
> is therefore historical, not the deployed judge's current behavior.

## 2. Grounding correlation (offline, deterministic)

For the same 8 reports we computed a judge quality probe (round-robin pairwise
win-rate, 28 battles) and correlated it with the deterministic grounding
signals already stored in `data/results/deep_v3/*.score.json`.

| Signal | Spearman rho | p | n |
|---|---|---|---|
| composite grounding (mean of the two below) | 0.429 | 0.289 | 8 |
| must_cite_recall (url_coverage details) | **0.503** | 0.204 | 8 |
| quote_match score | 0.333 | 0.420 | 8 |

All correlations are POSITIVE: the judge ranks better-grounded reports higher,
which is the direction validity requires. With only n=8 these are not
statistically significant (p > 0.05), so this is supporting, not standalone,
evidence. The point estimate of rho approx 0.5 against must-cite recall is the
most informative; it should be re-run at larger n (use `--limit` higher) for a
significant figure.

---

## 3. Public judge-benchmark agreement (LLMBar Natural)

LLMBar (`github.com/princeton-nlp/LLMBar`) ships human-labeled preferred
outputs. We downloaded the Natural split (100 pairs; the direct GitHub raw URL
was reachable from this box, the `172.30.48.1:7890` proxy was not) and ran the
judge on the first 60 pairs.

| Metric | Value |
|---|---|
| Pairs judged | 60 |
| Agreement with human label (ties count as misses) | **0.817 (49/60)** |
| Ties emitted by judge | 7 |
| Decisive wrong (gold != judged, non-tie) | 4 |
| Decisive agreement (excluding ties) | 49/53 = **0.925** |

0.817 agreement (0.925 on decisive calls) is a strong result for a lite judge:
published LLM judges on LLMBar Natural typically land in the high 0.7s to low
0.9s, and Natural is the easier LLMBar split. This is the only one of the three
methods backed by actual human labels.

Cached copy: `data/judge_gold/llmbar_natural.json`. If the download ever fails
on another box, the script skips this method cleanly and prints a ready-to-run
command.

---

## Verdict: how human-aligned is the judge?

Evidence-backed answer: **well-aligned for the discriminations that matter.**

- It reliably prefers complete, grounded, well-ordered reports over degraded
  copies (0.906 synthetic-gold, no inversions, all misses are ties).
- Its quality ranking moves in the right direction with deterministic grounding
  signals (positive Spearman, rho approx 0.5 vs must-cite recall).
- On borrowed human labels (LLMBar Natural) it agrees with humans 0.817 of the
  time (0.925 on decisive calls).

Caveats, stated plainly:
- No LOCAL human labels were used; methods (1) and (2) are proxies, and (2) is
  under-powered at n=8.
- The judge only sees the first ~5000 chars of each report, so it cannot judge
  anything that lives only in a long report's tail. The synthetic-gold number
  is measured within that window; it does not certify judgment of full reports.
- LLMBar Natural is the easier split and is English general-QA, not deep
  cited research; agreement there transfers only partially to our domain.

### What a full human-kappa study would still add

This validation cannot replace a direct human study. A full study would:
- collect human pairwise preferences on actual deep-research reports (not
  synthetic perturbations and not borrowed general-QA), then report
  judge-vs-human Cohen's kappa / agreement on the SAME items;
- include human inter-annotator agreement as the ceiling, so we know how much of
  the residual disagreement is judge error vs genuine human disagreement;
- cover the hard, realistic cases (two strong reports differing on depth vs
  coverage), where synthetic-gold (strong vs obviously-degraded) is silent;
- be run on the full report (or with the expanded judge window) so alignment on
  conclusions and late-appearing claims is actually measured.

Until then, the three label-free numbers above are the defensible evidence that
the judge tracks human judgment.
