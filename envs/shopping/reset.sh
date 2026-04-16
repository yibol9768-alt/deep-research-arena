#!/bin/bash
# WebArena Shopping reset script
# Strategy: stop & remove container, start fresh from image.
# Image itself carries the seeded DB state, so recreate gives us clean state.

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
  status=$(docker inspect --format='{{.State.Health.Status}}' webarena_shopping 2>/dev/null || echo "unknown")
  if [ "$status" = "healthy" ]; then
    echo "[reset] healthy ($(($i * 2))s)"
    healthy=1
    break
  fi
  sleep 2
done

if [ "$healthy" != "1" ]; then
  echo "[reset] TIMEOUT: container did not become healthy in 120s"
  docker compose logs --tail=40 shopping
  exit 1
fi

# Magento seed DB pins base_url to the upstream CMU host; rewrite to local.
BASE_URL="${SHOPPING_BASE_URL:-http://localhost:7770/}"
echo "[reset] rewriting Magento base_url -> $BASE_URL"
docker exec webarena_shopping /var/www/magento2/bin/magento \
  setup:store-config:set --base-url="$BASE_URL" >/dev/null
docker exec webarena_shopping /var/www/magento2/bin/magento cache:flush >/dev/null

echo "[reset] OK"
