#!/bin/bash
# Batch build golden JSONs for tasks 0031-0100 on westd.
# Run from /opt/deep_reserch inside WSL Ubuntu.
#
# Prerequisites:
#   - Docker containers running (kiwix, webarena_reddit, webarena_shopping)
#   - .venv-camel activated or used as prefix
#
# Usage:
#   bash scripts/batch_golden_westd.sh [start] [end]
#   bash scripts/batch_golden_westd.sh 31 50

set -euo pipefail
cd /opt/deep_reserch

START=${1:-31}
END=${2:-100}
VENV=".venv-camel/bin/python3"

export SHOPPING_URL="http://localhost:7770"
export REDDIT_URL="http://localhost:9999"
export WIKI_URL="http://localhost:8090"

echo "=== Batch golden build: tasks $START to $END ==="
echo "$(date): starting"

PASS=0
FAIL=0
SKIP=0

for NUM in $(seq $START $END); do
    PADDED=$(printf "%04d" $NUM)
    YAML=$(ls configs/deep_topics/${PADDED}_*.yaml 2>/dev/null | head -1)

    if [ -z "$YAML" ]; then
        echo "[$PADDED] SKIP: no YAML found"
        SKIP=$((SKIP + 1))
        continue
    fi

    TASK_ID="dr_cross_deep_${PADDED}"
    OUT="data/golden/deep/${TASK_ID}.json"

    if [ -f "$OUT" ]; then
        echo "[$PADDED] SKIP: golden already exists"
        SKIP=$((SKIP + 1))
        continue
    fi

    echo -n "[$PADDED] building golden from $YAML... "
    if $VENV scripts/build_deep_golden.py \
        --task-id "$TASK_ID" \
        --topic-config "$YAML" \
        --out "$OUT" 2>/tmp/golden_${PADDED}.err; then

        MUST=$(python3 -c "import json; d=json.load(open('$OUT')); print(len(d.get('must_cite_urls',[])))" 2>/dev/null || echo "?")
        POOL=$(python3 -c "import json; d=json.load(open('$OUT')); print(len(d.get('expected_pool_urls',[])))" 2>/dev/null || echo "?")
        echo "OK (must_cite=$MUST pool=$POOL)"
        PASS=$((PASS + 1))
    else
        echo "FAILED (see /tmp/golden_${PADDED}.err)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "=== Done: $PASS passed, $FAIL failed, $SKIP skipped ==="
echo "$(date): finished"
