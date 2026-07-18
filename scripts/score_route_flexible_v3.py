#!/usr/bin/env python3
"""Replay one sealed route-flexible rubric judgment deterministically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.observation_ledger import load_observation_ledger
from src.eval.route_flexible_scorer import score_route_flexible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--judgment", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    case = json.loads(args.case.read_text(encoding="utf-8"))
    report = args.report.read_text(encoding="utf-8")
    ledger = load_observation_ledger(args.ledger)
    judgment = json.loads(args.judgment.read_text(encoding="utf-8"))
    result = score_route_flexible(rubric, case, report, ledger, judgment)
    payload = json.dumps(
        result, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
