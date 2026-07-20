#!/usr/bin/env python3
"""Create a deterministic, stratified human audit queue for an E1 build."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any


ROW_STRATA = [
    (
        "commerce_product_with_review",
        "d.page_type='product' AND EXISTS ("
        "SELECT 1 FROM interactions i WHERE i.page_snapshot_id="
        "d.page_snapshot_id AND i.kind='review')",
    ),
    ("commerce_product", "d.page_type='product'"),
    (
        "community_thread_with_replies",
        "d.page_type='forum_thread' AND EXISTS ("
        "SELECT 1 FROM interactions i WHERE i.page_snapshot_id="
        "d.page_snapshot_id AND i.kind='reply')",
    ),
    ("community_thread", "d.page_type='forum_thread'"),
    (
        "wiki_article_with_tables",
        "d.page_type='wiki_article' AND EXISTS ("
        "SELECT 1 FROM blocks b WHERE b.page_snapshot_id="
        "d.page_snapshot_id AND b.block_type='table_cell')",
    ),
    (
        "wiki_article_with_links",
        "d.page_type='wiki_article' AND EXISTS ("
        "SELECT 1 FROM links l WHERE l.page_snapshot_id="
        "d.page_snapshot_id)",
    ),
    ("wiki_article", "d.page_type='wiki_article'"),
    ("wiki_redirect", "d.page_type='wiki_redirect'"),
    ("wiki_resource", "d.page_type='wiki_resource'"),
]

COMPACT_STRATA = [
    (
        "commerce_product_with_review",
        "d.page_type='product' AND d.review_count > 0",
    ),
    ("commerce_product", "d.page_type='product'"),
    (
        "community_thread_with_replies",
        "d.page_type='forum_thread' AND d.reply_count > 0",
    ),
    ("community_thread", "d.page_type='forum_thread'"),
    (
        "wiki_article_with_tables",
        "d.page_type='wiki_article' AND d.table_cell_count > 0",
    ),
    (
        "wiki_article_with_links",
        "d.page_type='wiki_article' AND d.link_count > 0",
    ),
    ("wiki_article", "d.page_type='wiki_article'"),
    ("wiki_redirect", "d.page_type='wiki_redirect'"),
    ("wiki_resource", "d.page_type='wiki_resource'"),
]


def sample_key(anchor_id: str, stratum: str, page_id: str) -> bytes:
    return sha256(
        f"{anchor_id}\0{stratum}\0{page_id}".encode("utf-8")
    ).digest()


def queue_definition_id(queue: dict[str, Any]) -> str:
    """Hash immutable sampling/content fields while excluding human reviews."""

    payload = {
        "schema": queue.get("schema"),
        "logical_build_id": queue.get("logical_build_id"),
        "source_manifest_id": queue.get("source_manifest_id"),
        "sampling": queue.get("sampling"),
        "items": [
            {
                "audit_item_id": item.get("audit_item_id"),
                "stratum": item.get("stratum"),
                "document": item.get("document"),
                "required_checks": item.get("required_checks"),
            }
            for item in queue.get("items") or []
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def document_details(
    conn: sqlite3.Connection, page_id: str, *, compact: bool
) -> dict[str, Any]:
    if compact:
        row = conn.execute(
            """
            SELECT d.page_snapshot_id,d.pack_id,d.source_id,d.canonical_url,
                   d.archive_entry_path,d.redirect_target,d.page_type,d.title,
                   d.mime_type,d.raw_content_hash,d.parsed_content_hash,
                   d.rendered_content_hash,d.capture_or_archive_locator,
                   d.block_count AS blocks,
                   d.table_cell_count AS table_cells,
                   d.link_count AS links,
                   d.structured_field_count AS fields,
                   d.interaction_count AS interactions,
                   d.reply_count AS replies
              FROM documents d WHERE d.page_snapshot_id=?
            """,
            (page_id,),
        ).fetchone()
        if row is None:
            raise KeyError(page_id)
        return dict(row)
    row = conn.execute(
        """
        SELECT d.page_snapshot_id,d.pack_id,d.source_id,d.canonical_url,
               d.archive_entry_path,d.redirect_target,d.page_type,d.title,
               d.mime_type,d.raw_content_hash,d.parsed_content_hash,
               d.rendered_content_hash,d.capture_or_archive_locator,
               (SELECT COUNT(*) FROM blocks b
                 WHERE b.page_snapshot_id=d.page_snapshot_id) AS blocks,
               (SELECT COUNT(*) FROM blocks b
                 WHERE b.page_snapshot_id=d.page_snapshot_id
                   AND b.block_type='table_cell') AS table_cells,
               (SELECT COUNT(*) FROM links l
                 WHERE l.page_snapshot_id=d.page_snapshot_id) AS links,
               (SELECT COUNT(*) FROM structured_fields f
                 WHERE f.page_snapshot_id=d.page_snapshot_id) AS fields,
               (SELECT COUNT(*) FROM interactions i
                 WHERE i.page_snapshot_id=d.page_snapshot_id) AS interactions,
               (SELECT COUNT(*) FROM interactions i
                 WHERE i.page_snapshot_id=d.page_snapshot_id
                   AND i.kind='reply') AS replies
          FROM documents d WHERE d.page_snapshot_id=?
        """,
        (page_id,),
    ).fetchone()
    if row is None:
        raise KeyError(page_id)
    return dict(row)


def required_checks(details: dict[str, Any]) -> list[str]:
    checks = [
        "raw_to_parsed_lineage",
        "parsed_to_served_content",
        "title_and_alias_identity",
    ]
    if details["blocks"]:
        checks.append("block_text_and_section_coordinates")
    if details["table_cells"]:
        checks.append("table_row_column_and_span_coordinates")
    if details["links"]:
        checks.append("outgoing_link_target_and_anchor")
    if details["fields"]:
        checks.append("structured_field_value_and_provenance")
    if details["interactions"]:
        checks.extend([
            "interaction_text_author_time_score_attribution",
            "interaction_parent_child_tree",
        ])
    if details["redirect_target"]:
        checks.append("redirect_target_identity")
    if details["page_type"] == "wiki_resource":
        checks.append("resource_mime_size_and_omission_marker")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--per-stratum", type=int, default=20)
    parser.add_argument(
        "--sampling-anchor",
        help=(
            "Optional frozen regression anchor. By default sampling is "
            "anchored to source_manifest_id so compiler changes do not "
            "silently replace the audited documents."
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.per_stratum <= 0:
        raise SystemExit("--per-stratum must be positive")

    build_dir = args.build_dir.resolve()
    build = json.loads(
        (build_dir / "build-manifest.json").read_text(encoding="utf-8")
    )
    build_id = str(build["logical_build_id"])
    source_manifest_id = str(build["source_manifest_id"])
    sampling_anchor = str(
        args.sampling_anchor or source_manifest_id
    )
    sampling_anchor_kind = (
        "explicit_regression_anchor"
        if args.sampling_anchor else "source_manifest_id"
    )
    conn = sqlite3.connect(
        f"file:{(build_dir / 'world-index.sqlite').resolve()}?mode=ro",
        uri=True,
    )
    conn.row_factory = sqlite3.Row
    document_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(documents)")
    }
    compact = "artifact_blob" in document_columns
    strata = COMPACT_STRATA if compact else ROW_STRATA
    used: set[str] = set()
    items = []
    strata_report = []
    for stratum, predicate in strata:
        candidates = [
            row[0] for row in conn.execute(
                f"SELECT d.page_snapshot_id FROM documents d "
                f"WHERE {predicate} ORDER BY d.page_snapshot_id"
            )
            if row[0] not in used
        ]
        candidates.sort(
            key=lambda page_id: sample_key(
                sampling_anchor, stratum, page_id
            )
        )
        selected = candidates[: args.per_stratum]
        used.update(selected)
        strata_report.append({
            "stratum": stratum,
            "available_after_cross_stratum_dedup": len(candidates),
            "requested": args.per_stratum,
            "selected": len(selected),
            "shortfall": max(0, args.per_stratum - len(selected)),
        })
        for page_id in selected:
            details = document_details(conn, page_id, compact=compact)
            items.append({
                "audit_item_id": sha256(
                    f"{sampling_anchor}\0{stratum}\0{page_id}".encode(
                        "utf-8"
                    )
                ).hexdigest()[:24],
                "stratum": stratum,
                "document": details,
                "required_checks": required_checks(details),
                "review": {
                    "status": "pending",
                    "reviewer_id": None,
                    "reviewer_kind": None,
                    "reviewed_at": None,
                    "check_results": {},
                    "systematic_loss_category": None,
                    "notes": None,
                },
            })
    conn.close()

    queue = {
        "schema": "dra_e1_manual_audit_queue_v1",
        "generator_sha256": sha256(
            Path(__file__).resolve().read_bytes()
        ).hexdigest(),
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "build_dir": str(build_dir),
        "logical_build_id": build_id,
        "source_manifest_id": source_manifest_id,
        "sampling": {
            "method": "sha256(anchor_id,NUL,stratum,NUL,page_id)",
            "anchor_kind": sampling_anchor_kind,
            "anchor_id": sampling_anchor,
            "without_replacement_across_strata": True,
            "per_stratum": args.per_stratum,
            "storage_profile": (
                "compact-document-artifact-v1"
                if compact else "row-structural-v1"
            ),
            "strata": strata_report,
        },
        "items": items,
        "summary": {
            "total": len(items),
            "pending": len(items),
            "passed": 0,
            "failed": 0,
            "formal_gate_passed": False,
        },
    }
    queue["queue_definition_id"] = queue_definition_id(queue)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "logical_build_id": build_id,
        "items": len(items),
        "strata": strata_report,
        "out": str(args.out.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
