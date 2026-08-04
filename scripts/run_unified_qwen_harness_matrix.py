#!/usr/bin/env python3
"""Score every delivered harness report with one shared Qwen task contract.

The task-level evaluation contract is immutable and common to the matrix.
Report-bound claim ledgers and fact packets are built separately because the
reports contain different claims.  Harnesses without a delivered report are
recorded as non-deliveries rather than assigned a fabricated content score.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _score_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    score = manifest["controlled_score"]
    return {
        "provenance": score["provenance"],
        "fact": score["fact"],
        "fact_resolution_rate": score["fact_resolution_rate"],
        "evidence": score["evidence"],
        "completeness": score["completeness"],
        "rubric": score["rubric"],
        "quality": score["quality"],
        "truth_linear_diagnostic": score["truth_linear_diagnostic"],
        "truth_geometric_candidate": score["truth_geometric_candidate"],
        "formal_truth": score["formal_truth"],
        "formal_eligible": score["formal_eligible"],
        "diagnostic_label": score["diagnostic_label"],
    }


def _discover(prepared_root: Path) -> tuple[list[tuple[str, Path]], list[dict[str, Any]]]:
    delivered: list[tuple[str, Path]] = []
    non_deliveries: list[dict[str, Any]] = []
    for harness_dir in sorted(
        (path for path in prepared_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        scorer_inputs = harness_dir / "scorer-inputs"
        required = (
            scorer_inputs / "report.normalized.md",
            scorer_inputs / "trace.json",
            scorer_inputs / "citation-map.json",
        )
        if all(path.is_file() for path in required):
            delivered.append((harness_dir.name, scorer_inputs))
            continue
        projection_path = harness_dir / "projection-manifest.json"
        projection = (
            _read_json(projection_path) if projection_path.is_file() else {}
        )
        non_deliveries.append(
            {
                "harness": harness_dir.name,
                "status": "non_delivery",
                "completed": projection.get("completed"),
                "scoreable": projection.get("scoreable"),
                "run_failure": projection.get("run_failure"),
                "execution_outcome": projection.get("execution_outcome"),
                "missing_inputs": [
                    path.name for path in required if not path.is_file()
                ],
            }
        )
    return delivered, non_deliveries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-root", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--task-world-model", required=True, type=Path)
    parser.add_argument("--research-test-suite", required=True, type=Path)
    parser.add_argument("--graph-dir", required=True, type=Path)
    parser.add_argument("--url-registry", required=True, type=Path)
    parser.add_argument("--shared-task-contract", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument(
        "--judge-base-url",
        default="http://127.0.0.1:8000/v1",
    )
    parser.add_argument(
        "--fact-search-base-url",
        default="http://127.0.0.1:8081",
    )
    parser.add_argument(
        "--single-run-script",
        type=Path,
        default=Path(__file__).with_name(
            "run_unified_qwen_controlled_score.py"
        ),
    )
    args = parser.parse_args()

    delivered, non_deliveries = _discover(args.prepared_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    progress_path = args.output_root / "matrix-progress.json"
    summary_path = args.output_root / "matrix-summary.json"
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, (harness, inputs) in enumerate(delivered, 1):
        output_dir = args.output_root / harness
        manifest_path = output_dir / "unified-qwen-run-manifest.json"
        if manifest_path.is_file():
            manifest = _read_json(manifest_path)
            results.append(
                {
                    "harness": harness,
                    "status": "scored",
                    **_score_projection(manifest),
                }
            )
            continue

        command = [
            sys.executable,
            str(args.single_run_script),
            "--task",
            str(args.task),
            "--report",
            str(inputs / "report.normalized.md"),
            "--trace",
            str(inputs / "trace.json"),
            "--citation-map",
            str(inputs / "citation-map.json"),
            "--task-world-model",
            str(args.task_world_model),
            "--research-test-suite",
            str(args.research_test_suite),
            "--graph-dir",
            str(args.graph_dir),
            "--url-registry",
            str(args.url_registry),
            "--shared-task-contract",
            str(args.shared_task_contract),
            "--output-root",
            str(output_dir),
            "--model",
            args.model,
            "--judge-base-url",
            args.judge_base_url,
            "--fact-search-base-url",
            args.fact_search_base_url,
        ]
        _write_json(
            progress_path,
            {
                "schema": "dra_unified_qwen_harness_matrix_progress_v1",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "current_harness": harness,
                "current_index": index,
                "delivered_count": len(delivered),
                "completed": results,
                "failures": failures,
                "non_deliveries": non_deliveries,
            },
        )
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failures.append(
                {
                    "harness": harness,
                    "status": "scorer_failed",
                    "returncode": completed.returncode,
                }
            )
            continue
        manifest = _read_json(manifest_path)
        results.append(
            {
                "harness": harness,
                "status": "scored",
                **_score_projection(manifest),
            }
        )

    ranked = sorted(
        results,
        key=lambda row: (
            row["truth_linear_diagnostic"],
            row["evidence"],
            row["completeness"],
        ),
        reverse=True,
    )
    summary = {
        "schema": "dra_unified_qwen_harness_matrix_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "judge_model": args.model,
        "shared_task_contract": str(args.shared_task_contract.resolve()),
        "score_interpretation": (
            "retrospective diagnostic; formal eligibility is reported per run"
        ),
        "delivered_count": len(delivered),
        "scored_count": len(results),
        "scorer_failure_count": len(failures),
        "non_delivery_count": len(non_deliveries),
        "ranking_by_truth_linear_diagnostic": ranked,
        "scorer_failures": failures,
        "non_deliveries": non_deliveries,
    }
    _write_json(summary_path, summary)
    _write_json(
        progress_path,
        {
            **summary,
            "schema": "dra_unified_qwen_harness_matrix_progress_v1",
            "finished": True,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
