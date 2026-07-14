#!/usr/bin/env python3
"""Create and attest the kernel boundary used by a formal DRA worker.

The recording proxy is useful only when framework code cannot open another
network path.  This launcher creates a dedicated Linux network namespace with
no default route, installs a default-drop nftables policy, drops the worker to
an unprivileged numeric uid with no capabilities, and runs live positive and
negative probes from that exact context.

The root-owned attestation is not a replacement for the boundary.  It binds a
run artifact to the namespace, nftables rules, uid, evidence permissions, and
live bypass results that were checked before the worker was admitted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
import pathlib
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "dra.production-isolation.v1"
PROOF_SCHEMA = "dra.production-isolation-proof.v1"
REMOTE_PROOF_SCHEMA = "dra.remote-isolation-proof.v1"
NFT_TABLE = "dra_guard"
STATE_BASE = pathlib.Path("/run/dra-isolation")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ORIGIN = re.compile(r"^(.+):(\d+)$")


class IsolationError(RuntimeError):
    """A fail-closed production-boundary error."""


def _run(
    argv: Sequence[str],
    *,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv), input=input_text, text=True, capture_output=True,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise IsolationError(
            f"command failed ({result.returncode}): {' '.join(argv)}: {detail}"
        )
    return result


def _require_root() -> None:
    if sys.platform != "linux":
        raise IsolationError("formal isolation requires Linux")
    if os.geteuid() != 0:
        raise IsolationError("formal isolation setup must run as root")
    missing = [name for name in ("ip", "nft", "setpriv") if not shutil.which(name)]
    if missing:
        raise IsolationError("required isolation tools missing: " + ", ".join(missing))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _payload_digest(value: Mapping[str, Any], field: str) -> str:
    body = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _write_json_atomic(path: pathlib.Path, value: Mapping[str, Any], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=path.name + ".tmp.", dir=path.parent)
    tmp = pathlib.Path(raw_tmp)
    try:
        os.fchmod(fd, mode)
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, mode)
        os.chown(path, 0, 0)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise IsolationError(f"cannot read isolation JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IsolationError(f"isolation JSON is not an object: {path}")
    return value


def _assert_root_owned_read_only(path: pathlib.Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise IsolationError(f"attestation unavailable: {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise IsolationError(f"attestation must be a regular non-symlink: {path}")
    if info.st_uid != 0 or info.st_gid != 0:
        raise IsolationError(f"attestation is not root-owned: {path}")
    if info.st_mode & 0o022:
        raise IsolationError(f"attestation is group/world writable: {path}")
    parent = path.parent.lstat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        raise IsolationError(f"attestation directory is not root-protected: {path.parent}")


def load_proof(path: str | os.PathLike[str]) -> dict[str, Any]:
    proof_path = pathlib.Path(path)
    _assert_root_owned_read_only(proof_path)
    proof = _load_json(proof_path)
    if proof.get("schema") != PROOF_SCHEMA:
        raise IsolationError(f"unsupported isolation proof schema: {proof.get('schema')!r}")
    expected = _payload_digest(proof, "proof_digest")
    if proof.get("proof_digest") != expected:
        raise IsolationError("isolation proof digest mismatch")
    if proof.get("passed") is not True:
        raise IsolationError("isolation proof did not pass")
    return proof


def load_remote_proof(path: str | os.PathLike[str]) -> dict[str, Any]:
    proof_path = pathlib.Path(path)
    _assert_root_owned_read_only(proof_path)
    proof = _load_json(proof_path)
    if proof.get("schema") != REMOTE_PROOF_SCHEMA:
        raise IsolationError("unsupported remote isolation proof schema")
    if proof.get("proof_digest") != _payload_digest(proof, "proof_digest"):
        raise IsolationError("remote isolation proof digest mismatch")
    if proof.get("passed") is not True:
        raise IsolationError("remote isolation proof did not pass")
    return proof


def _status_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in pathlib.Path("/proc/self/status").read_text().splitlines():
        if ":" in raw:
            key, value = raw.split(":", 1)
            fields[key] = value.strip()
    return fields


def _has_default_route() -> bool:
    try:
        rows = pathlib.Path("/proc/net/route").read_text().splitlines()[1:]
        if any(row.split()[1] == "00000000" and row.split()[7] == "00000000"
               for row in rows if len(row.split()) >= 8):
            return True
    except Exception:
        return True
    try:
        for raw in pathlib.Path("/proc/net/ipv6_route").read_text().splitlines():
            parts = raw.split()
            # Linux exposes its IPv6 null-entry as ``::/0 metric ffffffff
            # dev lo`` even in a namespace with no usable default route.  It
            # is a reject sink, not an egress path; treating it as a route
            # makes every correctly isolated worker fail the live probe.
            if (
                len(parts) >= 10
                and parts[0] == "0" * 32
                and parts[1] == "00"
                and parts[5].lower() != "ffffffff"
            ):
                return True
    except FileNotFoundError:
        pass
    except Exception:
        return True
    return False


def current_context_details(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify the current worker against its root-owned live proof."""
    source = os.environ if env is None else env
    result: dict[str, Any] = {"verified": False}
    proof_path = str(source.get("DRA_ISOLATION_PROOF", "")).strip()
    if not proof_path:
        result["error"] = "DRA_ISOLATION_PROOF is missing"
        return result
    try:
        proof = load_proof(proof_path)
        status_fields = _status_fields()
        uid = os.geteuid()
        gid = os.getegid()
        caps = int(status_fields.get("CapEff", "-1"), 16)
        no_new_privs = int(status_fields.get("NoNewPrivs", "0"))
        netns_inode = os.stat("/proc/self/ns/net").st_ino
        mountns_inode = os.stat("/proc/self/ns/mnt").st_ino
        proxy = str(source.get("DRA_EGRESS_PROXY", "")).rstrip("/")
        checks = {
            "active_marker": str(source.get("DRA_ISOLATION_ACTIVE", "")) == "1",
            "uid": uid == int(proof["worker_uid"]) and uid != 0,
            "gid": gid == int(proof["worker_gid"]),
            "cap_eff_zero": caps == 0,
            "no_new_privs": no_new_privs == 1,
            "netns_inode": netns_inode == int(proof["netns_inode"]),
            "not_host_netns": netns_inode != int(proof["host_netns_inode"]),
            "not_host_mountns": mountns_inode != int(proof["host_mountns_inode"]),
            "no_default_route": not _has_default_route(),
            "proxy": proxy == str(proof["proxy_url"]).rstrip("/"),
            "server_merge": str(source.get("DRA_EGRESS_SERVER_MERGE", "")) == "1",
            "run_set": str(source.get("DRA_RUN_SET_ID", "")) == str(proof["run_set_id"]),
            "worker": str(source.get("DRA_WORKER_ID", "")) == str(proof["worker_id"]),
            "backbone": str(source.get("DRA_BACKBONE", "")) == str(proof["backbone"]),
            "chroot_active": str(source.get("DRA_CHROOT_ACTIVE", "")) == "1",
            "hidden_gold_marker": str(source.get("DRA_HIDDEN_GOLD_MASKED", "")) == "1",
            "repository_read_only": not os.access(
                str(proof["repository_root"]), os.W_OK,
            ),
            "output_writable": os.access("/output", os.W_OK),
        }
        for hidden_path in proof.get("hidden_canary_paths", []):
            checks[f"hidden_unreadable:{hidden_path}"] = not os.access(hidden_path, os.R_OK)
        for evidence_path in proof.get("protected_evidence_paths", []):
            checks[f"evidence_not_writable:{evidence_path}"] = not os.access(
                evidence_path, os.W_OK,
            )
        result.update({
            "proof_id": proof["proof_id"],
            "proof_digest": proof["proof_digest"],
            "proof_path": proof_path,
            "worker_uid": uid,
            "worker_gid": gid,
            "netns_inode": netns_inode,
            "mountns_inode": mountns_inode,
            "cap_eff": f"{caps:x}",
            "no_new_privs": no_new_privs,
            "checks": checks,
        })
        failed = sorted(name for name, ok in checks.items() if not ok)
        if failed:
            result["error"] = "current isolation checks failed: " + ", ".join(failed)
            return result
        result["verified"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def current_context_is_enforced(env: Mapping[str, str] | None = None) -> bool:
    return current_context_details(env).get("verified") is True


def remote_context_is_enforced(env: Mapping[str, str] | None = None) -> bool:
    """Remote flags alone never attest a Windows or SSH worker."""
    source = os.environ if env is None else env
    path = str(source.get("DRA_REMOTE_ISOLATION_PROOF", "")).strip()
    proxy = str(source.get("DRA_REMOTE_EGRESS_PROXY", "")).strip()
    if not path or not proxy:
        return False
    try:
        proof = load_remote_proof(path)
        return (
            str(proof.get("proxy_url", "")).rstrip("/") == proxy.rstrip("/")
            and str(proof.get("run_set_id", "")) == str(source.get("DRA_RUN_SET_ID", ""))
            and str(proof.get("backbone", "")) == str(source.get("DRA_BACKBONE", ""))
        )
    except Exception:
        return False


def _parse_origin(raw: str) -> tuple[str, int]:
    match = ORIGIN.match(raw.strip())
    if not match:
        raise IsolationError(f"invalid host:port origin: {raw!r}")
    host = match.group(1).strip("[]").lower()
    port = int(match.group(2))
    if not host or not 1 <= port <= 65535:
        raise IsolationError(f"invalid host:port origin: {raw!r}")
    return host, port


def _origins(raw: str) -> list[tuple[str, int]]:
    values = [_parse_origin(item) for item in raw.split(",") if item.strip()]
    if not values:
        raise IsolationError("at least one origin is required")
    return sorted(set(values))


def _safe_name(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:10]
    return (prefix + digest)[:15]


def _used_networks() -> list[ipaddress.IPv4Network]:
    result = _run(["ip", "-j", "route", "show", "table", "all"])
    networks: list[ipaddress.IPv4Network] = []
    for row in json.loads(result.stdout or "[]"):
        dst = row.get("dst")
        if not dst or dst == "default" or ":" in dst:
            continue
        try:
            networks.append(ipaddress.ip_network(dst, strict=False))
        except ValueError:
            pass
    return networks


def _allocate_network(seed: str) -> ipaddress.IPv4Network:
    used = _used_networks()
    start = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % 16384
    base = int(ipaddress.ip_address("10.240.0.0"))
    for offset in range(16384):
        candidate = ipaddress.ip_network((base + 4 * ((start + offset) % 16384), 30))
        if not any(candidate.overlaps(item) for item in used):
            return candidate
    raise IsolationError("no free /30 network remains in 10.240.0.0/16")


def _allocate_uid(seed: str, worker_id: int, state_parent: pathlib.Path) -> int:
    occupied = {int(row.split(":")[2]) for row in pathlib.Path("/etc/passwd").read_text().splitlines()
                if len(row.split(":")) >= 3 and row.split(":")[2].isdigit()}
    for path in state_parent.glob("*.json"):
        try:
            row = _load_json(path)
            occupied.add(int(row.get("worker_uid", -1)))
        except Exception:
            pass
    # Normal worker ids get a stable collision-free uid. Large/custom ids fall
    # back to the same bounded scan while still checking every live state file.
    start = worker_id if 0 <= worker_id < 5000 else (
        int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % 5000
    )
    for offset in range(5000):
        uid = 60000 + ((start + offset) % 5000)
        if uid not in occupied:
            return uid
    raise IsolationError("no free numeric worker uid in 60000..64999")


def _secure_root_dir(path: pathlib.Path, mode: int = 0o700) -> None:
    if path.exists() and path.is_symlink():
        raise IsolationError(f"security-sensitive directory is a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != 0:
        raise IsolationError(f"security-sensitive directory is not root-owned: {path}")
    os.chown(path, 0, 0)
    os.chmod(path, mode)


def _grant_worker_tree(path: pathlib.Path, uid: int, gid: int, mode: int) -> None:
    if path.exists() and path.is_symlink():
        raise IsolationError(f"worker path is a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        for name in dirs + files:
            item = pathlib.Path(root, name)
            if item.is_symlink():
                raise IsolationError(f"worker tree contains a symlink: {item}")
            os.chown(item, uid, gid)
    os.chmod(path, mode)


def _make_read_only_tree(path: pathlib.Path) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, 0, 0)
        os.chmod(root, 0o555)
        for name in files:
            item = pathlib.Path(root, name)
            os.chown(item, 0, 0)
            executable = bool(item.stat().st_mode & 0o111)
            os.chmod(item, 0o555 if executable else 0o444)
        for name in dirs:
            item = pathlib.Path(root, name)
            os.chown(item, 0, 0)
            os.chmod(item, 0o555)


def _tree_digest(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: str(value.relative_to(path))):
        relative = str(item.relative_to(path))
        digest.update(relative.encode() + b"\0")
        if item.is_symlink():
            digest.update(b"L" + os.readlink(item).encode())
        elif item.is_file():
            digest.update(b"F" + hashlib.sha256(item.read_bytes()).digest())
        elif item.is_dir():
            digest.update(b"D")
    return digest.hexdigest()


def _prepare_safe_repo_views(
    repository: pathlib.Path, runtime_dir: pathlib.Path,
) -> dict[str, str]:
    """Copy the minimum harness view exposed inside the worker chroot."""
    safe = runtime_dir / "safe"
    if safe.exists():
        shutil.rmtree(safe)
    safe.mkdir(parents=True)

    safe_data = safe / "data"
    safe_data.mkdir()
    shutil.copytree(repository / "data" / "tasks", safe_data / "tasks")
    (safe_data / "results" / "deep").mkdir(parents=True)

    safe_scripts = safe / "scripts"
    safe_scripts.mkdir()
    for name in (
        "__init__.py", "run_deep_task.py", "run_manifest.py",
        "production_isolation.py",
    ):
        source = repository / "scripts" / name
        if source.exists():
            shutil.copy2(source, safe_scripts / name)
    shutil.copytree(repository / "scripts" / "runners", safe_scripts / "runners")

    safe_eval = safe / "src-eval"
    safe_eval.mkdir()
    for name in ("__init__.py", "report_stubs.py"):
        source = repository / "src" / "eval" / name
        if source.exists():
            shutil.copy2(source, safe_eval / name)

    safe_verifiers = safe / "src-verifiers"
    safe_verifiers.mkdir()
    # The repository initializer imports the complete scoring stack.  Workers
    # only need these deterministic modules, so expose an inert package root.
    (safe_verifiers / "__init__.py").write_text("", encoding="utf-8")
    for name in ("citation_format.py", "sandbox_compliance_verifier.py"):
        source = repository / "src" / "verifiers" / name
        if source.exists():
            shutil.copy2(source, safe_verifiers / name)

    empty = safe / "empty"
    empty.mkdir()
    empty_file = safe / "empty-file"
    empty_file.touch()
    _make_read_only_tree(safe)
    return {
        "safe_data": str(safe_data),
        "safe_scripts": str(safe_scripts),
        "safe_eval": str(safe_eval),
        "safe_verifiers": str(safe_verifiers),
        "empty_mask": str(empty),
        "empty_file_mask": str(empty_file),
    }


def _namespace_inode(namespace: str) -> int:
    raw = _run([
        "ip", "netns", "exec", namespace, "stat", "-Lc", "%i", "/proc/self/ns/net",
    ]).stdout.strip()
    return int(raw)


def _nft_rules(gateway: str, peer_if: str, allowed_ports: Sequence[int]) -> str:
    ports = ", ".join(str(port) for port in sorted(set(allowed_ports)))
    return f"""table inet {NFT_TABLE} {{
  set service_ports {{ type inet_service; elements = {{ {ports} }} }}
  chain input {{
    type filter hook input priority filter; policy drop;
    iifname \"lo\" accept
    ct state established,related accept
  }}
  chain output {{
    type filter hook output priority filter; policy drop;
    oifname \"lo\" accept
    oifname \"{peer_if}\" ip daddr {gateway} tcp dport @service_ports accept
    oifname \"{peer_if}\" ip daddr {gateway} meta l4proto tcp reject with tcp reset
  }}
}}
"""


def _state_digest(state: Mapping[str, Any]) -> str:
    return _payload_digest(state, "state_digest")


def _load_state(path: pathlib.Path) -> dict[str, Any]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise IsolationError(f"state file must be root-owned mode 0600: {path}")
    state = _load_json(path)
    if state.get("schema") != SCHEMA:
        raise IsolationError("unsupported isolation state schema")
    if state.get("state_digest") != _state_digest(state):
        raise IsolationError("isolation state digest mismatch")
    return state


def setup(args: argparse.Namespace) -> int:
    _require_root()
    for value, label in ((args.run_set_id, "run_set_id"), (args.backbone, "backbone")):
        if not SAFE_ID.fullmatch(value):
            raise IsolationError(f"unsafe {label}: {value!r}")
    if args.worker_id < 0 or not 1 <= args.egress_port <= 65535:
        raise IsolationError("worker id or egress port is out of range")

    state_path = pathlib.Path(args.state).resolve()
    if state_path.exists():
        raise IsolationError(
            f"isolation state already exists: {state_path}; run cleanup explicitly"
        )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    os.chown(state_path.parent, 0, 0)
    os.chmod(state_path.parent, 0o700)

    lock_path = state_path.parent / ".setup.lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        seed = f"{args.run_set_id}\0{args.backbone}\0{args.worker_id}"
        namespace = _safe_name("dn", seed)
        host_if = _safe_name("dh", seed)
        peer_if = _safe_name("dw", seed)
        if namespace in _run(["ip", "netns", "list"]).stdout.split():
            raise IsolationError(f"network namespace already exists: {namespace}")
        network = _allocate_network(seed)
        gateway = str(network.network_address + 1)
        worker_ip = str(network.network_address + 2)
        uid = _allocate_uid(seed, args.worker_id, state_path.parent)
        gid = uid
        corpus = _origins(args.corpus_origins)
        services = _origins(args.service_origins)
        allowed_ports = sorted({args.egress_port, *(port for _, port in services)})

        evidence_dir = pathlib.Path(args.evidence_dir).resolve()
        canonical_dir = pathlib.Path(args.canonical_evidence_dir).resolve()
        raw_dir = pathlib.Path(args.raw_dir).resolve()
        proof_dir = pathlib.Path(args.proof_dir).resolve()
        repository = pathlib.Path(args.repository_root).resolve()
        if not (repository / "scripts" / "run_deep_task.py").is_file():
            raise IsolationError(f"repository root is not a DRA checkout: {repository}")
        _secure_root_dir(evidence_dir, 0o700)
        _secure_root_dir(canonical_dir, 0o700)
        _secure_root_dir(proof_dir, 0o755)
        _grant_worker_tree(raw_dir, uid, gid, 0o750)

        rules = _nft_rules(gateway, peer_if, allowed_ports)
        created = False
        try:
            _run(["ip", "netns", "add", namespace])
            created = True
            _run(["ip", "link", "add", host_if, "type", "veth", "peer", "name", peer_if])
            _run(["ip", "link", "set", peer_if, "netns", namespace])
            _run(["ip", "addr", "add", f"{gateway}/30", "dev", host_if])
            _run(["ip", "link", "set", host_if, "up"])
            _run(["ip", "-n", namespace, "addr", "add", f"{worker_ip}/30", "dev", peer_if])
            _run(["ip", "-n", namespace, "link", "set", "lo", "up"])
            _run(["ip", "-n", namespace, "link", "set", peer_if, "up"])
            _run([
                "ip", "netns", "exec", namespace, "sysctl", "-q", "-w",
                "net.ipv6.conf.all.disable_ipv6=1",
            ])
            _run(["ip", "netns", "exec", namespace, "nft", "-f", "-"], input_text=rules)
            nft_text = _run([
                "ip", "netns", "exec", namespace, "nft", "list", "table", "inet", NFT_TABLE,
            ]).stdout
            netns_inode = _namespace_inode(namespace)
            host_netns_inode = os.stat("/proc/self/ns/net").st_ino
            if netns_inode == host_netns_inode:
                raise IsolationError("worker namespace is the host network namespace")

            runtime_dir = state_path.parent / (state_path.stem + ".runtime")
            _secure_root_dir(runtime_dir, 0o711)
            bootstrap = runtime_dir / "worker_bootstrap.py"
            shutil.copy2(pathlib.Path(__file__).resolve(), bootstrap)
            os.chown(bootstrap, 0, 0)
            os.chmod(bootstrap, 0o555)
            safe_views = _prepare_safe_repo_views(repository, runtime_dir)
            safe_view_digest = _tree_digest(runtime_dir / "safe")
            bootstrap_digest = hashlib.sha256(bootstrap.read_bytes()).hexdigest()
            rootfs = runtime_dir / "rootfs"
            rootfs.mkdir(mode=0o700)
            os.chown(rootfs, 0, 0)

            worker_runtime = raw_dir / ".worker-runtime"
            scratch_dir = raw_dir / ".tmp"
            worker_home = raw_dir / ".home"
            storm_scratch = raw_dir / ".storm-scratch"
            for path in (worker_runtime, scratch_dir, worker_home, storm_scratch):
                _grant_worker_tree(path, uid, gid, 0o700)

            overlays: list[dict[str, str]] = []
            deerflow_conf = repository / "third_party" / "deer-flow-v1" / "conf.yaml"
            if deerflow_conf.exists():
                overlay = worker_runtime / "deerflow-conf.yaml"
                shutil.copy2(deerflow_conf, overlay)
                os.chown(overlay, uid, gid)
                os.chmod(overlay, 0o600)
                overlays.append({"source": str(overlay), "target": str(deerflow_conf)})

            state: dict[str, Any] = {
                "schema": SCHEMA,
                "run_set_id": args.run_set_id,
                "backbone": args.backbone,
                "worker_id": args.worker_id,
                "worker_uid": uid,
                "worker_gid": gid,
                "namespace": namespace,
                "host_if": host_if,
                "peer_if": peer_if,
                "network": str(network),
                "gateway": gateway,
                "worker_ip": worker_ip,
                "egress_port": args.egress_port,
                "proxy_url": f"http://{gateway}:{args.egress_port}",
                "allowed_host_ports": allowed_ports,
                "corpus_origins": [f"{host}:{port}" for host, port in corpus],
                "service_origins": [f"{host}:{port}" for host, port in services],
                "evidence_dir": str(evidence_dir),
                "canonical_evidence_dir": str(canonical_dir),
                "raw_dir": str(raw_dir),
                "worker_home": str(worker_home),
                "worker_scratch": str(scratch_dir),
                "worker_runtime": str(worker_runtime),
                "storm_scratch": str(storm_scratch),
                "proof_dir": str(proof_dir),
                "runtime_dir": str(runtime_dir),
                "bootstrap": str(bootstrap),
                "rootfs": str(rootfs),
                "repository_root": str(repository),
                "safe_views": safe_views,
                "safe_view_digest": safe_view_digest,
                "bootstrap_sha256": bootstrap_digest,
                "writable_overlays": overlays,
                "hidden_canary_paths": [
                    str(repository / "data" / "golden" / "answer_keys" /
                        "dr_cross_deep_0001.json"),
                    str(repository / "data" / "golden" / "url_registry.json"),
                    str(repository / ".git" / "HEAD"),
                    str(repository / "scripts" / "score_deep_answer.py"),
                    str(repository / "src" / "eval" / "decidable_scorer.py"),
                    str(repository / "tests" / "test_egress_proxy.py"),
                ],
                "netns_inode": netns_inode,
                "host_netns_inode": host_netns_inode,
                "host_mountns_inode": os.stat("/proc/self/ns/mnt").st_ino,
                "nft_sha256": hashlib.sha256(nft_text.encode()).hexdigest(),
                "nft_rules": rules,
                "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            state["state_digest"] = _state_digest(state)
            _write_json_atomic(state_path, state, 0o600)
        except Exception:
            if created:
                _run(["ip", "netns", "del", namespace], check=False)
            _run(["ip", "link", "del", host_if], check=False)
            raise
    print(json.dumps({
        "state": str(state_path), "namespace": namespace, "gateway": gateway,
        "worker_uid": uid, "proxy_url": f"http://{gateway}:{args.egress_port}",
    }, sort_keys=True))
    return 0


def _check_evidence_permissions(state: Mapping[str, Any]) -> None:
    uid = int(state["worker_uid"])
    gid = int(state["worker_gid"])
    for raw in (state["evidence_dir"], state["canonical_evidence_dir"]):
        path = pathlib.Path(raw)
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o077:
            raise IsolationError(f"evidence directory is not root-only: {path}")
        probe = path / f".permission-check-{os.getpid()}"
        result = _run([
            "setpriv", f"--reuid={uid}", f"--regid={gid}", "--clear-groups",
            "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all",
            "--no-new-privs", "sh", "-c", f": > {str(probe)!r}",
        ], check=False)
        if result.returncode == 0 or probe.exists():
            probe.unlink(missing_ok=True)
            raise IsolationError(f"worker uid can write recorder evidence: {path}")


def check_state(state_path: pathlib.Path, proof_path: pathlib.Path | None = None) -> dict[str, Any]:
    _require_root()
    state = _load_state(state_path)
    namespace = str(state["namespace"])
    listed = _run(["ip", "netns", "list"]).stdout.split()
    if namespace not in listed:
        raise IsolationError(f"worker namespace disappeared: {namespace}")
    if _namespace_inode(namespace) != int(state["netns_inode"]):
        raise IsolationError("worker network namespace inode changed")
    if os.stat("/proc/self/ns/net").st_ino != int(state["host_netns_inode"]):
        raise IsolationError("launcher is no longer in the attested host namespace")

    routes = json.loads(_run(["ip", "-n", namespace, "-j", "route", "show"]).stdout or "[]")
    if any(row.get("dst") == "default" for row in routes):
        raise IsolationError("worker namespace has a default route")
    destinations = {row.get("dst") for row in routes if row.get("dst")}
    if destinations - {state["network"]}:
        raise IsolationError(f"worker namespace has unexpected routes: {sorted(destinations)}")

    nft_text = _run([
        "ip", "netns", "exec", namespace, "nft", "list", "table", "inet", NFT_TABLE,
    ]).stdout
    if hashlib.sha256(nft_text.encode()).hexdigest() != state["nft_sha256"]:
        raise IsolationError("worker nftables policy changed")
    if "policy drop" not in nft_text or "service_ports" not in nft_text:
        raise IsolationError("worker nftables policy is not default-drop")
    bootstrap = pathlib.Path(state["bootstrap"])
    if hashlib.sha256(bootstrap.read_bytes()).hexdigest() != state["bootstrap_sha256"]:
        raise IsolationError("worker isolation bootstrap changed")
    safe_root = pathlib.Path(state["runtime_dir"]) / "safe"
    if _tree_digest(safe_root) != state["safe_view_digest"]:
        raise IsolationError("read-only worker code/data view changed")
    _check_evidence_permissions(state)

    if proof_path is not None:
        proof = load_proof(proof_path)
        if proof.get("state_digest") != state["state_digest"]:
            raise IsolationError("proof does not bind the live namespace state")
        if int(proof.get("netns_inode", -1)) != int(state["netns_inode"]):
            raise IsolationError("proof does not bind the live network namespace")
    return state


def _isolated_argv(
    state_path: pathlib.Path,
    state: Mapping[str, Any],
    command: Sequence[str],
) -> list[str]:
    if not command:
        raise IsolationError("worker command is empty")
    return [
        "ip", "netns", "exec", str(state["namespace"]),
        "unshare", "--mount", "--pid", "--fork", "--kill-child", "--ipc",
        "--propagation", "private",
        sys.executable, str(state["bootstrap"]), "_mount-exec", str(state_path),
        "--", *command,
    ]


def _mount_bind(source: pathlib.Path, target: pathlib.Path, *, readonly: bool) -> None:
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        _run(["mount", "--bind", str(source), str(target)])
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.touch()
        _run(["mount", "--bind", str(source), str(target)])
    if readonly:
        _run(["mount", "-o", "remount,bind,ro", str(target)])


def _mount_rbind_readonly(source: pathlib.Path, target: pathlib.Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    _run(["mount", "--rbind", str(source), str(target)])
    _run(["mount", "--make-rslave", str(target)])
    # New mount API recursive read-only is not available on every production
    # image. Remount each visible child deepest-first and reject any failure.
    mounts = []
    prefix = str(target).rstrip("/") + "/"
    for raw in pathlib.Path("/proc/self/mountinfo").read_text().splitlines():
        fields = raw.split()
        if len(fields) > 4:
            mountpoint = fields[4].replace("\\040", " ")
            if mountpoint == str(target) or mountpoint.startswith(prefix):
                mounts.append(pathlib.Path(mountpoint))
    for mountpoint in sorted(mounts, key=lambda item: len(item.parts), reverse=True):
        _run(["mount", "-o", "remount,bind,ro", str(mountpoint)])


def _mount_hidden_path(
    empty_dir: pathlib.Path,
    empty_file: pathlib.Path,
    target: pathlib.Path,
) -> None:
    """Mask a repository path without assuming it is a directory.

    A normal checkout exposes ``.git`` as a directory; a linked Git worktree
    exposes it as a regular gitfile.  Mounting a directory mask over that file
    first calls ``mkdir`` and aborts the worker before its live isolation
    probe.  Select a same-kind empty mount and reject exotic/symlink targets so
    masking can never follow a repository-controlled path outside the root.
    """
    info = target.lstat()
    if stat.S_ISDIR(info.st_mode):
        source = empty_dir
    elif stat.S_ISREG(info.st_mode):
        source = empty_file
    else:
        raise IsolationError(
            f"refusing to mask non-regular repository path: {target}"
        )
    _mount_bind(source, target, readonly=True)


def mount_exec(state_path: pathlib.Path, command: Sequence[str]) -> int:
    """Build a read-only chroot in the already-created worker netns."""
    _require_root()
    state = _load_state(state_path)
    if os.stat("/proc/self/ns/net").st_ino != int(state["netns_inode"]):
        raise IsolationError("mount supervisor is not in the worker network namespace")
    proof_raw = os.environ.get("DRA_ISOLATION_PROOF", "").strip()
    probe_mode = "_worker-probe" in command
    proof_path: pathlib.Path | None = None
    if proof_raw:
        proof_path = pathlib.Path(proof_raw).resolve()
        proof = load_proof(proof_path)
        if proof.get("state_digest") != state["state_digest"]:
            raise IsolationError("mount supervisor proof/state mismatch")
    elif not probe_mode:
        raise IsolationError("mount supervisor requires DRA_ISOLATION_PROOF")

    rootfs = pathlib.Path(state["rootfs"])
    rootfs.mkdir(parents=True, exist_ok=True)
    _run([
        "mount", "-t", "tmpfs", "-o", "mode=0755,nosuid,nodev", "tmpfs", str(rootfs),
    ])
    try:
        _mount_bind(pathlib.Path("/usr"), rootfs / "usr", readonly=True)
        _mount_bind(pathlib.Path("/etc"), rootfs / "etc", readonly=True)
        if pathlib.Path("/dev").exists():
            _mount_rbind_readonly(pathlib.Path("/dev"), rootfs / "dev")
        if pathlib.Path("/sys").exists():
            _mount_rbind_readonly(pathlib.Path("/sys"), rootfs / "sys")
        (rootfs / "proc").mkdir()
        _run([
            "mount", "-t", "proc", "-o", "ro,nosuid,nodev,noexec", "proc", str(rootfs / "proc"),
        ])

        for name in ("bin", "sbin", "lib", "lib64"):
            source = pathlib.Path("/") / name
            target = rootfs / name
            if source.is_symlink():
                target.symlink_to(os.readlink(source))
            elif source.exists():
                _mount_bind(source, target, readonly=True)

        repository = pathlib.Path(state["repository_root"])
        repository_target = rootfs / repository.relative_to("/")
        _mount_bind(repository, repository_target, readonly=True)
        safe = state["safe_views"]
        _mount_bind(pathlib.Path(safe["safe_data"]), repository_target / "data", readonly=True)
        _mount_bind(pathlib.Path(safe["safe_scripts"]), repository_target / "scripts", readonly=True)
        _mount_bind(pathlib.Path(safe["safe_eval"]), repository_target / "src" / "eval", readonly=True)
        _mount_bind(
            pathlib.Path(safe["safe_verifiers"]),
            repository_target / "src" / "verifiers", readonly=True,
        )
        empty = pathlib.Path(safe["empty_mask"])
        empty_file = pathlib.Path(safe["empty_file_mask"])
        for relative in (".git", "internal", "docs", "tests"):
            target = repository_target / relative
            if target.exists():
                _mount_hidden_path(empty, empty_file, target)

        output = rootfs / "output"
        _mount_bind(pathlib.Path(state["raw_dir"]), output, readonly=False)
        _mount_bind(pathlib.Path(state["worker_scratch"]), rootfs / "tmp", readonly=False)
        storm_target = repository_target / "data" / "results" / "deep"
        _mount_bind(pathlib.Path(state["storm_scratch"]), storm_target, readonly=False)
        for overlay in state.get("writable_overlays", []):
            source = pathlib.Path(overlay["source"])
            target = rootfs / pathlib.Path(overlay["target"]).relative_to("/")
            _mount_bind(source, target, readonly=False)

        run_dir = rootfs / "run"
        run_dir.mkdir(mode=0o555)
        if proof_path is not None:
            proof_inside = run_dir / "dra-isolation-proof.json"
            _mount_bind(proof_path, proof_inside, readonly=True)
        probe_input = pathlib.Path(state["runtime_dir"]) / "probe-input.json"
        if probe_input.exists():
            _mount_bind(probe_input, run_dir / "dra-probe-input.json", readonly=True)

        os.chmod(rootfs, 0o555)
        os.chroot(rootfs)
        os.chdir(str(repository))
        worker_env = {
            "HOME": "/output/.home",
            "USER": "dra-worker",
            "LOGNAME": "dra-worker",
            "TMPDIR": "/tmp",
            "TMP": "/tmp",
            "TEMP": "/tmp",
            "DEEP_RUN_OUT_DIR": "/output",
            "DRA_WORKER_SCRATCH_DIR": "/tmp",
            "DRA_CHROOT_ACTIVE": "1",
            "DRA_HIDDEN_GOLD_MASKED": "1",
            "DRA_REPOSITORY_ROOT": str(repository),
        }
        if proof_path is not None:
            worker_env["DRA_ISOLATION_PROOF"] = "/run/dra-isolation-proof.json"
        else:
            worker_env.pop("DRA_ISOLATION_PROOF", None)
            os.environ.pop("DRA_ISOLATION_PROOF", None)
        os.environ.update(worker_env)
        argv = [
            "setpriv", f"--reuid={state['worker_uid']}", f"--regid={state['worker_gid']}",
            "--clear-groups", "--bounding-set=-all", "--inh-caps=-all",
            "--ambient-caps=-all", "--no-new-privs", "--pdeathsig", "keep",
            "env", *command,
        ]
        os.execvp("setpriv", argv)
    finally:
        # Normal execution replaces this process. This path is reached only on
        # setup failure, when unshare tears the private mounts down on exit.
        pass


def _http_json(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise IsolationError(f"control URL is not plain HTTP: {url}")
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=10)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        try:
            data = json.loads(raw or b"{}")
        except Exception:
            data = {"raw": raw.decode("utf-8", "replace")}
        return response.status, data
    finally:
        conn.close()


def _mark(base: str, phase: str, run_id: str, **extra: Any) -> dict:
    payload = {
        "run_id": run_id, "phase": phase, "lane": "isolation-preflight",
        "agent": "isolation-preflight", "task": "network-boundary",
        "task_id": "network-boundary", "backbone": "preflight", "worker": "preflight",
        "fetch_observable": True, **extra,
    }
    status, body = _http_json(base.rstrip("/") + "/_mark", "POST", payload)
    if status // 100 != 2:
        raise IsolationError(f"{base} /_mark {phase} failed: HTTP {status}: {body}")
    return body


def _host_aliases(state: Mapping[str, Any]) -> list[str]:
    aliases = {"127.0.0.1", "::1", str(state["gateway"])}
    try:
        for link in json.loads(_run(["ip", "-j", "address", "show"]).stdout or "[]"):
            for addr in link.get("addr_info", []):
                local = addr.get("local")
                if local:
                    aliases.add(str(local).split("%", 1)[0])
    except Exception:
        pass
    if shutil.which("docker"):
        ids = _run(["docker", "ps", "-q"], check=False).stdout.split()
        for container_id in ids:
            result = _run([
                "docker", "inspect", "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{.GlobalIPv6Address}} {{end}}",
                container_id,
            ], check=False)
            aliases.update(item for item in result.stdout.split() if item)
    return sorted(aliases)


def _worker_probe_payload(
    state: Mapping[str, Any], args: argparse.Namespace, run_id: str,
) -> dict[str, Any]:
    corpus = [_parse_origin(item) for item in state["corpus_origins"]]
    ports = sorted({port for _, port in corpus})
    aliases = _host_aliases(state)
    targets: set[tuple[str, int]] = set(corpus)
    for host in aliases:
        for port in ports:
            targets.add((host, port))
    return {
        "run_id": run_id,
        "proxy_url": state["proxy_url"],
        "corpus_url": args.corpus_url,
        "service_url": args.service_url,
        "service_direct_url": args.service_direct_url,
        "direct_targets": [{"host": host, "port": port} for host, port in sorted(targets)],
        "public_targets": [
            {"host": "1.1.1.1", "port": 443},
            {"host": "8.8.8.8", "port": 53},
        ],
        "protected_paths": [
            state["evidence_dir"], state["canonical_evidence_dir"],
            str(pathlib.Path(state["evidence_dir"]) / f"{run_id}.jsonl"),
            str(pathlib.Path(state["canonical_evidence_dir"]) / f"{run_id}.jsonl"),
        ],
        "hidden_canary_paths": list(state["hidden_canary_paths"]),
        "read_only_paths": [
            "/", "/usr", "/etc", str(state["repository_root"]),
            str(pathlib.Path(state["repository_root"]) / "scripts"),
            str(pathlib.Path(state["repository_root"]) / "data" / "tasks"),
            "/dev/shm",
        ],
        "writable_paths": ["/output", "/tmp"],
        "expected": {
            "uid": state["worker_uid"], "gid": state["worker_gid"],
            "netns_inode": state["netns_inode"], "host_netns_inode": state["host_netns_inode"],
            "host_mountns_inode": state["host_mountns_inode"],
        },
    }


def _curl_direct(url: str) -> dict[str, Any]:
    env = dict(os.environ)
    for key in (
        "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy",
        "ALL_PROXY", "no_proxy", "NO_PROXY",
    ):
        env.pop(key, None)
    result = subprocess.run([
        "curl", "--noproxy", "*", "--proxy", "", "--fail", "--silent",
        "--show-error", "--connect-timeout", "1", "--max-time", "2",
        "--output", "/dev/null", url,
    ], text=True, capture_output=True, env=env)
    return {"reachable": result.returncode == 0, "rc": result.returncode,
            "stderr": result.stderr[-300:]}


def _url_for(host: str, port: int) -> str:
    bracketed = f"[{host}]" if ":" in host else host
    return f"http://{bracketed}:{port}/"


def worker_probe(input_path: pathlib.Path) -> int:
    """Probe implementation executed after setpriv inside the worker netns."""
    payload = _load_json(input_path)
    expected = payload["expected"]
    status_fields = _status_fields()
    context = {
        "uid": os.geteuid(), "gid": os.getegid(),
        "cap_eff": int(status_fields.get("CapEff", "-1"), 16),
        "no_new_privs": int(status_fields.get("NoNewPrivs", "0")),
        "netns_inode": os.stat("/proc/self/ns/net").st_ino,
        "mountns_inode": os.stat("/proc/self/ns/mnt").st_ino,
        "has_default_route": _has_default_route(),
        "chroot_active": os.environ.get("DRA_CHROOT_ACTIVE") == "1",
        "hidden_gold_masked": os.environ.get("DRA_HIDDEN_GOLD_MASKED") == "1",
    }
    context_ok = (
        context["uid"] == int(expected["uid"]) != 0
        and context["gid"] == int(expected["gid"])
        and context["cap_eff"] == 0
        and context["no_new_privs"] == 1
        and context["netns_inode"] == int(expected["netns_inode"])
        and context["netns_inode"] != int(expected["host_netns_inode"])
        and context["mountns_inode"] != int(expected["host_mountns_inode"])
        and not context["has_default_route"]
        and context["chroot_active"]
        and context["hidden_gold_masked"]
    )

    hidden_reads: list[dict[str, str]] = []
    hidden_bypasses: list[dict[str, str]] = []
    for raw in payload["hidden_canary_paths"]:
        path = pathlib.Path(raw)
        row = {"path": str(path)}
        try:
            with path.open("rb") as handle:
                sample = handle.read(32)
            row["read"] = f"READABLE:{sample[:8].hex()}"
            hidden_bypasses.append({"method": "file_read", "path": str(path)})
        except OSError as exc:
            row["read"] = type(exc).__name__
        if path.is_dir():
            try:
                names = os.listdir(path)
                row["list"] = f"READABLE:{len(names)}"
                hidden_bypasses.append({"method": "directory_list", "path": str(path)})
            except OSError as exc:
                row["list"] = type(exc).__name__
        hidden_reads.append(row)

    filesystem_writes: list[dict[str, str]] = []
    filesystem_bypasses: list[dict[str, str]] = []
    for index, raw in enumerate(payload["read_only_paths"]):
        path = pathlib.Path(raw)
        if not path.exists():
            filesystem_writes.append({"path": str(path), "write": "ABSENT"})
            continue
        candidate = path / f".dra-write-probe-{os.getpid()}-{index}"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            candidate.unlink(missing_ok=True)
            filesystem_writes.append({"path": str(path), "write": "WRITABLE"})
            filesystem_bypasses.append({"method": "filesystem_write", "path": str(path)})
        except OSError as exc:
            filesystem_writes.append({"path": str(path), "write": type(exc).__name__})
    writable_checks: list[dict[str, str]] = []
    for index, raw in enumerate(payload["writable_paths"]):
        path = pathlib.Path(raw)
        candidate = path / f".dra-positive-write-{os.getpid()}-{index}"
        try:
            candidate.write_text("ok", encoding="utf-8")
            candidate.unlink()
            writable_checks.append({"path": str(path), "write": "OK"})
        except OSError as exc:
            writable_checks.append({"path": str(path), "write": type(exc).__name__})
            filesystem_bypasses.append({"method": "required_output_not_writable", "path": str(path)})

    proxy = payload["proxy_url"]
    positive: dict[str, Any] = {}
    for label, url in (
        ("corpus_via_proxy", payload["corpus_url"]),
        ("service_via_proxy", payload["service_url"]),
    ):
        result = subprocess.run([
            "curl", "--noproxy", "", "--proxy", proxy, "--fail", "--silent",
            "--show-error", "--connect-timeout", "2", "--max-time", "15",
            "--output", "/dev/null", url,
        ], text=True, capture_output=True)
        positive[label] = {"ok": result.returncode == 0, "rc": result.returncode,
                           "stderr": result.stderr[-500:]}
    direct_service = _curl_direct(payload["service_direct_url"])
    positive["service_door_direct"] = {"ok": not not direct_service.pop("reachable"),
                                        **direct_service}

    try:
        import requests
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"passed": False, "error": f"requests unavailable: {exc}"}))
        return 2

    bypasses: list[dict[str, Any]] = []
    direct_results: list[dict[str, Any]] = []
    for item in payload["direct_targets"]:
        host, port = str(item["host"]), int(item["port"])
        row: dict[str, Any] = {"host": host, "port": port}
        try:
            with socket.create_connection((host, port), timeout=0.8):
                row["raw_socket"] = "REACHABLE"
                bypasses.append({"method": "raw_socket", "host": host, "port": port})
        except OSError as exc:
            row["raw_socket"] = type(exc).__name__

        curl = _curl_direct(_url_for(host, port))
        row["curl_no_proxy"] = curl
        if curl["reachable"]:
            bypasses.append({"method": "curl_no_proxy", "host": host, "port": port})

        session = requests.Session()
        session.trust_env = False
        try:
            response = session.get(_url_for(host, port), timeout=1.5)
            row["requests_trust_env_false"] = f"REACHABLE:{response.status_code}"
            bypasses.append({
                "method": "requests_trust_env_false", "host": host, "port": port,
                "status": response.status_code,
            })
        except requests.RequestException as exc:
            row["requests_trust_env_false"] = type(exc).__name__
        finally:
            session.close()
        direct_results.append(row)

    public_results: list[dict[str, Any]] = []
    for item in payload["public_targets"]:
        host, port = str(item["host"]), int(item["port"])
        row = {"host": host, "port": port}
        try:
            with socket.create_connection((host, port), timeout=1):
                row["raw_socket"] = "REACHABLE"
                bypasses.append({"method": "public_raw_socket", "host": host, "port": port})
        except OSError as exc:
            row["raw_socket"] = type(exc).__name__
        public_results.append(row)
    public_curl = _curl_direct("https://example.com/")
    if public_curl["reachable"]:
        bypasses.append({"method": "public_curl", "url": "https://example.com/"})
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get("https://example.com/", timeout=2)
        public_requests = {"reachable": True, "status": response.status_code}
        bypasses.append({"method": "public_requests", "status": response.status_code})
    except requests.RequestException as exc:
        public_requests = {"reachable": False, "error": type(exc).__name__}
    finally:
        session.close()
    try:
        socket.getaddrinfo("example.com", 443)
        dns_direct = {"reachable": True}
        bypasses.append({"method": "direct_dns", "host": "example.com"})
    except OSError as exc:
        dns_direct = {"reachable": False, "error": type(exc).__name__}

    write_bypasses: list[dict[str, str]] = []
    write_results: list[dict[str, str]] = []
    for raw in payload["protected_paths"]:
        path = pathlib.Path(raw)
        row: dict[str, str] = {"path": str(path)}
        candidate = path / "worker-write" if path.is_dir() else path
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(fd)
            row["open_write"] = "WRITABLE"
            write_bypasses.append({"method": "open_write", "path": str(candidate)})
        except OSError as exc:
            row["open_write"] = type(exc).__name__
        if path.exists() and path.is_file():
            renamed = path.with_name(path.name + ".worker-rename")
            try:
                os.rename(path, renamed)
                row["rename"] = "WRITABLE"
                write_bypasses.append({"method": "rename", "path": str(path)})
                os.rename(renamed, path)
            except OSError as exc:
                row["rename"] = type(exc).__name__
            try:
                os.unlink(path)
                row["unlink"] = "WRITABLE"
                write_bypasses.append({"method": "unlink", "path": str(path)})
            except OSError as exc:
                row["unlink"] = type(exc).__name__
        write_results.append(row)

    positive_ok = all(row.get("ok") is True for row in positive.values())
    result = {
        "passed": (
            context_ok and positive_ok and not bypasses and not write_bypasses
            and not hidden_bypasses and not filesystem_bypasses
        ),
        "context": context,
        "context_ok": context_ok,
        "positive": positive,
        "direct_corpus": direct_results,
        "public_direct": {
            "sockets": public_results, "curl": public_curl,
            "requests_trust_env_false": public_requests, "dns": dns_direct,
        },
        "evidence_write_attempts": write_results,
        "hidden_gold_read_attempts": hidden_reads,
        "filesystem_write_attempts": filesystem_writes,
        "required_writable_paths": writable_checks,
        "network_bypasses": bypasses,
        "evidence_write_bypasses": write_bypasses,
        "hidden_gold_bypasses": hidden_bypasses,
        "filesystem_bypasses": filesystem_bypasses,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 3


def _evidence_summary(path: pathlib.Path, run_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise IsolationError(f"probe evidence missing: {path}")
    records: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise IsolationError(f"malformed probe evidence {path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict) or row.get("run_id") != run_id:
            raise IsolationError(f"probe evidence owner mismatch {path}:{lineno}")
        records.append(row)
    return {
        "starts": sum(row.get("kind") == "mark" and row.get("phase") == "start"
                      for row in records),
        "ends": sum(row.get("kind") == "mark" and row.get("phase") == "end"
                    for row in records),
        "fetches": sum(row.get("kind") == "fetch" for row in records),
        "blocks": sum(row.get("kind") == "block" for row in records),
        "merged_fetches": sum(row.get("kind") == "fetch" and row.get("recorder") == "egress"
                              for row in records),
        "records": len(records),
    }


def probe(args: argparse.Namespace) -> int:
    state_path = pathlib.Path(args.state).resolve()
    state = check_state(state_path)
    status, egress_health = _http_json(args.egress_control_url.rstrip("/") + "/healthz")
    if status != 200 or egress_health.get("ok") is not True:
        raise IsolationError(f"egress door is not healthy: {status}: {egress_health}")
    if egress_health.get("active_run") is not None:
        raise IsolationError(f"egress door already has an active run: {egress_health}")
    status, shim_health = _http_json(args.shim_control_url.rstrip("/") + "/_evidence/status")
    if status != 200:
        raise IsolationError(f"shim is not healthy: {status}: {shim_health}")
    if shim_health.get("active_run") is not None:
        raise IsolationError(f"shim already has an active run: {shim_health}")
    got_dir = os.path.realpath(str(shim_health.get("dir") or ""))
    if got_dir != os.path.realpath(state["canonical_evidence_dir"]):
        raise IsolationError(
            f"shim evidence directory mismatch: {got_dir!r} != {state['canonical_evidence_dir']!r}"
        )

    run_id = "isolation-preflight-" + uuid.uuid4().hex
    input_path = pathlib.Path(state["runtime_dir"]) / "probe-input.json"
    payload = _worker_probe_payload(state, args, run_id)
    _write_json_atomic(input_path, payload, 0o444)
    shim_open = egress_open = False
    worker_result: dict[str, Any] = {}
    egress_end: dict[str, Any] = {}
    try:
        _mark(args.shim_control_url, "start", run_id)
        shim_open = True
        _mark(args.egress_control_url, "start", run_id)
        egress_open = True
        inner_script = str(pathlib.Path(state["repository_root"]) / "scripts" /
                           "production_isolation.py")
        command = [sys.executable, inner_script, "_worker-probe",
                   "/run/dra-probe-input.json"]
        result = _run(_isolated_argv(state_path, state, command), check=False)
        try:
            worker_result = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"worker probe returned no valid JSON (rc={result.returncode}): "
                f"stdout={result.stdout[-1000:]!r} stderr={result.stderr[-1000:]!r}"
            ) from exc
        if result.returncode or worker_result.get("passed") is not True:
            raise IsolationError(
                f"worker isolation probe failed (rc={result.returncode}): {worker_result}"
            )
        egress_end = _mark(args.egress_control_url, "end", run_id)
        egress_open = False
        if not isinstance(egress_end.get("merge"), dict):
            raise IsolationError("egress recorder did not acknowledge privileged merge")
        _mark(args.shim_control_url, "end", run_id)
        shim_open = False
    finally:
        if egress_open:
            try:
                _mark(args.egress_control_url, "end", run_id)
            except Exception:
                pass
        if shim_open:
            try:
                _mark(args.shim_control_url, "end", run_id)
            except Exception:
                pass
        input_path.unlink(missing_ok=True)

    source_summary = _evidence_summary(
        pathlib.Path(state["evidence_dir"]) / f"{run_id}.jsonl", run_id,
    )
    canonical_summary = _evidence_summary(
        pathlib.Path(state["canonical_evidence_dir"]) / f"{run_id}.jsonl", run_id,
    )
    if source_summary["starts"] != 1 or source_summary["ends"] != 1:
        raise IsolationError(f"egress probe bracket invalid: {source_summary}")
    if source_summary["fetches"] != 1 or source_summary["blocks"] != 0:
        raise IsolationError(f"egress positive probe was not exactly one fetch: {source_summary}")
    if canonical_summary["starts"] != 1 or canonical_summary["ends"] != 1:
        raise IsolationError(f"canonical probe bracket invalid: {canonical_summary}")
    if canonical_summary["merged_fetches"] != 1:
        raise IsolationError(f"canonical stream lacks the one recorder fetch: {canonical_summary}")

    proof_id = uuid.uuid4().hex
    proof: dict[str, Any] = {
        "schema": PROOF_SCHEMA,
        "proof_id": proof_id,
        "passed": True,
        "run_set_id": state["run_set_id"],
        "backbone": state["backbone"],
        "worker_id": state["worker_id"],
        "worker_uid": state["worker_uid"],
        "worker_gid": state["worker_gid"],
        "namespace": state["namespace"],
        "netns_inode": state["netns_inode"],
        "host_netns_inode": state["host_netns_inode"],
        "host_mountns_inode": state["host_mountns_inode"],
        "repository_root": state["repository_root"],
        "hidden_canary_paths": state["hidden_canary_paths"],
        "network": state["network"],
        "gateway": state["gateway"],
        "proxy_url": state["proxy_url"],
        "allowed_host_ports": state["allowed_host_ports"],
        "nft_sha256": state["nft_sha256"],
        "safe_view_digest": state["safe_view_digest"],
        "chroot": True,
        "state_digest": state["state_digest"],
        "protected_evidence_paths": [
            state["evidence_dir"], state["canonical_evidence_dir"],
        ],
        "worker_probe": worker_result,
        "egress_finalize": egress_end.get("merge"),
        "source_evidence": source_summary,
        "canonical_evidence": canonical_summary,
        "probe_run_id": run_id,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    proof["proof_digest"] = _payload_digest(proof, "proof_digest")
    proof_path = pathlib.Path(state["proof_dir"]) / f"{proof_id}.json"
    _write_json_atomic(proof_path, proof, 0o444)
    check_state(state_path, proof_path)
    print(str(proof_path))
    return 0


def verify_meta(proof_dir: pathlib.Path, meta_path: pathlib.Path) -> dict[str, Any]:
    meta = _load_json(meta_path)
    isolation = meta.get("network_isolation")
    if not isinstance(isolation, dict) or isolation.get("verified") is not True:
        raise IsolationError(f"meta lacks a verified network isolation claim: {meta_path}")
    proof_id = str(isolation.get("proof_id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", proof_id):
        raise IsolationError(f"meta has an unsafe isolation proof id: {meta_path}")
    proof = load_proof(proof_dir / f"{proof_id}.json")
    if isolation.get("proof_digest") != proof["proof_digest"]:
        raise IsolationError(f"meta isolation digest differs from root proof: {meta_path}")
    expected = {
        "worker": str(proof["worker_id"]),
        "backbone": str(proof["backbone"]),
        "run_set": str(proof["run_set_id"]),
    }
    actual = {
        "worker": str(meta.get("worker") or meta.get("run_identity", {}).get("worker") or ""),
        "backbone": str(meta.get("backbone") or ""),
        "run_set": str(meta.get("run_set_id") or meta.get("run_identity", {}).get("run_set_id") or ""),
    }
    # Older sidecar shapes put worker/run-set only in the process environment
    # binding. The proof digest still prevents a worker from swapping proofs.
    for key in ("worker", "backbone", "run_set"):
        if actual[key] and actual[key] != expected[key]:
            raise IsolationError(
                f"meta/proof {key} mismatch: {actual[key]!r} != {expected[key]!r}"
            )
    egress = meta.get("egress_evidence")
    if not isinstance(egress, dict) or egress.get("enforced") is not True:
        raise IsolationError(f"meta lacks enforced egress evidence: {meta_path}")
    merge = egress.get("merge")
    if not isinstance(merge, dict) or merge.get("mode") != "recorder":
        raise IsolationError(f"meta lacks recorder-owned evidence finalization: {meta_path}")
    return {"meta": str(meta_path), "proof_id": proof_id, "proof_digest": proof["proof_digest"]}


def audit_meta(args: argparse.Namespace) -> int:
    proof_dir = pathlib.Path(args.proof_dir).resolve()
    meta_dir = pathlib.Path(args.meta_dir).resolve()
    rows: list[dict[str, Any]] = []
    nonpass: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for path in sorted(meta_dir.glob("*.meta.json")):
        try:
            meta = _load_json(path)
            if meta.get("status") != "pass":
                nonpass.append({"meta": str(path), "status": str(meta.get("status"))})
                continue
            rows.append(verify_meta(proof_dir, path))
        except Exception as exc:  # noqa: BLE001
            errors.append({"meta": str(path), "error": f"{type(exc).__name__}: {exc}"})
    if not rows and not nonpass and not errors:
        errors.append({"meta": str(meta_dir), "error": "no meta files found"})
    report = {
        "schema": "dra.production-isolation-audit.v1",
        "passed": not errors,
        "verified": rows,
        "nonpass_not_scorable": nonpass,
        "errors": errors,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if args.out:
        _write_json_atomic(pathlib.Path(args.out).resolve(), report, 0o644)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


def cleanup(state_path: pathlib.Path) -> int:
    _require_root()
    if not state_path.exists():
        return 0
    state = _load_state(state_path)
    namespace = str(state.get("namespace", ""))
    host_if = str(state.get("host_if", ""))
    if not re.fullmatch(r"dn[0-9a-f]{10}", namespace):
        raise IsolationError(f"refusing to delete unsafe namespace name: {namespace!r}")
    if not re.fullmatch(r"dh[0-9a-f]{10}", host_if):
        raise IsolationError(f"refusing to delete unsafe veth name: {host_if!r}")
    _run(["ip", "netns", "del", namespace], check=False)
    _run(["ip", "link", "del", host_if], check=False)
    runtime = pathlib.Path(str(state.get("runtime_dir", "")))
    if runtime.name == state_path.stem + ".runtime" and runtime.parent == state_path.parent:
        shutil.rmtree(runtime, ignore_errors=True)
    state_path.unlink(missing_ok=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup")
    setup_p.add_argument("--state", required=True)
    setup_p.add_argument("--run-set-id", required=True)
    setup_p.add_argument("--backbone", required=True)
    setup_p.add_argument("--worker-id", type=int, required=True)
    setup_p.add_argument("--egress-port", type=int, required=True)
    setup_p.add_argument("--evidence-dir", required=True)
    setup_p.add_argument("--canonical-evidence-dir", required=True)
    setup_p.add_argument("--raw-dir", required=True)
    setup_p.add_argument("--worker-home", required=True)
    setup_p.add_argument("--proof-dir", required=True)
    setup_p.add_argument("--repository-root", default=str(pathlib.Path.cwd()))
    setup_p.add_argument("--corpus-origins", required=True)
    setup_p.add_argument("--service-origins", required=True)

    get_p = sub.add_parser("get")
    get_p.add_argument("--state", required=True)
    get_p.add_argument("--field", required=True)

    check_p = sub.add_parser("check")
    check_p.add_argument("--state", required=True)
    check_p.add_argument("--proof")

    probe_p = sub.add_parser("probe")
    probe_p.add_argument("--state", required=True)
    probe_p.add_argument("--egress-control-url", required=True)
    probe_p.add_argument("--shim-control-url", required=True)
    probe_p.add_argument("--corpus-url", required=True)
    probe_p.add_argument("--service-url", required=True)
    probe_p.add_argument("--service-direct-url", required=True)

    exec_p = sub.add_parser("exec")
    exec_p.add_argument("--state", required=True)
    exec_p.add_argument("argv", nargs=argparse.REMAINDER)

    cleanup_p = sub.add_parser("cleanup")
    cleanup_p.add_argument("--state", required=True)

    verify_p = sub.add_parser("verify-meta")
    verify_p.add_argument("--proof-dir", required=True)
    verify_p.add_argument("--meta", required=True)

    audit_p = sub.add_parser("audit-meta")
    audit_p.add_argument("--proof-dir", required=True)
    audit_p.add_argument("--meta-dir", required=True)
    audit_p.add_argument("--out")

    worker_p = sub.add_parser("_worker-probe")
    worker_p.add_argument("input")

    mount_p = sub.add_parser("_mount-exec")
    mount_p.add_argument("state")
    mount_p.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "setup":
        return setup(args)
    if args.command == "get":
        state = _load_state(pathlib.Path(args.state).resolve())
        if args.field not in state:
            raise IsolationError(f"unknown state field: {args.field}")
        value = state[args.field]
        print(value if isinstance(value, (str, int, float)) else json.dumps(value))
        return 0
    if args.command == "check":
        state = check_state(
            pathlib.Path(args.state).resolve(),
            pathlib.Path(args.proof).resolve() if args.proof else None,
        )
        print(json.dumps({"ok": True, "namespace": state["namespace"]}, sort_keys=True))
        return 0
    if args.command == "probe":
        return probe(args)
    if args.command == "exec":
        if os.geteuid() != 0:
            raise IsolationError("isolation exec must be launched by root")
        command = list(args.argv)
        if command and command[0] == "--":
            command = command[1:]
        proof_raw = os.environ.get("DRA_ISOLATION_PROOF", "").strip()
        if not proof_raw:
            raise IsolationError("DRA_ISOLATION_PROOF is required for worker exec")
        state = check_state(pathlib.Path(args.state).resolve(), pathlib.Path(proof_raw).resolve())
        os.execvp("ip", _isolated_argv(pathlib.Path(args.state).resolve(), state, command))
    if args.command == "cleanup":
        return cleanup(pathlib.Path(args.state).resolve())
    if args.command == "verify-meta":
        result = verify_meta(
            pathlib.Path(args.proof_dir).resolve(), pathlib.Path(args.meta).resolve(),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "audit-meta":
        return audit_meta(args)
    if args.command == "_worker-probe":
        return worker_probe(pathlib.Path(args.input).resolve())
    if args.command == "_mount-exec":
        command = list(args.argv)
        if command and command[0] == "--":
            command = command[1:]
        return mount_exec(pathlib.Path(args.state).resolve(), command)
    raise IsolationError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IsolationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(6)
