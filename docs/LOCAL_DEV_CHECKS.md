# Local Dev Checks

This is the local-only smoke path for Deep Research Arena. It does not require
the remote `vircs` host, does not install dependencies, and should not touch
`data/changelog.json` or `web/dist/`.

## Python Runtime

The macOS system Python may be the wrong version or may miss local dependencies.
Prefer one of these:

- Codex Python 3.12:
  `/Users/liuyibo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- An existing `uv` environment, for example `uv run python -m pytest ...`
- A project virtual environment that already has the repo requirements

Always run from the repository root with `PYTHONPATH=.`.

## One-Command Smoke

```bash
bash scripts/check_track_a_local.sh
```

Available modes:

```bash
bash scripts/check_track_a_local.sh import
bash scripts/check_track_a_local.sh track-a
bash scripts/check_track_a_local.sh core
bash scripts/check_track_a_local.sh all
```

Override the interpreter when needed:

```bash
PYTHON_BIN=/path/to/python3 bash scripts/check_track_a_local.sh
PYTHON_BIN="uv run python" bash scripts/check_track_a_local.sh
```

## Manual Checks

Import check:

```bash
PYTHONPATH=. python3 - <<'PY'
import importlib

modules = [
    "src.rl.env",
    "src.rl.backends",
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
```

Track A tests:

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_action_parser.py \
  tests/test_tool_registry.py \
  tests/test_tools_write.py \
  tests/test_state_diff_verifier.py \
  tests/test_user_sim.py \
  tests/test_tools_vision.py \
  tests/test_computeruse_policy.py \
  tests/test_tools_rag.py \
  tests/test_build_rag_index.py \
  tests/test_modality_parity.py
```

Core regression smoke:

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_arena.py \
  tests/test_rl_reward.py \
  tests/test_grpo_harness.py
```

These checks are intentionally local and offline. If they fail because `pytest`
or another dependency is missing, switch to the Codex runtime, `uv`, or an
already-prepared virtual environment instead of installing from the script. The
helper script first tries `python -m pytest`; when that is unavailable and `uv`
exists, it uses `uv --offline` so it can reuse cached pytest wheels without
network access.
