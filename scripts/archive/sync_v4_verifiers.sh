#!/usr/bin/env bash
# Sync v4 verifiers + scorer + composite + smoke test from Windows mount
# to the production /opt/deep_reserch tree.
set -e
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch

FILES=(
  src/verifiers/source_diversity_verifier.py
  src/verifiers/perspective_balance_verifier.py
  src/verifiers/factual_exactness_verifier.py
  src/verifiers/internal_consistency_verifier.py
  src/verifiers/judge_client.py
  src/scoring/leaderboard_composites.py
  scripts/score_deep_answer.py
  scripts/smoke_v4_verifiers.py
)

for f in "${FILES[@]}"; do
  mkdir -p "$(dirname "$DST/$f")"
  tr -d '\r' < "$SRC/$f" > "$DST/$f"
  echo "synced $f"
done

echo
echo "=== smoke test on /opt/deep_reserch ==="
cd "$DST"
.venv-camel/bin/python scripts/smoke_v4_verifiers.py 2>&1 | tail -10
