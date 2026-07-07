# Deep Research Arena

**A controlled-sandbox benchmark and Elo arena for Deep-Research agents, with judge-independent grounding verification.**

Live site: [www.deepresearcharena.com](https://www.deepresearcharena.com)

Agents perform cross-site research tasks inside a frozen, offline sandbox web (Magento shopping on `:7770`, Postmill forum on `:9999`, Kiwix Wikipedia on `:8090`). Every cited URL is checked for reachability and quote-match against that sandbox, so a fluent report that cites unreachable or fabricated sources cannot top the board.

---

## Table of contents

1. [What this project is](#1-what-this-project-is)
2. [How it works (end-to-end)](#2-how-it-works-end-to-end)
3. [The sandbox and where the data comes from](#3-the-sandbox-and-where-the-data-comes-from)
4. [Tasks and goldens (how the QA is built)](#4-tasks-and-goldens-how-the-qa-is-built)
5. [Scoring: truth-gated Elo](#5-scoring-truth-gated-elo)
6. [Leaderboards (live)](#6-leaderboards-live)
7. [Quickstart: build the sandbox with Docker](#7-quickstart-build-the-sandbox-with-docker)
8. [Reproduce the boards](#8-reproduce-the-boards)
9. [Repository layout](#9-repository-layout)
10. [Deploy](#10-deploy)
11. [Status and limitations](#11-status-and-limitations)

---

## 1. What this project is

Deep Research Arena measures how good a "deep research" agent actually is at producing a long, well-cited market-intelligence report, and whether its citations are real.

The problem it solves: an LLM-as-judge will happily rank a fluent report highly even when most of its cited URLs do not exist. We separate two axes and score them independently:

- **Reads well** (judge quality): pairwise judge Elo.
- **Stands up** (grounding truthfulness): are the cited URLs reachable, and does the cited page actually contain the quoted claim. This is computed with no LLM at all, against a frozen sandbox.

The headline score multiplies the two, so a "fluent fabricator" can never top the board. Everything (tasks, goldens, scoring code, committed scores, the site) is in this repo and reproducible offline.

---

## 2. How it works (end-to-end)

```
                  data/tasks/...               data/golden/deep_clean/...
                  (task intent + spec)         (must-cite URLs + fact triples)
                          │                              │
   ┌──────────────────────┴──────────────┐               │
   │  Sandbox (frozen offline web)        │               │
   │   shopping :7770  reddit :9999       │               │
   │   wiki :8090   gateway :8081         │               │
   └──────────────────────┬──────────────┘               │
                          │ agent searches + browses             │
                          ▼                                      │
            Agent report (Markdown, cited)                       │
                          │                                      │
                          ▼                                      ▼
   scripts/score_deep_answer.py  ── reachability% ──┐   must-cite recall
       │                         ── quote-match%  ──┤   (golden compared
       │                         ── judge checklist ┘    to citations)
       ▼
   per-(agent,task) score JSON  →  scripts/build_real_leaderboard.py
                                   (pairwise judge battles → Bradley-Terry Elo
                                    × grounding gate → gated_score, with CIs)
                                          │
                                          ▼
                          data/results/.../leaderboard_deep_v3.json
                                          │
                          frontend/ (Next.js) → web/dist/ → Cloudflare (live site)
```

The five stages in words:

1. **Sandbox** brings up a frozen copy of a shopping site, a forum, and Wikipedia, plus a search gateway, all offline. This is the only "web" the agents may see.
2. **Tasks** tell the agent what report to write. **Goldens** record, per task, which sandbox URLs are the ground-truth must-cite sources and which facts (price, rating, thread score, wiki definition) are true.
3. **Agents** (claude-code, gpt-researcher, camel-ai, DR Tulu, etc.) run against the sandbox and produce a cited Markdown report.
4. **Scoring** checks every citation for reachability and quote-match (judge-free), runs pairwise judge battles for quality, and fits Bradley-Terry Elo.
5. **Leaderboard** = judge Elo gated by grounding, rebuilt from committed scores and published to the live site.

---

## 3. The sandbox and where the data comes from

All "web content" the agents see is a frozen, offline snapshot, served by four containers on one Docker network. Nothing reaches the real internet, which is what makes citation grounding verifiable and the benchmark reproducible.

| Service | Port | Corpus | Where the data comes from |
|---|---|---|---|
| `shopping` | 7770 | Magento product catalog (products, prices, ratings, reviews) | WebArena Magento snapshot, pre-populated DB baked into the image (`shopping_final_0712`, ~4.2 GB) |
| `reddit` | 9999 | Postmill forum (subforums, threads, comments, votes) | WebArena Postmill snapshot, pre-populated DB baked into the image (`postmill-populated-exposed-withimg`, ~1.8 GB) |
| `wiki` | 8090 | Wikipedia | Public Kiwix server image + a host-mounted `.zim` snapshot (English Wikipedia, ~28 GB) downloaded from [download.kiwix.org](https://download.kiwix.org/zim/wikipedia/) |
| `gateway` | 8081 | search + LLM shim | This repo (`infra/Dockerfile.gateway`); FastAPI search shim that exposes Tavily / Serper / Brave / SearxNG / DDG / OpenAI-compatible endpoints, all backed only by the three corpora above |
| `ds_proxy` | 8088 (internal) | LLM proxy | This repo (`infra/Dockerfile.ds_proxy`); OpenAI-compatible proxy to the backbone LLM, reached via the gateway |

Key design points:

- **The corpora are frozen.** The shopping and forum data were scraped once (2025-09 cutoff) and baked into images. They are deliberately not regenerated on the fly, because re-scraping would change the benchmark. The Magento and Postmill DBs ship inside the images; Wikipedia is a mounted `.zim` file.
- **The gateway is the only door.** Agents are pointed at `http://localhost:8081`. Every search result and browsed page resolves to a `localhost:7770/9999/8090` URL, which is exactly why a cited URL can later be probed for reachability.
- **Reset scripts** in `envs/{shopping,reddit}/reset.sh` rebuild or restore a container to its pristine state between runs.
- Full image inventory and offline rebuild paths are in [`infra/build-images.md`](infra/build-images.md).

---

## 4. Tasks and goldens (how the QA is built)

A "QA item" here is a **(task, golden)** pair. The task is the question (what report to write); the golden is the answer key (which sandbox URLs and facts are ground truth).

### Task definition

Tasks live in `data/tasks/deep_research/cross_site_deep/*.json` (101 deep tasks) and `cross_site_deep_v2/*.json` (22 adversarial tasks). Each task JSON (schema `deep-1.0.0`) specifies:

- `intent` — the research brief, e.g. *"Produce a comprehensive market-intelligence report on consumer-grade audio headphones, spanning three dimensions, grounded in at least 120 distinct sandbox URLs."*
- `sites` — which corpora the task spans (shopping / reddit / wikipedia).
- `markdown_spec` — hard requirements: min words, min citations, min pages browsed.
- `citation_policy` — what must be cited (price, rating, thread score, feature claim, wiki definition), min distinct sources/domains, allowed domains.
- `url_coverage` / `url_reachability` — must-cite recall threshold, min reachability rate (0.30).
- `synthesis_requirements` — cross-site reasoning the report must perform (contradiction findings, brand-sentiment rankings, a final buy list with sources per item).
- `golden` — pointer to the golden file and the expected fact predicates.

Tasks are generated from topic configs in `configs/deep_topics/*.yaml` (one topic per task: audio headphones, coffee gear, etc.).

### Golden generation

Goldens are built by **scraping the live sandbox**, not hand-written. `scripts/build_deep_golden.py` crawls the three corpora for a task's topic and emits `data/golden/deep_clean/<task>.json` containing:

- `must_cite_urls` — the ground-truth sources an honest report should cite (with category, weight, and a `why`).
- `expected_pool_urls` — the broader on-topic pool (cited is good but not mandatory).
- `triples` — `(subject, predicate, object, source_url)` facts (e.g. a product's price, a thread's score, a wiki definition) used to check that a claim is actually true on the page it cites.
- `metadata` — what was discovered (products parsed, brands, thread counts).

### Cleaning and the manifest

Auto-built goldens are noisy (keyword collisions pull in off-topic sources). Two steps clean them:

- `src/verifiers/golden_curate.py` deduplicates and quality-checks sources.
- `scripts/build_clean_benchmark_manifest.py` writes `data/golden/deep_clean/_manifest.json`, which records, per task, a `verdict` and the `valid_sources`.

Current manifest (`canonical_scorable = 75`):

| verdict | count | meaning |
|---|---:|---|
| `valid` | 65 | full cross-site golden, fully scorable |
| `forum-invalid` | 10 | usable but with thin forum coverage |
| `quarantine` | 25 | too few on-topic cross-site cites after cleaning, held out |

So of 100 deep tasks, **75 are scorable**. The 22 adversarial tasks (causal / contradiction / long-tail) exist but their goldens are not built yet. The full remediation log is in [`docs/EVAL_SET_REMEDIATION.md`](docs/EVAL_SET_REMEDIATION.md); contamination checks (no memorization leakage) are in [`docs/CONTAMINATION_REPORT.md`](docs/CONTAMINATION_REPORT.md).

---

## 5. Scoring: truth-gated Elo

The headline score multiplies a pairwise judge Elo by a judge-independent grounding gate:

```
gated_score = round( judge_Elo * (reachability% + quote%) / 200 )
```

- **judge Elo**: a 3-judge PoLL jury (deepseek-v4-flash, qwen3-max, glm-5), position-debiased, Bradley-Terry with bootstrap CIs. Measures "reads well".
- **grounding gate**: `reachability%` (cited sandbox URLs that resolve to HTTP 200) and `quote%` (quoted text actually present on the cited page), computed without any judge API. Measures "stands up".

Why this matters: judge preference and citation grounding are decoupled. A model the judges love can cite sources that mostly do not resolve. The gate keeps unsupported polish from dominating the ranking. The exact verifier and Elo formulas are in `src/verifiers/` and `src/scoring/bradley_terry.py`; the scoring methodology and its validation record are in [`docs/EVAL_FACTSHEET.md`](docs/EVAL_FACTSHEET.md).

---

## 6. Leaderboards (live)

**Framework board** (12 agents). Top by gated score:

| Agent | judge Elo | reach% | gated |
|---|---:|---:|---:|
| claude-code | 1166 | 90 | 1032 |
| opencode | 1078 | 94 | 975 |
| camel-ai | 1040 | 60 | 572 |
| deerflow | 1005 | 60 | 545 |
| flowsearcher-ds | 943 | 46 | 416 |

`gpt-researcher` ranks high on raw judge Elo (1147) but only about 4% of its citations resolve, so its gated score falls near the bottom. That inversion is the point of the gate.

**Backbone-LLM board** (`/models`): 8 vendor LLMs run on the same minimal scaffold, varying only the base model, over 24 tasks and 643 battles.

> Honest caveat: the live 12-agent framework board is currently about 40.5% single-juror (the later claude-code and opencode battles were judged when the judge accounts were nearly out of funds). A clean 3-judge re-judge is pending judge-API funding; progress is tracked on the site's [`/changelog`](https://www.deepresearcharena.com/changelog).

---

## 7. Quickstart: build the sandbox with Docker

One command brings up all four sandbox containers on a single Docker network:

```bash
docker compose -f infra/sandbox.docker-compose.yml up -d

# Smoke-test all services
curl -fsS http://localhost:8081/healthz   # gateway (returns 200 within ~90s)
curl -fsS http://localhost:7770/          # Magento shopping
curl -fsS http://localhost:9999/          # Postmill forum
curl -fsS http://localhost:8090/          # Kiwix Wikipedia
```

Then point any agent at the sandbox:

```bash
export TAVILY_API_URL=http://localhost:8081
export OPENAI_BASE_URL=http://localhost:8081/llm/v1   # any Bearer token works
export DEEPSEEK_API_KEY=sk-...                         # backbone LLM key (bring your own)
```

Image sourcing (`docker compose` reads these from env, with sensible local defaults):

- **Gateway and ds_proxy** build from this repo:
  ```bash
  docker build -f infra/Dockerfile.gateway  -t dr-bench-gateway:latest  .
  docker build -f infra/Dockerfile.ds_proxy -t dr-bench-ds-proxy:latest .
  ```
- **Wiki** pulls the public Kiwix image; set `WIKI_ZIM_DIR` to a folder holding a downloaded `.zim` snapshot.
- **Shopping and reddit** use the pre-populated corpus images. If you cannot pull them, see [`infra/build-images.md`](infra/build-images.md) for the offline rebuild path (`Path C`).

A `down -v` plus the `envs/{shopping,reddit}/reset.sh` scripts restore the sandbox to its pristine, frozen state.

---

## 8. Reproduce the boards

The committed jury sources rebuild both boards from the repo, with no live box needed:

```bash
python3 scripts/build_site_board_from_judge_elo.py   # framework board -> data/results/deep_v3/leaderboard_deep_v3.json
python3 infra/box/build_model_board.py               # backbone-LLM board (uses /opt paths; sed the root to run elsewhere)
```

Both reproduce every numeric value (Elo, CIs, grounding, ranking) of the deployed boards.

To score a single fresh report against a task (needs the sandbox up):

```bash
python3 scripts/score_deep_answer.py --task dr_cross_deep_0001 --answer path/to/report.md
# -> reachability%, quote-match%, judge checklist, must-cite recall
```

---

## 9. Repository layout

```
src/            scoring, verifiers (reachability / quote-match), jury, Bradley-Terry
scripts/        build / score / leaderboard pipeline
data/           tasks, cleaned goldens, committed boards + jury sources (data/results)
configs/        deep_topics/*.yaml — one topic config per task
frontend/       Next.js site (production source) -> web/dist (served static artifact)
web/            committed deploy artifact + Cloudflare worker (annotate / status API)
infra/          sandbox docker-compose, Dockerfiles, build-images.md; infra/box = box ops snapshots
envs/           WebArena sandbox envs (shopping / reddit) + reset scripts
integrations/   search shim + ds_proxy (OpenAI-compatible sandbox gateway)
tests/          offline tests
docs/           methodology, datasheet, status, findings; docs/archive = historical notes
```

---

## 10. Deploy

The public site is served by Cloudflare from the committed `web/dist/`. Build and publish:

```bash
cd frontend && npm ci && npm run typecheck && npm run build
rsync -a --delete --exclude 'wrangler.jsonc' frontend/out/ web/dist/
# commit frontend/ + data/ + web/dist/, then push main; Cloudflare redeploys automatically
```

Hard rule: every meaningful change must be logged in `data/changelog.json` (rendered on `/changelog`) before deploy. Full steps and the changelog schema are in [`CLAUDE.md`](CLAUDE.md).

---

## 11. Status and limitations

[`docs/EVAL_FACTSHEET.md`](docs/EVAL_FACTSHEET.md) records what has been validated and what has not; [`docs/DATASHEET.md`](docs/DATASHEET.md) documents the dataset; [`docs/EVAL_SET_REMEDIATION.md`](docs/EVAL_SET_REMEDIATION.md) logs the eval-set cleanup. Known open items (more scorable tasks, full reproducibility, real human-alignment kappa labels) are tracked on the site's [`/changelog`](https://www.deepresearcharena.com/changelog).
