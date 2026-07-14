#!/usr/bin/env python3
"""Refuse to start a scored run unless the instruments are provably alive.

`shim_search_delta` read 0 on all 312 runs of the 13-task subset. Nothing
failed. Nothing warned. The counter was simply never written, so "no agent ever
searched the sandbox" and "we never recorded that any agent searched the
sandbox" produced identical data, and the second one went unnoticed until the
scores had already been published.

This is the check that would have caught it. It is fail-closed: a non-zero exit
means do not run.

    python3 scripts/preflight.py --canary       # instrument liveness (no network)
    python3 scripts/preflight.py --parity       # lane protocol conformance
    python3 scripts/preflight.py --all          # everything runnable here
    python3 scripts/preflight.py --production   # no required check may skip

Checks that can only run on the box (model identity probes, the assertion that
a worker cannot reach the sandbox origins directly) are listed by `--all` as
SKIPPED with the reason, never silently passed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CheckResult:
    def __init__(self, name: str, ok: bool | None, detail: str,
                 *, required_in_production: bool = False) -> None:
        self.name = name
        self.ok = ok           # None => skipped
        self.detail = detail
        self.required_in_production = required_in_production

    def __str__(self) -> str:
        tag = "PASS" if self.ok else ("SKIP" if self.ok is None else "FAIL")
        return f"[{tag}] {self.name}: {self.detail}"


@contextlib.contextmanager
def _preserved_environ(*names: str):
    """Restore both present values and absent keys after an invasive canary."""
    before = {name: os.environ.get(name) for name in names}
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _free_tcp_port() -> int:
    """Ask the kernel for a port instead of sharing fixed pytest/preflight ports."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _required(results: list[CheckResult]) -> list[CheckResult]:
    for result in results:
        result.required_in_production = True
    return results


def _check_canary_impl() -> list[CheckResult]:
    """Drive the shim's evidence recorder with a scripted agent and assert the
    log says exactly what the agent did.

    The fake agent searches twice, fetches one of the returned URLs, and cites a
    second URL it never fetched. A correct instrument must be able to tell those
    two citations apart. An instrument that cannot is the one we shipped.
    """
    from fastapi.testclient import TestClient

    results: list[CheckResult] = []
    with tempfile.TemporaryDirectory(prefix="dra_canary_") as tmp:
        os.environ["SHIM_EVIDENCE_DIR"] = tmp
        os.environ["SHIM_EVIDENCE"] = "1"

        from integrations.search_shim import evidence
        evidence.reset_for_tests()

        # Record directly against the recorder: the canary asserts the evidence
        # layer, not the sandbox services (which may not be up on this host).
        evidence.mark_start({"run_id": "canary-1", "lane": "canary",
                             "task": "t0", "backbone": "none"})

        # Reentrancy must be refused, or two concurrent workers silently merge.
        reentrant_refused = False
        try:
            evidence.mark_start({"run_id": "canary-2"})
        except evidence.RunAlreadyActive:
            reentrant_refused = True
        results.append(CheckResult(
            "shim/_mark refuses reentrant start", reentrant_refused,
            "409 on a second open run" if reentrant_refused
            else "a second run was accepted; two workers would interleave"))

        u_fetched = "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee"
        u_cited_not_fetched = "http://localhost:7770/p/12345"
        u_guessed = "http://localhost:7770/p/does-not-exist"

        evidence.record_search("coffee", [u_fetched, u_cited_not_fetched], endpoint="/search")
        evidence.record_search("coffee roasting", [u_fetched], endpoint="/search")
        evidence.record_fetch(u_fetched, 200, b"Coffee is a beverage.", endpoint="/fetch")

        evidence.mark_end({"run_id": "canary-1"})

        log = Path(tmp) / "canary-1.jsonl"
        if not log.exists():
            results.append(CheckResult("evidence log written", False,
                                       f"no {log.name}; the recorder is not writing"))
            return results

        from src.eval.fetch_log import load_run_evidence, transport_metrics
        ev = load_run_evidence(log)

        n_search = len(ev.searches)
        n_fetch = len(ev.fetched)
        ok_counts = (n_search == 2 and n_fetch == 1)
        results.append(CheckResult(
            "evidence log counts match the agent's actions", ok_counts,
            f"searches={n_search} (want 2), fetches={n_fetch} (want 1)"))

        ok_runid = ev.run_id == "canary-1" and ev.lane == "canary"
        results.append(CheckResult("records carry run identity", ok_runid,
                                   f"run_id={ev.run_id!r} lane={ev.lane!r}"))

        # Registry stand-in: the two localhost:7770 pages "exist" except the
        # guessed one, so the three provenance classes are all exercised.
        real = {u_fetched, u_cited_not_fetched}
        m = transport_metrics([u_fetched, u_cited_not_fetched, u_guessed], ev,
                              in_registry=lambda u: u in real)

        ok_pof = abs(m["pof"] - 1 / 3) < 1e-9
        results.append(CheckResult(
            "pof counts only pages actually fetched", ok_pof,
            f"pof={m['pof']:.4f} (want 1/3: one of three cited URLs was fetched)"))

        # The un-opened page WAS returned by a search, so it is a snippet-only
        # citation, not parametric recall. A framework with no page-read step can
        # produce nothing else, and charging it with answering from memory would
        # be a false accusation.
        ok_snip = abs(m["snippet_only"] - 1 / 3) < 1e-9
        results.append(CheckResult(
            "snippet_only catches cite-from-search-result", ok_snip,
            f"={m['snippet_only']:.4f} (want 1/3: real page, searched, never opened)"))

        ok_hall = abs(m["hallucinated_grounding"] - 0.0) < 1e-9
        results.append(CheckResult(
            "hallucinated_grounding does NOT fire on a searched page", ok_hall,
            f"={m['hallucinated_grounding']:.4f} (want 0: nothing here came from memory)"))

        ok_fab = abs(m["fabrication"] - 1 / 3) < 1e-9
        results.append(CheckResult("fabrication catches the invented URL", ok_fab,
                                   f"={m['fabrication']:.4f} (want 1/3)"))

        counts = m["provenance_counts"]
        ok_prov = counts == {"searched": 2, "linked": 0, "guessed": 1}
        results.append(CheckResult("url_provenance separates searched from guessed",
                                   ok_prov, json.dumps(counts)))

        blob = evidence.load_blob(ev.blob_digest(u_fetched) or "")
        ok_blob = blob == b"Coffee is a beverage."
        results.append(CheckResult(
            "served bytes are content-addressed and readable", ok_blob,
            "scorer can read what the agent was shown without re-fetching"
            if ok_blob else "blob missing; scoring would have to re-fetch"))

    return results


