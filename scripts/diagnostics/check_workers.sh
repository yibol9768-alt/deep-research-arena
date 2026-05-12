#!/bin/bash
set +u
DIR=/opt/deep_reserch/data/results/deep_v3
echo "=== running processes ==="
ps -ef | grep -E 'run_full_leaderboard|run_deep_task|score_deep' | grep -v grep | wc -l
echo
echo "=== worker logs ==="
for w in 1 2 3 4 5 6; do
    echo "--- w${w} ---"
    tail -5 "$DIR/queue_w${w}.log" 2>/dev/null || echo "NO LOG"
done
echo
echo "=== score JSONs on disk ==="
ls "$DIR"/*_matrix.score.json 2>/dev/null | wc -l
