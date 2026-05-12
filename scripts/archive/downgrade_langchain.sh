#!/bin/bash
PIP=/opt/deep_reserch/.venv-camel/bin/pip
PY=/opt/deep_reserch/.venv-camel/bin/python
echo "=== before ==="
$PIP show langchain langchain-core langchain-community langchain-tavily 2>&1 | grep -E '^Name|^Version'
echo
echo "=== downgrading langchain ==="
$PIP install --quiet 'langchain<1.0' 'langchain-community<1.0' 'langchain-core<1.0' 2>&1 | tail -10
echo
echo "=== after ==="
$PIP show langchain langchain-core langchain-community langchain-tavily 2>&1 | grep -E '^Name|^Version'
echo
echo "=== test imports ==="
$PY - <<'PYEOF'
try:
    import gpt_researcher
    print("gpt_researcher OK")
except Exception as e:
    print(f"gpt_researcher FAIL: {e}")
try:
    import open_deep_research
    print("open_deep_research OK")
except Exception as e:
    print(f"open_deep_research FAIL: {e}")
try:
    import smolagents
    print("smolagents OK")
except Exception as e:
    print(f"smolagents FAIL: {e}")
PYEOF
