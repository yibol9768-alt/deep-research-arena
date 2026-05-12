#!/usr/bin/env bash
# Run the v4 experiment on /opt/deep_reserch with the production environment.
# 9 agents × 3 tasks = 27 runs. Heavy verifiers use deepseek-v4-pro via
# ds_proxy; light verifiers use deepseek-v4-flash.
set -e

# Sync experiment driver + new verifiers from Windows mount.
SRC=/mnt/d/lyb/deep_reserch
DST=/opt/deep_reserch
for f in \
  src/verifiers/source_diversity_verifier.py \
  src/verifiers/perspective_balance_verifier.py \
  src/verifiers/factual_exactness_verifier.py \
  src/verifiers/internal_consistency_verifier.py \
  src/verifiers/judge_client.py \
  src/verifiers/base.py \
  src/verifiers/citation_format.py \
  src/scoring/leaderboard_composites.py \
  scripts/score_deep_answer.py \
  scripts/smoke_v4_verifiers.py \
  scripts/run_v4_experiment.py ; do
  mkdir -p "$(dirname "$DST/$f")"
  tr -d '\r' < "$SRC/$f" > "$DST/$f"
done
echo "[sync] done"

cd "$DST"

export JUDGE_PROVIDER=openai
export JUDGE_BASE_URL=http://localhost:8088/v1
export JUDGE_API_KEY=anything
export JUDGE_MODEL=deepseek-v4-flash
export JUDGE_MODEL_HEAVY=deepseek-v4-pro

echo "[env]"
echo "  JUDGE_MODEL       = $JUDGE_MODEL"
echo "  JUDGE_MODEL_HEAVY = $JUDGE_MODEL_HEAVY"
echo

# Use --resume so a partial run can be re-launched without redoing work.
# -u for unbuffered output so tail -f shows progress live.
.venv-camel/bin/python -u scripts/run_v4_experiment.py \
  --agents camel-ai,flowsearcher-ds,smolagents,ldr,gpt-researcher,deerflow,ii-researcher,langchain-odr,storm \
  --tasks dr_cross_deep_0001,dr_cross_deep_0005,dr_cross_deep_0010 \
  --max 27 \
  --resume \
  2>&1
