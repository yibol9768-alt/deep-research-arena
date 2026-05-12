#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep
echo "=== flowsearcher-ds reports (size + head) ==="
for f in $DIR/flowsearcher-ds__*_matrix.md; do
    [ -f "$f" ] || continue
    task=$(basename "$f" .md | sed 's/^flowsearcher-ds__//;s/_matrix//')
    size=$(wc -c < "$f")
    head=$(head -c 100 "$f" | tr '\n' ' ')
    printf "  %s  chars=%d  head=%s\n" "$task" "$size" "$head"
done | head -20
