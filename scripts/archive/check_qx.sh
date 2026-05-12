#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep
echo "=== recent qx-agents reports ==="
ls -t "$DIR"/qx-agents__*.md 2>/dev/null | head -3 | while read f; do
    echo "--- $(basename $f) ---"
    head -c 400 "$f"
    echo
    echo
done

echo "=== qx-agents processes alive? ==="
ps -ef | grep -E 'qx-agents|_qx_driver|run_deep_task.*qx' | grep -v grep | head -5 || echo "none"

echo
echo "=== qx_runner.py: search_provider line ==="
grep -n 'search_provider' /opt/deep_reserch/scripts/runners/qx_runner.py | head -10

echo
echo "=== llm_config.py supported providers ==="
grep -n 'supported_search_providers\|Invalid search provider' /opt/deep_reserch/third_party/agents-deep-research/deep_researcher/llm_config.py | head -10
