#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/dra-qwen-unified-storm-20260729-r1
R2_ROOT="$ROOT/output/harness-matrix-qwen3-8b-shared-contract-r2"
OUTPUT_ROOT="$ROOT/output/harness-matrix-qwen3-8b-shared-contract-r3"
LOG_PATH="$ROOT/output/harness-matrix-qwen3-8b-shared-contract-r3.log"

mkdir -p "$OUTPUT_ROOT"
for harness in gpt-researcher ii-researcher opencode smolagents storm; do
  if [[ ! -e "$OUTPUT_ROOT/$harness" ]]; then
    cp -al "$R2_ROOT/$harness" "$OUTPUT_ROOT/$harness"
  fi
done

cache_roots=()
while IFS= read -r path; do
  cache_roots+=("$path")
done < <(
  find \
    "$ROOT/output/harness-matrix-qwen3-8b-shared-contract-r1" \
    "$R2_ROOT" \
    "$ROOT/output/storm-audio-qwen3-8b-run01" \
    "$ROOT/output/qwen-r5-smoke-camel" \
    "$OUTPUT_ROOT/claude-code.failed-before-positional-dedup" \
    "$OUTPUT_ROOT/claude-code.incomplete-after-positional-dedup-start" \
    "$OUTPUT_ROOT/claude-code.incomplete-before-fact-chunking" \
    "$OUTPUT_ROOT/claude-code.failed-before-evidence-excerpt" \
    "$OUTPUT_ROOT/deerflow.incomplete-before-positional-dedup" \
    "$OUTPUT_ROOT/deerflow.partial-before-evidence-excerpt" \
    "$OUTPUT_ROOT/langchain-odr.incomplete-before-evidence-excerpt" \
    -type d \
    \( \
      -name claim_proposal -o \
      -name claim_nli -o \
      -name claim_structural -o \
      -name fact -o \
      -name evidence_coverage_rubric -o \
      -name task_compiler \
    \) \
    -print 2>/dev/null
)
if ((${#cache_roots[@]})); then
  export DRA_JUDGE_CACHE_DIRS
  DRA_JUDGE_CACHE_DIRS="$(
    IFS=:
    echo "${cache_roots[*]}"
  )"
fi

exec python3 "$ROOT/scripts/run_unified_qwen_harness_matrix.py" \
  --prepared-root "$ROOT/data/results/four_axis_v4lite_matrix_20260724/prepared" \
  --task "$ROOT/data/results/qwen_unified_storm_20260729/deploy/inputs/task.json" \
  --task-world-model "$ROOT/data/pilot_v33/dra_v3_dev_audio_0002/task-world-model.json" \
  --research-test-suite "$ROOT/data/pilot_v33/dra_v3_dev_audio_0002/research-test-suite.json" \
  --graph-dir "$ROOT/data/evidence_graph/dra-v3-pilot-audio-speaker-claims-20260715-r1" \
  --url-registry "$ROOT/data/golden/url_registry.json" \
  --shared-task-contract "$ROOT/output/storm-audio-qwen3-8b-run01/02-frozen-assets/task-contract" \
  --output-root "$OUTPUT_ROOT" \
  --model qwen3-8b \
  --judge-base-url http://127.0.0.1:8000/v1 \
  --fact-search-base-url http://127.0.0.1:8081 \
  >>"$LOG_PATH" 2>&1
