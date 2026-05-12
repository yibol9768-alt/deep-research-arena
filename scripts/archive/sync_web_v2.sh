#!/bin/bash
set -e
SRC=/mnt/d/lyb/deep_reserch/web
DST=/opt/deep_reserch/web

tr -d '\r' < "$SRC/server.py" > "$DST/server.py"
for f in base.html index.html how_it_works.html contribute.html audit.html compare.html; do
    tr -d '\r' < "$SRC/templates/$f" > "$DST/templates/$f"
done

/opt/deep_reserch/.venv-camel/bin/python -c "import ast; ast.parse(open('$DST/server.py').read()); print('SYNTAX_OK')"

pkill -f 'uvicorn.*web.server' 2>/dev/null || true
sleep 1
cd /opt/deep_reserch
setsid nohup .venv-camel/bin/uvicorn web.server:app --host 0.0.0.0 --port 8000 > /tmp/web_server.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 4
echo "=== HTTP status ==="
for p in / /compare /how-it-works /contribute /audit /api/leaderboard.json; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$p")
    echo "  $code $p"
done
echo
echo "=== /compare snippet (LLM chips) ==="
curl -s http://127.0.0.1:8000/ | grep -E 'llm-chip|Backbone LLM' | head -8
