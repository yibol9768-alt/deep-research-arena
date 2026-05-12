#!/bin/bash
# After patching ds_proxy app.py with thinking-strip + min-max-tokens:
# halt bulk run + ds_proxy_lm, restart proxy with the patch + 27b config,
# probe to confirm thinking is stripped, relaunch bulk.
set -e
cd /opt/deep_reserch

echo "=== halting running processes ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
pkill -f "uvicorn.*ds_proxy.*8089" 2>/dev/null || true
sleep 3

echo "=== launching patched ds_proxy_lm with MIN_MAX_TOKENS=2048 ==="
LM_GW=${LM_STUDIO_GATEWAY:-172.30.48.1}
LM_PORT=${LM_PROXY_PORT:-8089}
LM_LOG=/tmp/ds_proxy_lm.log

OPENAI_PROXY_UPSTREAM="http://$LM_GW:1234/v1" \
OPENAI_PROXY_KEY="lmstudio" \
OPENAI_PROXY_REWRITE_MODEL="qwen3.5-27b" \
OPENAI_PROXY_THINKING_DISABLED="0" \
OPENAI_PROXY_STRIP_THINKING="1" \
OPENAI_PROXY_MIN_MAX_TOKENS="2048" \
nohup .venv-camel/bin/uvicorn integrations.ds_proxy.app:app \
    --host 0.0.0.0 --port "$LM_PORT" --log-level warning \
    > "$LM_LOG" 2>&1 < /dev/null &
LM_PID=$!
disown $LM_PID 2>/dev/null || true
echo "ds_proxy_lm PID=$LM_PID"
sleep 4

echo
echo "=== probe: thinking strip + min tokens ==="
.venv-camel/bin/python3 - <<'PYEOF'
import json, urllib.request
body = json.dumps({
    "model": "deepseek-v4-flash",
    "messages": [{"role":"user","content":'Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,  # caller asks for 60; proxy should bump to 2048
}).encode()
req = urllib.request.Request("http://localhost:8089/v1/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
import time; t0=time.time()
r = urllib.request.urlopen(req, timeout=120)
content = json.loads(r.read())["choices"][0]["message"]["content"]
print(f"latency: {time.time()-t0:.1f}s  len={len(content)}")
print("--- response ---")
print(content)
print("--- /response ---")
clean = "Thinking Process" not in content and "<think>" not in content
print(f"[{'OK' if clean else 'BAD'}] thinking {'stripped' if clean else 'leaked'}")
PYEOF

echo
echo "=== relaunching bulk run (judges + agents both on 27b) ==="
QUEUE=data/results/deep_v3/run_queue.tsv
LOG=data/results/deep_v3/run_full_leaderboard.log
[ -f "$LOG" ] && mv "$LOG" "${LOG}.thinking_bug_$(date +%s).bak" 2>/dev/null || true

DS_PROXY_URL=http://localhost:$LM_PORT/v1 \
JUDGE_BASE_URL=http://localhost:$LM_PORT/v1 \
JUDGE_MODEL=qwen3.5-27b \
BACKBONE=qwen3.5-27b \
nohup bash scripts/run_full_leaderboard.sh "$QUEUE" > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "bulk PID=$PID"
sleep 6
echo
echo "=== first 30 lines of new log ==="
head -30 "$LOG"
