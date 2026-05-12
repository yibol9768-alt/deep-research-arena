#!/bin/bash
# Score-fairness inspection. For each scored pair, surface the parts of the
# composite that drove the final number, plus the actual citation list and the
# golden must-cite list, so we can see WHY the score is what it is and whether
# any normalisation bug is keeping legitimate citations from matching golden
# URLs.
set -u
cd /opt/deep_reserch

for fp in data/results/deep_v3/*_matrix.score.json; do
    base=$(basename "$fp")
    echo "================================================================"
    echo "PAIR: $base"
    echo "================================================================"
    .venv-camel/bin/python - <<PYEOF
import json, re
from pathlib import Path

p = Path("$fp")
data = json.loads(p.read_text(encoding="utf-8"))

print(f"task         : {data.get('task')}")
print(f"answer_chars : {data.get('answer_chars')}")
print(f"composite_v2 : {data['composite']['composite_v2']:.4f}")
print(f"composite_v3 : {data['composite']['composite_v3']:.4f}")
print()

# ---- url_coverage drill-down ----
uc = data['url_coverage']
ucd = uc['details']
print(f"url_coverage.score        : {uc['score']:.3f}  passed={uc['passed']}")
print(f"  must_cite_total         : {ucd.get('must_cite_total')}")
print(f"  must_cite_hit           : {ucd.get('must_cite_hit')}  (recall={ucd.get('must_cite_recall')})")
print(f"  cited_unique            : {ucd.get('cited_unique')}")
print(f"  pool_total              : {ucd.get('pool_total')}")
print(f"  pool_hit                : {ucd.get('pool_hit')}  (coverage={ucd.get('pool_coverage')})")
print(f"  per_domain_cited        : {ucd.get('per_domain_cited')}")
print(f"  per_domain_minimum      : {ucd.get('per_domain_minimum')}")
print(f"  domain_balance          : {ucd.get('domain_balance')}")
print()

# ---- url_reachability ----
ur = data['url_reachability']
urd = ur['details']
print(f"url_reachability.score    : {ur['score']:.3f}  passed={ur['passed']}")
print(f"  cited_total / probed    : {urd.get('cited_total')} / {urd.get('probed')}")
print(f"  http_200 / 4xx / 5xx    : {urd.get('http_200')} / {urd.get('http_4xx')} / {urd.get('http_5xx')}")
print()

# ---- checklist ----
cl = data['checklist']
print(f"checklist : {cl['pass_count']}P / {cl['fail_count']}F / {cl['unclear_count']}U  (pass_rate={cl['pass_rate']:.3f})")
for i, v in enumerate(cl.get('verdicts') or [], 1):
    if isinstance(v, dict):
        # show only first 3 and last 1 for brevity
        if i <= 3 or i >= len(cl['verdicts']):
            verdict = v.get('verdict', '?')
            crit = (v.get('criterion') or '')[:90]
            print(f"  [{i:2d}] {verdict:8s} {crit}")
print()

# ---- composite math reconstruction ----
c = data['composite']
print("composite math:")
print(f"  spec_pass_fraction      : {c.get('spec_pass_fraction')}")
print(f"  quality_score           : {c.get('quality_score')}")
print(f"  truth_factor            : {c.get('truth_factor')}")
print(f"  qm_factor               : {c.get('qm_factor')}")
print(f"  nli_factor              : {c.get('nli_factor')}")
print(f"  grounding_gate          : {c.get('grounding_gate')}")
print(f"  raw_score_v3            : {c.get('raw_score_v3')}")
print(f"  composite_v3            : {c.get('composite_v3')}")
print(f"  composite_v2            : {c.get('composite_v2')}")
print(f"  composite_v1            : {c.get('composite_v1')}")
print()

# ---- Compare: agent's cited URLs vs the golden must-cite list ----
print("--- citation diagnostics ---")

# Pull the agent's cited URLs from the score's url_reachability samples (if any)
# or from the answer markdown directly.
ans_path = data.get('answer_path')
if ans_path:
    ans = Path("/opt/deep_reserch") / ans_path
    if ans.exists():
        text = ans.read_text(encoding="utf-8", errors="replace")
        # extract URLs from markdown links: [text](url)
        urls = re.findall(r'\[[^\]]+\]\((http[^\)]+)\)', text)
        # also bare http(s) URLs
        urls += re.findall(r'(?<![\(\[\"])\b(https?://[^\s\)\>\]\"\']+)', text)
        from urllib.parse import urlsplit
        def norm(u):
            try:
                s = urlsplit(u)
                return f"{s.scheme}://{s.netloc.lower()}{s.path}".rstrip('/')
            except Exception:
                return u
        cited = sorted(set(norm(u) for u in urls))
        # show first 15
        print(f"agent cited URLs (normalised, unique={len(cited)}):")
        for u in cited[:15]:
            print(f"  {u}")
        if len(cited) > 15:
            print(f"  ... (+{len(cited)-15} more)")

# Load the golden pool to see what URLs WERE expected
golden = Path("/opt/deep_reserch/data/golden_pools") / f"{data['task']}.golden.json"
if golden.exists():
    g = json.loads(golden.read_text(encoding="utf-8"))
    must_cite = g.get('must_cite_urls') or []
    print(f"\ngolden must_cite (n={len(must_cite)}):")
    for u in must_cite[:10]:
        print(f"  {u}")
    if len(must_cite) > 10:
        print(f"  ... (+{len(must_cite)-10} more)")

PYEOF

done
