#!/usr/bin/env python3
"""Score one frozen DRA three-axis judgment packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.three_axis_score import score_three_axis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    report_path = ROOT / packet["report_path"]
    report = report_path.read_text(encoding="utf-8")
    missing_quotes = [
        item["claim_id"]
        for item in packet["material_claims"]
        if item["exact_quote"] not in report
    ]
    if missing_quotes:
        raise SystemExit(
            "claim quotes are not exact report substrings: " + ", ".join(missing_quotes)
        )

    result = {
        "schema": "dra_three_axis_score_v1",
        "task_id": packet["task_id"],
        "packet_path": str(args.packet),
        "formal_eligible": bool(packet.get("formal_eligible", False)),
        "eligibility_notes": packet.get("eligibility_notes", []),
        **score_three_axis(packet),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
