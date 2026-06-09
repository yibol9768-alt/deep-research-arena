#!/bin/bash
cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env 2>/dev/null; set +a
python3 scripts/score_presentation_field.py --workers 8 --out data/results/presentation_uniform.json
cp data/results/presentation_uniform.json /mnt/c/Users/liuyibo/presentation_uniform.json 2>/dev/null
echo DONE_PRES
