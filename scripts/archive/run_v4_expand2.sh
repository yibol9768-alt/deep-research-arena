#!/usr/bin/env bash
# Second expansion — add 4 more tasks (= 9 × 4 = 36 more rows) to the v4 set.
# Combined with the existing 44 rows this gets us to ~80 rows, enough for
# adjacent-gap p-values to start dipping below 0.05 for the bigger gaps.
set -e

SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch
cd "$DST"

for f in src/verifiers/*.py src/scoring/leaderboard_composites.py scripts/run_v4_experiment.py scripts/recompute_v4c.py ; do
  mkdir -p "$(dirname "$DST/$f")"
  tr -d '\r' < "$SRC/$f" > "$DST/$f" 2>/dev/null || true
done

export JUDGE_PROVIDER=openai
export JUDGE_BASE_URL=http://localhost:8088/v1
export JUDGE_API_KEY=anything
export JUDGE_MODEL=deepseek-v4-flash
export JUDGE_MODEL_HEAVY=deepseek-v4-pro

# 4 additional tasks, resume safe. 0008/0011/0019/0024 are well-formed
# in the 0001-0030 range; pick ones we haven't scored yet.
.venv-camel/bin/python -u scripts/run_v4_experiment.py \
  --agents camel-ai,flowsearcher-ds,smolagents,ldr,gpt-researcher,deerflow,ii-researcher,langchain-odr,storm \
  --tasks dr_cross_deep_0008,dr_cross_deep_0011,dr_cross_deep_0019,dr_cross_deep_0024 \
  --max 36 \
  --resume \
  2>&1
