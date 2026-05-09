# V2 Validation Runbook

When this is run successfully, the V2 pipeline is locked in and we can
delete the V1 runners + retire `data/results/deep_v3/`. Until then,
V1 + V2 coexist.

## Prerequisites

* `infra/sync_to_westd.sh --apply` succeeded — westd has the V2 code
* Phase 7 smoke tests passed (`pytest tests/test_baselines_smoke.py
  tests/test_v2_wrappers.py` → green on Mac)
* Phase 8-D image build passed — westd `docker compose up` brings
  the sandbox up cleanly
* westd's existing per-framework venvs (`.venv-camel`, `.venv-storm`,
  `.venv-ldr312`, `.venv-qx`, `.venv-tongyi`, `.venv-ii`, `.venv-langchain-odr`,
  `.venv-gptr`, `.venv-smol`) are intact

## Step 1 — snapshot V1

```bash
ssh my5090 'wsl -d Ubuntu -- bash -lc "
  cd /opt/deep_reserch
  python3 scripts/migrate_validate.py --snapshot-v1
"'
```

Output: `data/results/LEADERBOARD_DEEP_v1_snapshot.json` is committed
locally and shows the per-agent V1 Elo. Don't proceed unless this
matches what's in `data/results/deep_v3/LEADERBOARD_DEEP.md`.

## Step 2 — re-run all 10 agents through V2

Long job (~6-8 h). Run it as a Windows scheduled task so it survives
SSH drops:

```bash
ssh my5090 'wsl -d Ubuntu -- bash -lc "
  cd /opt/deep_reserch
  nohup python3 scripts/migrate_validate.py --rescore-v2 \
      --tasks 0001-0030 \
      > /tmp/v2_validate.log 2>&1 &
  echo started: PID \$!
"'

# Tail progress
ssh my5090 'wsl -d Ubuntu -- bash -lc "tail -50 /tmp/v2_validate.log"'

# Or use schtasks for true persistence (CLAUDE.md note: WSL long tasks
# can only persist via schtasks /RU liuyibo /IT)
```

Resumable — `migrate_validate.py --rescore-v2` skips any
`(agent, task)` whose score file already exists. If westd reboots, just
re-launch the same command and it picks up.

## Step 3 — diff V2 vs V1

After Step 2 completes (`/tmp/v2_validate.log` ends with summary):

```bash
ssh my5090 'wsl -d Ubuntu -- bash -lc "
  cd /opt/deep_reserch
  python3 scripts/migrate_validate.py --diff
"'
```

Acceptance:
* per-agent V3 Elo |Δ| < 10 vs V1 snapshot — required for green
* per-task per-agent reach drift < 0.05 — flagged if any exceeds
* total composite_v3 drift < 0.02 — flagged if exceeds

If `--diff` exits 0 → V2 is locked in. Proceed to Step 4.

If `--diff` exits non-zero → **STOP**. The V2 path has unmasked a real
issue (or introduced one). Investigate the agent that drifted:

* drift > 0: V2 is scoring it higher → likely fewer false-zeros
  (e.g. ldr's bare URLs now counted). Probably a real fix.
* drift < 0: V2 is scoring it lower → either runner-error filter
  excluded a legit run, or a real V2 regression. Drill into one
  task's score file to see which.

## Step 4 — V1 cleanup

Only after Step 3 passed:

```bash
ssh my5090 'wsl -d Ubuntu -- bash -lc "
  cd /opt/deep_reserch
  # Archive V1 score files (do not delete; we may need them for
  # the paper appendix)
  mv data/results/deep_v3 data/results/deep_v3_archived_$(date +%Y%m%d)
  mv data/results/deep    data/results/deep_archived_$(date +%Y%m%d)

  # Promote V2
  mv data/results/deep_v2 data/results/deep_v3   # leaderboard reads here

  # Retire V1 runners (still in git history)
  git rm -r scripts/runners/                                # archived in git
  # Don't delete scripts/run_deep_task.py — it still serves the harness

  # Rebuild leaderboard from V2 data
  python3 scripts/build_deep_leaderboard.py
"'
```

## Step 5 — paper update

The published leaderboard in `paper/main.tex` references specific
V1 numbers. Generate the V2 numbers:

```bash
# Pull the new LEADERBOARD_DEEP.md to Mac
scp 'my5090:/opt/deep_reserch/data/results/deep_v3/LEADERBOARD_DEEP.md' \
    /Users/liuyibo/Desktop/lyb/deep_reserch/data/results/deep_v3/
```

Diff the markdown against the published version; update the paper's:

* `\section{Leaderboard}` Bradley-Terry table
* `\section{Errors and Limitations}` — drop the "framework-integration
  issues" caveat now that V2 has a clean adapter for every framework
* Cite the new commit SHA at the top of the methodology section

## Common failures + fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `--rescore-v2` hangs on one (agent, task) > 10 min | framework subprocess stuck | kill, mark `*.md.error`, continue |
| All agents drift ~+5 Elo | bare-URL fix recovered citations across the board | expected; verify trend not magnitude |
| One agent drifts > 30 Elo | runner placeholder no longer counted | check `*.md.error` count; was it being scored as 0 in V1? |
| `gateway healthz` 503 | ds_proxy can't reach DEEPSEEK | check `DEEPSEEK_API_KEY` is set in compose env |
| Agent's V2 markdown empty | wrapper detected runner placeholder; old V1 was scoring it | verify what the underlying runner actually returned |

## Estimated wallclock

* Step 1 (snapshot): 30s
* Step 2 (rescore): 6-8h (parallelism limited by gateway throughput
  ~3-5 LLM calls/sec)
* Step 3 (diff): 30s
* Step 4 (cleanup): 5 min
* Step 5 (paper update): 1-2 hours of editing

Total: 1 working day, mostly waiting on Step 2.
