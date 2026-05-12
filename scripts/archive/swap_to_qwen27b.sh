#!/bin/bash
# Halt bulk run, ask the LM Studio user to unload 35b-a3b + load 27b,
# wait, then verify the swap and relaunch the bulk run with 27b for both
# agents AND judges.
#
# (lms unload + load are run from Windows PowerShell, not WSL.)
set -e
cd /opt/deep_reserch

echo "=== halting current bulk run ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
sleep 3
ps -ef | awk '/run_full|run_deep_task/ && !/awk/ {print}' | head -5

echo
echo "=== stopping ds_proxy_lm (port 8089) ==="
pkill -f "uvicorn.*ds_proxy.*8089" 2>/dev/null || true
sleep 1

echo
echo "Run from Windows PowerShell (model swap):"
echo "  & \"\$env:USERPROFILE\\.lmstudio\\bin\\lms.exe\" unload qwen3.5-35b-a3b"
echo "  & \"\$env:USERPROFILE\\.lmstudio\\bin\\lms.exe\" load qwen3.5-27b --gpu 1.0 --context-length 32768"
echo
echo "After the swap completes, run scripts/relaunch_qwen27b.sh"
