#!/usr/bin/env bash
cd /opt/deep_reserch 2>/dev/null || { echo UNREACHABLE; exit 0; }
d=data/results/deep
echo "cc=$(ls $d/claude-code__*_matrix.md 2>/dev/null|wc -l) oc=$(ls $d/opencode__*_matrix.md 2>/dev/null|wc -l) glm=$(ls $d/eff-glm-5__*_matrix.md 2>/dev/null|wc -l) kimi=$(ls $d/eff-kimi-k2.5__*_matrix.md 2>/dev/null|wc -l) mm=$(ls $d/eff-minimax-m2.5__*_matrix.md 2>/dev/null|wc -l)"
