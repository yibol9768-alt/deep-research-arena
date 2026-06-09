import json
p='data/results/real/leaderboard_jury_elo.json.battles.jsonl'
seen={}
for l in open(p):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    res=r.get('res',{}) or {}
    jury=res.get('jury') or res.get('judge_votes') or {}
    nval=(len(jury) if jury else 3)-(res.get('judge_errors_partial') or 0)
    seen[(r.get('_task'),r.get('_a'),r.get('_b'))]=1 if nval>=2 else 0
v=sum(seen.values())
print(f"clean={v} degraded={len(seen)-v} unique={len(seen)}")
