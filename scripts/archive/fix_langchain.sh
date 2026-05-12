#!/bin/bash
PIP=/opt/deep_reserch/.venv-camel/bin/pip
PY=/opt/deep_reserch/.venv-camel/bin/python
echo "=== gpt-researcher ==="
$PIP show gpt-researcher 2>&1 | head -5
echo
echo "=== langchain ==="
$PIP show langchain langchain-community langchain-core 2>&1 | head -15
echo
echo "=== install langchain-community ==="
$PIP install --quiet langchain-community 2>&1 | tail -10
echo
echo "=== test ==="
$PY -c 'from langchain.docstore import document; print("docstore OK")' 2>&1 | head -3
$PY -c 'import gpt_researcher; print("gpt_researcher OK")' 2>&1 | head -3
