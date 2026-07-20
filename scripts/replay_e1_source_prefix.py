#!/usr/bin/env python3
"""Replay a deterministic E1 source prefix and report exact record failures."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import WorldIndexWriter, iter_jsonl


def source_records(
    source_dir: Path, manifest: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    for pack in manifest["packs"]:
        yield from iter_jsonl(source_dir / pack["records_path"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    manifest = json.loads(
        (source_dir / "source-manifest.json").read_text(encoding="utf-8")
    )
    writer = WorldIndexWriter(
        args.db.resolve(),
        snapshot_id=str(manifest["snapshot_id"]),
        overwrite=True,
    )
    started = time.perf_counter()
    attempted = 0
    compiled = 0
    failures = []
    for attempted, record in enumerate(
        source_records(source_dir, manifest), 1
    ):
        if attempted > args.limit:
            attempted -= 1
            break
        try:
            writer.add_record_atomic(record)
            compiled += 1
        except Exception as exc:
            failures.append({
                "record_index": attempted,
                "pack_id": record.get("pack_id"),
                "source_id": record.get("source_id"),
                "canonical_url": record.get("canonical_url"),
                "page_type": record.get("page_type"),
                "title": record.get("title"),
                "error": repr(exc),
            })
    writer.finalize()
    census = writer.census()
    writer.close()

    report = {
        "schema": "dra_e1_source_prefix_replay_v1",
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "source_manifest_id": manifest["source_manifest_id"],
        "limit": args.limit,
        "attempted": attempted,
        "compiled": compiled,
        "failures": failures,
        "failure_count": len(failures),
        "census": census,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            report, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "attempted": attempted,
        "compiled": compiled,
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
