#!/usr/bin/env bash
# Expand the v4 sample by 3 more tasks (= 9 × 3 = 27 more rows).
# Combined with the existing 25, this triples the data for v4b BT/Elo.
set -e

SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch
cd "$DST"

# Sync latest source.
for f in src/verifiers/*.py src/scoring/leaderboard_composites.py scripts/run_v4_experiment.py ; do
  mkdir -p "$(dirname "$DST/$f")"
  tr -d '\r' < "$SRC/$f" > "$DST/$f" 2>/dev/null || true
done

export JUDGE_PROVIDER=openai
export JUDGE_BASE_URL=http://localhost:8088/v1
export JUDGE_API_KEY=anything
export JUDGE_MODEL=deepseek-v4-flash
export JUDGE_MODEL_HEAVY=deepseek-v4-pro

# 3 additional tasks; --resume keeps existing 25 rows.
.venv-camel/bin/python -u scripts/run_v4_experiment.py \
  --agents camel-ai,flowsearcher-ds,smolagents,ldr,gpt-researcher,deerflow,ii-researcher,langchain-odr,storm \
  --tasks dr_cross_deep_0002,dr_cross_deep_0006,dr_cross_deep_0015 \
  --max 27 \
  --resume \
  2>&1
