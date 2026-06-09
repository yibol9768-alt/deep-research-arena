#!/bin/bash
cd /opt/deep_reserch
set -a; . /root/.config/dra/judge.env 2>/dev/null; set +a
export CONC=3
bash .dra_tmp/rescore_driver.sh
