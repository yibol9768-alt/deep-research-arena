#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep_v3

echo "=== queue files + how much each has left ==="
for q in queue_gptr queue_storm queue_smoke_ext queue_deepagents; do
    f=$DIR/${q}.tsv
    [ -f "$f" ] || continue
    total=$(wc -l < "$f")
    # Count pairs that already have a score JSON
    done_n=0
    while IFS=$'\t' read -r agent task; do
        [ -z "$agent" ] && continue
        score=$DIR/${agent}__${task}_matrix.score.json
        [ -f "$score" ] && done_n=$((done_n + 1))
    done < "$f"
    remaining=$((total - done_n))
    printf "  %-22s %d / %d done  (%d remaining)\n" "$q" "$done_n" "$total" "$remaining"
done

echo
echo "=== rate over last 20 score JSONs ==="
oldest=$(ls -t $DIR/*_matrix.score.json 2>/dev/null | head -20 | tail -1)
newest=$(ls -t $DIR/*_matrix.score.json 2>/dev/null | head -1)
if [ -f "$oldest" ] && [ -f "$newest" ]; then
    oldest_ts=$(stat -c %Y "$oldest")
    newest_ts=$(stat -c %Y "$newest")
    delta=$((newest_ts - oldest_ts))
    if [ "$delta" -gt 0 ]; then
        rate_min=$(awk "BEGIN { printf \"%.2f\", 20 * 60 / $delta }")
        echo "  20 pairs in $((delta/60))m$((delta%60))s = $rate_min pairs/min"
    fi
fi

echo
echo "=== alive workers ==="
ps -ef | grep run_full_leaderboard.sh | grep -v grep | wc -l
