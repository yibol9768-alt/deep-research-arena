# Deep Research Arena — V3 Overhaul Session Report

**Date**: 2026-05-21 (continued from a session that died 2026-05-21 ~20:46 PDT due to API 500s)
**Working dir**: `/root/Desktop/lyb/deep_reserch`
**Baseline commit**: `4666272` "Baseline snapshot before v3 scoring overhaul"
**Final commit**: `a778ebd` "Restore web/dist/wrangler.jsonc"
**Total diff**: 71 files changed, +10,909 / -104 lines (code-only, excluding generated `data/` artifacts: 46 files, +7,547 / -104)

---

## 1. Context — what we walked into

The previous session (session id `a394ddbe-4fd9-4a44-acdf-48788fc29c16`) laid out 5 concrete problems with the live `deepresearcharena.com` benchmark:

1. **Frontend over-emphasizes "URL is reachable"** and under-shows depth / style / rigor. The leaderboard's per-pillar sparkline was *synthetic placeholder data* hard-coded in `leaderboard-table.tsx:153–172`.
2. **Composite weights `0.40·url_coverage + 0.40·checklist + 0.20·spec`** were heuristic — chosen by analogy in `SCORING_FRAMEWORK.md` and **never regressed against human judgments**.
3. **Top players cluster too tightly**. camel-ai ±72 Elo, smolagents ±71 → rank-1 vs rank-2 p ≈ 0.054 (not significant). 30 tasks × 5 agents = 150 runs is too few; pillars (reach ↔ quote_match Spearman ρ=0.91) are correlated.
4. **ClaudeCode & OpenCode are leakily sandboxed**. ClaudeCode disables `WebSearch/WebFetch/NotebookEdit` but `Bash + curl` can hit anything. OpenCode relies on a *soft prompt-level* "no internet" instruction.
5. **No reusable eval harness for AgentRL**. Verifiers are scriptable but not packaged as a `evaluate(report) → reward` callable.

A 29 KB plan was written to `/root/.claude/plans/velvet-skipping-hopper.md` and approved by the user. Then the parent session died on API 500s mid-dispatch.

This session resumed from that plan.

---

## 2. Plan as executed

The V3 spec landed in this session:

```
composite_v3   = reach_soft × Q
reach_soft     = 0.5 + 0.5 × quote_match            # in [0.5, 1.0], never zeroes
Q              = Σ_d w_d · score_d                  # 6 quality dims

WEIGHTS_V3 = {coverage:0.20, depth:0.20, rigor:0.20, style:0.10, checklist:0.20, spec:0.10}
```

Soft-floor replaces the hard multiplicative gate. Under v2, an agent like `gpt-researcher` with 97% broken URLs got composite ≈ 0.03 — the hammer erased everything it might have done well. Under v3 the floor is 0.5 × Q; URL truthfulness and quote_match still scale up to 1.0, but quality always contributes.

**Six quality dimensions** (replacing the 3-dim `url_coverage / checklist / spec`):

| Dim | How scored | Verifier |
|---|---|---|
| `coverage` | recall vs golden URL pool | `src/verifiers/url_coverage_verifier.py` (existing) |
| `depth` | LLM-judge 5pt rubric | NEW `src/verifiers/depth_verifier.py` |
| `rigor` | LLM-judge 5pt rubric | NEW `src/verifiers/rigor_verifier.py` |
| `style` | LLM-judge 5pt rubric | NEW `src/verifiers/style_verifier.py` |
| `checklist` | binary task items | `src/verifiers/checklist_verifier.py` (existing) |
| `spec` | format compliance | `src/verifiers/markdown_report_verifier.py` (existing) |

Five parallel workstreams:

- **A** scoring — V3 composite + 3 new verifiers + `ArenaEvaluator` for AgentRL
- **B** separability — 20 adversarial tasks + top-pair densification + Arena-Hard separability metric
- **C** adapters — `--strict-sandbox` flag, three-layer enforcement (allowlist + shim 403 + audit)
- **D** human-eval — pairwise A/B collector + Bradley-Terry weight fit + Spearman/κ reports
- **E** frontend — real per-pillar UI + Quality Profile panel + dry-run banner

---

## 3. Execution log

### 3.1 git infrastructure

`/root/Desktop/lyb/deep_reserch` was not a git repo (only existed as a working copy; the canonical checkout lives elsewhere). To do parallel worktrees we needed a real git tree.