def check_canary() -> list[CheckResult]:
    with _preserved_environ("SHIM_EVIDENCE_DIR", "SHIM_EVIDENCE"):
        return _check_canary_impl()


def check_manifest() -> list[CheckResult]:
    """The run manifest is the only thing tying a leaderboard number to the code
    that produced it. This asserts the machinery is honest without any network:
    it must record the CURRENT host, and verify() must refuse a manifest that
    claims a different host or carries no commit. The real per-run manifest can
    only be generated on the box, so that stays a box-only SKIP; this proves the
    guard itself works here.
    """
    from scripts import run_manifest as rm

    results: list[CheckResult] = []
    m = rm.generate(ROOT, env={})

    ok_host = m.get("host", {}).get("hostname") == __import__("socket").gethostname()
    results.append(CheckResult(
        "manifest records the host it was generated on", ok_host,
        f"host={m.get('host', {}).get('hostname')!r} (a workstation-generated "
        f"manifest cannot masquerade as box-native)"))

    with tempfile.TemporaryDirectory(prefix="dra_manifest_") as tmp:
        (Path(tmp) / "r.md").write_text("x")
        wrong = rm.verify(m, tmp, hostname="not-this-host", root=ROOT)
        ok_reject = any("generated on host" in v for v in wrong)
        results.append(CheckResult(
            "verify refuses a manifest from another host", ok_reject,
            "hostname mismatch is a listed violation" if ok_reject
            else "a foreign-host manifest was accepted"))

        no_commit = dict(m)
        no_commit["git"] = {**m.get("git", {}), "commit": None}
        ok_nc = any("no git commit" in v for v in
                    rm.verify(no_commit, tmp, hostname=m["host"]["hostname"], root=ROOT))
        results.append(CheckResult(
            "verify refuses a manifest with no commit", ok_nc,
            "the exact 16-column-TSV defect is fail-closed" if ok_nc
            else "a commit-less manifest was accepted"))

    return results


