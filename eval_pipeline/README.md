# Deep Research Arena evaluation pipeline snapshot

This directory is a curated snapshot of the evaluation work that was validated on `sivenfuuliu-any2` in August 2026. It is intentionally small: no frozen corpora, no run outputs, no secrets.

## What is included

- `scoring/`: package-aware scorer and deterministic projection.
  - Citation diagnostics: registry/fetched/snippet/context/out-of-snapshot.
  - Exact-quote deterministic scoring path (`exact_quote_packet`) for zero-judge scoring when frozen quotes are cited legally.
  - URL canonicalization including strict `/content/<book>/<page>` alias and backtick stripping.
  - `<think>` prefix stripping for judges that emit reasoning before JSON.
  - Hard judge budget (`withheld_scorer_budget`) so scoring cannot burn unbounded judge calls.
- `matrix/`: harness/matrix runner and preflight pieces used for shadow cells.
  - Harness preflight and model-route checks.
  - Citation-space closure validator.
  - Cell scoring wrapper that seals projection + score artifacts.
  - Runner patches for DeerFlow / OpenCode / Claude Code used in the shadow smoke.
- `docs/eval/`: human-facing delivery notes and the metrics report plan.

## Current proof

The minimal sealed first question completed with:

```text
Citation Binding = 1.0
GCP = 1.0
GRR = 1.0
judge calls = 0
judge tokens = 0
```

See `docs/eval/FIRST_EXACT_Q1_DELIVERY_20260826.md`.

## Important boundary

This snapshot is a reference implementation and proof of pipeline mechanics. It is not a formal benchmark release. Broad Q1-v2 shadow reports still need citation-space closure and a narrow paraphrase judge before they can produce comparable formal scores.

## Quick checks

```bash
cd eval_pipeline/scoring
python3 -m unittest -v test_auto_score_biodiv_q1.py test_prepare_matrix_cell.py

cd ../matrix
python3 -m unittest discover -s tests -p 'test_*.py'
```

Some matrix scripts contain absolute deployment paths from the validation host. Treat them as sealed evidence of the run protocol; adapt paths before reuse.
