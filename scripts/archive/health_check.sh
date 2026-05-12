#!/bin/bash
# 5-min health check on the bulk Qwen3.5-27b run.
cd /opt/deep_reserch

echo "=== 1. processes ==="
ps -ef | awk '/run_full_leaderboard|run_deep_task|ds_proxy/ && !/awk/ {print}'

echo
echo "=== 2. log tail (last 30) ==="
tail -30 data/results/deep_v3/run_full_leaderboard.log 2>/dev/null

echo
echo "=== 3. progress count ==="
wc -l data/results/deep_v3/run_full_leaderboard.progress 2>/dev/null
echo "scored lines:"
grep -c " scored " data/results/deep_v3/run_full_leaderboard.progress 2>/dev/null || echo "0"

echo
echo "=== 4. score JSONs created since 16:12 ==="
find data/results/deep_v3 -name "*_matrix.score.json" -newer data/results/deep_v3/run_queue.tsv 2>/dev/null | wc -l
echo "(filenames):"
find data/results/deep_v3 -name "*_matrix.score.json" -newer data/results/deep_v3/run_queue.tsv 2>/dev/null | head -10

echo
echo "=== 5. errors ==="
if [ -f data/results/deep_v3/run_full_leaderboard.errors ]; then
    wc -l data/results/deep_v3/run_full_leaderboard.errors
    echo "tail:"
    tail -10 data/results/deep_v3/run_full_leaderboard.errors
else
    echo "(no errors file yet)"
fi

echo
echo "=== 6. thinking-leak check (latest score JSON) ==="
LATEST=$(find data/results/deep_v3 -name "*_matrix.score.json" -newer data/results/deep_v3/run_queue.tsv 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    echo "checking: $LATEST"
    .venv-camel/bin/python3 -c "
import json
d = json.loads(open('$LATEST', encoding='utf-8').read())
ck = d.get('checklist') or {}
ad_d = (d.get('analysis_depth') or {}).get('details') or {}
pres_d = (d.get('presentation') or {}).get('details') or {}
print(f'agent: {d.get(\"agent\") or \"?\"}  task: {d.get(\"task\") or \"?\"}  chars: {d.get(\"answer_chars\")}')
print(f'composite_v2: {(d.get(\"composite\") or {}).get(\"composite_v2\") or 0:.4f}')
print(f'checklist judge_error: {ck.get(\"judge_error\")}')
print(f'checklist pass_rate: {ck.get(\"pass_rate\")}')
print(f'analysis_depth judge_error: {ad_d.get(\"judge_error\")}')
print(f'presentation judge_error: {pres_d.get(\"judge_error\")}')
# Look for thinking leakage in any judge raw output
for field in ('checklist','analysis_depth','presentation'):
    s = json.dumps(d.get(field))
    if 'Thinking Process' in s or '<think>' in s:
        print(f'  [LEAK] {field} contains thinking text')
"
else
    echo "(no recent score files)"
fi
