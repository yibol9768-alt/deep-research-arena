"""Rollout generation helpers."""

from __future__ import annotations

from typing import Any, Callable

from src.eval.rollout import Rollout

from .env import Finalize, ResearchEnv, SandboxBackend
from .policy import Policy


def run_episode(
    task_config: dict[str, Any],
    env: ResearchEnv,
    policy: Policy,
) -> Rollout:
    """Drive ``env`` with ``policy`` until finalization or environment cap."""

    if hasattr(policy, "start_episode"):
        policy.start_episode(task_config)  # type: ignore[attr-defined]

    observation = env.reset()
    done = False
    max_steps = max(1, env.max_tool_calls + 8)
    steps = 0

    while not done and steps < max_steps:
        action = policy.act(observation)
        observation, done, _info = env.step(action)
        steps += 1
        if isinstance(action, Finalize):
            break

    return env.to_rollout()


def collect_group(
    task_config: dict[str, Any],
    backend_factory: Callable[[], SandboxBackend],
    policy: Policy,
    *,
    g: int = 8,
) -> list[Rollout]:
    """Collect G independent rollouts for one task with fresh envs."""

    rollouts: list[Rollout] = []
    max_calls = int(task_config.get("max_tool_calls") or 40)
    for _ in range(int(g)):
        env = ResearchEnv(task_config, backend_factory(), max_tool_calls=max_calls)
        rollouts.append(run_episode(task_config, env, policy))
    return rollouts


__all__ = ["collect_group", "run_episode"]
