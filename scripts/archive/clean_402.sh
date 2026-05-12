#!/bin/bash
# Find score JSONs whose judges all 402'd (DeepSeek "Insufficient Balance")
# and delete them. They're filtered by _looks_degenerate anyway, but it's
# cleaner to remove them from disk so the .md reports can be re-scored
# when API credits are added.
set -u
DIR=/opt/deep_reserch/data/results/deep_v3
removed=0
for sj in "$DIR"/*_matrix.score.json; do
    if grep -q '402 -' "$sj" 2>/dev/null; then
        rm -f "$sj"
        removed=$((removed + 1))
    fi
done
echo "removed: $removed score JSONs contaminated by 402 Insufficient Balance"
echo "remaining valid score JSONs: $(ls "$DIR"/*_matrix.score.json 2>/dev/null | wc -l)"
