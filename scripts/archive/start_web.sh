#!/bin/bash
# Stop any prior web server, start fresh on 127.0.0.1:8000.
pkill -f 'uvicorn.*web.server' 2>/dev/null || true
sleep 1
cd /opt/deep_reserch
LOG=/tmp/web_server.log
setsid nohup .venv-camel/bin/uvicorn web.server:app \
    --host 0.0.0.0 --port 8000 \
    > "$LOG" 2>&1 < /dev/null &
disown $! 2>/dev/null || true
echo "started uvicorn (logs: $LOG)"
sleep 4
echo "---listen---"
ss -tnl | grep ':8000' || echo "NOT LISTENING"
echo "---log head---"
head -20 "$LOG"
