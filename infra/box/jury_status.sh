cd /opt/deep_reserch 2>/dev/null || { echo UNREACHABLE; exit 0; }
fw=$(wc -l < data/results/real/leaderboard_jury_elo.json.battles.jsonl 2>/dev/null || echo 0)
md=$(wc -l < data/results/real/leaderboard_jury_models.json.battles.jsonl 2>/dev/null || echo 0)
fwd=$(grep -cs FW_JURY_DONE .dra_tmp/jury_fw.log || echo 0)
mdd=$(grep -cs MODEL_JURY_DONE .dra_tmp/jury_models.log || echo 0)
sb=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:7770/ 2>/dev/null)
echo "fw_battles=$fw model_battles=$md fw_done=$fwd model_done=$mdd shopping=$sb"
