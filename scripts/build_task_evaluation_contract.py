#!/usr/bin/env python3
"""Compile once, then seal a report-independent DRA task contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.audited_judge import AuditedJudge
from src.scoring.task_evaluation_contract import (
    CONTRACT_SEMANTICS,
    seal_compiled_task_contract,
)
from src.scoring.task_manifest_compiler import compile_task_manifest


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--task-world-model", required=True, type=Path)
    parser.add_argument("--research-test-suite", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument(
        "--contract-semantics",
        required=True,
        choices=sorted(CONTRACT_SEMANTICS),
        help=(
            "use transition_legacy_exact only to reproduce historical "
            "diagnostics; research_obligations_v1 is the target design"
        ),
    )
    parser.add_argument(
        "--frozen-before-report-input",
        action="store_true",
        help=(
            "attest that this build occurred before any evaluated report was "
            "available; do not use this flag for retrospective pilot assets"
        ),
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    build_dir = output_dir / "_build_audit"
    judge = AuditedJudge(build_dir / "judge_calls", model=args.model)
    task = _read_json(args.task)
    task_world_model = _read_json(args.task_world_model)
    research_test_suite = _read_json(args.research_test_suite)
    compile_task_manifest(
        task,
        task_world_model,
        research_test_suite,
        judge,
        build_dir / "compiled",
    )
    contract = seal_compiled_task_contract(
        compiled_dir=build_dir / "compiled",
        output_dir=output_dir,
        task=task,
        task_world_model=task_world_model,
        research_test_suite=research_test_suite,
        contract_semantics=args.contract_semantics,
        frozen_before_report_input=args.frozen_before_report_input,
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir.resolve()),
                "task_id": contract["manifest"]["task_id"],
                "contract_sha256": contract["manifest"]["contract_sha256"],
                "contract_semantics": contract["manifest"][
                    "contract_semantics"
                ],
                "counts": contract["manifest"]["counts"],
                "formal_eligible": contract["manifest"]["formal_eligible"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
