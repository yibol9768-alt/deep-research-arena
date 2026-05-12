#!/bin/bash
echo "score JSONs : $(ls /opt/deep_reserch/data/results/deep_v3/*.score.json 2>/dev/null | wc -l)"
echo "bulk PID    : $(pgrep -f run_full_leaderboard.sh | head -1 || echo NONE)"
echo "current     : $(ps -ef | grep run_deep_task | grep -v grep | awk '{for(i=1;i<=NF;i++) if($i=="--task") print $(i+1)}' | head -1)"
