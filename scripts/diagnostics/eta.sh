#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep_v3
done_n=$(ls $DIR/*_matrix.score.json 2>/dev/null | wc -l)
total=456
remain=$((total - done_n))
echo "done    : $done_n / $total"
echo "remaining: $remain"
echo
echo "score JSON timestamps (last 10):"
ls -t $DIR/*_matrix.score.json 2>/dev/null | head -10 | while read f; do
    ts=$(stat -c %y "$f" | awk '{print $2}' | cut -d. -f1)
    echo "  $ts  $(basename "$f" _matrix.score.json)"
done
echo
echo "rate over last 30 score JSONs:"
oldest=$(ls -t $DIR/*_matrix.score.json 2>/dev/null | head -30 | tail -1)
newest=$(ls -t $DIR/*_matrix.score.json 2>/dev/null | head -1)
oldest_ts=$(stat -c %Y "$oldest")
newest_ts=$(stat -c %Y "$newest")
delta=$((newest_ts - oldest_ts))
if [ "$delta" -gt 0 ]; then
    rate_per_min=$(awk "BEGIN { printf \"%.2f\", 30 * 60 / $delta }")
    eta_min=$(awk "BEGIN { printf \"%.0f\", $remain * $delta / 30 / 60 }")
    echo "  30 pairs in $((delta/60)) min ($delta s) = $rate_per_min pairs/min"
    echo "  ETA at this rate: ~$eta_min minutes ($(awk "BEGIN { printf \"%.1f\", $eta_min/60 }") hours)"
fi
