#!/bin/bash
# Relaunch the 226-pair bulk run with agent traffic routed to LM Studio
# (port 8089) and judge traffic still going to DeepSeek (port 8088).
set -e
cd /opt/deep_reserch

QUEUE=data/results/deep_v3/run_queue.tsv
LOG=data/results/deep_v3/run_full_leaderboard.log

echo "=== ports ==="
curl -s --max-time 3 -o /dev/null -w "lm-studio-proxy(8089): %{http_code}\n" -X POST http://localhost:8089/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"OK"}],"max_tokens":4}' || true
curl -s --max-time 3 -o /dev/null -w "deepseek-proxy(8088): %{http_code}\n" -X POST http://localhost:8088/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"OK"}],"max_tokens":4}' || true
echo

echo "=== rotating log ==="
[ -f "$LOG" ] && mv "$LOG" "${LOG}.deepseek_2026-05-09.bak"
echo

echo "=== launching with DS_PROXY_URL=:8089 (LM Studio), JUDGE_BASE_URL=:8088 (DeepSeek) ==="
DS_PROXY_URL=http://localhost:8089/v1 \
JUDGE_BASE_URL=http://localhost:8088/v1 \
JUDGE_MODEL=deepseek-v4-flash \
BACKBONE=deepseek-v4-flash \
nohup bash scripts/run_full_leaderboard.sh "$QUEUE" > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "PID=$PID"
sleep 6
echo "=== first 25 lines of new log ==="
head -25 "$LOG"
