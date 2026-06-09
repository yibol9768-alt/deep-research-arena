cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env; set +a
export JUDGE_THINKING=1
export JUDGE_TIMEOUT_S=60
export JURY_REDO_CONTAMINATED=1
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export DRA_SANDBOX_CACHE=/opt/deep_reserch/data/results/sandbox_cache.json
export PAIRWISE_REPORT_CAP=30000
export PYTHONUNBUFFERED=1
export PYTHONPATH=/opt/deep_reserch
python3 -u scripts/build_real_leaderboard.py \
  --agents camel-ai,deerflow,smolagents,flowsearcher-ds,ii-researcher,langchain-odr,ldr,gpt-researcher,storm,qx-agents \
  --grounding-floor 0 --n-samples 1 --judges deepseek-v4-flash,qwen3-max,glm-5 \
  --battle-workers 3 --word-budget 4000 \
  --out data/results/real/leaderboard_jury_elo.json >> .dra_tmp/jury_contam.log 2>&1
echo "CONTAM_EXIT=$? @ $(date)" >> .dra_tmp/jury_contam.log
