# Deep Research Benchmark

A controlled-sandbox + multi-pillar evaluation framework for AI agents
doing **deep research** tasks. Built on top of WebArena's Magento
(shopping) and Postmill (reddit) sandbox sites; agents are scored
across 6 deterministic + LLM-judge pillars and ranked via Arena Elo.

> Status (2026-04-16): 9 task × 4 agent × 27 battles MEGA arena
> running. DeerFlow multi-agent vs single-agent ReAct GLM variants.
> See `RESULTS_SUMMARY.md` for headline findings.

## Why this exists

Industry Deep Research benchmarks (DRACO, DeepResearch Bench,
LiveResearchBench) all evaluate against the *open web* — irreproducible
because search results drift. WebArena gives reproducible sandboxes but
its tasks are pure UI mechanics ("add to cart"), not research.

This project **bridges the two**: real sandboxed sites with actual data
+ deep-research style tasks (multi-step retrieval, cross-source
synthesis, structured reports with citations) + a 6-pillar
deterministic/LLM-judge composite + Chatbot Arena style Elo rankings.

## Architecture

```
data/tasks/deep_research/{shopping, reddit}/dr_*.json
                ↓
        PlaywrightRunner
                ↓
    Agent (ReAct or DeerFlow)
                ↓
   CompositeScorer v2 (6 pillars)
                ↓
   Arena Elo (Composite / Pairwise / Per-pillar)
```

**6 scoring pillars** (`SCORING_FRAMEWORK.md`):

| Pillar | Weight | Implementation |
|---|---:|---|
| Deterministic | 30% | JSON schema + field constraints (`ReportVerifier`) |
| Factuality | 25% | Citation-precision proxy (`CitationVerifier`) |
| Citation | 15% | ALCE recall/precision F1 (`CitationVerifier`) |
| LLM Judge | 15% | 4-dim CoT (`LLMJudgeVerifier`) |
| Comprehensiveness | 10% | DRACO-style binary checklist (`ChecklistVerifier`) |
| Efficiency | 5% | tokens × time × cost (`EfficiencyMetrics`) |

## Setup

```bash
# 1. Python deps (Python 3.9+)
pip install -r requirements.txt
pip install playwright requests beautifulsoup4 anthropic
playwright install chromium

# 2. Bring up sandboxes (see envs/*/README.md)
#    On the host machine:
cd envs/shopping && ./reset.sh   # → http://localhost:7770
cd envs/reddit   && ./reset.sh   # → http://localhost:9999

# 3. Configure LLM credentials
cp .env.example .env
# Fill in ANTHROPIC_AUTH_TOKEN with a Zhipu coding-plan token
# (or any Anthropic-compat token; adjust ANTHROPIC_BASE_URL)
```

## Running

```bash
# Single task with the GLM-5.1 ReAct agent
SHOPPING=http://localhost:7770 PYTHONPATH=. \
    python scripts/bench_v2.py react --tasks dr_shop_0001

# Score an existing answer file (e.g. DeerFlow output)
SHOPPING=http://localhost:7770 PYTHONPATH=. \
    python scripts/bench_v2.py \
    --from-file dr_shop_0001:my-agent:path/to/answer.md

# Full Arena (multiple agents × multiple tasks → leaderboard)
PYTHONPATH=. python scripts/bench_v2.py \
    --from-file dr_shop_0001:react-glm51:data/results/react-glm51_dr_shop_0001.answer.txt \
    --from-file dr_shop_0001:deerflow-glm51:data/results/deerflow_dr_shop_0001.md \
    ... \
    --out data/results/my_arena.md
```

## Repository layout

```
src/
├── runner/        PlaywrightRunner
├── verifiers/     6-pillar scorers (Report / Citation / LLMJudge / Checklist / DOM / String / URL)
├── scoring/       CompositeScorer v2 + Arena Elo (compute_elo, pairwise_battle, per_pillar_elo)
├── agents/        Site-aware ReAct agent (GLM via Anthropic-compat)
├── metrics/       EfficiencyMetrics
└── models/        DeepResearchTask pydantic schema

envs/
├── shopping/      docker-compose, reset.sh, oracle scripts (Magento)
├── reddit/        docker-compose, reset.sh, oracle scripts (Postmill)
└── gitlab/        (downloading)

data/
├── tasks/deep_research/{shopping, reddit}/   *.json + checklists.json
└── results/       Curated bench leaderboards (raw .json/.answer.txt are gitignored)

integrations/
└── deerflow/      Monkey-patch adapters for ByteDance DeerFlow v1

scripts/
├── bench_v2.py            main bench CLI (Arena leaderboard)
├── run_dr_oracle.py       run a single task through its hand-written Oracle
└── run_webarena_task.py   smoke against original WebArena tasks

tests/                     21/21 passing
```

## Documentation map

- `PLAN.md` — full progress + P0/P1/P2/P3 roadmap
- `RESULTS_SUMMARY.md` — TL;DR of 4 Arena experiments + 3 core findings
- `PROGRESS_REPORT.md` — one-page report (for advisors / colleagues)
- `SCORING_FRAMEWORK.md` — v2 six-pillar design rationale
- `DEEP_RESEARCH_TASK_SPEC.md` — what counts as a "deep research" task
- `ROADMAP.md` — Stage A / B / C path
- `data/results/bench_v2_MEGA.md` — current authoritative leaderboard

## Key findings so far

1. **Multi-site exposes DeerFlow's robustness gap.** Single-site (5 task)
   bench: DeerFlow leads by +122 Elo. Add reddit (9 task): lead drops
   to +5. GLM content-safety blocks DeerFlow's long prompts on
   politically charged reddit content; single-agent ReAct's shorter
   prompts avoid this.
2. **LLM judge length-bias is real.** Same `glm-4.5` agent ranks #4 by
   composite (936) and #1 by pairwise judge (1104). Demonstrates why
   pure LLM-judge benchmarks need a deterministic skeleton.
3. **No single agent dominates all pillars.** DeerFlow wins
   citation/factuality; `glm-4.6` ReAct wins comprehensiveness/judge;
   `glm-5.1` ReAct wins determinism. Multi-dim scoring isn't
   collapsible.

## License

TBD.
