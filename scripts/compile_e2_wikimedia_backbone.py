#!/usr/bin/env python3
"""Direct-stream a resumable Wikimedia ZIM into the E2 World Index.

The production path never writes a full JSONL staging copy.  Source entries
are converted with the same task-blind record builder validated in E1, added
to the compact structural index, and committed together with their resume
cursor.  W100K and W1M are deterministic nested rank-threshold views of the
same frozen population; Wfull selects every entry.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sqlite3
import sys
import time
from typing import Any, Mapping
import zlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compile_e1_world_shard import (
    deterministic_sample,
    file_sha256,
    utc_now,
)
from scripts.compile_e1_world_shard_compact import retrieval_audit
from scripts.export_e1_shard_sources import (
    DEFAULT_SNAPSHOT,
    DEFAULT_ZIM,
    PACK_WIKIMEDIA,
    WIKI_URL_IDENTITY_VERSION,
    build_wikimedia_record,
)
from src.world_index.e1 import (
    PARSER_VERSION,
    RENDERER_VERSION,
    canonical_json,
    stable_rank64,
)
from src.world_index.e1_compact import (
    ARTIFACT_CODEC,
    COMPACT_SCHEMA_VERSION,
    COMPACT_SEARCH_VERSION,
    CompactWorldIndexWriter,
)


E2_SCHEMA = "dra_e2_wikimedia_direct_stream_v2"
CHECKPOINT_SCHEMA = "dra_e2_wikimedia_checkpoint_v1"
CHECKPOINT_KEY = "e2_wikimedia_checkpoint"
RANK_SPACE = 1 << 64
VIEW_TARGETS: dict[str, int | None] = {
    "w100k": 100_000,
    "w1m": 1_000_000,
    "wfull": None,
}


@dataclass(frozen=True)
class ViewContract:
    view_id: str
    population: int
    target_documents: int
    rank_threshold_exclusive: int

    @property
    def selection_rate(self) -> float:
        return self.rank_threshold_exclusive / RANK_SPACE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "dra_nested_rank_view_v1",
            "view_id": self.view_id,
            "population": self.population,
            "target_documents": self.target_documents,
            "rank_bits": 64,
            "rank_threshold_exclusive": self.rank_threshold_exclusive,
            "selection_rate": self.selection_rate,
            "algorithm": (
                "uint64_be(sha256(snapshot_id,NUL,pack_id,NUL,source_id)"
                "[:8]) < rank_threshold_exclusive"
            ),
        }


def view_contract(view_id: str, population: int) -> ViewContract:
    if view_id not in VIEW_TARGETS:
        raise ValueError(f"unknown view: {view_id}")
    if population <= 0:
        raise ValueError("population must be positive")
    requested = VIEW_TARGETS[view_id]
    if requested is None or requested >= population:
        target = population
        threshold = RANK_SPACE
    else:
        target = requested
        threshold = (RANK_SPACE * target + population - 1) // population
    return ViewContract(view_id, population, target, threshold)


def nested_view_contracts(population: int) -> dict[str, dict[str, Any]]:
    contracts = {
        view_id: view_contract(view_id, population)
        for view_id in VIEW_TARGETS
    }
    thresholds = [
        contracts[name].rank_threshold_exclusive
        for name in ("w100k", "w1m", "wfull")
    ]
    if thresholds != sorted(thresholds):
        raise AssertionError("nested view thresholds are not monotonic")
    return {name: value.as_dict() for name, value in contracts.items()}


def selected_for_view(
    *,
    snapshot_id: str,
    source_id: str,
    contract: ViewContract,
) -> bool:
    if contract.rank_threshold_exclusive == RANK_SPACE:
        return True
    return stable_rank64(
        snapshot_id, PACK_WIKIMEDIA, source_id
    ) < contract.rank_threshold_exclusive


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    except (AttributeError, OSError):
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def source_identity(archive: Any, zim_path: Path) -> dict[str, Any]:
    return {
        "schema": "dra_e2_wikimedia_source_identity_v1",
        "zim_size": int(archive.filesize),
        "zim_uuid": str(archive.uuid),
        "zim_checksum": str(archive.checksum),
        "entry_count": int(archive.entry_count),
        "all_entry_count": int(archive.all_entry_count),
        "article_count": int(archive.article_count),
        "has_fulltext_index": bool(archive.has_fulltext_index),
        "has_title_index": bool(archive.has_title_index),
        "has_new_namespace_scheme": bool(
            archive.has_new_namespace_scheme
        ),
        "url_identity_version": WIKI_URL_IDENTITY_VERSION,
        "diagnostic_path": str(zim_path.resolve()),
    }


def content_identity(value: Mapping[str, Any]) -> str:
    stable = dict(value)
    stable.pop("diagnostic_path", None)
    return sha256(canonical_json(stable).encode("utf-8")).hexdigest()


def pipeline_contract(
    *,
    source: Mapping[str, Any],
    snapshot_id: str,
    view: ViewContract,
    scan_end: int,
    libzim_binary_path: Path,
) -> dict[str, Any]:
    files = {
        "compiler": Path(__file__).resolve(),
        "record_builder": ROOT / "scripts/export_e1_shard_sources.py",
        "e1_row_compiler_helpers": (
            ROOT / "scripts/compile_e1_world_shard.py"
        ),
        "e1_compact_compiler_helpers": (
            ROOT / "scripts/compile_e1_world_shard_compact.py"
        ),
        "compact_store": ROOT / "src/world_index/e1_compact.py",
        "structural_parser": ROOT / "src/world_index/e1.py",
        "libzim_binary": libzim_binary_path,
    }
    contract = {
        "schema": E2_SCHEMA,
        "snapshot_id": snapshot_id,
        "source_identity_id": content_identity(source),
        "view": view.as_dict(),
        "scan_end": scan_end,
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "world_index_schema": COMPACT_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "search_version": COMPACT_SEARCH_VERSION,
        "artifact_codec": ARTIFACT_CODEC,
        "url_identity_version": WIKI_URL_IDENTITY_VERSION,
        "code_sha256": {
            name: file_sha256(path) for name, path in files.items()
        },
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "beautifulsoup4": importlib_metadata.version("beautifulsoup4"),
            "lxml": importlib_metadata.version("lxml"),
            "zlib_compile": zlib.ZLIB_VERSION,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        },
    }
    contract["pipeline_contract_id"] = sha256(
        canonical_json(contract).encode("utf-8")
    ).hexdigest()
    return contract


def initial_checkpoint(
    *,
    contract: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "pipeline_contract_id": contract["pipeline_contract_id"],
        "source_identity_id": contract["source_identity_id"],
        "snapshot_id": contract["snapshot_id"],
        "view_id": contract["view"]["view_id"],
        "scan_end": contract["scan_end"],
        "next_entry_index": 0,
        "scanned": 0,
        "compiled": 0,
        "compiled_by_type": {},
        "content_bytes_read": 0,
        "record_chain_sha256": "0" * 64,
        "checkpoint_sequence": 0,
        "elapsed_seconds": 0.0,
        "peak_rss_kib": 0,
        "resource_curve": [],
        "scan_complete": False,
        "finalized": False,
        "source_entry_count": source["entry_count"],
    }


def advance_record_chain(
    previous: str,
    *,
    entry_index: int,
    record: Mapping[str, Any],
) -> str:
    digest = sha256()
    digest.update(bytes.fromhex(previous))
    digest.update(canonical_json([
        entry_index,
        record.get("source_id"),
        record.get("canonical_url"),
        record.get("page_type"),
        record.get("raw_content_hash"),
    ]).encode("utf-8"))
    return digest.hexdigest()


def checkpoint_database(
    *,
    writer: CompactWorldIndexWriter,
    state: dict[str, Any],
    checkpoint_path: Path,
    elapsed_before_run: float,
    run_started: float,
    curve_every: int,
) -> dict[str, Any]:
    state["checkpoint_sequence"] = int(
        state["checkpoint_sequence"]
    ) + 1
    state["elapsed_seconds"] = round(
        elapsed_before_run + time.perf_counter() - run_started, 3
    )
    state["peak_rss_kib"] = max(
        int(state.get("peak_rss_kib") or 0),
        int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    )
    document_high_watermark = int(writer.conn.execute(
        "SELECT COALESCE(MAX(doc_id),0) FROM documents"
    ).fetchone()[0])
    if document_high_watermark != int(state["compiled"]):
        raise RuntimeError(
            "checkpoint document high-watermark mismatch: "
            f"{document_high_watermark} != "
            f"{state['compiled']}"
        )
    page_count = int(
        writer.conn.execute("PRAGMA page_count").fetchone()[0]
    )
    page_size = int(
        writer.conn.execute("PRAGMA page_size").fetchone()[0]
    )
    if (
        not state["resource_curve"]
        or state["checkpoint_sequence"] % max(curve_every, 1) == 0
        or state["scan_complete"]
    ):
        state["resource_curve"].append({
            "checkpoint_sequence": state["checkpoint_sequence"],
            "next_entry_index": state["next_entry_index"],
            "scanned": state["scanned"],
            "compiled": state["compiled"],
            "elapsed_seconds": state["elapsed_seconds"],
            "sqlite_allocated_bytes": page_count * page_size,
            "peak_rss_kib": state["peak_rss_kib"],
        })
    writer.commit_checkpoint(CHECKPOINT_KEY, state)
    external = {
        **state,
        "database": str(writer.path.resolve()),
        "sqlite_allocated_bytes": page_count * page_size,
        "updated_at": utc_now(),
    }
    atomic_write_json(checkpoint_path, external)
    return deepcopy(state)


def validate_resume(
    *,
    writer: CompactWorldIndexWriter,
    state: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    expected = {
        "schema": CHECKPOINT_SCHEMA,
        "pipeline_contract_id": contract["pipeline_contract_id"],
        "source_identity_id": contract["source_identity_id"],
        "snapshot_id": contract["snapshot_id"],
        "view_id": contract["view"]["view_id"],
        "scan_end": contract["scan_end"],
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise ValueError(
                f"resume checkpoint mismatch for {key}: "
                f"{state.get(key)!r} != {value!r}"
            )
    documents = int(writer.conn.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0])
    fts_rows = int(writer.conn.execute(
        "SELECT COUNT(*) FROM search_fts"
    ).fetchone()[0])
    if documents != int(state["compiled"]) or fts_rows != documents:
        raise ValueError(
            "resume database/checkpoint census mismatch: "
            f"documents={documents}, fts={fts_rows}, "
            f"checkpoint={state['compiled']}"
        )
    next_index = int(state["next_entry_index"])
    if not 0 <= next_index <= int(state["scan_end"]):
        raise ValueError(f"invalid resume cursor: {next_index}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zim", type=Path, default=DEFAULT_ZIM)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--view", choices=tuple(VIEW_TARGETS), required=True
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--overwrite", action="store_true")
    parser.add_argument("--checkpoint-every-scanned", type=int, default=250_000)
    parser.add_argument("--checkpoint-every-compiled", type=int, default=10_000)
    parser.add_argument("--progress-every", type=int, default=100_000)
    parser.add_argument("--curve-every-checkpoints", type=int, default=10)
    parser.add_argument("--roundtrip-sample", type=int, default=100)
    parser.add_argument(
        "--engineering-scan-limit",
        type=int,
        help="Engineering only: scan a source prefix and mark it ineligible.",
    )
    parser.add_argument(
        "--engineering-stop-after-scanned",
        type=int,
        help=(
            "Checkpoint and exit 75 after this cumulative scanned count; "
            "used to test resume behavior."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for name in (
        "checkpoint_every_scanned",
        "checkpoint_every_compiled",
        "progress_every",
        "curve_every_checkpoints",
        "roundtrip_sample",
    ):
        if int(getattr(args, name)) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    if (
        args.engineering_scan_limit is not None
        and args.engineering_scan_limit <= 0
    ):
        raise SystemExit("--engineering-scan-limit must be positive")
    if (
        args.engineering_stop_after_scanned is not None
        and args.engineering_stop_after_scanned <= 0
    ):
        raise SystemExit(
            "--engineering-stop-after-scanned must be positive"
        )

    try:
        import libzim
        from libzim.reader import Archive
    except ImportError as exc:
        raise SystemExit(
            "python3-libzim is required on the frozen source host"
        ) from exc

    zim_path = args.zim.resolve()
    if not zim_path.is_file():
        raise SystemExit(f"missing ZIM: {zim_path}")
    archive = Archive(zim_path)
    libzim_binary_path = Path(libzim.__file__).resolve()
    source = source_identity(archive, zim_path)
    view = view_contract(args.view, int(source["entry_count"]))
    scan_end = int(source["entry_count"])
    if args.engineering_scan_limit is not None:
        scan_end = min(scan_end, args.engineering_scan_limit)
    contract = pipeline_contract(
        source=source,
        snapshot_id=args.snapshot_id,
        view=view,
        scan_end=scan_end,
        libzim_binary_path=libzim_binary_path,
    )

    out = args.out.resolve()
    db_path = out / "world-index.sqlite"
    checkpoint_path = out / "checkpoint.json"
    manifest_path = out / "build-manifest.json"
    if args.overwrite and out.exists():
        shutil.rmtree(out)
    if args.resume:
        if manifest_path.is_file():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("pipeline_contract_id") != contract[
                "pipeline_contract_id"
            ]:
                raise SystemExit(
                    "completed build belongs to a different pipeline contract"
                )
            if not db_path.is_file():
                raise SystemExit("completed manifest is missing its database")
            if db_path.stat().st_size != int(existing.get("sqlite_bytes") or 0):
                raise SystemExit(
                    "completed database size does not match its manifest"
                )
            completed_writer = CompactWorldIndexWriter.open_existing(
                db_path, snapshot_id=args.snapshot_id
            )
            completed_state = completed_writer.metadata_value(CHECKPOINT_KEY)
            validate_resume(
                writer=completed_writer,
                state=completed_state,
                contract=contract,
            )
            completed_writer.close()
            print(canonical_json({
                "status": "already_complete",
                "build_manifest": str(manifest_path),
                "logical_build_id": existing.get("logical_build_id"),
            }))
            return 0
        writer = CompactWorldIndexWriter.open_existing(
            db_path, snapshot_id=args.snapshot_id
        )
        state = writer.metadata_value(CHECKPOINT_KEY)
        validate_resume(writer=writer, state=state, contract=contract)
    else:
        if out.exists() and any(out.iterdir()):
            raise SystemExit(
                f"refusing non-empty output without --resume/--overwrite: {out}"
            )
        out.mkdir(parents=True, exist_ok=True)
        writer = CompactWorldIndexWriter(
            db_path, snapshot_id=args.snapshot_id, overwrite=False
        )
        writer.set_metadata("phase", "E2")
        writer.set_metadata("source_identity", source)
        writer.set_metadata("source_identity_id", content_identity(source))
        writer.set_metadata("view", view.as_dict())
        writer.set_metadata(
            "nested_view_contracts",
            nested_view_contracts(int(source["entry_count"])),
        )
        writer.set_metadata(
            "pipeline_contract_id", contract["pipeline_contract_id"]
        )
        writer.set_metadata("task_conditioned", False)
        writer.set_metadata("task_or_witness_inputs", [])
        writer.set_metadata(
            "storage_profile", "compact-document-artifact-v1"
        )
        state = initial_checkpoint(contract=contract, source=source)
        writer.commit_checkpoint(CHECKPOINT_KEY, state)
        atomic_write_json(checkpoint_path, {
            **state,
            "database": str(db_path),
            "updated_at": utc_now(),
        })

    committed_state = deepcopy(state)
    elapsed_before_run = float(state.get("elapsed_seconds") or 0.0)
    run_started = time.perf_counter()
    checkpoint_scanned = int(state["scanned"])
    checkpoint_compiled = int(state["compiled"])
    next_progress = (
        (int(state["scanned"]) // args.progress_every) + 1
    ) * args.progress_every
    failed_index: int | None = None
    failed_identity: dict[str, Any] | None = None
    try:
        if not state.get("scan_complete"):
            for index in range(int(state["next_entry_index"]), scan_end):
                failed_index = index
                entry = archive._get_entry_by_id(index)
                path = str(entry.path)
                failed_identity = {
                    "source_id": path,
                    "title": str(entry.title),
                    "selected": False,
                }
                state["next_entry_index"] = index + 1
                state["scanned"] = int(state["scanned"]) + 1
                if selected_for_view(
                    snapshot_id=args.snapshot_id,
                    source_id=path,
                    contract=view,
                ):
                    failed_identity["selected"] = True
                    built = build_wikimedia_record(
                        archive, index=index, entry=entry
                    )
                    failed_identity.update({
                        "canonical_url": built.record["canonical_url"],
                        "page_type": built.page_type,
                    })
                    writer.add_record_atomic(built.record)
                    state["compiled"] = int(state["compiled"]) + 1
                    by_type = dict(state.get("compiled_by_type") or {})
                    by_type[built.page_type] = int(
                        by_type.get(built.page_type) or 0
                    ) + 1
                    state["compiled_by_type"] = by_type
                    state["content_bytes_read"] = int(
                        state["content_bytes_read"]
                    ) + built.content_bytes_read
                    state["record_chain_sha256"] = advance_record_chain(
                        str(state["record_chain_sha256"]),
                        entry_index=index,
                        record=built.record,
                    )

                due = (
                    int(state["scanned"]) - checkpoint_scanned
                    >= args.checkpoint_every_scanned
                    or int(state["compiled"]) - checkpoint_compiled
                    >= args.checkpoint_every_compiled
                )
                stopping = (
                    args.engineering_stop_after_scanned is not None
                    and int(state["scanned"])
                    >= args.engineering_stop_after_scanned
                )
                if due or stopping:
                    committed_state = checkpoint_database(
                        writer=writer,
                        state=state,
                        checkpoint_path=checkpoint_path,
                        elapsed_before_run=elapsed_before_run,
                        run_started=run_started,
                        curve_every=args.curve_every_checkpoints,
                    )
                    checkpoint_scanned = int(state["scanned"])
                    checkpoint_compiled = int(state["compiled"])
                if int(state["scanned"]) >= next_progress:
                    print(
                        "[e2-wikimedia] "
                        f"view={args.view} scanned={state['scanned']}/"
                        f"{scan_end} compiled={state['compiled']} "
                        f"checkpoints={state['checkpoint_sequence']}",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress += args.progress_every
                if stopping:
                    writer.close()
                    print(canonical_json({
                        "status": "engineering_stop",
                        "checkpoint": str(checkpoint_path),
                        "next_entry_index": state["next_entry_index"],
                        "compiled": state["compiled"],
                    }))
                    return 75

            state["scan_complete"] = True
            committed_state = checkpoint_database(
                writer=writer,
                state=state,
                checkpoint_path=checkpoint_path,
                elapsed_before_run=elapsed_before_run,
                run_started=run_started,
                curve_every=args.curve_every_checkpoints,
            )

        if not state.get("finalized"):
            writer.finalize()
            state["finalized"] = True
            committed_state = checkpoint_database(
                writer=writer,
                state=state,
                checkpoint_path=checkpoint_path,
                elapsed_before_run=elapsed_before_run,
                run_started=run_started,
                curve_every=args.curve_every_checkpoints,
            )

        structural = writer.structural_audit(
            expected_documents=int(state["compiled"])
        )
        sample_ids = deterministic_sample(
            writer.conn, per_pack=args.roundtrip_sample
        )
        roundtrip = writer.roundtrip_audit(sample_ids)
        retrieval = retrieval_audit(writer, sample_ids)
        logical_build_id = writer.logical_digest(
            exclude_metadata_keys=(CHECKPOINT_KEY, "source_identity")
        )
        census = writer.census()
        writer.close()
    except BaseException as exc:
        writer.abort()
        failure = {
            "schema": "dra_e2_wikimedia_failure_v1",
            "failed_at": utc_now(),
            "failed_entry_index": failed_index,
            "failed_entry_identity": failed_identity,
            "error": repr(exc),
            "last_committed_checkpoint": committed_state,
            "resume_command_required": True,
        }
        atomic_write_json(out / "failure.json", failure)
        raise

    sqlite_sha256 = file_sha256(db_path)
    elapsed_seconds = round(
        elapsed_before_run + time.perf_counter() - run_started, 3
    )
    exact_rate = retrieval.get("exact_alias_rate")
    bm25_rate = retrieval.get("bm25_top20_rate")
    hard_gates = {
        "scan_complete": (
            bool(state["scan_complete"])
            and int(state["next_entry_index"]) == scan_end
        ),
        "compiler_errors_zero": True,
        "document_count_matches_checkpoint": (
            int(census["documents"]) == int(state["compiled"])
        ),
        "structural_checks_pass": structural["passed"],
        "roundtrip_failures_zero": roundtrip["failed"] == 0,
        "exact_alias_complete": exact_rate == 1.0,
        "bm25_top20_at_least_0_90": (
            bm25_rate is not None and bm25_rate >= 0.90
        ),
        "task_blind": (
            contract["task_conditioned"] is False
            and contract["task_or_witness_inputs"] == []
        ),
    }
    quality_report = {
        "schema": "dra_e2_wikimedia_quality_report_v1",
        "logical_build_id": logical_build_id,
        "pipeline_contract_id": contract["pipeline_contract_id"],
        "hard_gates": hard_gates,
        "structural": structural,
        "roundtrip": roundtrip,
        "retrieval": retrieval,
        "passed": all(hard_gates.values()),
    }
    resource_report = {
        "schema": "dra_e2_wikimedia_resource_report_v1",
        "view": view.as_dict(),
        "scan_end": scan_end,
        "elapsed_seconds": elapsed_seconds,
        "peak_rss_kib": state["peak_rss_kib"],
        "sqlite_bytes": db_path.stat().st_size,
        "content_bytes_read": state["content_bytes_read"],
        "checkpoint_sequence": state["checkpoint_sequence"],
        "resource_curve": state["resource_curve"],
    }
    full_backbone_candidate = (
        args.view == "wfull"
        and args.engineering_scan_limit is None
        and scan_end == int(source["entry_count"])
        and all(hard_gates.values())
    )
    manifest = {
        "schema": "dra_e2_wikimedia_build_manifest_v1",
        "created_at": utc_now(),
        "phase": "E2",
        "world_index_schema": COMPACT_SCHEMA_VERSION,
        "storage_profile": "compact-document-artifact-v1",
        "snapshot_id": args.snapshot_id,
        "source_identity": source,
        "source_identity_id": content_identity(source),
        "view": view.as_dict(),
        "nested_view_contracts": nested_view_contracts(
            int(source["entry_count"])
        ),
        "pipeline_contract_id": contract["pipeline_contract_id"],
        "pipeline_contract": contract,
        "logical_build_id": logical_build_id,
        "sqlite_sha256": sqlite_sha256,
        "sqlite_bytes": db_path.stat().st_size,
        "parser_version": PARSER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "search_version": COMPACT_SEARCH_VERSION,
        "artifact_codec": ARTIFACT_CODEC,
        "task_conditioned": False,
        "task_or_witness_inputs": [],
        "scan_end": scan_end,
        "full_source_scan": scan_end == int(source["entry_count"]),
        "full_backbone_candidate": full_backbone_candidate,
        "source_and_build_gates_pass": all(hard_gates.values()),
        "formal_eligible": False,
        "formal_eligibility_note": (
            "This compiler certifies the structural Wikimedia backbone only. "
            "The E2 stage still requires served-artifact enumeration/HTTP "
            "round-trip, exact versus uncertain Wikidata alignment, global "
            "statistics, and an external E2 stage certificate."
        ),
        "census": census,
        "checkpoint_summary": {
            key: state[key]
            for key in (
                "next_entry_index",
                "scanned",
                "compiled",
                "compiled_by_type",
                "content_bytes_read",
                "record_chain_sha256",
                "checkpoint_sequence",
                "scan_complete",
                "finalized",
            )
        },
        "quality_report": "quality-report.json",
        "resource_report": "resource-report.json",
    }
    atomic_write_json(out / "quality-report.json", quality_report)
    atomic_write_json(out / "resource-report.json", resource_report)
    atomic_write_json(manifest_path, manifest)
    failure_path = out / "failure.json"
    if failure_path.exists():
        failure_path.unlink()
    print(canonical_json({
        "status": "complete",
        "view": args.view,
        "scanned": state["scanned"],
        "compiled": state["compiled"],
        "logical_build_id": logical_build_id,
        "sqlite_sha256": sqlite_sha256,
        "quality_passed": quality_report["passed"],
        "full_backbone_candidate": manifest[
            "full_backbone_candidate"
        ],
        "formal_eligible": False,
        "out": str(out),
    }))
    return 0 if quality_report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
