#!/bin/bash
ps -ef | grep -E 'run_full_leaderboard|run_deep_task|score_deep_answer|_benchmark_driver' | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null
sleep 3
ps -ef | grep -E 'run_full_leaderboard|run_deep_task|score_deep_answer|_benchmark_driver' | grep -v grep
echo "remaining: $(ps -ef | grep -E 'run_full_leaderboard|run_deep_task|score_deep_answer|_benchmark_driver' | grep -v grep | wc -l)"
