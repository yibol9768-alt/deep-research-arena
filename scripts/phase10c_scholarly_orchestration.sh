#!/bin/bash
# Phase 10c orchestration (simplified DS path): 7 agents × 4 scholarly tasks.
# All OpenAI-compat agents run with .env defaults (DS backend).
# React agents use Anthropic-compat via glm_react_agent.
# Each run's output is renamed to match rescore AGENTS patterns.

set -u
cd /opt/deep_reserch

ROOT=/opt/deep_reserch
RESULTS="$ROOT/data/results"
ORCH_DIR="$ROOT/.orch"
STATUS="$ORCH_DIR/orch_status.log"
mkdir -p "$ORCH_DIR"
SCHOLARLY=(0088 0095 0100 0105)

: > "$STATUS"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$STATUS"; }

set -a
source .env
set +a
log "env loaded (DS backend default)"

log "(re)starting shim on 8081"
pkill -f "uvicorn.*search_shim.app" 2>/dev/null || true
sleep 1
setsid nohup ./.venv-camel/bin/uvicorn integrations.search_shim.app:app \
  --host 0.0.0.0 --port 8081 \
  > "$ORCH_DIR/shim.log" 2>&1 < /dev/null &
disown
sleep 4
ss -tlnp 2>/dev/null | grep -q :8081 || { log "SHIM FAIL — abort"; exit 1; }
log "shim OK"

safe_rename() {
  local src="$1" dst="$2"
  if [ -s "$src" ] && [ "$(stat -c%s "$src")" -gt 500 ]; then
    mv -f "$src" "$dst"
    log "    rename: $(basename "$src") → $(basename "$dst") ($(stat -c%s "$dst") B)"
  else
    log "    rename SKIP: $(basename "$src") missing or tiny ($( [ -f "$src" ] && stat -c%s "$src" || echo 0) B)"
  fi
}

# Check if target file already exists with reasonable size — if so, skip work.
# usage: have_target <path>   (returns 0 if target already present and >500B)
have_target() {
  [ -s "$1" ] && [ "$(stat -c%s "$1")" -gt 500 ]
}

run_cmd() {
  local tag="$1"; shift
  local t="$1"; shift
  [ "${1:-}" = "--" ] && shift
  log "  ▶ $tag (timeout=${t}s)"
  local t0 rc
  t0=$(date +%s)
  timeout "$t" "$@" > "$ORCH_DIR/run_${tag}.log" 2>&1
  rc=$?
  log "  ◀ $tag done rc=$rc in $(( $(date +%s) - t0 ))s"
  return $rc
}

