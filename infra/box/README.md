# infra/box — my5090 box-side ops + build scripts (version-controlled snapshot)

These are point-in-time snapshots (2026-06-09) of the operational and
board-build scripts that live on the my5090 box under `/opt/deep_reserch/.dra_tmp/`.
They are committed here so they survive a box wipe (the WSL sandbox is volatile
and `.dra_tmp/` is not otherwise backed up).

## Important caveats

- **Paths are box-absolute.** Several scripts hardcode `/opt/deep_reserch/` and
  `sys.path.insert(0, "/opt/deep_reserch")`. To run a build script on another
  machine, substitute the repo root (e.g. `sed "s#/opt/deep_reserch/#$(pwd)/#g"`).
- **Secrets scrubbed.** The `run_eff*.sh` / `run_jury*.sh` / `rejudge_models.sh`
  drivers originally hardcoded a DashScope key. That key was replaced with
  `${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}` before committing. Export
  the key in your shell before running; never re-add it to these files.
- These are a **snapshot, not a maintained package.** The authoritative runtime
  copy is on the box. Re-pull if the box versions change.

## What's here (by purpose)

Self-heal / sandbox ops:
- `boot.sh`, `watchdog.sh`, `dra_supervisor.sh`, `keeper.sh` — keep the box and
  sandbox alive across WSL/SSH teardown (see memory `my5090-detached-proc-kill`).
- `sandbox_fix.sh`, `sb_health.sh`, `status_reporter.sh`, `jury_status.sh` — health
  probes + status reporting.

Board / repro build pipeline (reproduces the committed board JSONs):
- `build_model_board.py` — builds `data/results/deep_v3/leaderboard_models_v3.json`
  from `data/results/real/leaderboard_jury_models.json.battles.jsonl` +
  `grounding_uniform2.json`. Verified to rebuild the deployed model board
  byte-identical (8 models, 24 tasks, 643 battles) on 2026-06-09.
- `build_gated_boards.py`, `count_clean.py`, `run_grounding.sh` — gated-board
  assembly, jury clean-count verification, grounding cache+score runner.

Jury / scoring run drivers:
- `run_jury.sh`, `run_juries.sh`, `run_elo.sh`, `run_elo3.sh`, `rejudge_models.sh`,
  `rescore_driver.sh`, `run_rescore.sh`, `run_pres.sh` — drive judge/jury/scoring
  passes on the box. Most need a funded judge API key (see task #45).
- `run_cc_batch.sh`, `run_oc_batch.sh`, `run_eff*.sh`, `run_dsq.sh` — per-agent /
  per-backbone batch runners.

The note in the repo-root `docs/PROJECT_STATUS_2026-06-09.md` (section 6) tracks
which of these still depend on a live box or a funded judge API.
