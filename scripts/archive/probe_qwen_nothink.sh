#!/bin/bash
# Try several no-thinking system prompts against qwen3.5-35b-a3b.
LM=${LM_STUDIO_URL:-http://172.30.48.1:1234/v1}

for SYSPROMPT in \
    "You are a JSON-only output bot. Do NOT think aloud. Do NOT prefix anything. Output ONLY the JSON requested." \
    "/no_think" \
    "Output the literal answer only. No analysis, no preamble, no \"Thinking Process\" prefix." ; do
    echo "============================================================"
    echo "SYSTEM PROMPT: $SYSPROMPT"
    echo "============================================================"
    /opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request, time
body = json.dumps({
    "model": "qwen3.5-35b-a3b",
    "messages": [
        {"role": "system", "content": '$SYSPROMPT'},
        {"role": "user", "content": 'Reply with EXACTLY this and nothing else: {"answer":"yes"}'},
    ],
    "temperature": 0,
    "max_tokens": 60,
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
t0=time.time()
try:
    r = urllib.request.urlopen(req, timeout=60)
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