def check_sandbox_hosts_agree() -> list[CheckResult]:
    """Every host the task text names must be a host the registry knows.

    `_resolve_intent` substitutes `__SHOPPING__` into the task before the agent
    sees it. Its default was `http://localhost:17770`. The URL registry, the
    shim's allowlist, and the shim's own store scraper all say `localhost:7770`,
    and `url_registry.classify("http://localhost:17770/...")` returns
    `host_not_in_sandbox`, which the scorer counts as FABRICATED.

    So 102 of 103 tasks pointed the agent at a store, and then the scorer
    punished it for citing that store. Whether the benchmark was valid depended
    on the box exporting SHOPPING correctly, and nothing checked. Across the 140
    scored reports of the 13-task subset there is not one citation of the store
    on any port, and `fact` (which grades store price and rating claims) read
    zero on 99% of them.

    This check is pure configuration. It needs no sandbox and no network.
    """
    import os

    from src.eval.closed_world_eval import load_registry

    results: list[CheckResult] = []
    registry = load_registry()
    if registry is None:
        return [CheckResult("sandbox hosts agree", None,
                            "no url_registry.json; cannot check")]

    named = {
        "__SHOPPING__": os.environ.get("SHOPPING", "http://localhost:7770"),
        "__REDDIT__": os.environ.get("REDDIT", "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    bad = []
    for placeholder, base in named.items():
        probe = base.rstrip("/") + "/probe"
        d = registry.classify(probe)
        if d.get("reason") == "host_not_in_sandbox":
            bad.append(f"{placeholder} -> {base} (registry: off-sandbox, cited => fabricated)")
    ok = not bad
    results.append(CheckResult(
        "task text names only hosts the registry knows", ok,
        "shopping/forum/wiki hosts agree with the registry" if ok
        else "; ".join(bad)))
    return results


def check_egress_captures_every_transport() -> list[CheckResult]:
    """Every HTTP client a lane might use must reach the sandbox through the door.

    `_install_inproc_sandbox_gate` patches `requests`. Eight of twelve lanes read
    pages with something else: `aiohttp` (qx-agents), `curl` (claude-code, codex,
    gemini-cli), or `httpx`. Those reads left no trace, so `proof_of_fetch` was
    withheld for them rather than guessed at.

    All four honour `http_proxy`. This drives each one at a live recording proxy
    and asserts the fetch landed in the run's evidence log. A transport that
    escapes here is a lane whose citations we cannot check, so it fails closed.
    """
    import http.client
    import http.server
    import socketserver
    import subprocess as _sub
    import threading
    import time as _time

    results: list[CheckResult] = []
    page = b"<html>ok</html>"

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *a):
            pass

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    try:
        site = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _H)
    except OSError as e:
        return [CheckResult(
            "egress door captures every transport", None,
            f"cannot bind probe site: {e}", required_in_production=True,
        )]
    threading.Thread(target=site.serve_forever, daemon=True).start()
    site_port = int(site.server_address[1])
    proxy_port = _free_tcp_port()

    import integrations.egress_proxy.app as eg
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    url = f"http://localhost:{site_port}/probe"
    proxy_keys = tuple(eg.proxy_env(proxy_url))
    changed_env = (*proxy_keys, "SHIM_EVIDENCE_DIR", "SHIM_EVIDENCE",
                   "DRA_EGRESS_CORPUS", "DRA_EGRESS_SERVICES",
                   "DRA_EGRESS_ALLOWED")

    proc = None
    try:
        with tempfile.TemporaryDirectory(prefix="dra_egress_") as tmp, \
                _preserved_environ(*changed_env):
            child_env = dict(os.environ)
            child_env.update({
                "SHIM_EVIDENCE_DIR": tmp,
                "SHIM_EVIDENCE": "1",
                "DRA_EGRESS_CORPUS": (
                    f"127.0.0.1:{site_port},localhost:{site_port}"
                ),
                # Keep the canary independent of a caller's service topology.
                "DRA_EGRESS_SERVICES": "127.0.0.1:1",
            })
            child_env.pop("DRA_EGRESS_ALLOWED", None)
            child_env["PYTHONPATH"] = (
                str(ROOT) + os.pathsep + child_env.get("PYTHONPATH", "")
            ).rstrip(os.pathsep)
            proc = _sub.Popen(
                [sys.executable, "-m", "integrations.egress_proxy.app",
                 "--host", "127.0.0.1", "--port", str(proxy_port)],
                cwd=ROOT, env=child_env, stdout=_sub.DEVNULL,
                stderr=_sub.DEVNULL,
            )

            def _control(method: str, path: str, payload: dict | None = None):
                raw = json.dumps(payload).encode() if payload is not None else None
                headers = ({"Content-Type": "application/json"} if raw else {})
                conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=2)
                try:
                    conn.request(method, path, body=raw, headers=headers)
                    response = conn.getresponse()
                    body = response.read()
                    return response.status, body
                finally:
                    conn.close()

            # Importing the composite supervisor environment is measurably
            # slower on WSL's /opt filesystem than on the workstation. Five
            # seconds produced a false negative while the child was alive and
            # still importing; this is startup allowance, not request timeout.
            deadline = _time.monotonic() + 20
            while True:
                try:
                    if _control("GET", "/healthz")[0] == 200:
                        break
                except Exception:
                    pass
                if proc.poll() is not None or _time.monotonic() >= deadline:
                    return [CheckResult(
                        "egress door captures every transport", False,
                        f"recording proxy did not start (exit={proc.poll()})",
                        required_in_production=True,
                    )]
                _time.sleep(0.05)

            for key, value in eg.proxy_env(proxy_url).items():
                os.environ[key] = value
            os.environ["SHIM_EVIDENCE_DIR"] = tmp
            os.environ["SHIM_EVIDENCE"] = "1"

            def _one(name: str, call) -> None:
                run_id = f"preflight-{name}"
                err = None
                opened = False
                try:
                    status, _ = _control("POST", "/_mark", {
                        "run_id": run_id, "lane": "preflight", "task": "t",
                        "backbone": "n/a", "phase": "start",
                    })
                    if status != 200:
                        raise RuntimeError(f"/_mark start returned {status}")
                    opened = True
                    call()
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"
                finally:
                    if opened:
                        status, _ = _control(
                            "POST", "/_mark",
                            {"run_id": run_id, "phase": "end"},
                        )
                        if status != 200 and err is None:
                            err = f"/_mark end returned {status}"

                from src.eval.fetch_log import load_run_evidence
                try:
                    evidence = load_run_evidence(Path(tmp) / f"{run_id}.jsonl")
                    fetched = bool(evidence.fetched)
                except Exception as e:  # noqa: BLE001
                    fetched = False
                    err = err or f"cannot read evidence: {e}"
                ok = fetched and err is None
                results.append(CheckResult(
                    f"egress door records {name}", ok,
                    "fetch recorded by the out-of-process door" if ok
                    else (err or "the read never reached the door; this lane's "
                                 "proof_of_fetch would be unmeasurable"),
                    required_in_production=True,
                ))

            def _requests():
                import requests
                response = requests.get(url, timeout=5)
                response.raise_for_status()

            def _httpx():
                import httpx
                response = httpx.get(url, timeout=5, trust_env=True)
                response.raise_for_status()

            def _aiohttp():
                import asyncio
                import aiohttp

                async def go():
                    async with aiohttp.ClientSession(trust_env=True) as session:
                        async with session.get(url) as response:
                            if response.status != 200:
                                raise RuntimeError(f"aiohttp got {response.status}")
                            await response.read()

                asyncio.run(go())

            def _curl():
                response = _sub.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                    capture_output=True, text=True, timeout=10,
                )
                if response.stdout.strip() != "200":
                    raise RuntimeError(f"curl got {response.stdout.strip()!r}")

            for name, call in (("requests", _requests), ("httpx", _httpx),
                               ("aiohttp", _aiohttp), ("curl", _curl)):
                _one(name, call)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except _sub.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        site.shutdown()
        site.server_close()
    return results


