cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env; set +a
export JUDGE_THINKING=1 JUDGE_TIMEOUT_S=300
unset JURY_REDO_CONTAMINATED
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export DRA_SANDBOX_CACHE=/opt/deep_reserch/data/results/sandbox_cache.json
export PAIRWISE_REPORT_CAP=12000 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/deep_reserch
python3 -u scripts/build_real_leaderboard.py \
  --agents camel-ai,deerflow,smolagents,flowsearcher-ds,ii-researcher,langchain-odr,ldr,gpt-researcher,storm,qx-agents,claude-code,opencode \
  --grounding-floor 0 --n-samples 1 --judges deepseek-v4-flash,qwen3-max,glm-5 \
  --battle-workers 10 --word-budget 4000 \
  --out data/results/real/leaderboard_jury_elo.json >> .dra_tmp/jury_fw.log 2>&1
echo "FW_JURY_DONE=$? @ $(date)" >> .dra_tmp/jury_fw.log
python3 -u scripts/build_real_leaderboard.py \
  --agents eff-deepseek-v4-flash,eff-qwen3-30b-a3b-instruct-2507,eff-qwen-flash,eff-qwen3-max,eff-qwen3-32b,eff-glm-5,eff-kimi-k2.5,eff-minimax-m2.5 \
  --grounding-floor 0 --n-samples 1 --judges deepseek-v4-flash,qwen3-max,glm-5 \
  --battle-workers 10 --word-budget 4000 --limit-tasks 30 \
  --out data/results/real/leaderboard_jury_models.json >> .dra_tmp/jury_models.log 2>&1
echo "MODEL_JURY_DONE=$? @ $(date)" >> .dra_tmp/jury_models.log
