#!/usr/bin/env python3
"""Assemble the agent prompt for a task (EXECUTION_PLAN P4.1).

prompts/agent_prompt.md template + the task's real-user intent + the
spec-derived soft output contract (spec_extract.natural_output_contract).
No hand-written per-task prompts, no quotas: this script IS the only path
from task JSON to the string an agent under test receives.

Usage:
  python3 scripts/render_agent_prompt.py dr_cross_deep_0001          # print
  python3 scripts/render_agent_prompt.py --all --out-dir prompts/rendered
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.spec_extract import natural_output_contract  # noqa: E402

TEMPLATE = ROOT / "prompts/agent_prompt.md"
TASK_DIR = ROOT / "data/tasks/deep_research/cross_site_deep"


def render(task_id: str) -> str:
    task = json.loads((TASK_DIR / f"{task_id}.json").read_text())
    intent = task.get("intent", "")
    if isinstance(intent, dict):
        intent = intent.get("prompt", "")
    tpl = TEMPLATE.read_text()
    body = tpl.split("## Sandbox preamble", 1)[1]
    body = "## Sandbox preamble" + body
    return (body
            .replace("{USER_QUESTION}", intent.strip())
            .replace("{OUTPUT_CONTRACT}", natural_output_contract(task)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id", nargs="?", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    tids = ([p.stem for p in sorted(TASK_DIR.glob("dr_cross_deep_*.json"))]
            if args.all else [args.task_id or "dr_cross_deep_0001"])
    outd = Path(args.out_dir) if args.out_dir else None
    if outd:
        outd.mkdir(parents=True, exist_ok=True)
    for tid in tids:
        text = render(tid)
        if outd:
            (outd / f"{tid}.md").write_text(text)
        else:
            print(text)
    if outd:
        print(f"rendered {len(tids)} prompts -> {outd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
