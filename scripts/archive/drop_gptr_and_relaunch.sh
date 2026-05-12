#!/bin/bash
# Drop all gpt-researcher pairs from the queue (it's incompatible with the
# current langchain 1.x; would need its own venv to run cleanly). Clean up
# any gpt-researcher score JSONs that hold runner-error placeholders so
# they don't pollute the leaderboard. Then re-split the remaining queue
# across 6 fresh parallel workers.
set -uo pipefail
cd /opt/deep_reserch

DIR=data/results/deep_v3
SRC=$DIR/run_queue.tsv

# Strip gpt-researcher pairs from the source queue (write a backup first)
cp "$SRC" "$SRC.with-gptr.bak"
grep -v "^gpt-researcher\b" "$SRC" > "$SRC.tmp" && mv "$SRC.tmp" "$SRC"
echo "queue size: $(wc -l < "$SRC") (was $(wc -l < "$SRC.with-gptr.bak"))"

# Wipe the in-flight queue/log artifacts from the previous run
rm -f $DIR/queue_w*.tsv $DIR/queue_w*.log $DIR/queue_w*.progress \
      $DIR/queue_w*.errors $DIR/queue_remaining.tsv $DIR/queue_shuffled.tsv

# Remove all gpt-researcher score JSONs so the bulk doesn't think it has
# stale gptr data lying around (and to keep deep_v3/ tidy)
gptr_count=$(ls $DIR/gpt-researcher__*.score.json 2>/dev/null | wc -l)
if [ "$gptr_count" -gt 0 ]; then
    rm -f $DIR/gpt-researcher__*.score.json
    echo "removed $gptr_count gpt-researcher score JSONs"
fi

bash scripts/parallel_bulk_launch.sh 6 2>&1 | tail -15
