#!/usr/bin/env python3
"""Build truth-gated framework + model boards from clean jury battles + offline
grounding (grounding_uniform.json). Judge-free aggregation: reuses the same
Bradley-Terry fit as build_real_leaderboard, drops judge-error battles, and
applies the hard grounding gate (agents below floor are removed from the
headline Elo fit so beating junk cannot inflate Elo)."""
import json,sys,os
from collections import defaultdict
sys.path.insert(0,"/opt/deep_reserch")
from scripts.build_real_leaderboard import is_judge_error_result
from src.scoring import bradley_terry as bt

FLOOR=float(sys.argv[1]) if len(sys.argv)>1 else 0.0
GU=os.environ.get("GU","/opt/deep_reserch/data/results/grounding_uniform.json")

gmean={}
if os.path.exists(GU):
    rows=json.load(open(GU)).get("rows",[])
    gv=defaultdict(list)
    for r in rows:
        cr=r.get("curated_recall"); qm=r.get("quote_match")
        cr=0.0 if cr is None else float(cr); qm=0.0 if qm is None else float(qm)
        gv[r["agent"]].append(0.5*cr+0.5*qm)
    gmean={a:sum(v)/len(v) for a,v in gv.items() if v}
    print(f"[grounding] loaded {GU}: {len(gmean)} agents")
else:
    print(f"[grounding] {GU} MISSING -> grounding=0 for all (no gating unless floor>0)")

def load_clean(ckpt):
    rows=[json.loads(l) for l in open(ckpt) if l.strip()]
    clean=[r for r in rows if not is_judge_error_result(r.get("res") or {})]
    bl=[{"agent_a":r["_a"],"agent_b":r["_b"],"winner":(r.get("res") or {}).get("agent_winner","tie")} for r in clean]
    return bl,len(rows),len(clean)

def board(name,ckpt):
    if not os.path.exists(ckpt):
        print(f"\n### {name}: checkpoint missing {ckpt}"); return
    bl,ntot,ncl=load_clean(ckpt)
    agents=set()
    for b in bl: agents.add(b["agent_a"]); agents.add(b["agent_b"])
    gated={a for a in agents if gmean.get(a,0.0)<FLOOR}
    ranked=[b for b in bl if b["agent_a"] not in gated and b["agent_b"] not in gated]
    elo_full=bt.fit_bradley_terry(bl)
    elo_head=bt.fit_bradley_terry(ranked) if ranked else {}
    print(f"\n### {name}  (battles total={ntot} clean={ncl}, FLOOR={FLOOR}, gated={sorted(gated)})")
    ordered=sorted(agents,key=lambda a:-(elo_head.get(a, elo_full.get(a,0))))
    for i,a in enumerate(ordered,1):
        g=gmean.get(a,0.0); he=elo_head.get(a); fe=elo_full.get(a)
        tag=" [GATED]" if a in gated else ""
        print(f"{i:2d}. {a:34s} elo={ (he if he is not None else fe):7.1f}  grounding={g:.3f}{tag}")

board("FRAMEWORK","/opt/deep_reserch/data/results/real/leaderboard_jury_elo.json.battles.jsonl")
board("MODEL","/opt/deep_reserch/data/results/real/leaderboard_jury_models.json.battles.jsonl")
