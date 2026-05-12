#!/bin/bash
cd /opt/deep_reserch
DONE=$(grep -c " scored " data/results/deep_v3/run_full_leaderboard.progress 2>/dev/null || echo 0)
SCORED=$(ls data/results/deep_v3/*_matrix.score.json 2>/dev/null | wc -l)
TOTAL=$(wc -l < data/results/deep_v3/run_queue.tsv 2>/dev/null)
START_TS=$(awk 'NR==1{print $4}' data/results/deep_v3/run_full_leaderboard.log 2>/dev/null)
NOW=$(date '+%H:%M:%S')
echo "scored events in progress file : $DONE"
echo "score JSONs on disk            : $SCORED"
echo "total queue                    : $TOTAL"
if [ "$TOTAL" -gt 0 ]; then
    PCT=$(awk "BEGIN { printf \"%.1f\", ($DONE/$TOTAL)*100 }")
    REMAINING=$((TOTAL - DONE))
    AVG_MIN=13
    ETA_HOURS=$(awk "BEGIN { printf \"%.1f\", ($REMAINING * $AVG_MIN) / 60 }")
    ETA_DAYS=$(awk "BEGIN { printf \"%.1f\", ($REMAINING * $AVG_MIN) / 60 / 24 }")
    echo "percent complete               : $PCT%"
    echo "remaining                      : $REMAINING pairs"
    echo "ETA (assuming 13 min/pair)     : $ETA_HOURS hours / $ETA_DAYS days"
fi
echo
echo "current pair in flight:"
ps -ef | awk '/run_deep_task.py.*--agent/ && !/awk/ {for (i=NF; i>=1; i--) if ($i=="--agent") {print $(i+1), $(i+3); break}}' | head -1
echo
echo "log start - now : $START_TS - $NOW"
