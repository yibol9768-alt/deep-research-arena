#!/bin/bash
cd /opt/deep_reserch
tmux has-session -t keepalive 2>/dev/null || tmux new -d -s keepalive "sleep infinity"
tmux has-session -t watchdog 2>/dev/null || tmux new -d -s watchdog "bash /opt/deep_reserch/.dra_tmp/watchdog.sh"
tmux has-session -t statusrep 2>/dev/null || tmux new -d -s statusrep "bash /opt/deep_reserch/.dra_tmp/status_reporter.sh"
if docker ps >/dev/null 2>&1 && [ "$(docker ps -q | wc -l)" -lt 5 ]; then
  docker compose -f /opt/deep_reserch/infra/sandbox.docker-compose.yml up -d >/dev/null 2>&1
fi
tmux has-session -t dsproxy 2>/dev/null || tmux new -d -s dsproxy "cd /opt/deep_reserch; OPENAI_PROXY_UPSTREAM=https://api.deepseek.com uvicorn integrations.ds_proxy.app:app --host 0.0.0.0 --port 8088 > .dra_tmp/dsproxy.log 2>&1"
tmux has-session -t shim 2>/dev/null || tmux new -d -s shim "cd /opt/deep_reserch; uvicorn integrations.search_shim.app:app --host 0.0.0.0 --port 8081 > .dra_tmp/shim.log 2>&1"
tmux has-session -t wiki 2>/dev/null || tmux new -d -s wiki "/opt/kiwix/kiwix-serve --port 8090 /opt/corpus/wiki/wikipedia_en_all_nopic.zim > /opt/deep_reserch/.dra_tmp/wiki.log 2>&1"
date >> /opt/deep_reserch/.dra_tmp/boot.log
