#!/bin/bash
# Sync files we just modified on Windows over to /opt/deep_reserch in WSL.
# Idempotent — re-run any time after editing on the Windows side.
set -e
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch

FILES=(
    scripts/audit_dr_scores.py
    scripts/build_deep_leaderboard.py
    scripts/run_deep_task.py
    scripts/smoke_test_drs.py
    scripts/runners/__init__.py
    scripts/runners/registry.py
    scripts/runners/costorm_runner.py
    scripts/runners/deepagents_runner.py
    scripts/runners/deerflow_runner.py
    scripts/runners/ldr_runner.py
    scripts/runners/local_deep_researcher_runner.py
    scripts/runners/qx_runner.py
    scripts/runners/storm_runner.py
    scripts/runners/tongyi_runner.py
    web/server.py
    web/requirements.txt
    web/README.md
    web/templates/base.html
    web/templates/index.html
    web/templates/agent.html
    web/templates/add.html
    web/templates/smoke.html
    web/templates/playground.html
    web/templates/audit.html
)
for f in "${FILES[@]}"; do
    mkdir -p "$(dirname "$DST/$f")"
    tr -d '\r' < "$SRC/$f" > "$DST/$f"
done
echo "synced ${#FILES[@]} files"
