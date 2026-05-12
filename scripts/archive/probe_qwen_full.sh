#!/bin/bash
# Probe with enough tokens that 27b finishes its thinking AND prints the answer.
LM=${LM_STUDIO_URL:-http://172.30.48.1:1234/v1}
/opt/deep_reserch/.venv-camel/bin/python3 - <<'PYEOF'
import json, urllib.request
body = json.dumps({
    "model": "qwen3.5-27b",
    "messages": [{"role":"user","content":'Output exactly the following JSON and nothing else: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 1024,
}).encode()
req = urllib.request.Request("http://172.30.48.1:1234/v1/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=120)
content = json.loads(r.read())["choices"][0]["message"]["content"]
print(f"=== full response ({len(content)} chars) ===")
print(content)
print("=== /response ===")
PYEOF
