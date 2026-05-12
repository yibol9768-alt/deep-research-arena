#!/bin/bash
# Actually call _run_gpt_researcher to trigger the shims + import.
PY=/opt/deep_reserch/.venv-camel/bin/python
cd /opt/deep_reserch
$PY - <<'PYEOF'
import asyncio
import sys
sys.path.insert(0, '/opt/deep_reserch')

from scripts.run_deep_task import _run_gpt_researcher

async def go():
    # We don't actually want the agent to run - just trigger the import
    # path. So set OPENAI_API_KEY etc. won't matter; the import happens
    # at function start before any LLM call.
    try:
        await _run_gpt_researcher("test query - exit fast")
        print("FUNCTION returned (unexpected, agent should have failed gracefully)")
    except Exception as e:
        print(f"FAIL during runtime: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(go())
PYEOF
