cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env 2>/dev/null; set +a
export DASHSCOPE_BASE_URL=https://api.deepseek.com/v1
export DASHSCOPE_API_KEY="$JUDGE_API_KEY"
export PYTHONUNBUFFERED=1
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | tr '\n' ',' | sed 's/,$//')
python3 -u scripts/efficiency_experiment.py --models deepseek-v4-flash --tasks "$TASKS" --shim http://localhost:8081 --out data/results/efficiency/ds_resume.json >> .dra_tmp/dsq_resume.log 2>&1
