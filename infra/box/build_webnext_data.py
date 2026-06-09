import json,sys
from collections import defaultdict
sys.path.insert(0,"/opt/deep_reserch")
from scripts.build_real_leaderboard import is_judge_error_result
OPT="/opt/deep_reserch/"; DST="/mnt/d/lyb/deep_reserch/data/results/deep_v3/"
def coverage(ckpt):
    cov=defaultdict(set); n=0
    for l in open(ckpt):
        l=l.strip()
        if not l: continue
        r=json.loads(l)
        if is_judge_error_result(r.get("res") or {}): continue
        n+=1; cov[r["_a"]].add(r["_task"]); cov[r["_b"]].add(r["_task"])
    alltasks=set().union(*cov.values()) if cov else set()
    return {a:len(ts) for a,ts in cov.items()}, len(alltasks), n
def build(src,ckpt,out,strip_eff,formula):
    d=json.load(open(OPT+src)); elo=d["elo_v3_ci"]; prof=d.get("per_agent_profile",{})
    cov,ntasks,nbatt=coverage(OPT+ckpt)
    ev={}; pc={}
    for a,e in elo.items():
        key=a[4:] if (strip_eff and a.startswith("eff-")) else a
        p=prof.get(a,{})
        ev[key]={"elo":e["elo"],"elo_mean":e.get("elo_mean",e["elo"]),"elo_lo":e["elo_lo"],"elo_hi":e["elo_hi"],
                 "elo_half_width":e["elo_half_width"],"n_resamples":1000,"confidence":0.95,"n_battles":e.get("n_battles",0),
                 "wins":e.get("wins",0),"losses":e.get("losses",0),"draws":e.get("draws",0),
                 "reachability_pct":p.get("reachability_pct"),"url_veracity_pct":p.get("url_veracity_pct")}
        pc[key]=cov.get(a,0)
    obj={"elo_v2_ci":ev,"agents":ev,"pair_counts":pc,"n_runs":nbatt,"n_tasks":ntasks,"n_tasks_target":ntasks,
         "composite_formula":formula}
    json.dump(obj,open(DST+out,"w"),indent=1)
    print(f"{out}: {len(ev)} agents, {ntasks} tasks, {nbatt} battles")
# backup existing framework board
import shutil,os
if os.path.exists(DST+"leaderboard_deep.json"):
    shutil.copy(DST+"leaderboard_deep.json", DST+"leaderboard_deep.json.bak_pre_ccoc")
build("data/results/deep_v3/leaderboard_deep_v3.json","data/results/real/leaderboard_jury_elo.json.battles.jsonl",
      "leaderboard_deep.json",False,
      "Headline = pairwise LLM-judge Bradley-Terry Elo (3-judge PoLL jury, position-debiased). Reach% / Quote% are judge-free grounding: fraction of cited sandbox URLs that resolve, and fraction of quoted snippets verified against the fetched page. Every agent is scored; grounding is shown so fluent-but-ungrounded reports are visible.")
build("data/results/deep_v3/leaderboard_models_v3.json","data/results/real/leaderboard_jury_models.json.battles.jsonl",
      "leaderboard_models.json",True,
      "Same minimal scaffold, varying only the backend LLM. Headline = judge Elo (3-judge PoLL). Reach% / Quote% are judge-free grounding (citation reachability + quote verification).")
