import json,sys
sys.path.insert(0,"/opt/deep_reserch")
from scripts.build_real_leaderboard import is_judge_error_result
from src.scoring import bradley_terry as bt
from collections import defaultdict
R="/opt/deep_reserch/"
rows=[json.loads(l) for l in open(R+"data/results/real/leaderboard_jury_models.json.battles.jsonl") if l.strip()]
clean=[r for r in rows if not is_judge_error_result(r.get("res") or {})]
bl=[{"agent_a":r["_a"],"agent_b":r["_b"],"winner":(r.get("res") or {}).get("agent_winner","tie")} for r in clean]
ntasks=len(set(r["_task"] for r in clean))
ci=bt.bootstrap_ci(bl)
wld=defaultdict(lambda:{"wins":0,"losses":0,"draws":0}); nb=defaultdict(int)
for b in bl:
    a,bb,w=b["agent_a"],b["agent_b"],b["winner"]; nb[a]+=1; nb[bb]+=1
    if w==a: wld[a]["wins"]+=1; wld[bb]["losses"]+=1
    elif w==bb: wld[bb]["wins"]+=1; wld[a]["losses"]+=1
    else: wld[a]["draws"]+=1; wld[bb]["draws"]+=1
g=json.load(open(R+"data/results/grounding_uniform2.json"))
acc=defaultdict(lambda:{"n":0,"reach":0.0,"quote":0.0})
for r in g.get("rows") or []:
    a=r.get("agent");
    if not a: continue
    acc[a]["n"]+=1; acc[a]["reach"]+=r.get("reachability",0) or 0; acc[a]["quote"]+=r.get("quote_match",0) or 0
elo_ci={}; profile={}
for a,c in ci.items():
    elo_ci[a]={"elo":round(c["elo"],1),"elo_mean":round(c["elo"],1),"elo_lo":round(c["lo"],1),"elo_hi":round(c["hi"],1),"elo_half_width":round(c["half_width"],1),"n_battles":nb[a],**wld[a]}
    ga=acc.get(a)
    profile[a]={"reachability_pct":round(100*ga["reach"]/ga["n"],1) if ga and ga["n"] else None,"url_veracity_pct":round(100*ga["quote"]/ga["n"],1) if ga and ga["n"] else None,"synthetic_placeholder":False}
out={"_schema_version":"v3-model-judge-elo-2026-06-08","_dry_run":False,"synthetic_placeholder":False,"source":"real","board_kind":"model",
 "composite_formula":"headline = judge Elo (3-judge PoLL, position-debiased) over a fixed minimal scaffold varying only the backend LLM; grounding (reachability% / quote-verified%) shown as columns. "+str(ntasks)+" tasks, "+str(len(clean))+" clean battles (judge-error battles excluded).",
 "elo_v3_ci":elo_ci,"per_agent_profile":profile,"n_tasks":ntasks,"n_battles":len(clean),"source_file":"leaderboard_jury_models.json.battles.jsonl (clean)"}
json.dump(out, open(R+"data/results/deep_v3/leaderboard_models_v3.json","w"), indent=1)
print(f"wrote leaderboard_models_v3.json: {len(elo_ci)} models, {ntasks} tasks, {len(clean)} clean battles")
for i,(a,e) in enumerate(sorted(elo_ci.items(),key=lambda x:-x[1]["elo"]),1):
    p=profile[a]; print(f"{i}. {a:34s} elo={e['elo']:7.1f} [{e['elo_lo']:.0f},{e['elo_hi']:.0f}]  reach%={p['reachability_pct']} quote%={p['url_veracity_pct']}  W/L/D={e['wins']}/{e['losses']}/{e['draws']}")
