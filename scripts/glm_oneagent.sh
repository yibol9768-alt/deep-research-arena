#!/usr/bin/env bash
set -euo pipefail

cd /opt/deep_reserch

AGENT="${AGENT:?must set AGENT}"
TASK="${TASK:?must set TASK}"
BACKBONE="${BACKBONE:-glm-4.7-flash}"
SUFFIX="${SUFFIX:-glmflash}"
DS_PROXY_URL="${DS_PROXY_URL:?must set DS_PROXY_URL, e.g. http://127.0.0.1:8089/v1}"

case "$AGENT" in
  camel-ai)       VENV=.venv-camel ;;
  claude-code)    VENV=.venv-camel ;;
  deerflow)       VENV=.venv-camel ;;
  flowsearcher-ds) VENV=.venv-camel ;;
  gpt-researcher) VENV=.venv-gptr ;;
  ii-researcher)  VENV=.venv-ii ;;
  langchain-odr)  VENV=.venv-langchain-odr ;;
  ldr)            VENV=.venv-ldr312 ;;
  opencode)       VENV=.venv-camel ;;
  qx-agents)      VENV=.venv-camel ;;
  smolagents)     VENV=.venv-smol ;;
  storm)          VENV=.venv-storm ;;
  *) echo "unknown agent $AGENT" >&2; exit 2 ;;
esac

source "$VENV/bin/activate"

export BACKBONE
export DS_PROXY_URL
export OPENAI_BASE_URL="$DS_PROXY_URL"
export OPENAI_API_BASE="$DS_PROXY_URL"
export OPENAI_API_KEY="${OPENAI_API_KEY:-anything-proxy-uses-server-key}"
export FAST_LLM="openai:${BACKBONE}"
export SMART_LLM="openai:${BACKBONE}"
export STRATEGIC_LLM="openai:${BACKBONE}"
export RETRIEVER="tavily"
export EMBEDDING="custom:text-embedding-v4"

export SHIM_URL="${SHIM_URL:-http://127.0.0.1:8081}"
export GPTR_SHIM_URL="$SHIM_URL"
export SHOPPING="${SHOPPING:-http://localhost:7770}"
export REDDIT="${REDDIT:-http://localhost:9999}"
export WIKIPEDIA="${WIKIPEDIA:-http://localhost:8090}"
export WIKIPEDIA_KIWIX_URL="${WIKIPEDIA_KIWIX_URL:-http://localhost:8090}"
export KIWIX="${KIWIX:-http://localhost:8090}"
export TAVILY_API_KEY="tvly-shim-fake"
export TIKTOKEN_CACHE_DIR="${TIKTOKEN_CACHE_DIR:-/root/tiktoken_cache}"

# CLI runners read these directly.
export OPENCODE_MODEL="${OPENCODE_MODEL:-ds-shim/${BACKBONE}}"
export OPENCODE_DS_PROXY="${OPENCODE_DS_PROXY:-$DS_PROXY_URL}"
# SSH/Windows is opt-in.  A default host silently changes the execution
# surface and turns a weak local output into a second, incomparable attempt.
if [ -n "${CLAUDE_CODE_SSH_HOST:-}" ]; then export CLAUDE_CODE_SSH_HOST; fi
if [ -n "${OPENCODE_SSH_HOST:-}" ]; then export OPENCODE_SSH_HOST; fi

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="*"

python3 scripts/run_deep_task.py \
  --agent "$AGENT" \
  --task "$TASK" \
  --backbone "$BACKBONE" \
  --out-suffix "$SUFFIX"
