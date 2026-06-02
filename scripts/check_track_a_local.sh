#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_PY="/Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
MODE="${1:-all}"

case "${MODE}" in
  all|import|track-a|core) ;;
  *)
    echo "Usage: $0 [all|import|track-a|core]" >&2
    exit 2
    ;;
esac

if [[ -n "${PYTHON_BIN:-}" ]]; then
  # Allow simple overrides like python3 and command-style overrides like
  # "uv run python" for pre-existing uv environments.
  read -r -a PYTHON_CMD <<< "${PYTHON_BIN}"
elif [[ -x "${CODEX_PY}" ]]; then
  PYTHON_CMD=("${CODEX_PY}")
else
  PY3="$(command -v python3 || true)"
  if [[ -z "${PY3}" ]]; then
    echo "No python3 found. Set PYTHON_BIN to a Python 3.12 interpreter." >&2
    exit 127
  fi
  PYTHON_CMD=("${PY3}")
fi

cd "${ROOT}"
export PYTHONPATH=.

echo "Using Python: ${PYTHON_CMD[*]}"
echo "Running import check"
"${PYTHON_CMD[@]}" - <<'PY'
import importlib

modules = [
    "src.rl.env",
    "src.rl.backends",
    "src.rl.action_parser",
    "src.rl.tools",
    "src.rl.tools_write",
    "src.rl.tools_vision",
    "src.rl.tools_rag",
    "src.rl.user_sim",
    "src.verifiers.state_diff_verifier",
]

for name in modules:
    importlib.import_module(name)
print("import check ok")
PY

if [[ "${MODE}" == "import" ]]; then
  exit 0
fi

if "${PYTHON_CMD[@]}" - <<'PY' >/dev/null 2>&1
import pytest  # noqa: F401
PY
then
  PYTEST_CMD=("${PYTHON_CMD[@]}" -m pytest)
elif command -v uv >/dev/null 2>&1; then
  if [[ ${#PYTHON_CMD[@]} -eq 1 ]]; then
    PYTEST_CMD=(uv run --offline --python "${PYTHON_CMD[0]}" --with pytest pytest)
  else
    PYTEST_CMD=(uv run --offline --with pytest pytest)
  fi
else
  echo "pytest is not importable from this Python and uv is unavailable." >&2
  echo "Run the import check with: bash scripts/check_track_a_local.sh import" >&2
  exit 1
fi

TRACK_A_TESTS=(
  tests/test_action_parser.py
  tests/test_tool_registry.py
  tests/test_tools_write.py
  tests/test_state_diff_verifier.py
  tests/test_user_sim.py
  tests/test_tools_vision.py
  tests/test_computeruse_policy.py
  tests/test_tools_rag.py
  tests/test_build_rag_index.py
  tests/test_modality_parity.py
)

CORE_SMOKE_TESTS=(
  tests/test_arena.py
  tests/test_rl_reward.py
  tests/test_grpo_harness.py
)

if [[ "${MODE}" == "all" || "${MODE}" == "track-a" ]]; then
  echo "Running Track A tests"
  "${PYTEST_CMD[@]}" -q "${TRACK_A_TESTS[@]}"
fi

if [[ "${MODE}" == "all" || "${MODE}" == "core" ]]; then
  echo "Running core regression smoke"
  "${PYTEST_CMD[@]}" -q "${CORE_SMOKE_TESTS[@]}"
fi
