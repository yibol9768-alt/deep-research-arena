#!/bin/bash
# Sync the V2 codebase from Mac to westd's /opt/deep_reserch.
#
# westd's /opt/deep_reserch is NOT a git checkout — code is maintained
# via rsync. This script pushes the directories that V2 actually changed,
# excludes data and venvs.
#
# Usage:
#   bash infra/sync_to_westd.sh           # dry-run
#   bash infra/sync_to_westd.sh --apply   # actually sync

set -euo pipefail

LOCAL=/Users/liuyibo/Desktop/lyb/deep_reserch
REMOTE_HOST=my5090
# Bridge through C:/tools/ because rsync can't write directly into WSL paths
# without sshd running INSIDE WSL.
REMOTE_BRIDGE=C:/tools/dr_v2_sync
REMOTE_TARGET=/opt/deep_reserch

DRYRUN="-n"
if [[ "${1:-}" == "--apply" ]]; then
  DRYRUN=""
fi

DIRS=(
  "infra"
  "integrations"
  "scripts"
  "src"
  "tests"
  "docs"
)

FILES=(
  "CONTRIBUTING.md"
  "CLAUDE.md"
  "claude.md"
)

EXCLUDES=(
  "--exclude=data/results/"
  "--exclude=.venv-*"
  "--exclude=__pycache__/"
  "--exclude=.pytest_cache/"
  "--exclude=*.pyc"
  "--exclude=node_modules/"
  "--exclude=.git/"
)

echo ">>> rsync ${DRYRUN:-(apply mode)} from $LOCAL → ${REMOTE_HOST}:${REMOTE_BRIDGE}"
for d in "${DIRS[@]}"; do
  rsync -avz $DRYRUN "${EXCLUDES[@]}" \
    "$LOCAL/$d/" "${REMOTE_HOST}:${REMOTE_BRIDGE}/$d/"
done
for f in "${FILES[@]}"; do
  [[ -f "$LOCAL/$f" ]] && rsync -avz $DRYRUN \
    "$LOCAL/$f" "${REMOTE_HOST}:${REMOTE_BRIDGE}/$f"
done

if [[ "$DRYRUN" == "" ]]; then
  echo ">>> bridging to WSL Ubuntu's $REMOTE_TARGET"
  ssh "$REMOTE_HOST" "wsl -d Ubuntu -- bash -lc \
    'rsync -av --delete-after /mnt/c/tools/dr_v2_sync/ ${REMOTE_TARGET}/ \
       --exclude data/results/ --exclude .venv-*'"
  echo ">>> verifying"
  ssh "$REMOTE_HOST" "wsl -d Ubuntu -- bash -lc \
    'cd ${REMOTE_TARGET} && ls integrations/agents/ | wc -l \
     && ls infra/ && head -3 CONTRIBUTING.md'"
fi

echo ">>> done"
