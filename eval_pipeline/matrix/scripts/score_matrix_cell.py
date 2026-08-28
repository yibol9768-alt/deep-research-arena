#!/usr/bin/env python3
"""Project, score, price and seal one successful Q1-v2 matrix attempt."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from summarize_cross5_pilot import Pricing, add_tokens, attempt_record, load_score


SCORE_VERSION_RE = re.compile(r"score-v[1-9][0-9]*\Z")


def validated_score_version(value: str) -> str:
    if not SCORE_VERSION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "score version must match score-v[1-9][0-9]*"
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)


def numeric_metrics(score: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = score.get("metrics")
    if not isinstance(source, dict):
        raise ValueError("shadow score lacks metrics")
    metrics: dict[str, dict[str, Any]] = {}
    for name in ("citation_binding", "gcp", "grr"):
        row = source.get(name)
        source_status = str(row.get("status") or "") if isinstance(row, dict) else ""
        if not isinstance(row, dict) or not source_status.startswith("scored"):
            raise ValueError(f"{name} is not scored")
        value = row.get("score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} is not numeric")
        value = float(value)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} is outside [0,1]")
        numerator = row.get(
            "passed_required_claim_count",
            row.get("grounded_claim_count", row.get("grounded_unit_count")),
        )
        denominator = row.get(
            "required_claim_count",
            row.get("eligible_claim_count", row.get("necessary_unit_count")),
        )
        metrics[name] = {
            "score": value,
            "status": "scored",
            "source_status": source_status,
            "numerator": numerator,
            "denominator": denominator,
        }
    if metrics["grr"]["denominator"] != 34:
        raise ValueError("GRR denominator is not the frozen 34")
    return metrics


def run_checked(command: list[str], stdout_path: Path, stderr_path: Path) -> None:
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr)
    if completed.returncode:
        raise RuntimeError(
            f"subprocess failed with exit {completed.returncode}: {command[1]}"
        )


def seal_tree(root: Path, output: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != output:
            files.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    document = {"schema_version": "q1_v2_cell_evaluation_seal_v1", "files": files}
    write_exclusive(output, document)
    return document


def score_cell(args: argparse.Namespace) -> dict[str, Any]:
    score_version = validated_score_version(args.score_version)
    judge_config = getattr(args, "judge_config", None)
    if judge_config is None:
        judge_config = args.scorer_dir / "config/judge.glm5d2.v1.json"
    judge_config = Path(judge_config).resolve()
    if not judge_config.is_file():
        raise ValueError(f"judge config is missing: {judge_config}")
    run_dir = args.matrix_run_dir.resolve()
    run_header = read_json(run_dir / "run.json")
    matrix_run_id = str(run_header["run_id"])
    attempt_dir = run_dir / "cells" / args.cell_id / f"attempt-{args.attempt_index}"
    exit_status = read_json(attempt_dir / "exit_status.json")
    identity = read_json(attempt_dir / "identity.json")
    observability = read_json(attempt_dir / "observability.json")
    provenance = read_json(attempt_dir / "report_provenance.json")
    if exit_status.get("status") != "success" or exit_status.get("exit_code") != 0:
        raise ValueError("matrix attempt is not a successful agent return")
    if identity.get("identity_consistent") is not True:
        raise ValueError("matrix attempt identity is not consistent")
    if not all(
        observability.get(key) is True
        for key in ("recorder_initialized", "capture_bracket_valid", "capture_healthy")
    ):
        raise ValueError("matrix attempt recorder health is not valid")
    if provenance.get("model_output_attested") is not True:
        raise ValueError("matrix report provenance is not attested")

    base = (
        args.output_root.resolve()
        / args.cell_id
        / f"attempt-{args.attempt_index}"
        / score_version
    )
    base.mkdir(parents=True, exist_ok=False)
    projection_dir = base / "projection"
    score_dir = base / "score"
    scoring_run_id = (
        f"{matrix_run_id}--{args.cell_id}--attempt-{args.attempt_index}--"
        f"{score_version}"
    )
    run_checked(
        [
            sys.executable,
            str(args.scorer_dir / "prepare_matrix_cell.py"),
            "--attempt-dir", str(attempt_dir),
            "--package-dir", str(args.package_dir),
            "--output-dir", str(projection_dir),
            "--run-id", scoring_run_id,
        ],
        base / "projection.stdout.log",
        base / "projection.stderr.log",
    )
    run_checked(
        [
            sys.executable,
            str(args.scorer_dir / "auto_score_biodiv_q1.py"),
            "--package-dir", str(args.package_dir),
            "--report", str(attempt_dir / "report.md"),
            "--ledger", str(projection_dir / "strict-evidence.jsonl"),
            "--run-manifest", str(projection_dir / "run-manifest.json"),
            "--output-dir", str(score_dir),
            "--run-id", scoring_run_id,
            "--judge-config", str(judge_config),
            "--aggregator", str(args.audit_script),
            "--scorer-root", str(args.scorer_root),
        ],
        base / "score.stdout.log",
        base / "score.stderr.log",
    )
    score_receipt = read_json(score_dir / "run-receipt.json")
    if score_receipt.get("status") != "SCORED":
        raise ValueError("automatic scorer did not return SCORED")
    shadow_score = read_json(score_dir / "shadow-score.json")
    metrics = numeric_metrics(shadow_score)

    pricing = Pricing(args.pricing)
    attempt = attempt_record(matrix_run_id, args.cell_id, attempt_dir, pricing, [])
    if not attempt["requests"]:
        raise ValueError("successful attempt has no attributable gateway usage")
    for row in attempt["requests"]:
        if row["cell_id"] != args.cell_id or row["identity_match"] is not True:
            raise ValueError("agent usage attribution or identity mismatch")
    score_view = load_score(
        score_dir,
        (matrix_run_id, args.cell_id, args.attempt_index),
        pricing,
    )
    evaluation = {
        "schema_version": "q1_v2_cell_evaluation_v1",
        "status": "SCORED",
        "matrix_run_id": matrix_run_id,
        "cell_id": args.cell_id,
        "attempt_index": args.attempt_index,
        "scoring_run_id": scoring_run_id,
        "formal_eligible": False,
        "release_mode": "shadow_experimental",
        "metrics": metrics,
        "agent": {
            "request_count": len(attempt["requests"]),
            "tokens": attempt["agent_tokens"],
            "cost": attempt["agent_cost"],
        },
        "judge": {
            "request_count": len(score_view["judge_calls"]),
            "tokens": score_view["judge_tokens"],
            "cost": score_view["judge_cost"],
            "identity_all_match": all(
                row.get("identity_match") is True for row in score_view["judge_calls"]
            ) if score_view["judge_calls"] else True,
        },
        "artifacts": {
            "report_sha256": sha256_file(attempt_dir / "report.md"),
            "projection_receipt_sha256": sha256_file(projection_dir / "projection-receipt.json"),
            "citation_diagnostics_sha256": sha256_file(projection_dir / "citation-diagnostics.json"),
            "score_receipt_sha256": sha256_file(score_dir / "run-receipt.json"),
            "shadow_score_sha256": sha256_file(score_dir / "shadow-score.json"),
            "judge_config_sha256": sha256_file(judge_config),
        },
    }
    write_exclusive(base / "cell-evaluation.json", evaluation)
    seal_tree(base, base / "cell-evaluation-seal.json")
    return evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-run-dir", required=True, type=Path)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--attempt-index", required=True, type=int)
    parser.add_argument(
        "--score-version",
        default="score-v1",
        type=validated_score_version,
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--scorer-dir", required=True, type=Path)
    parser.add_argument(
        "--judge-config",
        type=Path,
        help=(
            "Frozen Judge runtime config. Defaults to "
            "<scorer-dir>/config/judge.glm5d2.v1.json."
        ),
    )
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--audit-script", required=True, type=Path)
    parser.add_argument("--scorer-root", required=True, type=Path)
    parser.add_argument("--pricing", required=True, type=Path)
    args = parser.parse_args()
    result = score_cell(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
