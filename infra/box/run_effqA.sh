cd /opt/deep_reserch
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export PYTHONUNBUFFERED=1
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | tr '\n' ',' | sed 's/,$//')
python3 -u scripts/efficiency_experiment.py --models qwen3-30b-a3b-instruct-2507 --tasks "$TASKS" --shim http://localhost:8081 --out data/results/efficiency/eff_A.json >> .dra_tmp/effqA.log 2>&1
echo "EXIT_A=$? @ $(date)" >> .dra_tmp/effqA.log
