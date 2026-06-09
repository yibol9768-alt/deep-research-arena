#!/usr/bin/env bash
cd /opt/deep_reserch
export PYTHONPATH=/opt/deep_reserch PYTHONUNBUFFERED=1
export DRA_SANDBOX_CACHE=/opt/deep_reserch/data/results/sandbox_cache.json
echo "=== sandbox health ==="
ok=1
for p in 7770 9999 8090; do c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://localhost:$p/); echo "  :$p=$c"; [ "$c" = "200" ] || ok=0; done
[ "$ok" = "1" ] || { echo "SANDBOX_NOT_READY abort"; exit 3; }
echo "=== build_sandbox_cache (crawl missing URLs) $(date) ==="
python3 -u scripts/build_sandbox_cache.py --workers 6 --timeout 6
echo "=== score_grounding_from_cache (judge-free) $(date) ==="
python3 -u scripts/score_grounding_from_cache.py --out data/results/grounding_uniform.json
echo "GROUNDING_DONE=$? @ $(date)"
