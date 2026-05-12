#!/bin/bash
# Test if Qwen3.5-27b returns OpenAI-style `tool_calls` when given a
# function-calling-enabled chat completion. Camel-ai's ChatAgent.step()
# loops until the model returns a final text response with no tool_calls;
# if Qwen never emits tool_calls (or emits them in a non-OpenAI format),
# the loop hangs.
.venv-camel/bin/python - <<'PYEOF'
import json, urllib.request

body = json.dumps({
    "model": "deepseek-v4-flash",  # ds_proxy_lm rewrites to qwen3.5-27b
    "messages":[
        {"role":"system","content":"You are a helpful agent. Use tools when needed."},
        {"role":"user","content":"What is the price of Sony WH-1000XM5 headphones? Use the search_tavily tool."},
    ],
    "tools":[{
        "type":"function",
        "function":{
            "name":"search_tavily",
            "description":"Search the web for information",
            "parameters":{
                "type":"object",
                "properties":{"query":{"type":"string","description":"search query"}},
                "required":["query"],
            },
        },
    }],
    "tool_choice":"auto",
    "temperature":0,
    "max_tokens":2048,
}).encode()
req = urllib.request.Request("http://localhost:8089/v1/chat/completions", data=body,
    headers={"Content-Type":"application/json","Authorization":"Bearer x"})
r = urllib.request.urlopen(req, timeout=120)
d = json.loads(r.read())

msg = d["choices"][0]["message"]
print("finish_reason   :", d["choices"][0]["finish_reason"])
print("has tool_calls  :", bool(msg.get("tool_calls")))
print("tool_calls value:", msg.get("tool_calls"))
print("content len     :", len(msg.get("content") or ""))
print("content head    :", (msg.get("content") or "")[:300])
print("reasoning_content present:", "reasoning_content" in msg)

# What does camel-ai do with this response?
# - If tool_calls present: execute tool, loop back
# - If finish_reason='stop' AND no tool_calls: treat content as final answer
# - If finish_reason='tool_calls' but msg.tool_calls empty: undefined behaviour, possibly wait
PYEOF