def check_sources_alive() -> list[CheckResult]:
    """Each of the three sandbox sources must answer a canned query with hits.

    `_search_shopping` returned `[]` on a 4xx, on a timeout, and on a selector
    that stopped matching, so a dead store and a store with no match for this
    query produced identical data. The store was unreachable for at least two
    scored runs. Across 495 archived reports it was cited twice; across the 140
    reports of the 13-task subset, never. `fact` grades store price claims, so
    it read zero on 99% of reports, and that was written off as the cost of
    decidable scoring. It was a connection error.

    Absence must produce a signal. This check is the signal.
    """
    from integrations.search_shim import backend

    results: list[CheckResult] = []
    backend.search("headphones", max_results=5)
    diag = backend.last_source_diag()
    if not diag:
        return [CheckResult("sandbox sources answer a canned query", None,
                            "backend reported no diagnostics; sandbox not queried")]

    down = [f"{src}: {d['error'] or 'zero hits'}"
            for src, d in sorted(diag.items()) if not d["n_results"]]
    if len(down) == len(diag):
        # Nothing is up. On the workstation that is expected, not a failure.
        return [CheckResult("sandbox sources answer a canned query", None,
                            "no sandbox on this host; must run where the sites are up")]
    ok = not down
    return [CheckResult(
        "sandbox sources answer a canned query", ok,
        ", ".join(f"{s}={d['n_results']}" for s, d in sorted(diag.items())) if ok
        else "SOME SOURCES ARE DEAD while others answer: " + "; ".join(down))]


