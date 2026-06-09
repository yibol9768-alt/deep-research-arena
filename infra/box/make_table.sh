cd /opt/deep_reserch
export PYTHONUNBUFFERED=1
python3 -u scripts/build_sandbox_cache.py 2>&1 | tail -1
DRA_SANDBOX_CACHE=/opt/deep_reserch/data/results/sandbox_cache.json python3 -u scripts/score_grounding_from_cache.py --out data/results/grounding_uniform2.json 2>&1 | tail -1
python3 - <<'PY'
import json,re,glob
g=json.load(open('data/results/grounding_uniform2.json'))
from collections import defaultdict
agg=defaultdict(lambda: dict(n=0,reach=0.0,quote=0.0))
for r in g['rows']:
    a=r.get('agent') or ''
    if a.startswith('eff-'):
        agg[a]['n']+=1; agg[a]['reach']+=r.get('reachability',0) or 0; agg[a]['quote']+=r.get('quote_match',0) or 0
pat=re.compile(r"\[eff\] ([\w.-]+) (dr_cross_deep_\d+): tok=\d+ \(in (\d+)/out (\d+)\) words=(\d+) cites=(\d+)")
tok=defaultdict(dict)
for lg in glob.glob('.dra_tmp/*.log'):
    for line in open(lg,errors='ignore'):
        m=pat.search(line)
        if m: tok[m.group(1)][m.group(2)]=(int(m.group(3)),int(m.group(4)),int(m.group(5)),int(m.group(6)))
print("TABLE_BEGIN")
print(f"{'model':22}{'n':>4}{'gate':>7}{'reach':>7}{'quote':>7}{'tok_in':>9}{'tok_out':>9}{'words':>6}{'cites':>6}")
for a,v in sorted(agg.items(),key=lambda kv:-(kv[1]['reach']+kv[1]['quote'])/max(kv[1]['n'],1)):
    n=v['n']; re_=v['reach']/n; qu=v['quote']/n; model=a[4:]
    rows=tok.get(model,{}); tin=sum(x[0] for x in rows.values()); tout=sum(x[1] for x in rows.values())
    w=(sum(x[2] for x in rows.values())//max(len(rows),1)) if rows else 0; c=(sum(x[3] for x in rows.values())/max(len(rows),1)) if rows else 0
    print(f"{model:22}{n:>4}{0.5*re_+0.5*qu:>7.3f}{re_:>7.3f}{qu:>7.3f}{tin:>9,}{tout:>9,}{w:>6}{c:>6.1f}")
print("TABLE_END")
PY
