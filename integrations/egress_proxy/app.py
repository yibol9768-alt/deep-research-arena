"""Recording forward proxy: the one door every page read must pass through.

Why a proxy, when we already patch `requests`
---------------------------------------------
The in-process gate patches `requests.Session.send`. It covers smolagents'
VisitWebpageTool and langchain's loaders, and nothing else. The 2026-07-08 fetch
path audit found the rest of the field reads pages with libraries the patch
never sees:

    gpt-researcher, deerflow, ii-researcher   requests   (covered)
    qx-agents                                 aiohttp    (not covered)
    claude-code, codex, gemini-cli            curl       (not covered)
    anything using httpx                                 (not covered)

Eight of twelve lanes therefore had `fetch_observable: false`, which means
`proof_of_fetch` is withheld for them: we cannot say whether they opened what
they cite. Patching four client libraries in four places, in twelve adapters,
across three process boundaries, is a losing game. Two of the lanes run under
`--yolo` and `--dangerously-bypass-approvals-and-sandbox` and have no allowlist
to tighten at all.

But `requests`, `httpx`, `aiohttp(trust_env=True)` and `curl` all honour
`http_proxy`. Measured, all four: a single forward proxy captures every one.

So this is the door. It records what it serves into the run's evidence log, it
refuses anything outside the sandbox, and it needs no cooperation from the agent
or its framework.

What it is not
--------------
A proxy is a MECHANISM, not a GUARANTEE. An agent that connects straight to
`127.0.0.1:7770` bypasses it, because nothing at the network layer stops it. The
guarantee is the box-side rule that the sandbox origins are unreachable except
from this proxy (iptables owner-match, a netns, or binding the sites to an
address only the proxy can route to). `preflight.py` asserts that rule on the
box. This process is what makes the rule cheap to satisfy: with it in place,
every lane keeps working unchanged.

Run:
    python3 -m integrations.egress_proxy.app --port 8099
    export http_proxy=http://127.0.0.1:8099 HTTP_PROXY=http://127.0.0.1:8099
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.search_shim import evidence  # noqa: E402
from integrations.egress_proxy.finalize import merge_egress_evidence  # noqa: E402

# An allowed request is not necessarily a page read.  The shim, ds_proxy and
# llm_gateway are control/service planes.  Sending their JSON APIs through this
# door is necessary when NO_PROXY is empty, but recording those calls as corpus
# fetches manufactures proof-of-fetch for a framework that never opened a page.
_DEFAULT_CORPUS_ORIGINS = {
    "localhost:7770", "localhost:8090", "localhost:9999",
    "127.0.0.1:7770", "127.0.0.1:8090", "127.0.0.1:9999",
}
_DEFAULT_SERVICE_ORIGINS = {
    "localhost:8081", "localhost:8088", "localhost:8100",
    "127.0.0.1:8081", "127.0.0.1:8088", "127.0.0.1:8100",
}


def _parse_origins(raw: str) -> set[str]:
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _configured_origins() -> tuple[set[str], set[str]]:
    """Return ``(corpus, services)``.

    ``DRA_EGRESS_CORPUS`` names origins whose response bytes are evidence.
    ``DRA_EGRESS_SERVICES`` names origins that must remain reachable but must
    never be counted as page reads.  The old ``DRA_EGRESS_ALLOWED`` variable is
    accepted as a corpus-origin alias for existing launchers; known service
    origins are subtracted from it so a legacy list cannot turn ``/search`` or
    ``/v1/chat/completions`` into proof-of-fetch.
    """
    service_raw = os.environ.get("DRA_EGRESS_SERVICES", "").strip()
    services = (_parse_origins(service_raw) if service_raw
                else set(_DEFAULT_SERVICE_ORIGINS))

    corpus_raw = os.environ.get("DRA_EGRESS_CORPUS", "").strip()
    legacy_raw = os.environ.get("DRA_EGRESS_ALLOWED", "").strip()
    if corpus_raw:
        corpus = _parse_origins(corpus_raw)
    elif legacy_raw:
        corpus = _parse_origins(legacy_raw) - services
    else:
        corpus = set(_DEFAULT_CORPUS_ORIGINS)

    overlap = corpus & services
    if overlap:
        raise RuntimeError(
            "egress origin(s) cannot be both corpus and service: "
            + ", ".join(sorted(overlap))
        )
    return corpus, services


CORPUS_ORIGINS, SERVICE_ORIGINS = _configured_origins()
ALLOWED = CORPUS_ORIGINS | SERVICE_ORIGINS

MAX_BODY = int(os.environ.get("DRA_EGRESS_MAX_BODY", str(2_000_000)))
UPSTREAM_READ_TIMEOUT = float(os.environ.get("DRA_EGRESS_READ_TIMEOUT_S", "60"))
_CANONICAL_RAW = os.environ.get("DRA_EGRESS_CANONICAL_EVIDENCE_DIR", "").strip()
CANONICAL_EVIDENCE_DIR = Path(_CANONICAL_RAW).resolve() if _CANONICAL_RAW else None


def _netloc(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    port = p.port
    return f"{host}:{port}" if port else host


def _is_allowed(url: str) -> bool:
    return _netloc(url) in ALLOWED


def _is_recordable(url: str) -> bool:
    return _netloc(url) in CORPUS_ORIGINS


def _links_from(body: bytes, page_url: str) -> list[str]:
    """Outbound links of an HTML page, resolved against it. Best effort."""
    if not body or b"<a" not in body[:200_000].lower():
        return []
    try:
        from bs4 import BeautifulSoup

        from integrations.search_shim.backend import _navigable_links
        soup = BeautifulSoup(body.decode("utf-8", "replace"), "html.parser")
        return _navigable_links(soup, page_url)
    except Exception:
        return []


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, bytes] | None:
    """Parse an absolute-form request line: `GET http://host:port/path HTTP/1.1`."""
    line = await reader.readline()
    if not line:
        return None
    try:
        method, target, _ = line.decode("latin1").split(" ", 2)
    except ValueError:
        return None
    headers = bytearray()
    while True:
        h = await reader.readline()
        if not h or h in (b"\r\n", b"\n"):
            break
        headers += h
    return method, target, bytes(headers)


def _strip_hop_headers(raw: bytes) -> bytes:
    """Drop proxy-only headers before forwarding to the origin."""
    drop = (b"proxy-connection:", b"proxy-authorization:", b"connection:")
    out = bytearray()
    for line in raw.split(b"\r\n"):
        if not line:
            continue
        if line.lower().startswith(drop):
            continue
        out += line + b"\r\n"
    return bytes(out)


def _is_chunked(headers: bytes) -> bool:
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"transfer-encoding:") and b"chunked" in line.lower():
            return True
    return False


async def _read_body(reader: asyncio.StreamReader, headers: bytes) -> bytes:
    """Body by Content-Length. Chunked request bodies are not supported and must
    not be silently truncated: `_handle` refuses them with 411 instead, because a
    half-forwarded body is a corrupted request the origin may still act on."""
    n = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try:
                n = int(line.split(b":", 1)[1])
            except Exception:
                n = 0
    return await reader.readexactly(n) if n else b""


async def _control(target: str, method: str, body: bytes,
                   writer: asyncio.StreamWriter) -> None:
    """`POST /_mark` and `GET /healthz`, so the harness can bracket this door."""
    import json as _json

    def _reply(code: int, payload: dict) -> None:
        raw = _json.dumps(payload).encode()
        writer.write(f"HTTP/1.1 {code} .\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(raw)}\r\n\r\n".encode("latin1"))
        writer.write(raw)

    path = target.split("?", 1)[0]
    if path == "/healthz":
        ctx = evidence.active()
        _reply(200, {"ok": True, "active_run": ctx.run_id if ctx else None,
                     "recording": evidence.enabled(),
                     "server_merge": CANONICAL_EVIDENCE_DIR is not None,
                     "counters": evidence.counters()})
        await writer.drain()
        return

    if path != "/_mark" or method.upper() != "POST":
        _reply(404, {"error": "not_found"})
        await writer.drain()
        return

    try:
        payload = _json.loads(body or b"{}")
    except Exception:
        _reply(400, {"error": "bad_json"})
        await writer.drain()
        return
    if not isinstance(payload, dict):
        _reply(400, {"error": "body_must_be_object"})
        await writer.drain()
        return

    phase = str(payload.get("phase") or "start").lower()
    if phase not in {"start", "end"}:
        _reply(400, {"error": "phase_must_be_start_or_end"})
        await writer.drain()
        return
    try:
        if phase == "end":
            # Closing is an ownership operation, not a cleanup hint.  An empty,
            # stale, or sibling end marker must never clear another run's
            # evidence bracket.
            run_id = str(payload.get("run_id") or "").strip()
            if not run_id:
                _reply(400, {"error": "run_id_required_for_end"})
                await writer.drain()
                return
            active = evidence.active()
            if active is None or active.run_id != run_id:
                open_id = active.run_id if active else None
                _reply(409, {"error": "run_owner_mismatch",
                             "requested": run_id, "active_run": open_id})
                await writer.drain()
                return
            result = evidence.mark_end(payload)
            if CANONICAL_EVIDENCE_DIR is not None:
                try:
                    result["merge"] = merge_egress_evidence(
                        run_id,
                        egress_dir=evidence.evidence_dir(),
                        unified_dir=CANONICAL_EVIDENCE_DIR,
                    )
                    result["merge"]["mode"] = "recorder"
                except Exception as exc:  # noqa: BLE001
                    # The bracket is already closed. Returning a hard failure
                    # makes the lane an infrastructure abort rather than a
                    # fetch-observable run with missing canonical evidence.
                    _reply(500, {
                        "error": "privileged_evidence_merge_failed",
                        "run_id": run_id,
                        "message": f"{type(exc).__name__}: {exc}",
                    })
                    await writer.drain()
                    return
            _reply(200, result)
        else:
            ctx = evidence.mark_start(payload)
            _reply(200, {"ok": True, "run_id": ctx.run_id})
    except evidence.RunAlreadyActive as e:
        _reply(409, {"error": "run_already_active", "message": str(e)})
    except ValueError as e:
        _reply(400, {"error": str(e)})
    await writer.drain()


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        req = await _read_request(reader)
        if req is None:
            return
        method, target, headers = req

        if method.upper() == "CONNECT":
            # https to a sandbox that speaks http only. Refusing keeps the proxy
            # from becoming an opaque tunnel we cannot record through.
            evidence.record_block(target, "/egress", "connect_tunnel_refused")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        if target.startswith("/"):
            # Control plane. The proxy is a SEPARATE PROCESS, so the run bracket
            # opened on the shim is invisible here: `evidence._ACTIVE` is
            # per-process. Without this endpoint every page read this door serves
            # lands in `_unattributed.jsonl` with `run_id: null`, the scorer sees
            # FETCHED = {} for every lane, and `pof` reads 0 while
            # `hallucinated_grounding` reads 1. That is a false accusation of
            # fabrication against a lane that opened every page it cites.
            #
            # The harness brackets this door exactly as it brackets the shim and
            # ds_proxy.
            body = await _read_body(reader, headers)
            await _control(target, method, body, writer)
            return

        if not target.startswith("http://"):
            writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        if not _is_allowed(target):
            evidence.record_block(target, "/egress", "non_sandbox_url_blocked")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        if _is_chunked(headers):
            writer.write(b"HTTP/1.1 411 Length Required\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        p = urlparse(target)
        host, port = p.hostname, p.port or 80
        path = p.path + (f"?{p.query}" if p.query else "")

        recordable = _is_recordable(target)
        try:
            up_r, up_w = await asyncio.open_connection(host, port)
        except Exception as e:  # noqa: BLE001
            if recordable:
                evidence.record_fetch(target, 0, b"", endpoint="/egress",
                                      error=f"{type(e).__name__}: {e}")
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return

        # The request body. A proxy that forwards the head and drops the body
        # leaves the origin blocked on `Content-Length` bytes that never arrive,
        # so the client times out. The shim's own `/search` is a POST, so with
        # `http_proxy` exported every search in every lane would hang.
        try:
            body_out = await asyncio.wait_for(_read_body(reader, headers), timeout=30)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            body_out = b""

        up_w.write(f"{method} {path} HTTP/1.1\r\n".encode("latin1"))
        up_w.write(_strip_hop_headers(headers))
        up_w.write(b"Connection: close\r\n\r\n")
        if body_out:
            up_w.write(body_out)
        await up_w.drain()

        # An origin that ignores `Connection: close` and keeps the socket open
        # would hang this read forever, and with it the agent's request. The
        # sandbox services honour it, but a proxy that trusts the origin to be
        # well behaved is a proxy that can wedge a whole run.
        try:
            raw = await asyncio.wait_for(up_r.read(), timeout=UPSTREAM_READ_TIMEOUT)
        except asyncio.TimeoutError:
            if recordable:
                evidence.record_fetch(
                    target, 0, b"", endpoint="/egress",
                    error=f"upstream read timeout after {UPSTREAM_READ_TIMEOUT}s",
                )
            up_w.close()
            writer.write(b"HTTP/1.1 504 Gateway Timeout\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        up_w.close()

        # Split the response so the body can be content-addressed. The status is
        # what decides `fetched_ok`, so it must come from the wire, not a guess.
        head, _, body = raw.partition(b"\r\n\r\n")
        status = 0
        try:
            status = int(head.split(b" ", 2)[1])
        except Exception:
            pass
        # Stamp the page's outbound links. A citation the agent reached by
        # following a link from a page it read is honest navigation, and
        # `fetch_log.classify_provenance` calls it `linked`. Without this the
        # same citation is `guessed`, which reads as fabrication. The shim's
        # /extract already does this; the door must not be weaker than the shim.
        if recordable:
            evidence.record_fetch(
                target, status, body[:MAX_BODY], endpoint="/egress",
                links=_links_from(body[:MAX_BODY], target),
            )

        writer.write(raw)
        await writer.drain()
    except Exception:
        # A proxy that dies on a malformed request takes the run with it.
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def serve(host: str, port: int) -> None:
    server = await asyncio.start_server(_handle, host, port)
    bound = server.sockets[0].getsockname() if server.sockets else (host, port)
    print(f"[egress] recording proxy on {bound[0]}:{bound[1]}; "
          f"corpus={sorted(CORPUS_ORIGINS)}; services={sorted(SERVICE_ORIGINS)}")
    print(f"[egress] evidence dir: {evidence.evidence_dir()}")
    print(f"[egress] canonical merge dir: {CANONICAL_EVIDENCE_DIR}")
    async with server:
        await server.serve_forever()


def proxy_env(url: str | None = None) -> dict[str, str]:
    """The env a lane's subprocess needs so its HTTP client uses this door.

    All four clients in the field honour these: requests, httpx (trust_env),
    aiohttp (trust_env=True), and curl. `no_proxy` must NOT contain localhost,
    which is the default some images ship, or the sandbox origins go direct.
    """
    url = url or os.environ.get("DRA_EGRESS_PROXY", "http://127.0.0.1:8099")
    # Set every conventional spelling.  In particular, do not put ds_proxy or
    # the shim in NO_PROXY: they are explicit SERVICE_ORIGINS and pass through
    # this door without being recorded.  A localhost exception would also let
    # corpus pages take the same direct path and make transport evidence blind.
    return {
        "http_proxy": url, "HTTP_PROXY": url,
        "https_proxy": url, "HTTPS_PROXY": url,
        "all_proxy": url, "ALL_PROXY": url,
        "no_proxy": "", "NO_PROXY": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    try:
        asyncio.run(serve(args.host, args.port))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
