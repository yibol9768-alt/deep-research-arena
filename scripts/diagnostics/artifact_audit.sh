#!/usr/bin/env bash
set -u
echo "=== docs/ ==="
ls -la /opt/deep_reserch/docs/ 2>/dev/null

echo
echo "=== web/templates/ ==="
ls -la /opt/deep_reserch/web/templates/ 2>/dev/null

echo
echo "=== data/results/audit/ ==="
ls -la /opt/deep_reserch/data/results/audit/ 2>/dev/null

echo
echo "=== final_audit / fairness output ==="
ls -lt /opt/deep_reserch/data/results/ 2>/dev/null | grep -iE 'audit|fair|final' | head -10

echo
echo "=== server endpoint health ==="
for p in / /compare /how-it-works /contribute /audit "/api/leaderboard.json"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$p")
    echo "  $code  $p"
done

echo
echo "=== judge_error rows in score files ==="
python3 - <<'PY'
import json, glob, os
root = "/opt/deep_reserch/data/results/deep_v3"
files = glob.glob(os.path.join(root, "*.score.json"))
total = len(files)
judge_err = []
checklist_err = []
nli_err = []
for f in files:
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for k, v in (d.get("pillars") or {}).items():
        if isinstance(v, dict):
            if v.get("error"):
                judge_err.append((os.path.basename(f), k, str(v.get("error"))[:80]))
            if k == "checklist" and v.get("score") in (None,) and "judge_pass" not in v:
                checklist_err.append(os.path.basename(f))
            if k == "claim_nli" and v.get("error"):
                nli_err.append(os.path.basename(f))
print(f"total score files: {total}")
print(f"pillars with .error set: {len(judge_err)}")
for r in judge_err[:15]:
    print(f"  {r[0]}  pillar={r[1]}  err={r[2]}")
if len(judge_err) > 15:
    print(f"  ... +{len(judge_err)-15} more")
PY
