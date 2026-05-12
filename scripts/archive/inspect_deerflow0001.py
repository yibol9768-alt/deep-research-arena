#!/usr/bin/env python3
import json
from pathlib import Path

f = Path("data/results/deep_v3/deerflow__dr_cross_deep_0001_matrix.score.json")
d = json.loads(f.read_text(encoding="utf-8"))

print(f"answer_chars     : {d.get('answer_chars')}")
print(f"url_coverage     : {(d.get('url_coverage') or {}).get('score') or 0:.3f}")
print(f"url_reachability : {(d.get('url_reachability') or {}).get('score') or 0:.3f}")
ck = d.get("checklist") or {}
print(f"checklist pass   : {ck.get('pass_rate') or 0:.3f}  err={ck.get('judge_error')!r}")
ad = d.get("analysis_depth") or {}
adde = (ad.get("details") or {}).get("judge_error")
print(f"analysis_depth   : {(ad.get('score') or 0):.3f}  err={adde!r}")
pr = d.get("presentation") or {}
prre = (pr.get("details") or {}).get("judge_error")
print(f"presentation     : {(pr.get('score') or 0):.3f}  err={prre!r}")
print(f"composite block  : {d.get('composite')}")

raw = json.dumps(d)
leaks = [t for t in ("Thinking Process", "<think>", "</think>") if t in raw]
print("LEAKS:" if leaks else "OK", leaks if leaks else "no thinking strings")

# Re-derive composite_v2 inline (avoid src.scoring import on WSL)
url = (d.get("url_coverage") or {}).get("score") or 0
chk = ck.get("pass_rate") or ck.get("score") or 0
spec = d.get("markdown_spec") or {}
spec_frac = sum(bool(spec.get(k, False)) for k in ("words_ok", "citations_ok", "paragraphs_ok")) / 3
reach = (d.get("url_reachability") or {}).get("score") or 0
quality = 0.40 * float(url) + 0.40 * float(chk) + 0.20 * spec_frac
v2 = float(reach) * quality
print(f"computed composite_v2 = {v2:.4f}  (reach={reach:.3f} * quality={quality:.3f})")
