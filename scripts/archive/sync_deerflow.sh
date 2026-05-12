#!/bin/bash
cp /mnt/d/lyb/deep_reserch/scripts/runners/deerflow_runner.py \
   /opt/deep_reserch/scripts/runners/deerflow_runner.py
/opt/deep_reserch/.venv-camel/bin/python - <<'PY'
import ast
src = open("/opt/deep_reserch/scripts/runners/deerflow_runner.py").read()
ast.parse(src)
print("SYNTAX_OK")
print(f"size={len(src)} bytes")
PY
