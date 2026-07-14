"""Transport and attribution contract for the recording egress door."""

from __future__ import annotations

import asyncio
import http.client
import http.server
import json
import os
import pathlib
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.egress_proxy.app import (  # noqa: E402
    CORPUS_READ_TIMEOUT,
    SERVICE_READ_TIMEOUT,
    _read_timeout,
    proxy_env,
)
from scripts import run_deep_task  # noqa: E402
from scripts.runners import _egress  # noqa: E402
from scripts.runners.deepagents_runner import (  # noqa: E402
    _build_driver_script as _build_deepagents_driver,
    _build_env as _build_deepagents_env,
)
from src.eval.fetch_log import linked_urls, load_run_evidence  # noqa: E402

PAGE = b'<html><a href="/A/Betamax">b</a><a href="../A/Walkman">w</a>body</html>'


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Handler(http.server.BaseHTTPRequestHandler):
    last_body = b""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        _Handler.last_body = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def origins():
    servers = []
    urls = []
    for _ in range(2):
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        servers.append(server)
        port = int(server.server_address[1])
        urls.append(f"http://127.0.0.1:{port}")
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"corpus": urls[0], "service": urls[1]}
    for server in servers:
        server.shutdown()
        server.server_close()


def _control(port: int, method: str, path: str, payload: dict | None = None):
    raw = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if raw else {}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(method, path, body=raw, headers=headers)
        response = conn.getresponse()
        body = response.read()
        return response.status, json.loads(body or b"{}")
    finally:
        conn.close()


