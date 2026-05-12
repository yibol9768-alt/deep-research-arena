#!/bin/bash
PY=/opt/deep_reserch/.venv-camel/bin/python
echo "=== .venv-camel modules ==="
for mod in gpt_researcher open_deep_research smolagents storm camel knowledge_storm langchain_openai; do
    out=$($PY -c "import $mod; print('${mod}: OK')" 2>&1 | head -1)
    echo "$out"
done
echo
echo "=== other venvs exist? ==="
for v in .venv-camel .venv-smol .venv-gptr .venv-storm .venv-langchain-odr .venv-ldr312 .venv-ii .venv-qx .venv-tongyi; do
    if [ -x "/opt/deep_reserch/$v/bin/python" ]; then
        echo "$v EXISTS"
    else
        echo "$v MISSING"
    fi
done
