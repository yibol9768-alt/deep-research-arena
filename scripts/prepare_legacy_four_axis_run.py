#!/usr/bin/env python3
"""Prepare an older harness report for the four-axis scorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.legacy_report_adapter import adapt_legacy_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    observation = parser.add_mutually_exclusive_group(required=True)
    observation.add_argument("--observation-ledger", type=Path)
    observation.add_argument("--sources", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    result = adapt_legacy_run(
        report_path=args.report,
        observation_ledger_path=args.observation_ledger,
        sources_path=args.sources,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "report": str(result["report"]),
                "trace": str(result["trace"]),
                "citation_map": str(result["citation_map"]),
                **result["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
