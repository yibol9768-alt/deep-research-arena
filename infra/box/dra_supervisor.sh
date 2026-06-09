#!/bin/bash
cd /opt/deep_reserch || exit 2
echo "[dra_sup] start $(date)"
docker start $(docker ps -aq -f name=webarena) $(docker ps -aq -f name=kiwix) 2>/dev/null
up=0
for i in $(seq 1 36); do
  c1=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:7770/ 2>/dev/null)
  c3=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:8090/ 2>/dev/null)
  echo "[dra_sup sandbox $i] 7770=$c1 8090=$c3"
  [ "$c1" = "200" ] && [ "$c3" = "200" ] && { up=1; break; }
  sleep 5
done
if [ "$up" != "1" ]; then echo "[dra_sup] SANDBOX_DOWN abort (start failed; needs compose up)"; exit 3; fi
echo "[dra_sup] sandbox UP; rescoring at CONC=2"
export CONC=2
bash /opt/deep_reserch/.dra_tmp/rescore_driver.sh
echo "[dra_sup] DONE $(date)"