@pytest.fixture(scope="module")
def proxy_process(tmp_path_factory, origins):
    evidence_dir = tmp_path_factory.mktemp("egress-evidence")
    proxy_port = _free_port()
    corpus_port = origins["corpus"].rsplit(":", 1)[1]
    service_port = origins["service"].rsplit(":", 1)[1]
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(ROOT),
        "SHIM_EVIDENCE_DIR": str(evidence_dir),
        "SHIM_EVIDENCE": "1",
        "SHIM_BRACKET_TTL_S": "3600",
        "DRA_EGRESS_CORPUS": (
            f"127.0.0.1:{corpus_port},localhost:{corpus_port}"
        ),
        "DRA_EGRESS_SERVICES": (
            f"127.0.0.1:{service_port},localhost:{service_port}"
        ),
    })
    env.pop("DRA_EGRESS_ALLOWED", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "integrations.egress_proxy.app",
         "--host", "127.0.0.1", "--port", str(proxy_port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while True:
        try:
            if _control(proxy_port, "GET", "/healthz")[0] == 200:
                break
        except Exception:
            pass
        if proc.poll() is not None or time.monotonic() >= deadline:
            stderr = proc.stderr.read() if proc.stderr else ""
            proc.kill()
            pytest.fail(f"egress proxy failed to start: {stderr}")
        time.sleep(0.05)

    yield {
        "port": proxy_port,
        "url": f"http://127.0.0.1:{proxy_port}",
        "evidence_dir": evidence_dir,
    }
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


class _Run:
    def __init__(self, proxy: dict, run_id: str) -> None:
        self.proxy = proxy
        self.run_id = run_id
        self.path = proxy["evidence_dir"] / f"{run_id}.jsonl"
        self.ended = False

    def end(self) -> None:
        if self.ended:
            return
        status, body = _control(
            self.proxy["port"], "POST", "/_mark",
            {"run_id": self.run_id, "phase": "end"},
        )
        assert status == 200, body
        self.ended = True

    def evidence(self):
        self.end()
        return load_run_evidence(self.path)


@pytest.fixture
def run(monkeypatch, proxy_process):
    run_id = "r-" + uuid.uuid4().hex
    status, body = _control(
        proxy_process["port"], "POST", "/_mark",
        {"run_id": run_id, "lane": "probe", "task": "t",
         "backbone": "b", "phase": "start"},
    )
    assert status == 200, body
    for key, value in proxy_env(proxy_process["url"]).items():
        monkeypatch.setenv(key, value)
    handle = _Run(proxy_process, run_id)
    yield handle
    if not handle.ended:
        handle.end()


def _corpus_url(origins: dict) -> str:
    port = origins["corpus"].rsplit(":", 1)[1]
    return f"http://localhost:{port}/content/wiki/A/Sony"


def test_proxy_env_is_explicit_full_proxy_policy():
    env = proxy_env("http://127.0.0.1:12345")
    for key in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        assert env[key] == "http://127.0.0.1:12345"
    assert env["no_proxy"] == env["NO_PROXY"] == ""


def test_service_requests_have_a_separate_long_read_timeout(origins, monkeypatch):
    from integrations.egress_proxy import app as egress_app

    service_origin = origins["service"].removeprefix("http://")
    monkeypatch.setattr(egress_app, "SERVICE_ORIGINS", {service_origin})
    assert SERVICE_READ_TIMEOUT > CORPUS_READ_TIMEOUT
    assert _read_timeout(_corpus_url(origins)) == CORPUS_READ_TIMEOUT
    assert _read_timeout(origins["service"] + "/v1/chat/completions") == SERVICE_READ_TIMEOUT


def test_final_runner_env_cannot_erase_configured_door(monkeypatch):
    url = "http://127.0.0.1:32123"
    monkeypatch.setenv("DRA_EGRESS_PROXY", url)
    monkeypatch.setenv("HTTP_PROXY", "http://ambient.invalid:1")
    monkeypatch.setenv("NO_PROXY", "*")
    env = _build_deepagents_env("http://127.0.0.1:8088/v1", "model")
    for key, value in proxy_env(url).items():
        assert env[key] == value
    driver = _build_deepagents_driver(
        "intent", "model", "http://127.0.0.1:8081",
        "http://127.0.0.1:8088/v1",
    )
    assert "if not _DRA_EGRESS_ON" in driver
    assert "os.environ['NO_PROXY'] = '*'" in driver


def test_fetch_observable_upgrade_requires_bracket_and_enforcement(monkeypatch):
    # qx is protocol-false, so it is a useful canary for accidental optimistic
    # upgrades. A configured proxy by itself is never enough.
    monkeypatch.setenv("DRA_EGRESS_PROXY", "http://127.0.0.1:32123")
    monkeypatch.delenv("DRA_EGRESS_ENFORCED", raising=False)
    assert not run_deep_task._lane_fetch_observable(
        "qx-agents", egress_bracketed=True,
    )
    monkeypatch.setenv("DRA_EGRESS_ENFORCED", "1")
    # A boolean supplied by the operator is not an enforcement boundary.
    assert not _egress.enforced()
    assert not run_deep_task._lane_fetch_observable(
        "qx-agents", egress_bracketed=True,
    )
    monkeypatch.setattr(_egress, "enforced", lambda env=None: True)
    assert not run_deep_task._lane_fetch_observable(
        "qx-agents", egress_bracketed=False,
    )
    assert run_deep_task._lane_fetch_observable(
        "qx-agents", egress_bracketed=True,
    )
    assert not run_deep_task._lane_fetch_observable(
        "codex", egress_bracketed=True,
    )
    monkeypatch.setenv("DRA_REMOTE_EGRESS_PROXY", "http://127.0.0.1:39099")
    monkeypatch.setenv("DRA_REMOTE_EGRESS_ENFORCED", "1")
    # Remote flags are also self-attestations and must not upgrade the lane.
    assert not run_deep_task._lane_fetch_observable(
        "codex", egress_bracketed=True,
    )
    monkeypatch.setattr(_egress, "remote_enforced", lambda env=None: True)
    assert run_deep_task._lane_fetch_observable(
        "codex", egress_bracketed=True,
    )


def test_requests_is_recorded(run, origins):
    import requests
    assert requests.get(_corpus_url(origins), timeout=5).status_code == 200
    assert run.evidence().fetched


def test_httpx_is_recorded(run, origins):
    import httpx
    assert httpx.get(_corpus_url(origins), timeout=5, trust_env=True).status_code == 200
    assert run.evidence().fetched, "httpx bypassed the door"


def test_aiohttp_is_recorded(run, origins):
    import aiohttp

    async def go():
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(_corpus_url(origins)) as response:
                return response.status

    assert asyncio.run(go()) == 200
    assert run.evidence().fetched, "aiohttp bypassed the door"


def test_curl_is_recorded(run, origins):
    response = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         _corpus_url(origins)],
        capture_output=True, text=True, timeout=10,
    )
    assert response.stdout.strip() == "200"
    assert run.evidence().fetched, "curl bypassed the door"


