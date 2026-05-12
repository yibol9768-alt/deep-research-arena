#!/bin/bash
# Smoke-test the 5 not-yet-run agents on 2 tasks each (10 pairs total).
# Run via parallel_bulk_launch with 4 workers to finish in ~15 min.
set -e
cd /opt/deep_reserch

DIR=data/results/deep_v3
QUEUE=$DIR/queue_smoke_untested.tsv

# Build the smoke queue
> "$QUEUE"
for agent in camel-ai tongyi-dr co-storm local-deep-researcher dzhng; do
    for task in dr_cross_deep_0001 dr_cross_deep_0005; do
        printf '%s\t%s\n' "$agent" "$task" >> "$QUEUE"
    done
done

echo "=== smoke queue ==="
cat "$QUEUE"
echo
echo "=== launching 4 workers ==="

# Use parallel_bulk_launch with the smoke queue
bash scripts/parallel_bulk_launch.sh 4 "$QUEUE" 2>&1 | tail -15
