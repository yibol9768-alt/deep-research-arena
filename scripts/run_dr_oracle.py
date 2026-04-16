"""Run a deep-research task through its oracle + verifier chain.

Usage:
    SHOPPING=http://localhost:7770 python scripts/run_dr_oracle.py dr_shop_0001
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_dr_oracle.py <task_id>", file=sys.stderr)
        return 2
    task_id = sys.argv[1]

    # Resolve task file + oracle module based on task_id prefix
    if task_id.startswith("dr_shop_"):
        site, oracle_pkg = "shopping", "envs.shopping.oracle_dr"
    elif task_id.startswith("dr_red_"):
        site, oracle_pkg = "reddit", "envs.reddit.oracle_dr"
    else:
        print(f"unknown task prefix: {task_id}", file=sys.stderr)
        return 2

    task_path = ROOT / "data" / "tasks" / "deep_research" / site / f"{task_id}.json"
    if not task_path.exists():
        print(f"no such task: {task_path}", file=sys.stderr)
        return 2
    cfg = json.loads(task_path.read_text())

    mod = importlib.import_module(f"{oracle_pkg}.{task_id}_oracle")
    oracle = mod.oracle

    runner = PlaywrightRunner(headless=True, timeout_ms=90_000)
    result = runner.run(cfg, agent=oracle)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False)[:4000])
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
