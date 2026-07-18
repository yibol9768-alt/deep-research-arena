#!/usr/bin/env python3
"""Build or verify a formal DRA v3 protocol manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

# Allow direct execution from any working directory, not only repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.protocol_manifest_v3 import (
    verify_v3_protocol_manifest,
    write_v3_protocol_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind a verified evidence graph, complete corpus registry, and exact "
            "compiled DRA v3 cases into one deterministic formal protocol manifest."
        )
    )
    parser.add_argument(
        "--graph-dir",
        required=True,
        type=Path,
        help="directory containing the verified evidence-graph artifact set",
    )
    parser.add_argument(
        "--case",
        dest="cases",
        required=True,
        action="append",
        type=Path,
        help="compiled private CaseSpecV3 JSON (repeat for each task)",
    )
    parser.add_argument(
        "--public-task",
        dest="public_tasks",
        action="append",
        type=Path,
        required=True,
        help="aligned public rendered-task JSON (repeat exactly once for every case)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--out",
        type=Path,
        help="build and write a new canonical manifest to this path",
    )
    mode.add_argument(
        "--verify",
        type=Path,
        metavar="MANIFEST",
        help="verify this existing manifest against the supplied artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verify is not None:
            manifest = verify_v3_protocol_manifest(
                args.verify,
                args.graph_dir,
                args.cases,
                public_task_paths=args.public_tasks,
            )
            action = "verified"
            target = args.verify
        else:
            manifest = write_v3_protocol_manifest(
                args.graph_dir,
                args.cases,
                args.out,
                public_task_paths=args.public_tasks,
            )
            action = "written"
            target = args.out
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = {
        "status": "ok",
        "action": action,
        "manifest": str(target),
        "manifest_sha256": manifest["manifest_sha256"],
        "n_tasks": len(manifest["task_ids"]),
        "public_tasks_bound": bool(manifest["public_task_hashes"]),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
