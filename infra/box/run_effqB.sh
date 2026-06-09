cd /opt/deep_reserch
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export PYTHONUNBUFFERED=1
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | tr '\n' ',' | sed 's/,$//')
python3 -u scripts/efficiency_experiment.py --models qwen-flash,qwen3-max --tasks "$TASKS" --shim http://localhost:8081 --out data/results/efficiency/eff_B.json >> .dra_tmp/effqB.log 2>&1
echo "EXIT_B=$? @ $(date)" >> .dra_tmp/effqB.log
