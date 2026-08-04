#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 HARNESS" >&2
  exit 64
fi

harness=$1
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
matrix="$root/data/results/four_axis_v4lite_matrix_20260724"
prepared="$matrix/prepared/$harness/scorer-inputs"
output="$matrix/scores/$harness"
fact_ssh_host=${FACT_SSH_HOST:-my5090}

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
  JUDGE_API_KEY=$(
    ssh "$fact_ssh_host" \
      "wsl -d Ubuntu -- sed -n s/^DEEPSEEK_API_KEY=//p /root/.config/dra-harness-adapters/deepseek.env"
  )
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
  --task /root/Desktop/lyb/dra-harness-adapters/smoke-results/dr-tulu-dra-v3-dev-audio-0002/task.json \
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
  --fact-ssh-host "$fact_ssh_host" \
  --judge-cache-dir data/results/four_axis_pilot/dr-tulu-dra-v3-dev-audio-0002-v10-dynamic/judge_calls
