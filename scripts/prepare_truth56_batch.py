#!/usr/bin/env python3
"""Prepare the fixed 56-task harness matrix and deterministically prefilter P=0.

The script combines the original 12-harness batch with an optional replacement
rerun for selected harnesses.  It adapts every delivered report into the
four-axis scorer contract, computes URL Provenance without an LLM, and writes a
sealed lane manifest.  Report non-delivery and evaluator preparation failures
remain distinct states.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.four_axis_pipeline import cited_url_rows
from src.scoring.four_axis_score import _provenance_score
from src.scoring.minimal_harness_artifact_adapter import adapt_minimal_harness_run
from src.scoring.url_registry import FrozenURLRegistry


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def original_run_root(matrix_dir: Path, harness: str) -> Path | None:
    stdout = matrix_dir / harness / "stdout.log"
    if not stdout.exists():
        return None
    candidates: list[Path] = []
    for line in stdout.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        text = line.strip()
        if not text.startswith("/") or not text.endswith(".json"):
            continue
        path = Path(text)
        if path.parent.name == "control" and path.is_file():
            candidates.append(path)
    return candidates[-1].parent.parent if candidates else None


def task_path_for(task_root: Path, task_id: str) -> Path:
    matches = list(task_root.rglob(f"{task_id}.json"))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one task file for {task_id}, found {len(matches)}"
        )
    return matches[0]


def prepare_lane(
    lane: dict[str, Any],
    output_dir: Path,
    registry_path: Path,
) -> dict[str, Any]:
    harness = str(lane["harness"])
    task_id = str(lane["task_id"])
    result = dict(lane)
    if (
        lane.get("source_batch") == "replacement"
        and lane.get("source_status") != "success"
    ):
        result.update(
            {
                "lane_status": "report_generation_failure",
                "truth": 0.0,
                "zero_reason": "replacement_audit_terminal_failure",
            }
        )
        return result
    run_root_text = lane.get("run_root")
    if not run_root_text:
        result.update(
            {
                "lane_status": "report_generation_failure",
                "truth": 0.0,
                "zero_reason": "no_run_manifest",
            }
        )
        return result

    run_root = Path(str(run_root_text))
    prepared = output_dir / "prepared" / harness / task_id
    try:
        adapted = adapt_minimal_harness_run(
            run_dir=run_root,
            output_dir=prepared,
        )
    except FileNotFoundError as exc:
        result.update(
            {
                "lane_status": "report_generation_failure",
                "truth": 0.0,
                "zero_reason": "no_delivered_report",
                "detail": str(exc),
            }
        )
        return result
    except Exception as exc:  # evaluator failures must never become task zeros
        result.update(
            {
                "lane_status": "preparation_failure",
                "error_type": type(exc).__name__,
                "detail": str(exc),
            }
        )
        return result

    report_path = Path(adapted["report"])
    citation_map_path = Path(adapted["citation_map"])
    registry = FrozenURLRegistry.load(registry_path)
    report = report_path.read_text(encoding="utf-8")
    citation_map = load_json(citation_map_path)
    url_rows = cited_url_rows(report, citation_map, registry)
    provenance = _provenance_score(url_rows)
    result.update(
        {
            "lane_status": (
                "ready_for_semantic_scoring"
                if provenance["score"] > 0
                else "deterministic_zero"
            ),
            "prepared_dir": str(prepared),
            "report": str(report_path),
            "trace": str(adapted["trace"]),
            "citation_map": str(citation_map_path),
            "provenance": provenance,
            "truth": 0.0 if provenance["score"] == 0 else None,
            "zero_reason": (
                "provenance_zero" if provenance["score"] == 0 else None
            ),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-audit", required=True, type=Path)
    parser.add_argument("--replacement-audit", type=Path)
    parser.add_argument(
        "--replacement-harness",
        action="append",
        default=[],
        help="harness whose original lanes are replaced by replacement-audit",
    )
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--assets-root", required=True, type=Path)
    parser.add_argument("--url-registry", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--excluded-task-id", action="append", default=[])
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    original = load_json(args.original_audit)
    excluded = set(args.excluded_task_id)
    task_rows = [
        row
        for row in original["tasks"]
        if row.get("status") == "complete-matrix"
        and row["task_id"] not in excluded
    ]
    if len(task_rows) != 56:
        raise RuntimeError(f"fixed matrix must contain 56 tasks, found {len(task_rows)}")

    first_matrix = Path(task_rows[0]["matrix"])
    harnesses = sorted(
        path.name
        for path in first_matrix.iterdir()
        if path.is_dir() and (path / "exit-code.txt").exists()
    )
    if len(harnesses) != 12:
        raise RuntimeError(f"expected 12 harnesses, found {harnesses}")

    replacement_harnesses = set(args.replacement_harness)
    replacement_lanes: dict[tuple[str, str], dict[str, Any]] = {}
    if args.replacement_audit:
        replacement = load_json(args.replacement_audit)
        replacement_lanes = {
            (str(row["task_id"]), str(row["harness"])): row
            for row in replacement.get("lanes", [])
        }

    lanes: list[dict[str, Any]] = []
    for task_row in task_rows:
        task_id = str(task_row["task_id"])
        task_path = task_path_for(args.task_root, task_id)
        asset_dir = args.assets_root / task_id
        required_assets = [
            asset_dir / "task-world-model.json",
            asset_dir / "research-test-suite.json",
            asset_dir / "graph" / "manifest.json",
        ]
        if not all(path.exists() for path in required_assets):
            raise RuntimeError(f"missing transition assets for {task_id}")
        matrix_dir = Path(task_row["matrix"])
        for harness in harnesses:
            source = "original"
            run_root: Path | None
            source_status: str | None = None
            if harness in replacement_harnesses:
                source = "replacement"
                replacement_lane = replacement_lanes.get((task_id, harness))
                if replacement_lane is None:
                    raise RuntimeError(
                        f"missing replacement lane for {task_id}/{harness}"
                    )
                source_status = str(replacement_lane.get("status") or "")
                run_root_value = replacement_lane.get("run_root")
                run_root = Path(str(run_root_value)) if run_root_value else None
            else:
                exit_path = matrix_dir / harness / "exit-code.txt"
                source_status = (
                    exit_path.read_text(encoding="utf-8").strip()
                    if exit_path.exists()
                    else None
                )
                run_root = original_run_root(matrix_dir, harness)
            lanes.append(
                {
                    "task_id": task_id,
                    "harness": harness,
                    "source_batch": source,
                    "source_status": source_status,
                    "run_root": str(run_root) if run_root else None,
                    "task_path": str(task_path),
                    "asset_dir": str(asset_dir),
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                prepare_lane,
                lane,
                args.output_dir,
                args.url_registry,
            ): lane
            for lane in lanes
        }
        for future in as_completed(futures):
            completed.append(future.result())

    completed.sort(key=lambda row: (row["harness"], row["task_id"]))
    manifest_path = args.output_dir / "lane-manifest.jsonl"
    manifest_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in completed
        ),
        encoding="utf-8",
    )
    status_counts: dict[str, int] = {}
    positive_by_harness: dict[str, int] = {harness: 0 for harness in harnesses}
    delivered_by_harness: dict[str, int] = {harness: 0 for harness in harnesses}
    for row in completed:
        status = str(row["lane_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in {"ready_for_semantic_scoring", "deterministic_zero"}:
            delivered_by_harness[row["harness"]] += 1
        if status == "ready_for_semantic_scoring":
            positive_by_harness[row["harness"]] += 1
    summary = {
        "schema": "dra_truth56_preparation_summary_v1",
        "task_count": len(task_rows),
        "harness_count": len(harnesses),
        "lane_count": len(completed),
        "replacement_harnesses": sorted(replacement_harnesses),
        "status_counts": dict(sorted(status_counts.items())),
        "delivered_by_harness": delivered_by_harness,
        "positive_provenance_by_harness": positive_by_harness,
        "manifest": str(manifest_path),
    }
    write_json(args.output_dir / "preparation-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status_counts.get("preparation_failure", 0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
