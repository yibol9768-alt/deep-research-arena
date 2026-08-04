#!/usr/bin/env python3
"""Seal an existing report-blind compiler output as a reusable task contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.task_evaluation_contract import (
    CONTRACT_SEMANTICS,
    seal_compiled_task_contract,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiled-dir", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--task-world-model", required=True, type=Path)
    parser.add_argument("--research-test-suite", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--contract-semantics",
        required=True,
        choices=sorted(CONTRACT_SEMANTICS),
    )
    parser.add_argument(
        "--frozen-before-report-input",
        action="store_true",
        help=(
            "attest that the compiler output was created before evaluated "
            "reports existed; omit for retrospective pilot contracts"
        ),
    )
    args = parser.parse_args()
    contract = seal_compiled_task_contract(
        compiled_dir=args.compiled_dir,
        output_dir=args.output_dir,
        task=_read_json(args.task),
        task_world_model=_read_json(args.task_world_model),
        research_test_suite=_read_json(args.research_test_suite),
        contract_semantics=args.contract_semantics,
        frozen_before_report_input=args.frozen_before_report_input,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "task_id": contract["manifest"]["task_id"],
                "contract_sha256": contract["manifest"]["contract_sha256"],
                "contract_semantics": contract["manifest"][
                    "contract_semantics"
                ],
                "counts": contract["manifest"]["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
