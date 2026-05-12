#!/bin/bash
# Inventory all DR frameworks available in the codebase + venvs.
ROOT=/opt/deep_reserch

echo "=== 1. Runners registered (scripts/runners/*.py) ==="
ls $ROOT/scripts/runners/*_runner.py 2>/dev/null | while read f; do
    name=$(basename "$f" _runner.py | sed 's/_/-/g')
    agent=$(grep -E '^AGENT_NAME' "$f" | head -1 | sed 's/.*= *"\(.*\)".*/\1/' | sed 's/.*= *.\(.\)/\1/')
    [ -z "$agent" ] && agent="(no AGENT_NAME)"
    printf "  %-30s AGENT_NAME=%s\n" "$(basename $f)" "$agent"
done

echo
echo "=== 2. In-process runners (in scripts/run_deep_task.py _MANUAL_RUNNERS) ==="
grep -E '^\s*"[a-z\-]+":\s*_run_' $ROOT/scripts/run_deep_task.py | sed 's/^/    /'

echo
echo "=== 3. Per-agent venvs ==="
for v in .venv-camel .venv-smol .venv-gptr .venv-storm .venv-langchain-odr .venv-ldr312 .venv-ii .venv-qx .venv-tongyi .venv-deepagents .venv-lcdr; do
    p=$ROOT/$v/bin/python
    if [ -x "$p" ]; then
        ver=$($p --version 2>&1 | head -1)
        size=$(du -sh $ROOT/$v 2>/dev/null | awk '{print $1}')
        printf "  %-25s EXISTS  %-15s  size=%s\n" "$v" "$ver" "$size"
    else
        printf "  %-25s MISSING\n" "$v"
    fi
done

echo
echo "=== 4. What's in the current leaderboard (per-agent count) ==="
DIR=$ROOT/data/results/deep_v3
for a in camel-ai deerflow flowsearcher-ds gpt-researcher ii-researcher \
         langchain-odr ldr qx-agents smolagents storm tongyi-dr \
         deepagents local-deep-researcher; do
    n=$(ls $DIR/${a}__*_matrix.score.json 2>/dev/null | wc -l)
    if [ "$n" -gt 0 ]; then
        printf "  %-25s %d score JSONs\n" "$a" "$n"
    else
        printf "  %-25s (no score JSONs)\n" "$a"
    fi
done

echo
echo "=== 5. Pre-existing reports in data/results/deep/ per agent ==="
DEEP=$ROOT/data/results/deep
for a in camel-ai deerflow flowsearcher-ds gpt-researcher ii-researcher \
         langchain-odr ldr qx-agents smolagents storm tongyi-dr \
         deepagents local-deep-researcher; do
    n=$(ls $DEEP/${a}__*_matrix.md 2>/dev/null | wc -l)
    if [ "$n" -gt 0 ]; then
        printf "  %-25s %d .md files (can be re-scored without re-running agent)\n" "$a" "$n"
    fi
done
