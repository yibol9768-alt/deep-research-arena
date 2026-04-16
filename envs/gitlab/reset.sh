#!/bin/bash
# WebArena GitLab reset. GitLab bootstraps *slowly* (Rails + Postgres +
# Redis + Sidekiq + Puma + Nginx all in one container); `start_period`
# is 180s and overall boot can still take 3-5 minutes on a cold start.

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "[reset] stopping container (if any)..."
docker compose down -v --remove-orphans 2>/dev/null || true

echo "[reset] starting fresh..."
docker compose up -d

echo "[reset] waiting for healthy (gitlab cold start ≈ 3-5 min)..."
healthy=0
for i in $(seq 1 180); do
  status=$(docker inspect --format='{{.State.Health.Status}}' webarena_gitlab 2>/dev/null || echo "unknown")
  if [ "$status" = "healthy" ]; then
    echo "[reset] healthy ($(($i * 2))s)"
    healthy=1
    break
  fi
  sleep 2
done

if [ "$healthy" != "1" ]; then
  echo "[reset] TIMEOUT: container did not become healthy in 360s"
  docker compose logs --tail=60 gitlab
  exit 1
fi

echo "[reset] OK"
