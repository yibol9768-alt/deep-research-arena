#!/bin/bash
# Launch N parallel workers on chunks of the run queue. Each worker is a full
# run_full_leaderboard.sh invocation against its own queue chunk + private
# progress/errors files. Score JSONs all land in data/results/deep_v3/ where
# the leaderboard reader picks them up — atomic per (agent, task) so no file
# collision.
#
# Usage:
#   bash parallel_bulk_launch.sh <num_workers> [<queue.tsv>]
#
# The pinned backbone is deepseek-v4-flash via ds_proxy:8088 (thinking off).
set -uo pipefail
cd /opt/deep_reserch

NUM_WORKERS=${1:-4}
QUEUE_SRC=${2:-data/results/deep_v3/run_queue.tsv}
DEEP_DIR=data/results/deep_v3
mkdir -p "$DEEP_DIR"

if [ ! -f "$QUEUE_SRC" ]; then
    echo "ERROR: queue $QUEUE_SRC not found" >&2
    exit 2
fi

# Build a "remaining" queue: pairs without an existing score JSON.
REMAIN=$DEEP_DIR/queue_remaining.tsv
> "$REMAIN"
while IFS=$'\t' read -r AGENT TASK; do
    [ -z "$AGENT" ] && continue
    SCORE=$DEEP_DIR/${AGENT}__${TASK}_matrix.score.json
    [ -f "$SCORE" ] && continue
    printf '%s\t%s\n' "$AGENT" "$TASK" >> "$REMAIN"
done < "$QUEUE_SRC"

REMAIN_N=$(wc -l < "$REMAIN")
echo "remaining pairs: $REMAIN_N (of $(wc -l < "$QUEUE_SRC"))"

if [ "$REMAIN_N" -eq 0 ]; then
    echo "nothing to do — every pair in source queue has a score JSON"
    exit 0
fi

# Shuffle then round-robin split. The source queue is grouped by agent
# (all deerflow first, then all gpt-researcher, etc.). Without shuffling,
# every worker's first ~10 pairs are the same agent, which pile up on the
# per-agent runner lock and serialise the whole bulk. Shuffling interleaves
# agents so workers naturally diversify across runner locks.
SHUFFLED=$DEEP_DIR/queue_shuffled.tsv
shuf "$REMAIN" > "$SHUFFLED"

for w in $(seq 1 "$NUM_WORKERS"); do
    > "$DEEP_DIR/queue_w${w}.tsv"
done
i=0
while IFS= read -r LINE; do
    w=$(( (i % NUM_WORKERS) + 1 ))
    printf '%s\n' "$LINE" >> "$DEEP_DIR/queue_w${w}.tsv"
    i=$((i + 1))
done < "$SHUFFLED"

echo "split into $NUM_WORKERS chunks:"
for w in $(seq 1 "$NUM_WORKERS"); do
    n=$(wc -l < "$DEEP_DIR/queue_w${w}.tsv")
    echo "  worker $w: $n pairs"
done

# Launch all workers in the background, each with its own log file.
# Use ``setsid`` to fully detach — without it, WSL kills the children when
# the parent bash invocation exits (`nohup` alone is not enough under WSL).
for w in $(seq 1 "$NUM_WORKERS"); do
    LOG=$DEEP_DIR/queue_w${w}.log
    DS_PROXY_URL=http://localhost:8088/v1 \
    JUDGE_BASE_URL=http://localhost:8088/v1 \
    JUDGE_MODEL=deepseek-v4-flash \
    JUDGE_PROVIDER=openai \
    JUDGE_API_KEY=anything \
    BACKBONE=deepseek-v4-flash \
        setsid nohup bash scripts/run_full_leaderboard.sh "$DEEP_DIR/queue_w${w}.tsv" \
        > "$LOG" 2>&1 < /dev/null &
    PID=$!
    disown $PID 2>/dev/null || true
    echo "worker $w launched (PID=$PID, log=$LOG)"
done

echo
echo "all $NUM_WORKERS workers running. Tail one with:"
echo "  tail -F $DEEP_DIR/queue_w1.log"
echo "Aggregate progress: ls $DEEP_DIR/*_matrix.score.json | wc -l"
