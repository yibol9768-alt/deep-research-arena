#!/bin/bash
# Auto-retry SCORE-FAILED pairs from the bulk run. Polls the errors log
# every 60s. For each pair without a score JSON in deep_v3/, attempts a
# fresh score once the main bulk has moved on (signal: errors log shows
# the next SCORE-FAILED is at least one pair past it, OR no entry has
# been added in the last 5 min).

set -u
cd /opt/deep_reserch

ERRORS=data/results/deep_v3/run_full_leaderboard.errors
RETRY_LOG=data/results/deep_v3/auto_retry.log
DONE_FILE=/tmp/auto_retry_done.list
mkdir -p "$(dirname "$RETRY_LOG")"
touch "$RETRY_LOG" "$DONE_FILE"

while true; do
    if [ -f "$ERRORS" ]; then
        grep "SCORE-FAILED" "$ERRORS" | while read -r line; do
            # Extract: 2026-05-09 18:40:28  SCORE-FAILED deerflow dr_cross_deep_0004
            agent=$(echo "$line" | awk '{print $4}')
            task=$(echo "$line" | awk '{print $5}')
            [ -z "$agent" ] && continue
            [ -z "$task" ] && continue
            key="${agent}__${task}"
            if grep -q "^$key\$" "$DONE_FILE"; then continue; fi
            score_path="data/results/deep_v3/${agent}__${task}_matrix.score.json"
            report_path="data/results/deep/${agent}__${task}_matrix.md"
            if [ -f "$score_path" ]; then
                echo "$key" >> "$DONE_FILE"
                continue
            fi
            if [ ! -f "$report_path" ]; then
                echo "[$(date '+%H:%M:%S')] $key NO-REPORT (cannot retry)" >> "$RETRY_LOG"
                echo "$key" >> "$DONE_FILE"
                continue
            fi
            echo "[$(date '+%H:%M:%S')] retrying $key" >> "$RETRY_LOG"
            DS_PROXY_URL=http://localhost:8089/v1 \
            JUDGE_BASE_URL=http://localhost:8089/v1 \
            JUDGE_MODEL=qwen3.5-27b \
            JUDGE_PROVIDER=openai \
            JUDGE_API_KEY=lmstudio \
                timeout 1800 .venv-camel/bin/python scripts/score_deep_answer.py \
                --task "$task" --answer "$report_path" --out "$score_path" \
                >> "$RETRY_LOG" 2>&1
            rc=$?
            if [ -f "$score_path" ]; then
                echo "[$(date '+%H:%M:%S')] retry $key SUCCEEDED (rc=$rc)" >> "$RETRY_LOG"
                # emit one stdout line so a Monitor can pick it up
                echo "RETRY-OK   $agent $task"
            else
                echo "[$(date '+%H:%M:%S')] retry $key FAILED (rc=$rc)" >> "$RETRY_LOG"
                echo "RETRY-FAIL $agent $task rc=$rc"
            fi
            echo "$key" >> "$DONE_FILE"
        done
    fi
    sleep 60
done