def check_search_hits_are_in_corpus() -> list[CheckResult]:
    """The search tool must never hand the agent a URL the scorer calls fabricated.

    A source emits links at the origin it knows itself by. On the box the store's
    base_url is `localhost:17770` (the teardown ports of
    `infra/sandbox.verify.docker-compose.yml`) while `url_registry`, the release
    compose, and `MAGENTO_BASE_URL` all say 7770. So `catalogsearch` hands the
    agent `http://localhost:17770/<product>.html`, and
    `registry.classify` returns `host_not_in_sandbox`, which the scorer counts as
    FABRICATED. An agent that cites exactly what the tool showed it is recorded as
    having made it up.

    Checking whether the store redirects is not enough: a reverse proxy in front
    of it answers without a redirect while the pages still carry base_url links.
    The invariant is end-to-end and holds for every source: classify what the
    agent actually receives.
    """
    from integrations.search_shim import backend
    from src.eval.closed_world_eval import load_registry

    name = "search hits are in-corpus"
    registry = load_registry()
    if registry is None:
        return [CheckResult(name, None, "no url_registry.json; cannot check")]

    try:
        hits = backend.search("headphones", max_results=6)
    except Exception as e:  # noqa: BLE001
        return [CheckResult(name, None, f"sandbox not queryable ({e}); "
                                        "must run where the sites are up")]
    if not hits:
        return [CheckResult(name, None, "no sandbox on this host; "
                                        "must run where the sites are up")]

    # A source that contributes no hit contributes no URL to classify, and the
    # loop below would then report "all in-corpus" -- a clean instrument reading
    # for the exact failure this check was written after. Only skip when the
    # whole sandbox is absent (workstation); a partial answer is a failure.
    diag = backend.last_source_diag()
    silent = [s for s in ("shopping", "forum", "wiki")
              if not (diag.get(s) or {}).get("n_results")]
    if len(silent) == 3:
        return [CheckResult(name, None, "no sandbox on this host; "
                                        "must run where the sites are up")]
    if silent:
        return [CheckResult(name, False,
            f"source(s) {silent} returned no URL to classify while the others "
            "answered. Absence of a source cannot be certified in-corpus.")]

    bad = []
    for h in hits:
        c = registry.classify(h.url)
        if not c.get("in_corpus"):
            bad.append(f"{h.url} -> {c.get('reason')}")
    if not bad:
        return [CheckResult(name, True, f"{len(hits)} hits, all in-corpus")]
    return [CheckResult(
        name, False,
        f"{len(bad)}/{len(hits)} hits would be scored FABRICATED if cited: "
        + "; ".join(bad[:3])
        + ". The source emits links at an origin url_registry does not list. "
          "Align the site's base_url with the registry hosts.")]


def check_backbone_sampling() -> list[CheckResult]:
    """Both proxies stamp the declared sampler, and `thinking` matches its declaration.

    `lane_protocol.yaml` said the backbone knobs "must be identical across lanes
    AND across backbones" and named the proxy as the enforcement point. Neither
    proxy enforced anything. storm ran every stage at 0.7 while holding #1 on the
    qwen board, costorm passed `top_p=0.9`, and a lane that sends no temperature
    inherits the upstream default.

    Enforcing it in one proxy is not enough: `run_deep_task._setup_ds_backbone`
    points ELEVEN lanes at ds_proxy (:8088) and only claude-code at llm_gateway
    (:8100).

    `thinking` is a maintainer decision (glm stays ON per 2026-07-06), so it is
    not forced. It is DECLARED, and this asserts the code says what the protocol
    says, which turns a silent cross-backbone confound into a written one.
    """
    from integrations import sampling_policy as sp
    from integrations.ds_proxy import app as dsp
    from integrations.llm_gateway import app as gw

    results: list[CheckResult] = []
    t, p = sp.forced_temperature(), sp.forced_top_p()
    if t is None or p is None:
        return [CheckResult("backbone sampling is declared", False,
                            f"lane_protocol declares temperature={t} top_p={p}; "
                            "both must be set for lanes to be comparable")]

    for name, apply in (("ds_proxy (11 lanes)", lambda b: sp.apply_sampling(b)),
                        ("llm_gateway (claude-code)",
                         lambda b: gw._apply_policy({"thinking_off": False}, b))):
        body = {"model": "qwen3-8b", "temperature": 0.7, "top_p": 0.9}
        apply(body)
        ok = body.get("temperature") == t and body.get("top_p") == p
        results.append(CheckResult(
            f"{name} forces the declared sampler", ok,
            f"temperature={body.get('temperature')} top_p={body.get('top_p')} "
            f"(want {t}/{p})"))

    # The output-token budget is a scored quantity's input: report length feeds
    # completeness (0.33 of quality weight). The protocol declared 8192
    # "identical" while the gateway capped qwen, left deepseek uncapped, and
    # raised glm 16x. Assert the declared ceiling (with its DECLARED exceptions)
    # is what each backbone actually gets through the gateway door.
    for model in ("qwen3-8b", "deepseek-v4-flash", "glm-4.7-flash"):
        want = sp.max_output_tokens_for(model)
        entry = gw._match_entry(model) or {}
        body = {"model": model, "max_tokens": 999_999}
        gw._apply_policy(entry, body)
        got = body.get("max_tokens")
        results.append(CheckResult(
            f"max_tokens ceiling enforced for {model}", got == want,
            f"asked 999999, got {got} (declared {want})"))
        empty = {"model": model}
        gw._apply_policy(entry, empty)
        results.append(CheckResult(
            f"absent max_tokens is pinned for {model}", empty.get("max_tokens") is not None,
            f"a lane sending nothing must not inherit the upstream default "
            f"(got {empty.get('max_tokens')})"))

    # The declaration must describe the code, not an aspiration.
    decl = sp.declared_thinking()
    per = {k: str(v).lower() for k, v in (decl.get("per_backbone") or {}).items()}
    actual = {prefix: ("off" if dsp._needs_thinking_off(prefix) else "on")
              for prefix in per}
    matches = per == actual
    results.append(CheckResult(
        "thinking matches its declaration", matches,
        f"declared={per} actual={actual}"
        + ("" if matches else "; ds_proxy._needs_thinking_off disagrees with "
                              "config/lane_protocol.yaml")))

    if not decl.get("uniform", False):
        results.append(CheckResult(
            "thinking is uniform across backbones", None,
            "DECLARED NON-UNIFORM: " + f"{per}. Single-backbone boards are fine; "
            "a cross-backbone truth comparison is confounded until a maintainer "
            "equalises this. Disclosed in config/lane_protocol.yaml."))
    return results


