#!/bin/bash
# Find out where ds_proxy is forwarding requests: real DeepSeek API, or
# the local LM Studio? The smoking gun is in /proc/<pid>/environ.
set -e
PID=$(pgrep -f 'integrations.ds_proxy' | head -1)
if [ -z "$PID" ]; then
    echo "ds_proxy not running"; exit 1
fi
echo "ds_proxy PID=$PID"
echo
echo "=== relevant env vars ==="
tr '\0' '\n' < /proc/$PID/environ | grep -E -i "DEEPSEEK|OPENAI|LM_STUDIO|REWRITE|PROXY|TOKEN|API_KEY|TARGET" | sed 's/\(KEY=\).*/\1<redacted>/' | head -20
echo
echo "=== test what /v1/chat/completions actually proxies to ==="
echo "--- deepseek-v4-flash (production backbone) ---"
T0=$(date +%s.%N)
curl -s --max-time 60 -o /tmp/dsproxy_resp.json -w "HTTP %{http_code} time %{time_total}s size %{size_download}\n" \
    -X POST http://localhost:8088/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"reply with exactly OK"}],"temperature":0,"max_tokens":8}'
echo "  body sample:"
head -c 400 /tmp/dsproxy_resp.json
echo
