#!/usr/bin/env bash
# Sync web + docs from Windows mount to /opt/deep_reserch and restart uvicorn.
set -e
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch

mkdir -p "$DST/docs" "$DST/web/templates"

tr -d '\r' < "$SRC/web/server.py" > "$DST/web/server.py"
for f in base.html about.html; do
    tr -d '\r' < "$SRC/web/templates/$f" > "$DST/web/templates/$f"
done
cp -f "$SRC/docs/PROJECT_WRITEUP.md" "$DST/docs/PROJECT_WRITEUP.md"

"$DST/.venv-camel/bin/python" -c "import ast; ast.parse(open('$DST/web/server.py').read()); print('SYNTAX_OK')"

pkill -f 'uvicorn.*web.server' 2>/dev/null || true
sleep 1
cd "$DST"
setsid nohup .venv-camel/bin/uvicorn web.server:app --host 0.0.0.0 --port 8000 > /tmp/web_server.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 4

echo "=== HTTP status ==="
for p in / /about /compare /how-it-works /contribute /audit "/api/leaderboard.json"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$p")
    echo "  $code  $p"
done

echo
echo "=== /about: first H1 + word count ==="
about_html=$(curl -s http://127.0.0.1:8000/about)
echo "  H1 count: $(echo "$about_html" | grep -c '<h1')"
echo "  H2 count: $(echo "$about_html" | grep -c '<h2')"
echo "  body length: $(echo -n "$about_html" | wc -c)"
echo "  About link in nav?: $(echo "$about_html" | grep -c 'href="/about"')"
