#!/bin/bash
# Run one pre-registered queue inside an immutable run-set/backbone namespace.
# A run is resumable only by reusing RUN_SET_ID, whose manifest must still
# verify against the current clean checkout. Old reports from another model or
# code version can therefore never satisfy this run's cache check.
set -uo pipefail

QUEUE=data/results/run_queue.tsv
if [ "$#" -gt 0 ] && [ "$1" != "--model-probe" ]; then
    QUEUE=$1
    shift
fi

# Repeatable model probes use the run_manifest.py v2 contract. Operators may
# pass them directly or as newline-separated DRA_MODEL_PROBES. With neither,
# the single declared backbone is probed through DS_PROXY_URL. Setting
# DRA_MODEL_PROBES to an empty value is an explicit refusal rather than a way
# to generate a probe-free manifest.
CLI_MODEL_PROBES=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --model-probe)
            [ "$#" -ge 2 ] || { echo "ERROR: --model-probe requires a value" >&2; exit 2; }
            CLI_MODEL_PROBES+=("$2")
            shift 2
            ;;
        *)
            echo "ERROR: unknown argument $1" >&2
            exit 2
            ;;
    esac
done

BACKBONE=${BACKBONE:-deepseek-v4-flash}
RUN_SET_ID=${RUN_SET_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
RESULTS_ROOT=${DEEP_RESULTS_ROOT:-data/results/runs}
if [[ ! "$RUN_SET_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
    echo "ERROR: unsafe RUN_SET_ID=$RUN_SET_ID" >&2
    exit 2
fi
if [[ ! "$BACKBONE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
    echo "ERROR: unsafe BACKBONE=$BACKBONE" >&2
    exit 2
fi
BACKBONE_SAFE=$(printf '%s' "$BACKBONE" | tr -c 'A-Za-z0-9._-' '_')
WORKER_ID=${DRA_WORKER_ID:-0}
case "$WORKER_ID" in
    ''|*[!0-9]*) echo "ERROR: DRA_WORKER_ID must be a non-negative integer" >&2; exit 2 ;;
esac
WORKER_ID=$((10#$WORKER_ID))
# Never inherit an operator assertion as proof. These variables are exported
# only after this launcher creates a netns and passes the live worker probes.
unset DRA_EGRESS_ENFORCED DRA_ISOLATION_ACTIVE DRA_ISOLATION_PROOF
unset DRA_SUPERVISOR_SOURCE_CHECK DRA_HIDDEN_GOLD_MASKED DRA_CHROOT_ACTIVE
RUN_DIR=${RESULTS_ROOT}/${RUN_SET_ID}/${BACKBONE_SAFE}
RAW_DIR=${RUN_DIR}/raw
SCORE_DIR=${RUN_DIR}/scores
EVIDENCE_ROOT=${RUN_DIR}/evidence
if [ "$WORKER_ID" -eq 0 ]; then
    MANIFEST=${RUN_DIR}/run_manifest.json
else
    MANIFEST=${RUN_DIR}/run_manifest.worker-${WORKER_ID}.json
fi
LOG_DIR=${RUN_DIR}/logs
mkdir -p "$RAW_DIR" "$SCORE_DIR" "$EVIDENCE_ROOT" "$LOG_DIR"

QUEUE_BASE=$(basename "$QUEUE" .tsv)
PROGRESS=${LOG_DIR}/${QUEUE_BASE}.progress
ERRORS=${LOG_DIR}/${QUEUE_BASE}.errors

# Formal comparative runs use the unified multi-backbone gateway. The legacy
# DS_PROXY_URL name is retained because runners already consume it, but its
# default is the gateway, not the single-upstream :8088 proxy.
export DS_PROXY_URL=${DS_PROXY_URL:-http://localhost:8100/v1}
export OPENAI_BASE_URL=${OPENAI_BASE_URL:-$DS_PROXY_URL}
export OPENAI_API_KEY=${OPENAI_API_KEY:-anything-proxy-uses-server-key}
export JUDGE_BASE_URL=${JUDGE_BASE_URL:-$DS_PROXY_URL}
export JUDGE_MODEL=${JUDGE_MODEL:-$BACKBONE}
export JUDGE_PROVIDER=${JUDGE_PROVIDER:-openai}
export JUDGE_API_KEY=${JUDGE_API_KEY:-${OPENAI_API_KEY:-anything}}
export SHOPPING=${SHOPPING:-http://localhost:7770}
export REDDIT=${REDDIT:-http://localhost:9999}
export WIKIPEDIA=${WIKIPEDIA:-http://localhost:8090}

_SHIM_PRESET=${SHIM_URL:-}
export SHIM_URL=${SHIM_URL:-http://localhost:8081}
if [ -z "${_SHIM_PRESET}" ]; then
    export SHIM_URL="http://localhost:$((8081 + WORKER_ID))"
fi
export DRA_WORKER_ID=$WORKER_ID
export SHIM_EVIDENCE_DIR=${SHIM_EVIDENCE_DIR:-${EVIDENCE_ROOT}/worker-${WORKER_ID}}
EGRESS_PORT=${DRA_EGRESS_PORT:-$((18099 + WORKER_ID))}
QX_ADAPTER_PORT=${DRA_QX_ADAPTER_PORT:-$((19000 + WORKER_ID))}
case "$EGRESS_PORT" in
    ''|*[!0-9]*) echo "ERROR: DRA_EGRESS_PORT must be an integer" >&2; exit 6 ;;
esac
case "$QX_ADAPTER_PORT" in
    ''|*[!0-9]*) echo "ERROR: DRA_QX_ADAPTER_PORT must be an integer" >&2; exit 6 ;;
esac
EGRESS_PORT=$((10#$EGRESS_PORT))
QX_ADAPTER_PORT=$((10#$QX_ADAPTER_PORT))
if [ "$EGRESS_PORT" -lt 1 ] || [ "$EGRESS_PORT" -gt 65535 ] || \
   [ "$QX_ADAPTER_PORT" -lt 1 ] || [ "$QX_ADAPTER_PORT" -gt 65535 ] || \
   [ "$EGRESS_PORT" -eq "$QX_ADAPTER_PORT" ]; then
    echo "ERROR: invalid or colliding egress/QX worker ports" >&2
    exit 6
fi
export DRA_EGRESS_PORT=$EGRESS_PORT
export DRA_EGRESS_EVIDENCE_DIR=${EVIDENCE_ROOT}/egress-worker-${WORKER_ID}
export DRA_QX_ADAPTER_PORT=$QX_ADAPTER_PORT
export DRA_BACKBONE=$BACKBONE
export DEEP_RUN_OUT_DIR=$RAW_DIR
export DRA_RUN_SET_ID=$RUN_SET_ID
export DRA_RUN_MANIFEST=$MANIFEST

PYTHON=${PYTHON:-python3}
REPLICATES=${REPLICATES:-1}
# No comparative wall-clock by default. A positive operator override is
# recorded in the manifest and must not be presented as the standard protocol.
RUN_TIMEOUT=${RUN_TIMEOUT:-0}

if ! command -v "$PYTHON" >/dev/null 2>&1 && [ ! -x "$PYTHON" ]; then
    echo "ERROR: Python executable not found: $PYTHON" >&2
    exit 2
fi

# Build two disjoint origin sets. Corpus origins are the only responses that
# count as page evidence. Shim/model/router/QX origins stay reachable through
# the door but can never manufacture proof-of-fetch. Both loopback spellings
# are included because framework URLs use both.
ORIGIN_OUTPUT=$("$PYTHON" - \
    "$SHOPPING" "$REDDIT" "$WIKIPEDIA" \
    "$SHIM_URL" "$DS_PROXY_URL" "$OPENAI_BASE_URL" "$JUDGE_BASE_URL" \
    "$DRA_QX_ADAPTER_PORT" <<'PY'
import sys
from urllib.parse import urlsplit


def parsed_origin(raw, label):
    try:
        parsed = urlsplit(raw)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("must be an http URL with a hostname")
        port = parsed.port or 80
    except Exception as exc:
        raise SystemExit(f"{label}={raw!r} is not a valid formal origin: {exc}")
    return parsed.hostname.lower(), port


def add_origin(out, host, port):
    if host in {"localhost", "127.0.0.1"}:
        out.add(f"localhost:{port}")
        out.add(f"127.0.0.1:{port}")
    else:
        out.add(f"{host}:{port}")


corpus = set()
source_origins = set()
for label, raw in zip(("SHOPPING", "REDDIT", "WIKIPEDIA"), sys.argv[1:4]):
    host, port = parsed_origin(raw, label)
    if port == 17770:
        raise SystemExit(
            f"{label} uses retired internal port 17770; formal public store port is 7770"
        )
    source_origins.add((host, port))
    add_origin(corpus, host, port)
if len(source_origins) != 3:
    raise SystemExit("SHOPPING, REDDIT and WIKIPEDIA must be three distinct origins")

services = set()
for label, raw in zip(
    ("SHIM_URL", "DS_PROXY_URL", "OPENAI_BASE_URL", "JUDGE_BASE_URL"),
    sys.argv[4:8],
):
    host, port = parsed_origin(raw, label)
    add_origin(services, host, port)

qx_port = int(sys.argv[8])
for port in [8100, *range(3461, 3464), *range(3470, 3490), qx_port]:
    add_origin(services, "localhost", port)

overlap = corpus & services
if overlap:
    raise SystemExit(
        "egress corpus/service origins overlap: " + ", ".join(sorted(overlap))
    )
print(",".join(sorted(corpus)))
print(",".join(sorted(services)))
PY
) || exit 6
if [[ "$ORIGIN_OUTPUT" != *$'\n'* ]]; then
    echo "ERROR: failed to construct egress corpus/service origins" >&2
    exit 6
fi
export DRA_EGRESS_CORPUS=${ORIGIN_OUTPUT%%$'\n'*}
export DRA_EGRESS_SERVICES=${ORIGIN_OUTPUT#*$'\n'}

if [ ! -f "$QUEUE" ]; then
    echo "ERROR: queue file $QUEUE not found" >&2
    exit 2
fi
case "$REPLICATES" in
    ''|*[!0-9]*|0) echo "ERROR: REPLICATES must be a positive integer" >&2; exit 2 ;;
esac

# GOAL_GATES_V1 permanent fixture (docs/GOAL_GATES_V1.md): the two leaderboard
# properties are enforced by the deterministic goal gates, and a formal run may
# not start unless the workstation-runnable gates are green. This is the hard
# automated entry point the goal doc calls a "常驻项". Placed after the cheap
# arg/origin/queue fail-fast checks (so those keep their exit codes) but before
# any isolation setup or lane process. --quick is the 13-task subset; rc!=0
# aborts here.
echo "== goal gates (run_gates.py --quick) =="
if ! "$PYTHON" scripts/run_gates.py --quick; then
    echo "ERROR: goal gates are not green; refusing to start (GOAL_GATES_V1)" >&2
    exit 5
fi

# Build a real production boundary before any manifest probe or lane process.
# The worker namespace has no default route. Its nftables policy permits only
# the root-owned recording door and explicit host service ports, and the lane
# later runs as a dedicated non-root uid with no capabilities.
ISOLATION_TOKEN=$("$PYTHON" - "$RUN_SET_ID" "$BACKBONE" "$WORKER_ID" <<'PY'
import hashlib, sys
print(hashlib.sha256("\0".join(sys.argv[1:]).encode()).hexdigest()[:16])
PY
) || exit 6
ISOLATION_STATE_ROOT=${DRA_ISOLATION_STATE_ROOT:-/run/dra-isolation}
ISOLATION_STATE=${ISOLATION_STATE_ROOT}/worker-${ISOLATION_TOKEN}.json
ISOLATION_PROOF_DIR=${RUN_DIR}/isolation/proofs
ISOLATION_AUDIT=${RUN_DIR}/isolation/isolation_audit.json
WORKER_HOME=${RUN_DIR}/isolation/worker-home-${WORKER_ID}
EGRESS_PID=""
ISOLATION_READY=0

cleanup_production_boundary() {
    if [ -n "${EGRESS_PID:-}" ]; then
        if kill -0 "$EGRESS_PID" 2>/dev/null; then
            kill "$EGRESS_PID" 2>/dev/null || true
        fi
        wait "$EGRESS_PID" 2>/dev/null || true
        EGRESS_PID=""
    fi
    if [ "${ISOLATION_READY:-0}" -eq 1 ]; then
        "$PYTHON" scripts/production_isolation.py cleanup \
            --state "$ISOLATION_STATE" >/dev/null 2>&1 || true
        ISOLATION_READY=0
    fi
}
trap cleanup_production_boundary EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$PYTHON" scripts/production_isolation.py setup \
    --state "$ISOLATION_STATE" \
    --run-set-id "$RUN_SET_ID" --backbone "$BACKBONE" \
    --worker-id "$WORKER_ID" --egress-port "$EGRESS_PORT" \
    --evidence-dir "$DRA_EGRESS_EVIDENCE_DIR" \
    --canonical-evidence-dir "$SHIM_EVIDENCE_DIR" \
    --raw-dir "$RAW_DIR" --worker-home "$WORKER_HOME" \
    --proof-dir "$ISOLATION_PROOF_DIR" \
    --repository-root "$(pwd -P)" \
    --corpus-origins "$DRA_EGRESS_CORPUS" \
    --service-origins "$DRA_EGRESS_SERVICES" || exit 6
ISOLATION_READY=1
ISOLATION_GATEWAY=$("$PYTHON" scripts/production_isolation.py get \
    --state "$ISOLATION_STATE" --field gateway) || exit 6
export DRA_EGRESS_PROXY=http://${ISOLATION_GATEWAY}:${EGRESS_PORT}
export DRA_EGRESS_CONTROL_URL=$DRA_EGRESS_PROXY
export DRA_EGRESS_SERVER_MERGE=1

# Save canonical service URLs for the through-proxy probe, then rewrite local
# service doors to the host side of the worker veth. A namespace's localhost is
# intentionally private and cannot address host services.
PUBLIC_SHIM_URL=$SHIM_URL
rewrite_loopback_url() {
    "$PYTHON" - "$1" "$ISOLATION_GATEWAY" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit
p = urlsplit(sys.argv[1])
host = sys.argv[2] if (p.hostname or "").lower() in {"localhost", "127.0.0.1"} else p.hostname
port = f":{p.port}" if p.port else ""
print(urlunsplit((p.scheme, f"{host}{port}", p.path, p.query, p.fragment)))
PY
}
export SHIM_URL=$(rewrite_loopback_url "$SHIM_URL") || exit 6
export DS_PROXY_URL=$(rewrite_loopback_url "$DS_PROXY_URL") || exit 6
export OPENAI_BASE_URL=$(rewrite_loopback_url "$OPENAI_BASE_URL") || exit 6
export JUDGE_BASE_URL=$(rewrite_loopback_url "$JUDGE_BASE_URL") || exit 6
export DRA_EGRESS_SERVICES=$("$PYTHON" - "$DRA_EGRESS_SERVICES" "$ISOLATION_GATEWAY" <<'PY'
import sys
origins = {item for item in sys.argv[1].split(",") if item}
gateway = sys.argv[2]
for origin in list(origins):
    _, sep, port = origin.rpartition(":")
    if sep:
        origins.add(f"{gateway}:{port}")
print(",".join(sorted(origins)))
PY
) || exit 6

# These are production gates, not advisory diagnostics. Runtime RUNNERS and
# the protocol must be exactly equal, every queued lane/task must be declared,
# and no fallback control may enter the formal process environment.
"$PYTHON" scripts/verify_run_set.py formal-env || exit 5
"$PYTHON" scripts/verify_run_set.py lane-parity --queue "$QUEUE" || exit 5

MODEL_PROBES=()
if [ "${#CLI_MODEL_PROBES[@]}" -gt 0 ]; then
    MODEL_PROBES=("${CLI_MODEL_PROBES[@]}")
elif [ -n "${DRA_MODEL_PROBES+x}" ]; then
    while IFS= read -r probe; do
        [ -n "$probe" ] && MODEL_PROBES+=("$probe")
    done <<< "${DRA_MODEL_PROBES}"
else
    MODEL_PROBES+=("${DS_PROXY_URL},${BACKBONE},OPENAI_API_KEY,${BACKBONE}")
fi
if [ "${#MODEL_PROBES[@]}" -eq 0 ]; then
    echo "ERROR: a formal run requires at least one --model-probe" >&2
    exit 7
fi
MANIFEST_PROBE_ARGS=()
for probe in "${MODEL_PROBES[@]}"; do
    MANIFEST_PROBE_ARGS+=(--model-probe "$probe")
done

# A resumed run must be byte-comparable to the checkout doing the resume.
# First creation is delegated to run_manifest's fail-closed CLI. Credential
# values stay in named environment variables and never enter argv or JSON.
if [ -f "$MANIFEST" ]; then
    "$PYTHON" scripts/run_manifest.py --verify "$MANIFEST" --reports-dir "$RUN_DIR" || exit 7
else
    MANIFEST_TMP=${MANIFEST}.tmp.$$
    rm -f "$MANIFEST_TMP"
    "$PYTHON" scripts/run_manifest.py --out "$MANIFEST_TMP" \
        "${MANIFEST_PROBE_ARGS[@]}" || { rm -f "$MANIFEST_TMP"; exit 7; }
    mv "$MANIFEST_TMP" "$MANIFEST"
fi
"$PYTHON" scripts/verify_run_set.py manifest \
    --manifest "$MANIFEST" --run-set-id "$RUN_SET_ID" --backbone "$BACKBONE" \
    --compare-current-env || exit 7

# Never reuse a process already listening on this worker's door. /healthz does
# not expose its evidence directory, so a healthy foreign process is still
# unverifiable and must fail closed.
"$PYTHON" - "$ISOLATION_GATEWAY" "$EGRESS_PORT" <<'PY' || exit 6
import socket
import sys

sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind((sys.argv[1], int(sys.argv[2])))
except OSError as exc:
    raise SystemExit(
        f"egress door {sys.argv[1]}:{sys.argv[2]} is already occupied: {exc}"
    )
finally:
    sock.close()
PY

EGRESS_LOG=${LOG_DIR}/egress-worker-${WORKER_ID}.log
SHIM_EVIDENCE_DIR="$DRA_EGRESS_EVIDENCE_DIR" \
SHIM_EVIDENCE=1 \
DRA_EGRESS_CORPUS="$DRA_EGRESS_CORPUS" \
DRA_EGRESS_SERVICES="$DRA_EGRESS_SERVICES" \
DRA_EGRESS_CANONICAL_EVIDENCE_DIR="$SHIM_EVIDENCE_DIR" \
    "$PYTHON" -m integrations.egress_proxy.app \
        --host "$ISOLATION_GATEWAY" --port "$EGRESS_PORT" >>"$EGRESS_LOG" 2>&1 &
EGRESS_PID=$!

EGRESS_READY=0
for _ in $(seq 1 100); do
    if ! kill -0 "$EGRESS_PID" 2>/dev/null; then
        break
    fi
    EGRESS_HEALTH=$(curl --noproxy '*' -fsS --max-time 1 \
        "${DRA_EGRESS_CONTROL_URL%/}/healthz" 2>/dev/null) || EGRESS_HEALTH=""
    if [ -n "$EGRESS_HEALTH" ] && "$PYTHON" -c '
import json, sys
health = json.loads(sys.argv[1])
raise SystemExit(0 if health.get("ok") is True
                 and health.get("recording") is True
                 and health.get("server_merge") is True
                 and health.get("active_run") is None else 1)
' "$EGRESS_HEALTH"; then
        EGRESS_READY=1
        break
    fi
    sleep 0.1
done
if [ "$EGRESS_READY" -ne 1 ]; then
    echo "ERROR: owned egress proxy failed readiness at $DRA_EGRESS_PROXY" >&2
    tail -20 "$EGRESS_LOG" >&2 2>/dev/null || true
    exit 6
fi

# The shim process, not this shell, owns the evidence directory. Refuse a
# mismatched externally-launched shim rather than mixing workers in one log.
SHIM_STATUS=$(curl --noproxy '*' -fsS --max-time 10 "${SHIM_URL%/}/_evidence/status") || {
    echo "ERROR: shim unavailable at $SHIM_URL" >&2; exit 6;
}
"$PYTHON" - "$SHIM_STATUS" "$SHIM_EVIDENCE_DIR" <<'PY' || exit 6
import json, os, sys
got = os.path.realpath(json.loads(sys.argv[1]).get("dir") or "")
want = os.path.realpath(sys.argv[2])
if got != want:
    raise SystemExit(f"shim evidence dir mismatch: shim={got!r}, run={want!r}")
PY

# Hidden answer keys and the URL registry never enter the worker chroot. Run
# the registry-dependent source check here in the trusted supervisor, then pass
# only the boolean disposition into the lane metadata.
"$PYTHON" - <<'PY' || exit 6
from scripts.preflight import check_search_hits_are_in_corpus, check_sources_alive

results = check_sources_alive() + check_search_hits_are_in_corpus()
for result in results:
    print(result)
if not results or any(result.ok is not True for result in results):
    raise SystemExit("trusted source/registry preflight did not pass")
PY
export DRA_SUPERVISOR_SOURCE_CHECK=1

# Run live probes from the exact uid, capability set, and network namespace
# used by every lane. Corpus liveness is first proven through the recorder.
# Then curl --noproxy, requests trust_env=False, raw sockets, host/container
# aliases, public HTTP/HTTPS/DNS, and recorder-file mutation must all fail.
PROOF_PATH=$("$PYTHON" scripts/production_isolation.py probe \
    --state "$ISOLATION_STATE" \
    --egress-control-url "$DRA_EGRESS_CONTROL_URL" \
    --shim-control-url "$SHIM_URL" \
    --corpus-url "${SHOPPING%/}/" \
    --service-url "${PUBLIC_SHIM_URL%/}/_evidence/status" \
    --service-direct-url "${SHIM_URL%/}/_evidence/status") || exit 6
export DRA_ISOLATION_PROOF=$PROOF_PATH
export DRA_ISOLATION_ACTIVE=1
export DRA_EGRESS_ENFORCED=1
"$PYTHON" scripts/production_isolation.py check \
    --state "$ISOLATION_STATE" --proof "$DRA_ISOLATION_PROOF" || exit 6

echo "============================================================"
echo "DRA RUN SET start=$(date '+%Y-%m-%d %H:%M:%S')"
echo "run_set: $RUN_SET_ID"
echo "backbone: $BACKBONE"
echo "queue:    $QUEUE ($(wc -l < "$QUEUE") pairs)"
echo "raw:      $RAW_DIR"
echo "evidence: $SHIM_EVIDENCE_DIR"
echo "egress:   $DRA_EGRESS_PROXY -> $DRA_EGRESS_EVIDENCE_DIR"
echo "isolation: netns proof=$DRA_ISOLATION_PROOF"
echo "repeats:  $REPLICATES"
echo "============================================================"

i=0; done_n=0; skipped=0; failed=0
total=$(( $(wc -l < "$QUEUE") * REPLICATES ))
while IFS=$'\t' read -r AGENT TASK; do
    [ -z "$AGENT" ] && continue
    for REP in $(seq 1 "$REPLICATES"); do
        i=$((i + 1))
        SUFFIX="rep${REP}"
        REPORT=${RAW_DIR}/${AGENT}__${TASK}_${SUFFIX}.md
        META=${RAW_DIR}/${AGENT}__${TASK}_${SUFFIX}.meta.json
        SCORE=${SCORE_DIR}/${AGENT}__${TASK}_${SUFFIX}.score.json

        # Namespace isolation plus a matching pass meta is the cache key. A bare
        # score file is never enough: interrupted writes and failed reruns remain
        # runnable.
        if [ -f "$SCORE" ] && [ -f "$META" ] && [ -f "$REPORT" ] && \
           "$PYTHON" scripts/production_isolation.py verify-meta \
                --proof-dir "$ISOLATION_PROOF_DIR" --meta "$META" >/dev/null && \
           "$PYTHON" scripts/verify_run_set.py verify-entry \
                --score "$SCORE" --meta "$META" --report "$REPORT" \
                --manifest "$MANIFEST" --run-set-id "$RUN_SET_ID" \
                --backbone "$BACKBONE" --replicate "$REP" \
                --agent "$AGENT" --task "$TASK" >/dev/null
        then
            skipped=$((skipped + 1)); continue
        fi

        echo "[$i/$total] $(date '+%H:%M:%S') $AGENT $TASK rep=$REP"
        echo "$(date '+%FT%T') starting $AGENT $TASK rep=$REP" >> "$PROGRESS"
        # A stale score must not survive a failed rerun and pair with the new
        # report/meta. It can never be a cache hit after verify-entry rejected
        # it, so remove only this generated score artifact before execution.
        rm -f "$SCORE"
        if [ "$RUN_TIMEOUT" -gt 0 ] 2>/dev/null; then
            timeout "$RUN_TIMEOUT" "$PYTHON" scripts/production_isolation.py exec \
                --state "$ISOLATION_STATE" -- \
                "$PYTHON" scripts/run_deep_task.py --agent "$AGENT" \
                --task "$TASK" --backbone "$BACKBONE" --out-suffix "$SUFFIX"
        else
            "$PYTHON" scripts/production_isolation.py exec \
                --state "$ISOLATION_STATE" -- \
                "$PYTHON" scripts/run_deep_task.py --agent "$AGENT" \
                --task "$TASK" --backbone "$BACKBONE" --out-suffix "$SUFFIX"
        fi
        run_rc=$?
        if [ "$run_rc" -ne 0 ]; then
            failed=$((failed + 1))
            echo "$(date '+%FT%T') RUN-FAILED $AGENT $TASK rep=$REP rc=$run_rc" >> "$ERRORS"
            continue
        fi
        if [ ! -f "$REPORT" ]; then
            failed=$((failed + 1))
            echo "$(date '+%FT%T') NO-REPORT $AGENT $TASK rep=$REP" >> "$ERRORS"
            continue
        fi
        if [ ! -f "$META" ] || \
           ! "$PYTHON" scripts/production_isolation.py verify-meta \
                --proof-dir "$ISOLATION_PROOF_DIR" --meta "$META" || \
           ! "$PYTHON" scripts/verify_run_set.py bind-entry \
            --report "$REPORT" --meta "$META" --manifest "$MANIFEST" \
            --run-set-id "$RUN_SET_ID" --backbone "$BACKBONE" \
            --replicate "$REP" --agent "$AGENT" --task "$TASK"; then
            failed=$((failed + 1))
            echo "$(date '+%FT%T') INTEGRITY-FAILED $AGENT $TASK rep=$REP" >> "$ERRORS"
            continue
        fi
        SCORE_TMP=${SCORE}.tmp.$$
        rm -f "$SCORE_TMP"
        if timeout 600 "$PYTHON" scripts/score_deep_answer.py \
            --task "$TASK" --answer "$REPORT" --out "$SCORE_TMP" && \
           "$PYTHON" scripts/verify_run_set.py verify-entry \
            --score "$SCORE_TMP" --meta "$META" --report "$REPORT" \
            --manifest "$MANIFEST" --run-set-id "$RUN_SET_ID" \
            --backbone "$BACKBONE" --replicate "$REP" \
            --agent "$AGENT" --task "$TASK"; then
            mv "$SCORE_TMP" "$SCORE"
            done_n=$((done_n + 1))
        else
            rm -f "$SCORE_TMP"
            failed=$((failed + 1))
            echo "$(date '+%FT%T') SCORE-OR-INTEGRITY-FAILED $AGENT $TASK rep=$REP" >> "$ERRORS"
        fi
    done
done < "$QUEUE"

echo "DONE run_set=$RUN_SET_ID scored=$done_n skipped=$skipped failed=$failed total=$total"
echo "Results stay isolated under $RUN_DIR; do not merge them into a legacy board."
rm -f "$ISOLATION_AUDIT"
if ! "$PYTHON" scripts/production_isolation.py audit-meta \
    --proof-dir "$ISOLATION_PROOF_DIR" --meta-dir "$RAW_DIR" \
    --out "$ISOLATION_AUDIT" >/dev/null; then
    echo "ERROR: network-isolation artifact audit failed; see $ISOLATION_AUDIT" >&2
    exit 9
fi
INTEGRITY_REPORT=${RUN_DIR}/integrity_report.json
rm -f "$INTEGRITY_REPORT"
if ! "$PYTHON" scripts/verify_run_set.py audit \
    --run-set-dir "${RESULTS_ROOT}/${RUN_SET_ID}" --out "$INTEGRITY_REPORT"; then
    echo "ERROR: run-set integrity audit failed; see $INTEGRITY_REPORT" >&2
    exit 9
fi
if [ "$failed" -ne 0 ]; then
    echo "ERROR: $failed entries failed and the run set is incomplete" >&2
    exit 8
fi
