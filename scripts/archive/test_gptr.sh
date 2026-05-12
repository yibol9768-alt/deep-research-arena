#!/bin/bash
cp /mnt/d/lyb/deep_reserch/scripts/run_deep_task.py /opt/deep_reserch/scripts/run_deep_task.py
PY=/opt/deep_reserch/.venv-camel/bin/python
$PY -c "import ast; ast.parse(open('/opt/deep_reserch/scripts/run_deep_task.py').read()); print('SYNTAX_OK')"
echo
echo "=== test gpt_researcher import via run_deep_task ==="
$PY -c "
import asyncio
import sys
sys.path.insert(0, '/opt/deep_reserch')
from scripts.run_deep_task import _run_gpt_researcher
print('runner imports OK')
" 2>&1 | head -10
echo
echo "=== test gpt_researcher with all shims (legacy) ==="
$PY - <<'PYEOF'
import sys, types
from langchain_core.documents import Document as LCDoc
from langchain_core.vectorstores import VectorStore as LCVS

def shim(name, attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m

shim("langchain.docstore", {"Document": LCDoc})
shim("langchain.docstore.document", {"Document": LCDoc})
sys.modules["langchain.docstore"].document = sys.modules["langchain.docstore.document"]
shim("langchain.vectorstores", {"VectorStore": LCVS})

try:
    import gpt_researcher
    print("gpt_researcher import OK")
    from gpt_researcher import GPTResearcher
    print("GPTResearcher class OK")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
PYEOF
