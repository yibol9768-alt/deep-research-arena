#!/bin/bash
# Probe both qwen models in LM Studio via plain Python (no jq needed).
LM=${LM_STUDIO_URL:-http://172.30.48.1:1234/v1}

for MODEL in qwen3.5-27b qwen3.5-35b-a3b; do
    echo "============================================================"
    echo "MODEL: $MODEL"
    echo "============================================================"
    /opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request
body = json.dumps({
    "model": "$MODEL",
    "messages": [{"role": "user", "content": 'Reply with EXACTLY this and nothing else: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 120,
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
import time; t0=time.time()
try:
    r = urllib.request.urlopen(req, timeout=90)
    d = json.loads(r.read())
    content = d["choices"][0]["message"]["content"]
    print(f"latency: {time.time()-t0:.1f}s, {len(content)} chars")
    print("--- response ---")
    print(content)
except Exception as e:
    print(f"FAILED: {e}")
PYEOF
    echo
done
