#!/usr/bin/env python3
"""Gate Q1-v2 on its first cell, then run and score the remaining matrix."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CROSS5_CELL_IDS = (
    "biodiversity-q1-v2--deerflow--gpt-5-6-sol",
    "biodiversity-q1-v2--deerflow--gemini-3-1-pro-preview",
    "biodiversity-q1-v2--deerflow--claude-opus-5",
    "biodiversity-q1-v2--opencode--gpt-5-6-sol",
    "biodiversity-q1-v2--claude-code--gpt-5-6-sol",
)
SCORE_VERSION_RE = re.compile(r"score-v[1-9][0-9]*\Z")


def validated_score_version(value: str) -> str:
    if not SCORE_VERSION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "score version must match score-v[1-9][0-9]*"
        )
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_gate_receipt(path: Path, expected_status: str) -> dict[str, Any]:
    document = read_json(path)
    if document.get("status") != expected_status:
        raise ValueError(f"gate receipt is not {expected_status}: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "status": expected_status,
    }


def run_logged(command: list[str], log_dir: Path, label: str) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{label}.stdout.log").open("ab") as stdout, (
        log_dir / f"{label}.stderr.log"
    ).open("ab") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr)
    return int(completed.returncode)


def cell_state(run_dir: Path, cell_id: str) -> dict[str, Any]:
    return read_json(run_dir / "cells" / cell_id / "state.json")


def score_command(args: argparse.Namespace, cell_id: str, attempt_index: int) -> list[str]:
    judge_config = getattr(args, "judge_config", None)
    if judge_config is None:
        judge_config = args.scorer_dir / "config/judge.glm5d2.v1.json"
    return [
        sys.executable,
        str(ROOT / "scripts/score_matrix_cell.py"),
        "--matrix-run-dir", str(args.runs_root / args.run_id),
        "--cell-id", cell_id,
        "--attempt-index", str(attempt_index),
        "--score-version", args.score_version,
        "--output-root", str(args.scores_root / args.run_id),
        "--scorer-dir", str(args.scorer_dir),
        "--judge-config", str(judge_config),
        "--package-dir", str(args.package_dir),
        "--audit-script", str(args.audit_script),
        "--scorer-root", str(args.scorer_root),
        "--pricing", str(args.pricing),
    ]


def evaluation_path(args: argparse.Namespace, cell_id: str, attempt_index: int) -> Path:
    return (
        args.scores_root
        / args.run_id
        / cell_id
        / f"attempt-{attempt_index}"
        / args.score_version
        / "cell-evaluation.json"
    )


def valid_evaluation(path: Path) -> bool:
    if not path.is_file():
        return False
    document = read_json(path)
    if document.get("status") != "SCORED":
        return False
    metrics = document.get("metrics") if isinstance(document.get("metrics"), dict) else {}
    return all(
        isinstance((metrics.get(name) or {}).get("score"), (int, float))
        and not isinstance((metrics.get(name) or {}).get("score"), bool)
        for name in ("citation_binding", "gcp", "grr")
    ) and (metrics.get("grr") or {}).get("denominator") == 34


async def score_all(
    args: argparse.Namespace,
    cells: list[tuple[str, int]],
    concurrency: int,
    log_dir: Path,
) -> dict[str, int]:
    gate = asyncio.Semaphore(concurrency)
    results: dict[str, int] = {}

    async def one(cell_id: str, attempt_index: int) -> None:
        path = evaluation_path(args, cell_id, attempt_index)
        if valid_evaluation(path):
            results[cell_id] = 0
            return
        async with gate:
            process = await asyncio.create_subprocess_exec(
                *score_command(args, cell_id, attempt_index),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            cell_log = log_dir / "scoring" / args.score_version / cell_id
            cell_log.mkdir(parents=True, exist_ok=True)
            (cell_log / "stdout.log").write_bytes(stdout)
            (cell_log / "stderr.log").write_bytes(stderr)
            results[cell_id] = int(process.returncode)

    await asyncio.gather(*(one(cell, attempt) for cell, attempt in cells))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--scores-root", required=True, type=Path)
    parser.add_argument("--scorer-dir", required=True, type=Path)
    parser.add_argument(
        "--judge-config",
        type=Path,
        help=(
            "Frozen Judge runtime config passed to every Cross-5 score. "
            "Defaults to <scorer-dir>/config/judge.glm5d2.v1.json."
        ),
    )
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--audit-script", required=True, type=Path)
    parser.add_argument("--scorer-root", required=True, type=Path)
    parser.add_argument("--pricing", required=True, type=Path)
    parser.add_argument("--harness-preflight-receipt", required=True, type=Path)
    parser.add_argument("--route-probe-receipt", required=True, type=Path)
    parser.add_argument(
        "--score-version",
        default="score-v1",
        type=validated_score_version,
        help="Immutable score output version, for example score-v1 or score-v2.",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    actual_cell_ids = tuple(row.get("cell_id") for row in manifest.get("cells", []))
    if actual_cell_ids != EXPECTED_CROSS5_CELL_IDS:
        raise SystemExit("BLOCKED_MATRIX_NOT_FROZEN_CROSS5")
    if manifest.get("design") != "CROSS5_FIXED_HARNESS_FIXED_MODEL":
        raise SystemExit("BLOCKED_MATRIX_DESIGN_NOT_CROSS5")
    first_cell = manifest["cells"][0]
    if first_cell["cell_id"] != "biodiversity-q1-v2--deerflow--gpt-5-6-sol":
        raise SystemExit("BLOCKED_FIRST_CELL_BINDING")
    gates = {
        "harness_preflight": validate_gate_receipt(
            args.harness_preflight_receipt, "PASS_NO_MODEL"
        ),
        "model_routes": validate_gate_receipt(args.route_probe_receipt, "PASS"),
    }
    harness_receipt = read_json(args.harness_preflight_receipt)
    if harness_receipt.get("matrix_manifest_sha256") != sha256_file(args.manifest):
        raise SystemExit("BLOCKED_HARNESS_PREFLIGHT_MANIFEST_MISMATCH")
    if harness_receipt.get("matrix_cell_count") != 5:
        raise SystemExit("BLOCKED_HARNESS_PREFLIGHT_NOT_CROSS5")
    run_dir = args.runs_root / args.run_id
    logs = run_dir / "supervisor"
    state_path = args.scores_root / args.run_id / "goal-state.json"
    write_atomic(
        state_path,
        {
            "schema_version": "q1_v2_goal_state_v1",
            "run_id": args.run_id,
            "stage": "starting",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "gates": gates,
            "score_version": args.score_version,
        },
    )

    if not run_dir.exists():
        if args.resume:
            raise SystemExit("BLOCKED_RESUME_RUN_MISSING")
        write_atomic(state_path, {"run_id": args.run_id, "stage": "first_cell_running", "gates": gates})
        code = run_logged(
            [
                sys.executable,
                str(ROOT / "scripts/matrix_executor.py"),
                "--run-id", args.run_id,
                "--manifest", str(args.manifest),
                "--runs-root", str(args.runs_root),
                "--execute",
                "--cell-id", first_cell["cell_id"],
            ],
            logs,
            "first-cell",
        )
        if code:
            write_atomic(state_path, {"run_id": args.run_id, "stage": "first_cell_executor_failed", "exit_code": code, "gates": gates})
            return 10

    first_state = cell_state(run_dir, first_cell["cell_id"])
    if first_state.get("status") != "success":
        write_atomic(state_path, {"run_id": args.run_id, "stage": "first_cell_not_success", "first_cell_state": first_state, "gates": gates})
        return 11
    first_attempt = int(first_state.get("attempt_count") or 0)
    first_evaluation = evaluation_path(args, first_cell["cell_id"], first_attempt)
    if not valid_evaluation(first_evaluation):
        write_atomic(state_path, {"run_id": args.run_id, "stage": "first_cell_scoring", "first_cell_state": first_state, "gates": gates})
        code = run_logged(
            score_command(args, first_cell["cell_id"], first_attempt),
            logs,
            f"first-cell-{args.score_version}",
        )
        if code or not valid_evaluation(first_evaluation):
            write_atomic(state_path, {"run_id": args.run_id, "stage": "first_cell_score_failed", "exit_code": code, "gates": gates})
            return 12

    first_doc = read_json(first_evaluation)
    write_atomic(
        args.scores_root / args.run_id / "first-cell-gate.json",
        {
            "schema_version": "q1_v2_first_cell_gate_v1",
            "decision": "PASS_CONTINUE_REMAINING_4",
            "cell_id": first_cell["cell_id"],
            "attempt_index": first_attempt,
            "metrics": first_doc["metrics"],
            "agent": first_doc["agent"],
            "judge": first_doc["judge"],
            "evaluation_sha256": sha256_file(first_evaluation),
            "score_version": args.score_version,
            "gates": gates,
        },
    )

    pending = [
        cell for cell in manifest["cells"]
        if cell_state(run_dir, cell["cell_id"]).get("status") == "pending"
    ]
    if pending:
        write_atomic(state_path, {"run_id": args.run_id, "stage": "remaining_4_running", "pending": len(pending), "gates": gates})
        code = run_logged(
            [
                sys.executable,
                str(ROOT / "scripts/matrix_executor.py"),
                "--run-id", args.run_id,
                "--manifest", str(args.manifest),
                "--runs-root", str(args.runs_root),
                "--resume",
                "--execute",
                "--parallel",
                "--global-cells", str(manifest["concurrency"]["global_cells"]),
            ],
            logs,
            "remaining-cells",
        )
        if code:
            write_atomic(state_path, {"run_id": args.run_id, "stage": "remaining_executor_failed", "exit_code": code, "gates": gates})
            return 13

    successful = []
    status_counts: dict[str, int] = {}
    for cell in manifest["cells"]:
        state = cell_state(run_dir, cell["cell_id"])
        status = str(state.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "success":
            successful.append((cell["cell_id"], int(state.get("attempt_count") or 0)))
    write_atomic(state_path, {"run_id": args.run_id, "stage": "scoring", "matrix_status_counts": status_counts, "score_candidates": len(successful), "gates": gates})
    score_results = asyncio.run(
        score_all(
            args,
            successful,
            int(manifest["concurrency"]["judge_requests"]),
            logs,
        )
    )
    scored = sum(
        valid_evaluation(evaluation_path(args, cell_id, attempt))
        for cell_id, attempt in successful
    )
    result = {
        "schema_version": "q1_v2_goal_result_v1",
        "run_id": args.run_id,
        "matrix_cell_count": 5,
        "matrix_status_counts": status_counts,
        "scored_cell_count": scored,
        "score_version": args.score_version,
        "score_process_failures": sorted(
            cell_id for cell_id, code in score_results.items() if code != 0
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "goal_complete": scored == 5 and status_counts == {"success": 5},
    }
    write_atomic(args.scores_root / args.run_id / "goal-result.json", result)
    write_atomic(state_path, {**result, "stage": "complete" if result["goal_complete"] else "incomplete"})
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["goal_complete"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
