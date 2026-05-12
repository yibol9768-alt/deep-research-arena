#!/bin/bash
# Drop the 2048 max-tokens floor in ds_proxy_lm. Judges already pass
# max_tokens=1500 themselves and auto-retry at 8192 if empty. Adding a 2048
# floor on agent traffic just bloats every short tool-call into a multi-
# second wait, and camel-ai sends 20+ such calls per pair.
set -e
cd /opt/deep_reserch

LM_GW=${LM_STUDIO_GATEWAY:-172.30.48.1}
LM_PORT=${LM_PROXY_PORT:-8089}
LM_LOG=/tmp/ds_proxy_lm.log

echo "=== halting bulk + ds_proxy_lm ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
pkill -f "uvicorn.*ds_proxy.*$LM_PORT" 2>/dev/null || true
sleep 3

echo "=== restarting ds_proxy_lm with MIN_MAX_TOKENS=0 ==="
OPENAI_PROXY_UPSTREAM="http://$LM_GW:1234/v1" \
OPENAI_PROXY_KEY="lmstudio" \
OPENAI_PROXY_REWRITE_MODEL="qwen3.5-27b" \
OPENAI_PROXY_THINKING_DISABLED="0" \
OPENAI_PROXY_STRIP_THINKING="1" \
OPENAI_PROXY_MIN_MAX_TOKENS="0" \
nohup .venv-camel/bin/uvicorn integrations.ds_proxy.app:app \
    --host 0.0.0.0 --port "$LM_PORT" --log-level warning \
    > "$LM_LOG" 2>&1 < /dev/null &
disown $! 2>/dev/null || true
echo "ds_proxy_lm PID=$!"
sleep 3

echo "=== rotating run log + relaunching ==="
mv data/results/deep_v3/run_full_leaderboard.log data/results/deep_v3/run_full_leaderboard.log.slow.bak 2>/dev/null || true

DS_PROXY_URL=http://localhost:$LM_PORT/v1 \
JUDGE_BASE_URL=http://localhost:$LM_PORT/v1 \
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
