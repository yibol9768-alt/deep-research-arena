#!/usr/bin/env python3
"""Carry prior E1 review notes into a new build without granting it a pass."""

from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.create_e1_manual_audit_queue import queue_definition_id


def load_queue(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value.get("queue"), dict):
        return value["queue"], {
            "saved_at": value.get("saved_at"),
            "wrapper_reviewer_id": value.get("reviewer_id"),
        }
    return value, {}


def identity(item: dict[str, Any]) -> tuple[str, ...]:
    document = item.get("document") or {}
    return (
        str(item.get("audit_item_id") or ""),
        str(item.get("stratum") or ""),
        str(document.get("page_snapshot_id") or ""),
        str(document.get("pack_id") or ""),
        str(document.get("source_id") or ""),
        str(document.get("raw_content_hash") or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-queue", type=Path, required=True)
    parser.add_argument("--to-queue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    previous, wrapper = load_queue(args.from_queue.resolve())
    target, _ = load_queue(args.to_queue.resolve())
    if previous.get("source_manifest_id") != target.get(
        "source_manifest_id"
    ):
        raise SystemExit("source_manifest_id mismatch")
    expected_definition = queue_definition_id(target)
    if target.get("queue_definition_id") != expected_definition:
        raise SystemExit("target queue definition hash mismatch")

    target_by_identity = {
        identity(item): item for item in target.get("items") or []
    }
    carried = 0
    skipped_pending = 0
    missing = []
    for source_item in previous.get("items") or []:
        review = dict(source_item.get("review") or {})
        meaningful = (
            review.get("status") in {"passed", "failed"}
            or bool(review.get("notes"))
            or bool(review.get("systematic_loss_category"))
            or any((review.get("check_results") or {}).values())
        )
        if not meaningful:
            skipped_pending += 1
            continue
        target_item = target_by_identity.get(identity(source_item))
        if target_item is None:
            missing.append(identity(source_item))
            continue
        history = list(target_item.get("review_history") or [])
        history.append({
            "logical_build_id": previous.get("logical_build_id"),
            "queue_definition_id": previous.get("queue_definition_id"),
            "saved_at": wrapper.get("saved_at"),
            "review": deepcopy(review),
            "formal_status": "history_only_not_counted_for_target_build",
        })
        target_item["review_history"] = history
        carried += 1

    if missing:
        raise SystemExit(
            f"{len(missing)} reviewed source items do not match target identity"
        )
    if queue_definition_id(target) != expected_definition:
        raise SystemExit("review history unexpectedly changed queue definition")
    target["review_history_summary"] = {
        "source_logical_build_id": previous.get("logical_build_id"),
        "target_logical_build_id": target.get("logical_build_id"),
        "carried_items": carried,
        "skipped_unreviewed_items": skipped_pending,
        "formal_credit_granted": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(target, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        target["review_history_summary"], ensure_ascii=False, indent=2
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
