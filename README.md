# Deep Research Arena

**A controlled-sandbox benchmark and Elo arena for Deep-Research agents, with judge-independent grounding verification.**

Live site: [www.deepresearcharena.com](https://www.deepresearcharena.com)

Agents perform cross-site research tasks inside an immutable sandbox web (Magento shopping on :7770, Postmill forum on :9999, kiwix Wikipedia on :8090). Every cited URL is checked for reachability and quote-match against that sandbox, so a fluent report that cites unreachable or fabricated sources cannot top the board.

---

## Scoring: truth-gated Elo

The headline score multiplies a pairwise judge Elo by a judge-independent grounding gate:

```
gated_score = round( judge_Elo * (reachability% + quote%) / 200 )
```

- **judge Elo**: a 3-judge PoLL jury (deepseek-v4-flash, qwen3-max, glm-5), position-debiased, Bradley-Terry with bootstrap CIs. Measures "reads well".
- **grounding gate**: `reachability%` (cited sandbox URLs that resolve) and `quote%` (quoted text actually present on the cited page), computed without any judge API. Measures "stands up".

Why this matters: judge preference and citation grounding are decoupled. A model the judges love can cite sources that mostly do not resolve. The gate keeps unsupported polish from dominating the ranking. See `docs/FINDINGS_2026-06-09.md`.

---

## Leaderboards (live)

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

> Honest caveat: the live 12-agent framework board is currently about 40.5% single-juror (the later claude-code and opencode battles were judged when the judge accounts were nearly out of funds). A clean 3-judge re-judge is pending judge-API funding. See `docs/PROJECT_STATUS_2026-06-09.md`.

---

## Repository layout

```
src/            scoring, verifiers (reachability / quote-match), jury, Bradley-Terry
scripts/        build / score / leaderboard pipeline
data/           tasks, cleaned goldens, committed boards + jury sources (data/results)
frontend/       Next.js site (production source) -> web/dist (served static artifact)
web/            committed deploy artifact + Cloudflare worker (annotate / status API)
infra/          sandbox docker-compose; infra/box = version-controlled box ops snapshots
envs/           WebArena sandbox envs (shopping / reddit) + reset scripts
integrations/   search shim + ds_proxy (OpenAI-compatible sandbox gateway)
tests/          offline tests
docs/           methodology, datasheet, status, findings; docs/archive = historical notes
```

## Reproduce the boards

The committed jury sources rebuild both boards from the repo, no live box needed:

```bash
python3 scripts/build_site_board_from_judge_elo.py   # framework board -> data/results/deep_v3/leaderboard_deep_v3.json
python3 infra/box/build_model_board.py               # backbone-LLM board (uses /opt paths; sed the root to run elsewhere)
```

Both reproduce every numeric value (Elo, CIs, grounding, ranking) of the deployed boards.

## Tasks and goldens

100 cross-site deep tasks, of which 75 are scorable and 25 are quarantined (too few on-topic cross-site cites after cleaning). A further 20 adversarial tasks (causal, contradiction, long-tail) exist but their goldens are not built yet. Cleaning, per-task source restriction, and contamination checks are documented in `docs/EVAL_SET_REMEDIATION.md` and `docs/CONTAMINATION_REPORT.md`.

## Deploy

The public site is served by Cloudflare from the committed `web/dist/`. The build and publish steps, and the mandatory changelog rule, are in `CLAUDE.md`.

## Status and limitations

`docs/PROJECT_STATUS_2026-06-09.md` is the authoritative, file-verified status: what is done, what remains (more tasks, full reproducibility, real human-alignment labels), and the current honest caveats. `docs/FULL_PROJECT_ROADMAP.md` holds the phased plan.
