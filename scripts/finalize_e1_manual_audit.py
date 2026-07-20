#!/usr/bin/env python3
"""Validate a completed E1 human audit queue and issue its gate report."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.create_e1_manual_audit_queue import (
    COMPACT_STRATA,
    queue_definition_id,
)


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_item(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    item_id = str(item.get("audit_item_id") or "<missing>")
    review = item.get("review") or {}
    if review.get("status") not in {"passed", "failed"}:
        errors.append(f"{item_id}: review.status must be passed or failed")
    if review.get("reviewer_kind") != "human":
        errors.append(f"{item_id}: reviewer_kind must be human")
    if not str(review.get("reviewer_id") or "").strip():
        errors.append(f"{item_id}: reviewer_id is required")
    if not str(review.get("reviewed_at") or "").strip():
        errors.append(f"{item_id}: reviewed_at is required")
    results = review.get("check_results")
    if not isinstance(results, dict):
        errors.append(f"{item_id}: check_results must be an object")
        results = {}
    for check in item.get("required_checks") or []:
        if check not in results:
            errors.append(f"{item_id}: missing check result {check}")
        elif not isinstance(results[check], bool):
            errors.append(f"{item_id}: check result {check} must be boolean")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--machine-preaudit", type=Path, required=True)
    parser.add_argument("--min-per-stratum", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.min_per_stratum <= 0:
        raise SystemExit("--min-per-stratum must be positive")

    queue_path = args.queue.resolve()
    build_dir = args.build_dir.resolve()
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    machine_path = args.machine_preaudit.resolve()
    machine = json.loads(machine_path.read_text(encoding="utf-8"))
    build = json.loads(
        (build_dir / "build-manifest.json").read_text(encoding="utf-8")
    )
    validation_errors: list[str] = []
    if queue.get("schema") != "dra_e1_manual_audit_queue_v1":
        validation_errors.append("unsupported queue schema")
    if len(str(queue.get("generator_sha256") or "")) != 64:
        validation_errors.append("queue generator hash missing")
    actual_definition_id = queue_definition_id(queue)
    if queue.get("queue_definition_id") != actual_definition_id:
        validation_errors.append("queue definition hash mismatch")
    if queue.get("logical_build_id") != build.get("logical_build_id"):
        validation_errors.append("queue/build logical_build_id mismatch")
    if queue.get("source_manifest_id") != build.get("source_manifest_id"):
        validation_errors.append("queue/build source_manifest_id mismatch")
    if machine.get("schema") != "dra_e1_manual_audit_machine_precheck_v1":
        validation_errors.append("unsupported machine preaudit schema")
    if len(str(machine.get("auditor_sha256") or "")) != 64:
        validation_errors.append("machine preaudit auditor hash missing")
    if machine.get("queue_definition_id") != actual_definition_id:
        validation_errors.append("machine preaudit/queue definition mismatch")
    if machine.get("logical_build_id") != build.get("logical_build_id"):
        validation_errors.append("machine preaudit/build logical ID mismatch")
    if machine.get("source_manifest_id") != build.get("source_manifest_id"):
        validation_errors.append("machine preaudit/build source ID mismatch")

    items = queue.get("items")
    if not isinstance(items, list) or not items:
        validation_errors.append("audit queue must contain items")
        items = []
    strata = {
        str(entry.get("stratum")): entry
        for entry in queue.get("sampling", {}).get("strata", [])
    }
    expected_strata = {name for name, _ in COMPACT_STRATA}
    if set(strata) != expected_strata:
        validation_errors.append("audit queue stratum set mismatch")
    for name, entry in strata.items():
        available = int(entry.get("available_after_cross_stratum_dedup") or 0)
        requested = int(entry.get("requested") or 0)
        selected = int(entry.get("selected") or 0)
        if available >= requested and selected != requested:
            validation_errors.append(
                f"stratum {name}: unexplained sampling shortfall"
            )
        minimum_required = min(args.min_per_stratum, available)
        if selected < minimum_required:
            validation_errors.append(
                f"stratum {name}: selected {selected} below required "
                f"{minimum_required}"
            )

    machine_summary = machine.get("summary") or {}
    machine_total = machine_summary.get("total")
    machine_passed = machine_summary.get("passed")
    machine_failed = machine_summary.get("failed")
    if machine_total != len(items):
        validation_errors.append("machine preaudit item count mismatch")
    if machine_passed != len(items):
        validation_errors.append("machine preaudit did not pass every item")
    if machine_failed != 0:
        validation_errors.append("machine preaudit contains failures")
    machine_items = machine.get("items")
    if not isinstance(machine_items, list):
        validation_errors.append("machine preaudit items missing")
        machine_items = []
    machine_by_id = {
        str(item.get("audit_item_id")): item for item in machine_items
    }
    if len(machine_by_id) != len(machine_items):
        validation_errors.append("duplicate machine preaudit item IDs")
    for item in items:
        audit_id = str(item.get("audit_item_id"))
        machine_item = machine_by_id.get(audit_id)
        if machine_item is None:
            validation_errors.append(
                f"{audit_id}: missing machine preaudit item"
            )
            continue
        expected_page_id = str(
            (item.get("document") or {}).get("page_snapshot_id")
        )
        if str(machine_item.get("page_snapshot_id")) != expected_page_id:
            validation_errors.append(
                f"{audit_id}: machine preaudit page mismatch"
            )
        if machine_item.get("machine_precheck_passed") is not True:
            validation_errors.append(
                f"{audit_id}: machine precheck did not pass"
            )
        if machine_item.get("machine_precheck_failures") not in ([], None):
            validation_errors.append(
                f"{audit_id}: machine precheck failures are non-empty"
            )

    passed = 0
    failed = 0
    pending = 0
    systematic_losses: dict[str, int] = {}
    check_failures: dict[str, int] = {}
    for item in items:
        item_errors = validate_item(item)
        validation_errors.extend(item_errors)
        review = item.get("review") or {}
        status = review.get("status")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        else:
            pending += 1
        for check, result in (review.get("check_results") or {}).items():
            if result is False:
                check_failures[str(check)] = (
                    check_failures.get(str(check), 0) + 1
                )
        category = str(
            review.get("systematic_loss_category") or ""
        ).strip()
        if category:
            systematic_losses[category] = systematic_losses.get(category, 0) + 1

    formal_gate_passed = (
        not validation_errors
        and pending == 0
        and failed == 0
        and not check_failures
        and not systematic_losses
    )
    report = {
        "schema": "dra_e1_manual_audit_report_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "queue": str(queue_path),
        "queue_sha256": file_sha256(queue_path),
        "queue_definition_id": actual_definition_id,
        "machine_preaudit": str(machine_path),
        "machine_preaudit_sha256": file_sha256(machine_path),
        "build_dir": str(build_dir),
        "logical_build_id": build["logical_build_id"],
        "source_manifest_id": build["source_manifest_id"],
        "sample_total": len(items),
        "min_per_stratum": args.min_per_stratum,
        "passed_items": passed,
        "failed_items": failed,
        "pending_items": pending,
        "check_failures": check_failures,
        "systematic_losses": systematic_losses,
        "validation_errors": validation_errors,
        "formal_gate_passed": formal_gate_passed,
        "note": (
            "This gate accepts only completed reviews explicitly attributed "
            "to human reviewers; machine pre-audits cannot satisfy it."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if formal_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
