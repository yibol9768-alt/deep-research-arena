#!/usr/bin/env bash
out=""
for p in 7770 9999 8090 8081 8088; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$p/" 2>/dev/null)
  out="$out $p=$c"
done
echo "ports:$out"
