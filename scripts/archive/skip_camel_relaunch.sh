#!/bin/bash
# camel-ai hangs on Qwen3.5-27b (no LLM calls after some point, GPU drops to
# idle, agent process consumes 0% CPU). Likely a tool-calling format the
# agent expects but Qwen doesn't return. Skip camel-ai for the Qwen run;
# revisit later. Also delete any stale OLD reports for camel-ai/0001 in
# data/results/deep/ so the bulk script doesn't accidentally score them.
set -e
cd /opt/deep_reserch

echo "=== halting bulk + run_deep_task ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
pkill -f scripts/score_deep_answer.py 2>/dev/null || true
sleep 4

echo "=== regenerating queue WITHOUT camel-ai ==="
.venv-camel/bin/python scripts/plan_full_leaderboard.py \
    --agents deerflow flowsearcher-ds gpt-researcher ii-researcher langchain-odr ldr qx-agents smolagents storm \
    --task-range 1-57 \
    --out data/results/deep_v3/run_queue.tsv
wc -l data/results/deep_v3/run_queue.tsv

echo
echo "=== rotating log ==="
mv data/results/deep_v3/run_full_leaderboard.log data/results/deep_v3/run_full_leaderboard.log.camel_hang.bak 2>/dev/null || true

echo
echo "=== relaunching ==="
DS_PROXY_URL=http://localhost:8089/v1 \
JUDGE_BASE_URL=http://localhost:8089/v1 \
JUDGE_MODEL=qwen3.5-27b \
JUDGE_PROVIDER=openai \
JUDGE_API_KEY=lmstudio \
BACKBONE=qwen3.5-27b \
nohup bash scripts/run_full_leaderboard.sh data/results/deep_v3/run_queue.tsv \
    > data/results/deep_v3/run_full_leaderboard.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
echo "bulk PID=$!"
sleep 5
echo
echo "=== first 25 lines of new log ==="
head -25 data/results/deep_v3/run_full_leaderboard.log
