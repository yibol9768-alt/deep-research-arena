#!/bin/bash
# Halt bulk run, delete the polluted camel-ai 0044 score, relaunch with
# JUDGE_PROVIDER=openai so judges actually go through ds_proxy_lm instead
# of crashing on missing anthropic SDK.
set -e
cd /opt/deep_reserch

echo "=== halting ==="
pkill -f run_full_leaderboard.sh 2>/dev/null || true
pkill -f scripts/run_deep_task.py 2>/dev/null || true
sleep 3

echo "=== removing bad score files (anthropic judge_error) ==="
.venv-camel/bin/python3 - <<'PYEOF'
import json, os, glob
removed = 0
for f in glob.glob("data/results/deep_v3/*_matrix.score.json"):
    try:
        d = json.loads(open(f, encoding='utf-8').read())
    except Exception:
        continue
    err = ((d.get("checklist") or {}).get("judge_error") or "").lower()
    if "anthropic" in err:
        # Also remove the matching report so the runner re-fetches it.
        # Keep it in deep/ as the agent's actual report; only delete the
        # bad score JSON in deep_v3/.
        os.remove(f)
        removed += 1
print(f"removed {removed} score files with anthropic judge_error")
PYEOF

echo "=== rotating log ==="
mv data/results/deep_v3/run_full_leaderboard.log data/results/deep_v3/run_full_leaderboard.log.anthropic.bak 2>/dev/null || true

echo "=== regenerating queue (now with the 48 freshly-deleted pairs back in) ==="
.venv-camel/bin/python3 scripts/plan_full_leaderboard.py --task-range 1-57 --out data/results/deep_v3/run_queue.tsv
wc -l data/results/deep_v3/run_queue.tsv

echo "=== relaunching with JUDGE_PROVIDER=openai ==="
LOG=data/results/deep_v3/run_full_leaderboard.log
DS_PROXY_URL=http://localhost:8089/v1 \
JUDGE_BASE_URL=http://localhost:8089/v1 \
JUDGE_MODEL=qwen3.5-27b \
JUDGE_PROVIDER=openai \
JUDGE_API_KEY=lmstudio \
BACKBONE=qwen3.5-27b \
nohup bash scripts/run_full_leaderboard.sh data/results/deep_v3/run_queue.tsv > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "bulk PID=$PID"
sleep 5
echo "=== first 30 lines of new log ==="
head -30 "$LOG"
