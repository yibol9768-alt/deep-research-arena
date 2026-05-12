#!/bin/bash
cd /opt/deep_reserch
for t in 0001 0005; do
  echo "===$t==="
  DS_PROXY_URL=http://localhost:8088/v1 SHIM_URL=http://localhost:8081 timeout 1900 .venv-camel/bin/python scripts/run_deep_task.py --agent gpt-researcher --task dr_cross_deep_$t --backbone deepseek-v4-flash --out-suffix smoketest 2>&1 | tail -10
done
