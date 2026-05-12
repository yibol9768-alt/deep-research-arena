#!/bin/bash
# Halt bulk + ds_proxy_lm, install patched ds_proxy/app.py (preserves
# reasoning_content so judge_client auto-retries with 8192 tokens when
# Qwen's CoT eats the whole max_tokens budget). Delete the bad deerflow
# 0001 score so it gets re-scored under the new proxy.
set -e
cd /opt/deep_reserch

echo "=== halting ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
pkill -f "uvicorn.*ds_proxy.*8089" 2>/dev/null || true
sleep 4

echo "=== installing patched ds_proxy/app.py ==="
cp /mnt/d/lyb/deep_reserch/integrations/ds_proxy/app.py integrations/ds_proxy/app.py
.venv-camel/bin/python -c "import ast; ast.parse(open('integrations/ds_proxy/app.py').read()); print('syntax OK')"

echo
echo "=== restarting ds_proxy_lm ==="
LM_PORT=8089
LM_LOG=/tmp/ds_proxy_lm.log
OPENAI_PROXY_UPSTREAM=http://172.30.48.1:1234/v1 \
OPENAI_PROXY_KEY=lmstudio \
OPENAI_PROXY_REWRITE_MODEL=qwen3.5-27b \
OPENAI_PROXY_THINKING_DISABLED=0 \
OPENAI_PROXY_STRIP_THINKING=1 \
OPENAI_PROXY_MIN_MAX_TOKENS=0 \
nohup .venv-camel/bin/uvicorn integrations.ds_proxy.app:app \
    --host 0.0.0.0 --port $LM_PORT --log-level warning \
    > $LM_LOG 2>&1 < /dev/null &
disown $! 2>/dev/null || true
echo "ds_proxy_lm PID=$!"
sleep 4

echo
echo "=== probing patched proxy ==="
.venv-camel/bin/python - <<'PYEOF'
import json, urllib.request
body = json.dumps({
    "model": "deepseek-v4-flash",
    "messages":[{"role":"user","content":'Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,   # too small, should produce empty content + reasoning
}).encode()
req = urllib.request.Request("http://localhost:8089/v1/chat/completions", data=body,
    headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=120)
d = json.loads(r.read())
msg = d["choices"][0]["message"]
print("content     :", repr(msg.get("content"))[:120])
print("reasoning_content present:", "reasoning_content" in msg)
print("reasoning_content head   :", repr((msg.get("reasoning_content") or "")[:200]))
PYEOF

echo
echo "=== deleting bad deerflow 0001 score (was scored before patch) ==="
rm -f data/results/deep_v3/deerflow__dr_cross_deep_0001_matrix.score.json
.venv-camel/bin/python scripts/plan_full_leaderboard.py \
    --agents deerflow flowsearcher-ds gpt-researcher ii-researcher langchain-odr ldr qx-agents smolagents storm \
    --task-range 1-57 \
    --out data/results/deep_v3/run_queue.tsv
echo "queue: $(wc -l < data/results/deep_v3/run_queue.tsv) pairs"

echo
echo "=== rotating log + relaunching ==="
mv data/results/deep_v3/run_full_leaderboard.log data/results/deep_v3/run_full_leaderboard.log.preretry.bak 2>/dev/null || true

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
echo "=== first 25 lines of new log ==="
head -25 data/results/deep_v3/run_full_leaderboard.log
