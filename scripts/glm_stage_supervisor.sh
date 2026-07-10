#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/root/pilot_v2}"
PROXY_BASE="${GLM_STAGE_PROXY:-http://127.0.0.1:8092}"
DRIVER="${DRIVER:-$BASE/glm_lane_driver.sh}"
LOGDIR="${LOGDIR:-$BASE/logs}"
RUN_TIMEOUT="${RUN_TIMEOUT:-1800}"
SUFFIX="${SUFFIX:-glmflash}"
BACKBONE="${BACKBONE:-glm-4.7-flash}"
QUEUE_TAG="${QUEUE_TAG:-no_claude}"
LANE_TAG="${LANE_TAG:-single_${QUEUE_TAG}}"

mkdir -p "$LOGDIR"

wait_for_tmux_session() {
  local session="$1"
  while tmux has-session -t "$session" 2>/dev/null; do
    printf '[%s] waiting for existing tmux session %s to finish\n' \
      "$(date '+%Y-%m-%d %H:%M:%S')" "$session"
    sleep 60
  done
}

run_stage() {
  local stage="$1"
  local queue="$2"
  local lane="${stage}_${LANE_TAG}"
  local log="$LOGDIR/glm_${stage}_${LANE_TAG}.log"

  printf '============================================================\n'
  printf '[%s] stage=%s queue=%s proxy=%s log=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$stage" "$queue" "$PROXY_BASE" "$log"
  printf '============================================================\n'

  RUN_TIMEOUT="$RUN_TIMEOUT" SUFFIX="$SUFFIX" BACKBONE="$BACKBONE" \
    bash "$DRIVER" "$queue" "$lane" "$PROXY_BASE" >"$log" 2>&1

  printf '[%s] stage=%s finished\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$stage"
}

cd "$BASE"

# This supervisor is intentionally single-lane. GLM-4.7-Flash is currently
# rate-limited enough that two task lanes mostly amplify 429 retries.
wait_for_tmux_session glm_subset_lane1

run_stage subset "$BASE/queues/queue_glm_subset_${QUEUE_TAG}.tsv"
run_stage mini "$BASE/queues/queue_glm_mini_${QUEUE_TAG}.tsv"
run_stage full "$BASE/queues/queue_glm_full_all_${QUEUE_TAG}.tsv"

printf '[%s] %s staged run complete\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$QUEUE_TAG"
