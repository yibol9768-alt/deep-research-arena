#!/bin/bash
PIP=/opt/deep_reserch/.venv-camel/bin/pip
PY=/opt/deep_reserch/.venv-camel/bin/python
echo "=== upgrade langchain back to 1.x ==="
$PIP install --quiet 'langchain>=1.0' 'langchain-core>=1.0' 'langchain-community' 2>&1 | tail -5
echo
echo "=== verify ==="
$PIP show langchain langchain-core langchain-community 2>&1 | grep -E '^Name|^Version'
echo
echo "=== test imports ==="
$PY - <<'PYEOF'
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
