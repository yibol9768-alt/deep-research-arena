#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! docker version >/dev/null 2>&1; then
  echo "Docker is not available. Start Docker Engine and retry." >&2
  exit 1
fi

shopt -s nullglob
image_archives=(images/*.tar images/*.tar.gz images/*.tgz)
if [ "${#image_archives[@]}" -eq 0 ]; then
  echo "No Docker image archives found under $ROOT/images" >&2
  exit 1
fi

for image_archive in "${image_archives[@]}"; do
  echo "[load] $image_archive"
  docker load -i "$image_archive"
done

tag_if_present() {
  local from="$1"
  local to="$2"
  if docker image inspect "$from" >/dev/null 2>&1; then
    docker tag "$from" "$to"
  fi
}

tag_if_present webarenaimages/shopping_final_0712:latest shopping_final_0712:latest
tag_if_present webarenaimages/postmill-populated-exposed-withimg:latest postmill-populated-exposed-withimg:latest

required_images=(
  shopping_final_0712:latest
  postmill-populated-exposed-withimg:latest
  dr-bench-gateway:latest
  dr-bench-ds-proxy:latest
  ghcr.io/kiwix/kiwix-serve:latest
)

missing=0
for image in "${required_images[@]}"; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "[ok] $image"
  else
    echo "[missing] $image" >&2
    missing=1
  fi
done

exit "$missing"

