#!/bin/bash
# Batch generate task JSON specs for tasks 0031-0100.
# Runs after batch_golden_westd.sh has produced all golden JSONs.
# Needs LLM access (ds_proxy on westd or direct DeepSeek/GLM API).
#
# Usage:
#   OPENAI_BASE_URL=http://localhost:8088/v1 OPENAI_API_KEY=sk-xxx \
#   bash scripts/batch_taskspec.sh [start] [end]

set -euo pipefail
cd /opt/deep_reserch

START=${1:-31}
END=${2:-100}
VENV=".venv-camel/bin/python3"

# Use GLM Coding Plan (DeepSeek balance exhausted)
export OPENAI_BASE_URL="https://open.bigmodel.cn/api/coding/paas/v4"
export OPENAI_API_KEY="5e4b5082f8954dc98d63935220002707.9Go2OiZMkcbDDXVx"
export GEN_MODEL="glm-4-flash"

# Intent mapping (from TASK_EXPANSION_MATRIX.md)
declare -A INTENT_MAP
# Health/Medicine
INTENT_MAP[31]=Recommendation; INTENT_MAP[32]=Recommendation
INTENT_MAP[33]=Comparison; INTENT_MAP[34]=Comparison
INTENT_MAP[35]=Debunking; INTENT_MAP[36]=Debunking
INTENT_MAP[37]=Causal; INTENT_MAP[38]=Causal
INTENT_MAP[39]=Timeline; INTENT_MAP[40]=Timeline
INTENT_MAP[41]=Enumeration
# Technology
INTENT_MAP[42]=Recommendation; INTENT_MAP[43]=Recommendation
INTENT_MAP[44]=Comparison; INTENT_MAP[45]=Comparison
INTENT_MAP[46]=Debunking; INTENT_MAP[47]=Debunking
INTENT_MAP[48]=Causal; INTENT_MAP[49]=Causal
INTENT_MAP[50]=Timeline; INTENT_MAP[51]=Timeline
INTENT_MAP[52]=Enumeration; INTENT_MAP[53]=Enumeration
# Environment
INTENT_MAP[54]=Recommendation; INTENT_MAP[55]=Recommendation
INTENT_MAP[56]=Comparison
INTENT_MAP[57]=Debunking; INTENT_MAP[58]=Debunking
INTENT_MAP[59]=Causal; INTENT_MAP[60]=Causal
INTENT_MAP[61]=Timeline; INTENT_MAP[62]=Timeline
INTENT_MAP[63]=Enumeration; INTENT_MAP[64]=Enumeration
# Business
INTENT_MAP[65]=Recommendation; INTENT_MAP[66]=Recommendation
INTENT_MAP[67]=Comparison
INTENT_MAP[68]=Debunking
INTENT_MAP[69]=Causal; INTENT_MAP[70]=Causal
INTENT_MAP[71]=Timeline
INTENT_MAP[72]=Enumeration; INTENT_MAP[73]=Enumeration
# Politics
INTENT_MAP[74]=Recommendation
INTENT_MAP[75]=Comparison; INTENT_MAP[76]=Comparison
INTENT_MAP[77]=Debunking
INTENT_MAP[78]=Causal; INTENT_MAP[79]=Causal
INTENT_MAP[80]=Timeline
INTENT_MAP[81]=Enumeration
# Existing domain gaps
INTENT_MAP[82]=Recommendation
INTENT_MAP[83]=Timeline; INTENT_MAP[84]=Enumeration
INTENT_MAP[85]=Recommendation
INTENT_MAP[86]=Timeline; INTENT_MAP[87]=Enumeration
INTENT_MAP[88]=Recommendation
INTENT_MAP[89]=Debunking; INTENT_MAP[90]=Timeline
INTENT_MAP[91]=Recommendation
INTENT_MAP[92]=Debunking; INTENT_MAP[93]=Enumeration
INTENT_MAP[94]=Causal
INTENT_MAP[95]=Timeline; INTENT_MAP[96]=Enumeration
INTENT_MAP[97]=Causal
INTENT_MAP[98]=Timeline
INTENT_MAP[99]=Comparison
INTENT_MAP[100]=Timeline

echo "=== Batch task spec generation: $START to $END ==="

PASS=0
FAIL=0
SKIP=0

for NUM in $(seq $START $END); do
    PADDED=$(printf "%04d" $NUM)
    TASK_ID="dr_cross_deep_${PADDED}"
    GOLDEN="data/golden/deep/${TASK_ID}.json"
    YAML=$(ls configs/deep_topics/${PADDED}_*.yaml 2>/dev/null | head -1)
    OUT="data/tasks/deep_research/cross_site_deep/${TASK_ID}.json"
    INTENT="${INTENT_MAP[$NUM]:-Recommendation}"

    if [ -f "$OUT" ]; then
        echo "[$PADDED] SKIP: task JSON already exists"
        SKIP=$((SKIP + 1))
        continue
    fi

    if [ ! -f "$GOLDEN" ]; then
        echo "[$PADDED] SKIP: no golden JSON"
        SKIP=$((SKIP + 1))
        continue
    fi

    if [ -z "$YAML" ]; then
        echo "[$PADDED] SKIP: no topic YAML"
        SKIP=$((SKIP + 1))
        continue
    fi

    echo -n "[$PADDED] generating task spec (intent=$INTENT)... "
    if $VENV scripts/gen_task_spec.py \
        --golden-json "$GOLDEN" \
        --intent-type "$INTENT" \
        --topic-yaml "$YAML" \
        --task-id "$TASK_ID" \
        --out "$OUT" 2>/tmp/taskspec_${PADDED}.err; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "FAILED (see /tmp/taskspec_${PADDED}.err)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "=== Done: $PASS passed, $FAIL failed, $SKIP skipped ==="
