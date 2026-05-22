# Human Pairwise Preference Protocol (Workstream D)

Goal: regress the composite_v3 dimension weights from human pairwise
preferences and validate that the resulting composite tracks human
judgement. Target: `Spearman(composite_v3, human winner-rate) >= 0.85`.

## Sampling strategy

- Population: the top-5 agents on `data/results/deep_v3/leaderboard_deep.json`
  ranked by `elo_v2_ci.elo` (currently claude-code, opencode, camel-ai,
  tongyi-dr, storm).
- 30 tasks drawn from the front of `data/results/deep_v3/leaderboard_deep.json["tasks"]`
  (deterministic; first 30 task ids in publication order).
- All `C(5, 2) = 10` agent pairs x 30 tasks = 300 pairs, shuffled with seed=17.
- One pair = one annotation. Average annotator time ~ 2 minutes per pair => ~10 hours
  per annotator to clear the queue. Two annotators in parallel halves wall-clock.

## What "depth", "rigor", "style", "checklist", "coverage", "spec" mean here

The annotator picks up to many of these chips when explaining their preference.
Their meaning, kept deliberately short for in-pane reference:

- **depth** -- does the report dig into the *why* of each claim, follow up with
  comparisons, surface causal chains? Or does it stop at a list of facts?
- **rigor** -- are quotes faithful to the cited URL? Are numbers consistent
  between sections? Does it admit uncertainty rather than fabricating?
- **style** -- is the prose readable, sectioned, free of LLM tics
  ("As an AI...", repeated boilerplate, run-on bullets)?
- **checklist** -- does it cover the items the task pre-registration calls out
  (brand list, divergence section, top-N list, etc.)?
- **coverage** -- breadth of distinct sources and URL diversity. Did it look
  beyond the first three Google-equivalent hits?
- **spec** -- does the report meet the markdown contract: word count,
  citation count, paragraph count, valid markdown links?

The chip set is multi-select; "other" is reserved for reasons that don't
fit the six dims (e.g. one report is truncated, one report is in the wrong
language).

## Running the collector locally

```
# Build / rebuild the pair queue (auto-runs on first launch):
python tools/human_pref_collector/server.py --rebuild-queue --port 8000

# Then open http://localhost:8000/ in any browser.
# Preferences land in data/human_prefs/prefs.jsonl one row at a time.
# Progress survives restarts via tools/human_pref_collector/.cursor
```

Keyboard shortcuts in the UI: `a` = Prefer A, `s` = Tie, `d` = Prefer B,
`Enter` = submit and load next pair.

## Fitting the weights

Once N >= 200 prefs (rule of thumb: ~30 prefs per dim is the minimum to
identify a 6-dim Bradley-Terry-logit fit at this noise level):

```
python scripts/fit_weights_v3.py
```

The script:

1. Reads `data/human_prefs/*.jsonl`.
2. Reads per-agent per-dim scores from `data/results/deep_v3/leaderboard_deep_v3.json`
   (falls back to `leaderboard_deep.json` with synthesised dims if v3 file
   isn't shipped yet -- logs a warning when it does).
3. Fits `P(A wins) = sigmoid(sum_d w_d (s_d^A - s_d^B))` via softmax
   reparameterisation + L-BFGS-B with 8 random restarts. Constraints
   `w_d >= 0` and `sum_d w_d = 1` hold by construction.
4. 5-fold CV reports mean held-out log-likelihood vs the uniform baseline.
5. **Refuses to write** `weights_v3.json` if CV log-lik is worse than uniform.

`--dry-run` uses a synthetic prefs/scores fixture with known ground-truth
weights `[0.10, 0.30, 0.25, 0.05, 0.20, 0.10]` and asserts the recovered
weights fall within 0.10 of ground truth per dim.

## Validation gates

Before publishing new weights:

1. CV held-out log-lik > uniform baseline. Hard gate -- script refuses to
   write the file otherwise. Override with `--force` only if the parent
   agent has audited the alternative.
2. Spearman(composite_v3, human winner-rate) >= 0.75 on the full prefs set.
   Computed by `scripts/compute_human_alignment.py`; result lands in
   `docs/HUMAN_ALIGNMENT_REPORT.md`.
3. Stretch target: Spearman >= 0.85. Above this the composite is treated
   as headline-trustworthy.
4. Cohen's kappa per judge-dim, computed by
   `scripts/compute_judge_human_kappa.py`. Any dim with kappa < 0.40 and
   n_filtered >= 10 is flagged as a rubric to iterate.

## Outputs (canonical paths)

| file | producer |
|------|----------|
| `data/human_prefs/prefs.jsonl` | the collector |
| `data/results/deep_v3/weights_v3.json` | `scripts/fit_weights_v3.py` |
| `docs/HUMAN_ALIGNMENT_REPORT.md` | `scripts/compute_human_alignment.py` |
| `docs/JUDGE_HUMAN_KAPPA.md` | `scripts/compute_judge_human_kappa.py` |
