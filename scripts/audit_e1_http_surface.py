#!/usr/bin/env python3
"""Audit the E1 renderer over real HTTP against the compiled SQLite truth."""

from __future__ import annotations

import argparse
from hashlib import sha256
import heapq
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote, urlencode
from urllib.request import urlopen


def get_json(url: str, timeout: float) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(url: str, timeout: float) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_ids(
    conn: sqlite3.Connection, per_pack: int
) -> list[tuple[str, str, str]]:
    output = []
    packs = [
        row[0] for row in conn.execute(
            "SELECT DISTINCT pack_id FROM documents ORDER BY pack_id"
        )
    ]
    for pack in packs:
        rows = heapq.nsmallest(
            per_pack,
            conn.execute(
                "SELECT page_snapshot_id,title,rendered_content_hash "
                "FROM documents WHERE pack_id=?",
                (pack,),
            ),
            key=lambda row: (
                sha256(row[0].encode("utf-8")).digest(),
                row[0],
            ),
        )
        output.extend(rows)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:18090"
    )
    parser.add_argument("--per-pack", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--min-search-top20-rate", type=float, default=0.90
    )
    parser.add_argument(
        "--build-manifest", type=Path,
        help="Defaults to build-manifest.json beside --db when present.",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not 0 < args.min_search_top20_rate <= 1:
        raise SystemExit("--min-search-top20-rate must be in (0,1]")

    db_path = args.db.resolve()
    manifest_path = (
        args.build_manifest.resolve()
        if args.build_manifest
        else db_path.parent / "build-manifest.json"
    )
    build_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists() else None
    )
    actual_db_sha256 = (
        file_sha256(db_path) if build_manifest is not None else None
    )
    conn = sqlite3.connect(db_path)
    expected_documents = conn.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0]
    samples = sample_ids(conn, args.per_pack)
    health = get_json(
        f"{args.base_url.rstrip('/')}/health", args.timeout
    )
    hard_failures = []
    search_misses = []
    if (
        build_manifest is not None
        and actual_db_sha256 != build_manifest.get("sqlite_sha256")
    ):
        hard_failures.append({
            "kind": "build_manifest_sqlite_hash_mismatch",
            "expected": build_manifest.get("sqlite_sha256"),
            "actual": actual_db_sha256,
        })
    if not health.get("ok"):
        hard_failures.append({"kind": "health_not_ok"})
    if health.get("census", {}).get("documents") != expected_documents:
        hard_failures.append({
            "kind": "health_census_mismatch",
            "expected": expected_documents,
            "actual": health.get("census", {}).get("documents"),
        })

    document_pass = 0
    search_pass = 0
    search_eligible = 0
    for page_id, title, expected_hash in samples:
        payload = get_bytes(
            f"{args.base_url.rstrip('/')}/document/"
            f"{quote(page_id, safe='')}",
            args.timeout,
        )
        actual_hash = sha256(payload).hexdigest()
        if actual_hash == expected_hash:
            document_pass += 1
        else:
            hard_failures.append({
                "kind": "http_render_hash_mismatch",
                "page_snapshot_id": page_id,
                "expected": expected_hash,
                "actual": actual_hash,
            })

        tokens = [
            token for token in str(title or "").replace('"', " ").split()
            if len(token) >= 3 and token.replace("-", "").isalnum()
        ][:5]
        if not tokens:
            continue
        search_eligible += 1
        query = " OR ".join(f'"{token}"' for token in tokens)
        url = (
            f"{args.base_url.rstrip('/')}/search?"
            + urlencode({"q": query, "limit": 20})
        )
        result = get_json(url, args.timeout)
        if any(
            hit.get("page_snapshot_id") == page_id
            for hit in result.get("results", [])
        ):
            search_pass += 1
        else:
            search_misses.append({
                "kind": "http_search_top20_miss",
                "page_snapshot_id": page_id,
                "query": query,
            })
    conn.close()

    search_rate = (
        search_pass / search_eligible if search_eligible else None
    )
    gates = {
        "no_hard_failures": not hard_failures,
        "health_pass": not any(
            failure["kind"].startswith("health")
            for failure in hard_failures
        ),
        "document_hash_rate_1_0": (
            len(samples) > 0 and document_pass == len(samples)
        ),
        "search_top20_at_least_threshold": (
            search_rate is not None
            and search_rate >= args.min_search_top20_rate
        ),
    }
    report = {
        "schema": "dra_e1_http_audit_v2",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "renderer_script_sha256": file_sha256(
            Path(__file__).resolve().parent / "serve_e1_world_shard.py"
        ),
        "db": str(db_path),
        "build_manifest": (
            str(manifest_path) if build_manifest is not None else None
        ),
        "logical_build_id": (
            build_manifest.get("logical_build_id")
            if build_manifest is not None else None
        ),
        "sqlite_sha256": actual_db_sha256,
        "base_url": args.base_url,
        "sampled": len(samples),
        "health_pass": gates["health_pass"],
        "document_hash_pass": document_pass,
        "document_hash_rate": (
            document_pass / len(samples) if samples else None
        ),
        "search_eligible": search_eligible,
        "search_top20_pass": search_pass,
        "search_top20_rate": search_rate,
        "min_search_top20_rate": args.min_search_top20_rate,
        "search_misses": search_misses,
        "failures": hard_failures,
        "gates": gates,
        "passed": all(gates.values()),
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
