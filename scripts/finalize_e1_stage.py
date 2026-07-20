#!/usr/bin/env python3
"""Aggregate every external E1 gate into one formal stage certificate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def manifest_document_count(manifest: dict[str, Any]) -> int:
    """Read the document census from current or legacy build manifests."""

    return int(
        (manifest.get("census") or {}).get("documents")
        or manifest.get("document_count")
        or 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--reproducibility", type=Path, required=True)
    parser.add_argument("--http-audit", type=Path, required=True)
    parser.add_argument(
        "--canonical-structure-audit", type=Path, required=True
    )
    parser.add_argument("--manual-audit", type=Path, required=True)
    parser.add_argument("--resource-projection", type=Path, required=True)
    parser.add_argument("--storage-fidelity", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source_path = args.source_dir.resolve() / "source-manifest.json"
    build_a_path = args.build_a.resolve() / "build-manifest.json"
    build_b_path = args.build_b.resolve() / "build-manifest.json"
    paths = {
        "source_manifest": source_path,
        "build_a_manifest": build_a_path,
        "build_b_manifest": build_b_path,
        "reproducibility": args.reproducibility.resolve(),
        "http_audit": args.http_audit.resolve(),
        "canonical_structure_audit": (
            args.canonical_structure_audit.resolve()
        ),
        "manual_audit": args.manual_audit.resolve(),
        "resource_projection": args.resource_projection.resolve(),
        "storage_fidelity": args.storage_fidelity.resolve(),
    }
    values = {name: load(path) for name, path in paths.items()}
    source = values["source_manifest"]
    build_a = values["build_a_manifest"]
    build_b = values["build_b_manifest"]
    logical_id = build_a["logical_build_id"]
    source_id = source["source_manifest_id"]
    expected_build_paths = {
        str(args.build_a.resolve()),
        str(args.build_b.resolve()),
    }
    reproducibility_build_paths = {
        str(Path(values["reproducibility"].get("first", "")).resolve()),
        str(Path(values["reproducibility"].get("second", "")).resolve()),
    }
    checks = {
        "source_manifest_formal_task_blind": (
            source.get("formal_eligible") is True
            and source.get("task_conditioned") is False
            and source.get("task_or_witness_inputs") == []
        ),
        "build_a_internal_gates_pass": (
            build_a.get("source_and_build_gates_pass") is True
        ),
        "build_b_internal_gates_pass": (
            build_b.get("source_and_build_gates_pass") is True
        ),
        "builds_bind_same_source": (
            build_a.get("source_manifest_id") == source_id
            and build_b.get("source_manifest_id") == source_id
        ),
        "builds_task_blind": (
            build_a.get("task_conditioned") is False
            and build_b.get("task_conditioned") is False
            and build_a.get("task_or_witness_inputs") == []
            and build_b.get("task_or_witness_inputs") == []
        ),
        "reproducibility_pass": (
            values["reproducibility"].get("passed") is True
            and all(values["reproducibility"].get("checks", {}).values())
            and reproducibility_build_paths == expected_build_paths
            and values["reproducibility"].get("first_logical_build_id")
            == logical_id
            and values["reproducibility"].get("second_logical_build_id")
            == logical_id
            and values["reproducibility"].get("source_manifest_id")
            == source_id
        ),
        "http_audit_pass_and_bound": (
            values["http_audit"].get("passed") is True
            and values["http_audit"].get("logical_build_id") == logical_id
            and values["http_audit"].get("sqlite_sha256")
            == build_a.get("sqlite_sha256")
            and str(Path(values["http_audit"].get("db", "")).resolve())
            == str((args.build_a.resolve() / "world-index.sqlite").resolve())
            and int(values["http_audit"].get("sampled") or 0) >= 300
            and float(values["http_audit"].get(
                "document_hash_rate"
            ) or 0.0) == 1.0
            and float(values["http_audit"].get(
                "min_search_top20_rate"
            ) or 0.0) >= 0.90
            and float(values["http_audit"].get(
                "search_top20_rate"
            ) or 0.0) >= 0.90
        ),
        "canonical_structure_audit_pass_and_bound": (
            values["canonical_structure_audit"].get("passed") is True
            and values["canonical_structure_audit"].get(
                "logical_build_id"
            ) == logical_id
            and values["canonical_structure_audit"].get(
                "source_manifest_id"
            ) == source_id
            and values["canonical_structure_audit"].get("sqlite_sha256")
            == build_a.get("sqlite_sha256")
            and str(Path(values["canonical_structure_audit"].get(
                "build_dir", ""
            )).resolve()) == str(args.build_a.resolve())
            and str(Path(values["canonical_structure_audit"].get(
                "database", ""
            )).resolve()) == str(
                (args.build_a.resolve() / "world-index.sqlite").resolve()
            )
            and int(values["canonical_structure_audit"].get(
                "totals", {}
            ).get("documents") or 0) == int(
                manifest_document_count(build_a)
            )
            and not values["canonical_structure_audit"].get(
                "failure_counts"
            )
        ),
        "manual_audit_pass_and_bound": (
            values["manual_audit"].get("formal_gate_passed") is True
            and values["manual_audit"].get("logical_build_id") == logical_id
            and values["manual_audit"].get("source_manifest_id") == source_id
            and str(Path(
                values["manual_audit"].get("build_dir", "")
            ).resolve()) == str(args.build_a.resolve())
            and int(values["manual_audit"].get("min_per_stratum") or 0)
            >= 20
            and len(str(values["manual_audit"].get(
                "queue_definition_id", ""
            ))) == 64
            and len(str(values["manual_audit"].get(
                "machine_preaudit_sha256", ""
            ))) == 64
        ),
        "resource_projection_pass_and_bound": (
            values["resource_projection"].get("formal_gate_passed") is True
            and values["resource_projection"].get("logical_build_id")
            == logical_id
            and values["resource_projection"].get("source_manifest_id")
            == source_id
            and str(Path(values["resource_projection"].get(
                "candidate_build", ""
            )).resolve()) == str(args.build_a.resolve())
        ),
        "resource_policy_not_weakened": (
            values["resource_projection"].get("selection", {}).get(
                "selection_rate"
            ) == 0.01
            and int(values["resource_projection"].get("observed", {}).get(
                "ingest_checkpoints"
            ) or 0) >= 20
            and float(values["resource_projection"].get(
                "host_budget", {}
            ).get("disk_usable_fraction") or 1.0) <= 0.80
            and float(values["resource_projection"].get(
                "host_budget", {}
            ).get("memory_usable_fraction") or 1.0) <= 0.80
            and float(values["resource_projection"].get(
                "host_budget", {}
            ).get("max_runtime_hours") or float("inf")) <= 168.0
            and float(values["resource_projection"].get(
                "projection", {}
            ).get("disk_uncertainty_factor") or 0.0) >= 1.25
            and float(values["resource_projection"].get(
                "projection", {}
            ).get("runtime_uncertainty_factor") or 0.0) >= 1.50
            and float(values["resource_projection"].get(
                "projection", {}
            ).get("memory_uncertainty_factor") or 0.0) >= 2.0
        ),
        "storage_fidelity_pass_and_bound": (
            values["storage_fidelity"].get("passed") is True
            and str(Path(
                values["storage_fidelity"].get("compact_build", "")
            ).resolve()) == str(args.build_a.resolve())
            and values["storage_fidelity"].get(
                "compact_logical_build_id"
            ) == logical_id
            and values["storage_fidelity"].get("source_manifest_id")
            == source_id
        ),
        "compact_production_profile": (
            build_a.get("storage_profile")
            == "compact-document-artifact-v1"
            and build_b.get("storage_profile")
            == "compact-document-artifact-v1"
        ),
        "production_code_hashes_present": all(
            isinstance(build.get(key), str)
            and len(build[key]) == 64
            for build in (build_a, build_b)
            for key in (
                "compiler_sha256",
                "world_index_module_sha256",
                "structural_parser_module_sha256",
            )
        ),
        "gate_auditor_hashes_present": all(
            isinstance(values[name].get("auditor_sha256"), str)
            and len(values[name]["auditor_sha256"]) == 64
            for name in (
                "reproducibility",
                "http_audit",
                "canonical_structure_audit",
                "manual_audit",
                "resource_projection",
                "storage_fidelity",
            )
        ),
    }
    passed = all(checks.values())
    certificate = {
        "schema": "dra_phase_e1_stage_certificate_v1",
        "issuer_sha256": file_sha256(Path(__file__).resolve()),
        "issued_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "phase": "E1",
        "status": "PASS" if passed else "FAIL",
        "logical_build_id": logical_id,
        "source_manifest_id": source_id,
        "world_index_schema": build_a.get("world_index_schema"),
        "storage_profile": build_a.get("storage_profile"),
        "checks": checks,
        "artifacts": {
            name: {
                "path": str(path),
                "sha256": file_sha256(path),
            }
            for name, path in paths.items()
        },
        "notes": [
            "The certificate is external to immutable build manifests; a "
            "single build cannot self-certify reproducibility, HTTP, human, "
            "resource, or cross-layout fidelity gates.",
            "A FAIL certificate is retained as evidence and must not be "
            "rewritten to PASS without supplying new versioned gate artifacts.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        certificate, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
