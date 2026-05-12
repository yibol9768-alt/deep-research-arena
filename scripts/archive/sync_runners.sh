#!/bin/bash
SRC=/mnt/d/lyb/deep_reserch/scripts/runners
DST=/opt/deep_reserch/scripts/runners
for f in _runner_lock.py deerflow_runner.py qx_runner.py tongyi_runner.py \
         deepagents_runner.py local_deep_researcher_runner.py ldr_runner.py; do
    cp "$SRC/$f" "$DST/$f"
done
/opt/deep_reserch/.venv-camel/bin/python - <<'PY'
import ast, sys
for f in (
    "_runner_lock.py", "deerflow_runner.py", "qx_runner.py",
    "tongyi_runner.py", "deepagents_runner.py",
    "local_deep_researcher_runner.py", "ldr_runner.py",
):
    p = f"/opt/deep_reserch/scripts/runners/{f}"
    src = open(p).read()
    try:
        ast.parse(src)
        print(f"OK   {f} ({len(src)} bytes)")
    except SyntaxError as e:
        print(f"FAIL {f}: {e}")
        sys.exit(1)
PY
