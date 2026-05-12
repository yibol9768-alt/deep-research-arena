#!/usr/bin/env bash
# Ping deepseek-v4-pro and v4-flash via local ds_proxy to confirm routing.
set -e
PROXY=http://localhost:8088/v1
for M in deepseek-v4-flash deepseek-v4-pro; do
  echo "=== $M ==="
  curl -s -X POST $PROXY/chat/completions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer anything' \
    -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"reply OK\"}],\"max_tokens\":12,\"temperature\":0}" \
    | head -c 400
  echo
done
