#!/bin/bash
PIP=/opt/deep_reserch/.venv-camel/bin/pip
PY=/opt/deep_reserch/.venv-camel/bin/python
$PIP show langchain-text-splitters 2>&1 | head -3
echo
$PY -c "from langchain_text_splitters import RecursiveCharacterTextSplitter; print('text_splitters OK')"
