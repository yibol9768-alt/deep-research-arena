import os, json, sys, urllib.request

BASE = os.environ["DASHSCOPE_BASE_URL"].rstrip("/")
KEY = os.environ["DASHSCOPE_API_KEY"]

prompt = """You are generating realistic forum threads for a home-coffee-brewing subreddit (r/coffee style).
Generate 12 DISTINCT threads about home coffee brewing. Cover a spread of subtopics:
pour-over technique, French press, espresso at home, grind size, water quality, bean freshness/storage,
cold brew, AeroPress, milk frothing/latte art, budget vs premium grinders, decaf, and troubleshooting bitter/sour coffee.

Each thread must be a realistic Reddit-style self-post: a specific question or experience-sharing post.
Where natural, mention real consumer products that a shopper could buy (e.g. "Andina Premium Colombian whole bean medium roast",
"Javy cold brew concentrate", "Mount Hagen organic ground coffee", a French press, a burr grinder). Do not invent brand-specific
spec claims; keep mentions plausible and generic where unsure.

Return STRICT JSON: a JSON array of 12 objects, each {"title": "...", "body": "..."}.
Titles: 6-14 words, natural Reddit style. Bodies: 80-180 words, conversational, first-person, with a clear question or takeaway.
Output ONLY the JSON array, no markdown fences, no commentary."""

payload = {
    "model": "qwen3-30b-a3b-instruct-2507",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.8,
    "max_tokens": 4000,
}
req = urllib.request.Request(
    BASE + "/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=180) as r:
    d = json.loads(r.read().decode())
content = d["choices"][0]["message"]["content"].strip()
# strip code fences if any
if content.startswith("```"):
    content = content.split("\n", 1)[1].rsplit("```", 1)[0] if "```" in content else content
    content = content.strip()
# locate JSON array
start = content.find("[")
end = content.rfind("]")
arr = json.loads(content[start:end+1])
# normalize
clean = []
for o in arr:
    t = (o.get("title") or "").strip()
    b = (o.get("body") or "").strip()
    if t and b:
        clean.append({"title": t, "body": b})
json.dump(clean, open("/opt/deep_reserch/.dra_tmp/coffee_threads.json","w"), indent=2, ensure_ascii=False)
print("generated", len(clean), "threads")
for c in clean[:3]:
    print(" -", c["title"])
