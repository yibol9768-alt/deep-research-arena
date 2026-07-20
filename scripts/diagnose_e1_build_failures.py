#!/usr/bin/env python3
"""Diagnose records missing from an in-progress E1 build checkpoint."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import WorldIndexWriter, iter_jsonl


def source_records(source_dir: Path) -> Iterator[dict[str, Any]]:
    manifest = json.loads(
        (source_dir / "source-manifest.json").read_text(encoding="utf-8")
    )
    for pack in manifest["packs"]:
        yield from iter_jsonl(source_dir / pack["records_path"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--attempted", type=int, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    expected: list[dict[str, Any]] = []
    for index, record in enumerate(source_records(source_dir), 1):
        if index > args.attempted:
            break
        expected.append(record)

    conn = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    actual = {
        (str(pack_id), str(source_id))
        for pack_id, source_id in conn.execute(
            "SELECT pack_id,source_id FROM documents"
        )
    }
    expected_keys = [
        (str(record["pack_id"]), str(record["source_id"]))
        for record in expected
    ]
    missing_records = [
        (index, record)
        for index, record in enumerate(expected, 1)
        if (str(record["pack_id"]), str(record["source_id"])) not in actual
    ]

    key_counts = Counter(expected_keys)
    url_counts = Counter(
        str(record.get("canonical_url") or "") for record in expected
    )
    missing = []
    for index, record in missing_records:
        canonical_url = str(record.get("canonical_url") or "")
        url_owner = conn.execute(
            "SELECT pack_id,source_id FROM documents WHERE canonical_url=?",
            (canonical_url,),
        ).fetchone()
        isolated_error = None
        with tempfile.TemporaryDirectory(prefix="dra-e1-diagnose-") as tmp:
            writer = WorldIndexWriter(
                Path(tmp) / "isolated.sqlite",
                snapshot_id="dra-e1-diagnostic",
                overwrite=True,
            )
            try:
                writer.add_record(record)
                writer.finalize()
            except Exception as exc:  # diagnostic artifact needs exact repr
                isolated_error = repr(exc)
            finally:
                writer.close()
        missing.append({
            "record_index": index,
            "pack_id": str(record.get("pack_id")),
            "source_id": str(record.get("source_id")),
            "canonical_url": canonical_url,
            "page_type": record.get("page_type"),
            "title": record.get("title"),
            "duplicate_source_key_count": key_counts[
                (str(record["pack_id"]), str(record["source_id"]))
            ],
            "duplicate_canonical_url_count": url_counts[canonical_url],
            "canonical_url_existing_owner": (
                list(url_owner) if url_owner is not None else None
            ),
            "isolated_error": isolated_error,
        })
    conn.close()

    report = {
        "schema": "dra_e1_live_build_diagnostic_v1",
        "attempted": args.attempted,
        "expected_loaded": len(expected),
        "actual_documents_visible": len(actual),
        "missing_count": len(missing),
        "missing": missing,
    }
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
