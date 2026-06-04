# Eval Factsheet: Deep Research Arena scoring methodology

A concise, honest record of how a Deep Research report is scored, what has been
validated, what has NOT, and how to reproduce the inputs exactly. Companion to
`docs/DATASHEET.md` (the dataset) and `data/results/benchmark_manifest.json`
(the reproducibility fingerprint).

Principle, in one line: **two orthogonal numbers and one gate.** Report GROUNDING
and QUALITY separately, never a single weighted composite (which is gameable),
and use grounding as a truth-gate on quality. This mirrors the field consensus
(DeepResearch Bench RACE/FACT, ALCE/FActScore/SAFE/RAGAS for grounding,
Arena-Hard / AlpacaEval-LC / MT-Bench for pairwise quality).

---

## 1. The grounding gate (deterministic)

Implemented in `src/scoring/simple_score.py` (`grounding_score` + `gate_and_rank`).

```
citation_precision = supported_cited_pairs / total_cited_pairs
must_cite_recall   = curated_golden_must_cite_hits / total_curated_must_cite
grounding          = F1(citation_precision, must_cite_recall)
```

- A `(url, claim)` pair is **supported** only if the URL passes **proof-of-fetch**
  (it was actually retrieved by the agent; a cited-but-never-fetched URL is a
  fabrication) AND its claim is supported by the retrieved snippet. The default
  support check is deterministic token overlap; an NLI entailment checker can be
  injected via `support_fn`.
- Recall counts hits against the **curated golden must-cite set**
  (`data/golden/deep_clean/`) only. There is deliberately **no domain-balance
  term and no raw-count term**, so the score cannot be inflated by citing more
  URLs. Adding unsupported citations lowers precision; adding non-golden
  citations does not raise recall.

### The truth gate

```
final_quality = 0.0   if fabricated (a cited URL was never fetched)
final_quality = 0.0   if grounding_f1 < floor   (default floor = 0.15)
final_quality = QUALITY (passed through unchanged) otherwise
```

The gate (`gate_and_rank`) is the only place the two numbers interact. GROUNDING
and QUALITY are otherwise reported as two separate columns, like RACE/FACT. The
gate is what zeroes out fluent-but-fabricated reports.

---

## 2. The quality judge

### GLM-5.1 cross-family pairwise

QUALITY is a **length-controlled pairwise Bradley-Terry Elo**:

- **Pairwise**, not absolute 1-10 scoring (more discriminative, less scale drift).
  Implemented in `src/scoring/pairwise_judge.py` (`battle`).
- **Position-swap debiasing**: each pair is judged in both orders (A,B) and
  (B,A); the verdicts are un-swapped and combined, and disagreement collapses to
  a tie.
- **Majority over `n_samples` rounds** (default 3).
- **Length discounting**: the system prompt explicitly tells the judge to
  discount verbosity, so a tight correct answer beats a long rambling one. This
  is the AlpacaEval-LC / Arena-Hard style-control idea, applied here as an
  instruction rather than a post-hoc regression.
- **Cross-family judge**: the published leaderboard uses **GLM-5.1 on
  Bailian/DashScope** (OpenAI-compatible) as the judge while the agents under
  test are a different family (Qwen). Cross-family judging mitigates the
  self-preference bias (Wataoka 2024; JudgeBench ICLR 2025). The judge model is
  resolved from `PAIRWISE_JUDGE_MODEL` / `JUDGE_MODEL` / `CHECKLIST_JUDGE_MODEL`
  and stamped into each score file via `judge_identity()`; the manifest records
  it under `judge_model`.

The per-pair verdicts are aggregated into per-agent ratings with Bradley-Terry /
Elo plus bootstrap confidence intervals (`src/scoring/bradley_terry.py`,
`src/scoring/arena.py`).

### Dimension-aware variant

`battle(dimension=...)` reframes the judge to compare ONE dimension only
(`depth`, `rigor`, `style`, `checklist`), matching how human annotators labeled
pairs (pick a winner, cite a dimension). These dimensions are diagnostic; they
are not re-weighted back into a single composite.

### The judge prompts are hashed

The exact judge prompts (`_SYSTEM` and `_DIMENSION_FOCUS` in
`src/scoring/pairwise_judge.py`) are content-hashed into the manifest's
`judge_prompt_hash`, so a prompt edit is detectable and a published number is
tied to the prompt that produced it.

---

## 3. What is validated (and what is NOT)

The judge alignment evidence so far was measured with the **lite DeepSeek**
judge (`deepseek-v4-flash`; project policy forbids the pro tier). Full detail and
reproduction commands are in `docs/JUDGE_ALIGNMENT_VALIDATION.md`; raw results in
`data/judge_gold/meta_eval_results.json`.

### Validated (label-free)

