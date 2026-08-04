#!/usr/bin/env bash
set -euo pipefail

ROOT="${DRA_ROOT:-/opt/dra-truth56-score-20260727-r1}"
TASK_ID="${QWEN8B_PILOT_TASK_ID:-dra_v3_dev_keyboard_0004}"
HARNESS="${QWEN8B_PILOT_HARNESS:-storm}"
MODEL="${QWEN8B_SERVED_MODEL:-qwen3-8b}"
JUDGE_BASE_URL="${QWEN8B_JUDGE_BASE_URL:-http://127.0.0.1:8000/v1}"
OUTPUT_ROOT="${QWEN8B_PILOT_OUTPUT_ROOT:-data/results/qwen8b_judge_pilot}"
ATTEMPT="${QWEN8B_PILOT_ATTEMPT:-2}"
CACHE_ATTEMPT="${QWEN8B_PILOT_CACHE_ATTEMPT:-1}"
printf -v ATTEMPT_PAD '%03d' "${ATTEMPT}"
printf -v CACHE_ATTEMPT_PAD '%03d' "${CACHE_ATTEMPT}"
RUN_DIR="${ROOT}/${OUTPUT_ROOT}/${HARNESS}/${TASK_ID}/attempt-${ATTEMPT_PAD}"
LOG_DIR="${ROOT}/${OUTPUT_ROOT}/${HARNESS}/${TASK_ID}"
CACHE_ROOT="${LOG_DIR}/attempt-${CACHE_ATTEMPT_PAD}/judge_calls"
CACHE_DIRS="$(
  IFS=:
  printf '%s' \
    "${CACHE_ROOT}/compiler:${CACHE_ROOT}/claim_proposal:${CACHE_ROOT}/claim_nli:${CACHE_ROOT}/claim_structural:${CACHE_ROOT}/fact:${CACHE_ROOT}/evidence_coverage_rubric"
)"

cd "${ROOT}"
mkdir -p "${LOG_DIR}"

if ! curl -fsS --max-time 5 "${JUDGE_BASE_URL}/models" >/dev/null; then
  echo "Local Qwen judge is unavailable at ${JUDGE_BASE_URL}" >&2
  exit 1
fi
if [[ -e "${RUN_DIR}" ]]; then
  echo "Pilot output already exists: ${RUN_DIR}" >&2
  exit 1
fi

task_path="data/tasks/deep_research/v3/development/${TASK_ID}.json"
prepared="data/results/truth56_full_20260727/prepared/${HARNESS}/${TASK_ID}/scorer-inputs"
assets="data/results/truth56_full_20260727/assets/${TASK_ID}"
stdout_log="${LOG_DIR}/driver.stdout.log"
stderr_log="${LOG_DIR}/driver.stderr.log"
pid_path="${LOG_DIR}/driver.pid"

setsid -f bash -c '
  cd "$1"
  exec env \
    JUDGE_PROVIDER=openai \
    JUDGE_BASE_URL="$2" \
    JUDGE_API_KEY=EMPTY \
    JUDGE_TIMEOUT_S=600 \
    DRA_JUDGE_CACHE_DIRS="$8" \
    python3 scripts/run_four_axis_pipeline.py \
      --task "$3" \
      --report "$4/report.normalized.md" \
      --trace "$4/trace.json" \
      --citation-map "$4/citation-map.json" \
      --task-world-model "$5/task-world-model.json" \
      --research-test-suite "$5/research-test-suite.json" \
      --graph-dir "$5/graph" \
      --url-registry data/golden/url_registry.json \
      --output-dir "$6" \
      --model "$7" \
      --claim-proposal-model "$7" \
      --nli-model "$7" \
      --structural-model "$7" \
      --fact-model "$7" \
      --evidence-model "$7" \
      --fact-search-base-url http://localhost:8081
' _ \
  "${ROOT}" \
  "${JUDGE_BASE_URL}" \
  "${task_path}" \
  "${prepared}" \
  "${assets}" \
  "${RUN_DIR}" \
  "${MODEL}" \
  "${CACHE_DIRS}" \
  >"${stdout_log}" 2>"${stderr_log}"

for _ in $(seq 1 10); do
  pid="$(pgrep -f "run_four_axis_pipeline.py.*${RUN_DIR}" | head -n 1 || true)"
  if [[ -n "${pid}" ]]; then
    printf '%s\n' "${pid}" >"${pid_path}"
    echo "Started Qwen pilot pid=${pid}; output=${RUN_DIR}"
    exit 0
  fi
  sleep 1
done

echo "Qwen pilot did not stay running; inspect ${stderr_log}" >&2
exit 1
