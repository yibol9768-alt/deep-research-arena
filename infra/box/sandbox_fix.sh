#!/bin/bash
cd /opt/deep_reserch
echo "[fix] $(date) removing legacy duplicate sandbox containers (NOT course-kg)"
docker rm -f webarena_shopping webarena_reddit kiwix 2>/dev/null
echo "[fix] clean recreate unified stack"
docker compose -f infra/sandbox.docker-compose.yml down 2>&1 | tail -3
docker compose -f infra/sandbox.docker-compose.yml up -d 2>&1 | tail -10
echo "[fix] waiting for health"
for i in $(seq 1 48); do
  c1=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:7770/ 2>/dev/null)
  c2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:9999/ 2>/dev/null)
  c3=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:8090/ 2>/dev/null)
  echo "[fix wait $i] 7770=$c1 9999=$c2 8090=$c3"
  [ "$c1" = "200" ] && [ "$c3" = "200" ] && { echo "[fix] CORE READY"; break; }
  sleep 5
done
echo "[fix] container status:"
docker ps -a --format '{{.Names}}|{{.Status}}' | grep dr_sandbox
echo "[fix] wiki logs (if unhealthy):"
docker logs --tail 15 dr_sandbox_wiki 2>&1 | tail -15
echo "[fix] gateway logs:"
docker logs --tail 8 dr_sandbox_gateway 2>&1 | tail -8
echo "[fix] DONE $(date)"
