#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 HARNESS" >&2
  exit 64
fi

harness=$1
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
matrix=${MATRIX_ROOT:-"$root/data/results/four_axis_v4lite_matrix_20260724"}
prepared="$matrix/prepared/$harness/scorer-inputs"
output="$matrix/scores/$harness"
task=${TASK_PATH:-"$root/smoke-results/dr-tulu-dra-v3-dev-audio-0002/task.json"}
fact_search_base_url=${FACT_SEARCH_BASE_URL:-http://localhost:8081}

for file in report.normalized.md trace.json citation-map.json; do
  if [[ ! -f "$prepared/$file" ]]; then
    echo "missing prepared scorer input: $prepared/$file" >&2
    exit 66
  fi
done
if [[ -e "$output/score.json" ]]; then
  echo "score already exists: $output/score.json" >&2
  exit 73
fi

if [[ -z "${JUDGE_API_KEY:-}" ]]; then
  judge_env=${JUDGE_ENV_FILE:-/root/.config/dra-harness-adapters/deepseek.env}
  JUDGE_API_KEY=$(sed -n 's/^DEEPSEEK_API_KEY=//p' "$judge_env")
fi
export JUDGE_API_KEY
export JUDGE_PROVIDER=openai
export JUDGE_MODEL=deepseek-v4-flash
export JUDGE_MODEL_HEAVY=deepseek-v4-flash
export JUDGE_THINKING=0
export JUDGE_TIMEOUT_S=180
export PYTHONPATH="$root"

cd "$root"
exec python3 scripts/run_four_axis_pipeline.py \
  --task "$task" \
  --report "$prepared/report.normalized.md" \
  --trace "$prepared/trace.json" \
  --citation-map "$prepared/citation-map.json" \
  --task-world-model data/pilot_v33/dra_v3_dev_audio_0002/task-world-model.json \
  --research-test-suite data/pilot_v33/dra_v3_dev_audio_0002/research-test-suite.json \
  --graph-dir data/evidence_graph/dra-v3-pilot-audio-speaker-claims-20260715-r1 \
  --url-registry data/golden/url_registry.json \
  --output-dir "$output" \
  --model deepseek-v4-flash \
  --claim-proposal-model deepseek-v4-flash \
  --nli-model deepseek-v4-flash \
  --structural-model deepseek-v4-flash \
  --fact-model deepseek-v4-flash \
  --evidence-model deepseek-v4-flash \
  --fact-search-base-url "$fact_search_base_url" \
  --judge-cache-dir \
    data/results/four_axis_pilot/dr-tulu-dra-v3-dev-audio-0002-v10-dynamic/judge_calls
