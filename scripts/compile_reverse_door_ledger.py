#!/usr/bin/env python3
"""Compile search-sidecar and reverse-door evidence into observation_ledger_v1."""

from __future__ import annotations

import argparse
from datetime import datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlunsplit


PORTS = {"shopping": 7770, "reddit": 9999, "wiki": 8090}


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def epoch(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(str(value)).timestamp()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    audit = args.run_dir / "control/audit"
    run_manifest = json.loads((args.run_dir / "control/run-manifest.json").read_text())
    run_id = str(run_manifest["run_id"])
    reverse = json.loads((audit / "reverse-door-evidence.json").read_text())
    window = reverse["worker_window"]
    start_ns = int(window["started_monotonic_ns"])
    end_ns = int(window["finished_monotonic_ns"])

    pending: list[tuple[float, dict]] = []
    strict_path = audit / "strict-evidence" / f"{run_id}.jsonl"
    for row in rows(strict_path):
        if row.get("kind") != "search":
            continue
        for url in row.get("urls_returned") or []:
            pending.append((epoch(row.get("ts")), {
                "event_type": "search_result",
                "timestamp": row.get("ts"),
                "request_url": str(row.get("endpoint") or ""),
                "canonical_url": str(url),
                "content_sha256": "",
                # The strict sidecar proves the returned URL but does not retain
                # result snippets.  The ledger schema has an explicit legacy
                # no-snippet marker: it licenses discovery without claim credit.
                "observable": True,
                "metadata": {
                    "query": row.get("query"),
                    "source": "tavily_sidecar",
                    "legacy_snippet_unavailable": True,
                },
            }))

    blobs_out = args.output.parent / "blobs"
    blobs_out.mkdir(parents=True, exist_ok=True)
    source_blobs = audit / "response-blobs"
    for row in rows(audit / "egress.jsonl"):
        door = str(row.get("door") or "")
        mono = int(row.get("monotonic_ns") or 0)
        if door not in PORTS or not (start_ns <= mono <= end_ns):
            continue
        path = str(row.get("path") or "/")
        query = str(row.get("query") or "")
        url = urlunsplit(("http", f"localhost:{PORTS[door]}", path, query, ""))
        source_digest = str(row.get("response_blob_sha256") or "")
        body = (source_blobs / source_digest).read_bytes()
        if body.startswith(b"\x1f\x8b"):
            body = gzip.decompress(body)
        digest = sha256(body).hexdigest()
        destination = blobs_out / digest
        if not destination.exists():
            destination.write_bytes(body)
        pending.append((epoch(row.get("timestamp")), {
            "event_type": "fetch_body",
            "timestamp": row.get("timestamp"),
            "request_url": url,
            "canonical_url": url,
            "content_sha256": digest,
            "blob_ref": digest,
            "http_status": row.get("status"),
            "observable": bool(row.get("response_complete")),
            "metadata": {
                "door": door,
                "wire_response_sha256": source_digest,
                "wire_content_decoded": digest != source_digest,
            },
        }))

    pending.sort(key=lambda item: item[0])
    events = []
    for event_id, (_, event) in enumerate(pending, 1):
        events.append({"run_id": run_id, "event_id": event_id, **event})
    artifact = {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
        "compiler": "reverse_door_plus_tavily_v1",
    }
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "events": len(events),
        "search_results": sum(e["event_type"] == "search_result" for e in events),
        "fetches": sum(e["event_type"] == "fetch_body" for e in events),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
