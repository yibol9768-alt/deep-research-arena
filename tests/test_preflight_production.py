"""Production preflight must fail closed around network evidence checks."""

from __future__ import annotations

import os
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.egress_proxy.app import proxy_env  # noqa: E402
from scripts import preflight  # noqa: E402


def test_direct_corpus_socket_is_a_failed_bypass_check():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        result = preflight.check_direct_sandbox_bypass(
            {f"127.0.0.1:{port}"}, timeout_s=0.2,
        )[0]
    assert result.ok is False
    assert result.required_in_production
    assert "DIRECT BYPASS REACHABLE" in result.detail


def test_production_returns_nonzero_when_required_box_check_skips(
        monkeypatch, capsys,
):
    empty_checks = (
        "check_canary", "check_manifest", "check_parity",
        "check_bracket_self_heal", "check_on_page_link_not_hallucinated",
        "check_sandbox_hosts_agree", "check_sources_alive",
        "check_search_hits_are_in_corpus", "check_backbone_sampling",
        "check_egress_captures_every_transport", "check_no_refetch_at_scoring",
    )
    for name in empty_checks:
        monkeypatch.setattr(preflight, name, lambda: [])
    monkeypatch.setattr(
        preflight, "check_direct_sandbox_bypass",
        lambda: [preflight.CheckResult("direct isolation", True, "blocked",
                                       required_in_production=True)],
    )
    monkeypatch.setattr(preflight, "BOX_ONLY", [("required probe", "not run")])
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--production"])
    assert preflight.main() != 0
    assert "Production checks skipped" in capsys.readouterr().err


def test_egress_preflight_restores_every_environment_key(monkeypatch):
    proxy_keys = tuple(proxy_env("http://127.0.0.1:1"))
    other_keys = (
        "SHIM_EVIDENCE_DIR", "SHIM_EVIDENCE", "DRA_EGRESS_CORPUS",
        "DRA_EGRESS_SERVICES", "DRA_EGRESS_ALLOWED",
    )
    for index, key in enumerate(proxy_keys):
        monkeypatch.setenv(key, f"sentinel-{index}")
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", "/sentinel/evidence")
    monkeypatch.setenv("SHIM_EVIDENCE", "0")
    monkeypatch.setenv("DRA_EGRESS_CORPUS", "127.0.0.1:1")
    monkeypatch.setenv("DRA_EGRESS_SERVICES", "127.0.0.1:2")
    monkeypatch.setenv("DRA_EGRESS_ALLOWED", "127.0.0.1:3")
    keys = proxy_keys + other_keys
    before = {key: os.environ.get(key) for key in keys}

    results = preflight.check_egress_captures_every_transport()

    assert results and all(result.ok for result in results), results
    assert {key: os.environ.get(key) for key in keys} == before
