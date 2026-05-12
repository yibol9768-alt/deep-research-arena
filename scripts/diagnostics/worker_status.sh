#!/bin/bash
echo "=== which worker queues are running ==="
ps -ef | grep run_full_leaderboard.sh | grep -v grep | awk '{for(i=1;i<=NF;i++) if(match($i, "queue_w[0-9]+\\.tsv")) print $i}'
echo
echo "=== log sizes (each worker) ==="
for w in 1 2 3 4 5 6; do
    LOG=/opt/deep_reserch/data/results/deep_v3/queue_w${w}.log
    if [ -f "$LOG" ]; then
        size=$(stat -c %s "$LOG")
        printf "  w%d log: %d bytes\n" "$w" "$size"
    fi
done
echo
echo "=== last line of any worker that's not advancing ==="
for w in 1 2 3 4 5 6; do
    LOG=/opt/deep_reserch/data/results/deep_v3/queue_w${w}.log
    [ -f "$LOG" ] || continue
    last=$(tail -1 "$LOG" 2>/dev/null)
    printf "  w%d last: %s\n" "$w" "${last:0:100}"
done
