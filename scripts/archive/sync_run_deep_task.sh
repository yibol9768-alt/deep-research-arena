#!/bin/bash
cp /mnt/d/lyb/deep_reserch/scripts/run_deep_task.py \
   /opt/deep_reserch/scripts/run_deep_task.py
PY=/opt/deep_reserch/.venv-camel/bin/python
$PY -c "import ast; ast.parse(open('/opt/deep_reserch/scripts/run_deep_task.py').read()); print('SYNTAX_OK')"
echo
echo "=== test gpt_researcher import with shim ==="
$PY - <<'PYEOF'
import sys, types
from langchain_core.documents import Document as LCDoc
docstore = types.ModuleType("langchain.docstore")
docdoc = types.ModuleType("langchain.docstore.document")
docstore.document = docdoc
docstore.Document = LCDoc
docdoc.Document = LCDoc
sys.modules["langchain.docstore"] = docstore
sys.modules["langchain.docstore.document"] = docdoc
import gpt_researcher
print("gpt_researcher OK:", gpt_researcher.__name__)
PYEOF
