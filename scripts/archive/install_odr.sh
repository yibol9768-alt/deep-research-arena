#!/bin/bash
cd /opt/deep_reserch/third_party/langchain-open-deep-research
/opt/deep_reserch/.venv-camel/bin/pip install --quiet --no-warn-script-location -e . 2>&1 | tail -10
echo
echo "=== verify ==="
/opt/deep_reserch/.venv-camel/bin/python -c 'import open_deep_research; print("open_deep_research OK")' 2>&1 | tail -5
