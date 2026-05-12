#!/bin/bash
echo "=== score_deep_answer process? ==="
ps -ef | grep score_deep_answer | grep -v grep
echo
echo "=== run_deep_task processes? ==="
ps -ef | grep run_deep_task | grep -v grep
echo
echo "=== bulk scripts ==="
ps -ef | grep run_full_leaderboard | grep -v grep
echo
echo "=== last 10 log lines ==="
tail -10 /opt/deep_reserch/data/results/deep_v3/run_full_leaderboard.log
echo
echo "=== bulk script's child processes ==="
pstree -p $(pgrep -f run_full_leaderboard.sh | head -1) 2>&1 | head -20
echo
echo "=== open TCP sockets to LM Studio ==="
ss -tan state established 2>/dev/null | grep -E ':(1234|8089)' | head -10
