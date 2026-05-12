#!/usr/bin/env python3
"""Generate the run queue for the "full Elo" expansion.

For every (agent, task) that's missing a `*_matrix.score.json` under
`data/results/deep_v3/`, emit one line `<agent>\t<task>` to stdout (or to
the queue file if `--out` is given). Resumable: re-running after some
runs land just shrinks the queue.

Skips agents/tasks the caller doesn't want via `--agents` / `--task-range`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_AGENTS = [
    "camel-ai",
    "deerflow",
    "flowsearcher-ds",
    "gpt-researcher",
    "ii-researcher",
    "langchain-odr",
    "ldr",
    "qx-agents",
    "smolagents",
    "storm",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="+", default=DEFAULT_AGENTS,
                    help="agents to schedule (default: all 10)")
    ap.add_argument("--task-range", default="1-57",
                    help="task id range, inclusive, e.g. 1-30 or 31-57 (default: 1-57)")
    ap.add_argument("--results-dir", default="deep_v3",
                    help="dir under data/results/ to read existing scores from")
    ap.add_argument("--out", default=None, help="write queue to this file (else stdout)")
    args = ap.parse_args()

    deep_dir = ROOT / "data" / "results" / args.results_dir
    task_dir = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"

    lo, hi = (int(x) for x in args.task_range.split("-"))
    all_tasks = sorted(t.stem for t in task_dir.glob("dr_cross_deep_*.json"))
    in_range = [t for t in all_tasks if lo <= int(t.split("_")[-1]) <= hi]

    queue = []
    for agent in args.agents:
        for task in in_range:
            score = deep_dir / f"{agent}__{task}_matrix.score.json"
            if score.exists():
                continue
            queue.append((agent, task))

    out = sys.stdout if args.out is None else open(args.out, "w", encoding="utf-8")
    for agent, task in queue:
        print(f"{agent}\t{task}", file=out)
    if args.out:
        out.close()
        print(f"wrote {len(queue)} (agent, task) pairs to {args.out}", file=sys.stderr)
    else:
        print(f"# {len(queue)} pairs", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
