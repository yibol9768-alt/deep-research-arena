#!/usr/bin/env bash
# Quick post-bulk status: workers, daemons, recent scores.
echo "=== workers (run_deep_task.py) ==="
pgrep -af run_deep_task.py 2>/dev/null | head -20
echo
echo "count: $(pgrep -af run_deep_task.py 2>/dev/null | wc -l)"
echo
echo "=== daemons (ds_proxy / shim / sandbox / dzhng) ==="
ss -lntp 2>/dev/null | awk 'NR==1 || /:(7770|8081|8088|8090|9999|3051|8000) /' | sort -u
echo
echo "=== most-recent score files (top 8) ==="
ls -lt /opt/deep_reserch/data/results/deep_v3/*.score.json 2>/dev/null | head -8
echo
echo "=== current leaderboard summary ==="
head -40 /opt/deep_reserch/data/results/deep_v3/LEADERBOARD_DEEP.md 2>/dev/null || echo "(no LEADERBOARD_DEEP.md)"
