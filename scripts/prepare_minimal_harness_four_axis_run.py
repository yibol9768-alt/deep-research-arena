#!/usr/bin/env python3
"""Prepare one sealed minimal-harness run for the four-axis scorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.minimal_harness_artifact_adapter import (
    adapt_minimal_harness_run,
    project_minimal_harness_non_delivery,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--allow-non-delivery",
        action="store_true",
        help="record a failed run with no report instead of creating scorer inputs",
    )
    args = parser.parse_args()
    try:
        result = adapt_minimal_harness_run(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
        )
    except FileNotFoundError:
        if not args.allow_non_delivery:
            raise
        result = project_minimal_harness_non_delivery(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
        )
    print(
        json.dumps(
            {
                "report": str(result["report"]) if result.get("report") else None,
                "trace": str(result["trace"]) if result.get("trace") else None,
                "citation_map": (
                    str(result["citation_map"])
                    if result.get("citation_map")
                    else None
                ),
                "sources": str(result["sources"]),
                "projection_manifest": str(result["projection_manifest"]),
                "summary": result["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
