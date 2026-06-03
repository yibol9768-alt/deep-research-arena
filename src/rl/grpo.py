"""GRPO trainer skeleton for the offline-testable RL harness."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from src.eval.evaluator import ArenaEvaluator
from src.rubrics.refresh_scheduler import RefreshScheduler
from src.rubrics.store import RubricItem, RubricStore

from .env import SandboxBackend
from .policy import Policy
from .runner import collect_group


@dataclass
class GRPOConfig:
    g: int = 8
    kl: float = 0.001
    lr: float = 5e-7
    advantage_mode: str = "token_level_dapo"
    tool_token_masking: bool = True
    refresh_every_n: int = 16
    kmax: int = 5
    base_model: str = "Qwen3-3B"
    eps: float = 1e-8


@dataclass
class StepStats:
    step: int
    task_id: str
    rewards: list[float]
    mean_reward: float
    std_reward: float
    advantages: list[float]
    advantage_mean: float
    advantage_std: float
    metrics: dict[str, float] = field(default_factory=dict)
    kl: float = 0.0
    rubric_version: int = 0
    refreshed: bool = False
    post_refresh_rubric_version: int = 0


class GRPOTrainer:
    def __init__(
        self,
        policy: Policy,
        evaluator_factory: Callable[[str], ArenaEvaluator] | None,
        rubric_stores: Mapping[str, RubricStore] | None,
        config: GRPOConfig | None = None,
    ) -> None:
        self.policy = policy
        self.evaluator_factory = evaluator_factory or (
            lambda task_id: ArenaEvaluator(task_id, mode="fast")
        )
        self.rubric_stores: dict[str, RubricStore] = dict(rubric_stores or {})
        self.config = config or GRPOConfig()
        self.scheduler = RefreshScheduler(self.config.refresh_every_n)
        self.step_count = 0
        self.task_steps: dict[str, int] = {}

    def step(
        self,
        task_config: dict[str, Any],
        backend_factory: Callable[[], SandboxBackend],
    ) -> StepStats:
        task_id = _task_id(task_config)
        store = self._store(task_id)
        snapshot = store.snapshot()
        evaluator = self._evaluator(task_id, task_config)

        rollouts = collect_group(
            task_config,
            backend_factory,
            self.policy,
            g=self.config.g,
        )
        eval_results = [
            evaluator.evaluate_rollout(rollout, rubric_snapshot=snapshot)
            for rollout in rollouts
        ]
        rewards = [
            float(getattr(result, "reward", getattr(result, "composite", 0.0)))
            for result in eval_results
        ]
        advantages = self._advantages(rewards)
        batch = self._build_batch(
            task_id=task_id,
            task_config=task_config,
            rollouts=rollouts,
            rewards=rewards,
            advantages=advantages,
            rubric_snapshot=snapshot,
        )
        metrics = dict(self.policy.update(batch))

        self.step_count += 1
        task_step = self.task_steps.get(task_id, 0) + 1
        self.task_steps[task_id] = task_step
        refreshed = self._maybe_refresh(task_id, task_config, rollouts, rewards, task_step)
        post_version = store.snapshot()["version"]

        return StepStats(
            step=self.step_count,
            task_id=task_id,
            rewards=rewards,
            mean_reward=_mean(rewards),
            std_reward=_pstdev(rewards),
            advantages=advantages,
            advantage_mean=_mean(advantages),
            advantage_std=_pstdev(advantages),
            metrics=metrics,
            kl=0.0,
            rubric_version=int(snapshot.get("version", 0)),
            refreshed=refreshed,
            post_refresh_rubric_version=int(post_version),
        )

    def save_checkpoint(self, directory: str | Path) -> Path:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "step_count": self.step_count,
            "task_steps": dict(self.task_steps),
            "scheduler_last_refresh": dict(self.scheduler.last_refresh),
            "config": asdict(self.config),
            "rubric_stores": {
                task_id: _store_payload(store)
                for task_id, store in self.rubric_stores.items()
            },
        }
        state_path = root / "trainer_state.json"
        state_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if hasattr(self.policy, "save"):
            self.policy.save(root / "policy")  # type: ignore[attr-defined]
        return state_path

    def load_checkpoint(self, directory: str | Path) -> None:
        root = Path(directory)
        payload = json.loads((root / "trainer_state.json").read_text(encoding="utf-8"))
        self.step_count = int(payload.get("step_count", 0))
        self.task_steps = {
            str(task_id): int(step)
            for task_id, step in (payload.get("task_steps") or {}).items()
        }
        self.scheduler.last_refresh = {
            str(task_id): int(step)
            for task_id, step in (payload.get("scheduler_last_refresh") or {}).items()
        }
        self.config = GRPOConfig(**(payload.get("config") or {}))
        self.scheduler.n = self.config.refresh_every_n
        self.rubric_stores = {
            task_id: _store_from_payload(task_id, store_payload)
            for task_id, store_payload in (payload.get("rubric_stores") or {}).items()
        }
        if hasattr(self.policy, "load"):
            self.policy.load(root / "policy")  # type: ignore[attr-defined]

    def _evaluator(self, task_id: str, task_config: dict[str, Any]) -> ArenaEvaluator:
        try:
            evaluator = self.evaluator_factory(task_id)
        except TypeError:
            evaluator = self.evaluator_factory(task_config)  # type: ignore[arg-type]
        if hasattr(evaluator, "_task_config"):
            evaluator._task_config = task_config  # type: ignore[attr-defined]
        # Strict grounding is mandatory for the live RL training loop: no-fetch
        # rollouts score 0 (no text-only proxy) and citing unfetched URLs
        # nullifies as fabrication. Without this the reward perversely favours
        # not reading. We force it here so callers cannot silently train against
        # the non-strict reward by passing a factory that forgets to set it.
        evaluator._rl_strict = True  # type: ignore[attr-defined]
        return evaluator

    def _store(self, task_id: str) -> RubricStore:
        if task_id not in self.rubric_stores:
            self.rubric_stores[task_id] = RubricStore(task_id)
        return self.rubric_stores[task_id]

    def _advantages(self, rewards: list[float]) -> list[float]:
        if not rewards:
            return []
        mean_reward = _mean(rewards)
        std_reward = _pstdev(rewards)
        if std_reward <= self.config.eps:
            return [0.0 for _ in rewards]
        return [
            (float(reward) - mean_reward) / (std_reward + self.config.eps)
            for reward in rewards
        ]

    def _build_batch(
        self,
        *,
        task_id: str,
        task_config: dict[str, Any],
        rollouts: list[Any],
        rewards: list[float],
        advantages: list[float],
        rubric_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "task_config": dict(task_config),
            "rollouts": rollouts,
            "rewards": list(rewards),
            "advantages": list(advantages),
            "token_ids": [getattr(rollout, "token_ids", None) for rollout in rollouts],
            "logprobs": [getattr(rollout, "logprobs", None) for rollout in rollouts],
            "action_sequences": [
                list(getattr(rollout, "sessions", []) or [])
                for rollout in rollouts
            ],
            "advantage_mode": self.config.advantage_mode,
            "mask_tool_tokens": bool(self.config.tool_token_masking),
            "tool_token_masks": [
                _tool_token_mask(rollout, enabled=self.config.tool_token_masking)
                for rollout in rollouts
            ],
            "kl": float(self.config.kl),
            "lr": float(self.config.lr),
            "rubric_snapshot": rubric_snapshot,
        }

    def _maybe_refresh(
        self,
        task_id: str,
        task_config: dict[str, Any],
        rollouts: list[Any],
        rewards: list[float],
        task_step: int,
    ) -> bool:
        self.scheduler.last_refresh.setdefault(task_id, 0)
        if not self.scheduler.should_refresh(task_id, task_step):
            return False

        from src.rubrics import buffer as rubric_buffer
        from src.rubrics import generator as rubric_generator

        rows = [
            {
                "report_md": getattr(rollout, "report_md", ""),
                "retrieved_snippets": getattr(rollout, "retrieved_snippets", {}),
                "evidence": getattr(rollout, "retrieved_snippets", {}),
                "tool_calls": getattr(rollout, "tool_calls", []),
                "reward": float(reward),
            }
            for rollout, reward in zip(rollouts, rewards)
        ]
        generated = rubric_generator.generate_active_rubrics(
            task_config,
            rows,
            k=self.config.kmax,
        )
        per_item_scores = {
            item.id: list(rewards)
            for item in generated
        }
        kept = rubric_buffer.manage_buffer(
            generated,
            per_item_scores,
            kmax=self.config.kmax,
        )
        self._store(task_id).replace_active(kept)
        return True


def _task_id(task_config: dict[str, Any]) -> str:
    return str(task_config.get("task_id") or task_config.get("id") or "unknown_task")


def _mean(values: list[float]) -> float:
    return sum(float(v) for v in values) / len(values) if values else 0.0


def _pstdev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean_value = _mean(values)
    variance = sum((float(v) - mean_value) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _tool_token_mask(rollout: Any, *, enabled: bool) -> list[int]:
    if not enabled:
        return []
    n_tool = len(getattr(rollout, "tool_calls", []) or [])
    has_report = bool(getattr(rollout, "report_md", ""))
    return [0 for _ in range(n_tool)] + ([1] if has_report else [])


def _store_payload(store: RubricStore) -> dict[str, Any]:
    return {
        "task_id": store.task_id,
        "version": store.version,
        "persist": [item.to_dict() for item in store.persist],
        "active": [item.to_dict() for item in store.active],
        "negative": [item.to_dict() for item in store.negative],
    }


def _store_from_payload(task_id: str, payload: dict[str, Any]) -> RubricStore:
    store = RubricStore(str(payload.get("task_id") or task_id))
    store.version = int(payload.get("version", 0))
    store.persist = [
        RubricItem.from_dict(item)
        for item in payload.get("persist", [])
    ]
    store.active = [
        RubricItem.from_dict(item)
        for item in payload.get("active", [])
    ]
    store.negative = [
        RubricItem.from_dict(item)
        for item in payload.get("negative", [])
    ]
    return store


__all__ = ["GRPOConfig", "GRPOTrainer", "StepStats"]
