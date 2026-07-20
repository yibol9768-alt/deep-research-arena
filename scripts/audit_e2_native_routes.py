#!/usr/bin/env python3
"""Audit compiled E2 identities against the frozen native Kiwix surface."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, build_opener, urlopen


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rewrite_origin(url: str, base_url: str) -> str:
    source = urlsplit(url)
    base = urlsplit(base_url)
    return urlunsplit((
        base.scheme,
        base.netloc,
        source.path,
        source.query,
        source.fragment,
    ))


def normalized_route(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    return parsed.path, parsed.query


def request_without_redirect(url: str, timeout: float) -> dict[str, Any]:
    opener = build_opener(NoRedirect)
    try:
        response = opener.open(url, timeout=timeout)
        try:
            return {
                "status": int(response.status),
                "location": response.headers.get("Location"),
                "body": response.read(),
            }
        finally:
            response.close()
    except HTTPError as exc:
        return {
            "status": int(exc.code),
            "location": exc.headers.get("Location"),
            "body": exc.read(),
        }


def sample_rows(
    connection: sqlite3.Connection,
    *,
    page_type: str,
    limit: int,
) -> list[sqlite3.Row]:
    return list(connection.execute(
        "SELECT page_snapshot_id,source_id,canonical_url,redirect_target,"
        "raw_content_hash,page_type,metadata_json FROM documents "
        "WHERE page_type=? ORDER BY page_snapshot_id LIMIT ?",
        (page_type, limit),
    ))


def edge_identity_rows(
    connection: sqlite3.Connection,
    *,
    limit: int,
) -> list[sqlite3.Row]:
    """Select paths most likely to be damaged by URL normalization."""

    return list(connection.execute(
        "SELECT page_snapshot_id,source_id,canonical_url,redirect_target,"
        "raw_content_hash,page_type,metadata_json FROM documents "
        "WHERE source_id LIKE '/%' "
        "OR (length(source_id)>=2 AND substr(source_id,2,1)='/') "
        "ORDER BY page_snapshot_id LIMIT ?",
        (limit,),
    ))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8090",
        help="Origin of the frozen native Kiwix service.",
    )
    parser.add_argument("--per-type", type=int, default=100)
    parser.add_argument("--edge-identity-limit", type=int, default=1_000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--build-manifest", type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.per_type <= 0:
        raise SystemExit("--per-type must be positive")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    if args.edge_identity_limit <= 0:
        raise SystemExit("--edge-identity-limit must be positive")

    db_path = args.db.resolve()
    manifest_path = (
        args.build_manifest.resolve()
        if args.build_manifest
        else db_path.parent / "build-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_db_hash = file_sha256(db_path)
    failures: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}

    if actual_db_hash != manifest.get("sqlite_sha256"):
        failures.append({
            "kind": "manifest_sqlite_hash_mismatch",
            "expected": manifest.get("sqlite_sha256"),
            "actual": actual_db_hash,
        })

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows_by_type = {
            page_type: sample_rows(
                connection,
                page_type=page_type,
                limit=args.per_type,
            )
            for page_type in (
                "wiki_article",
                "wiki_resource",
                "wiki_redirect",
            )
        }
        edge_rows = edge_identity_rows(
            connection, limit=args.edge_identity_limit
        )
    finally:
        connection.close()

    edge_ids = {str(row["page_snapshot_id"]) for row in edge_rows}
    selected_ids = {
        str(row["page_snapshot_id"])
        for rows in rows_by_type.values()
        for row in rows
    }
    for row in edge_rows:
        page_id = str(row["page_snapshot_id"])
        if page_id in selected_ids:
            continue
        rows_by_type.setdefault(str(row["page_type"]), []).append(row)
        selected_ids.add(page_id)

    edge_passed = 0
    for page_type, rows in rows_by_type.items():
        passed = 0
        counts[page_type] = {"sampled": len(rows), "passed": 0}
        for row in rows:
            native_url = rewrite_origin(
                str(row["canonical_url"]), args.base_url
            )
            metadata = json.loads(row["metadata_json"])
            failure_base = {
                "page_snapshot_id": row["page_snapshot_id"],
                "source_id": row["source_id"],
                "page_type": page_type,
                "native_url": native_url,
            }
            try:
                if page_type != "wiki_redirect" or metadata.get(
                    "redirect_kind"
                ) == "html_meta_refresh":
                    with urlopen(native_url, timeout=args.timeout) as response:
                        status = int(response.status)
                        body = response.read()
                    actual_hash = sha256(body).hexdigest()
                    if status != 200 or actual_hash != row["raw_content_hash"]:
                        failures.append({
                            **failure_base,
                            "kind": "native_content_mismatch",
                            "status": status,
                            "expected_raw_hash": row["raw_content_hash"],
                            "actual_raw_hash": actual_hash,
                        })
                        continue
                else:
                    response = request_without_redirect(
                        native_url, args.timeout
                    )
                    location = response.get("location")
                    expected = rewrite_origin(
                        str(row["redirect_target"]), args.base_url
                    )
                    actual = (
                        urljoin(native_url, str(location))
                        if location else None
                    )
                    if (
                        response["status"] not in (301, 302, 303, 307, 308)
                        or actual is None
                        or normalized_route(actual)
                        != normalized_route(expected)
                    ):
                        failures.append({
                            **failure_base,
                            "kind": "native_redirect_mismatch",
                            "status": response["status"],
                            "location": location,
                            "expected_target": expected,
                            "actual_target": actual,
                        })
                        continue
                passed += 1
                if str(row["page_snapshot_id"]) in edge_ids:
                    edge_passed += 1
            except Exception as exc:
                failures.append({
                    **failure_base,
                    "kind": "native_request_error",
                    "error": repr(exc),
                })
        counts[page_type]["passed"] = passed

    sampled = sum(value["sampled"] for value in counts.values())
    passed = sum(value["passed"] for value in counts.values())
    gates = {
        "manifest_sqlite_hash_valid": (
            actual_db_hash == manifest.get("sqlite_sha256")
        ),
        "all_requested_page_types_present": all(
            value["sampled"] > 0 for value in counts.values()
        ),
        "native_roundtrip_rate_1_0": sampled > 0 and passed == sampled,
        "edge_identity_roundtrip_rate_1_0": (
            len(edge_ids) > 0 and edge_passed == len(edge_ids)
        ),
    }
    report = {
        "schema": "dra_e2_native_route_audit_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "db": str(db_path),
        "build_manifest": str(manifest_path),
        "logical_build_id": manifest.get("logical_build_id"),
        "sqlite_sha256": actual_db_hash,
        "base_url": args.base_url,
        "counts": counts,
        "sampled": sampled,
        "passed_samples": passed,
        "edge_identity_sampled": len(edge_ids),
        "edge_identity_passed": edge_passed,
        "failures": failures,
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
