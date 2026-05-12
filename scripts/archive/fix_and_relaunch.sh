#!/bin/bash
# Kill any in-flight run_full_leaderboard.sh, strip CRLF from the queue,
# wipe partial logs, and re-launch detached.
set -e
cd /opt/deep_reserch

QUEUE=data/results/deep_v3/run_queue.tsv
LOG=data/results/deep_v3/run_full_leaderboard.log

echo "=== killing existing runs ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
sleep 2
ps -ef | awk '/run_full_leaderboard|run_deep_task/ && !/awk/ {print}' | head -5
echo

echo "=== stripping CRLF from queue ==="
tr -d '\r' < "$QUEUE" > /tmp/q.tsv
mv /tmp/q.tsv "$QUEUE"
echo "queue line 1 (od):"
head -1 "$QUEUE" | od -c | head -2
echo "wc -l: $(wc -l < "$QUEUE")"
echo

echo "=== wiping previous log + progress + errors ==="
rm -f "$LOG" data/results/deep_v3/run_full_leaderboard.progress data/results/deep_v3/run_full_leaderboard.errors
echo

echo "=== relaunching detached ==="
nohup bash scripts/run_full_leaderboard.sh "$QUEUE" > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "PID=$PID"
sleep 6
echo
echo "=== first 25 lines of new log ==="
head -25 "$LOG"
