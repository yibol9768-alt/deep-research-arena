#!/usr/bin/env python3
"""Compile E1 source records into the compact structural World Index."""

from __future__ import annotations

import argparse
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

from scripts.compile_e1_world_shard import (
    REQUIRED_PACK_IDS,
    deterministic_sample,
    file_sha256,
    resource_checkpoint,
    utc_now,
)
from src.world_index.e1 import PARSER_VERSION, RENDERER_VERSION, iter_jsonl
from src.world_index.e1_compact import (
    ARTIFACT_CODEC,
    COMPACT_SCHEMA_VERSION,
    COMPACT_SEARCH_VERSION,
    CompactWorldIndexWriter,
)


def retrieval_audit(
    writer: CompactWorldIndexWriter, page_ids: list[str]
) -> dict[str, Any]:
    exact_total = writer.conn.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0]
    exact_pass = writer.conn.execute(
        """
        SELECT COUNT(*) FROM documents d
         WHERE EXISTS (
           SELECT 1 FROM aliases a
            WHERE a.doc_id=d.doc_id AND a.alias_type='title'
              AND a.alias=d.title
         )
           AND EXISTS (
           SELECT 1 FROM aliases a
            WHERE a.doc_id=d.doc_id AND a.alias_type='source_id'
              AND a.alias=d.source_id
         )
        """
    ).fetchone()[0]
    bm25_pass = 0
    bm25_eligible = 0
    failures: list[dict[str, Any]] = []
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


