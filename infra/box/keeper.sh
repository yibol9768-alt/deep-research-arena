#!/usr/bin/env bash
cd /opt/deep_reserch 2>/dev/null || exit 0
P=""
for i in $(seq 1 600); do
  FWD=$(grep -cs FW_JURY_DONE .dra_tmp/jury_fw.log 2>/dev/null)
  MDD=$(grep -cs MODEL_JURY_DONE .dra_tmp/jury_models.log 2>/dev/null)
  SH=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:7770/ 2>/dev/null)
  FB=$(cat data/results/real/leaderboard_jury_elo.json.battles.jsonl 2>/dev/null | wc -l)
  MB=$(cat data/results/real/leaderboard_jury_models.json.battles.jsonl 2>/dev/null | wc -l)
  CUR="fwdone=${FWD:-0} modeldone=${MDD:-0} shopping=$SH"
  if [ "$CUR" != "$P" ]; then echo "MILE $(date +%H:%M) $CUR fw_battles=$FB model_battles=$MB"; P="$CUR"; fi
  [ "${MDD:-0}" -ge 1 ] && { echo ALLDONE; break; }
  sleep 110
done
