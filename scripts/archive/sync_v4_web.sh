#!/usr/bin/env bash
# Sync v4 web changes (server.py + base.html + v4.html) from Windows
# mount to /opt/deep_reserch, then validate Python loads and /v4 renders.
set -e
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch

for f in \
  web/server.py \
  web/templates/base.html \
  web/templates/v4.html \
  scripts/build_v4_leaderboard.py \
  scripts/run_v4_experiment.py ; do
  mkdir -p "$(dirname "$DST/$f")"
  tr -d '\r' < "$SRC/$f" > "$DST/$f"
  echo "synced $f"
done

cd "$DST"
echo
echo "[syntax] server.py"
.venv-camel/bin/python -c "import ast; ast.parse(open('web/server.py').read()); print('OK')"

# Restart uvicorn on 8000 if it's running.
echo
echo "[restart] uvicorn web.server:app"
pkill -f 'uvicorn.*web.server' 2>/dev/null || true
sleep 1
setsid nohup .venv-camel/bin/uvicorn web.server:app --host 0.0.0.0 --port 8000 > /tmp/web_server.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 4

echo
echo "[probe] /, /v4, /api/v4.json"
for p in / /v4 "/api/v4.json"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$p")
  echo "  $code  $p"
done

echo
echo "[probe] /v4 contains 'composite_v4' and 'camel-ai'?"
html=$(curl -s http://127.0.0.1:8000/v4)
echo -n "  composite_v4: "; echo "$html" | grep -q 'composite_v4' && echo yes || echo NO
echo -n "  camel-ai: ";     echo "$html" | grep -q 'camel-ai' && echo yes || echo NO
echo -n "  flowsearcher-ds: "; echo "$html" | grep -q 'flowsearcher-ds' && echo yes || echo NO
echo -n "  source_diversity: "; echo "$html" | grep -q 'source_diversity' && echo yes || echo NO
