#!/bin/bash
# Quick diagnostic on a pair: shows answer head + score summary.
# Usage: bash diag_pair.sh <agent> <task>
agent=$1
task=$2
cd /opt/deep_reserch
echo "=== answer.md head ==="
head -c 600 "data/results/deep/${agent}__${task}_matrix.md" 2>/dev/null
echo
echo
echo "=== score summary ==="
.venv-camel/bin/python - <<PY
import json
fp = "/opt/deep_reserch/data/results/deep_v3/${agent}__${task}_matrix.score.json"
d = json.load(open(fp))
c = d.get("composite", {})
print(f"composite_v2 : {c.get('composite_v2')}")
print(f"composite_v3 : {c.get('composite_v3')}")
print(f"answer_chars : {d.get('answer_chars')}")
print(f"reach        : {(d.get('url_reachability') or {}).get('score')}")
print(f"cited_total  : {((d.get('url_reachability') or {}).get('details') or {}).get('cited_total')}")
print(f"url_cov      : {(d.get('url_coverage') or {}).get('score')}")
print(f"must_hit     : {((d.get('url_coverage') or {}).get('details') or {}).get('must_cite_hit')}")
cl = d.get("checklist") or {}
print(f"checklist    : {cl.get('pass_count')}P/{cl.get('fail_count')}F/{cl.get('unclear_count')}U  err={cl.get('judge_error')}")
print(f"ad err       : {((d.get('analysis_depth') or {}).get('details') or {}).get('judge_error')}")
print(f"pres err     : {((d.get('presentation') or {}).get('details') or {}).get('judge_error')}")
PY
