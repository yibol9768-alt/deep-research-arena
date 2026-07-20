#!/usr/bin/env python3
"""Serve a compiled E1 World Index through a minimal agent-visible HTTP API."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.world_index.e1 import WorldIndexWriter
from src.world_index.e1_compact import (
    COMPACT_SCHEMA_VERSION,
    CompactWorldIndexWriter,
)


def open_writer(
    db_path: Path,
) -> WorldIndexWriter | CompactWorldIndexWriter:
    probe = sqlite3.connect(
        f"file:{db_path}?mode=ro", uri=True
    )
    row = probe.execute(
        "SELECT value_json FROM metadata WHERE key='schema_version'"
    ).fetchone()
    probe.close()
    schema_version = json.loads(row[0]) if row else None
    writer_type = (
        CompactWorldIndexWriter
        if schema_version == COMPACT_SCHEMA_VERSION
        else WorldIndexWriter
    )
    writer = object.__new__(writer_type)
    writer.path = db_path
    writer.snapshot_id = ""
    writer.conn = sqlite3.connect(
        f"file:{db_path}?mode=ro", uri=True
    )
    writer.conn.row_factory = sqlite3.Row
    return writer


def make_handler(db_path: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DRA-E1-Renderer/1"

        def send_bytes(
            self, status: int, content_type: str, payload: bytes
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, status: int, value) -> None:
            payload = (
                json.dumps(
                    value, ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n"
            ).encode("utf-8")
            self.send_bytes(
                status, "application/json; charset=utf-8", payload
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/ready":
                self.send_json(200, {"ok": True})
                return
            writer = open_writer(db_path)
            try:
                if parsed.path == "/health":
                    self.send_json(
                        200, {"ok": True, "census": writer.census()}
                    )
                    return
                if parsed.path.startswith("/document/"):
                    page_id = unquote(
                        parsed.path[len("/document/") :]
                    )
                    try:
                        payload = writer.render_by_id(page_id).encode(
                            "utf-8"
                        )
                    except KeyError:
                        self.send_json(
                            404, {"error": "unknown_document"}
                        )
                        return
                    self.send_bytes(
                        200, "text/html; charset=utf-8", payload
                    )
                    return
                if parsed.path == "/search":
                    query = parse_qs(parsed.query).get("q", [""])[0]
                    try:
                        limit = int(
                            parse_qs(parsed.query).get(
                                "limit", ["10"]
                            )[0]
                        )
                    except ValueError:
                        limit = 10
                    if not query:
                        self.send_json(
                            400, {"error": "query_required"}
                        )
                        return
                    try:
                        results = writer.search(
                            query, limit=max(1, min(100, limit))
                        )
                    except sqlite3.OperationalError as exc:
                        self.send_json(
                            400, {"error": "invalid_query",
                                  "detail": str(exc)}
                        )
                        return
                    self.send_json(
                        200, {"query": query, "results": results}
                    )
                    return
                self.send_json(404, {"error": "not_found"})
            finally:
                writer.close()

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write(
                "[e1-renderer] "
                + (fmt % args)
                + "\n"
            )

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    args = parser.parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")
    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(db_path)
    )
    print(
        f"[e1-renderer] serving {db_path} "
        f"on http://{args.host}:{args.port}",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
