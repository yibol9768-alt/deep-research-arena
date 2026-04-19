# Deep Research Arena

**A controlled-sandbox benchmark + multi-framework Elo arena for Deep Research agents.**

Agents work inside a WebArena sandbox (Magento shopping + Postmill reddit + kiwix Wikipedia), every factual claim is verified against the sandbox's backing database, and 13 frameworks battle on a paper-ready Elo leaderboard.

> **Status — 2026-04-19**: 13 agents × 4 cross-site tasks scored, 7-pillar composite, DeepSeek ↔ GLM dual-judge with 1000-sample bootstrap CI and permutation rank test. Task bank expanded to 107 (consumer + scholarly). Sandbox search unified behind a single Tavily / Firecrawl-compatible shim so any DR framework integrates in zero code.

---

## 🏆 Current leaderboard (paper-ready)

52 runs · **dual-judge** (GLM-agent runs judged by DeepSeek V3.2; DeepSeek-agent runs (`-ds` suffix) judged by GLM-4.5 — different-family always, per [Wataoka 2024 NeurIPS](https://arxiv.org/abs/2410.21819)) · bootstrap over C(13,2) × 4 = **312 battles**.

| Rank | Agent | Elo | 95% CI | W-L-D |
|---:|---|---:|---|---|
| 🥇 **1** | **react-qwen35plus** | **1295.1** | [1224, 1360] | 43-4-1 |
| 🥈 **2** | **gpt-researcher** | **1278.5** | [1197, 1347] | 42-5-1 |
| 🥉 **3** | **react-glm5** | **1261.6** | [1188, 1332] | 41-6-1 |
| 4 | deerflow-glm46-shim | 1161.6 | [1080, 1240] | 35-13-0 |
| 5 | camel-ai | 1121.2 | [1039, 1190] | 31-15-2 |
| 6 | deerflow-glm46-new | 1095.1 | [1022, 1171] | 30-17-1 |
| 7 | deerflow-glm46 | 999.0 | [928, 1073] | 24-24-0 |
| 8 | camel-ai-ds | 974.8 | [900, 1048] | 22-26-0 |
| 9 | smolagents | 882.0 | [816, 959] | 16-32-0 |
| 10 | odr-ds | 780.2 | [719, 866] | 9-38-1 |
| 11 | smolagents-ds | 730.6 | [655, 805] | 6-42-0 |
| 12 | deerflow-ds | 729.8 | [668, 798] | 5-41-2 |
| 13 | gpt-researcher-ds | 690.5 | [626, 760] | 3-44-1 |

Full table, per-pillar Elo, and rank-significance test: [`data/results/FINAL_LEADERBOARD.md`](data/results/FINAL_LEADERBOARD.md).

### Three headline findings

1. **Adapter quality matters more than framework reputation.** DeerFlow jumped +162 Elo (837 → 999) when we swapped our custom adapter for the unified Tavily-compat shim. Benchmarks that hand-roll each framework's integration systematically under-report.
2. **Agent model and judge model both shift the ranking, independently.** The 5 `-ds` rows are the same frameworks with DeepSeek instead of GLM as agent (and GLM instead of DeepSeek as judge). DeepSeek agents consistently fall 150–600 Elo behind their GLM twins — because DeepSeek writes reports with hallucinated external URLs (`onestopmarket.com/...`) instead of real sandbox URLs (`localhost:7770/...`), crushing the citation pillar.
3. **Judges have length / style bias that's detectable here.** smolagents emits flowery but ungrounded reports; its composite is 9th, but the per-pillar `llm_judge` row puts it at Elo 1296 — highest of any agent. Structured pillars (`fact_kg`, `evidence_density`) cut the illusion.

---

## 🧭 What this is

**The problem.** Industry DR benchmarks split three ways:

- *Open-web* (OpenAI Deep Research, Perplexity, Gemini) — not reproducible, search drifts daily.
- *Human-labeled* (DRACO 40 rubrics/task, ResearchRubrics 2,800 human hours) — reproducible, ruinously expensive to refresh.
- *WebArena-style sandboxes* — fully reproducible but only test UI mechanics, not research synthesis.

**Our angle.** Put Deep Research tasks **inside** a reproducible sandbox, and use the sandbox's own database as ground truth. Every factual claim is checkable by direct SQL against Magento / Postgres / a static Wikipedia corpus. You get the grounding that ResearchRubrics paid 2,800 human hours for — out of a Docker container, at zero marginal cost.

Closest neighbours in prior work (see [`PAPER_POSITIONING.md`](PAPER_POSITIONING.md)):

- **BrowseComp-Plus** (static corpus, Q&A format) — we match the reproducibility but target long-form research synthesis.
- **WebArena-Verified** (transactional sandbox) — we inherit the sandbox, drop the UI obsession, test report writing.
- **DeepResearch Bench / LiveDRBench** — same long-form target, but they can't anchor to a database.

---

## 🏗 Architecture

```
                ┌──── Shim (FastAPI :8081) ─────┐
  Any DR agent  │  /search    (Tavily-compat)   │  Magento  :7770
  ──────────►   │  /v1,/v2/scrape (Firecrawl)   │  Postmill :9999
  (zero code)   │  /extract   (kiwix Wikipedia) │  kiwix    :8090
                └──────────────┬────────────────┘
                               │ markdown report
                               ▼
          CompositeScorer v3.1  (7 pillars, weighted)
          ┌────────────────────────────────────────┐
          │ citation          0.25  ALCE / NLI     │
          │ evidence_density  0.20  entity ratio   │
          │ llm_judge         0.20  RACE 4-dim CoT │
          │ checklist         0.20  15-item DRACO  │
          │ fact_kg           0.05  DB verify      │
          │ markdown_structure 0.05                │
          │ efficiency        0.05                 │
          └────────────────────────────────────────┘
                               │
                               ▼
                     Arena (compute_elo_with_ci
                           + permutation test
                           + per_pillar_elo)
```

### Sandbox search shim

A single FastAPI process exposes Tavily's `/search`, Firecrawl v1/v2 `/search` + `/scrape`, plus a kiwix Wikipedia pass-through. Any DR framework that speaks Tavily or Firecrawl integrates with **no code change** — just:

```bash
export TAVILY_API_KEY=tvly-anything
export TAVILY_API_URL=http://localhost:8081
# (frameworks that hard-code base_url are monkey-patched in scripts/run_*.py)
```

---

## 🚀 Quickstart

```bash
# 1. clone + deps
git clone <repo> deep_reserch && cd deep_reserch
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 2. start the sandbox (WSL2 / Docker Compose)
#    Magento :7770, Postmill :9999, kiwix :8090
#    See envs/ for docker-compose files.

# 3. start the search shim
uvicorn integrations.search_shim.app:app --port 8081 &

# 4. pick an agent and run 4 cross-site tasks
python scripts/run_gpt_researcher.py      # grounded, 4 tasks, ~10 min
python scripts/run_camel_ai.py            # 4 tasks, ~6 min
python scripts/run_deerflow_cross.py      # via shim, ~15 min
python scripts/run_smolagents.py          # code-as-action, ~5 min

# 5. score with the composite + judge
python scripts/rescore_all_with_deepseek.py  # writes final_<agent>_<task>.json

# 6. build the paper-ready leaderboard
python scripts/build_final_leaderboard.py    # writes FINAL_LEADERBOARD.md
```

### Environment

```bash
# agent backend (swap for a different model)
OPENAI_API_KEY=<zhipu coding-plan key>
OPENAI_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4

# judge backend (different family from agent → self-preference mitigation)
JUDGE_PROVIDER=openai
JUDGE_API_KEY=<deepseek key>
JUDGE_BASE_URL=https://api.deepseek.com
JUDGE_MODEL=deepseek-chat
```

To run the role-swapped arena (agent = DeepSeek, judge = GLM-4.5), swap the two keys and set `JUDGE_MODEL=glm-4.5`. `.env.bak.*` files record prior configurations.

---

## 🤖 Integrated agents

All 13 are driven from `scripts/run_*.py` and hit the same shim.

| Agent | LLM | Pattern | Notes |
|---|---|---|---|
| `react-qwen35plus` | Qwen 3.5-plus | ReAct (our impl) | Tool loop over Playwright + shim |
| `react-glm5` | GLM-5.1 | ReAct (our impl) | Same harness, different LLM |
| `gpt-researcher` | GLM-4.7 | RAG + report | Tavily monkey-patched to shim |
| `camel-ai` | GLM-4.7 | Role-play 2-agent | Toolkit includes web-search + code |
| `deerflow` × 3 | GLM-4.6 | Plan-Execute-Report | legacy / new adapter / shim adapter |
| `smolagents` | GLM-4.7 | Code-as-action | Hallucinates on GLM (sentinel mismatch) |
| `camel-ai-ds` | DeepSeek V3.2 | Role-play | `-ds` = DeepSeek agent / GLM judge |
| `gpt-researcher-ds` | DeepSeek V3.2 | RAG | URL hallucination hurts `cite` |
| `deerflow-ds` | DeepSeek V3.2 | Plan-Execute-Report | |
| `smolagents-ds` | DeepSeek V3.2 | Code-as-action | Sentinel fixed, grounding still weak |
| `odr-ds` | DeepSeek V3.2 | LangChain graph | Only unlocks on DeepSeek (GLM can't return JSON schema) |

**Parked** (documented incompatibilities): `dzhng/deep-research` (Node API stalls >30 min/task on DeepSeek), `LearningCircuit/local-deep-research` (template placeholders not filled), `Stanford STORM` (retrieval module bypasses the shim and hits `en.wikipedia.org` directly).

---

## 📊 Scoring pillars

| Pillar | Weight | Verifier | Deterministic? |
|---|---:|---|---|
| `citation` | **0.25** | `CitationVerifier` — ALCE substring; `CITATION_MODE=entailment` switches to DeepSeek NLI | substring: ✓ · NLI: ✗ |
| `evidence_density` | **0.20** | `compute_evidence_density` — distinct PDP / Reddit post ratio | ✓ |
| `llm_judge` | **0.20** | `LLMJudgeVerifier` — RACE 4-dim CoT | ✗ |
| `checklist` | **0.20** | `ChecklistVerifier` — 15-item DRACO binary rubric | ✗ |
| `fact_kg` | **0.05** | `FactKGVerifier` — golden triples + DB-verified precision | recall: ✓ |
| `markdown_structure` | **0.05** | `MarkdownReportVerifier` — min words / paragraphs / citations / pages | ✓ |
| `efficiency` | **0.05** | `EfficiencyMetrics` — tokens × wall-time × cost | ✓ |

`fact_kg` is demoted to 0.05 in v3.1 because the auto-generated oracle has known false negatives (a $607 printer surfaced in a $500 home-office build, "Magic Home Nightstand" in a kitchen task). Intent-aware `scripts/rebuild_oracle_filtered.py` produces clean `data/golden/*.filtered.json` oracles for all 87 consumer tasks — re-weighting pending full rescore.

---

## 🗂 Task bank

**107 tasks** across two tiers:

- `dr_cross_v3_0001 — 0087` — consumer / UGC cross-site (shopping + reddit + optional wikipedia)
- `dr_cross_v3_0088 — 0107` — scholarly / policy (medicine, economics, history, AI ethics, urban planning — wikipedia-heavy with reddit community sentiment)

All tasks specify `markdown_spec` (min words, paragraphs, citations, distinct pages browsed), `citation_policy` (domain allowlist, min distinct sources), and a `golden` triples path. See `data/tasks/deep_research/cross_site/TASK_INDEX.md`.

---

## 🧪 Statistical rigor

- **Bootstrap 95% CI** (N=1000 resamples with replacement) on every Elo point estimate.
- **Permutation rank-significance test** (N=1000 label shuffles) on every adjacent-rank gap.
- **Per-pillar Elo** — seven independent boards so no single pillar saturates the ranking.
- **Dual-judge**: agent and judge are always different model families, per [Wataoka 2024 NeurIPS](https://arxiv.org/abs/2410.21819) / [JudgeBench ICLR 2025](https://arxiv.org/abs/2410.12784).

At N=48 battles per agent, none of the adjacent gaps reach p < 0.05. We're honest about the underpowering — the leaderboard separates **tiers**, not adjacent positions.

---

## 📁 Repo layout

```
src/
├── verifiers/        # 7 pillar verifiers + judge_client abstraction
├── scoring/          # composite_v3 + arena (Elo, bootstrap, permutation)
├── golden/           # DB-verified fact KG extractor
└── agents/           # ReAct agent (dual Anthropic/OpenAI backend)

integrations/
├── search_shim/      # FastAPI Tavily + Firecrawl compat shim
└── deerflow/         # unified multi-site adapter

scripts/
├── run_<agent>.py    # 13 agent runners (all point at the shim)
├── bench_v3.py       # orchestrator
├── rescore_all_with_deepseek.py
├── build_final_leaderboard.py
├── rebuild_oracle_filtered.py
└── generate_scholarly_tasks.py

data/
├── tasks/deep_research/cross_site/   # 107 task specs + checklists
├── golden/                            # ground-truth triples (+ .filtered.json v2)
└── results/
    ├── FINAL_LEADERBOARD.md           # ← the paper-ready board
    ├── LEADERBOARD_v3_ED.md           # evidence-density rescored
    ├── arena_final.json
    └── final_<agent>_<task>.{json,answer.md}

third_party/          # 14 cloned frameworks (smolagents / ODR / CAMEL / …)
```

---

## 📖 Related docs

- [`PLAN.md`](PLAN.md) — full roadmap, milestones, current status
- [`PAPER_POSITIONING.md`](PAPER_POSITIONING.md) — our place among contemporary DR benchmarks
- [`METHODOLOGY_AUDIT_2026-04-19.md`](METHODOLOGY_AUDIT_2026-04-19.md) — peer-review self-critique + P0 fixes
- [`PAPER_FINDINGS.md`](PAPER_FINDINGS.md) — headline plots + findings narrative
- [`data/results/FINAL_LEADERBOARD.md`](data/results/FINAL_LEADERBOARD.md) — full Elo table + per-pillar breakdown

---

## ⚠️ Caveats for reviewers

1. **Sample size.** 48 battles/agent — CI half-widths 60–80 Elo. Adjacent gaps almost never reach p < 0.05; the board separates tiers, not neighbours.
2. **Oracle v1 vs v2.** Default `data/golden/*.json` is auto-scraped top-N per category and has false negatives; intent-aware v2 (`*.filtered.json`) is regenerated but not yet used for rescoring. `fact_kg` weight demoted to 0.05 in the interim.
3. **Task domain.** 107 tasks generated but only 4 scored so far. Scholarly tier (0088-0107) expansion pending.
4. **Framework incompatibilities documented**:
   - smolagents + GLM emits `</code>` instead of `<end_code>` → zero-tool-call hallucinations (fixed with DeepSeek).
   - LangChain ODR / dzhng require structured JSON output → GLM 4.7 returns free text (fixed with DeepSeek + `method=function_calling` patch).
   - STORM's scraper bypasses the shim and hits `en.wikipedia.org` directly.
5. **Citation metric.** Default is ALCE substring; `CITATION_MODE=entailment` swaps to claim-level NLI via DeepSeek. Headline scores use substring; NLI variant recorded in pillar `details`.

---

## 📄 Citing this work

```bibtex
@software{liu2026deepresearcharena,
  title  = {Deep Research Arena: a Sandbox + Multi-Framework Elo Benchmark},
  author = {Liu, Yibo},
  year   = {2026},
  url    = {https://github.com/yibol9768-alt/deep-research-arena}
}
```

---

<sub>Active research. Expect the board to change as (a) the scholarly tier gets scored, (b) oracle v2 gets applied, (c) real pairwise battles scale past N=12, and (d) additional frameworks (ii-researcher, magentic-ui, suna) come online.</sub>
