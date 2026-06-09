#!/bin/bash
# Uniform re-score of all agent reports on the non-quarantine clean-benchmark
# tasks, so the full field is comparable on the same tasks with the SAME
# (current, full) signal set. Runs inside tmux on the box; resumable; logged.
# Needs: sandbox up (:7770/:9999/:8090) for reachability, judge.env for the
# checklist/presentation judge.
set -u
cd /opt/deep_reserch || exit 2
set -a; . /root/.config/dra/judge.env 2>/dev/null; set +a
export PYTHONUNBUFFERED=1
CONC="${CONC:-6}"

# Build the work list: (task<TAB>report.md) for every report whose task is NOT
# quarantined in the clean manifest.
python3 - > /opt/deep_reserch/.dra_tmp/rescore_list.txt <<'PY'
import json, glob, os
m = json.load(open('data/golden/deep_clean/_manifest.json'))['tasks']
for md in sorted(glob.glob('data/results/deep/*__dr_cross_deep_*_matrix.md')):
    base = os.path.basename(md)
    task = base.split('__')[1].rsplit('_matrix', 1)[0]
    if (m.get(task) or {}).get('verdict') == 'quarantine':
        continue
    print(f"{task}\t{md}")
PY

total=$(wc -l < /opt/deep_reserch/.dra_tmp/rescore_list.txt)
echo "[rescore] start: $total reports, concurrency=$CONC, $(date)"
i=0
while IFS=$'\t' read -r task md; do
  i=$((i+1))
  out="${md%.md}.score.json"
  # Resume: skip if already re-scored in this pass (new signal set present).
  if [ -f "$out" ] && python3 -c "import json,sys;d=json.load(open('$out'));sys.exit(0 if 'source_diversity' in (d.get('composite') or {}) else 1)" 2>/dev/null; then
    continue
  fi
  (
    timeout 150 python3 scripts/score_deep_answer.py --task "$task" --answer "$md" --out "$out" >/dev/null 2>&1 \
      && echo "[ok $i/$total] $(basename "$md")" \
      || echo "[FAIL $i/$total] $(basename "$md")"
  ) &
  # concurrency cap
  while [ "$(jobs -rp | wc -l)" -ge "$CONC" ]; do sleep 0.4; done
done < /opt/deep_reserch/.dra_tmp/rescore_list.txt
wait
ok=$(grep -c '^\[ok' /opt/deep_reserch/.dra_tmp/rescore.log 2>/dev/null || echo '?')
echo "[rescore] ALL DONE $(date)"
