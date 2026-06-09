cd /opt/deep_reserch
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export PYTHONUNBUFFERED=1
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | tr '\n' ',' | sed 's/,$//')
echo "task count: $(echo $TASKS | tr ',' '\n' | wc -l)"
python3 -u scripts/efficiency_experiment.py --models qwen3-30b-a3b-instruct-2507,qwen3-32b,qwen-flash,qwen3-max --tasks "$TASKS" --shim http://localhost:8081 --out data/results/efficiency/efficiency_full.json
echo "EXIT=$? @ $(date)"