def test_allowed_service_api_is_not_recorded_as_page_fetch(run, origins):
    import requests
    response = requests.get(origins["service"] + "/v1/chat/completions", timeout=5)
    assert response.status_code == 200
    assert not run.evidence().fetched, \
        "ds_proxy/shim service traffic was manufactured into page evidence"


def test_escape_is_refused_and_attributed(run):
    import requests
    assert requests.get("http://example.com/", timeout=5).status_code == 403
    blocked = run.evidence().blocked
    assert any(item["url"].startswith("http://example.com") for item in blocked)


def test_links_are_stamped_so_navigation_is_not_fabrication(run, origins):
    import requests
    requests.get(_corpus_url(origins), timeout=5)
    evidence = run.evidence()
    def load_blob(digest: str):
        path = run.proxy["evidence_dir"] / "blobs" / digest
        return path.read_bytes() if path.exists() else None

    links = linked_urls(evidence, load_blob)
    assert any(url.endswith("/A/Betamax") for url in links)
    assert any(url.endswith("/A/Walkman") for url in links)


def test_out_of_process_bracket_has_no_unattributed_fetches(run, origins):
    import requests
    requests.get(_corpus_url(origins), timeout=5)
    evidence = run.evidence()
    assert evidence.run_id == run.run_id and evidence.lane == "probe"
    assert evidence.fetched
    unattributed = run.proxy["evidence_dir"] / "_unattributed.jsonl"
    assert not unattributed.exists(), "out-of-process fetch lost its owner bracket"


def test_closed_egress_stream_merges_into_single_canonical_bracket(
    run, origins, tmp_path,
):
    """The shim and egress process must not contribute duplicate marks."""
    import requests

    unified = tmp_path / "unified"
    unified.mkdir()
    target = unified / f"{run.run_id}.jsonl"
    start = {
        "ts": time.time(), "run_id": run.run_id, "worker": "0",
        "lane": "probe", "task": "t", "backbone": "b",
        "fetch_observable": True, "kind": "mark", "phase": "start",
    }
    target.write_text(json.dumps(start) + "\n", encoding="utf-8")

    assert requests.get(_corpus_url(origins), timeout=5).status_code == 200
    run.end()
    merged = run_deep_task._merge_egress_evidence(
        run.run_id,
        egress_dir=run.proxy["evidence_dir"],
        unified_dir=unified,
    )
    end = dict(start, ts=time.time(), phase="end")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(end) + "\n")

    evidence = load_run_evidence(target)
    assert evidence.available and evidence.fetched
    assert merged["records"] >= 1
    digest = next(iter(evidence.fetched.values()))["body_sha256"]
    assert (unified / "blobs" / digest).is_file()


