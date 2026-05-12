#!/bin/bash
# One-shot deploy: tar deep_reserch → scp to westd → untar in Ubuntu WSL →
# pip install → playwright install chromium → docker load → compose up.
#
# Assumes:
#   - ~/.ssh/config has `westd` alias (免密)
#   - /root/webarena/shopping_final_0712.tar exists on server (fully downloaded)
#   - WSL Ubuntu has docker + systemd + proxy env set
#
# Run from deep_reserch/ on the Mac.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

TARBALL="/tmp/deep_reserch_deploy.tgz"
REMOTE_WIN_DIR="C:/tools"
REMOTE_WSL_DIR="/root/deep_reserch"

echo "[deploy] packing tarball (excludes webarena_ref, paper_*, caches)..."
tar czf "$TARBALL" \
  --exclude='webarena_ref' \
  --exclude='paper_dr_lab' \
  --exclude='paper_survey' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.egg-info' \
  -C "$(dirname "$HERE")" "$(basename "$HERE")"
du -h "$TARBALL"

echo "[deploy] scp to westd:$REMOTE_WIN_DIR ..."
scp "$TARBALL" "westd:$REMOTE_WIN_DIR/"

echo "[deploy] untar + install + load + up on server..."
ssh westd 'wsl -d Ubuntu -- bash -c "
set -e
source /etc/environment
rm -rf /root/deep_reserch.bak 2>/dev/null || true
[ -d /root/deep_reserch ] && mv /root/deep_reserch /root/deep_reserch.bak
mkdir -p /root/deep_reserch
cd /root
tar xzf /mnt/c/tools/deep_reserch_deploy.tgz
ls -la /root/deep_reserch | head

echo --- pip install ---
apt-get install -y -qq python3-pip python3-venv
cd /root/deep_reserch
python3 -m venv .venv
. .venv/bin/activate
pip install --quiet --no-cache-dir -r requirements.txt
python3 -m playwright install chromium
python3 -m playwright install-deps chromium 2>&1 | tail -5

echo --- unit tests ---
python3 -m pytest tests/test_verifiers.py -q

echo --- docker load ---
if [ -f /root/webarena/shopping_final_0712.tar ] && [ \$(stat -c %s /root/webarena/shopping_final_0712.tar) -gt 60000000000 ]; then
  if ! docker image inspect shopping_final_0712:latest >/dev/null 2>&1; then
    docker load -i /root/webarena/shopping_final_0712.tar
    docker tag shopping_final_0712 shopping_final_0712:latest
  else
    echo \"image already loaded\"
  fi
else
  echo \"WARN: shopping_final_0712.tar not fully downloaded yet, skipping load\"
fi

echo --- compose up ---
cd /root/deep_reserch/envs/shopping
./reset.sh || true
curl -sI http://localhost:7770/ | head -3

echo --- smoke test ---
cd /root/deep_reserch
. .venv/bin/activate
SHOPPING=http://localhost:7770 python3 scripts/smoke_test_pipeline.py 158 | tail -30
"
'

echo ""
echo "[deploy] done."
