#!/bin/bash
# Phase 5 driver: run 5 agents × 10 tasks sequentially on westd.
# Keeps a per-run log; skips (agent, task) combinations already completed.
#
# Runs on westd (WSL Ubuntu) — agent venvs + sandbox + ds_proxy must be up.

set -u
exec > /tmp/deep_matrix.log 2>&1
cd /opt/deep_reserch

AGENTS=(${AGENTS:-gpt-researcher smolagents camel-ai langchain-odr storm})
TASKS=(${TASKS:-dr_cross_deep_0001 dr_cross_deep_0002 dr_cross_deep_0003 dr_cross_deep_0004 dr_cross_deep_0005 dr_cross_deep_0006 dr_cross_deep_0007 dr_cross_deep_0008 dr_cross_deep_0009 dr_cross_deep_0010})

total=0
skipped=0
completed=0
failed=0
started=$(date +%s)

for AGENT in "${AGENTS[@]}"; do
  for TASK in "${TASKS[@]}"; do
    total=$((total+1))
    OUT=data/results/deep/${AGENT}__${TASK}_matrix.md
    if [ -f "$OUT" ] && [ $(wc -c < "$OUT") -gt 3000 ]; then
      echo "[$total] skip ${AGENT} × ${TASK} (already done, $(wc -c < $OUT) chars)"
      skipped=$((skipped+1))
      continue
    fi
    if [ ! -f "data/tasks/deep_research/cross_site_deep/${TASK}.json" ]; then
      echo "[$total] skip ${AGENT} × ${TASK} — no task spec"
      skipped=$((skipped+1))
      continue
    fi
    echo
    echo "========================================"
    echo "[$total] ${AGENT} × ${TASK} — begin $(date +%H:%M:%S)"
    echo "========================================"
    AGENT="$AGENT" TASK="$TASK" SUFFIX=matrix \
      bash scripts/smoke_deep_oneagent.sh 2>&1 | tail -40
    if [ -f "$OUT" ] && [ $(wc -c < "$OUT") -gt 3000 ]; then
      completed=$((completed+1))
      echo "[$total] ${AGENT} × ${TASK} OK"
    else
      failed=$((failed+1))
      echo "[$total] ${AGENT} × ${TASK} FAILED"
    fi
    elapsed=$(( $(date +%s) - started ))
    echo "-- elapsed ${elapsed}s | done ${completed}/${total} | skipped ${skipped} | failed ${failed}"
  done
done

echo
echo "===================================="
echo "MATRIX DONE  total=${total}  completed=${completed}  skipped=${skipped}  failed=${failed}"
echo "wall=$(( $(date +%s) - started ))s"
echo "===================================="
