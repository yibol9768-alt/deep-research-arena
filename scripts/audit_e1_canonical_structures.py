#!/usr/bin/env python3
"""Exhaustively audit canonical E1 table, interaction, and resource structure."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping
import zlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import canonical_json, normalize_text


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def audit_artifact(
    document: Mapping[str, Any], artifact: Mapping[str, Any]
) -> tuple[Counter[str], list[dict[str, Any]]]:
    metrics: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    page_id = str(document.get("page_snapshot_id") or "")

    cells_by_table_row: dict[tuple[int, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    occupancy: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for block in artifact.get("blocks") or []:
        if block.get("block_type") != "table_cell":
            continue
        metrics["table_cells"] += 1
        if not normalize_text(block.get("text")):
            metrics["empty_table_cells"] += 1
        structural = dict(block.get("structural") or {})
        required = (
            "table_index", "row_index", "cell_index", "column_index",
            "grid_column_index", "rowspan", "colspan",
        )
        if any(not isinstance(structural.get(key), int) for key in required):
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "table_cell_coordinate_missing_or_non_integer",
                "dom_path": block.get("dom_path"),
            })
            continue
        table = int(structural["table_index"])
        row = int(structural["row_index"])
        cell_index = int(structural["cell_index"])
        column = int(structural["column_index"])
        grid_column = int(structural["grid_column_index"])
        if min(table, row, cell_index, column, grid_column) < 0:
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "negative_table_coordinate",
                "dom_path": block.get("dom_path"),
            })
            continue
        if grid_column != column:
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "logical_column_alias_mismatch",
                "dom_path": block.get("dom_path"),
            })
        cells_by_table_row[(table, row)].append({
            "cell_index": cell_index,
            "column": column,
            "structural": structural,
            "dom_path": block.get("dom_path"),
        })
        rowspan = int(
            structural.get("effective_rowspan")
            or structural.get("rowspan")
            or 1
        )
        colspan = int(
            structural.get("effective_colspan")
            or structural.get("colspan")
            or 1
        )
        if (
            rowspan <= 0 or colspan <= 0
            or rowspan > 100_000 or colspan > 100_000
            or rowspan * colspan > 1_000_000
        ):
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "invalid_effective_table_span",
                "dom_path": block.get("dom_path"),
                "rowspan": rowspan,
                "colspan": colspan,
            })
            continue
        # Typical tables are small; bounding above prevents hostile expansion.
        occupied_coordinates = {
            (occupied_row, occupied_column)
            for occupied_row in range(row, row + rowspan)
            for occupied_column in range(column, column + colspan)
        }
        overlap = occupied_coordinates & occupancy[table]
        if overlap:
            occupied_row, occupied_column = min(overlap)
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "overlapping_table_cells",
                "table_index": table,
                "row_index": occupied_row,
                "column_index": occupied_column,
            })
        occupancy[table].update(occupied_coordinates)

    metrics["tables"] += len(occupancy)
    for (table, row), cells in cells_by_table_row.items():
        observed = sorted(cell["cell_index"] for cell in cells)
        if observed != list(range(len(cells))):
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "noncontiguous_physical_cell_index",
                "table_index": table,
                "row_index": row,
                "observed": observed[:20],
            })

    interactions = list(artifact.get("interactions") or [])
    metrics["interactions"] += len(interactions)
    by_id = {
        str(item.get("interaction_id") or ""): item
        for item in interactions
    }
    if len(by_id) != len(interactions) or "" in by_id:
        failures.append({
            "page_snapshot_id": page_id,
            "reason": "duplicate_or_empty_interaction_id",
        })
    parent_by_id = {
        interaction_id: str(item.get("parent_interaction_id") or "")
        for interaction_id, item in by_id.items()
    }
    for interaction_id, parent_id in parent_by_id.items():
        if parent_id and parent_id not in by_id:
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "orphan_interaction_parent",
                "interaction_id": interaction_id,
                "parent_interaction_id": parent_id,
            })
    depth_cache: dict[str, int] = {}

    def interaction_depth(interaction_id: str, trail: set[str]) -> int:
        if interaction_id in depth_cache:
            return depth_cache[interaction_id]
        if interaction_id in trail:
            return 0
        parent_id = parent_by_id.get(interaction_id, "")
        value = (
            0 if not parent_id or parent_id not in by_id
            else 1 + interaction_depth(
                parent_id, trail | {interaction_id}
            )
        )
        depth_cache[interaction_id] = value
        return value

    for interaction_id in by_id:
        trail: set[str] = set()
        current = interaction_id
        while current and current in by_id:
            if current in trail:
                failures.append({
                    "page_snapshot_id": page_id,
                    "reason": "interaction_parent_cycle",
                    "interaction_id": current,
                })
                break
            trail.add(current)
            current = parent_by_id.get(current, "")
        metrics["max_interaction_depth"] = max(
            metrics["max_interaction_depth"],
            interaction_depth(interaction_id, set()),
        )

    if str(document.get("page_type") or "") == "wiki_resource":
        metrics["wiki_resources"] += 1
        title = normalize_text(document.get("title"))
        if not title or title.casefold() in {"null", "none", "undefined"}:
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "unusable_resource_title",
            })
        for key in (
            "source_id", "archive_entry_path", "mime_type",
            "raw_content_hash", "capture_or_archive_locator",
        ):
            if not normalize_text(document.get(key)):
                failures.append({
                    "page_snapshot_id": page_id,
                    "reason": f"resource_{key}_missing",
                })
        metadata = document.get("metadata") or {}
        if metadata.get("resource_content_omitted") is not True:
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "resource_omission_marker_missing",
            })
        item_size = [
            field for field in artifact.get("structured_fields") or []
            if normalize_text(field.get("name")) == "item_size"
        ]
        if len(item_size) != 1 or not normalize_text(item_size[0].get("value")):
            failures.append({
                "page_snapshot_id": page_id,
                "reason": "resource_item_size_missing_or_duplicated",
            })
    return metrics, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--progress-every", type=int, default=10_000)
    parser.add_argument("--max-failure-examples", type=int, default=100)
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    db_path = build_dir / "world-index.sqlite"
    build_manifest_path = build_dir / "build-manifest.json"
    build_manifest = json.loads(
        build_manifest_path.read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    totals: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    rows = conn.execute("""
        SELECT page_snapshot_id,page_type,title,source_id,archive_entry_path,
               mime_type,raw_content_hash,capture_or_archive_locator,
               metadata_json,artifact_blob,artifact_raw_bytes,artifact_hash
          FROM documents ORDER BY page_snapshot_id
    """)
    for index, row in enumerate(rows, start=1):
        raw = zlib.decompress(row["artifact_blob"])
        if (
            len(raw) != int(row["artifact_raw_bytes"])
            or sha256(raw).hexdigest() != row["artifact_hash"]
        ):
            item_failures = [{
                "page_snapshot_id": row["page_snapshot_id"],
                "reason": "artifact_length_or_hash_mismatch",
            }]
            metrics = Counter()
        else:
            document = dict(row)
            document["metadata"] = json.loads(
                document.pop("metadata_json")
            )
            artifact = json.loads(raw.decode("utf-8"))
            metrics, item_failures = audit_artifact(document, artifact)
        document_max_depth = metrics.pop("max_interaction_depth", 0)
        totals.update(metrics)
        totals["max_interaction_depth"] = max(
            totals["max_interaction_depth"], document_max_depth
        )
        totals["documents"] += 1
        for failure in item_failures:
            failure_counts[str(failure["reason"])] += 1
            if len(examples) < args.max_failure_examples:
                examples.append(failure)
        if args.progress_every and index % args.progress_every == 0:
            print(
                f"[canonical-structure-audit] documents={index} "
                f"failures={sum(failure_counts.values())}",
                file=sys.stderr,
                flush=True,
            )
    conn.close()
    report = {
        "schema": "dra_e1_canonical_structure_audit_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "created_at": utc_now(),
        "build_dir": str(build_dir),
        "database": str(db_path.resolve()),
        "logical_build_id": build_manifest.get("logical_build_id"),
        "source_manifest_id": build_manifest.get("source_manifest_id"),
        "sqlite_sha256": file_sha256(db_path),
        "passed": not failure_counts,
        "totals": dict(sorted(totals.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "failure_examples": examples,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(canonical_json({
        "passed": report["passed"],
        "totals": report["totals"],
        "failure_counts": report["failure_counts"],
        "out": str(args.out.resolve()),
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
