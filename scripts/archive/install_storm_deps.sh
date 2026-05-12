#!/bin/bash
# Install storm + co-storm deps into .venv-camel so the bulk runner stops
# skipping them. Done on a live venv: pip is atomic per-file, the running
# bulk run will only see new packages when it next re-imports the runner
# module (i.e. on its next storm/co-storm pair).
set -e
cd /opt/deep_reserch
PIP=.venv-camel/bin/pip

echo "=== current state ==="
.venv-camel/bin/python -c "
import importlib
for mod in ['numpy','dspy','knowledge_storm','sentence_transformers']:
    try:
        m = importlib.import_module(mod)
        print(f'{mod:25s} = OK ({getattr(m, \"__version__\", \"?\")})')
    except Exception as e:
        print(f'{mod:25s} = MISSING ({type(e).__name__})')
"

echo
echo "=== installing missing packages ==="
# dspy-ai is the right pip name for the `import dspy` package.
# knowledge-storm is Stanford STORM's PyPI name.
# sentence-transformers is a STORM transitive dep.
$PIP install --quiet --no-input \
    numpy \
    sentence-transformers \
    dspy-ai \
    knowledge-storm \
    2>&1 | tail -20

echo
echo "=== post-install state ==="
.venv-camel/bin/python -c "
import importlib
ok = True
for mod in ['numpy','dspy','knowledge_storm','sentence_transformers']:
    try:
        m = importlib.import_module(mod)
        print(f'{mod:25s} = OK ({getattr(m, \"__version__\", \"?\")})')
    except Exception as e:
        ok = False
        print(f'{mod:25s} = STILL MISSING: {type(e).__name__}: {e}')
print()
print('ALL OK' if ok else 'SOME PACKAGES STILL MISSING')
"

echo
echo "=== try importing the runner modules ==="
.venv-camel/bin/python -c "
import sys
sys.path.insert(0, '.')
from scripts.runners import registry
runners, errs = registry.discover()
print('registered:', sorted(runners.keys()))
print('import errors:', errs)
"
