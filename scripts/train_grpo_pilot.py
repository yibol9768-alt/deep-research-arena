#!/usr/bin/env python3
"""Run the Phase B Qwen GRPO pilot loop."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.evaluator import ArenaEvaluator
from src.rl.env import backend_from_task_config
from src.rl.grpo import GRPOConfig, GRPOTrainer
from src.rl.qwen_policy import QwenPolicy
from src.rubrics import RubricItem, RubricStore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-file", required=True, help="Path to one task JSON file")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--g", type=int, default=6)
    parser.add_argument("--ctx", type=int, default=8192)
    parser.add_argument("--shim-url", default="http://localhost:8081")
    parser.add_argument("--out", default="runs/pilot1")
    parser.add_argument("--model", default="unsloth/Qwen3-4B")
    parser.add_argument("--max-new-tokens", type=int, default=256,
                        help="per-turn generation budget")
    parser.add_argument("--max-tool-calls", type=int, default=12,
                        help="hard cap on tool calls per episode")
    parser.add_argument("--lr", type=float, default=1e-5,
                        help="LoRA learning rate (pilot demo uses a higher lr "
                             "than the locked 5e-7 to make movement visible)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    task_file = Path(args.task_file)
    task_config = json.loads(task_file.read_text(encoding="utf-8"))
    task_config.setdefault("task_id", task_config.get("id") or task_file.stem)
    task_config["prompt"] = _prompt_from_task(task_config)
    task_config["max_tool_calls"] = int(args.max_tool_calls)
    task_id = str(task_config["task_id"])

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    trend_path = out_dir / "trend.jsonl"

    policy = QwenPolicy(
        model_name=args.model,
        ctx=args.ctx,
        lr=args.lr,
        max_new_tokens=args.max_new_tokens,
    )
    # Select the acquisition backend from the task's `acquisition` field
    # (search_shim | browser | computer_use). Defaults to the shim, so tasks
    # without the field are byte-identical to the old HttpSandboxBackend path.
    backend_factory = lambda: backend_from_task_config(task_config, shim_url=args.shim_url)

    def evaluator_factory(tid: str) -> ArenaEvaluator:
        evaluator = ArenaEvaluator(tid, mode="fast")
        evaluator._task_config = task_config
        # Strict grounding for RL: no-fetch rollouts score 0 (no text-only proxy)
        # and citing unfetched URLs nullifies as fabrication. Without this the
        # reward perversely favours not reading. (arena eval keeps the default.)
        evaluator._rl_strict = True
        return evaluator

    store = RubricStore(task_id)
    store.set_persist(_rubric_items(task_id, task_config, task_file))
    trainer = GRPOTrainer(
        policy=policy,
        evaluator_factory=evaluator_factory,
        rubric_stores={task_id: store},
        config=GRPOConfig(g=args.g, refresh_every_n=16, lr=args.lr),
    )

    latest = out_dir / "checkpoints" / "latest"
    if latest.exists():
        trainer.load_checkpoint(latest)

    for _ in range(int(args.steps)):
        stats = trainer.step(task_config, backend_factory)
        row = asdict(stats)
        row["time"] = round(time.time(), 3)
        row["loss"] = float(stats.metrics.get("loss", 0.0))
        row["mean_abs_adv"] = float(stats.metrics.get("mean_abs_adv", 0.0))
        with trend_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "step": stats.step,
                    "mean_reward": stats.mean_reward,
                    "std_reward": stats.std_reward,
                    "advantage_std": stats.advantage_std,
                    "loss": row["loss"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if stats.step % 10 == 0:
            step_dir = out_dir / "checkpoints" / f"step_{stats.step:06d}"
            trainer.save_checkpoint(step_dir)
            trainer.save_checkpoint(latest)

    trainer.save_checkpoint(latest)
    os._exit(0)


def _prompt_from_task(task_config: dict[str, Any]) -> str:
    prompt = str(
        task_config.get("prompt")
        or task_config.get("intent")
        or task_config.get("question")
        or ""
    )
    substitutions = {
        "__SHOPPING__": os.environ.get("SHOPPING", "http://localhost:7770"),
        "__REDDIT__": os.environ.get("REDDIT", "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    for needle, replacement in substitutions.items():
        prompt = prompt.replace(needle, replacement)
    lang = str(task_config.get("language", "en") or "en").lower()
    if lang == "zh":
        return prompt + "\n\n请用中文撰写完整的研究报告。"
    if lang == "bilingual":
        return (
            prompt
            + "\n\nProvide the full research report in BOTH English and Chinese "
            "(中英双语,两种语言都要完整)."
        )
    return prompt


def _rubric_items(
    task_id: str,
    task_config: dict[str, Any],
    task_file: Path,
) -> list[RubricItem]:
    raw_items = task_config.get("checklist") or task_config.get("checklist_items")
    if not raw_items:
        raw_items = _load_checklist_path(task_id, task_config, task_file)
    items: list[RubricItem] = []
    for idx, raw in enumerate(raw_items or [], start=1):
        if isinstance(raw, dict):
            criterion = str(
                raw.get("criterion")
                or raw.get("question")
                or raw.get("text")
                or raw.get("description")
                or ""
            ).strip()
            weight = float(raw.get("weight", 1.0))
            deterministic = bool(raw.get("is_deterministic", False))
        else:
            criterion = str(raw).strip()
            weight = 1.0
            deterministic = False
        if not criterion:
            continue
        items.append(
            RubricItem(
                id=f"{task_id}-persist-{idx:03d}",
                criterion=criterion,
                weight=weight,
                is_deterministic=deterministic,
                polarity="positive",
                tier="persist",
                origin="task_checklist",
            )
        )
    return items


def _load_checklist_path(
    task_id: str,
    task_config: dict[str, Any],
    task_file: Path,
) -> list[Any]:
    path_value = task_config.get("coverage_checklist_path")
    if not path_value:
        return []
    path = Path(str(path_value))
    candidates = [
        path,
        ROOT / path,
        task_file.parent / path,
    ]
    checklist_path = next((candidate for candidate in candidates if candidate.exists()), None)
    if checklist_path is None:
        return []
    data = json.loads(checklist_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get(task_id) or data.get(str(task_config.get("id") or ""))
        return list(items or [])
    if isinstance(data, list):
        return list(data)
    return []


if __name__ == "__main__":
    main()