def check_parity() -> list[CheckResult]:
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_parity.py")],
                          capture_output=True, text=True)
    ok = proc.returncode == 0
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    return [CheckResult("lane protocol parity", ok,
                        detail[0] if detail else f"exit {proc.returncode}")]


def check_disclosure() -> list[CheckResult]:
    """Every lane difference is declared so the board can footnote it (G0).

    A green parity check proves no lane re-introduced a forbidden steer; this
    proves no lane differs from the shared protocol WITHOUT saying so (off-shim
    fetch withhold, a swapped retriever, a truncated context). Undeclared
    difference => the comparison silently stops being apples-to-apples."""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_disclosure.py")],
                          capture_output=True, text=True)
    ok = proc.returncode == 0
    out = (proc.stdout or proc.stderr).strip().splitlines()
    return [CheckResult("lane difference disclosure", ok,
                        out[0] if out else f"exit {proc.returncode}")]


def check_no_refetch_at_scoring() -> list[CheckResult]:
    """The scorer must never open a socket. If it can, a URL the model invented
    but which happens to exist gets fetched at scoring time and counted as
    grounded."""
    from src.verifiers import sandbox_http_cache as shc
    ok = getattr(shc, "STRICT_NO_REFETCH", False)
    return [CheckResult(
        "scoring never re-fetches on cache miss", bool(ok),
        "sandbox_http_cache.STRICT_NO_REFETCH is on" if ok
        else "a cache miss would issue a live HTTP request during scoring")]


def _check_bracket_self_heal_impl() -> list[CheckResult]:
    """A run killed without posting mark_end (timeout SIGTERM / watchdog os._exit
    / SIGKILL) leaves the shim's bracket open. Assert the NEXT run reclaims the
    orphaned bracket instead of 409-ing forever (which would brick the queue),
    while a still-live bracket is still protected."""
    results: list[CheckResult] = []
    from integrations.search_shim import evidence

    old_ttl = os.environ.get("SHIM_BRACKET_TTL_S")
    try:
        with tempfile.TemporaryDirectory(prefix="dra_wedge_") as tmp:
            os.environ["SHIM_EVIDENCE_DIR"] = tmp
            os.environ["SHIM_EVIDENCE"] = "1"

            # Live bracket must still 409 a concurrent different run.
            os.environ["SHIM_BRACKET_TTL_S"] = "3600"
            evidence.reset_for_tests()
            evidence.mark_start({"run_id": "wedge-live", "lane": "canary"})
            still_409 = False
            try:
                evidence.mark_start({"run_id": "wedge-intruder"})
            except evidence.RunAlreadyActive:
                still_409 = True
            results.append(CheckResult(
                "live bracket still 409s a concurrent run", still_409,
                "attribution protected while the owner is live" if still_409
                else "a live bracket was stolen; concurrent traffic would misattribute"))

            # Orphaned (idle past TTL) bracket must be reclaimed, not refused.
            os.environ["SHIM_BRACKET_TTL_S"] = "0"
            evidence.reset_for_tests()
            evidence.mark_start({"run_id": "wedge-dead", "lane": "canary"})
            reclaimed = False
            try:
                ctx = evidence.mark_start({"run_id": "wedge-next"})
                reclaimed = (ctx.run_id == "wedge-next"
                             and evidence.active().run_id == "wedge-next")
            except evidence.RunAlreadyActive:
                reclaimed = False
            results.append(CheckResult(
                "orphaned bracket is reclaimed, not a permanent 409", reclaimed,
                "a killed run no longer bricks the rest of the queue" if reclaimed
                else "a stale bracket 409s forever; one crash halts the batch"))
            evidence.reset_for_tests()
    finally:
        if old_ttl is None:
            os.environ.pop("SHIM_BRACKET_TTL_S", None)
        else:
            os.environ["SHIM_BRACKET_TTL_S"] = old_ttl
    return results


