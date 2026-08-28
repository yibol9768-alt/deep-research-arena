#!/usr/bin/env python3
"""Per-cell search door with a private bracket and evidence directory."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SEARCH_PATHS = {"/search", "/bm25/search", "/_search"}
FETCH_PATHS = {"/fetch", "/extract"}


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    finally:
        os.close(fd)


class SharedSlot:
    def __init__(self, directory: Path, count: int, cell_id: str, ledger: Path):
        self.directory, self.count, self.cell_id, self.ledger = directory, count, cell_id, ledger
        self.handle = None
        self.slot = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        while True:
            for idx in range(self.count):
                handle = (self.directory / f"slot-{idx}.lock").open("a+")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.handle, self.slot = handle, idx
                    _append(self.ledger, {"at_ns": time.time_ns(), "event": "acquire", "cell_id": self.cell_id, "slot": idx})
                    return self
                except BlockingIOError:
                    handle.close()
            time.sleep(0.01)

    def __exit__(self, exc_type, _value, _tb):
        try:
            _append(self.ledger, {"at_ns": time.time_ns(), "event": "release", "cell_id": self.cell_id, "slot": self.slot, "outcome": "exception" if exc_type else "complete"})
        finally:
            if self.handle:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                self.handle.close()


class Bracket:
    def __init__(self, cell_id: str, evidence_dir: Path):
        self.cell_id, self.evidence_dir = cell_id, evidence_dir
        self.lock = threading.Lock()
        self.run_id: str | None = None
        self.counters = {"search": 0, "fetch": 0}

    def mark(self, payload: dict) -> tuple[int, dict]:
        run_id, phase = payload.get("run_id"), payload.get("phase")
        if not isinstance(run_id, str) or not run_id or phase not in {"start", "end"}:
            return 400, {"error": "invalid_mark"}
        with self.lock:
            if phase == "start":
                if self.run_id not in {None, run_id}:
                    return 409, {"error": "bracket_owned", "owner": self.run_id}
                self.run_id = run_id
            elif self.run_id != run_id:
                return 409, {"error": "not_bracket_owner", "owner": self.run_id}
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            _append(self.evidence_dir / f"{run_id}.jsonl", {"schema_version": "1.0.0", "at_ns": time.time_ns(), "kind": "mark", "phase": phase, "cell_id": self.cell_id, "run_id": run_id})
            if phase == "end":
                self.run_id = None
            return 200, {"ok": True, "phase": phase, "run_id": run_id}


def _store_blob(directory: Path, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    target = directory / "blobs" / digest
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return digest
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    return digest


def start_proxy(*, upstream: str, cell_id: str, evidence_dir: Path, slot_dir: Path, slot_ledger: Path, slot_count: int = 4, timeout: float = 600):
    bracket = Bracket(cell_id, evidence_dir)
    upstream = upstream.rstrip("/")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _json(self, status: int, body: dict):
            payload = json.dumps(body, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle(self):
            route = urllib.parse.urlsplit(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            if route == "/_mark" and self.command == "POST":
                try:
                    payload = json.loads(body)
                except Exception:
                    return self._json(400, {"error": "invalid_json"})
                status, response = bracket.mark(payload)
                return self._json(status, response)
            if route in {"/_evidence/status", "/healthz"}:
                with bracket.lock:
                    return self._json(200, {"cell_id": cell_id, "active_run_id": bracket.run_id, "counters": dict(bracket.counters)})
            if route == "/_sources/health":
                return self._source_health()
            if route in SEARCH_PATHS | FETCH_PATHS:
                with bracket.lock:
                    run_id = bracket.run_id
                if not run_id:
                    return self._json(409, {"error": "no_active_bracket", "cell_id": cell_id})
            else:
                run_id = None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection", "content-length"}}
            request = urllib.request.Request(upstream + self.path, data=body if body else None, headers=headers, method=self.command)
            guarded = route in SEARCH_PATHS
            gate = SharedSlot(slot_dir, slot_count, cell_id, slot_ledger) if guarded else contextlib.nullcontext()
            try:
                with gate:
                    try:
                        with urllib.request.urlopen(request, timeout=timeout) as response:
                            response_body, status, response_headers = response.read(), response.status, response.headers
                    except urllib.error.HTTPError as exc:
                        response_body, status, response_headers = exc.read(), exc.code, exc.headers
            except Exception as exc:
                return self._json(502, {"error": "search_upstream_failure", "type": type(exc).__name__})
            if run_id and route in SEARCH_PATHS | FETCH_PATHS:
                kind = "search" if route in SEARCH_PATHS else "fetch"
                digest = _store_blob(evidence_dir, response_body)
                with bracket.lock:
                    bracket.counters[kind] += 1
                _append(evidence_dir / f"{run_id}.jsonl", {
                    "schema_version": "1.0.0", "at_ns": time.time_ns(), "cell_id": cell_id,
                    "run_id": run_id, "kind": kind, "method": self.command, "path": self.path,
                    "status": status, "request_sha256": hashlib.sha256(body).hexdigest(),
                    "response_sha256": digest, "response_blob_ref": f"blobs/{digest}", "response_bytes": len(response_body),
                })
            self.send_response(status)
            for key, value in response_headers.items():
                if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def _source_health(self):
            """Translate shared three-source health into the frozen Kiwix census.

            This still calls the real upstream health endpoint. It does not
            treat shopping/forum failures as relevant to a Kiwix-only task, but
            requires a real wiki hit, a wiki-shaped returned URL, and a concrete
            backend identity before reporting ok.
            """
            target = upstream + "/_sources/health?fresh=true"
            try:
                request = urllib.request.Request(target, method="GET")
                with urllib.request.urlopen(request, timeout=min(timeout, 30)) as response:
                    raw, upstream_status = response.read(), response.status
                upstream_doc = json.loads(raw)
            except Exception as exc:
                return self._json(503, {"ok": False, "down": {"wiki": f"upstream_health:{type(exc).__name__}"}, "sources": {}, "not_queried": [], "sample_urls": []})
            wiki = (upstream_doc.get("sources") or {}).get("wiki")
            wiki_hits = int((wiki or {}).get("n_results") or 0)
            sample_urls = [url for url in upstream_doc.get("sample_urls") or [] if isinstance(url, str)]
            wiki_urls = [url for url in sample_urls if any(token in url.lower() for token in ("wikipedia", "kiwix", "localhost:8090"))]
            backend_sha = upstream_doc.get("backend_sha256")
            ok = upstream_status == 200 and wiki_hits > 0 and bool(wiki_urls) and isinstance(backend_sha, str) and bool(backend_sha)
            receipt = {
                "schema_version": "1.0.0", "at_ns": time.time_ns(), "cell_id": cell_id,
                "task_source_census_sha256": os.environ.get("DRA_TASK_SOURCE_CENSUS_SHA256"),
                "required_sources": ["wiki"], "upstream_http_status": upstream_status,
                "upstream_response_sha256": hashlib.sha256(raw).hexdigest(),
                "wiki_n_results": wiki_hits, "wiki_sample_urls": wiki_urls,
                "backend_sha256": backend_sha, "decision": "PASS" if ok else "FAIL",
            }
            _append(evidence_dir / "source_health_receipts.jsonl", receipt)
            filtered = {
                "ok": ok, "sources": {"wiki": wiki} if isinstance(wiki, dict) else {},
                "down": {} if ok else {"wiki": "missing_hit_url_or_backend_identity"},
                "degraded": {}, "not_queried": [], "sample_urls": wiki_urls,
                "query": upstream_doc.get("query"), "backend_sha256": backend_sha,
                "task_source_census_sha256": receipt["task_source_census_sha256"],
                "required_sources": ["wiki"], "upstream_response_sha256": receipt["upstream_response_sha256"],
            }
            return self._json(200 if ok else 503, filtered)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name=f"cell-search-{cell_id}")
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def stop_proxy(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