for tid in "${SCHOLARLY[@]}"; do
  TID="dr_cross_v3_${tid}"
  log "======== task $TID ========"

  # --- gpt-researcher-ds ---
  if have_target "$RESULTS/gpt-researcher-ds_${TID}.md"; then
    log "  = skip gptr_ds_${tid} (target exists)"
  else
    (
      export GPTR_ONLY_TASK="$TID"
      run_cmd "gptr_ds_${tid}" 1800 -- ./.venv-gptr/bin/python scripts/run_gpt_researcher.py || true
    )
    safe_rename "$RESULTS/gpt-researcher_${TID}.md" "$RESULTS/gpt-researcher-ds_${TID}.md"
  fi

  # --- camel-ai-ds ---
  if have_target "$RESULTS/camel-ai-ds_${TID}.md"; then
    log "  = skip camel_ds_${tid} (target exists)"
  else
    (
      export CAMEL_ONLY_TASK="$TID"
      run_cmd "camel_ds_${tid}" 1800 -- ./.venv-camel/bin/python scripts/run_camel_ai.py || true
    )
    safe_rename "$RESULTS/camel-ai_${TID}.md" "$RESULTS/camel-ai-ds_${TID}.md"
  fi

  # --- smolagents-ds ---
  if have_target "$RESULTS/smolagents-ds_${TID}.md"; then
    log "  = skip smol_ds_${tid} (target exists)"
  else
    (
      export SMOL_ONLY_TASK="$TID"
      run_cmd "smol_ds_${tid}" 1800 -- ./.venv-smol/bin/python scripts/run_smolagents.py || true
    )
    safe_rename "$RESULTS/smolagents_${TID}.md" "$RESULTS/smolagents-ds_${TID}.md"
  fi

  # --- odr-ds ---
  if have_target "$RESULTS/open-deep-research-ds_${TID}.md"; then
    log "  = skip odr_ds_${tid} (target exists)"
  else
    (
      export ODR_ONLY_TASK="$TID"
      run_cmd "odr_ds_${tid}" 1800 -- ./.venv-odr/bin/python scripts/run_open_deep_research.py || true
    )
    safe_rename "$RESULTS/open-deep-research_${TID}.md" "$RESULTS/open-deep-research-ds_${TID}.md"
  fi

  # --- deerflow-ds ---
  if have_target "$RESULTS/deerflow-ds_${TID}.md"; then
    log "  = skip deer_ds_${tid} (target exists)"
  else
    (
      export DEERFLOW_ONLY_TASK="$TID"
      run_cmd "deer_ds_${tid}" 1800 -- ./.venv-camel/bin/python scripts/run_deerflow_cross.py || true
    )
    safe_rename "$RESULTS/deerflow_${TID}.md" "$RESULTS/deerflow-ds_${TID}.md"
  fi

  # --- react-qwen35plus (GLM via Anthropic-compat @ ANTHROPIC_BASE_URL) ---
  if have_target "$RESULTS/final_react-qwen35plus_${TID}.answer.md"; then
    log "  = skip react_qwen_${tid} (target exists)"
  else
    (
      run_cmd "react_qwen_${tid}" 1800 -- ./.venv/bin/python scripts/bench_v3.py react --no-judge --no-pairwise --tasks "$TID" --model qwen3.5-plus || true
    )
    newest=$(ls -t "$RESULTS"/react-qwen35plus_${TID}_*.answer.md 2>/dev/null | head -1 || true)
    if [ -n "${newest:-}" ]; then
      safe_rename "$newest" "$RESULTS/final_react-qwen35plus_${TID}.answer.md"
    else
      log "    react-qwen35plus: no timestamped output found"
    fi
  fi

  # --- react-glm5 (GLM-5.1 via Anthropic-compat) ---
  if have_target "$RESULTS/final_react-glm5_${TID}.answer.md"; then
    log "  = skip react_glm5_${tid} (target exists)"
  else
    (
      run_cmd "react_glm5_${tid}" 1800 -- ./.venv/bin/python scripts/bench_v3.py react --no-judge --no-pairwise --tasks "$TID" --model glm-5.1 || true
    )
    newest=$(ls -t "$RESULTS"/react-glm5_${TID}_*.answer.md 2>/dev/null | head -1 || true)
    if [ -n "${newest:-}" ]; then
      safe_rename "$newest" "$RESULTS/final_react-glm5_${TID}.answer.md"
    else
      log "    react-glm5: no timestamped output found"
    fi
  fi

done

log "==========  orch COMPLETE  =========="

# summary
for tid in "${SCHOLARLY[@]}"; do
  TID="dr_cross_v3_${tid}"
  for f in \
    "gpt-researcher-ds_${TID}.md" \
    "camel-ai-ds_${TID}.md" \
    "smolagents-ds_${TID}.md" \
    "open-deep-research-ds_${TID}.md" \
    "deerflow-ds_${TID}.md" \
    "final_react-qwen35plus_${TID}.answer.md" \
    "final_react-glm5_${TID}.answer.md"; do
    if [ -s "$RESULTS/$f" ]; then
      log "  ✓ $f ($(stat -c%s "$RESULTS/$f") B)"
    else
      log "  ✗ $f MISSING"
    fi
  done
done

log "ALL DONE"
