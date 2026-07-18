#!/usr/bin/env python3
"""Export replay-validated DRA v3 cases as benchmark and SFT-QA pilot data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tasks.benchmark_sft_dataset_v3 import (  # noqa: E402
    BuildOptions,
    DatasetBuildError,
    build_same_task_pilot,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates-root",
        default="data/pilot_v3/formal_candidates",
        help=(
            "directory whose children contain either oracle_suite/suite.json "
            "or oracle_suites/synthetic/suite.json"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="data/pilot_v3/benchmark_sft_same_task_pilot_v1",
    )
    parser.add_argument("--oracle-kind", default="machine")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="include suites labelled synthetic_only (pilot use only)",
    )
    parser.add_argument(
        "--allow-intentional-overlap",
        action="store_true",
        help="acknowledge that every exported benchmark query also enters SFT",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_same_task_pilot(
            args.candidates_root,
            args.out_dir,
            options=BuildOptions(
                oracle_kind=args.oracle_kind,
                allow_synthetic=bool(args.allow_synthetic),
                allow_intentional_overlap=bool(args.allow_intentional_overlap),
            ),
        )
    except DatasetBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "built",
                "output_dir": str(Path(args.out_dir)),
                "dataset_id": manifest["dataset_id"],
                "dataset_sha256": manifest["dataset_sha256"],
                "counts": manifest["counts"],
                "overlap_policy": manifest["overlap_policy"]["kind"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
