#!/bin/bash
cd /opt/deep_reserch/third_party/deep-research
LOG=/tmp/dzhng_api.log
# Kill any prior process
pkill -f 'tsx.*src/api.ts' 2>/dev/null || true
sleep 1
# Start fresh
setsid nohup npm run api > "$LOG" 2>&1 < /dev/null &
disown $! 2>/dev/null || true
echo "started dzhng API (logs: $LOG)"
sleep 6
echo "---listen---"
ss -tnl | grep ':3051' || echo "NOT LISTENING"
echo "---log tail---"
tail -15 "$LOG"
