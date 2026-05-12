#!/usr/bin/env bash
# Sync v4b web changes + restart uvicorn + probe.
set -e
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch

for f in web/server.py web/templates/v4.html ; do
  tr -d '\r' < "$SRC/$f" > "$DST/$f"
  echo "synced $f"
done

cd "$DST"
.venv-camel/bin/python -c "import ast; ast.parse(open('web/server.py').read()); print('SYNTAX_OK')"

pkill -f 'uvicorn.*web.server' 2>/dev/null || true
sleep 1
setsid nohup .venv-camel/bin/uvicorn web.server:app --host 0.0.0.0 --port 8000 > /tmp/web_server.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 4

echo
echo "=== probes ==="
for p in / /v4 "/api/v4.json"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$p")
  echo "  $code  $p"
done

echo
echo "=== /v4 content checks ==="
html=$(curl -s http://127.0.0.1:8000/v4)
for s in 'composite_v4b' 'IC sharp' 'Min adjacent gap' 'flowsearcher-ds' 'deerflow' 'IC raw'; do
  if echo "$html" | grep -q "$s"; then
    echo "  yes:  $s"
  else
    echo "   NO:  $s"
  fi
done
