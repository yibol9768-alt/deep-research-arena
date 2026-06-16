#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

export SHOPPING_PORT="${SHOPPING_PORT:-7770}"
export REDDIT_PORT="${REDDIT_PORT:-9999}"
export WIKI_PORT="${WIKI_PORT:-8090}"
export GATEWAY_PORT="${GATEWAY_PORT:-8081}"
export WIKI_ZIM_DIR="${WIKI_ZIM_DIR:-$ROOT/wiki}"
export WIKI_ZIM_FILE="${WIKI_ZIM_FILE:-}"

if [ -z "$WIKI_ZIM_FILE" ]; then
  WIKI_ZIM_FILE="$(find "$WIKI_ZIM_DIR" -maxdepth 1 -name '*.zim' -printf '%f\n' | sort | head -n 1)"
  export WIKI_ZIM_FILE
fi

if [ -z "$WIKI_ZIM_FILE" ] || [ ! -f "$WIKI_ZIM_DIR/$WIKI_ZIM_FILE" ]; then
  echo "No wiki ZIM file found. Put one under $WIKI_ZIM_DIR or set WIKI_ZIM_FILE." >&2
  exit 1
fi

if [ -z "${WIKI_KIWIX_BOOK:-}" ]; then
  export WIKI_KIWIX_BOOK="${WIKI_ZIM_FILE%.zim}"
fi

docker compose -f compose.yml up -d

wait_container_healthy() {
  local container="$1"
  local limit="${2:-90}"
  local status
  for _ in $(seq 1 "$limit"); do
    status="$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
    if [ "$status" = "healthy" ]; then
      echo "[healthy] $container"
      return 0
    fi
    sleep 2
  done
  echo "[timeout] $container did not become healthy" >&2
  docker logs --tail=80 "$container" >&2 || true
  return 1
}

wait_container_healthy dr_sandbox_shopping 90
wait_container_healthy dr_sandbox_reddit 60
wait_container_healthy dr_sandbox_wiki 60
wait_container_healthy dr_sandbox_gateway 60

shopping_base_url="${SHOPPING_BASE_URL:-http://localhost:${SHOPPING_PORT}/}"
echo "[shopping] setting Magento base_url to $shopping_base_url"
docker exec dr_sandbox_shopping /var/www/magento2/bin/magento \
  setup:store-config:set --base-url="$shopping_base_url" >/dev/null
docker exec dr_sandbox_shopping /var/www/magento2/bin/magento cache:flush >/dev/null

echo "[ready] sandbox gateway: http://localhost:${GATEWAY_PORT}"

