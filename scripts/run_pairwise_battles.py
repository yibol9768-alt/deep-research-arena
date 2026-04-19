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
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.pairwise_judge import battle

RESULTS = ROOT / "data" / "results"
TASKS = ROOT / "data" / "tasks" / "deep_research"


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

    # Emit battles: for each task, for each agent pair, for each judge
    plan = []
    for task_id in tasks:
        for a, b in itertools.combinations(agents, 2):
            if (a, task_id) not in runs or (b, task_id) not in runs:
                continue
            for judge in judges:
                plan.append((task_id, a, b, judge))
    print(f"\n{len(plan)} battles planned "
          f"({len(tasks)} tasks × {len(list(itertools.combinations(agents, 2)))} pairs × {len(judges)} judges)")

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
