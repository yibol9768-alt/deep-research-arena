#!/bin/bash
# Halt the bulk run, start a second ds_proxy on port 8089 forwarding to
# the local LM Studio (Qwen3.5-35b-a3b on the 5090), and update the
# bulk runner to send agent traffic to 8089. Judges keep going to 8088
# (DeepSeek cloud), per CLAUDE.md "judge MUST use DeepSeek-V4 flash".
#
# Idempotent: re-running re-stops/relaunches the LM-Studio proxy.
set -e
cd /opt/deep_reserch

LM_GW=${LM_STUDIO_GATEWAY:-172.30.48.1}
LM_MODEL=${LM_STUDIO_MODEL:-qwen3.5-35b-a3b}
LM_PORT=${LM_PROXY_PORT:-8089}
LM_LOG=/tmp/ds_proxy_lm.log

echo "=== halting current bulk run ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
sleep 2
ps -ef | awk '/run_full|run_deep_task/ && !/awk/ {print}' | head -5
echo

echo "=== stopping any prior ds_proxy_lm on port $LM_PORT ==="
pkill -f "uvicorn.*ds_proxy.*$LM_PORT" 2>/dev/null || true
sleep 1

echo "=== launching ds_proxy_lm -> http://$LM_GW:1234/v1 on port $LM_PORT ==="
OPENAI_PROXY_UPSTREAM="http://$LM_GW:1234/v1" \
OPENAI_PROXY_KEY="lmstudio" \
OPENAI_PROXY_REWRITE_MODEL="$LM_MODEL" \
OPENAI_PROXY_THINKING_DISABLED="0" \
OPENAI_PROXY_STRIP_THINKING="1" \
nohup .venv-camel/bin/uvicorn integrations.ds_proxy.app:app \
    --host 0.0.0.0 --port "$LM_PORT" --log-level warning \
    > "$LM_LOG" 2>&1 < /dev/null &
LM_PID=$!
disown $LM_PID 2>/dev/null || true
echo "ds_proxy_lm PID=$LM_PID"
sleep 4

echo
echo "=== verifying ds_proxy_lm is up ==="
curl -s --max-time 30 -o /tmp/lm_proxy_resp.json -w "HTTP %{http_code} time %{time_total}s\n" \
    -X POST "http://localhost:$LM_PORT/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"reply with exactly OK"}],"temperature":0,"max_tokens":24}'
echo "  body sample:"
head -c 400 /tmp/lm_proxy_resp.json
echo
echo
echo "ds_proxy_lm log tail:"
tail -10 "$LM_LOG" 2>&1 || true
echo
echo "DONE. Port $LM_PORT now translates deepseek-v4-flash -> qwen3.5-35b-a3b on the 5090."
echo "Resume bulk run with:  bash scripts/run_full_leaderboard.sh data/results/deep_v3/run_queue.tsv"
echo "Required env to flip the bulk runner to LM Studio:"
echo "  DS_PROXY_URL=http://localhost:$LM_PORT/v1"
echo "  JUDGE_BASE_URL=http://localhost:8088/v1   # unchanged, judges still on DeepSeek"
echo "  BACKBONE=deepseek-v4-flash                # ds_proxy_lm rewrites to qwen3.5"
