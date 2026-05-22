#!/usr/bin/env python3
"""Run pairwise LLM-judge battles across all agent × task pairs.

Supports **dual judges** to measure inter-judge agreement and correct for
single-judge self-preference (a known issue when glm-5 judges glm-5 outputs).

Inputs (read from data/results/):
  - `final_<agent>_<task>.answer.md`   — agent output (full markdown)
  - task JSON at `data/tasks/deep_research/**/<task>.json` — intent

Output:
  - `data/results/pairwise_dual_<ts>.json` — list of battles with:
      {task, a1, a2, agent_winner, verdicts_raw, reasonings, judge_model}

Usage:
    python scripts/run_pairwise_battles.py \\
        --judges glm-5,qwen3.5-plus \\
        --agents react-glm5,react-qwen35plus,deerflow-glm46 \\
        --tasks dr_cross_v3_0001,dr_cross_v3_0005 \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.pairwise_judge import battle

RESULTS = ROOT / "data" / "results"
TASKS = ROOT / "data" / "tasks" / "deep_research"
LEADERBOARD_PATH = RESULTS / "deep_v3" / "leaderboard_deep.json"
LEADERBOARD_V2_PATH = RESULTS / "deep_v2" / "leaderboard_deep.json"


def discover_runs() -> dict[tuple[str, str], Path]:
    """Return {(agent, task): answer_path} from final_*.answer.md files."""
    out: dict[tuple[str, str], Path] = {}
    for p in RESULTS.glob("final_*.answer.md"):
        stem = p.name.replace("final_", "").replace(".answer.md", "")
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        out[(parts[0], parts[1])] = p
    return out


def load_task_intent(task_id: str) -> str:
    for pat in (f"**/{task_id}.json",):
        for p in TASKS.glob(pat):
            try:
                cfg = json.loads(p.read_text())
                return cfg.get("intent", "") or cfg.get("description", "") or ""
            except Exception:
                continue
    return ""


def _load_leaderboard() -> dict | None:
    """Read the current Elo leaderboard so we can pick the top-N agents.

    Tries the v3 path first, then the v2 fallback. Returns the parsed dict or
    None if neither exists (caller must then fall back to --agents).
    """
    for p in (LEADERBOARD_PATH, LEADERBOARD_V2_PATH):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[warn] could not parse {p}: {e}", file=sys.stderr)
                continue
    return None


def _top_n_agents(leaderboard: dict, n: int) -> list[str]:
    """Return the top-N agents from the v2 truthful Elo table.

    Uses `elo_v2_ci` if present (preferred — bootstrap CI table), else
    `elo_v2`, else `elo_v1_ci`. Excludes anything in `excluded_agents`.
    """
    for key in ("elo_v2_ci", "elo_v2", "elo_v1_ci", "elo_v1"):
        table = leaderboard.get(key)
        if table:
            break
    else:
        return []

    excluded = set(leaderboard.get("excluded_agents", []) or [])
    rows = [
        (agent, info.get("elo", info.get("elo_mean", 0.0)))
        for agent, info in table.items()
        if agent not in excluded
    ]
    rows.sort(key=lambda r: -r[1])
    return [a for a, _ in rows[:n]]


def _plan_top_pair_densify(
    *,
    runs: dict[tuple[str, str], Path],
    tasks: list[str],
    judges: list[str],
    top_n: int,
    n_per_pair: int,
    seed: int,
) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """Build a densified battle plan focused on the top-N agents.

    For each of the C(top_n, 2) agent pairs we schedule `n_per_pair` battles
    sampled uniformly from the tasks where BOTH agents have answers. Battles
    are tagged with `judges` — each pair x task x judge combination is one
    entry in the returned plan.

    Returns (plan, top_agents). Plan items: (task_id, a, b, judge).
    """
    leaderboard = _load_leaderboard()
    if leaderboard is None:
        return [], []
    top_agents = _top_n_agents(leaderboard, top_n)
    if len(top_agents) < 2:
        return [], top_agents

    rng = random.Random(seed)
    plan: list[tuple[str, str, str, str]] = []
    for a, b in itertools.combinations(top_agents, 2):
        eligible_tasks = [
            t for t in tasks
            if (a, t) in runs and (b, t) in runs
        ]
        if not eligible_tasks:
            print(
                f"[warn] no overlapping tasks for {a} vs {b}; skipping pair.",
                file=sys.stderr,
            )
            continue
        # Sample with replacement so n_per_pair can exceed eligible-task count
        # (small pools were the original problem — that's the whole point of
        # densifying).
        sampled = [rng.choice(eligible_tasks) for _ in range(n_per_pair)]
        for task_id in sampled:
            for judge in judges:
                plan.append((task_id, a, b, judge))
    return plan, top_agents


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", default="glm-5",
                    help="Comma-separated list of judge models (e.g. glm-5,qwen3.5-plus)")
    ap.add_argument("--agents", default="",
                    help="Comma-separated agents to include (default: all discovered)")
    ap.add_argument("--tasks", default="",
                    help="Comma-separated tasks to include (default: all discovered)")
    ap.add_argument("--dry-run", action="store_true",
                    help="List battles without calling the LLM judge")
    ap.add_argument("--out", default="",
                    help="Explicit output path; default pairwise_dual_<ts>.json")
    ap.add_argument(
        "--strategy",
        default="full-matrix",
        choices=["full-matrix", "top-pair-densify"],
        help=(
            "Battle-selection strategy. 'full-matrix' (default) emits all "
            "pairs x tasks x judges. 'top-pair-densify' reads the current "
            "leaderboard, picks the top-N agents, and schedules N_per_pair "
            "battles per pair (designed to lift Elo CI half-width below the "
            "top-cluster gap)."
        ),
    )
    ap.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Top-N agents to densify around when --strategy=top-pair-densify.",
    )
    ap.add_argument(
        "--n-per-pair",
        type=int,
        default=20,
        help="Battles per agent pair under --strategy=top-pair-densify.",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for top-pair-densify task sampling.",
    )
    args = ap.parse_args()

    judges = [j.strip() for j in args.judges.split(",") if j.strip()]
    runs = discover_runs()
    all_agents = sorted({a for (a, _) in runs.keys()})
    all_tasks = sorted({t for (_, t) in runs.keys()})
    agents = [a for a in (args.agents.split(",") if args.agents else all_agents) if a]
    tasks = [t for t in (args.tasks.split(",") if args.tasks else all_tasks) if t]

    print(f"Agents ({len(agents)}): {agents}")
    print(f"Tasks  ({len(tasks)}): {tasks}")
    print(f"Judges ({len(judges)}): {judges}")
    print(f"Strategy: {args.strategy}")

    plan: list[tuple[str, str, str, str]] = []

    if args.strategy == "top-pair-densify":
        plan, top_agents = _plan_top_pair_densify(
            runs=runs,
            tasks=tasks,
            judges=judges,
            top_n=args.top_n,
            n_per_pair=args.n_per_pair,
            seed=args.seed,
        )
        print(f"Top-{args.top_n} agents (from leaderboard): {top_agents}")
        n_pairs = len(list(itertools.combinations(top_agents, 2)))
        print(
            f"\n{len(plan)} densified battles planned "
            f"({n_pairs} top-N pairs x {args.n_per_pair} per pair "
            f"x {len(judges)} judges)"
        )
        if not plan:
            print(
                "[error] top-pair-densify produced an empty plan. Check that "
                "data/results/deep_v3/leaderboard_deep.json exists and that "
                "the discovered runs cover the top agents.",
                file=sys.stderr,
            )
            return
    else:
        # Default: full matrix — keep the existing behaviour unchanged.
        for task_id in tasks:
            for a, b in itertools.combinations(agents, 2):
                if (a, task_id) not in runs or (b, task_id) not in runs:
                    continue
                for judge in judges:
                    plan.append((task_id, a, b, judge))
        print(
            f"\n{len(plan)} battles planned "
            f"({len(tasks)} tasks x "
            f"{len(list(itertools.combinations(agents, 2)))} pairs x "
            f"{len(judges)} judges)"
        )

    if args.dry_run:
        for t, a, b, j in plan[:10]:
            print(f"  [dry] {t}  {a}  vs  {b}  judge={j}")
        if len(plan) > 10:
            print(f"  ... +{len(plan)-10} more")
        return

    # Run battles
    results = []
    t0 = time.time()
    for i, (task_id, a, b, judge) in enumerate(plan, 1):
        intent = load_task_intent(task_id)
        ans_a = runs[(a, task_id)].read_text(encoding="utf-8", errors="ignore")
        ans_b = runs[(b, task_id)].read_text(encoding="utf-8", errors="ignore")
        elapsed = time.time() - t0
        print(f"[{i}/{len(plan)}  {elapsed:.0f}s] {task_id}  {a} vs {b}  judge={judge}  ...",
              end=" ", flush=True)
        r = battle(
            task_intent=intent,
            agent_a=a, answer_a=ans_a,
            agent_b=b, answer_b=ans_b,
            model=judge,
        )
        r["task"] = task_id
        r["a1"] = a
        r["a2"] = b
        r["judge_model"] = judge
        results.append(r)
        print(f"winner={r.get('agent_winner')}")

    # Save
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else RESULTS / f"pairwise_dual_{ts}.json"
    out_path.write_text(json.dumps({
        "judges": judges,
        "agents": agents,
        "tasks": tasks,
        "battles": results,
        "n_battles": len(results),
    }, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(results)} battles → {out_path}")

    # Summary
    from collections import Counter
    per_judge_winner = {j: Counter() for j in judges}
    for r in results:
        per_judge_winner[r["judge_model"]][r.get("agent_winner", "tie")] += 1
    print("\nPer-judge win counts:")
    for j, c in per_judge_winner.items():
        print(f"  {j}: {dict(c)}")


if __name__ == "__main__":
    main()
