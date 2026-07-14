#!/usr/bin/env python3
"""Run one formal sandbox task across the maintained harness matrix.

The worker processes are concurrent and retain independent namespaces, search
shims, ds_proxy instances, evidence streams and cost ledgers.  Their ds_proxy
instances share only an advisory upstream admission pool, which protects a
single CLIProxyAPI account from a 12-request startup burst without merging any
worker's attribution stream.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HARNESSES = (
    "camel-ai",
    "claude-code",
    "deerflow",
    "flowsearcher-ds",
    "gpt-researcher",
    "ii-researcher",
    "langchain-odr",
    "ldr",
    "opencode",
    "qx-agents",
    "smolagents",
    "storm",
)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# The host-side services are dialled over loopback, while Magento and the URL
# registry identify the public sandbox as ``localhost``.  Keep transport and
# identity separate: using 127.0.0.1 as Magento's Host triggers a canonical
# 302 and makes the trusted source preflight (correctly) fail.
SANDBOX_SOURCE_ENV = {
    "SHOPPING": "http://127.0.0.1:7770",
    "SHOPPING_PUBLIC": "http://localhost:7770",
    "REDDIT": "http://127.0.0.1:9999",
    "REDDIT_PUBLIC": "http://localhost:9999",
    "KIWIX": "http://127.0.0.1:8090",
    "KIWIX_PUBLIC": "http://localhost:8090",
}


@dataclass
class Lane:
    harness: str
    index: int
    worker_id: int
    run_set_id: str
    queue: Path
    run_dir: Path
    shim_port: int
    dsproxy_port: int
    egress_port: int
    qx_port: int
    shim_log: Path
    dsproxy_log: Path
    worker_log: Path
    usage_log: Path
    shim_proc: subprocess.Popen | None = None
    dsproxy_proc: subprocess.Popen | None = None
    worker_proc: subprocess.Popen | None = None
    handles: list[Any] = field(default_factory=list)
    worker_rc: int | None = None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _read_client_key(path: Path) -> str:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
        raise RuntimeError(f"client env must be a root-owned regular file: {path}")
    if info.st_mode & 0o077:
        raise RuntimeError(f"client env permissions are too broad: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        try:
            parsed = shlex.split(value, posix=True)
        except ValueError as exc:
            raise RuntimeError(f"cannot parse {name} in {path}: {exc}") from exc
        if len(parsed) == 1:
            values[name] = parsed[0]
    for name in ("OPENAI_API_KEY", "CLIPROXY_API_KEY", "DRA_CLIPROXY_API_KEY"):
        if values.get(name):
            return values[name]
    candidates = [value for name, value in values.items() if name.endswith("API_KEY")]
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(f"no unambiguous client API key found in {path}")


def _cliproxy_metadata() -> dict[str, str]:
    binary = Path("/usr/local/bin/cli-proxy-api")
    config = Path("/run/cliproxyapi/config.yaml")
    auth_dir = Path("/etc/cliproxyapi/auths")
    metadata: dict[str, str] = {}
    binary_hash = _sha256_file(binary)
    config_hash = _sha256_file(config)
    if binary_hash:
        metadata["DRA_CLIPROXY_BINARY_SHA256"] = binary_hash
    if config_hash:
        metadata["DRA_CLIPROXY_CONFIG_SHA256"] = config_hash
    auth_hashes = sorted(
        item for item in (_sha256_file(path) for path in auth_dir.glob("*.json"))
        if item
    )
    if auth_hashes:
        metadata["DRA_CLIPROXY_AUTH_COUNT"] = str(len(auth_hashes))
        metadata["DRA_CLIPROXY_AUTH_POOL_SHA256"] = hashlib.sha256(
            "\n".join(auth_hashes).encode()
        ).hexdigest()
    for flag in ("-version", "--version"):
        try:
            result = subprocess.run(
                [str(binary), flag], text=True, capture_output=True, timeout=10,
                check=False,
            )
        except Exception:
            continue
        raw = (result.stdout or result.stderr or "").strip()
        if raw:
            metadata["DRA_CLIPROXY_VERSION"] = "_".join(raw.split())[:300]
            break
    return metadata


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _json_get(url: str, *, key: str | None = None, timeout: float = 10) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    request = urllib.request.Request(url, headers=headers)
    with _opener().open(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError(f"non-object JSON from {url}")
    return value


def _check_api(api_base: str, key: str, model: str) -> None:
    parsed = urllib.parse.urlsplit(api_base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("the credential-bearing smoke endpoint must be loopback HTTP")
    payload = _json_get(api_base.rstrip("/") + "/models", key=key, timeout=20)
    ids = {
        str(row.get("id"))
        for row in payload.get("data", [])
        if isinstance(row, dict) and row.get("id")
    }
    if model not in ids:
        raise RuntimeError(f"model {model!r} is absent from CLIProxyAPI /models")


def _assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"required smoke port {port} is occupied: {exc}") from exc


def _start(
    lane: Lane, argv: list[str], env: dict[str, str], log: Path, role: str,
) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("ab", buffering=0)
    lane.handles.append(handle)
    proc = subprocess.Popen(
        argv,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    if role == "shim":
        lane.shim_proc = proc
    elif role == "dsproxy":
        lane.dsproxy_proc = proc
    elif role == "worker":
        lane.worker_proc = proc
    return proc


def _wait_ready(lane: Lane, role: str, url: str, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + 90
    error = "not attempted"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"{lane.harness} {role} exited {proc.returncode}; see its log"
            )
        try:
            if _json_get(url, timeout=2).get("ok") is True:
                return
            error = "health JSON did not report ok=true"
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.2)
    raise RuntimeError(f"{lane.harness} {role} not ready: {error}")


def _terminate(procs: list[subprocess.Popen], grace_s: float = 20) -> None:
    running = [proc for proc in procs if proc and proc.poll() is None]
    for proc in running:
        proc.terminate()
    deadline = time.monotonic() + grace_s
    while running and time.monotonic() < deadline:
        running = [proc for proc in running if proc.poll() is None]
        if running:
            time.sleep(0.2)
    for proc in running:
        proc.kill()
    for proc in running:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _lane_snapshot(lane: Lane) -> dict[str, Any]:
    worker_rc = lane.worker_rc
    if worker_rc is None and lane.worker_proc is not None:
        worker_rc = lane.worker_proc.poll()
    return {
        "harness": lane.harness,
        "worker_id": lane.worker_id,
        "run_set_id": lane.run_set_id,
        "worker_pid": lane.worker_proc.pid if lane.worker_proc else None,
        "worker_rc": worker_rc,
        "shim_pid": lane.shim_proc.pid if lane.shim_proc else None,
        "shim_rc": lane.shim_proc.poll() if lane.shim_proc else None,
        "dsproxy_pid": lane.dsproxy_proc.pid if lane.dsproxy_proc else None,
        "dsproxy_rc": lane.dsproxy_proc.poll() if lane.dsproxy_proc else None,
        "run_dir": str(lane.run_dir),
        "worker_log": str(lane.worker_log),
    }


def _write_status(path: Path, tag: str, model: str, lanes: list[Lane]) -> None:
    _atomic_json(path, {
        "tag": tag,
        "model": model,
        "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lanes": [_lane_snapshot(lane) for lane in lanes],
    })


def _load_one(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _summarize(tag: str, model: str, task: str, lanes: list[Lane]) -> dict:
    rows: dict[str, dict[str, Any]] = {}
    total = {
        "n_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "usage_missing_calls": 0,
        "cost": None,
        "cost_currency": None,
        "cost_complete": False,
    }
    for lane in lanes:
        raw = lane.run_dir / "raw"
        meta = _load_one(raw / f"{lane.harness}__{task}_rep1.meta.json") or {}
        report = raw / f"{lane.harness}__{task}_rep1.md"
        score = lane.run_dir / "scores" / f"{lane.harness}__{task}_rep1.score.json"
        ledger = _load_one(lane.run_dir / f"api_costs.worker-{lane.worker_id}.json") or {}
        usage = ledger.get("totals") if isinstance(ledger.get("totals"), dict) else {}
        for key in (
            "n_calls", "prompt_tokens", "completion_tokens", "total_tokens",
            "usage_missing_calls",
        ):
            value = int(usage.get(key) or 0)
            total[key] += value
        rows[lane.harness] = {
            "worker_rc": lane.worker_rc,
            "status": meta.get("status"),
            "error": meta.get("error"),
            "run_id": meta.get("run_id"),
            "elapsed_seconds": meta.get("elapsed_seconds"),
            "report_chars": meta.get("report_chars"),
            "report_exists": report.is_file(),
            "score_exists": score.is_file(),
            "model_identity": meta.get("model_identity"),
            "network_verified": (meta.get("network_isolation") or {}).get("verified"),
            "egress_enforced": (meta.get("egress_evidence") or {}).get("enforced"),
            "usage": usage,
            "paths": {
                "run_dir": str(lane.run_dir),
                "worker_log": str(lane.worker_log),
                "cost_ledger": str(
                    lane.run_dir / f"api_costs.worker-{lane.worker_id}.json"
                ),
            },
        }
    return {
        "tag": tag,
        "model": model,
        "task": task,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "all_workers_zero": all(lane.worker_rc == 0 for lane in lanes),
        "scoreable": sum(bool(row["score_exists"]) for row in rows.values()),
        "harness_count": len(lanes),
        "agents": rows,
        "totals": total,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--task", default="dr_cross_deep_0010")
    parser.add_argument("--api-base", default="http://127.0.0.1:8317/v1")
    parser.add_argument("--client-env", default="/etc/cliproxyapi/client.env")
    parser.add_argument("--results-root", default="/opt/dra-smoke-results")
    parser.add_argument("--control-root", default="/opt/dra-smoke-control")
    parser.add_argument("--tag")
    parser.add_argument(
        "--harness", action="append", choices=DEFAULT_HARNESSES,
        help="repeat for a subset; default is the full 12-harness matrix",
    )
    parser.add_argument("--upstream-slots", type=int, default=2)
    # QX's unmodified multi-section planner legitimately admitted 160 calls
    # before all parallel section writers had finished (formal qx9 evidence),
    # without any schema retry.  Keep a finite uniform fuse, but leave enough
    # headroom for that native topology; the independent 750k-token ceiling
    # still stops high-context runaways such as the earlier DeerFlow failure.
    parser.add_argument("--max-calls", type=int, default=256)
    parser.add_argument("--max-total-tokens", type=int, default=750_000)
    parser.add_argument("--launch-stagger-s", type=float, default=1.0)
    parser.add_argument("--model-probe-timeout-s", type=int, default=900)
    parser.add_argument("--service-read-timeout-s", type=int, default=1200)
    parser.add_argument("--upstream-read-timeout-s", type=int, default=600)
    parser.add_argument("--score-timeout-s", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if os.geteuid() != 0:
        raise SystemExit("formal smoke matrix must run as root")
    if not (ROOT / ".venv-camel/bin/python").is_file():
        raise SystemExit("composite supervisor runtime .venv-camel is missing")
    if args.upstream_slots <= 0:
        raise SystemExit("--upstream-slots must be positive")
    if (
        args.max_calls < 0
        or args.max_total_tokens < 0
        or args.score_timeout_s < 0
    ):
        raise SystemExit("smoke budgets must be non-negative")

    tag = args.tag or (
        "smoke12-gpt56l-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    if not SAFE_ID.fullmatch(tag):
        raise SystemExit(f"unsafe --tag: {tag!r}")
    harnesses = list(dict.fromkeys(args.harness or DEFAULT_HARNESSES))
    key = _read_client_key(Path(args.client_env))
    _check_api(args.api_base, key, args.model)

    results_root = Path(args.results_root).resolve()
    control = Path(args.control_root).resolve() / tag
    if control.exists() and any(control.iterdir()):
        raise SystemExit(f"control directory already exists and is non-empty: {control}")
    control.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(control, 0o700)
    shared_slots_dir = Path("/run/dra-cliproxy-slots") / tag
    shared_slots_dir.mkdir(parents=True, mode=0o755, exist_ok=True)

    metadata = _cliproxy_metadata()
    lanes: list[Lane] = []
    for harness in harnesses:
        index = DEFAULT_HARNESSES.index(harness)
        worker_id = 100 + index
        run_set_id = f"{tag}-{harness}"
        run_dir = results_root / run_set_id / args.model
        queue = control / f"queue-{harness}.tsv"
        queue.write_text(f"{harness}\t{args.task}\n")
        lane = Lane(
            harness=harness,
            index=index,
            worker_id=worker_id,
            run_set_id=run_set_id,
            queue=queue,
            run_dir=run_dir,
            shim_port=18401 + index,
            dsproxy_port=18501 + index,
            egress_port=18199 + index,
            qx_port=19100 + index,
            shim_log=control / f"service-shim-{harness}.log",
            dsproxy_log=control / f"service-dsproxy-{harness}.log",
            worker_log=control / f"worker-{harness}.log",
            usage_log=run_dir / "logs" / f"dsproxy-worker-{worker_id}.usage.jsonl",
        )
        for port in (lane.shim_port, lane.dsproxy_port, lane.egress_port, lane.qx_port):
            _assert_port_free(port)
        lanes.append(lane)

    python = str(ROOT / ".venv-camel/bin/python")
    terminating = False

    def stop(_signum=None, _frame=None):
        nonlocal terminating
        terminating = True
        _terminate([
            lane.worker_proc for lane in lanes if lane.worker_proc is not None
        ], grace_s=30)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        for lane in lanes:
            lane.usage_log.parent.mkdir(parents=True, exist_ok=True)
            (lane.run_dir / "evidence" / f"worker-{lane.worker_id}").mkdir(
                parents=True, exist_ok=True,
            )
            ds_env = dict(os.environ)
            ds_env.update({
                "PYTHONPATH": str(ROOT),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "OPENAI_PROXY_UPSTREAM": args.api_base.rstrip("/"),
                "OPENAI_PROXY_KEY": key,
                "OPENAI_PROXY_CHAT_READ_TIMEOUT_S": str(args.upstream_read_timeout_s),
                "OPENAI_PROXY_RETRY_MAX_ATTEMPTS": "3",
                "OPENAI_PROXY_SHARED_SLOTS_DIR": str(shared_slots_dir),
                "OPENAI_PROXY_SHARED_SLOTS": str(args.upstream_slots),
                "DSPROXY_MAX_CALLS": str(args.max_calls),
                "DSPROXY_MAX_TOTAL_TOKENS": str(args.max_total_tokens),
                "DSPROXY_ALLOWED_CLIENT_CIDRS": "127.0.0.0/8,10.240.0.0/16",
                "DSPROXY_USAGE_LOG": str(lane.usage_log),
                "DRA_WORKER_ID": str(lane.worker_id),
            })
            _start(
                lane,
                [python, "-m", "uvicorn", "integrations.ds_proxy.app:app",
                 "--host", "0.0.0.0", "--port", str(lane.dsproxy_port)],
                ds_env,
                lane.dsproxy_log,
                "dsproxy",
            )

            shim_env = dict(os.environ)
            shim_env.update({
                "PYTHONPATH": str(ROOT),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "SHIM_MODE": "strict",
                "SHIM_EVIDENCE": "1",
                "SHIM_EVIDENCE_DIR": str(
                    lane.run_dir / "evidence" / f"worker-{lane.worker_id}"
                ),
                "SHIM_LLM_UPSTREAM": f"http://127.0.0.1:{lane.dsproxy_port}/v1",
                **SANDBOX_SOURCE_ENV,
            })
            _start(
                lane,
                [python, "-m", "uvicorn", "integrations.search_shim.app:app",
                 "--host", "0.0.0.0", "--port", str(lane.shim_port)],
                shim_env,
                lane.shim_log,
                "shim",
            )

        for lane in lanes:
            assert lane.dsproxy_proc is not None and lane.shim_proc is not None
            _wait_ready(
                lane, "dsproxy", f"http://127.0.0.1:{lane.dsproxy_port}/healthz",
                lane.dsproxy_proc,
            )
            _wait_ready(
                lane, "shim", f"http://127.0.0.1:{lane.shim_port}/healthz",
                lane.shim_proc,
            )

        for lane in lanes:
            env = dict(os.environ)
            env.update(metadata)
            env.update({
                "PYTHON": python,
                "BACKBONE": args.model,
                "RUN_SET_ID": lane.run_set_id,
                "DEEP_RESULTS_ROOT": str(results_root),
                "DRA_WORKER_ID": str(lane.worker_id),
                "DRA_EGRESS_PORT": str(lane.egress_port),
                "DRA_QX_ADAPTER_PORT": str(lane.qx_port),
                "DRA_MODEL_PROBE_TIMEOUT_S": str(args.model_probe_timeout_s),
                "DRA_EGRESS_SERVICE_READ_TIMEOUT_S": str(args.service_read_timeout_s),
                "DRA_SCORE_TIMEOUT_S": str(args.score_timeout_s),
                "DRA_SMOKE_SCOPE": f"{len(lanes)}-harness-x-1-task",
                "DRA_SMOKE_TASK": args.task,
                "DS_PROXY_URL": f"http://127.0.0.1:{lane.dsproxy_port}/v1",
                "OPENAI_BASE_URL": f"http://127.0.0.1:{lane.dsproxy_port}/v1",
                "OPENAI_API_KEY": "worker-uses-server-side-key",
                "JUDGE_BASE_URL": f"http://127.0.0.1:{lane.dsproxy_port}/v1",
                "JUDGE_MODEL": args.model,
                "JUDGE_PROVIDER": "openai",
                "JUDGE_API_KEY": "worker-uses-server-side-key",
                "SHIM_URL": f"http://127.0.0.1:{lane.shim_port}",
                **SANDBOX_SOURCE_ENV,
                "WIKIPEDIA": "http://127.0.0.1:8090",
                "DSPROXY_USAGE_LOG": str(lane.usage_log),
                "DSPROXY_MAX_CALLS": str(args.max_calls),
                "DSPROXY_MAX_TOTAL_TOKENS": str(args.max_total_tokens),
                "DSPROXY_ALLOWED_CLIENT_CIDRS": "127.0.0.0/8,10.240.0.0/16",
                "OPENAI_PROXY_CHAT_READ_TIMEOUT_S": str(args.upstream_read_timeout_s),
                "OPENAI_PROXY_RETRY_MAX_ATTEMPTS": "3",
                "OPENAI_PROXY_SHARED_SLOTS_DIR": str(shared_slots_dir),
                "OPENAI_PROXY_SHARED_SLOTS": str(args.upstream_slots),
            })
            _start(
                lane,
                ["bash", "scripts/run_full_leaderboard.sh", str(lane.queue)],
                env,
                lane.worker_log,
                "worker",
            )
            if args.launch_stagger_s:
                time.sleep(args.launch_stagger_s)

        status_path = control / "status.json"
        while True:
            alive = 0
            for lane in lanes:
                assert lane.worker_proc is not None
                rc = lane.worker_proc.poll()
                if rc is None:
                    alive += 1
                elif lane.worker_rc is None:
                    lane.worker_rc = rc
            _write_status(status_path, tag, args.model, lanes)
            if not alive or terminating:
                break
            time.sleep(5)

        if terminating:
            for lane in lanes:
                if lane.worker_proc is not None:
                    lane.worker_rc = lane.worker_proc.poll()
        else:
            for lane in lanes:
                assert lane.worker_proc is not None
                lane.worker_rc = lane.worker_proc.wait()

        summary = _summarize(tag, args.model, args.task, lanes)
        _atomic_json(control / "summary.json", summary)
        _write_status(status_path, tag, args.model, lanes)
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
        return 0 if summary["all_workers_zero"] else 1
    finally:
        _terminate([
            proc
            for lane in lanes
            for proc in (lane.worker_proc, lane.shim_proc, lane.dsproxy_proc)
            if proc is not None
        ], grace_s=30)
        for lane in lanes:
            for handle in lane.handles:
                try:
                    handle.close()
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
