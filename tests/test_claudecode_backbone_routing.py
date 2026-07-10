"""Regression tests for claude-code per-backbone router selection.

Root cause being locked down (2026-07-07): the runner used to point every run
at ONE shared claude-code-router port regardless of --backbone, so the lane
label (qwen/deepseek/glm) and the actual model diverged silently — the subset
"deepseek-v4-flash" passes were really qwen3-8b. These tests pin:

  * the backbone -> dedicated-port mapping (stable, collision-free);
  * the generated ccr config (gateway provider, :8100, maxtoken 8192,
    every Router route pinned to the backbone);
  * the pre-run identity assertion that refuses to run mislabeled;
  * never-kill semantics when a foreign process squats the port;
  * ssh fallback being default-disabled (no more "5090" -> 0.0.19.226);
  * the provenance sidecar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.runners.claudecode_runner as ccrun  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in (
        "CLAUDE_CODE_CCR_URL",
        "CLAUDE_CODE_LOCAL_CCR_URL",
        "CLAUDE_CODE_SSH_HOST",
        "CLAUDE_CODE_GATEWAY_URL",
        "DS_PROXY_URL",
        "DEEP_RUN_REPORT_PATH",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ccrun, "CCR_HOME_BASE", tmp_path / "ccr_homes")
    yield


# ---------------------------------------------------------------------------
# Port mapping
# ---------------------------------------------------------------------------
def test_known_backbones_get_dedicated_ports():
    assert ccrun._port_for_backbone("qwen3-8b") == 3461
    assert ccrun._port_for_backbone("deepseek-v4-flash") == 3462
    assert ccrun._port_for_backbone("glm-4.7-flash") == 3463


def test_unknown_backbone_hashes_into_reserved_range():
    p1 = ccrun._port_for_backbone("mystery-model-7b")
    p2 = ccrun._port_for_backbone("mystery-model-7b")
    assert p1 == p2, "port must be stable across calls"
    assert 3470 <= p1 < 3490
    # and never collides with a known backbone's dedicated port
    assert p1 not in {3461, 3462, 3463}


# ---------------------------------------------------------------------------
# Generated ccr config
# ---------------------------------------------------------------------------
def test_config_pins_every_route_to_backbone():
    cfg = ccrun._build_ccr_config("deepseek-v4-flash", 3462)
    assert cfg["PORT"] == 3462
    assert cfg["APIKEY"] == "anything"
    assert cfg["API_TIMEOUT_MS"] == 600000
    (provider,) = cfg["Providers"]
    assert provider["name"] == "gateway"
    assert provider["api_base_url"] == "http://127.0.0.1:8100/v1/chat/completions"
    assert provider["models"] == ["deepseek-v4-flash"]
    # maxtoken transformer semantics preserved from the old :3457 qwen lane
    assert provider["transformer"] == {"use": [["maxtoken", {"max_tokens": 8192}]]}
    for route in ("default", "background", "think", "longContext", "webSearch"):
        assert cfg["Router"][route] == "gateway,deepseek-v4-flash"


def test_config_uses_runtime_worker_gateway_not_host_loopback():
    gateway = "http://10.240.9.1:8100/v1"
    chat = ccrun._gateway_chat_url(gateway)
    assert chat == "http://10.240.9.1:8100/v1/chat/completions"
    cfg = ccrun._build_ccr_config("deepseek-v4-flash", 3462, chat)
    assert cfg["Providers"][0]["api_base_url"] == chat
    assert ccrun._config_routes_model(cfg, "deepseek-v4-flash", chat)
    assert not ccrun._config_routes_model(
        cfg,
        "deepseek-v4-flash",
        "http://127.0.0.1:8100/v1/chat/completions",
    )


def test_local_tool_policy_uses_exact_runtime_shim_origin():
    args = ccrun._local_tool_policy_args(
        strict_sandbox=True,
        shim_url="http://10.240.9.1:8081",
    )
    assert args[:3] == ["--allowed-tools", "Write", "Edit"]
    bash_tools = args[3:]
    assert bash_tools == ccrun._shim_bash_tools("http://10.240.9.1:8081")
    assert bash_tools and all("10.240.9.1:8081" in item for item in bash_tools)
    assert all("localhost" not in item for item in bash_tools)


# ---------------------------------------------------------------------------
# Selection + env override
# ---------------------------------------------------------------------------
def test_ccr_for_backbone_returns_dedicated_url():
    url, home = ccrun._ccr_for_backbone("qwen3-8b")
    assert url == "http://127.0.0.1:3461"
    assert home is not None and home.name == "qwen3-8b"


def test_env_override_wins_but_is_marked_unverified(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_LOCAL_CCR_URL", "http://127.0.0.1:9999")
    url, home = ccrun._ccr_for_backbone("deepseek-v4-flash")
    assert url == "http://127.0.0.1:9999"
    assert home is None  # unverifiable: no owned config to assert against
    out = capsys.readouterr().out
    assert "override" in out and "unverified" in out


# ---------------------------------------------------------------------------
# Pre-run identity assertion (the anti-mislabeling guard)
# ---------------------------------------------------------------------------
def _write_cfg(home: Path, cfg: dict) -> Path:
    p = ccrun._ccr_config_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_assert_ccr_model_accepts_matching_config(tmp_path):
    home = tmp_path / "h"
    cfg_path = _write_cfg(home, ccrun._build_ccr_config("qwen3-8b", 3461))
    default = ccrun._assert_ccr_model(cfg_path, "http://127.0.0.1:3461", "qwen3-8b")
    assert default == "gateway,qwen3-8b"


def test_assert_ccr_model_rejects_mislabeled_router(tmp_path):
    home = tmp_path / "h"
    # router actually points at qwen while the lane label says deepseek —
    # the exact 2026-07-07 failure mode; must raise, never run.
    cfg_path = _write_cfg(home, ccrun._build_ccr_config("qwen3-8b", 3462))
    with pytest.raises(RuntimeError, match="mislabeled"):
        ccrun._assert_ccr_model(cfg_path, "http://127.0.0.1:3462", "deepseek-v4-flash")


def test_assert_ccr_model_rejects_missing_config(tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        ccrun._assert_ccr_model(
            tmp_path / "nope" / "config.json", "http://127.0.0.1:3461", "qwen3-8b"
        )


# ---------------------------------------------------------------------------
# ensure: never kill a foreign process; idempotent config write
# ---------------------------------------------------------------------------
def test_ensure_refuses_foreign_process_on_port(monkeypatch):
    monkeypatch.setattr(ccrun, "_tcp_listening", lambda *a, **k: True)
    home = ccrun._ccr_home_for_backbone("qwen3-8b")
    # port listening but OUR home has no config -> someone else's process
    with pytest.raises(RuntimeError, match="does not own"):
        ccrun._ensure_ccr_for_backbone("qwen3-8b", "http://127.0.0.1:3461", home)


def test_ensure_refuses_when_owned_config_routes_elsewhere(monkeypatch):
    monkeypatch.setattr(ccrun, "_tcp_listening", lambda *a, **k: True)
    home = ccrun._ccr_home_for_backbone("deepseek-v4-flash")
    _write_cfg(home, ccrun._build_ccr_config("qwen3-8b", 3462))
    with pytest.raises(RuntimeError, match="does not route"):
        ccrun._ensure_ccr_for_backbone(
            "deepseek-v4-flash", "http://127.0.0.1:3462", home
        )


def test_ensure_writes_config_before_start(monkeypatch):
    monkeypatch.setattr(ccrun, "_tcp_listening", lambda *a, **k: False)
    monkeypatch.setattr(ccrun.shutil, "which", lambda name: None)  # no ccr binary
    home = ccrun._ccr_home_for_backbone("deepseek-v4-flash")
    _write_cfg(home, {"PORT": 1, "stale": True})  # stale config gets replaced
    with pytest.raises(RuntimeError, match="ccr executable not found"):
        ccrun._ensure_ccr_for_backbone(
            "deepseek-v4-flash", "http://127.0.0.1:3462", home
        )
    written = json.loads(ccrun._ccr_config_path(home).read_text())
    assert written == ccrun._build_ccr_config("deepseek-v4-flash", 3462)


# ---------------------------------------------------------------------------
# SSH fallback default-disabled
# ---------------------------------------------------------------------------
def test_ssh_host_empty_by_default():
    assert ccrun._ssh_host() == ""


def test_ssh_raises_without_host():
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_SSH_HOST"):
        ccrun._ssh("echo hi")


# ---------------------------------------------------------------------------
# Provenance sidecar
# ---------------------------------------------------------------------------
def test_provenance_sidecar_written(monkeypatch, tmp_path, capsys):
    report = tmp_path / "claude-code__dr_x_0001.md"
    monkeypatch.setenv("DEEP_RUN_REPORT_PATH", str(report))
    monkeypatch.setenv("_FLOWSEARCHER_TASK_ID", "dr_x_0001")
    ccrun._emit_provenance(
        "deepseek-v4-flash",
        "http://127.0.0.1:3462",
        Path("/root/ccr_homes/deepseek-v4-flash/.claude-code-router/config.json"),
        "gateway,deepseek-v4-flash",
    )
    out = capsys.readouterr().out
    assert "router=http://127.0.0.1:3462" in out
    assert "backbone=deepseek-v4-flash" in out
    sidecar = tmp_path / "claude-code__dr_x_0001.provenance.json"
    rec = json.loads(sidecar.read_text())
    assert rec["backbone"] == "deepseek-v4-flash"
    assert rec["router_url"] == "http://127.0.0.1:3462"
    assert rec["config_router_default"] == "gateway,deepseek-v4-flash"
    assert rec["task"] == "dr_x_0001"
    assert rec["timestamp"]
