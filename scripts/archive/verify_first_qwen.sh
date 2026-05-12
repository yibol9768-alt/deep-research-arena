#!/bin/bash
cd /opt/deep_reserch
F=data/results/deep_v3/deerflow__dr_cross_deep_0001_matrix.score.json
if [ ! -f "$F" ]; then
    echo "[FAIL] $F does not exist"
    exit 1
fi
ls -la "$F"
echo
.venv-camel/bin/python - <<PYEOF
import json
import sys
sys.path.insert(0, '.')
from src.scoring.leaderboard_composites import (
    composite_v2_truthful, composite_v1, quality,
    spec_pass_fraction, checklist_pass_rate,
)
d = json.loads(open("$F", encoding="utf-8").read())
print(f"answer_chars        : {d.get('answer_chars')}")
print(f"url_coverage        : {(d.get('url_coverage') or {}).get('score'):.3f}")
print(f"url_reachability    : {(d.get('url_reachability') or {}).get('score'):.3f}")
ck = d.get("checklist") or {}
print(f"checklist pass_rate : {checklist_pass_rate(ck):.3f}")
print(f"checklist judge_err : {ck.get('judge_error')!r}")
print(f"spec pass fraction  : {spec_pass_fraction(d.get('markdown_spec')):.3f}")
ad = (d.get('analysis_depth') or {})
ad_d = ad.get('details') or {}
print(f"analysis_depth.score: {ad.get('score'):.3f}  judge_err: {ad_d.get('judge_error')!r}")
pres = (d.get('presentation') or {})
pres_d = pres.get('details') or {}
print(f"presentation.score  : {pres.get('score'):.3f}  judge_err: {pres_d.get('judge_error')!r}")
print(f"quality (v1)        : {quality(d):.3f}")
print(f"composite_v2        : {composite_v2_truthful(d):.4f}")
print(f"composite_v1        : {composite_v1(d):.4f}")
raw = json.dumps(d)
leaks = []
for tag in ["Thinking Process", "<think>", "</think>"]:
    if tag in raw:
        leaks.append(tag)
if leaks:
    print(f"[LEAK] thinking traces in JSON: {leaks}")
else:
    print("[OK] no thinking-prefix leakage")
PYEOF
