#!/bin/bash
for path in / /how-it-works /contribute /audit /api/leaderboard.json; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$path")
    echo "$code $path"
done
echo
echo "=== /  page first 20 lines ==="
curl -s http://127.0.0.1:8000/ | head -20
