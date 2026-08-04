#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${QWEN8B_MODEL_PATH:-/opt/models/Qwen3-8B}"
SERVED_MODEL="${QWEN8B_SERVED_MODEL:-qwen3-8b}"
HOST="${QWEN8B_HOST:-127.0.0.1}"
PORT="${QWEN8B_PORT:-8000}"
MAX_MODEL_LEN="${QWEN8B_MAX_MODEL_LEN:-40960}"
GPU_MEMORY_UTILIZATION="${QWEN8B_GPU_MEMORY_UTILIZATION:-0.88}"
VLLM_BIN="${QWEN8B_VLLM_BIN:-/root/vllm-venv/bin/vllm}"
OUTPUT_DIR="${QWEN8B_OUTPUT_DIR:-/opt/dra-truth56-score-20260727-r1/data/results/qwen8b_judge_pilot}"
LOG_PATH="${OUTPUT_DIR}/vllm.log"
PID_PATH="${OUTPUT_DIR}/vllm.pid"

mkdir -p "${OUTPUT_DIR}"

if curl -fsS --max-time 3 "http://${HOST}:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "Qwen judge is already serving at http://${HOST}:${PORT}/v1"
  exit 0
fi

if [[ ! -x "${VLLM_BIN}" ]]; then
  echo "vLLM executable not found: ${VLLM_BIN}" >&2
  exit 1
fi
if [[ ! -f "${MODEL_PATH}/config.json" ]]; then
  echo "Qwen model not found: ${MODEL_PATH}" >&2
  exit 1
fi

: >"${LOG_PATH}"
setsid -f bash -c '
  exec env \
    VLLM_USE_V2_MODEL_RUNNER=0 \
    VLLM_USE_FLASHINFER_SAMPLER=0 \
    "$1" serve "$2" \
    --served-model-name "$3" \
    --host "$4" \
    --port "$5" \
    --max-model-len "$6" \
    --gpu-memory-utilization "$7" \
    --enable-prefix-caching
' _ \
  "${VLLM_BIN}" \
  "${MODEL_PATH}" \
  "${SERVED_MODEL}" \
  "${HOST}" \
  "${PORT}" \
  "${MAX_MODEL_LEN}" \
  "${GPU_MEMORY_UTILIZATION}" \
  >>"${LOG_PATH}" 2>&1

for _ in $(seq 1 10); do
  pid="$(pgrep -f "vllm serve ${MODEL_PATH}" | head -n 1 || true)"
  if [[ -n "${pid}" ]]; then
    printf '%s\n' "${pid}" >"${PID_PATH}"
    echo "Started Qwen judge pid=${pid}; log=${LOG_PATH}"
    exit 0
  fi
  sleep 1
done

echo "Qwen judge did not stay running; inspect ${LOG_PATH}" >&2
exit 1
