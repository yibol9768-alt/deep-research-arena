#!/usr/bin/env python3
"""Compare row and compact E1 builds for semantic and retrieval fidelity."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import WorldIndexWriter
from src.world_index.e1_compact import CompactWorldIndexWriter


IDENTITY_COLUMNS = [
    "page_snapshot_id",
    "pack_id",
    "source_id",
    "canonical_url",
    "archive_entry_path",
    "redirect_target",
    "http_status",
    "source_family",
    "page_type",
    "snapshot_id",
    "mime_type",
    "language",
    "title",
    "raw_content_hash",
    "parsed_content_hash",
    "rendered_content_hash",
    "capture_or_archive_locator",
    "rights_class",
    "parser_version",
    "renderer_version",
    "metadata_json",
]


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(
        (path / "build-manifest.json").read_text(encoding="utf-8")
    )


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def open_row(path: Path) -> WorldIndexWriter:
    writer = object.__new__(WorldIndexWriter)
    writer.path = path
    writer.snapshot_id = ""
    writer.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    writer.conn.row_factory = sqlite3.Row
    return writer


def open_compact(path: Path) -> CompactWorldIndexWriter:
    writer = object.__new__(CompactWorldIndexWriter)
    writer.path = path
    writer.snapshot_id = ""
    writer.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    writer.conn.row_factory = sqlite3.Row
    return writer


def sample_ids(
    conn: sqlite3.Connection, *, per_pack: int, seed: str
) -> list[str]:
    selected: list[str] = []
    for pack_id, in conn.execute(
        "SELECT DISTINCT pack_id FROM documents ORDER BY pack_id"
    ):
        values = [row[0] for row in conn.execute(
            "SELECT page_snapshot_id FROM documents "
            "WHERE pack_id=? ORDER BY page_snapshot_id",
            (pack_id,),
        )]
        values.sort(key=lambda page_id: sha256(
            f"{seed}\0{pack_id}\0{page_id}".encode("utf-8")
        ).digest())
        selected.extend(values[:per_pack])
    return selected


def title_query(title: str) -> str | None:
    tokens = [
        token for token in str(title or "").replace('"', " ").split()
        if len(token) >= 3 and token.replace("-", "").isalnum()
    ][:5]
    return " OR ".join(f'"{token}"' for token in tokens) if tokens else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row-build", type=Path, required=True)
    parser.add_argument("--compact-build", type=Path, required=True)
    parser.add_argument("--per-pack", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    row_build = args.row_build.resolve()
    compact_build = args.compact_build.resolve()
    row_manifest = load_manifest(row_build)
    compact_manifest = load_manifest(compact_build)
    row_db = row_build / "world-index.sqlite"
    compact_db = compact_build / "world-index.sqlite"

    conn = sqlite3.connect(row_db)
    conn.execute("ATTACH DATABASE ? AS compact", (str(compact_db),))
    identity_predicate = " OR ".join(
        f"r.{name} IS NOT c.{name}" for name in IDENTITY_COLUMNS
    )
    full_checks = {
        "source_manifest_id_equal": (
            row_manifest["source_manifest_id"]
            == compact_manifest["source_manifest_id"]
        ),
        "snapshot_id_equal": (
            row_manifest["snapshot_id"] == compact_manifest["snapshot_id"]
        ),
        "parser_version_equal": (
            row_manifest["parser_version"]
            == compact_manifest["parser_version"]
        ),
        "renderer_version_equal": (
            row_manifest["renderer_version"]
            == compact_manifest["renderer_version"]
        ),
        "row_documents": conn.execute(
            "SELECT COUNT(*) FROM main.documents"
        ).fetchone()[0],
        "compact_documents": conn.execute(
            "SELECT COUNT(*) FROM compact.documents"
        ).fetchone()[0],
        "missing_in_compact": conn.execute(
            "SELECT COUNT(*) FROM main.documents r "
            "LEFT JOIN compact.documents c USING(page_snapshot_id) "
            "WHERE c.page_snapshot_id IS NULL"
        ).fetchone()[0],
        "missing_in_row": conn.execute(
            "SELECT COUNT(*) FROM compact.documents c "
            "LEFT JOIN main.documents r USING(page_snapshot_id) "
            "WHERE r.page_snapshot_id IS NULL"
        ).fetchone()[0],
        "identity_or_hash_mismatches": conn.execute(
            "SELECT COUNT(*) FROM main.documents r "
            "JOIN compact.documents c USING(page_snapshot_id) WHERE "
            + identity_predicate
        ).fetchone()[0],
    }
    conn.close()

    row_writer = open_row(row_db)
    compact_writer = open_compact(compact_db)
    core_census_keys = [
        "documents",
        "blocks",
        "links",
        "structured_fields",
        "interactions",
        "aliases",
        "duplicate_clusters",
        "documents_by_pack",
        "documents_by_pack_and_type",
    ]
    row_census = row_writer.census()
    compact_census = compact_writer.census()
    census_checks = {
        key: row_census.get(key) == compact_census.get(key)
        for key in core_census_keys
    }
    sampled = sample_ids(
        row_writer.conn,
        per_pack=args.per_pack,
        seed=str(row_manifest["source_manifest_id"]),
    )
    render_failures: list[dict[str, Any]] = []
    search_failures: list[dict[str, Any]] = []
    for page_id in sampled:
        try:
            row_render = row_writer.render_by_id(page_id)
            compact_render = compact_writer.render_by_id(page_id)
        except Exception as exc:
            render_failures.append({
                "page_snapshot_id": page_id,
                "kind": "render_exception",
                "error": repr(exc),
            })
            continue
        if row_render != compact_render:
            render_failures.append({
                "page_snapshot_id": page_id,
                "kind": "rendered_bytes_differ",
                "row_sha256": sha256(row_render.encode("utf-8")).hexdigest(),
                "compact_sha256": sha256(
                    compact_render.encode("utf-8")
                ).hexdigest(),
            })
        title_row = row_writer.conn.execute(
            "SELECT title FROM documents WHERE page_snapshot_id=?",
            (page_id,),
        ).fetchone()
        query = title_query(title_row[0] if title_row else "")
        if not query:
            continue
        try:
            row_hits = [
                hit["page_snapshot_id"]
                for hit in row_writer.search(query, limit=20)
            ]
            compact_hits = [
                hit["page_snapshot_id"]
                for hit in compact_writer.search(query, limit=20)
            ]
        except sqlite3.OperationalError as exc:
            search_failures.append({
                "page_snapshot_id": page_id,
                "kind": "query_error",
                "query": query,
                "error": str(exc),
            })
            continue
        if row_hits != compact_hits:
            search_failures.append({
                "page_snapshot_id": page_id,
                "kind": "top20_ranking_differs",
                "query": query,
                "row_hits": row_hits,
                "compact_hits": compact_hits,
            })
    row_writer.close()
    compact_writer.close()

    boolean_full_checks = [
        full_checks["source_manifest_id_equal"],
        full_checks["snapshot_id_equal"],
        full_checks["parser_version_equal"],
        full_checks["renderer_version_equal"],
        full_checks["row_documents"] == full_checks["compact_documents"],
        full_checks["missing_in_compact"] == 0,
        full_checks["missing_in_row"] == 0,
        full_checks["identity_or_hash_mismatches"] == 0,
    ]
    passed = (
        all(boolean_full_checks)
        and all(census_checks.values())
        and not render_failures
        and not search_failures
    )
    report = {
        "schema": "dra_e1_storage_profile_fidelity_report_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "row_build": str(row_build),
        "compact_build": str(compact_build),
        "row_logical_build_id": row_manifest["logical_build_id"],
        "compact_logical_build_id": compact_manifest["logical_build_id"],
        "source_manifest_id": compact_manifest["source_manifest_id"],
        "full_corpus_checks": full_checks,
        "census_checks": census_checks,
        "sample": {
            "method": "sha256(source_manifest_id,NUL,pack_id,NUL,page_id)",
            "per_pack": args.per_pack,
            "sampled": len(sampled),
            "render_failures": render_failures,
            "search_failures": search_failures,
        },
        "row_sqlite_bytes": row_db.stat().st_size,
        "compact_sqlite_bytes": compact_db.stat().st_size,
        "compact_to_row_size_ratio": (
            compact_db.stat().st_size / row_db.stat().st_size
            if row_db.stat().st_size else None
        ),
        "passed": passed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
