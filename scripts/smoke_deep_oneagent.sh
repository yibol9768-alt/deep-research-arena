#!/bin/bash
# Run one agent on dr_cross_deep_0001 with DS backbone via westd ds_proxy.
#
# Usage on westd WSL:
#   AGENT=gpt-researcher bash /tmp/smoke_deep_oneagent.sh
#   AGENT=smolagents bash /tmp/smoke_deep_oneagent.sh
#   AGENT=camel-ai bash /tmp/smoke_deep_oneagent.sh
#   AGENT=langchain-odr bash /tmp/smoke_deep_oneagent.sh
#
set -e
cd /opt/deep_reserch

AGENT="${AGENT:?must set AGENT=gpt-researcher|smolagents|camel-ai|langchain-odr|...}"
TASK="${TASK:-dr_cross_deep_0001}"
SUFFIX="${SUFFIX:-smoke}"

# pick venv per agent
case "$AGENT" in
  gpt-researcher) VENV=.venv-gptr ;;
  smolagents)     VENV=.venv-smol ;;
  camel-ai)       VENV=.venv-camel ;;
  langchain-odr)  VENV=.venv-langchain-odr ;;
  storm)          VENV=.venv-storm ;;
  deerflow)       VENV=.venv-camel ;;       # uses subprocess into deerflow's own venv
  ldr)            VENV=.venv-ldr312 ;;     # py3.10 .venv-ldr lacks datetime.UTC
  ii-researcher)  VENV=.venv-ii ;;
  qx-agents)      VENV=.venv-camel ;;       # uses subprocess into .venv-qx
  dzhng)          VENV=.venv-camel ;;       # only requests; any venv works
  *) echo "unknown agent $AGENT"; exit 2 ;;
esac

source "$VENV/bin/activate"
echo "venv: $(which python)"

# Mihomo for any external HTTPS (tiktoken BPE, model registry, etc).
# localhost / 172.30.48.1 must bypass so shim/proxy/sandbox aren't routed back through it.
export HTTPS_PROXY=http://172.30.48.1:7890
export HTTP_PROXY=http://172.30.48.1:7890
export NO_PROXY=localhost,127.0.0.1,172.30.48.1

# DS proxy + sandbox URLs
export DS_PROXY_URL=http://localhost:8088/v1
export OPENAI_BASE_URL=http://localhost:8088/v1
export OPENAI_API_BASE=http://localhost:8088/v1
export OPENAI_API_KEY=anything-proxy-uses-server-key
export SHIM_URL=http://localhost:8081
export GPTR_SHIM_URL=http://localhost:8081
export SHOPPING=http://localhost:7770
export REDDIT=http://localhost:9999
export WIKIPEDIA=http://localhost:8090
export TAVILY_API_KEY=tvly-shim-fake

echo "== sanity =="
curl -sS --max-time 5 http://localhost:8088/healthz; echo
curl -sS --max-time 5 http://localhost:8081/healthz; echo

echo "== running $AGENT on $TASK =="
timeout 1400 python3 scripts/run_deep_task.py \
  --agent "$AGENT" \
  --task "$TASK" \
  --backbone deepseek-v4-flash \
  --out-suffix "$SUFFIX" 2>&1 | tail -200
