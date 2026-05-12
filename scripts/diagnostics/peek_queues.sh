#!/bin/bash
DIR=/opt/deep_reserch/data/results/deep_v3
for w in 1 2 3 4 5 6; do
    echo "=== worker ${w} (first 4 pairs) ==="
    head -4 "$DIR/queue_w${w}.tsv"
done
