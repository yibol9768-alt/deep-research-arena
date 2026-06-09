cd /opt/deep_reserch
TASKS=$(ls data/results/deep/deerflow__dr_cross_deep_*_matrix.md | sed -E 's/.*(dr_cross_deep_[0-9]+).*/\1/' | sort -u)
echo "$TASKS" | xargs -P3 -I{} bash scripts/runners/claudecode_wsl.sh {} claude-code claude >> .dra_tmp/cc_batch.log 2>&1
echo "CC_BATCH_DONE=$? @ $(date)" >> .dra_tmp/cc_batch.log
