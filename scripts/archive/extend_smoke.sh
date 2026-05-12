#!/bin/bash
# Add 3 more tasks (0010, 0020, 0030) per newly-added agent so each
# reaches 5 sampled pairs.
set -e
cd /opt/deep_reserch
DIR=data/results/deep_v3
QUEUE=$DIR/queue_smoke_ext.tsv

> "$QUEUE"
for agent in camel-ai tongyi-dr co-storm local-deep-researcher dzhng deepagents; do
    for task in dr_cross_deep_0010 dr_cross_deep_0020 dr_cross_deep_0030; do
        score=$DIR/${agent}__${task}_matrix.score.json
        if [ ! -f "$score" ]; then
            printf '%s\t%s\n' "$agent" "$task" >> "$QUEUE"
        fi
    done
done

echo "=== queued ==="
cat "$QUEUE"
echo

# Launch as a single setsid'd worker (we already have 6 other workers running).
LOG=$DIR/queue_smoke_ext.log
DS_PROXY_URL=http://localhost:8088/v1 \
JUDGE_BASE_URL=http://localhost:8088/v1 \
JUDGE_MODEL=deepseek-v4-flash \
JUDGE_PROVIDER=openai \
JUDGE_API_KEY=anything \
BACKBONE=deepseek-v4-flash \
    setsid nohup bash scripts/run_full_leaderboard.sh "$QUEUE" \
    > "$LOG" 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 3
echo "extension worker launched (log: $LOG)"
ps -ef | grep "$(basename $QUEUE)" | grep -v grep | head -2