def check_bracket_self_heal() -> list[CheckResult]:
    with _preserved_environ("SHIM_EVIDENCE_DIR", "SHIM_EVIDENCE",
                            "SHIM_BRACKET_TTL_S"):
        return _check_bracket_self_heal_impl()


def check_on_page_link_not_hallucinated() -> list[CheckResult]:
    """A page reached by following an on-page link is honest navigation, not
    parametric recall. Assert a cited URL that only appears in a fetched page's
    stamped `links` (the /extract get_text path strips hrefs) is scored `linked`,
    NOT hallucinated_grounding. This is the X1 false-accusation guard."""
    from src.eval.fetch_log import RunEvidence, transport_metrics, linked_urls, canonical

    page = "http://localhost:8090/A/Sony"
    followed = "http://localhost:8090/A/Walkman"
    ev = RunEvidence(available=True, fetch_observable=True)
    # Fetched the hub page (status 200) whose stamped links include `followed`;
    # the blob is href-free stripped text, exactly what /extract stores.
    ev.fetched[canonical(page)] = {"status": 200, "url": page,
                                   "body_sha256": "d", "links": [followed]}
    linked = linked_urls(ev)  # no blob loader needed: links are on the record
    m = transport_metrics([followed], ev, in_registry=lambda u: True, linked=linked)
    ok = (m.get("hallucinated_grounding") == 0.0
          and m.get("url_provenance", {}).get(canonical(followed)) == "linked")
    return [CheckResult(
        "on-page-link citation scored `linked`, not hallucinated", bool(ok),
        "stamped page links exempt honest navigation from false accusation" if ok
        else f"an on-page-link cite was mis-scored: {json.dumps(m, ensure_ascii=False)}")]


def check_direct_sandbox_bypass(
        origins: set[str] | None = None, *, timeout_s: float = 0.4,
) -> list[CheckResult]:
    """Fail when the worker can open a direct socket to a corpus origin.

    This must run with the same uid/network namespace as the lane subprocess.
    Source liveness is checked separately through the shim, so "everything is
    down" cannot turn connection refusals into a valid production result.
    """
    proof_path = os.environ.get("DRA_ISOLATION_PROOF", "").strip()
    if proof_path:
        try:
            from scripts.production_isolation import load_proof

            proof = load_proof(proof_path)
            worker_probe = proof.get("worker_probe") or {}
            source = proof.get("source_evidence") or {}
            canonical = proof.get("canonical_evidence") or {}
            ok = (
                worker_probe.get("passed") is True
                and not worker_probe.get("network_bypasses")
                and not worker_probe.get("evidence_write_bypasses")
                and not worker_probe.get("hidden_gold_bypasses")
                and not worker_probe.get("filesystem_bypasses")
                and source.get("fetches") == 1
                and canonical.get("merged_fetches") == 1
            )
            return [CheckResult(
                "worker cannot bypass the recording proxy", bool(ok),
                (f"root-owned live worker proof {proof.get('proof_id')} passed "
                 "curl --noproxy, requests trust_env=False, raw socket, "
                 "host/container alias, public network/DNS, positive proxy, "
                 "and evidence-permission probes" if ok else
                 f"isolation proof is incomplete: {proof_path}"),
                required_in_production=True,
            )]
        except Exception as exc:  # noqa: BLE001
            return [CheckResult(
                "worker cannot bypass the recording proxy", False,
                f"invalid DRA_ISOLATION_PROOF: {type(exc).__name__}: {exc}",
                required_in_production=True,
            )]

    if origins is None:
        from integrations.egress_proxy.app import CORPUS_ORIGINS
        origins = set(CORPUS_ORIGINS)
    if not origins:
        return [CheckResult(
            "worker cannot bypass the recording proxy", False,
            "no corpus origins are configured; isolation cannot be tested",
            required_in_production=True,
        )]

    reachable: list[str] = []
    tested: list[str] = []
    for origin in sorted(origins):
        host, sep, raw_port = origin.rpartition(":")
        if not sep or not host:
            return [CheckResult(
                "worker cannot bypass the recording proxy", False,
                f"invalid corpus origin {origin!r}",
                required_in_production=True,
            )]
        try:
            port = int(raw_port)
        except ValueError:
            return [CheckResult(
                "worker cannot bypass the recording proxy", False,
                f"invalid corpus port in {origin!r}",
                required_in_production=True,
            )]
        tested.append(origin)
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                reachable.append(origin)
        except OSError:
            pass

    ok = not reachable
    return [CheckResult(
        "worker cannot bypass the recording proxy", ok,
        (f"direct sockets blocked for {len(tested)} configured corpus origins"
         if ok else "DIRECT BYPASS REACHABLE: " + ", ".join(reachable)
         + ". Run this preflight in the lane's uid/network namespace and do not "
           "score until only the egress-proxy identity can reach these origins."),
        required_in_production=True,
    )]