def test_recorder_process_owns_privileged_merge(origins, tmp_path):
    """Production mode merges before the worker asks the shim to close."""
    import requests

    evidence_dir = tmp_path / "egress"
    canonical_dir = tmp_path / "canonical"
    evidence_dir.mkdir()
    canonical_dir.mkdir()
    run_id = "server-merge-" + uuid.uuid4().hex
    target = canonical_dir / f"{run_id}.jsonl"
    start = {
        "ts": time.time(), "run_id": run_id, "worker": "0",
        "lane": "probe", "task": "t", "backbone": "b",
        "fetch_observable": True, "kind": "mark", "phase": "start",
    }
    target.write_text(json.dumps(start) + "\n", encoding="utf-8")

    proxy_port = _free_port()
    corpus_port = origins["corpus"].rsplit(":", 1)[1]
    service_port = origins["service"].rsplit(":", 1)[1]
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(ROOT),
        "SHIM_EVIDENCE_DIR": str(evidence_dir),
        "SHIM_EVIDENCE": "1",
        "DRA_EGRESS_CORPUS": f"127.0.0.1:{corpus_port},localhost:{corpus_port}",
        "DRA_EGRESS_SERVICES": f"127.0.0.1:{service_port},localhost:{service_port}",
        "DRA_EGRESS_CANONICAL_EVIDENCE_DIR": str(canonical_dir),
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "integrations.egress_proxy.app",
         "--host", "127.0.0.1", "--port", str(proxy_port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                status, health = _control(proxy_port, "GET", "/healthz")
                if status == 200:
                    assert health["server_merge"] is True
                    break
            except Exception:
                pass
            if proc.poll() is not None or time.monotonic() >= deadline:
                pytest.fail(proc.stderr.read() if proc.stderr else "proxy startup failed")
            time.sleep(0.05)

        status, body = _control(
            proxy_port, "POST", "/_mark",
            {"run_id": run_id, "lane": "probe", "task": "t",
             "backbone": "b", "phase": "start"},
        )
        assert status == 200, body
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            _corpus_url(origins),
            proxies={"http": f"http://127.0.0.1:{proxy_port}"}, timeout=5,
        )
        assert response.status_code == 200
        status, body = _control(
            proxy_port, "POST", "/_mark", {"run_id": run_id, "phase": "end"},
        )
        assert status == 200, body
        assert body["merge"]["mode"] == "recorder"
        assert body["merge"]["records"] == 1

        end = dict(start, ts=time.time(), phase="end")
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(end) + "\n")
        merged = load_run_evidence(target)
        assert merged.available and merged.fetched
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def test_mark_end_requires_the_current_owner(run):
    port = run.proxy["port"]
    status, _ = _control(port, "POST", "/_mark", {"phase": "end"})
    assert status == 400
    status, body = _control(
        port, "POST", "/_mark", {"run_id": "sibling", "phase": "end"},
    )
    assert status == 409 and body["error"] == "run_owner_mismatch"
    status, health = _control(port, "GET", "/healthz")
    assert status == 200 and health["active_run"] == run.run_id
    run.end()
    status, _ = _control(
        port, "POST", "/_mark", {"run_id": run.run_id, "phase": "end"},
    )
    assert status == 409, "an already-closed caller must not get a false owner ack"


def test_reentrant_start_is_refused(run):
    status, _ = _control(
        run.proxy["port"], "POST", "/_mark",
        {"run_id": "sibling", "phase": "start"},
    )
    assert status == 409


def test_post_body_is_forwarded(run, origins):
    import requests
    _Handler.last_body = b""
    response = requests.post(
        origins["corpus"] + "/api", json={"q": "headphones"}, timeout=6,
    )
    assert response.status_code == 200
    assert _Handler.last_body == b'{"q": "headphones"}'


def test_chunked_request_is_refused_not_truncated(run, origins):
    corpus_port = origins["corpus"].rsplit(":", 1)[1]
    conn = http.client.HTTPConnection("127.0.0.1", run.proxy["port"], timeout=6)
    conn.putrequest("POST", f"http://localhost:{corpus_port}/api",
                    skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", f"localhost:{corpus_port}")
    conn.putheader("Transfer-Encoding", "chunked")
    conn.endheaders()
    conn.send(b"5\r\nhello\r\n0\r\n\r\n")
    assert conn.getresponse().status == 411
    conn.close()
