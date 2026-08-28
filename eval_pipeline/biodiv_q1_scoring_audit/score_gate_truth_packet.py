#!/usr/bin/env python3
"""Fail-closed, no-model aggregation for one biodiversity shadow-score cell.

This script deliberately does not extract claims, judge factuality, decide
citation support, or match report text to required units.  It consumes those
already-adjudicated rows and invokes the SHA-bound GATE-TRUTH implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


REQUIRED_PACKET_FIELDS = (
    "material_claims",
    "citation_bindings",
    "citation_required_units",
    "completeness_units",
    "rubric_items",
    "failure_status",
)
WITHHELD_CATEGORIES = {
    "harness",
    "environment",
    "adapter",
    "scorer",
    "judge_transport",
    "task_asset",
}


class AuditError(ValueError):
    """Input cannot be scored without changing the frozen denominator."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"expected JSON object: {path}")
    return value


def resolve_reference(package_dir: Path, reference: dict[str, Any]) -> Path:
    recorded = Path(str(reference.get("path") or ""))
    candidates = [recorded]
    if recorded.name:
        candidates.append(package_dir / recorded.name)
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise AuditError(f"missing referenced artifact: {recorded}")
    if sha256(path) != reference.get("sha256"):
        raise AuditError(f"artifact SHA mismatch: {path}")
    if path.stat().st_size != reference.get("bytes"):
        raise AuditError(f"artifact byte count mismatch: {path}")
    return path


def verify_package(package_dir: Path, scorer_root: Path) -> dict[str, Any]:
    package_dir = package_dir.resolve()
    manifest_path = package_dir / "evaluation_package_manifest.json"
    package = read_json(manifest_path)
    if package.get("decision") != "STRUCTURAL_READY_UNCALIBRATED":
        raise AuditError("unexpected evaluation-package decision")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, dict):
        raise AuditError("evaluation package has no artifact table")
    required_roles = {
        "eco_scoring_manifest",
        "gate_truth_input_contract",
        "required_units",
        "task_evidence_contract",
        "task_source_census",
    }
    if not required_roles.issubset(artifacts):
        raise AuditError("evaluation package lacks required scorer artifacts")
    resolved = {
        role: resolve_reference(package_dir, reference)
        for role, reference in artifacts.items()
        if isinstance(reference, dict)
    }

    contract = read_json(resolved["gate_truth_input_contract"])
    if contract.get("required_packet_fields") != list(REQUIRED_PACKET_FIELDS):
        raise AuditError("GATE-TRUTH packet contract differs")

    scoring = read_json(resolved["eco_scoring_manifest"])
    runtime = scoring.get("scorer_runtime") or {}
    if runtime.get("authorization") != "SHADOW_EXPERIMENTAL_SCORING":
        raise AuditError("package does not authorize shadow aggregation")
    components = runtime.get("components") or {}
    implementation = scorer_root.resolve() / "src/scoring/gate_truth_score.py"
    implementation_ref = components.get("implementation")
    if not isinstance(implementation_ref, dict):
        raise AuditError("package has no bound GATE-TRUTH implementation")
    if not implementation.is_file():
        raise AuditError(f"missing scorer implementation: {implementation}")
    if (
        sha256(implementation) != implementation_ref.get("sha256")
        or implementation.stat().st_size != implementation_ref.get("bytes")
    ):
        raise AuditError("active GATE-TRUTH implementation is not the bound bytes")

    required_units = read_json(resolved["required_units"])
    rows = required_units.get("required_units")
    if not isinstance(rows, list) or required_units.get("unit_count") != len(rows):
        raise AuditError("task required-unit count differs")
    unit_ids = [str(row.get("information_unit_id") or "") for row in rows]
    if not unit_ids or "" in unit_ids or len(unit_ids) != len(set(unit_ids)):
        raise AuditError("task required-unit identities are empty or duplicated")
    if not all(
        row.get("necessary") is True and row.get("applicable") is True
        for row in rows
    ):
        raise AuditError("task package contains a non-required unit")

    return {
        "package": package,
        "manifest_path": manifest_path,
        "scoring": scoring,
        "implementation": implementation,
        "required_unit_ids": unit_ids,
    }


def load_scorer(path: Path):
    name = f"biodiv_gate_truth_{sha256(path)[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AuditError("cannot load bound GATE-TRUTH implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for symbol in ("score_gate_truth", "binding_gate"):
        if not callable(getattr(module, symbol, None)):
            raise AuditError(f"bound scorer lacks {symbol}")
    return module


def failure_mode(packet: dict[str, Any]) -> str:
    failure = packet.get("failure_status") or {}
    category = str(failure.get("category") or "none")
    status = str(failure.get("status_code") or "scored")
    if (
        category in WITHHELD_CATEGORIES
        or status.startswith("withheld")
        or status == "task_asset_excluded"
    ):
        return "withheld"
    if category == "report" and status.startswith("scored_zero"):
        return "scored_zero"
    return "scored"


def unique_ids(rows: list[dict[str, Any]], field: str, label: str) -> list[str]:
    values = [str(row.get(field) or "") for row in rows]
    if "" in values or len(values) != len(set(values)):
        raise AuditError(f"{label} {field} values are empty or duplicated")
    return values