def linux_process_io() -> dict[str, int] | None:
    path = Path("/proc/self/io")
    if not path.exists():
        return None
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key.strip()] = int(raw.strip())
    except (OSError, ValueError):
        return None
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--roundtrip-per-pack", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=5_000)
    parser.add_argument(
        "--max-per-pack", type=int,
        help="Engineering-only cap; any use makes the build non-formal.",
    )
    args = parser.parse_args()
    if args.max_per_pack is not None and args.max_per_pack <= 0:
        raise SystemExit("--max-per-pack must be positive")

    source_dir = args.source_dir.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()) and not args.overwrite:
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

    pack_inputs: list[tuple[dict[str, Any], Path]] = []
    for pack in source_manifest["packs"]:
        path = source_dir / pack["records_path"]
        actual_sha = file_sha256(path)
        if actual_sha != pack["records_sha256"]:
            raise SystemExit(
                f"source hash mismatch for {path}: "
                f"{actual_sha} != {pack['records_sha256']}"
            )
        pack_inputs.append((pack, path))

    started = time.perf_counter()
    db_path = out / "world-index.sqlite"
    writer = CompactWorldIndexWriter(
        db_path,
        snapshot_id=str(source_manifest["snapshot_id"]),
        overwrite=args.overwrite,
    )
    writer.set_metadata(
        "source_manifest_id", source_manifest["source_manifest_id"]
    )
    writer.set_metadata("selection", source_manifest["selection"])
    writer.set_metadata("task_conditioned", False)
    writer.set_metadata("storage_profile", "compact-document-artifact-v1")

    attempted = 0
    compiled = 0
    failures: list[dict[str, Any]] = []
    resource_curve: list[dict[str, Any]] = []
    compiled_by_pack: dict[str, int] = {}
    for pack, path in pack_inputs:
        pack_id = str(pack["pack_id"])
        pack_count = 0
        for record in iter_jsonl(path):
            if (
                args.max_per_pack is not None
                and pack_count >= args.max_per_pack
            ):
                break
            attempted += 1
            pack_count += 1
            try:
                writer.add_record_atomic(record)
                compiled += 1
                compiled_by_pack[pack_id] = (
                    compiled_by_pack.get(pack_id, 0) + 1
                )
            except Exception as exc:
                failures.append({
                    "record_path": str(path),
                    "pack_id": record.get("pack_id"),
                    "source_id": record.get("source_id"),
                    "error": repr(exc),
                })
                print(
                    "[compact-compile-error] "
                    f"record={attempted} pack={record.get('pack_id')} "
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
            if attempted % args.progress_every == 0:
                point = resource_checkpoint(
                    writer,
                    records_attempted=attempted,
                    records_compiled=compiled,
                    started=started,
                    stage="compact_ingest",
                )
                point["pack_id"] = pack_id
                resource_curve.append(point)
                print(
                    f"[compact-compile] records={attempted} "
                    f"elapsed={point['elapsed_seconds']:.1f}s "
                    f"failures={len(failures)}",
                    file=sys.stderr,
                    flush=True,
                )

    writer.finalize()
    resource_curve.append(resource_checkpoint(
        writer,
        records_attempted=attempted,
        records_compiled=compiled,
        started=started,
        stage="compact_post_finalize",
    ))
    expected_documents = sum(
        min(
            int(pack["selected"]) - int(pack.get("errors") or 0),
            args.max_per_pack
            if args.max_per_pack is not None else int(pack["selected"]),
        )
        for pack in source_manifest["packs"]
    )
    structural = writer.structural_audit(
        expected_documents=expected_documents
    )
    sample_ids = deterministic_sample(
        writer.conn, per_pack=args.roundtrip_per_pack
    )
    roundtrip = writer.roundtrip_audit(sample_ids)
    retrieval = retrieval_audit(writer, sample_ids)
    logical_digest = writer.logical_digest()
    census = writer.census()
    writer.close()

    elapsed = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    input_bytes = sum(path.stat().st_size for _, path in pack_inputs)
    resource_report = {
        "schema": "dra_e1_compact_resource_report_v1",
        "storage_profile": "compact-document-artifact-v1",
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_kib": usage.ru_maxrss,
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "filesystem_input_blocks": usage.ru_inblock,
        "filesystem_output_blocks": usage.ru_oublock,
        "voluntary_context_switches": usage.ru_nvcsw,
        "involuntary_context_switches": usage.ru_nivcsw,
        "linux_process_io": linux_process_io(),
        "input_compressed_bytes": input_bytes,
        "sqlite_bytes": db_path.stat().st_size,
        "disk_amplification_vs_compressed_input": (
            db_path.stat().st_size / input_bytes if input_bytes else None
        ),
        "records_attempted": attempted,
        "records_compiled": compiled,
        "records_failed": len(failures),
        "compiled_by_pack": compiled_by_pack,
        "artifact_raw_bytes": census["artifact_raw_bytes"],
        "artifact_compressed_bytes": census["artifact_compressed_bytes"],
        "artifact_compression_ratio": (
            census["artifact_compressed_bytes"]
            / census["artifact_raw_bytes"]
            if census["artifact_raw_bytes"] else None
        ),
        "curve": resource_curve,
    }
    source_export_errors = sum(
        int(pack.get("errors") or 0) for pack in source_manifest["packs"]
    )
    exact_gate = retrieval["exact_alias_rate"] == 1.0
    bm25_rate = retrieval["bm25_top20_rate"]
    bm25_gate = bm25_rate is not None and bm25_rate >= 0.90
    quality_report = {
        "schema": "dra_e1_compact_quality_report_v1",
        "compiler_failures": failures,
        "structural": structural,
        "roundtrip": roundtrip,
        "retrieval": retrieval,
        "gates": {
            "source_export_errors_zero": source_export_errors == 0,
            "compiler_failures_zero": not failures,
            "structural_checks_pass": structural["passed"],
            "roundtrip_failures_zero": roundtrip["failed"] == 0,
            "exact_alias_complete": exact_gate,
            "bm25_top20_at_least_0_90": bm25_gate,
            "bm25_top20_observed_rate": bm25_rate,
        },
    }
    hard_gates = [
        source_export_errors == 0,
        not failures,
        structural["passed"],
        roundtrip["failed"] == 0,
        exact_gate,
        bm25_gate,
    ]
    formal_candidate = formal_source and args.max_per_pack is None
    build_manifest = {
        "schema": "dra_e1_compact_build_manifest_v1",
        "created_at": utc_now(),
        "world_index_schema": COMPACT_SCHEMA_VERSION,
        "snapshot_id": source_manifest["snapshot_id"],
        "source_manifest_id": source_manifest["source_manifest_id"],
        "source_manifest_sha256": file_sha256(source_manifest_path),
        "logical_build_id": logical_digest,
        "sqlite_sha256": file_sha256(db_path),
        "parser_version": PARSER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "search_version": COMPACT_SEARCH_VERSION,
        "artifact_codec": ARTIFACT_CODEC,
        "storage_profile": "compact-document-artifact-v1",
        "compiler_sha256": file_sha256(Path(__file__).resolve()),
        "world_index_module_sha256": file_sha256(
            ROOT / "src/world_index/e1_compact.py"
        ),
        "structural_parser_module_sha256": file_sha256(
            ROOT / "src/world_index/e1.py"
        ),
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "engineering_cap_per_pack": args.max_per_pack,
        "source_and_build_gates_pass": (
            formal_candidate and all(hard_gates)
        ),
        "formal_eligible": False,
        "formal_eligibility_note": (
            "External reproducibility, HTTP, human stratified audit, resource "
            "projection, and compact-vs-baseline fidelity gates remain required."
        ),
        "engineering_smoke": not formal_candidate,
        "census": census,
        "quality_report": "quality-report.json",
        "resource_report": "resource-report.json",
    }
    for filename, payload in (
        ("quality-report.json", quality_report),
        ("resource-report.json", resource_report),
        ("build-manifest.json", build_manifest),
    ):
        (out / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
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
