#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep_v3
echo "score JSONs : $(ls $DIR/*_matrix.score.json 2>/dev/null | wc -l)"
echo "workers     : $(ps -ef | grep -E 'run_full_leaderboard.sh' | grep -v grep | wc -l)"
echo "agent procs : $(ps -ef | grep -E 'run_deep_task.py' | grep -v grep | wc -l)"
echo
echo "per-agent breakdown:"
for a in deerflow flowsearcher-ds ii-researcher langchain-odr ldr qx-agents smolagents storm; do
    n=$(ls $DIR/${a}__*_matrix.score.json 2>/dev/null | wc -l)
    printf "  %-18s %d\n" "$a" "$n"
done
