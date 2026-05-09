"""Auto-discovery registry for deep-research runner modules.

Drop a new ``<framework>_runner.py`` into this directory with two symbols and
the framework is automatically benchmarkable — no edits to ``run_deep_task.py``,
``smoke_test_drs.py`` or anywhere else.

Required contract for each ``*_runner.py``:

    AGENT_NAME = "my-framework"        # the leaderboard identifier
    async def run(
        intent: str,
        model: str,
        shim_url: str,
        proxy_url: str,
        *,
        timeout_s: int = 1800,
    ) -> str:
        ...                            # return the agent's markdown report

The agent name is what shows up in score-file names
(``data/results/deep_v3/<AGENT_NAME>__<task>_matrix.score.json``) and in the
Elo leaderboard. Pick something stable: renaming an agent here means past
score files become unreachable to ``build_deep_leaderboard``.

Discovery is purely additive — runners that don't satisfy the contract are
listed in ``import_errors`` instead of crashing the registry, so a broken new
contribution can't silently de-rate every existing agent.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable

RUNNERS_DIR = Path(__file__).resolve().parent

# A discovered runner's run() must take these positional args (in order). Any
# additional kwargs (e.g. timeout_s) are allowed via **kwargs at call time.
_REQUIRED_POSITIONAL = ("intent", "model", "shim_url", "proxy_url")


def _module_name_from_file(p: Path) -> str:
    return f"scripts.runners.{p.stem}"


def discover() -> tuple[dict[str, Callable[..., Awaitable[str]]], dict[str, str]]:
    """Scan ``scripts/runners/`` for valid runner modules.

    Returns ``(runners, import_errors)`` where ``runners`` maps
    ``AGENT_NAME -> async run(...)`` and ``import_errors`` maps file stem to a
    human-readable failure reason. The two-tuple shape lets callers surface
    broken runners in their UI (the smoke test does this) without losing the
    working ones.
    """
    runners: dict[str, Callable[..., Awaitable[str]]] = {}
    import_errors: dict[str, str] = {}

    for path in sorted(RUNNERS_DIR.glob("*_runner.py")):
        stem = path.stem
        mod_name = _module_name_from_file(path)
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            import_errors[stem] = f"import: {type(e).__name__}: {e}"
            continue

        agent_name = getattr(mod, "AGENT_NAME", None)
        run_fn = getattr(mod, "run", None)
        if not isinstance(agent_name, str) or not agent_name:
            import_errors[stem] = "missing AGENT_NAME (str) at module top level"
            continue
        if run_fn is None or not callable(run_fn):
            import_errors[stem] = "missing async run(...) function"
            continue
        if not inspect.iscoroutinefunction(run_fn):
            import_errors[stem] = "run() must be defined with `async def`"
            continue

        sig = inspect.signature(run_fn)
        positional = [
            n for n, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if positional[: len(_REQUIRED_POSITIONAL)] != list(_REQUIRED_POSITIONAL):
            import_errors[stem] = (
                f"run() positional args {positional!r} do not start with "
                f"{list(_REQUIRED_POSITIONAL)!r}"
            )
            continue

        if agent_name in runners:
            import_errors[stem] = f"duplicate AGENT_NAME {agent_name!r} (already registered)"
            continue
        runners[agent_name] = run_fn

    return runners, import_errors


def list_agents() -> list[str]:
    """Convenience: just the agent names that registered cleanly."""
    runners, _ = discover()
    return sorted(runners.keys())


__all__ = ["discover", "list_agents"]
