#!/usr/bin/env python3
"""Fail-closed citation-space closure gate for a frozen evaluation package.

This gate answers one question before any Harness×LLM cell is allowed: does the
public query's source scope match the world the solver can see and the citations
the scorer can legally count?  It never calls a model.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)


def infer_public_scope(question: str) -> str:
    text = question.lower()
    if "snapshot" in text or "wikipedia" in text or "kiwix" in text:
        return "whole_snapshot"
    return "explicit_subset"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--public-scope", choices=["whole_snapshot", "closed_registry", "explicit_subset"])
    parser.add_argument("--solver-world-scope", default="whole_snapshot", choices=["whole_snapshot", "closed_registry", "explicit_subset"])
    parser.add_argument("--scorer-registry-scope", default="closed_registry", choices=["whole_snapshot", "closed_registry", "explicit_subset"])
    parser.add_argument("--citation-legality-scope", default="registry_only", choices=["whole_snapshot", "registry_only"])
    parser.add_argument("--max-urls", type=int, default=0)
    parser.add_argument("--verifier-max-urls", type=int, default=0)
    parser.add_argument("--allow-context-claims", action="store_true")
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    manifest = read_json(package_dir / "evaluation_package_manifest.json")
    task = read_json(package_dir / "task_json.json")
    registry = read_json(package_dir / "url_registry.json")
    evidence = read_json(package_dir / "evidence_mapping.json")
    required = read_json(package_dir / "required_units.json")

    question = str(task.get("question") or "")
    public_scope = args.public_scope or infer_public_scope(question)
    registry_urls = registry.get("urls") or []
    evidence_rows = evidence.get("evidence_rows") or []
    required_units = required.get("required_units") or []

    violations: list[dict[str, Any]] = []
    if manifest.get("decision") != "STRUCTURAL_READY_UNCALIBRATED":
        violations.append({"code": "package_not_structural_ready", "decision": manifest.get("decision")})
    if manifest.get("formal_eligible") is not False:
        violations.append({"code": "formal_eligible_not_false"})
    if not registry_urls:
        violations.append({"code": "empty_url_registry"})
    if not evidence_rows:
        violations.append({"code": "empty_evidence_mapping"})
    if not required_units:
        violations.append({"code": "empty_required_units"})
    if args.verifier_max_urls and args.max_urls and args.verifier_max_urls < args.max_urls:
        violations.append(
            {
                "code": "verifier_capacity_below_report_budget",
                "max_urls": args.max_urls,
                "verifier_max_urls": args.verifier_max_urls,
            }
        )

    scope_tuple = (public_scope, args.solver_world_scope, args.scorer_registry_scope)
    if (
        args.citation_legality_scope == "registry_only"
        and not args.allow_context_claims
        and len(set(scope_tuple)) != 1
    ):
        violations.append(
            {
                "code": "scope_mismatch",
                "public_scope": public_scope,
                "solver_world_scope": args.solver_world_scope,
                "scorer_registry_scope": args.scorer_registry_scope,
            }
        )
    if public_scope == "whole_snapshot" and args.citation_legality_scope == "registry_only" and not args.allow_context_claims:
        violations.append(
            {
                "code": "whole_snapshot_query_with_registry_only_citations",
                "detail": "A whole-snapshot query cannot be scored by a registry-only legality gate unless context claims are explicitly separated from core claims.",
                "registry_url_count": len(registry_urls),
            }
        )

    status = "PASS" if not violations else "FAIL"
    receipt = {
        "schema_version": "citation_space_closure.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "package_dir": str(package_dir),
        "package_manifest_sha256": manifest.get("package_payload_sha256"),
        "task_id": task.get("task_id"),
        "question_sha256": task.get("question_sha256") or sha256_text(question),
        "source_scope_contract": {
            "public_scope": public_scope,
            "solver_world_scope": args.solver_world_scope,
            "scorer_registry_scope": args.scorer_registry_scope,
            "citation_legality_scope": args.citation_legality_scope,
            "allow_context_claims": bool(args.allow_context_claims),
            "max_urls": args.max_urls,
            "verifier_max_urls": args.verifier_max_urls,
        },
        "registry_coverage": {
            "url_count": len(registry_urls),
            "evidence_row_count": len(evidence_rows),
            "required_unit_count": len(required_units),
        },
        "violations": violations,
        "formal_eligible": False,
        "release_mode": "SHADOW_EXPERIMENTAL_ONLY",
    }
    write_exclusive(args.output, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