- **Synthetic-gold perturbation discrimination: 0.906** (29/32). The judge is
  shown a real report vs. a programmatically degraded copy of itself (dropped
  citations, injected false claims, truncation, shuffled paragraphs) and must
  pick the original, which any human would. It never preferred a degraded
  variant; all 3 misses were ties on the subtle perturbations. Measured within
  the judge-visible window after the window fix.
- **LLMBar Natural (borrowed human labels): 0.817** agreement (49/60), **0.925**
  on decisive (non-tie) calls. This is the only number backed by actual human
  labels; LLMBar ships human-preferred outputs and the judge picks the
  human-preferred answer 49 times out of 53 decisive calls.
- **Grounding-signal correlation: Spearman rho approx 0.5** vs. must-cite recall
  (positive, i.e. the judge ranks better-grounded reports higher). Under-powered
  at n=8 (not statistically significant); supporting, not standalone, evidence.

### NOT validated (stated plainly)

- **No human Cohen's kappa yet.** There are NO local human preference labels on
  actual deep-research reports. Methods (1) and (3) are proxies; a full study
  would collect human pairwise preferences on real reports, report
  judge-vs-human kappa, and include human inter-annotator agreement as the
  ceiling. See `docs/JUDGE_ALIGNMENT_VALIDATION.md` "What a full human-kappa
  study would still add."
- **The GLM-5.1 judge inherits NONE of these numbers.** Every alignment figure
  above was measured with `deepseek-v4-flash`. The published leaderboard uses
  `glm-5.1`, which has zero alignment evidence of its own. Before trusting a
  GLM-judged board, re-run `scripts/judge_meta_eval.py --run synth grounding
  llmbar` with `JUDGE_MODEL=glm-5.1` and confirm GLM clears the same bars.
  Treat the DeepSeek numbers as DeepSeek-only.
- **Same-family history.** The existing corpus on disk was generated by a
  DeepSeek backbone AND judged by DeepSeek (same family, a self-preference risk).
  The cross-family GLM-vs-Qwen setup is the intended design for the published
  run, not what every legacy score file reflects.
- **Cross-family routing is configuration-dependent.** The cross-family judge
  helper exists but is not auto-invoked by `battle`; fairness depends on running
  the queue single-family (all Qwen agents, GLM judge), not on code enforcement.
  If families are mixed later, route GLM-family agents to a non-GLM judge.
- **Judge window.** The judge sees a bounded per-report window
  (`PAIRWISE_REPORT_CAP`, default 12000 chars, with head+conclusion smart
  truncation). Anything living only in a long report's deep middle is not judged.

---

## 4. Reproducibility via the manifest hashes

`scripts/benchmark_manifest.py` writes `data/results/benchmark_manifest.json`,
the single fingerprint that pins a leaderboard number to its inputs:

| Field | What it pins |
| --- | --- |
| `task_set_hash` | sha256 over the 100 canonical `dr_cross_deep_NNNN.json` task specs + `checklists_deep.json` |
| `golden_hash` | sha256 over the canonical golden in `data/golden/deep/` + `data/golden/deep_clean/` |
| `judge_prompt_hash` | sha256 over the live `_SYSTEM` + `_DIMENSION_FOCUS` judge prompts |
| `judge_model` | the resolved pairwise judge model (canonical: `glm-5.1`; default `deepseek-v4-flash` when no judge env is exported) |
| `grounding_formula` | the F1-precision-recall + truth-gate formula, as a string |
| `n_tasks` / `n_golden` | 100 / 100 at snapshot |

Each hash is sha256 over the **sorted** list of `(repo-relative-path, raw-bytes)`,
length-prefixed so the byte stream is unambiguous. Sorting makes the digest
independent of filesystem order; hashing raw bytes (not re-serialized JSON) means
any change, including whitespace, is detected. Only canonical files are hashed;
backups / variants (`*.bak`, `*.cleaned.json`, `*.quotes*.json`, `._*`) are
excluded because the scorer does not consume them.

Regenerate and compare:

```bash
python3 scripts/benchmark_manifest.py
# diff task_set_hash / golden_hash / judge_prompt_hash against a published manifest
```

The judge model is configured via the OpenAI-compatible DashScope endpoint; the
key lives outside the repo in `/root/.config/dra/bailian.env`
(`DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`) and is never committed or printed.
To stamp `glm-5.1` into the manifest, export `PAIRWISE_JUDGE_MODEL=glm-5.1` (and
the DashScope `JUDGE_*` env) before regenerating; otherwise the manifest honestly
records the `deepseek-v4-flash` default.

Determinism caveat: only the `generated_at` timestamp changes between runs; the
hashes are stable for identical inputs. The grounding pillar is fully
deterministic. The pairwise QUALITY judge is non-deterministic (LLM sampling),
which is why position-swap, multi-sample majority, and a stamped `judge_identity`
are used, and why QUALITY is always reported with bootstrap CIs rather than as a
single point number.
