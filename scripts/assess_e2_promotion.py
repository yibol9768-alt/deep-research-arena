#!/usr/bin/env python3
"""Issue a machine-readable promotion gate between nested E2 views."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any


VIEW_ORDER = ("w100k", "w1m", "wfull")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def monotonic(values: list[float]) -> bool:
    return all(right >= left for left, right in zip(values, values[1:]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--canonical-audit", type=Path, required=True)
    parser.add_argument("--http-audit", type=Path, required=True)
    parser.add_argument("--native-audit", type=Path, required=True)
    parser.add_argument("--identity-audit", type=Path, required=True)
    parser.add_argument("--next-view", choices=VIEW_ORDER, required=True)
    parser.add_argument("--available-disk-bytes", type=int, required=True)
    parser.add_argument("--total-memory-bytes", type=int, required=True)
    parser.add_argument("--max-runtime-hours", type=float, default=168.0)
    parser.add_argument("--disk-usable-fraction", type=float, default=0.80)
    parser.add_argument("--memory-usable-fraction", type=float, default=0.80)
    parser.add_argument("--disk-uncertainty-factor", type=float, default=1.25)
    parser.add_argument("--runtime-uncertainty-factor", type=float, default=1.50)
    parser.add_argument("--memory-uncertainty-factor", type=float, default=2.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    for name in ("disk_usable_fraction", "memory_usable_fraction"):
        value = float(getattr(args, name))
        if not 0 < value <= 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be in (0,1]")
    for name in (
        "disk_uncertainty_factor",
        "runtime_uncertainty_factor",
        "memory_uncertainty_factor",
    ):
        if float(getattr(args, name)) < 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be >= 1")

    build_dir = args.build_dir.resolve()
    manifest = load(build_dir / "build-manifest.json")
    quality = load(build_dir / "quality-report.json")
    resource = load(build_dir / "resource-report.json")
    canonical = load(args.canonical_audit.resolve())
    http = load(args.http_audit.resolve())
    native = load(args.native_audit.resolve())
    identity = load(args.identity_audit.resolve())
    db_path = build_dir / "world-index.sqlite"
    current_view = str(manifest["view"]["view_id"])
    current_index = VIEW_ORDER.index(current_view)
    expected_next = (
        VIEW_ORDER[current_index + 1]
        if current_index + 1 < len(VIEW_ORDER)
        else None
    )
    next_contract = manifest["nested_view_contracts"][args.next_view]
    observed_documents = int(manifest["census"]["documents"])
    target_documents = int(next_contract["target_documents"])
    expansion = target_documents / observed_documents
    observed_sqlite = int(resource["sqlite_bytes"])
    observed_elapsed = float(resource["elapsed_seconds"])
    observed_rss = int(resource["peak_rss_kib"]) * 1024
    point_disk = observed_sqlite * expansion
    point_runtime = observed_elapsed * expansion
    upper_disk = point_disk * args.disk_uncertainty_factor
    upper_runtime = point_runtime * args.runtime_uncertainty_factor
    upper_rss = observed_rss * args.memory_uncertainty_factor
    disk_budget = args.available_disk_bytes * args.disk_usable_fraction
    memory_budget = args.total_memory_bytes * args.memory_usable_fraction
    curve = list(resource.get("resource_curve") or [])
    thresholds = [
        int(manifest["nested_view_contracts"][name][
            "rank_threshold_exclusive"
        ])
        for name in VIEW_ORDER
    ]

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        integrity = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        documents = int(connection.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0])
        fts_rows = int(connection.execute(
            "SELECT COUNT(*) FROM search_fts"
        ).fetchone()[0])
    finally:
        connection.close()
    actual_sqlite_hash = file_sha256(db_path)

    checks = {
        "next_view_is_immediate_successor": args.next_view == expected_next,
        "full_source_scan": (
            manifest.get("full_source_scan") is True
            and int(manifest["scan_end"])
            == int(manifest["source_identity"]["entry_count"])
        ),
        "compiler_quality_pass": (
            manifest.get("source_and_build_gates_pass") is True
            and quality.get("passed") is True
        ),
        "canonical_audit_pass": (
            canonical.get("passed") is True
            and canonical.get("logical_build_id")
            == manifest.get("logical_build_id")
        ),
        "http_audit_pass": (
            http.get("passed") is True
            and http.get("logical_build_id")
            == manifest.get("logical_build_id")
            and http.get("sqlite_sha256") == manifest.get("sqlite_sha256")
        ),
        "native_route_audit_pass": (
            native.get("passed") is True
            and native.get("logical_build_id")
            == manifest.get("logical_build_id")
            and native.get("sqlite_sha256")
            == manifest.get("sqlite_sha256")
        ),
        "url_identity_audit_pass": (
            identity.get("passed") is True
            and identity.get("view", {}).get("view_id") == current_view
            and int(identity.get("scan_end") or -1)
            == int(manifest["source_identity"]["entry_count"])
            and int(identity.get("selected") or -1) == observed_documents
            and identity.get("zim_uuid")
            == manifest["source_identity"].get("zim_uuid")
            and identity.get("url_identity_version")
            == manifest["source_identity"].get("url_identity_version")
        ),
        "sqlite_manifest_hash_valid": (
            actual_sqlite_hash == manifest.get("sqlite_sha256")
        ),
        "sqlite_integrity_ok": integrity == "ok",
        "database_census_consistent": (
            documents == observed_documents and fts_rows == documents
        ),
        "no_failure_artifact": not (build_dir / "failure.json").exists(),
        "task_blind": (
            manifest.get("task_conditioned") is False
            and manifest.get("task_or_witness_inputs") == []
        ),
        "nested_thresholds_monotonic": thresholds == sorted(thresholds),
        "resource_curve_present": len(curve) >= 3,
        "resource_curve_scanned_monotonic": monotonic([
            float(point["scanned"]) for point in curve
        ]),
        "resource_curve_compiled_monotonic": monotonic([
            float(point["compiled"]) for point in curve
        ]),
        "resource_curve_disk_monotonic": monotonic([
            float(point["sqlite_allocated_bytes"]) for point in curve
        ]),
        "next_view_fits_disk_budget": upper_disk <= disk_budget,
        "next_view_fits_memory_budget": upper_rss <= memory_budget,
        "next_view_fits_runtime_budget": (
            upper_runtime <= args.max_runtime_hours * 3600
        ),
    }
    promote = all(checks.values())
    report = {
        "schema": "dra_e2_view_promotion_report_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "build_dir": str(build_dir),
        "logical_build_id": manifest["logical_build_id"],
        "pipeline_contract_id": manifest["pipeline_contract_id"],
        "current_view": current_view,
        "next_view": args.next_view,
        "audit_inputs": {
            "canonical": str(args.canonical_audit.resolve()),
            "http_projection": str(args.http_audit.resolve()),
            "native_route": str(args.native_audit.resolve()),
            "url_identity": str(args.identity_audit.resolve()),
        },
        "checks": checks,
        "observed": {
            "documents": observed_documents,
            "sqlite_bytes": observed_sqlite,
            "elapsed_seconds": observed_elapsed,
            "peak_rss_bytes": observed_rss,
            "resource_curve_points": len(curve),
            "sqlite_integrity": integrity,
        },
        "projection": {
            "target_documents": target_documents,
            "conservative_expansion_factor": expansion,
            "point_sqlite_bytes": point_disk,
            "upper_sqlite_bytes": upper_disk,
            "point_runtime_hours": point_runtime / 3600,
            "upper_runtime_hours": upper_runtime / 3600,
            "upper_peak_rss_bytes": upper_rss,
            "disk_uncertainty_factor": args.disk_uncertainty_factor,
            "runtime_uncertainty_factor": args.runtime_uncertainty_factor,
            "memory_uncertainty_factor": args.memory_uncertainty_factor,
            "note": (
                "Runtime is conservatively scaled by selected-document "
                "expansion even though all nested views scan the same source "
                "population. Safety factors are operational margins, not "
                "statistical confidence intervals. The completed next view "
                "supersedes this projection."
            ),
        },
        "host_budget": {
            "available_disk_bytes": args.available_disk_bytes,
            "disk_budget_bytes": disk_budget,
            "total_memory_bytes": args.total_memory_bytes,
            "memory_budget_bytes": memory_budget,
            "max_runtime_hours": args.max_runtime_hours,
        },
        "promote_next_view": promote,
    }
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if promote else 2


if __name__ == "__main__":
    raise SystemExit(main())
