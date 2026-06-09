cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env 2>/dev/null; set +a
export DRA_SANDBOX_CACHE=/opt/deep_reserch/data/results/sandbox_cache.json
export JUDGE_TIMEOUT_S=30
export PYTHONUNBUFFERED=1
AGENTS="camel-ai,deerflow,smolagents,flowsearcher-ds,ii-researcher,langchain-odr,ldr,gpt-researcher,storm,qx-agents"
python3 -u scripts/build_real_leaderboard.py --agents "$AGENTS" --grounding-floor 0 --n-samples 1 \
  --out data/results/real/leaderboard_judge_elo.json > .dra_tmp/elo3.log 2>&1
echo "EXIT=$? @ $(date)" >> .dra_tmp/elo3.log
cp data/results/real/leaderboard_judge_elo.json /mnt/c/Users/liuyibo/leaderboard_judge_elo.json 2>/dev/null
