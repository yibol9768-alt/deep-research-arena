#!/bin/bash
set -e
mkdir -p /opt/deep_reserch/web/templates /opt/deep_reserch/web/static
# Sync server + templates (CRLF stripped on copy via tr)
for f in server.py README.md requirements.txt; do
    src=/mnt/d/lyb/deep_reserch/web/$f
    dst=/opt/deep_reserch/web/$f
    [ -f "$src" ] && tr -d '\r' < "$src" > "$dst"
done
# Remove obsolete templates from /opt
for f in agent.html add.html smoke.html playground.html; do
    rm -f /opt/deep_reserch/web/templates/$f
done
# Copy current templates
for f in base.html index.html how_it_works.html contribute.html audit.html; do
    src=/mnt/d/lyb/deep_reserch/web/templates/$f
    dst=/opt/deep_reserch/web/templates/$f
    [ -f "$src" ] && tr -d '\r' < "$src" > "$dst"
done
# Static screenshots
cp -r /mnt/d/lyb/deep_reserch/web/static/* /opt/deep_reserch/web/static/ 2>/dev/null || true

echo "=== synced files ==="
ls -la /opt/deep_reserch/web/templates/

echo
echo "=== syntax check server.py ==="
/opt/deep_reserch/.venv-camel/bin/python -c "import ast; ast.parse(open('/opt/deep_reserch/web/server.py').read()); print('OK')"
