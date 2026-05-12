#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep_v3
DEEP=/opt/deep_reserch/data/results/deep

echo "=== 1. Workers currently running ==="
ps -ef | grep -E 'run_full_leaderboard.sh|run_deep_task.py' | grep -v grep | awk '{
    for(i=1;i<=NF;i++) {
        if($i ~ /queue_[a-z_0-9]+\.tsv/) print "  queue: " $i;
        if($i == "--agent") print "  in-flight: " $(i+1) " task=" $(i+3);
    }
}' | sort -u

echo
echo "=== 2. Per-agent score count (all live) ==="
for a in camel-ai deerflow flowsearcher-ds gpt-researcher ii-researcher \
         langchain-odr ldr qx-agents smolagents storm tongyi-dr \
         co-storm local-deep-researcher dzhng deepagents; do
    n=$(ls $DIR/${a}__*_matrix.score.json 2>/dev/null | wc -l)
    if [ "$n" -gt 0 ]; then
        printf "  %-25s %d\n" "$a" "$n"
    fi
done

echo
echo "=== 3. Smoke results from queue_w*.log (latest pairs landed) ==="
for w in 1 2 3 4; do
    LOG=$DIR/queue_w${w}.log
    [ -f "$LOG" ] || continue
    pair=$(tail -50 "$LOG" 2>/dev/null | grep -E 'scored|RUN-FAILED|SCORE-FAILED' | tail -2 | sed 's/^/    w'$w': /')
    [ -n "$pair" ] && echo "$pair"
done

echo
echo "=== 4. Latest .md sizes for the 5 untested agents ==="
for a in camel-ai tongyi-dr co-storm local-deep-researcher dzhng; do
    for t in dr_cross_deep_0001 dr_cross_deep_0005; do
        f=$DEEP/${a}__${t}_matrix.md
        if [ -f "$f" ]; then
            chars=$(wc -c < "$f")
            head=$(head -c 80 "$f" | tr '\n' ' ')
            printf "  %-22s %-22s chars=%-6d head=%s\n" "$a" "$t" "$chars" "$head"
        else
            printf "  %-22s %-22s NOT YET\n" "$a" "$t"
        fi
    done
done

echo
echo "=== 5. Bugs status ==="
qx_left=$(ls $DEEP/qx-agents__*_matrix.md 2>/dev/null | head -5 | xargs -I{} head -c 30 {} | grep -c 'qx.*error\|qx stderr' || echo 0)
storm_with_refs=$(ls $DEEP/storm__*_smoketest.md $DEEP/storm__*_matrix.md 2>/dev/null | head -10 | while read f; do grep -l '## References' "$f" 2>/dev/null; done | wc -l)
echo "  qx-agents broken (placeholder count in 5 samples): $qx_left (we accept this, filter excludes them)"
echo "  storm reports with '## References' (newer ones): $storm_with_refs"
