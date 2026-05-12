#!/bin/bash
agent=$1
task=$2
/opt/deep_reserch/.venv-camel/bin/python - <<PY
import json
fp = f"/opt/deep_reserch/data/results/deep_v3/${agent}__${task}_matrix.score.json"
d = json.load(open(fp))
ur = d.get("url_reachability") or {}
det = ur.get("details") or {}
print(f"reach.score      : {ur.get('score')}")
print(f"reach.passed     : {ur.get('passed')}")
print(f"cited_total      : {det.get('cited_total')}")
print(f"http_200         : {det.get('http_200')}")
print(f"http_4xx         : {det.get('http_4xx')}")
print(f"http_5xx         : {det.get('http_5xx')}")
print(f"net_fail         : {det.get('net_fail')}")
print(f"reachability_rate: {det.get('reachability_rate')}")
print(f"threshold        : {det.get('threshold')}")
PY
