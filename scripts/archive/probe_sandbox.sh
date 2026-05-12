#!/bin/bash
echo "=== WSL listening ports (sandbox + shim + dsproxy) ==="
ss -tlnp 2>/dev/null | grep -E ":(7770|8081|8088|8090|9999) " | head -20
echo
echo "=== shim / dsproxy processes ==="
ps -ef | grep -iE "shim|ds_proxy|search_shim|gateway|integrations" | grep -v grep | head -20
echo
echo "=== integrations dir ==="
ls -la /opt/deep_reserch/integrations 2>&1 | head -10
echo
echo "=== docker containers ==="
docker ps --format '{{.Names}} | {{.Status}} | {{.Ports}}' 2>&1 | head -10
echo
echo "=== test sandbox ports inside containers ==="
for name in webarena_shopping webarena_reddit kiwix; do
    echo -n "$name: "
    docker inspect --format '{{range .NetworkSettings.Ports}}{{range .}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}' "$name" 2>/dev/null
done
