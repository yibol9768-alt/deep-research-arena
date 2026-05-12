#!/bin/bash
# Wrapper that nohup-launches run_full_leaderboard.sh and prints the PID.
# Avoids the bash-quoting hell when wsl.exe is the entry point.
set -e
cd /opt/deep_reserch
QUEUE=${1:-data/results/deep_v3/run_queue.tsv}
LOG=data/results/deep_v3/run_full_leaderboard.log

nohup bash scripts/run_full_leaderboard.sh "$QUEUE" > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "PID=$PID"
echo "LOG=$LOG"
sleep 4
echo "---first 30 lines of log---"
head -30 "$LOG" 2>&1 || true
