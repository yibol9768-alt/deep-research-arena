#!/bin/bash
# Point dzhng at our ds_proxy:8088 (uses the topped-up DeepSeek key) instead
# of its own out-of-balance account at api.deepseek.com.
set -e
ENV=/opt/deep_reserch/third_party/deep-research/.env.local

cp "$ENV" "$ENV.bak.$(date +%s)"

cat > "$ENV" <<EOF
OPENAI_KEY=anything-proxy-uses-server-key
OPENAI_ENDPOINT=http://localhost:8088
CUSTOM_MODEL=deepseek-v4-flash
FIRECRAWL_KEY=fc-shim-fake
FIRECRAWL_BASE_URL=http://localhost:8081
CONTEXT_SIZE=32000
PORT=3051
FIRECRAWL_CONCURRENCY=2
EOF

echo "=== new .env.local ==="
cat "$ENV"
echo
echo "=== restart dzhng API ==="
pkill -f 'tsx.*src/api.ts' 2>/dev/null || true
sleep 1
cd /opt/deep_reserch/third_party/deep-research
setsid nohup npm run api > /tmp/dzhng_api.log 2>&1 < /dev/null &
disown $! 2>/dev/null || true
sleep 5
ss -tnl | grep ':3051' && echo "LISTENING" || echo "NOT LISTENING"
echo "---log tail---"
tail -10 /tmp/dzhng_api.log