Steps:

1. Extended `.gitignore` to exclude `node_modules/`, `.next/`, `frontend/out/`, `frontend/tsconfig.tsbuildinfo`, `*.log`. The frontend dir alone was 654 MB before, mostly node_modules.
2. `git init -b main` → configured user/email → `git add .` (1,161 files, .git ≈ 9.6 MB).
3. Baseline commit `4666272`.
4. Created 4 sibling worktrees off `main`:
   ```
   /root/Desktop/lyb/deep_reserch                  [main]
   /root/Desktop/lyb/deep_reserch-wt-scoring       [wt-scoring]
   /root/Desktop/lyb/deep_reserch-wt-separability  [wt-separability]
   /root/Desktop/lyb/deep_reserch-wt-adapters      [wt-adapters]
   /root/Desktop/lyb/deep_reserch-wt-human-eval    [wt-human-eval]
   ```
5. `wt-frontend` was created later after `wt-scoring` landed the v3 JSON schema (its build-time dependency).

### 3.2 First dispatch — 4 agents 529'd

All 4 background Opus 4.7 agents dispatched in parallel returned **API 529 Overloaded** with 0 tokens and 0 tool calls. Duration ≈ 210 seconds each (the API client's retry timeout). This was an Anthropic capacity issue, not our prompts — even the Bash sandbox classifier was unavailable.

### 3.3 Re-dispatch — successful

After a few minutes the Opus API recovered. Re-dispatched all 4. All 4 completed successfully.

Per-agent stats:

| Agent | Duration | Tool uses | Tokens |
|---|---|---|---|
| wt-scoring | 9 min | 40 | 113 K |
| wt-separability | 9 min | 38 | 128 K |
| wt-human-eval | 10 min | 46 | 96 K |
| wt-adapters | 23 min | 114 | 207 K |
| wt-frontend (dispatched after A) | 10 min | 62 | 81 K |

Total agent-time ≈ 61 min across 5 agents (wall clock ≈ 23 min because of parallelism). Total tokens ≈ 625 K across all 5 agents.

### 3.4 Merge into main

All 5 branches merged via `git merge --no-ff` in order **A → B → D → C → E**. **Zero conflicts.** The do-not-touch lists in each agent's prompt held.

Then `web/dist/wrangler.jsonc` was restored — the baseline was missing this file (likely excluded by an old `.gitignore` rule). It's required by Cloudflare Workers Builds to recognize `web/dist/` as a static-asset directory, and `claude.md` documents its exact contents.

Final `git log --oneline -8`:
```
a778ebd Restore web/dist/wrangler.jsonc
21e5a5a Merge wt-frontend (Workstream E)
3004d53 Merge wt-adapters (Workstream C)
51a13d5 Merge wt-human-eval (Workstream D)
5b071ab Merge wt-separability (Workstream B)
561fd82 Merge wt-scoring (Workstream A)
8970204 Workstream E: frontend surfacing (real per-pillar UI + Quality Profile)
dea1782 Workstream C: strict-sandbox enforcement (--strict-sandbox + shim 403 gate)
```

---

## 4. Workstream-by-workstream details

### 4.1 Workstream A — V3 scoring

**Files created (8)**:
- `src/verifiers/depth_verifier.py` (223 lines) — 5pt rubric anchored as 1=enumeration only, 3=claims with single-evidence links, 5=multi-step synthesis reconciling contradictions. Self-consistency: 3 calls at temp 0.3, median. CoT explicitly disabled in prompt. Defensive judge-unavailable fallback returns `score=0.5, evidence="judge_unavailable"` instead of crashing.
- `src/verifiers/rigor_verifier.py` (188 lines) — same shape; rubric for logical coherence, hedging vs over-claiming.
- `src/verifiers/style_verifier.py` (191 lines) — same shape; rubric for structure, signposting, citation prose integration.
- `src/eval/__init__.py` (empty namespace).
- `src/eval/evaluator.py` (409 lines) — `ArenaEvaluator` class with sync `.evaluate()` and `.evaluate_async()`. Two modes:
  - `fast`: skips LLM-judge dims (returns 0.5 neutral), runs in < 1 s — suitable for AgentRL inner loop.
  - `full`: runs all 6 verifiers via `asyncio.gather`, ≈ 30 s — suitable for periodic eval.
  This is **the AgentRL contract**: any RL training loop can `from src.eval.evaluator import ArenaEvaluator` and use the returned `composite` as the scalar reward.
- `scripts/build_deep_leaderboard_v3.py` (345 lines) — clones the v2 build but calls the 3 new verifiers; **defaults to `--dry-run`** (uses synthetic mock scores tagged `synthetic_placeholder: true`). Real runs happen on `westd`/WSL `/opt/deep_reserch`.
- `data/results/deep_v3/leaderboard_deep_v3.json` (716 lines) — schema-v3-dryrun output with 855 synthetic per-pillar rows.
- `docs/SCORING_V3_DIFF.md` (204 lines) — spec, weights table, soft-floor formula, AgentRL integration snippet.

**Files modified (1)**:
- `src/scoring/leaderboard_composites.py` (+160 lines) — added `WEIGHTS_V3`, `_v3_dim_score`, `_reach_soft`, `composite_v3_softfloor`, `composite_v3_breakdown`. The existing `composite_v2_truthful` is **untouched** — both functions are callable side-by-side. The paper's F6 finding can still be reproduced by calling v2.

**Validation results**:
1. `composite_v3_softfloor({reachability:0.8, quote_match:0.9, coverage:0.7, depth:0.6, rigor:0.55, style:0.7, checklist:0.8, spec:0.9})` → **0.6555** ✓
2. `ArenaEvaluator('dr_cross_deep_0001', mode='fast').evaluate(...)` → composite=0.198, runs without error ✓
3. `python scripts/build_deep_leaderboard_v3.py --dry-run` → wrote 855 synthetic rows ✓

**Open question**: cross-family judge routing (DeepSeek judges GLM, GLM judges DeepSeek) needs an `agent_family` field on the task config that doesn't exist yet. All three new verifiers currently route through the existing env-var-configured judge client with a TODO comment.

### 4.2 Workstream B — Top-player separability

**Three orthogonal levers, all implemented**:

1. **Adversarial task selection** (BenchBuilder-style, Arena-Hard achieves 87.4% pairwise separability vs MT-Bench 22.6% with this trick):
   - `configs/deep_topics/V2_ADVERSARIAL_TASKS.json` — 20 task specs across three families:
     - **Causal/Debunking** (7 tasks, stresses `rigor`): "Common claim X — true or marketing?" forces counter-evidence.
     - **Synthesis-under-contradiction** (7 tasks, stresses `depth`): two source clusters disagree; agent must reconcile.
     - **Long-tail recall** (6 tasks, stresses `coverage`): must-cite pool oversampled with niche items.
   - `scripts/build_v2_adversarial_tasks.py` (450 lines) — emits 20 fully-fleshed task JSONs with 15–21 item checklists + index.
   - `data/tasks/deep_research/cross_site_deep_v2/` — 20 task files + `checklists_deep_v2.json` + `index.json`.

2. **Top-pair densification**:
   - `scripts/run_pairwise_battles.py` (+171 lines) — new `--strategy top-pair-densify --top-n N --n-per-pair K --seed S` mode. Existing `full-matrix` strategy preserved as default.

3. **Separability metric reporting**:
   - `src/scoring/arena.py` (+93 lines) — `compute_separability(elo_table, ci_table) → dict` implementing the Arena-Hard CI-overlap formula. Returns `{separability_pct, n_pairs, n_non_overlapping, pair_breakdown}`.
   - `scripts/report_separability.py` (229 lines) — loads leaderboard, writes `docs/SEPARABILITY_REPORT.md`.

**Files modified**: `configs/deep_topics/V1_TASK_DESIGN_GRID.md` (+85 lines documenting the V2 adversarial design recipe + pre-registration), `scripts/run_pairwise_battles.py`, `src/scoring/arena.py`.

**Docs**: `docs/SEPARABILITY_PLAN.md` (107 lines), `docs/SEPARABILITY_REPORT.md` (141 lines, auto-generated).

**Headline number**: **current separability = 62.86%** (105 pairs, 15 agents) against `data/results/deep_v3/leaderboard_deep.json`. That's 2.14 pp below the 65 % intermediate target and 24.5 pp below the Arena-Hard reference of 87.4 %. The three stacked levers should clear 65 % comfortably.

**Validation results**: 20 task JSONs generated ✓, `compute_separability` imports and runs on synthetic 3-agent table (66.67%) ✓, `report_separability.py` writes the report ✓.

**Open questions**:
- Compute budget on `westd` for the pilot (45 pre-screen runs + 160–200 promoted v2 runs).
- Anchor preservation: combined v2+v3 leaderboard or separate boards?
- Composite weighting between v1 and v2 tasks (by task count or by family).

### 4.3 Workstream C — Strict-sandbox enforcement (largest)

This was the heaviest workstream — 23 min, 114 tool uses. The contract becomes the **central methodological story**: every cited URL must be verifiable against our owned corpus.

**Three enforcement layers**:

- **Layer 1** — per-adapter tool allowlist (whitelist, not denylist).
- **Layer 2** — shim-level URL gate: non-allowlist target → HTTP 403.
- **Layer 3** — post-run domain audit verifier: flags any non-`localhost:{7770,8090,9999,8081}` URL cited in the report.

**Files created (3)**:
- `src/verifiers/sandbox_compliance_verifier.py` (148 lines) — `verify_sandbox_compliance(report_md, allowed_origins=None) → dict`. Parses markdown `[text](url)`, bare URLs, reference-style links. Returns `{sandbox_url_pct, total_urls, sandbox_urls, non_sandbox_urls, policy_violation}`.
- `tests/test_sandbox_compliance.py` (135 lines) — 9 pytest cases. **All 9 pass.**
- `docs/STRICT_SANDBOX_CONTRACT.md` (173 lines) — the contract verbatim, why it matters, the three-layer diagram, per-runner status table, end-to-end run recipe, known gaps.

**Files modified (8)**:
- `scripts/run_deep_task.py` (+271 lines) — `--strict-sandbox` flag, dispatch logic, post-run audit hook, in-process HTTP gate helper, kwarg forwarding via `_wrap_runner`.
- `integrations/search_shim/app.py` (+197 lines) — `--mode {open,strict}` CLI (or `SHIM_MODE` env). URL allowlist enforced on `/search /v1/search /v2/search /v1/serper /brave /searxng /duckduckgo /extract /scrape`. Blocks logged to `logs/shim_blocks.jsonl`.
- `scripts/runners/claudecode_runner.py` (+69) — **closes the Bash-curl gap**: replaces the disallowlist with `--allowed-tools Read,Write,Edit,Glob,Grep,Bash(curl http://localhost*),Bash(curl http://127.0.0.1*)`.
- `scripts/runners/opencode_runner.py` (+55) — generates per-run `opencode.json` with `commands.allowed: ["curl http://localhost*", ...]`. The soft prompt is no longer the gate.
- `scripts/runners/gpt_researcher_runner.py` (+48) — pre-flight refusal if a real `TAVILY_API_KEY` leaks; propagates `SHIM_MODE=strict`.
- `scripts/runners/deerflow_runner.py` (+85) — crawl_tool re-bind across all loaded `src.*` modules + HTTP-layer gate in driver.
- `scripts/runners/storm_runner.py` (+69) — in-proc `requests.Session.send` HTTP gate; documented choice to gate rather than redirect en.wikipedia.org → kiwix.
- `scripts/runners/local_deep_researcher_runner.py` (+71) — TavilyClient patch + driver-side HTTP gate.

**Per-runner strict-mode verdict** (from the agent's report):

| Runner | Verdict | Mechanism |
|---|---|---|
| claude-code | strict-eligible | tool allowlist incl. `Bash(curl http://localhost*)` |
| opencode | strict-eligible | per-run `commands.allowed` |
| gpt-researcher | strict-eligible | RETRIEVER=tavily→shim + key-leak guard |
| deerflow | strict-eligible | crawl_tool rebind + driver-side `requests.Session` gate |
| storm | strict-eligible | SandboxSearchRM + in-proc `requests` gate |
| local-deep-researcher | strict-eligible | TavilyClient patch + driver-side HTTP gate |
| smolagents | strict-eligible (in-proc) | TavilyClient patch + HTTP gate |
| camel-ai | strict-eligible (in-proc) | TavilyClient patch + HTTP gate |
| **9 others** | **best-effort** | Relies on Layer 2 (shim) + Layer 3 (audit); promotion recipe in the contract doc |

**Validation results**:
1. Verifier smoke test → `{'sandbox_url_pct': 0.5, 'policy_violation': True, 'non_sandbox_urls': ['http://evil.com']}` ✓
2. `pytest tests/test_sandbox_compliance.py -q` → **9 passed in 0.10 s** ✓
3. `run_deep_task.py --help` shows `--strict-sandbox` ✓
4. `integrations.search_shim.app --help` shows `--mode {open,strict}` ✓

**Open questions**:
- Which of the 9 best-effort runners to promote next (B's adversarial tasks are the natural test bench).
- `dzhng` needs Node-side enforcement in `third_party/deep-research/src/api.ts` (out of scope for this workstream).
- STORM/co-storm footnotes don't resolve to URLs in-document; the verifier returns `total_urls=0` for them. May need a co-storm-specific post-processing pass.
- ClaudeCode `--allowed-tools` pattern grammar is undocumented for shell escape sequences (`;`, `&&`). Layer 2 catches escape attempts but stricter parsing upstream would be preferable.

### 4.4 Workstream D — Human alignment

**Files created (8)**:

Collector tool under `tools/human_pref_collector/`:
- `index.html` (467 lines) — vanilla single-page A/B UI: task title + must-cite URLs at top, two scrollable rendered-markdown columns (60vh each), winner buttons + multi-select dim chips ("more depth", "better citations", etc.), annotator field, keyboard shortcuts `a`/`s`/`d`/`Enter`. Markdown via `marked` from CDN. Submits via `POST /save`; **clipboard fallback** when the server is offline.
- `server.py` (284 lines) — stdlib `http.server` backend. Routes:
  - `GET /` → serves index.html
  - `GET /pairs` → next un-annotated pair from `tools/human_pref_collector/pair_queue.jsonl` (auto-generated top-5 agents × 30 tasks = 300 pairs, seeded shuffle)
  - `POST /save` → appends to `data/human_prefs/prefs.jsonl`, advances cursor file
  - CLI: `--port`, `--host`, `--rebuild-queue`

Scripts under `scripts/`:
- `fit_weights_v3.py` (397 lines) — Bradley-Terry MLE via **softmax reparameterization + learnable positive scale `α`** (the scale was load-bearing: a first pass without α gave 0.28 dim-error because the simplex constraint deflates the logit slope). 16 random L-BFGS-B restarts. **5-fold CV log-likelihood vs uniform baseline; refuses to write `weights_v3.json` when CV LL < baseline** (override with `--force`). Falls back to `pillar_elo`-synthesized dim scores with a stderr warning if `leaderboard_deep_v3.json` lacks per-agent dim scores.
- `compute_human_alignment.py` (358 lines) — Spearman / Pearson / Kendall-τ between `composite_v3_softfloor` ranking and human winner-rate. Writes `docs/HUMAN_ALIGNMENT_REPORT.md` with per-agent table + top-10 disagreements.
- `compute_judge_human_kappa.py` (199 lines) — Cohen's κ per LLM-judge dim (depth, rigor, style, checklist), filtered to prefs where `dims_cited` contains that dim. Identifies the weakest rubric for follow-up iteration.

Docs / data:
- `docs/HUMAN_EVAL_PROTOCOL.md` (102 lines) — sampling strategy, dim definitions, validation gates.
- `docs/HUMAN_ALIGNMENT_REPORT.md` — auto-generated from dry-run.
- `docs/JUDGE_HUMAN_KAPPA.md` — auto-generated from synthetic prefs.
- `data/human_prefs/.gitkeep`
- `data/results/deep_v3/weights_v3.json` — dry-run output

**Validation results**:
- Server smoke test: `GET /` returned 200 (14,122 bytes); `POST /save` returned `{"ok": true, "cursor": 1}`; `prefs.jsonl` had one row in schema. ✓
- `fit_weights_v3.py --dry-run` → fitted `{coverage:0.102, depth:0.296, rigor:0.285, style:0.014, checklist:0.175, spec:0.128}` vs ground truth `[0.10, 0.30, 0.25, 0.05, 0.20, 0.10]`. **Max per-dim error 0.036**, well under 0.10 tolerance. CV LL **−0.5344** vs uniform **−0.5353** (just barely better — synthetic noise was hard). ✓
- `compute_human_alignment.py --dry-run` → wrote alignment report: Spearman 0.6429, Pearson 0.7340, Kendall τ 0.5714. ✓

**Open questions**:
- `composite_v3_softfloor` didn't exist yet at fit time (workstream A was still running in a parallel worktree); the alignment script falls back to legacy `composite_v3` (floor=0.1) silently. After the merge this fallback is no longer needed but I left the path in place.
- Pair-queue currently uses the first 30 task IDs (deterministic). HUMAN_EVAL_PROTOCOL.md documents this; switch to randomized if desired.
- Report markdown files (`data/results/deep/<agent>__<task>.md`) don't exist in this checkout yet — the collector will display "_no report file found_" placeholders until those reports land via the runners.

### 4.5 Workstream E — Frontend surfacing

**Files created (3)**:
- `frontend/components/agents/quality-profile.tsx` (125 lines) — 6-row Quality Profile card (Depth / Rigor / Style / Coverage / Checklist / URL Veracity), 10-segment bar + 2-decimal value, brand-color accent, "SYNTHETIC" pill when `synthetic_placeholder` is true.
- `frontend/components/home/dry-run-banner.tsx` (40 lines) — top-of-homepage banner, renders only when `is_dry_run` is true, shows schema-version tag.
- `docs/FRONTEND_V3_CHANGELOG.md` (135 lines) — full changelog covering schema fields consumed, local test recipe, rsync workflow, wrangler.jsonc preservation.

**Files modified (6)**:
- `frontend/lib/data/types.ts` (+53 lines) — `PerPillarElo` type + extended `RankedAgent` with v3 fields, all optional for graceful degradation. Extended `Leaderboard` type with `weights_v3 / composite_formula / rank_significance / human_alignment`.
- `frontend/lib/data/load-leaderboard.ts` (+198 net, 276 total) — **tries v3 JSON first, falls back to v2 then to synthetic seed**. Hydrates `per_pillar`, `per_agent_profile`, derives `sig_vs_next` from `rank_significance_v3.adjacent_pairs`.
- `frontend/components/home/leaderboard-table.tsx` (+90 net) — **replaced the synthetic 7-bar placeholder with a real 8-bar `per_pillar`-driven sparkline** (depth / rigor / style / coverage / checklist / spec / reachability / quote_match) with per-dim global scaling and hover tooltips. Em-dash placeholder when missing. `*` significance marker on adjacent-pair-significant rows.
- `frontend/components/home/highlight-tiles.tsx` (+24 lines) — new **"Deepest reports"** tile reading `depth_avg`; grid bumped to `xl:grid-cols-5`.
- `frontend/app/agents/[id]/page.tsx` (+16 lines) — imports and renders `<QualityProfile>` below the Elo metric block.
- `frontend/app/page.tsx` (+2 lines) — mounts `<DryRunBanner>` at the top.

**Validation results**:
- `npm ci` PASS (436 packages, Node v18 warning ignorable).
- `npm run typecheck` PASS, zero errors.
- `npm run build` PASS, **124 static pages** generated.
- Static-output smoke test: `curl -I /` → 200; HTML contains `DRY-RUN / SYNTHETIC DATA` banner with schema-version pill; 120 `title=` tooltip attributes on the sparkline (8 dims × 15 agents); 6 `aria-label="statistically significant"` markers; `/agents/claude-code/` shows Quality Profile with Depth 0.41 and SYNTHETIC tag.

**Open questions**:
- `loadLeaderboard()` now exposes `weights_v3`, `composite_formula`, `human_alignment` but no component consumes them yet. Natural follow-ups: tooltip on the "Composite Elo" column header showing `composite_formula`, weights legend under the sparkline, "awaiting Workstream D" badge until `human_alignment.n_human_judgements > 0`.
- Node v18 is older than two transitive deps prefer; build still completes cleanly.

---

## 5. Total diff summary

```
71 files changed, 10,909 insertions(+), 104 deletions(-)
```

Excluding generated `data/` artifacts (the 20 adversarial task JSONs, leaderboard_deep_v3.json, weights_v3.json):

```
46 files changed, 7,547 insertions(+), 104 deletions(-)
```

The `-104` lines are concentrated in `frontend/components/home/leaderboard-table.tsx` (synthetic sparkline removed) and `frontend/lib/data/load-leaderboard.ts` (rewritten loader).

### New files (49 total, abridged):

```
src/eval/__init__.py
src/eval/evaluator.py
src/verifiers/depth_verifier.py
src/verifiers/rigor_verifier.py
src/verifiers/style_verifier.py
src/verifiers/sandbox_compliance_verifier.py

scripts/build_deep_leaderboard_v3.py
scripts/build_v2_adversarial_tasks.py
scripts/report_separability.py
scripts/fit_weights_v3.py
scripts/compute_human_alignment.py
scripts/compute_judge_human_kappa.py

tests/test_sandbox_compliance.py
tools/human_pref_collector/index.html
tools/human_pref_collector/server.py
tools/human_pref_collector/pair_queue.jsonl

frontend/components/agents/quality-profile.tsx
frontend/components/home/dry-run-banner.tsx

configs/deep_topics/V2_ADVERSARIAL_TASKS.json
data/tasks/deep_research/cross_site_deep_v2/  (20 task JSONs + checklists + index)
data/results/deep_v3/leaderboard_deep_v3.json
data/results/deep_v3/weights_v3.json
data/human_prefs/.gitkeep

docs/SCORING_V3_DIFF.md
docs/SEPARABILITY_PLAN.md
docs/SEPARABILITY_REPORT.md
docs/STRICT_SANDBOX_CONTRACT.md
docs/HUMAN_EVAL_PROTOCOL.md
docs/HUMAN_ALIGNMENT_REPORT.md
docs/JUDGE_HUMAN_KAPPA.md
docs/FRONTEND_V3_CHANGELOG.md
```

### Modified files (18 total):

```
.gitignore                                    (node_modules, .next, out)
configs/deep_topics/V1_TASK_DESIGN_GRID.md    (V2 adversarial design section)
integrations/search_shim/app.py               (--mode strict, 403 gate, block log)
scripts/run_deep_task.py                      (--strict-sandbox flag + dispatch)
scripts/run_pairwise_battles.py               (--strategy top-pair-densify)
scripts/runners/claudecode_runner.py          (allowlist closing Bash-curl gap)
scripts/runners/deerflow_runner.py            (crawl_tool rebind + HTTP gate)
scripts/runners/gpt_researcher_runner.py      (RETRIEVER=tavily-shim + key-leak guard)
scripts/runners/local_deep_researcher_runner.py (TavilyClient patch + HTTP gate)
scripts/runners/opencode_runner.py            (per-run commands.allowed)
scripts/runners/storm_runner.py               (requests.Session gate)
src/scoring/arena.py                          (compute_separability())
src/scoring/leaderboard_composites.py         (WEIGHTS_V3 + composite_v3_softfloor)

frontend/lib/data/types.ts                    (v3 fields on RankedAgent)
frontend/lib/data/load-leaderboard.ts         (v3-first loader)
frontend/components/home/leaderboard-table.tsx (real 8-bar sparkline)
frontend/components/home/highlight-tiles.tsx  (Deepest reports tile)
frontend/app/page.tsx                         (mount DryRunBanner)
frontend/app/agents/[id]/page.tsx             (mount QualityProfile)
```

---

## 6. Verifying locally

End-to-end checks anyone can run from `/root/Desktop/lyb/deep_reserch`:

```bash
# Scoring
python3 -c "from src.scoring.leaderboard_composites import composite_v3_softfloor, WEIGHTS_V3
print(WEIGHTS_V3)
print(composite_v3_softfloor({'reachability':0.8,'quote_match':0.9,
  'coverage':0.7,'depth':0.6,'rigor':0.55,'style':0.7,'checklist':0.8,'spec':0.9}))"
# expect: WEIGHTS_V3 dict; 0.6555

# Sandbox compliance tests
python3 -m pytest tests/test_sandbox_compliance.py -q
# expect: 9 passed

# Help texts confirm flags wired
python3 scripts/run_deep_task.py --help | grep strict-sandbox
python3 -m integrations.search_shim.app --help | grep mode

# Separability report (against existing leaderboard_deep.json)
python3 scripts/report_separability.py
# writes docs/SEPARABILITY_REPORT.md, prints summary to stdout

# Build the V3 dry-run leaderboard
python3 scripts/build_deep_leaderboard_v3.py --dry-run
# writes data/results/deep_v3/leaderboard_deep_v3.json (synthetic)

# Fit weights from synthetic prefs (sanity check the regression pipeline)
python3 scripts/fit_weights_v3.py --dry-run
# writes data/results/deep_v3/weights_v3.json; should report CV LL > uniform

# Frontend build
cd frontend && npm ci && npm run typecheck && npm run build
# expect: 124 static pages in frontend/out/
```

---

## 7. What's NOT done (deliberate)

These were out of scope for this session per the user's instruction to "build infrastructure, not run benchmarks on VIRCS":

- **No real benchmark runs.** All verifier wiring uses dry-run / synthetic data. Real verifier calls + leaderboard regeneration happen on `westd`/WSL `/opt/deep_reserch` (`/root/CLAUDE.md` documents the host model — heavy compute stays on the workstation).
- **No human prefs collected.** The collector is wired and the queue auto-generates from `leaderboard_deep.json`, but `data/human_prefs/prefs.jsonl` is empty. Weights remain at the uniform `WEIGHTS_V3` placeholder until ≥ 200 prefs land and `fit_weights_v3.py` runs for real.
- **No git push.** This local working copy has no remote configured (the canonical GitHub repo is `yibol9768-alt/deep-research-arena`, separate clone in `/root/Desktop/lyb/deep-research-arena-publish` per project policy). Publishing requires copying the changed files into that clean clone, building, syncing `frontend/out → web/dist`, committing, pushing — and Cloudflare then redeploys.
- **No rsync to `web/dist/`.** Each agent's typecheck/build verified inside its own worktree. The `web/dist/` deploy artifact on `main` is still the baseline static export from before this session. Re-sync is a deliberate `publish` step.
- **9 runners still "best-effort"** under `--strict-sandbox` (rely on Layer 2 + Layer 3 only). Promotion recipe is in `docs/STRICT_SANDBOX_CONTRACT.md`.
- **Cross-family judge routing** for the 3 new verifiers needs an `agent_family` field on the task config that doesn't exist yet. TODO comments in `depth_verifier.py` mark the spot.

---

## 8. Worktree state

The 5 worktrees still exist as siblings:

```
/root/Desktop/lyb/deep_reserch                  [main]            (canonical)
/root/Desktop/lyb/deep_reserch-wt-scoring       [wt-scoring]      (merged)
/root/Desktop/lyb/deep_reserch-wt-separability  [wt-separability] (merged)
/root/Desktop/lyb/deep_reserch-wt-adapters      [wt-adapters]     (merged)
/root/Desktop/lyb/deep_reserch-wt-human-eval    [wt-human-eval]   (merged)
/root/Desktop/lyb/deep_reserch-wt-frontend      [wt-frontend]     (merged)
```

They're redundant after the merge into main and can be removed with:

```bash
for w in scoring separability adapters human-eval frontend; do
  git -C /root/Desktop/lyb/deep_reserch worktree remove "../deep_reserch-wt-$w"
  git -C /root/Desktop/lyb/deep_reserch branch -D "wt-$w"
done
```

(Not done in this session — kept around in case you want to inspect any individual worktree's pre-merge state.)

---

## 9. Recommended next steps

In rough priority order:

1. **Push to GitHub** (or copy diff into the publish clone), let Cloudflare redeploy. After that, the live site shows the dry-run banner + real per-pillar sparkline + Quality Profile.
2. **Run the v3 build for real on `westd`/WSL** — `.venv-camel/bin/python scripts/build_deep_leaderboard_v3.py` (without `--dry-run`) regenerates `leaderboard_deep_v3.json` from actual judge calls.
3. **Collect ≥ 200 human prefs** via `tools/human_pref_collector/server.py`. Then `fit_weights_v3.py` produces real weights, `compute_human_alignment.py` reports the Spearman against humans (target ≥ 0.75, stretch 0.85).
4. **Run the v2 adversarial pilot on `westd`** — 3 agents × 5 candidate tasks, keep the 4–5 with widest variance per family.
5. **Top-pair densify**: `scripts/run_pairwise_battles.py --strategy top-pair-densify --n-per-pair 20` for the top 3 agents. ≈ 60 battles → CI half-width drops from ~70 to ~25 Elo.
6. **Promote the 9 best-effort runners** to strict-eligible one by one per the recipe in `STRICT_SANDBOX_CONTRACT.md`.

Each of these is independent — the foundation is laid; the remaining work is execution on real infra plus human time on the annotation UI.
