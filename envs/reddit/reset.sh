#!/bin/bash
# WebArena Reddit (Postmill) reset script.
# The `postmill-populated-exposed-withimg` image carries a seeded DB and
# serves forum content at http://<host>:9999/ (Symfony routing reads the
# Host header, so no base_url rewrite is needed — unlike Magento).

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "[reset] stopping container (if any)..."
docker compose down -v --remove-orphans 2>/dev/null || true

echo "[reset] starting fresh..."
docker compose up -d

echo "[reset] waiting for healthy..."
healthy=0
for i in $(seq 1 60); do
  status=$(docker inspect --format='{{.State.Health.Status}}' webarena_reddit 2>/dev/null || echo "unknown")
  if [ "$status" = "healthy" ]; then
    echo "[reset] healthy ($(($i * 2))s)"
    healthy=1
    break
  fi
  sleep 2
done

if [ "$healthy" != "1" ]; then
  echo "[reset] TIMEOUT: container did not become healthy in 120s"
  docker compose logs --tail=40 reddit
  exit 1
fi

# Postmill reads host from incoming request headers → no URL rewrite needed.
# (Contrast with Magento shopping which pins base_url in the DB.)

echo "[reset] OK"
