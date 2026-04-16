"""End-to-end smoke test: run the runner against a url_match task using the
url_match_oracle. Should produce score=1.0 if everything is wired correctly.

Assumes:
  - shopping env is up at $SHOPPING (default http://localhost:7770)
  - Playwright + Chromium installed

Usage:
    export SHOPPING=http://localhost:7770
    python scripts/smoke_test_pipeline.py              # uses default task 158
    python scripts/smoke_test_pipeline.py 159          # specify task_id
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner  # noqa: E402
from envs.shopping.oracle.url_match_oracle import url_match_oracle  # noqa: E402


def main() -> int:
    task_id = int(sys.argv[1]) if len(sys.argv) > 1 else 158
    task_path = ROOT / "data" / "tasks" / "webarena" / "shopping" / f"{task_id}.json"
    if not task_path.exists():
        print(f"no such task: {task_path}", file=sys.stderr)
        return 2
    cfg = json.loads(task_path.read_text())
    print(f"[smoke] task {task_id}: {cfg['intent'][:100]}")
    print(f"[smoke] eval_types: {cfg['eval']['eval_types']}")

    runner = PlaywrightRunner(headless=True)
    result = runner.run(cfg, agent=url_match_oracle)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
