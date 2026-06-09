cd /opt/deep_reserch
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY in env}
export SHIM_URL=http://localhost:8081
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md 2>/dev/null | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u | paste -sd,)
for M in glm-5 kimi-k2.5; do
  echo "=== vendor batch $M @ $(date) ===" >> .dra_tmp/effvendors.log
  python3 -u scripts/efficiency_experiment.py --models "$M" --tasks "$TASKS" \
    --out data/results/efficiency/vendor_$(echo $M|tr 'A-Z' 'a-z').json >> .dra_tmp/effvendors.log 2>&1
done
echo "EFFVENDORS_DONE @ $(date)" >> .dra_tmp/effvendors.log
