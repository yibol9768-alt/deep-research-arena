"""Run a single WebArena shopping task through our runner.

Usage:
    # Use an oracle that just returns a known-good answer (to sanity-check the pipeline):
    SHOPPING=http://localhost:7770 python scripts/run_webarena_task.py 21 --oracle "Some answer"

    # Hook up a real agent (any callable that returns a str given page+cfg):
    SHOPPING=http://localhost:7770 python scripts/run_webarena_task.py 21 --agent-module my.module:my_agent
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner  # noqa: E402


def stub_agent(answer: str):
    def _fn(page, cfg):
        return answer
    return _fn


def load_dotted_agent(spec: str):
    mod_name, attr = spec.split(":")
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("task_id", type=int)
    p.add_argument("--tasks-dir", default="data/tasks/webarena/shopping")
    p.add_argument("--oracle", help="Static answer string (dry-run, no real agent).")
    p.add_argument("--agent-module", help="Import path like 'my.mod:my_agent_fn'")
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()

    task_path = ROOT / args.tasks_dir / f"{args.task_id}.json"
    if not task_path.exists():
        print(f"no such task: {task_path}", file=sys.stderr)
        return 2
    cfg = json.loads(task_path.read_text())

    if args.oracle is not None:
        agent = stub_agent(args.oracle)
    elif args.agent_module:
        agent = load_dotted_agent(args.agent_module)
    else:
        print("must pass --oracle or --agent-module", file=sys.stderr)
        return 2

    runner = PlaywrightRunner(headless=not args.headed)
    result = runner.run(cfg, agent)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
