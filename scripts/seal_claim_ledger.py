#!/usr/bin/env python3
"""Seal an existing DRA claim-extraction directory for judge reuse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.frozen_claim_ledger import seal_claim_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = args.report.read_text(encoding="utf-8")
    manifest = seal_claim_ledger(
        args.claims_dir,
        report,
        intended_for_cross_judge_reuse=True,
    )
    print(
        json.dumps(
            {
                "claims_dir": str(args.claims_dir.resolve()),
                "claim_ledger_sha256": manifest["claim_ledger_sha256"],
                "report_sha256": manifest["report_sha256"],
                "frozen_claim_count": manifest["frozen_claim_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
