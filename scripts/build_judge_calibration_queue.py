#!/usr/bin/env python3
"""Export a blinded human-calibration queue from controlled judge runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.calibration_queue import build_calibration_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True, type=Path)
    parser.add_argument("--run-b", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--agreement-sample-per-axis", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260728)
    args = parser.parse_args()
    manifest = build_calibration_queue(
        args.run_a,
        args.run_b,
        args.output_dir,
        agreement_sample_per_axis=args.agreement_sample_per_axis,
        seed=args.seed,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
