import json, os, random, time
from src.scoring import pairwise_judge as PJ
board=json.load(open('data/results/real/leaderboard_judge_elo.json'))
draws=[b for b in board['battle_log'] if b.get('verdicts_raw')==['A','A']]
random.seed(7); sample=random.sample(draws,30)
def rd(a,t):
    p=f'data/results/deep/{a}__{t}_matrix.md'
    return open(p,encoding='utf-8',errors='ignore').read()
def intent(t):
    p=f'data/tasks/deep_research/cross_site_deep/{t}.json'
    try: return json.load(open(p)).get('intent') or t
    except Exception: return t
res={'decisive':0,'tie':0,'pos_locked':0,'winners':{}}
for i,b in enumerate(sample):
    t,a1,a2=b['task'],b['agent_a'],b['agent_b']
    try:
        r=PJ.battle(task_intent=intent(t),agent_a=a1,answer_a=rd(a1,t),agent_b=a2,answer_b=rd(a2,t),n_samples=1)
    except Exception as e:
        print(i,'ERR',type(e).__name__,str(e)[:80],flush=True); continue
    w=r.get('winner'); v=r.get('verdicts_raw')
    if w in ('a','b',a1.lower(),a2.lower()):
        res['decisive']+=1
        name=a1 if w in ('a',a1.lower()) else a2
        res['winners'][name]=res['winners'].get(name,0)+1
    else:
        res['tie']+=1
        if v in (['A','A'],['B','B']): res['pos_locked']+=1
    print(i,t,a1,'vs',a2,'->',w,v,flush=True)
print('SUMMARY',json.dumps(res))
