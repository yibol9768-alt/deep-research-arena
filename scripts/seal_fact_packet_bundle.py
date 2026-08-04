#!/usr/bin/env python3
"""Seal existing per-claim Fact packets for controlled rejudging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.frozen_claim_ledger import load_frozen_claim_ledger
from src.scoring.frozen_fact_packets import seal_fact_packet_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", required=True, type=Path)
    parser.add_argument("--claims-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    report = args.report.read_text(encoding="utf-8")
    claims_artifact = load_frozen_claim_ledger(args.claims_dir, report)
    manifest = seal_fact_packet_bundle(
        args.packet_dir,
        claims_artifact["claims"],
        claim_ledger_sha256=claims_artifact["manifest"][
            "claim_ledger_sha256"
        ],
    )
    print(
        json.dumps(
            {
                "packet_dir": str(args.packet_dir.resolve()),
                "fact_packet_bundle_sha256": manifest[
                    "fact_packet_bundle_sha256"
                ],
                "claim_ledger_sha256": manifest["claim_ledger_sha256"],
                "packet_count": manifest["packet_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
