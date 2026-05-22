# Judge / Human Cohen kappa

_Generated: 2026-05-22T05:30:41.279948+00:00_
_Source: `data/results/deep_v3/leaderboard_deep.json (approx via pillar_elo)`  prefs=80_

| dim | n_filtered | kappa | interpretation |
|-----|-----------|-------|----------------|
| depth | 29 | 0.246 | fair |
| rigor | 17 | -0.272 | near-chance |
| style | 21 | 0.329 | fair |
| checklist | 13 | 0.133 | near-chance |

## Weakest judge

The lowest-kappa judge is **rigor** (kappa=-0.272).
Iterate the rubric for this dim next: tighten the criterion, add few-shot exemplars.

## Method note

For each pair `(A, B)` where the annotator cited dim D as a reason, we set the
judge's label to whichever agent had the higher per-dim score in the v3 leaderboard.
'Tie' human verdicts are dropped. Kappa is computed over the binary {A, B} contingency.
