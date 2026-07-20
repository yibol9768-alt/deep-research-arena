#!/usr/bin/env python3
"""Compare two independently compiled E1 shard artifacts."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


SQLITE_MAGIC = b"SQLite format 3\x00"
# These two SQLite header fields record write-transaction state, not database
# content.  See https://www.sqlite.org/fileformat.html#the_database_header.
SQLITE_NONCONTENT_HEADER_RANGES = ((24, 28), (92, 96))


def load(path: Path) -> dict:
    return json.loads(
        (path / "build-manifest.json").read_text(encoding="utf-8")
    )


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sqlite_sha256(path: Path) -> str:
    """Hash SQLite content while neutralizing non-content header counters."""

    digest = sha256()
    with path.open("rb") as handle:
        header = bytearray(handle.read(100))
        if len(header) != 100 or not header.startswith(SQLITE_MAGIC):
            raise ValueError(f"not a complete SQLite database: {path}")
        for start, end in SQLITE_NONCONTENT_HEADER_RANGES:
            header[start:end] = b"\x00" * (end - start)
        digest.update(header)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_header_differences(first: Path, second: Path) -> list[int]:
    with first.open("rb") as first_handle, second.open("rb") as second_handle:
        first_header = first_handle.read(100)
        second_header = second_handle.read(100)
    return [
        offset
        for offset, (left, right) in enumerate(
            zip(first_header, second_header, strict=True)
        )
        if left != right
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    first = load(args.first)
    second = load(args.second)
    first_sqlite = args.first / "world-index.sqlite"
    second_sqlite = args.second / "world-index.sqlite"
    first_raw_sqlite_sha256 = file_sha256(first_sqlite)
    second_raw_sqlite_sha256 = file_sha256(second_sqlite)
    first_canonical_sqlite_sha256 = canonical_sqlite_sha256(first_sqlite)
    second_canonical_sqlite_sha256 = canonical_sqlite_sha256(second_sqlite)
    header_differences = sqlite_header_differences(
        first_sqlite, second_sqlite
    )
    allowed_header_offsets = {
        offset
        for start, end in SQLITE_NONCONTENT_HEADER_RANGES
        for offset in range(start, end)
    }
    checks = {
        "snapshot_id_equal": (
            first["snapshot_id"] == second["snapshot_id"]
        ),
        "source_manifest_id_equal": (
            first["source_manifest_id"]
            == second["source_manifest_id"]
        ),
        "logical_build_id_equal": (
            first["logical_build_id"]
            == second["logical_build_id"]
        ),
        "sqlite_manifest_hashes_valid": (
            first["sqlite_sha256"] == first_raw_sqlite_sha256
            and second["sqlite_sha256"] == second_raw_sqlite_sha256
        ),
        "sqlite_canonical_sha256_equal": (
            first_canonical_sqlite_sha256
            == second_canonical_sqlite_sha256
        ),
        "sqlite_header_differences_noncontent_only": (
            set(header_differences) <= allowed_header_offsets
        ),
        "census_equal": first["census"] == second["census"],
        "world_index_schema_equal": (
            first["world_index_schema"] == second["world_index_schema"]
        ),
        "parser_version_equal": (
            first["parser_version"] == second["parser_version"]
        ),
        "renderer_version_equal": (
            first["renderer_version"] == second["renderer_version"]
        ),
        "search_version_equal": (
            first["search_version"] == second["search_version"]
        ),
        "storage_profile_equal": (
            first.get("storage_profile") == second.get("storage_profile")
        ),
        "artifact_codec_equal": (
            first.get("artifact_codec") == second.get("artifact_codec")
        ),
        "compiler_sha256_equal": (
            first.get("compiler_sha256") == second.get("compiler_sha256")
        ),
        "world_index_module_sha256_equal": (
            first.get("world_index_module_sha256")
            == second.get("world_index_module_sha256")
        ),
        "structural_parser_module_sha256_equal": (
            first.get("structural_parser_module_sha256")
            == second.get("structural_parser_module_sha256")
        ),
        "both_source_and_build_gates_pass": (
            first.get("source_and_build_gates_pass") is True
            and second.get("source_and_build_gates_pass") is True
        ),
        "both_task_blind": (
            first.get("task_conditioned") is False
            and second.get("task_conditioned") is False
            and first.get("task_or_witness_inputs") == []
            and second.get("task_or_witness_inputs") == []
        ),
    }
    report = {
        "schema": "dra_e1_reproducibility_report_v2",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "first": str(args.first.resolve()),
        "second": str(args.second.resolve()),
        "first_logical_build_id": first["logical_build_id"],
        "second_logical_build_id": second["logical_build_id"],
        "source_manifest_id": first["source_manifest_id"],
        "checks": checks,
        "diagnostics": {
            "raw_sqlite_sha256_equal": (
                first_raw_sqlite_sha256 == second_raw_sqlite_sha256
            ),
            "first_raw_sqlite_sha256": first_raw_sqlite_sha256,
            "second_raw_sqlite_sha256": second_raw_sqlite_sha256,
            "first_canonical_sqlite_sha256": (
                first_canonical_sqlite_sha256
            ),
            "second_canonical_sqlite_sha256": (
                second_canonical_sqlite_sha256
            ),
            "sqlite_header_differing_offsets": header_differences,
            "normalized_sqlite_header_ranges": [
                [start, end]
                for start, end in SQLITE_NONCONTENT_HEADER_RANGES
            ],
        },
        "passed": all(checks.values()),
        "note": (
            "Logical identities and canonical SQLite bytes must match. Raw "
            "SQLite hashes remain diagnostic because the file change counter "
            "(offset 24) and version-valid-for number (offset 92) encode "
            "write-transaction state rather than benchmark content. Run "
            "timestamps and measured elapsed time are also excluded."
        ),
    }
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
