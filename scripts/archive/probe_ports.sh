#!/bin/bash
echo "=== sandbox + shim + ds_proxy connectivity ==="
for port_name in "7770:shop" "9999:reddit" "8090:wiki" "8081:shim" "8088:dsproxy"; do
    port="${port_name%:*}"
    name="${port_name#*:}"
    code=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "http://localhost:$port/" 2>/dev/null)
    printf "%-12s port %5s -> HTTP %s\n" "$name" "$port" "$code"
done
echo
echo "=== shim health ==="
curl -s --max-time 5 http://localhost:8081/health 2>&1 | head -c 200
echo
echo
echo "=== dsproxy /v1/models ==="
curl -s --max-time 5 http://localhost:8088/v1/models 2>&1 | head -c 200
