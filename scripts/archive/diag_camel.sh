#!/bin/bash
echo "=== ds_proxy_lm log tail ==="
tail -40 /tmp/ds_proxy_lm.log 2>&1

echo
echo "=== camel-ai process resource usage ==="
ps -o pid,etime,pcpu,pmem,cmd -p 24359 2>&1

echo
echo "=== latest camel-ai .md report (in deep/) ==="
ls -lt /opt/deep_reserch/data/results/deep/camel-ai__dr_cross_deep_0001* 2>&1 | head -5

echo
echo "=== open TCP connections to LM Studio ==="
ss -tan state established 2>/dev/null | grep -E ':(1234|8089)' | head -10

echo
echo "=== tail of run log (last 5 lines) ==="
tail -5 /opt/deep_reserch/data/results/deep_v3/run_full_leaderboard.log 2>&1
