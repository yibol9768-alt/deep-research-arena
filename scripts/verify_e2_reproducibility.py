#!/usr/bin/env python3
"""Compare two completed E2 builds at the logical-content boundary."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_build(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        load_json(path / "build-manifest.json"),
        load_json(path / "quality-report.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    first, first_quality = load_build(args.first)
    second, second_quality = load_build(args.second)
    first_sqlite = args.first / "world-index.sqlite"
    second_sqlite = args.second / "world-index.sqlite"
    first_raw_hash = file_sha256(first_sqlite)
    second_raw_hash = file_sha256(second_sqlite)
    first_checkpoint = first["checkpoint_summary"]
    second_checkpoint = second["checkpoint_summary"]

    checks = {
        "manifest_schema_equal": first["schema"] == second["schema"],
        "snapshot_id_equal": first["snapshot_id"] == second["snapshot_id"],
        "source_identity_id_equal": (
            first["source_identity_id"] == second["source_identity_id"]
        ),
        "view_contract_equal": first["view"] == second["view"],
        "pipeline_contract_id_equal": (
            first["pipeline_contract_id"]
            == second["pipeline_contract_id"]
        ),
        "logical_build_id_equal": (
            first["logical_build_id"] == second["logical_build_id"]
        ),
        "record_chain_equal": (
            first_checkpoint["record_chain_sha256"]
            == second_checkpoint["record_chain_sha256"]
        ),
        "census_equal": first["census"] == second["census"],
        "scan_boundary_equal": first["scan_end"] == second["scan_end"],
        "both_complete": (
            first_checkpoint["scan_complete"] is True
            and second_checkpoint["scan_complete"] is True
            and first_checkpoint["finalized"] is True
            and second_checkpoint["finalized"] is True
        ),
        "both_quality_pass": (
            first_quality["passed"] is True
            and second_quality["passed"] is True
        ),
        "sqlite_manifest_hashes_valid": (
            first["sqlite_sha256"] == first_raw_hash
            and second["sqlite_sha256"] == second_raw_hash
        ),
        "both_task_blind": (
            first["task_conditioned"] is False
            and second["task_conditioned"] is False
            and first["task_or_witness_inputs"] == []
            and second["task_or_witness_inputs"] == []
        ),
    }
    report = {
        "schema": "dra_e2_reproducibility_report_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "first": str(args.first.resolve()),
        "second": str(args.second.resolve()),
        "first_logical_build_id": first["logical_build_id"],
        "second_logical_build_id": second["logical_build_id"],
        "checks": checks,
        "diagnostics": {
            "raw_sqlite_sha256_equal": first_raw_hash == second_raw_hash,
            "first_raw_sqlite_sha256": first_raw_hash,
            "second_raw_sqlite_sha256": second_raw_hash,
            "first_checkpoint_sequence": first_checkpoint[
                "checkpoint_sequence"
            ],
            "second_checkpoint_sequence": second_checkpoint[
                "checkpoint_sequence"
            ],
        },
        "passed": all(checks.values()),
        "note": (
            "E2 reproducibility is defined over the frozen pipeline contract, "
            "logical rows, selected-record chain, and census. Raw SQLite "
            "bytes remain diagnostic because checkpoint schedules may change "
            "transaction history and physical page layout without changing "
            "logical content."
        ),
    }
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