def validate_scored_packet(packet: dict[str, Any], required_unit_ids: list[str]) -> None:
    missing = [field for field in REQUIRED_PACKET_FIELDS if field not in packet]
    if missing:
        raise AuditError(f"judgment packet missing fields: {missing}")
    for field in REQUIRED_PACKET_FIELDS[:-1]:
        if not isinstance(packet[field], list):
            raise AuditError(f"judgment packet field must be an array: {field}")
    if not isinstance(packet["failure_status"], dict):
        raise AuditError("failure_status must be an object")
    if failure_mode(packet) != "scored":
        return

    claims = packet["material_claims"]
    claim_ids = set(unique_ids(claims, "claim_id", "material_claims"))
    completeness = packet["completeness_units"]
    observed_unit_ids = unique_ids(completeness, "unit_id", "completeness_units")
    if set(observed_unit_ids) != set(required_unit_ids):
        missing_units = sorted(set(required_unit_ids) - set(observed_unit_ids))
        extra_units = sorted(set(observed_unit_ids) - set(required_unit_ids))
        raise AuditError(
            f"frozen GRR denominator drift; missing={missing_units}, extra={extra_units}"
        )
    if not all(
        row.get("necessary") is True and row.get("applicable") is True
        for row in completeness
    ):
        raise AuditError("all G completeness rows must stay necessary and applicable")

    required_rows = packet["citation_required_units"]
    required_claim_ids = set(
        unique_ids(required_rows, "claim_id", "citation_required_units")
    )
    citation_policy_claims = {
        str(row["claim_id"])
        for row in claims
        if row.get("evidence_policy") == "citation_required"
    }
    if required_claim_ids != citation_policy_claims:
        raise AuditError("citation-required claim denominator differs from claims")
    if not required_claim_ids.issubset(claim_ids):
        raise AuditError("citation-required unit references an unknown claim")
    for row in packet["citation_bindings"]:
        if str(row.get("claim_id") or "") not in claim_ids:
            raise AuditError("citation binding references an unknown claim")


def citation_binding_metric(packet: dict[str, Any], scorer: Any) -> dict[str, Any]:
    mode = failure_mode(packet)
    if mode == "withheld":
        return {
            "score": None,
            "status": str(packet["failure_status"].get("status_code") or "withheld"),
            "passed_required_claim_count": 0,
            "required_claim_count": 0,
        }
    if mode == "scored_zero":
        return {
            "score": 0.0,
            "status": str(packet["failure_status"].get("status_code")),
            "passed_required_claim_count": 0,
            "required_claim_count": 0,
        }

    required = {
        str(row["claim_id"]) for row in packet["citation_required_units"]
    }
    passed = {
        str(row.get("claim_id") or "")
        for row in packet["citation_bindings"]
        if str(row.get("claim_id") or "") in required
        and scorer.binding_gate(row)["passed"]
    }
    return {
        # The package joins required citation units by claim_id.  One required
        # claim receives binding credit when at least one attached occurrence
        # passes the frozen binding gate.  Fact truth is intentionally separate.
        # A normally completed report with no citation-required material claim
        # is a valid capability result.  It receives numeric zero; only an
        # infrastructure-withheld packet is allowed to carry ``None``.
        "score": len(passed) / len(required) if required else 0.0,
        "status": "scored" if required else "scored_no_required_claim",
        "passed_required_claim_count": len(passed),
        "required_claim_count": len(required),
        "passed_required_claim_ids": sorted(passed),
    }


def aggregate(
    package_dir: Path, scorer_root: Path, packet_path: Path
) -> dict[str, Any]:
    verified = verify_package(package_dir, scorer_root)
    packet = read_json(packet_path)
    validate_scored_packet(packet, verified["required_unit_ids"])
    scorer = load_scorer(verified["implementation"])
    gate_truth = scorer.score_gate_truth(packet)
    binding = citation_binding_metric(packet, scorer)
    mode = failure_mode(packet)
    if mode != "withheld":
        # The frozen GATE-TRUTH runtime predates the Q1-v2 capability-result
        # convention and may return None for an empty claim denominator.  The
        # matrix contract requires real numeric values for every normal model
        # outcome, while preserving None for infrastructure failures.
        for metric_id in ("gcp", "grr"):
            metric = gate_truth.get(metric_id)
            if not isinstance(metric, dict):
                raise AuditError(f"bound scorer omitted metric: {metric_id}")
            if metric.get("score") is None:
                metric["score"] = 0.0
                metric["status"] = (
                    "scored_zero_normal_capability_result"
                    if mode == "scored_zero"
                    else "scored_zero_no_eligible_numerator"
                )
        if not packet["material_claims"]:
            gate_truth["gcp"]["score"] = 0.0
            gate_truth["gcp"]["status"] = "scored_zero_no_material_claim"
        if not any(
            bool(row.get("gate_truth_grounded_covered"))
            for row in packet["completeness_units"]
        ):
            gate_truth["grr"]["score"] = 0.0
            gate_truth["grr"]["status"] = "scored_zero_no_grounded_required_unit"
    if mode == "scored_zero":
        gate_truth.setdefault("grr", {})["frozen_required_unit_count"] = len(
            verified["required_unit_ids"]
        )
    return {
        "schema": "truth1000_biodiv_shadow_cell_score_v1",
        "release_mode": "shadow",
        "formal_eligible": False,
        "formal_score": None,
        "composite_score": None,
        "package": {
            "batch_id": verified["package"]["identity"]["batch_id"],
            "task_id": verified["package"]["identity"]["query_job_id"],
            "manifest_sha256": sha256(verified["manifest_path"]),
        },
        "inputs": {
            "judgment_packet_sha256": sha256(packet_path),
            "gate_truth_implementation_sha256": sha256(
                verified["implementation"]
            ),
            "frozen_required_unit_count": len(verified["required_unit_ids"]),
        },
        "metrics": {
            "citation_binding": binding,
            "gcp": gate_truth["gcp"],
            "grr": gate_truth["grr"],
        },
        "gate_truth": gate_truth,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--scorer-root", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = aggregate(args.package_dir, args.scorer_root, args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
