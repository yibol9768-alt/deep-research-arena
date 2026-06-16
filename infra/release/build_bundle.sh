#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE_STAMP="${DATE_STAMP:-$(date +%Y%m%d)}"
RELEASE_ROOT="${RELEASE_ROOT:-/opt/dr-eval-release-${DATE_STAMP}}"
WIKI_SOURCE_DIR="${WIKI_SOURCE_DIR:-/opt/corpus/wiki}"
WIKI_SOURCE_FILE="${WIKI_SOURCE_FILE:-wikipedia_en_all_nopic.zim}"
SHOPPING_TAR_URL="${SHOPPING_TAR_URL:-http://metis.lti.cs.cmu.edu/webarena-images/shopping_final_0712.tar}"
REDDIT_TAR_URL="${REDDIT_TAR_URL:-http://metis.lti.cs.cmu.edu/webarena-images/postmill-populated-exposed-withimg.tar}"

mkdir -p "$RELEASE_ROOT"/{bin,images,wiki}

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.bak*' \
  --exclude '.cache/' \
  --exclude '.dra_tmp/' \
  --exclude '.pytest_cache/' \
  --exclude '.venv*/' \
  --exclude '__pycache__/' \
  --exclude 'logs/' \
  --exclude 'worktrees/' \
  --exclude 'frontend/node_modules/' \
  "$ROOT/" "$RELEASE_ROOT/deep_reserch/"

cp "$ROOT/infra/release/README.md" "$RELEASE_ROOT/README.md"
cp "$ROOT/infra/release/compose.yml" "$RELEASE_ROOT/compose.yml"
cp "$ROOT/infra/release/env.example" "$RELEASE_ROOT/.env.example"
cp "$ROOT/infra/release/bin/"*.sh "$RELEASE_ROOT/bin/"
chmod +x "$RELEASE_ROOT/bin/"*.sh

if [ ! -f "$RELEASE_ROOT/wiki/$WIKI_SOURCE_FILE" ]; then
  if [ ! -f "$WIKI_SOURCE_DIR/$WIKI_SOURCE_FILE" ]; then
    echo "Missing wiki file: $WIKI_SOURCE_DIR/$WIKI_SOURCE_FILE" >&2
    exit 1
  fi
  ln "$WIKI_SOURCE_DIR/$WIKI_SOURCE_FILE" "$RELEASE_ROOT/wiki/$WIKI_SOURCE_FILE" 2>/dev/null \
    || cp -n "$WIKI_SOURCE_DIR/$WIKI_SOURCE_FILE" "$RELEASE_ROOT/wiki/$WIKI_SOURCE_FILE"
fi

download_if_missing() {
  local url="$1"
  local out="$2"
  if [ -f "$out" ]; then
    echo "[exists] $out"
    return 0
  fi
  echo "[download] $url"
  if command -v aria2c >/dev/null 2>&1; then
    aria2c --continue=true --max-connection-per-server=8 --split=8 \
      --min-split-size=64M --dir "$(dirname "$out")" \
      --out "$(basename "$out")" "$url"
  else
    curl -L --fail --continue-at - --output "$out" "$url"
  fi
}

download_if_missing "$SHOPPING_TAR_URL" "$RELEASE_ROOT/images/shopping_final_0712.tar"
download_if_missing "$REDDIT_TAR_URL" "$RELEASE_ROOT/images/postmill-populated-exposed-withimg.tar"

docker build -f "$ROOT/infra/Dockerfile.gateway" -t dr-bench-gateway:latest "$ROOT"
docker build -f "$ROOT/infra/Dockerfile.ds_proxy" -t dr-bench-ds-proxy:latest "$ROOT"
docker pull ghcr.io/kiwix/kiwix-serve:latest

docker save -o "$RELEASE_ROOT/images/dr-bench-gateway.tar" dr-bench-gateway:latest
docker save -o "$RELEASE_ROOT/images/dr-bench-ds-proxy.tar" dr-bench-ds-proxy:latest
docker save -o "$RELEASE_ROOT/images/kiwix-serve.tar" ghcr.io/kiwix/kiwix-serve:latest

cat > "$RELEASE_ROOT/MANIFEST.txt" <<EOF
Deep Research Arena Docker release
Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source: $ROOT
Wiki: $WIKI_SOURCE_FILE
Shopping image tar: $(basename "$RELEASE_ROOT/images/shopping_final_0712.tar")
Reddit image tar: $(basename "$RELEASE_ROOT/images/postmill-populated-exposed-withimg.tar")
EOF

du -sh "$RELEASE_ROOT"
find "$RELEASE_ROOT" -maxdepth 2 -type f -printf '%p %s\n' | sort
