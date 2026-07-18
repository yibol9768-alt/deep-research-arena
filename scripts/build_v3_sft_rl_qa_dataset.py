#!/usr/bin/env python3
"""Build graph-derived SFT QA and replay-scored RL QA from DRA v3 suites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tasks.benchmark_sft_dataset_v3 import DatasetBuildError  # noqa: E402
from src.tasks.sft_rl_qa_dataset_v3 import (  # noqa: E402
    BuildOptions,
    build_sft_rl_qa_dataset,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates-root",
        default="data/pilot_v3/formal_candidates",
    )
    parser.add_argument(
        "--out-dir",
        default="data/pilot_v3/sft_rl_qa_v1",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="include synthetic-only suites and preserve that label",
    )
    parser.add_argument(
        "--allow-intentional-overlap",
        action="store_true",
        help="acknowledge source-task reuse across training/evaluation pilot data",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_sft_rl_qa_dataset(
            args.candidates_root,
            args.out_dir,
            options=BuildOptions(
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
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

