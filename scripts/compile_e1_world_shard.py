#!/usr/bin/env python3
"""Compile exported E1 Domain Pack records into the common World Index."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import (
    E1_SCHEMA_VERSION,
    PARSER_VERSION,
    RENDERER_VERSION,
    SEARCH_VERSION,
    WorldIndexWriter,
    canonical_json,
    iter_jsonl,
)


REQUIRED_PACK_IDS = {
    "commerce-magento-v0",
    "community-postmill-v0",
    "wikimedia-zim-v0",
}


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resource_checkpoint(
    writer: WorldIndexWriter,
    *,
    records_attempted: int,
    records_compiled: int,
    started: float,
    stage: str,
) -> dict[str, Any]:
    """Capture an in-build point for full-corpus resource extrapolation."""

    writer.conn.commit()
    page_count = writer.conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = writer.conn.execute("PRAGMA page_size").fetchone()[0]
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "stage": stage,
        "records_attempted": records_attempted,
        "records_compiled": records_compiled,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "sqlite_allocated_bytes": int(page_count) * int(page_size),
        "peak_rss_kib": usage.ru_maxrss,
    }


def deterministic_sample(
    conn: sqlite3.Connection, *, per_pack: int
) -> list[str]:
    selected: list[str] = []
    packs = [
        row[0] for row in conn.execute(
            "SELECT DISTINCT pack_id FROM documents ORDER BY pack_id"
        )
    ]
    for pack in packs:
        candidates = [
            row[0] for row in conn.execute(
                "SELECT page_snapshot_id FROM documents "
                "WHERE pack_id=? ORDER BY page_snapshot_id",
                (pack,),
            )
        ]
        candidates.sort(
            key=lambda value: sha256(value.encode("utf-8")).digest()
        )
        selected.extend(candidates[:per_pack])
    return selected


def retrieval_audit(
    writer: WorldIndexWriter, page_ids: list[str]
) -> dict[str, Any]:
    exact_total = writer.conn.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0]
    exact_pass = writer.conn.execute(
        """
        SELECT COUNT(*)
          FROM documents d
         WHERE EXISTS (
           SELECT 1 FROM aliases a
            WHERE a.page_snapshot_id=d.page_snapshot_id
              AND a.alias_type='title'
              AND a.alias=d.title
         )
           AND EXISTS (
           SELECT 1 FROM aliases a
            WHERE a.page_snapshot_id=d.page_snapshot_id
              AND a.alias_type='source_id'
              AND a.alias=d.source_id
         )
        """
    ).fetchone()[0]
    bm25_pass = 0
    bm25_eligible = 0
    failures = []
    for page_id in page_ids:
        row = writer.conn.execute(
            "SELECT title FROM documents WHERE page_snapshot_id=?",
            (page_id,),
        ).fetchone()
        if row is None:
            failures.append({
                "page_snapshot_id": page_id,
                "kind": "missing_document",
            })
            continue
        tokens = [
            token for token in str(row[0] or "").replace('"', " ").split()
            if len(token) >= 3 and token.replace("-", "").isalnum()
        ][:5]
        if not tokens:
            continue
        bm25_eligible += 1
        query = " OR ".join(f'"{token}"' for token in tokens)
        try:
            hits = writer.search(query, limit=20)
        except sqlite3.OperationalError as exc:
            failures.append({
                "page_snapshot_id": page_id,
                "kind": "bm25_query_error",
                "error": str(exc),
            })
            continue
        if any(hit["page_snapshot_id"] == page_id for hit in hits):
            bm25_pass += 1
        else:
            failures.append({
                "page_snapshot_id": page_id,
                "kind": "bm25_top20_miss",
                "query": query,
            })
    return {
        "sampled": len(page_ids),
        "exact_alias_documents": exact_total,
        "exact_alias_pass": exact_pass,
        "exact_alias_rate": exact_pass / exact_total if exact_total else None,
        "bm25_eligible": bm25_eligible,
        "bm25_top20_pass": bm25_pass,
        "bm25_top20_rate": (
            bm25_pass / bm25_eligible if bm25_eligible else None
        ),
        "failures": failures,
    }


def structural_audit(
    conn: sqlite3.Connection, *, expected_documents: int
) -> dict[str, Any]:
    checks = {
        "document_count_mismatch": abs(
            conn.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0] - expected_documents
        ),
        "empty_evidence_documents": conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE page_type IN "
            "('product','forum_thread','wiki_article') "
            "AND trim(body_text)=''"
        ).fetchone()[0],
        "invalid_block_offsets": conn.execute(
            "SELECT COUNT(*) FROM blocks "
            "WHERE char_start < 0 OR char_end < char_start "
            "OR (char_end-char_start) != length(text)"
        ).fetchone()[0],
        "orphan_interaction_parents": conn.execute(
            "SELECT COUNT(*) FROM interactions child "
            "WHERE child.parent_interaction_id IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM interactions parent "
            "  WHERE parent.interaction_id="
            "        child.parent_interaction_id "
            "    AND parent.page_snapshot_id="
            "        child.page_snapshot_id"
            ")"
        ).fetchone()[0],
        "empty_link_targets": conn.execute(
            "SELECT COUNT(*) FROM links "
            "WHERE trim(canonical_target)=''"
        ).fetchone()[0],
        "empty_structured_field_names": conn.execute(
            "SELECT COUNT(*) FROM structured_fields "
            "WHERE trim(name)=''"
        ).fetchone()[0],
        "bad_raw_hashes": conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE length(raw_content_hash) NOT IN (64,71)"
        ).fetchone()[0],
    }
    return {
        "checks": checks,
        "passed": all(value == 0 for value in checks.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--resume-existing", action="store_true",
        help=(
            "Resume an interrupted build from its committed documents. "
            "Existing (pack_id,source_id) records are verified/skipped and "
            "the complete source stream is replayed before finalization."
        ),
    )
    parser.add_argument("--roundtrip-per-pack", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=10_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    out = args.out.resolve()
    if args.resume_existing and args.overwrite:
        raise SystemExit("--resume-existing and --overwrite are mutually exclusive")
    if (
        out.exists() and any(out.iterdir())
        and not args.overwrite and not args.resume_existing
    ):
        raise SystemExit(
            f"refusing non-empty output directory without --overwrite: {out}"
        )
    out.mkdir(parents=True, exist_ok=True)

    source_manifest_path = source_dir / "source-manifest.json"
    source_manifest = json.loads(
        source_manifest_path.read_text(encoding="utf-8")
    )
    if source_manifest.get("task_conditioned") is not False:
        raise SystemExit("source manifest must declare task_conditioned=false")
    if source_manifest.get("task_or_witness_inputs") != []:
        raise SystemExit("source manifest contains task/witness inputs")
    pack_ids = {
        str(pack.get("pack_id")) for pack in source_manifest.get("packs", [])
    }
    formal_source = bool(source_manifest.get("formal_eligible", False))
    if formal_source and pack_ids != REQUIRED_PACK_IDS:
        raise SystemExit(
            "formal source manifest must contain exactly the three E1 packs"
        )
    snapshot_id = str(source_manifest["snapshot_id"])
    record_paths = []
    for pack in source_manifest["packs"]:
        record_path = source_dir / pack["records_path"]
        actual_sha = file_sha256(record_path)
        if actual_sha != pack["records_sha256"]:
            raise SystemExit(
                f"source hash mismatch for {record_path}: "
                f"{actual_sha} != {pack['records_sha256']}"
            )
        record_paths.append(record_path)

    started = time.perf_counter()
    db_path = out / "world-index.sqlite"
    resumed_existing_documents = 0
    existing_keys: set[tuple[str, str]] = set()
    if args.resume_existing:
        if not db_path.exists():
            raise SystemExit(
                f"--resume-existing database not found: {db_path}"
            )
        writer = object.__new__(WorldIndexWriter)
        writer.path = db_path
        writer.snapshot_id = snapshot_id
        writer.conn = sqlite3.connect(db_path)
        writer.conn.row_factory = sqlite3.Row
        stored_snapshot = writer.conn.execute(
            "SELECT value_json FROM metadata WHERE key='snapshot_id'"
        ).fetchone()
        if stored_snapshot is None or json.loads(stored_snapshot[0]) != snapshot_id:
            writer.close()
            raise SystemExit("resume database snapshot_id mismatch")
        stored_source = writer.conn.execute(
            "SELECT value_json FROM metadata WHERE key='source_manifest_id'"
        ).fetchone()
        if (
            stored_source is None
            or json.loads(stored_source[0])
            != source_manifest["source_manifest_id"]
        ):
            writer.close()
            raise SystemExit("resume database source_manifest_id mismatch")
        existing_keys = {
            (str(row[0]), str(row[1]))
            for row in writer.conn.execute(
                "SELECT pack_id,source_id FROM documents"
            )
        }
        resumed_existing_documents = len(existing_keys)
    else:
        writer = WorldIndexWriter(
            db_path, snapshot_id=snapshot_id, overwrite=args.overwrite
        )
    writer.set_metadata(
        "source_manifest_id", source_manifest["source_manifest_id"]
    )
    writer.set_metadata("selection", source_manifest["selection"])
    writer.set_metadata(
        "task_conditioned", source_manifest["task_conditioned"]
    )
    added = 0
    compiled = resumed_existing_documents
    failures = []
    resource_curve = []
    for path in record_paths:
        for record in iter_jsonl(path):
            record_key = (
                str(record.get("pack_id")),
                str(record.get("source_id")),
            )
            if record_key in existing_keys:
                added += 1
                if added % args.progress_every == 0:
                    resource_curve.append(resource_checkpoint(
                        writer,
                        records_attempted=added,
                        records_compiled=compiled,
                        started=started,
                        stage="resume_scan",
                    ))
                    print(
                        f"[compile-resume] records={added} "
                        f"elapsed={time.perf_counter() - started:.1f}s "
                        f"compiled={compiled} failures={len(failures)}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue
            try:
                writer.add_record_atomic(record)
                compiled += 1
                existing_keys.add(record_key)
            except Exception as exc:
                failures.append({
                    "record_path": str(path),
                    "pack_id": record.get("pack_id"),
                    "source_id": record.get("source_id"),
                    "error": repr(exc),
                })
                print(
                    "[compile-error] "
                    f"record={added + 1} "
                    f"pack={record.get('pack_id')} "
                    f"source={record.get('source_id')} "
                    f"error={repr(exc)[:2000]}",
                    file=sys.stderr,
                    flush=True,
                )
                if len(failures) >= 100:
                    writer.close()
                    raise RuntimeError(
                        "aborting after 100 compiler failures"
                    ) from exc
            added += 1
            if added % args.progress_every == 0:
                resource_curve.append(resource_checkpoint(
                    writer,
                    records_attempted=added,
                    records_compiled=compiled,
                    started=started,
                    stage="ingest",
                ))
                elapsed = time.perf_counter() - started
                print(
                    f"[compile] records={added} elapsed={elapsed:.1f}s "
                    f"failures={len(failures)}",
                    file=sys.stderr,
                    flush=True,
                )

    # The FTS population query is correlated by page_snapshot_id.  Older
    # interrupted baselines lack this index and otherwise degrade to an
    # O(N_documents * N_aliases) scan during finalization.
    writer.conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_aliases_page "
        "ON aliases(page_snapshot_id,normalized_alias,alias_type)"
    )
    writer.finalize()
    resource_curve.append(resource_checkpoint(
        writer,
        records_attempted=added,
        records_compiled=compiled,
        started=started,
        stage="post_finalize",
    ))
    logical_digest = writer.logical_digest()
    census = writer.census()
    expected_documents = sum(
        int(pack["selected"]) - int(pack.get("errors") or 0)
        for pack in source_manifest["packs"]
    )
    structural = structural_audit(
        writer.conn, expected_documents=expected_documents
    )
    sample_ids = deterministic_sample(
        writer.conn, per_pack=args.roundtrip_per_pack
    )
    roundtrip = writer.roundtrip_audit(sample_ids)
    retrieval = retrieval_audit(writer, sample_ids)
    writer.close()

    elapsed = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    input_bytes = sum(path.stat().st_size for path in record_paths)
    resource_report = {
        "schema": "dra_e1_resource_report_v1",
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_kib": usage.ru_maxrss,
        "input_compressed_bytes": input_bytes,
        "sqlite_bytes": db_path.stat().st_size,
        "disk_amplification_vs_compressed_input": (
            db_path.stat().st_size / input_bytes if input_bytes else None
        ),
        "records_attempted": added,
        "records_compiled": compiled,
        "records_failed": len(failures),
        "resumed_existing_documents": resumed_existing_documents,
        "complete_build_resource_measurement": (
            resumed_existing_documents == 0
        ),
        "curve": resource_curve,
    }
    source_export_errors = sum(
        int(pack.get("errors") or 0)
        for pack in source_manifest["packs"]
    )
    exact_alias_complete = retrieval["exact_alias_rate"] == 1.0
    bm25_rate = retrieval["bm25_top20_rate"]
    bm25_gate = bm25_rate is not None and bm25_rate >= 0.90
    quality_report = {
        "schema": "dra_e1_quality_report_v1",
        "compiler_failures": failures,
        "structural": structural,
        "roundtrip": roundtrip,
        "retrieval": retrieval,
        "gates": {
            "source_export_errors_zero": source_export_errors == 0,
            "compiler_failures_zero": not failures,
            "structural_checks_pass": structural["passed"],
            "roundtrip_failures_zero": roundtrip["failed"] == 0,
            "exact_alias_complete": exact_alias_complete,
            "bm25_top20_at_least_0_90": bm25_gate,
            "bm25_top20_observed_rate": bm25_rate,
        },
    }
    hard_gates = [
        source_export_errors == 0,
        not failures,
        structural["passed"],
        roundtrip["failed"] == 0,
        exact_alias_complete,
        bm25_gate,
    ]
    build_manifest = {
        "schema": "dra_e1_build_manifest_v1",
        "created_at": utc_now(),
        "world_index_schema": E1_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "source_manifest_id": source_manifest["source_manifest_id"],
        "source_manifest_sha256": file_sha256(source_manifest_path),
        "logical_build_id": logical_digest,
        "sqlite_sha256": file_sha256(db_path),
        "parser_version": PARSER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "search_version": SEARCH_VERSION,
        "compiler_sha256": file_sha256(Path(__file__).resolve()),
        "world_index_module_sha256": file_sha256(
            ROOT / "src/world_index/e1.py"
        ),
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "source_and_build_gates_pass": (
            bool(source_manifest.get("formal_eligible", False))
            and all(hard_gates)
        ),
        "formal_eligible": False,
        "formal_eligibility_note": (
            "E1 formal eligibility requires external reproducibility, HTTP, "
            "manual stratified audit, and resource gates in addition to this "
            "source/build artifact."
        ),
        "engineering_smoke": bool(
            source_manifest.get("engineering_smoke", False)
        ),
        "resumed_existing_documents": resumed_existing_documents,
        "census": census,
        "quality_report": "quality-report.json",
        "resource_report": "resource-report.json",
    }
    (out / "quality-report.json").write_text(
        json.dumps(
            quality_report, ensure_ascii=False,
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    (out / "resource-report.json").write_text(
        json.dumps(
            resource_report, ensure_ascii=False,
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    (out / "build-manifest.json").write_text(
        json.dumps(
            build_manifest, ensure_ascii=False,
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "logical_build_id": logical_digest,
        "census": census,
        "quality_gates": quality_report["gates"],
        "resource_report": resource_report,
    }, ensure_ascii=False, indent=2))
    return 0 if all(hard_gates) else 2


if __name__ == "__main__":
    raise SystemExit(main())
