"""Run the GLM-5.1 ReAct agent against all 5 DR shopping tasks.

Usage:
    SHOPPING=http://localhost:7770 python scripts/run_dr_baseline.py            # all 5
    SHOPPING=http://localhost:7770 python scripts/run_dr_baseline.py dr_shop_0001
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import PlaywrightRunner  # noqa: E402
from src.agents import glm_react_agent  # noqa: E402


def main() -> int:
    tasks_dir = ROOT / "data" / "tasks" / "deep_research" / "shopping"
    if len(sys.argv) > 1:
        ids = [sys.argv[1]]
    else:
        ids = sorted(p.stem for p in tasks_dir.glob("dr_shop_*.json"))

    runner = PlaywrightRunner(headless=True, timeout_ms=90_000)
    summary = []
    for tid in ids:
        cfg = json.loads((tasks_dir / f"{tid}.json").read_text())
        print(f"\n======= {tid} =======")
        print(f"intent: {cfg['intent'][:140]}")
        result = runner.run(cfg, agent=glm_react_agent)
        row = {
            "task_id": tid,
            "passed": result.passed,
            "score": result.score,
            "elapsed_sec": round(result.elapsed_sec, 1),
            "answer_preview": (result.answer or "")[:500],
            "verifier_misses": [vr for vr in result.verifier_results if not vr.get("passed")],
            "error": result.error,
        }
        print(json.dumps(row, indent=2, ensure_ascii=False)[:2500])
        summary.append(row)

    print("\n======= SUMMARY =======")
    passed = sum(1 for r in summary if r["passed"])
    print(f"{passed} / {len(summary)} tasks passed")
    for r in summary:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  {icon}  {r['task_id']}  score={r['score']:.2f}  t={r['elapsed_sec']}s")
    return 0 if passed == len(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