def check_gates_smoke() -> list[CheckResult]:
    """GOAL_GATES_V1 permanent fixture: the goal-gate tests must be COLLECTIBLE
    and non-empty.

    The seven gates enforce the two leaderboard properties (docs/GOAL_GATES_V1.md).
    A gate file present but with 0 tests is the bad state run_gates now FAILs on
    (rc=5). This check catches that at preflight time without paying for the full
    oracle sweep: it only `--collect-only`s the gate nodes declared in
    run_gates.GATES and asserts collection succeeds and yields > 0 tests. A green
    result here means the gate suite exists and can run; run_full_leaderboard.sh
    additionally runs `run_gates.py --quick` (the real assertions) before a run.
    """
    from scripts.run_gates import GATES

    nodes: list[str] = []
    for _desc, gate_nodes, _skip in GATES.values():
        if gate_nodes:
            nodes.extend(gate_nodes)
    if not nodes:
        return [CheckResult("goal gates are collectible", False,
                            "run_gates.GATES declares no pytest gate nodes")]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--run-gates", *nodes],
        cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # rc 5 == nothing collected. Count node ids robustly (one `::` line each)
    # instead of parsing the version-specific summary line.
    collected = sum(1 for line in out.splitlines() if "::" in line)
    ok = proc.returncode == 0 and collected > 0
    return [CheckResult(
        "goal gates are collectible and non-empty", ok,
        f"{collected} goal-gate tests collectible (run_full_leaderboard.sh runs "
        "run_gates.py --quick before the run)" if ok
        else f"gate collection failed (rc={proc.returncode}, {collected} "
             f"collected); a gate file is missing or empty")]


BOX_ONLY = [
    ("per-lane model identity probe",
     "must run on the box: probes each lane's actual endpoint and asserts the "
     "returned model id equals the declared backbone"),
    ("run manifest generated on the executing host",
     "must run on the box: git commit, dirty tree, env snapshot, corpus hashes"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--parity", action="store_true")
    ap.add_argument("--disclosure", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--production", action="store_true",
                    help="run all checks and fail if any required box check skips")
    args = ap.parse_args()
    if args.production:
        args.all = True
    if not (args.canary or args.parity or args.disclosure or args.manifest
            or args.all or args.production):
        args.all = True

    results: list[CheckResult] = []
    if args.canary or args.all:
        results += check_canary()
    if args.manifest or args.all:
        results += check_manifest()
    if args.parity or args.all:
        results += check_parity()
    if args.disclosure or args.parity or args.all:
        results += check_disclosure()
    if args.canary or args.all:
        results += check_bracket_self_heal()
        results += check_on_page_link_not_hallucinated()
    if args.all:
        results += check_gates_smoke()
        results += _required(check_sandbox_hosts_agree())
        results += _required(check_sources_alive())
        results += _required(check_search_hits_are_in_corpus())
        results += check_backbone_sampling()
        results += check_egress_captures_every_transport()
        results += check_no_refetch_at_scoring()
        if args.production:
            results += check_direct_sandbox_bypass()
        else:
            results.append(CheckResult(
                "worker cannot bypass the recording proxy", None,
                "production-only: must run with the lane's uid/network namespace",
                required_in_production=True,
            ))
        results += [CheckResult(n, None, why, required_in_production=True)
                    for n, why in BOX_ONLY]

    for r in results:
        print(r)

    failed = [r for r in results if r.ok is False]
    skipped = [r for r in results if r.ok is None]
    required_skipped = [r for r in skipped if r.required_in_production]
    print(f"\n{len(results) - len(failed) - len(skipped)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print("\nDO NOT RUN. The instrument is not proven alive.", file=sys.stderr)
        return 1
    if args.production and required_skipped:
        print("\nDO NOT RUN. Production checks skipped: "
              + ", ".join(r.name for r in required_skipped), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
