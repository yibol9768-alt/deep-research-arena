# DR-Arena web app

A minimal FastAPI portal that serves the deep-research leaderboard, runs the
smoke test on demand, and proxies chat completions to a local LM Studio so a
user with a 5090 box can host the whole stack on one machine without any cloud
key.

## Run

```bash
# from repo root
pip install -r web/requirements.txt
python -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
# or just:
python web/server.py
```

Then open <http://localhost:8000>.

## Pages

| Route | What it does |
|---|---|
| `/` | Leaderboard: featured cards, composite_v2 + v1 Elo tables, per-pillar Elo, audit trail |
| `/agent/<name>` | Per-task scores + per-pillar Elo + score-file accounting for one agent |
| `/add` | Drop-in guide for adding a new DR runner (registry contract) |
| `/smoke` | Run `scripts/smoke_test_drs.py` against LM Studio + see the latest report inline |
| `/playground` | Direct chat with the LM Studio backbone (sanity check) |
| `/api/leaderboard` | Raw JSON the page reads |
| `/api/health` | LM Studio liveness ping (drives the green/red pill in the nav bar) |
| `/api/chat` | Proxies `POST /v1/chat/completions` |
| `/api/smoke` | Spawns the smoke runner |

## Environment

| Var | Default |
|---|---|
| `LM_STUDIO_URL` | `http://127.0.0.1:1234/v1` |
| `LM_STUDIO_MODEL` | `qwen3.5-35b-a3b` |
| `DEEP_RESULTS_DIR` | `deep_v3` |

## Data flow

```
data/results/deep_v3/<agent>__<task>_matrix.score.json
        │
        ▼
scripts/build_deep_leaderboard.py  (Bradley-Terry MLE + bootstrap CIs)
        │
        ▼
data/results/deep_v3/leaderboard_deep.json
        │
        ▼
web/server.py  →  Jinja2 templates  →  browser
```

The web app does **not** mutate score files or the leaderboard JSON; rebuild
the leaderboard with `python scripts/build_deep_leaderboard.py` after you add
new runs.
