# Benchmark Datasheet Template

## 1. Basic Information

- Benchmark name:
- Version:
- Release date:
- Maintainer:
- Repository:
- License:

## 2. Purpose

Describe what the benchmark measures and what it does not measure.

## 3. Corpus Boundary

| Corpus | Host | Content type | Mutable? | Notes |
| --- | --- | --- | --- | --- |
| Magento | `localhost:7770` | product pages, reviews | no |  |
| Postmill | `localhost:9999` | posts, comments | no |  |
| Kiwix | `localhost:8090` | offline Wikipedia | no |  |

## 4. Task Splits

| Split | Path | Count | Purpose | Public? |
| --- | --- | --- | --- | --- |
| RL train | `data/tasks/deep_research/rl/` |  | training curriculum |  |
| Public leaderboard |  |  | external comparison |  |
| Held-out |  |  | final evaluation |  |

## 5. Task Schema

List required fields:

- `task_id`
- `intent`
- `sites`
- `markdown_spec`
- `citation_policy`
- `url_coverage`
- `golden`
- `acquisition`
- optional `execution_goal`

## 6. Golden Data

- Golden source:
- Generation method:
- Human review:
- URL live validation date:
- Known 404 or repoint notes:

## 7. Scoring

| Dimension | Weight | Verifier | Deterministic? |
| --- | --- | --- | --- |
| coverage |  |  |  |
| citation / grounding |  |  |  |
| source_diversity |  |  |  |
| perspective_balance |  |  |  |
| longform_quality |  |  |  |
| checklist |  |  |  |
| state_diff | opt-in | `StateDiffVerifier` | yes |

## 8. Baselines

| Agent | Model | Tools | Score | Notes |
| --- | --- | --- | --- | --- |

## 9. Reproducibility

Required services:

- Magento
- Postmill
- Kiwix
- Search shim

Validation commands:

```bash
bash scripts/check_track_a_local.sh import
bash scripts/check_track_a_local.sh track-a
bash scripts/check_track_a_local.sh core
```

## 10. Known Limitations

- Sandbox scope is smaller than the open web.
- URL paths can be case-sensitive.
- Some oracle data may have false negatives before filtered rebuild.
- LLM judge dimensions require calibration against human audit.
- RL training tasks are separate from public leaderboard tasks.

## 11. Change Log

Do not edit `data/changelog.json` for draft benchmark work. Only update the public changelog during an approved release.
