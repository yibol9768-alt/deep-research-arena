#!/bin/bash
cd /opt/deep_reserch
echo "=== last 40 lines of run log ==="
tail -40 data/results/deep_v3/run_full_leaderboard.log

echo
echo "=== errors file ==="
if [ -f data/results/deep_v3/run_full_leaderboard.errors ]; then
    cat data/results/deep_v3/run_full_leaderboard.errors
else
    echo "(no errors file)"
fi

echo
echo "=== current run_deep_task processes ==="
ps -ef | grep run_deep_task | grep -v grep | head -3

echo
echo "=== bulk script alive? ==="
ps -ef | grep run_full_leaderboard | grep -v grep | head -3

echo
echo "=== recent score files (last 60 min) ==="
find data/results/deep_v3 -name "*_matrix.score.json" -mmin -60 2>/dev/null | head -20
echo "(count): $(find data/results/deep_v3 -name "*_matrix.score.json" -mmin -60 2>/dev/null | wc -l)"

echo
echo "=== md reports written in last 60 min ==="
find data/results/deep -name "*_matrix.md" -mmin -60 2>/dev/null | head -10

echo
echo "=== progress file tail ==="
tail -10 data/results/deep_v3/run_full_leaderboard.progress 2>/dev/null

echo
echo "=== ds_proxy_lm log tail ==="
tail -5 /tmp/ds_proxy_lm.log 2>&1
