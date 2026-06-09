cd /opt/deep_reserch
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export SHIM_URL=http://localhost:8081
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md 2>/dev/null | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | paste -sd,)
echo "=== minimax batch @ $(date) ===" >> .dra_tmp/effminimax.log
python3 -u scripts/efficiency_experiment.py --models MiniMax-M2.5 --tasks "$TASKS" \
  --out data/results/efficiency/vendor_minimax-m2.5.json >> .dra_tmp/effminimax.log 2>&1
echo "EFFMINIMAX_DONE @ $(date)" >> .dra_tmp/effminimax.log
