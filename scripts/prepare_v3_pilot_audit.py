#!/usr/bin/env python3
"""Validate the hand-picked v3 candidate-20 and create a blank human audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.pilot_audit_v3 import (  # noqa: E402
    build_audit_worksheet,
    promotion_readiness,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=Path,
                    default=ROOT / "data/pilot_v3/candidate_20.json")
    ap.add_argument("--tasks-dir", type=Path,
                    default=ROOT / "data/tasks/deep_research/cross_site_deep")
    ap.add_argument("--out", type=Path, help="write a fresh human audit worksheet")
    ap.add_argument("--check-audit", type=Path,
                    help="check promotion readiness of a completed worksheet")
    args = ap.parse_args(argv)
    if bool(args.out) == bool(args.check_audit):
        ap.error("choose exactly one of --out or --check-audit")
    if args.check_audit:
        audit = json.loads(args.check_audit.read_text(encoding="utf-8"))
        result = promotion_readiness(audit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0
    doc = json.loads(args.candidates.read_text(encoding="utf-8"))
    worksheet = build_audit_worksheet(doc, args.tasks_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(worksheet, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
