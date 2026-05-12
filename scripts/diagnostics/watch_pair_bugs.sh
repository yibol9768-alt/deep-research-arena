#!/bin/bash
# Polling watcher: emits one line per newly-landed score JSON during the bulk
# Elo run. Each line is either ``OK <agent> <task> ...`` or ``BUG <agent>
# <task>: <reason>``. inotifywait not installed in this WSL, so we poll.
#
# Designed to be run as a Monitor — every emitted line becomes a notification.
# Polls every 15s; pair turnover is ~13 min so this is plenty fine-grained.

set -u
cd /opt/deep_reserch
DIR=data/results/deep_v3
SEEN=/tmp/audited_pairs.seen

# Seed the seen-set with the files that already existed when the watcher
# started. This way the first poll only reports NEW pairs, not the historical
# ones (we already audited 0001/0002 manually before arming this).
mkdir -p "$(dirname "$SEEN")"
ls "$DIR"/*_matrix.score.json 2>/dev/null | sort > "$SEEN"

while true; do
    CUR=$(ls "$DIR"/*_matrix.score.json 2>/dev/null | sort)
    NEW=$(comm -13 "$SEEN" <(echo "$CUR") 2>/dev/null)
    if [ -n "$NEW" ]; then
        echo "$NEW" | while read -r fp; do
            # tiny grace window so the writer can finish the JSON
            sleep 1
            .venv-camel/bin/python scripts/audit_one_pair.py "$fp" 2>&1
        done
        echo "$CUR" > "$SEEN"
    fi
    sleep 15
done
