#!/bin/bash
# Poll sandbox until shopping (Magento) + reddit (Postmill) are 200 OK or
# timeout at 240s. Returns 0 on healthy, 1 on still-down.
set -e
DEADLINE=$(($(date +%s) + 240))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    s=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" http://localhost:7770/ 2>/dev/null)
    r=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" http://localhost:9999/ 2>/dev/null)
    w=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" http://localhost:8090/ 2>/dev/null)
    echo "$(date +%H:%M:%S)  shop:$s reddit:$r wiki:$w"
    if [[ "$s" == "200" || "$s" == "302" ]] && [[ "$r" == "200" || "$r" == "302" ]] && [[ "$w" == "200" ]]; then
        echo "sandbox healthy."
        exit 0
    fi
    sleep 15
done
echo "sandbox not healthy after 240s."
exit 1
