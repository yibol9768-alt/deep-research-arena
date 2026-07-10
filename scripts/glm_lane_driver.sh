#!/usr/bin/env bash
set -uo pipefail

QUEUE="${1:?usage: glm_lane_driver.sh <queue.tsv> <lane_name> <proxy_base_url>}"
LANE_NAME="${2:?usage: glm_lane_driver.sh <queue.tsv> <lane_name> <proxy_base_url>}"
PROXY_BASE="${3:?usage: glm_lane_driver.sh <queue.tsv> <lane_name> <proxy_base_url>}"

cd /opt/deep_reserch

BACKBONE="${BACKBONE:-glm-4.7-flash}"
SUFFIX="${SUFFIX:-glmflash}"
RUN_TIMEOUT="${RUN_TIMEOUT:-}"
ONEAGENT="${ONEAGENT:-/opt/deep_reserch/scripts/glm_oneagent.sh}"
RESUME_COMPLETED="${RESUME_COMPLETED:-1}"

if [ ! -f "$QUEUE" ]; then
  echo "ERROR: queue not found: $QUEUE" >&2
  exit 2
fi
if [ ! -x "$ONEAGENT" ]; then
  echo "ERROR: oneagent script not executable: $ONEAGENT" >&2
  exit 2
fi

PROXY_BASE="${PROXY_BASE%/}"
DS_PROXY_URL="${PROXY_BASE}/v1"
TOTAL=$(wc -l < "$QUEUE")

echo "============================================================"
echo "GLM lane start=$(date '+%Y-%m-%d %H:%M:%S')"
echo "lane:     $LANE_NAME"
echo "queue:    $QUEUE ($TOTAL pairs)"
echo "proxy:    $DS_PROXY_URL"
echo "suffix:   $SUFFIX"
echo "timeout:  ${RUN_TIMEOUT:-none (production default)}"
echo "============================================================"

i=0
done_n=0
skipped=0
failed=0
active_pgid=""

cleanup_child() {
  if [ -n "$active_pgid" ]; then
    kill -TERM "-$active_pgid" 2>/dev/null || true
    sleep 2
    kill -KILL "-$active_pgid" 2>/dev/null || true
  fi
}

trap cleanup_child HUP INT TERM

while IFS=$'\t' read -r AGENT TASK; do
  i=$((i + 1))
  [ -z "$AGENT" ] && continue

  OUT="data/results/deep/${AGENT}__${TASK}_${SUFFIX}.md"
  META="data/results/deep/${AGENT}__${TASK}_${SUFFIX}.meta.json"
  if [ "$RESUME_COMPLETED" = "1" ] && python3 - "$META" "$OUT" "$BACKBONE" <<'PY'
import json, pathlib, sys
meta = pathlib.Path(sys.argv[1])
report = pathlib.Path(sys.argv[2])
backbone = sys.argv[3]
try:
    d = json.loads(meta.read_text())
    ok = report.is_file() and d.get("status") == "pass" and d.get("backbone") == backbone
except Exception:
    ok = False
raise SystemExit(0 if ok else 1)
PY
  then
    skipped=$((skipped + 1))
    echo "[$i/$TOTAL] SKIP completed $AGENT $TASK size=$(wc -c < "$OUT")"
    continue
  fi

  echo "--------"
  echo "[$i/$TOTAL] $(date '+%H:%M:%S') RUN $AGENT $TASK lane=$LANE_NAME"

  run_env=(env \
      AGENT="$AGENT" TASK="$TASK" BACKBONE="$BACKBONE" SUFFIX="$SUFFIX" \
      DS_PROXY_URL="$DS_PROXY_URL" OPENCODE_DS_PROXY="$DS_PROXY_URL")
  if [ -n "$RUN_TIMEOUT" ]; then
    # One explicit, recorded operator override. run_deep_task's watchdog owns
    # the clock and stamps timeout_contract.production_comparable=false.
    run_env+=(DRA_WALL_CLOCK_S="$RUN_TIMEOUT")
  fi
  setsid "${run_env[@]}" "$ONEAGENT" </dev/null &
  active_pgid=$!
  wait "$active_pgid"
  rc=$?
  active_pgid=""
  if [ "$rc" -eq 0 ]; then
    sz=$(wc -c < "$OUT" 2>/dev/null || echo 0)
    done_n=$((done_n + 1))
    echo "DONE $AGENT $TASK size=$sz"
  else
    failed=$((failed + 1))
    echo "FAILED $AGENT $TASK rc=$rc"
  fi

  echo "progress done=$done_n skipped=$skipped failed=$failed remaining=$((TOTAL - i))"
done < "$QUEUE"

echo "============================================================"
echo "GLM lane end=$(date '+%Y-%m-%d %H:%M:%S')"
echo "done=$done_n skipped=$skipped failed=$failed total=$TOTAL"
echo "============================================================"
