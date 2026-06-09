cd /opt/deep_reserch
while true; do
  curl -s -o /dev/null --max-time 4 http://localhost:8090/ 2>/dev/null || nohup /opt/kiwix/kiwix-serve --port 8090 /opt/corpus/wiki/wikipedia_en_all_nopic.zim >/dev/null 2>&1 &
  if ! grep -qs MODEL_JURY_DONE .dra_tmp/jury_models.log && ! tmux has-session -t juries 2>/dev/null && ! pgrep -f build_real_leaderboard >/dev/null 2>&1; then
    echo "$(date '+%F %T') juries dead -> resume" >> .dra_tmp/watchdog.log
    tmux new -d -s juries "bash /opt/deep_reserch/.dra_tmp/run_juries.sh" 2>/dev/null
  fi
  sleep 120
done
