#!/bin/bash
# Try several ways to disable thinking for Qwen3 family.
LM=${LM_STUDIO_URL:-http://172.30.48.1:1234/v1}
MODEL=${LM_MODEL:-qwen3.5-27b}

echo "=== test 1: /no_think tag in user message ==="
/opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request
body = json.dumps({
    "model": "$MODEL",
    "messages": [{"role":"user","content":'/no_think Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=60)
print(json.loads(r.read())["choices"][0]["message"]["content"])
PYEOF
echo

echo "=== test 2: enable_thinking=False extra-body ==="
/opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request
body = json.dumps({
    "model": "$MODEL",
    "messages": [{"role":"user","content":'Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,
    "enable_thinking": False,
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=60)
print(json.loads(r.read())["choices"][0]["message"]["content"])
PYEOF
echo

echo "=== test 3: chat_template_kwargs=enable_thinking:false ==="
/opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request
body = json.dumps({
    "model": "$MODEL",
    "messages": [{"role":"user","content":'Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,
    "chat_template_kwargs": {"enable_thinking": False},
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=60)
print(json.loads(r.read())["choices"][0]["message"]["content"])
PYEOF
echo

echo "=== test 4: think=false top-level ==="
/opt/deep_reserch/.venv-camel/bin/python3 - <<PYEOF
import json, urllib.request
body = json.dumps({
    "model": "$MODEL",
    "messages": [{"role":"user","content":'Output exactly: {"answer":"yes"}'}],
    "temperature": 0,
    "max_tokens": 60,
    "think": False,
}).encode()
req = urllib.request.Request("$LM/chat/completions", data=body,
                             headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=60)
print(json.loads(r.read())["choices"][0]["message"]["content"])
PYEOF
