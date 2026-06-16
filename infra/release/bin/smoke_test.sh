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

SHOPPING_PORT="${SHOPPING_PORT:-7770}"
REDDIT_PORT="${REDDIT_PORT:-9999}"
WIKI_PORT="${WIKI_PORT:-8090}"
GATEWAY_PORT="${GATEWAY_PORT:-8081}"

check_url() {
  local name="$1"
  local url="$2"
  echo "[check] $name $url"
  curl -fsS "$url" >/dev/null
}

check_url gateway "http://localhost:${GATEWAY_PORT}/healthz"
check_url shopping "http://localhost:${SHOPPING_PORT}/"
check_url reddit "http://localhost:${REDDIT_PORT}/"
check_url wiki "http://localhost:${WIKI_PORT}/"

echo "[ok] all sandbox services respond"

