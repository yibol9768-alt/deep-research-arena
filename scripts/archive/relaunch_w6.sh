#!/bin/bash
cd /opt/deep_reserch
LOG=data/results/deep_v3/queue_w6.log
DS_PROXY_URL=http://localhost:8088/v1 \
JUDGE_BASE_URL=http://localhost:8088/v1 \
JUDGE_MODEL=deepseek-v4-flash \
JUDGE_PROVIDER=openai \
JUDGE_API_KEY=anything \
BACKBONE=deepseek-v4-flash \
    setsid nohup bash scripts/run_full_leaderboard.sh data/results/deep_v3/queue_w6.tsv \
    > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "worker 6 relaunched (PID=$PID)"
sleep 3
ps -ef | grep "queue_w6" | grep -v grep | head -2
