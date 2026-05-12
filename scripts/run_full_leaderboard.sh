#!/bin/bash
# Drive the full-Elo expansion: for every line of the queue file,
# run the agent on the task and score the report. Resumable: skip pairs
# whose score JSON already exists. Per-pair errors don't abort the loop.
#
# Usage (from /opt/deep_reserch):
#   nohup .venv-camel/bin/python -V > /dev/null  # keep venv loaded
#   bash scripts/run_full_leaderboard.sh \
#       data/results/deep_v3/run_queue.tsv \
#       2>&1 | tee data/results/deep_v3/run_full_leaderboard.log
#
# Or detach:
#   nohup bash scripts/run_full_leaderboard.sh queue.tsv \
#       > data/results/deep_v3/run_full_leaderboard.log 2>&1 &
#
# Tail progress:  tail -f data/results/deep_v3/run_full_leaderboard.log
# Pair count:     wc -l data/results/deep_v3/run_queue.tsv
# Done count:     ls data/results/deep_v3/*_matrix.score.json | wc -l
set -uo pipefail

QUEUE=${1:-data/results/deep_v3/run_queue.tsv}
DEEP_DIR=${DEEP_RESULTS_DIR:-data/results/deep_v3}
LOG_DIR=$(dirname "$QUEUE")
# Per-queue progress/errors so multiple parallel workers don't race-write to
# the same file. queue_w1.tsv -> queue_w1.progress / queue_w1.errors.
QUEUE_BASE=$(basename "$QUEUE" .tsv)
PROGRESS=${LOG_DIR}/${QUEUE_BASE}.progress
ERRORS=${LOG_DIR}/${QUEUE_BASE}.errors

# Production backbone: DeepSeek V4 flash via ds_proxy. Per CLAUDE.md, judge
# calls also go through ds_proxy with thinking off. Override via env if you
# really need to test against LM Studio (mixing backbones invalidates Elo
# comparison with the existing 326 scored runs).
export DS_PROXY_URL=${DS_PROXY_URL:-http://localhost:8088/v1}
export OPENAI_BASE_URL=${OPENAI_BASE_URL:-$DS_PROXY_URL}
export OPENAI_API_KEY=${OPENAI_API_KEY:-anything-proxy-uses-server-key}
export SHIM_URL=${SHIM_URL:-http://localhost:8081}
export JUDGE_BASE_URL=${JUDGE_BASE_URL:-$DS_PROXY_URL}
export JUDGE_MODEL=${JUDGE_MODEL:-deepseek-v4-flash}
# CRITICAL: judge_client.py defaults JUDGE_PROVIDER to "anthropic". Without
# this override, every judge call tries to import the anthropic SDK, fails
# with "anthropic SDK not installed", and lands judge_error on every score.
# The existing leaderboard already had ~48 such phantom failures.
export JUDGE_PROVIDER=${JUDGE_PROVIDER:-openai}
export JUDGE_API_KEY=${JUDGE_API_KEY:-${OPENAI_API_KEY:-anything}}
export SHOPPING=${SHOPPING:-http://localhost:7770}
export REDDIT=${REDDIT:-http://localhost:9999}
export WIKIPEDIA=${WIKIPEDIA:-http://localhost:8090}

BACKBONE=${BACKBONE:-deepseek-v4-flash}
PYTHON=${PYTHON:-.venv-camel/bin/python3}

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: $PYTHON not executable. Set PYTHON env var to the right venv python." >&2
    exit 2
fi

if [ ! -f "$QUEUE" ]; then
    echo "ERROR: queue file $QUEUE not found." >&2
    exit 2
fi

echo "============================================================"
echo "FULL-ELO EXPANSION  start=$(date '+%Y-%m-%d %H:%M:%S')"
echo "queue:    $QUEUE  ($(wc -l < "$QUEUE") pairs)"
echo "deep dir: $DEEP_DIR"
echo "backbone: $BACKBONE  via $DS_PROXY_URL"
echo "shim:     $SHIM_URL"
echo "============================================================"

i=0
total=$(wc -l < "$QUEUE")
done=0
skipped=0
failed=0

while IFS=$'\t' read -r AGENT TASK; do
    i=$((i + 1))
    [ -z "$AGENT" ] && continue
    SCORE=$DEEP_DIR/${AGENT}__${TASK}_matrix.score.json
    if [ -f "$SCORE" ]; then
        skipped=$((skipped + 1))
        continue
    fi

    echo "--------"
    echo "[$i/$total] $(date '+%H:%M:%S')  $AGENT  $TASK"
    echo "$(date '+%Y-%m-%d %H:%M:%S')  starting   $AGENT  $TASK" >> "$PROGRESS"

    # run_deep_task.py hardcodes its OUT_DIR to data/results/deep/. The
    # leaderboard reads from data/results/deep_v3/. So we run from deep/,
    # score, then drop the score JSON in deep_v3/. The .md sits in deep/
    # and the score.json that build_deep_leaderboard reads sits in deep_v3/.
    REPORT=data/results/deep/${AGENT}__${TASK}_matrix.md
    TIMEOUT=${RUN_TIMEOUT:-1800}   # per-pair wall-clock cap

    # 1. Run the agent
    RUN_OK=0
    if timeout "$TIMEOUT" "$PYTHON" scripts/run_deep_task.py \
        --agent "$AGENT" --task "$TASK" --backbone "$BACKBONE" \
        --out-suffix matrix; then
        RUN_OK=1
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S')  RUN-FAILED $AGENT $TASK rc=$?" >> "$ERRORS"
    fi

    # 2. Score (always attempt: even if run wrote a placeholder, scoring
    # produces a JSON the leaderboard's degenerate filter will skip).
    if [ -f "$REPORT" ]; then
        if timeout 600 "$PYTHON" scripts/score_deep_answer.py \
            --task "$TASK" --answer "$REPORT" --out "$SCORE"; then
            done=$((done + 1))
            echo "$(date '+%Y-%m-%d %H:%M:%S')  scored     $AGENT  $TASK" >> "$PROGRESS"
        else
            failed=$((failed + 1))
            echo "$(date '+%Y-%m-%d %H:%M:%S')  SCORE-FAILED $AGENT $TASK" >> "$ERRORS"
        fi
    else
        failed=$((failed + 1))
        echo "$(date '+%Y-%m-%d %H:%M:%S')  NO-REPORT  $AGENT $TASK" >> "$ERRORS"
    fi

    echo "  done=$done  skipped=$skipped  failed=$failed  remaining=$((total - i))"
done < "$QUEUE"

echo "============================================================"
echo "DONE  end=$(date '+%Y-%m-%d %H:%M:%S')"
echo "scored=$done  skipped=$skipped  failed=$failed  total=$total"
echo "============================================================"

# Rebuild leaderboard so the live page reflects the new scores.
"$PYTHON" scripts/build_deep_leaderboard.py
