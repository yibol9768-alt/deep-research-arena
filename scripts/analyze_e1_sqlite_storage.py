#!/usr/bin/env python3
"""Record auditable table/index storage attribution for an E1 SQLite build."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build_dir = args.build_dir.resolve()
    db_path = build_dir / "world-index.sqlite"
    manifest_path = build_dir / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_sha = file_sha256(db_path)
    conn = sqlite3.connect(db_path)
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(
        conn.execute("PRAGMA freelist_count").fetchone()[0]
    )
    objects = [
        {
            "name": str(row[0]),
            "bytes": int(row[1]),
            "pages": int(row[2]),
        }
        for row in conn.execute(
            "SELECT name,SUM(pgsize),COUNT(*) FROM dbstat "
            "GROUP BY name ORDER BY SUM(pgsize) DESC,name"
        )
    ]
    conn.close()
    object_bytes = sum(item["bytes"] for item in objects)
    report = {
        "schema": "dra_e1_sqlite_storage_attribution_v1",
        "build_dir": str(build_dir),
        "logical_build_id": manifest["logical_build_id"],
        "storage_profile": manifest.get("storage_profile", "row-structural-v1"),
        "sqlite_sha256": actual_sha,
        "manifest_sqlite_sha256": manifest["sqlite_sha256"],
        "manifest_hash_matches": actual_sha == manifest["sqlite_sha256"],
        "sqlite_file_bytes": db_path.stat().st_size,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "freelist_bytes": freelist_count * page_size,
        "dbstat_object_bytes": object_bytes,
        "objects": objects,
        "passed": (
            actual_sha == manifest["sqlite_sha256"]
            and object_bytes <= db_path.stat().st_size
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
