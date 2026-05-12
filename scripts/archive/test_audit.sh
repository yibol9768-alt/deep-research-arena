#!/bin/bash
cd /opt/deep_reserch
echo "=== audit existing 2 pairs ==="
for f in data/results/deep_v3/deerflow__dr_cross_deep_0001_matrix.score.json \
         data/results/deep_v3/deerflow__dr_cross_deep_0002_matrix.score.json; do
    .venv-camel/bin/python scripts/audit_one_pair.py "$f"
done
echo
echo "=== inotifywait available? ==="
which inotifywait || echo "MISSING"
