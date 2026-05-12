#!/bin/bash
# Start ds_proxy_lm pointed at the now-loaded qwen3.5-27b, verify it
# produces clean output (no Thinking-Process preamble), and relaunch the
# bulk run with judges + agents BOTH using 27b on the 5090.
set -e
cd /opt/deep_reserch

LM_GW=${LM_STUDIO_GATEWAY:-172.30.48.1}
LM_MODEL=${LM_STUDIO_MODEL:-qwen3.5-27b}
LM_PORT=${LM_PROXY_PORT:-8089}
LM_LOG=/tmp/ds_proxy_lm.log

echo "=== ensuring previous ds_proxy_lm is gone ==="
pkill -f "uvicorn.*ds_proxy.*$LM_PORT" 2>/dev/null || true
sleep 1

echo "=== launching ds_proxy_lm -> $LM_GW:1234, rewrite to $LM_MODEL ==="
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
echo "ds_proxy_lm PID=$LM_PID (port $LM_PORT)"
sleep 4

echo
echo "=== probe 27b for thinking-prefix bug ==="
.venv-camel/bin/python3 - <<'PYEOF'
import json, urllib.request
body = json.dumps({
    "model": "deepseek-v4-flash",  # ds_proxy_lm rewrites to qwen3.5-27b
    "messages": [{"role":"user","content":'Output exactly the string {"answer":"yes"} and nothing else.'}],
    "temperature": 0,
    "max_tokens": 32,
}).encode()
req = urllib.request.Request("http://localhost:8089/v1/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer lm"})
r = urllib.request.urlopen(req, timeout=60)
d = json.loads(r.read())
content = d["choices"][0]["message"]["content"]
print("len:", len(content))
print("--- response ---")
print(content)
print("--- /response ---")
if "Thinking Process" in content[:80]:
    print("\n[ALERT] still has Thinking Process preamble. judges will fail.")
else:
    print("\n[OK] clean response, judges should be fine.")
PYEOF

echo
echo "=== relaunching bulk run (agent + judge both on 27b) ==="
QUEUE=data/results/deep_v3/run_queue.tsv
LOG=data/results/deep_v3/run_full_leaderboard.log
[ -f "$LOG" ] && mv "$LOG" "${LOG}.lmstudio35a3b_$(date +%s).bak" 2>/dev/null || true

DS_PROXY_URL=http://localhost:$LM_PORT/v1 \
JUDGE_BASE_URL=http://localhost:$LM_PORT/v1 \
JUDGE_MODEL=$LM_MODEL \
BACKBONE=$LM_MODEL \
nohup bash scripts/run_full_leaderboard.sh "$QUEUE" > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "bulk PID=$PID"
sleep 5
echo "=== first 25 lines of new log ==="
head -25 "$LOG"
