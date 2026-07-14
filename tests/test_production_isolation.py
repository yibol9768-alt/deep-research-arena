"""Fail-closed contracts for the formal worker network boundary."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import production_isolation as isolation  # noqa: E402
from scripts.runners import _egress  # noqa: E402


def test_operator_boolean_is_not_enforcement(monkeypatch):
    monkeypatch.setenv("DRA_EGRESS_PROXY", "http://127.0.0.1:18099")
    monkeypatch.setenv("DRA_EGRESS_ENFORCED", "1")
    monkeypatch.delenv("DRA_ISOLATION_PROOF", raising=False)
    assert not _egress.enforced()


def test_remote_boolean_is_not_enforcement(monkeypatch):
    monkeypatch.setattr(_egress, "enforced", lambda env=None: True)
    monkeypatch.setenv("DRA_REMOTE_EGRESS_PROXY", "http://127.0.0.1:39099")
    monkeypatch.setenv("DRA_REMOTE_EGRESS_ENFORCED", "1")
    monkeypatch.delenv("DRA_REMOTE_ISOLATION_PROOF", raising=False)
    assert not _egress.remote_enforced()


def test_nft_policy_is_default_drop_and_gateway_scoped():
    rules = isolation._nft_rules("10.240.1.1", "dw0123456789", [18099, 8081, 8100])
    assert rules.count("policy drop") == 2
    assert "ip daddr 10.240.1.1 tcp dport @service_ports accept" in rules
    assert "0.0.0.0/0" not in rules and "accept all" not in rules
    assert "meta l4proto tcp reject with tcp reset" in rules


def test_root_host_context_cannot_reuse_worker_proof(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("root ownership is required for proof-file contract")
    os.chmod(tmp_path, 0o755)
    proof = {
        "schema": isolation.PROOF_SCHEMA,
        "proof_id": "0" * 32,
        "passed": True,
        "worker_uid": 60001,
        "worker_gid": 60001,
        "netns_inode": os.stat("/proc/self/ns/net").st_ino + 1,
        "host_netns_inode": os.stat("/proc/self/ns/net").st_ino,
        "host_mountns_inode": os.stat("/proc/self/ns/mnt").st_ino,
        "proxy_url": "http://10.240.0.1:18099",
        "run_set_id": "rs",
        "worker_id": 1,
        "backbone": "b",
        "protected_evidence_paths": [],
        "hidden_canary_paths": [],
        "repository_root": str(tmp_path),
    }
    proof["proof_digest"] = isolation._payload_digest(proof, "proof_digest")
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(proof), encoding="utf-8")
    path.chmod(0o444)
    monkeypatch.setenv("DRA_ISOLATION_PROOF", str(path))
    monkeypatch.setenv("DRA_ISOLATION_ACTIVE", "1")
    monkeypatch.setenv("DRA_EGRESS_PROXY", proof["proxy_url"])
    monkeypatch.setenv("DRA_EGRESS_SERVER_MERGE", "1")
    monkeypatch.setenv("DRA_RUN_SET_ID", "rs")
    monkeypatch.setenv("DRA_WORKER_ID", "1")
    monkeypatch.setenv("DRA_BACKBONE", "b")
    details = isolation.current_context_details()
    assert not details["verified"]
    assert details["checks"]["uid"] is False


def test_state_and_proof_digests_detect_mutation():
    state = {"schema": isolation.SCHEMA, "namespace": "dn0123456789"}
    state["state_digest"] = isolation._state_digest(state)
    assert state["state_digest"] == isolation._state_digest(state)
    state["namespace"] = "dn9876543210"
    assert state["state_digest"] != isolation._state_digest(state)


def test_default_route_ignores_ipv6_null_entry(tmp_path, monkeypatch):
    ipv4 = tmp_path / "route"
    ipv4.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n",
        encoding="utf-8",
    )
    ipv6 = tmp_path / "ipv6_route"
    ipv6.write_text(
        "0" * 32 + " 00 " + "0" * 32 + " 00 " + "0" * 32
        + " ffffffff 00000001 00000000 00200200 lo\n",
        encoding="utf-8",
    )
    real_read_text = pathlib.Path.read_text

    def fake_read_text(path, *args, **kwargs):
        if str(path) == "/proc/net/route":
            return real_read_text(ipv4, *args, **kwargs)
        if str(path) == "/proc/net/ipv6_route":
            return real_read_text(ipv6, *args, **kwargs)
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", fake_read_text)
    assert isolation._has_default_route() is False


def test_default_route_detects_usable_ipv6_default(tmp_path, monkeypatch):
    ipv4 = tmp_path / "route"
    ipv4.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n",
        encoding="utf-8",
    )
    ipv6 = tmp_path / "ipv6_route"
    ipv6.write_text(
        "0" * 32 + " 00 " + "0" * 32 + " 00 " + "0" * 32
        + " 00000400 00000000 00000000 00000003 eth0\n",
        encoding="utf-8",
    )
    real_read_text = pathlib.Path.read_text

    def fake_read_text(path, *args, **kwargs):
        if str(path) == "/proc/net/route":
            return real_read_text(ipv4, *args, **kwargs)
        if str(path) == "/proc/net/ipv6_route":
            return real_read_text(ipv6, *args, **kwargs)
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", fake_read_text)
    assert isolation._has_default_route() is True


def test_formal_launcher_uses_kernel_exec_and_live_probe():
    text = (ROOT / "scripts" / "run_full_leaderboard.sh").read_text(encoding="utf-8")
    assert "production_isolation.py setup" in text
    assert "production_isolation.py probe" in text
    assert "production_isolation.py exec" in text
    assert "production_isolation.py cleanup" in text
    assert "DRA_ISOLATION_PROOF" in text
    assert "DRA_EGRESS_CANONICAL_EVIDENCE_DIR" in text
    source = (ROOT / "scripts" / "production_isolation.py").read_text(encoding="utf-8")
    assert '"unshare", "--mount", "--pid"' in source
    assert "os.chroot(rootfs)" in source
    assert "hidden_gold_read_attempts" in source
    assert '"safe_data"' in source and '"safe_scripts"' in source
    assert '"run_manifest.py"' in source
    assert '(safe_verifiers / "__init__.py").write_text("", encoding="utf-8")' in source
