# Agent Entry Point

This file is the project agent maintenance guide. On case-insensitive macOS,
`AGENT.md` and `agent.md` may be the same inode, as they are in this checkout.
Treat those names as aliases. If `CLAUDE.md` and `claude.md` show the same
case-collision pattern, document the fact only. Do not delete, rename, or
"clean up" either spelling unless the user explicitly asks.

Production source is `frontend/`; deploy output is `web/dist/`; the public site
is `https://www.deepresearcharena.com/`.

## Multi-Agent Parallel Work

For substantial tasks, split work into independent slices such as tools,
verifiers, frontend, docs, tests, runner scripts, or release packaging. The
main agent owns the complete plan before workers start, and the main agent
remains responsible for final integration.

- Use separate Git worktrees or otherwise isolated working directories when
  multiple workers may edit code. Seed each worktree from the current working
  tree when the active uncommitted changes are part of the baseline.
- Give every worker a narrow ownership boundary: specific files, modules, or
  one subsystem. Workers should read the relevant files before editing and
  should not touch adjacent areas just to tidy them.
- Assume the worktree is dirty. Never revert, reset, delete, rename, or
  overwrite unrelated changes. If an overlap blocks progress, report the
  conflict to the main agent instead of resolving it by discarding work.
- Workers must not commit, push, deploy, or publish. The main agent performs
  final conflict resolution, staged integration, and any user-approved release
  step.
- Workers must not edit `data/changelog.json`, `web/dist/`, generated release
  artifacts, or deployment metadata unless the main agent explicitly assigns a
  release-output task.
- Keep core algorithms, training loops, task data, and recorded results outside
  a worker's scope unless that worker was specifically assigned those files.

## Validation

Run focused checks inside each worker's scope, then let the main agent run the
combined suite from the integrated tree. Worker results are useful signals, but
they do not replace the main agent's final verification.

Local Python environments vary on this machine. Prefer the Codex Python 3.12
runtime or an existing `uv` environment, and always run tests with
`PYTHONPATH=.` from the repository root.

Useful local checks:

```bash
bash scripts/check_track_a_local.sh
```

Focused Track A smoke:

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

Frontend checks only apply when `frontend/` source changes:

```bash
cd frontend
npm run typecheck
npm run build
```

Do not sync `frontend/out/` into `web/dist/`, modify `data/changelog.json`, or
run publish commands as a parallel worker.
