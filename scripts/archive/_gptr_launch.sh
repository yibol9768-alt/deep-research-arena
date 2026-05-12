#!/bin/bash
# One-shot launcher for the gpt-researcher bulk worker over all 57 pairs.
set -uo pipefail
cd /opt/deep_reserch

DEEP_DIR=data/results/deep_v3
mkdir -p "$DEEP_DIR"

QUEUE=$DEEP_DIR/queue_gptr.tsv
> "$QUEUE"
for n in $(seq -w 1 57); do
  printf 'gpt-researcher\tdr_cross_deep_00%s\n' "$n" >> "$QUEUE"
done
echo "queue written: $QUEUE ($(wc -l < "$QUEUE") pairs)"

LOG=$DEEP_DIR/queue_gptr.log
DS_PROXY_URL=http://localhost:8088/v1 \
JUDGE_BASE_URL=http://localhost:8088/v1 \
JUDGE_MODEL=deepseek-v4-flash \
JUDGE_PROVIDER=openai \
JUDGE_API_KEY=anything \
BACKBONE=deepseek-v4-flash \
    setsid nohup bash scripts/run_full_leaderboard.sh "$QUEUE" \
    > "$LOG" 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null || true
echo "gpt-researcher worker launched (PID=$PID, log=$LOG)"
sleep 2
if kill -0 $PID 2>/dev/null; then
    echo "worker alive after 2s"
else
    echo "WARN: worker died within 2s — check log"
fi
