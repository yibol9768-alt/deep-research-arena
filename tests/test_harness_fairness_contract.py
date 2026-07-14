from __future__ import annotations

import json
from pathlib import Path

import scripts.run_deep_task as rdt


def test_deep_run_out_dir_override_is_resolved_from_repo(monkeypatch):
    monkeypatch.setenv("DEEP_RUN_OUT_DIR", "data/results/run_sets/r1/glm")
    assert rdt._run_output_dir() == rdt.ROOT / "data/results/run_sets/r1/glm"


def test_previous_report_and_meta_are_archived_not_reused(tmp_path):
    report = tmp_path / "a__t.md"
    meta = tmp_path / "a__t.meta.json"
    provenance = report.with_suffix(".provenance.json")
    report.write_text("old weak but real")
    meta.write_text(json.dumps({"attempts": 3, "status": "pass"}))
    provenance.write_text("{}")

    attempts, archive = rdt._archive_previous_outputs(report, meta)
    assert attempts == 3 and archive
    assert not report.exists() and not meta.exists() and not provenance.exists()
    archived = Path(archive)
    assert (archived / report.name).read_text() == "old weak but real"
    assert (archived / meta.name).is_file()


def test_model_probe_uses_the_real_lane_door(monkeypatch):
    monkeypatch.setenv("DS_PROXY_URL", "http://worker-proxy:8088/v1")
    monkeypatch.setenv(
        "CLAUDE_CODE_GATEWAY_URL", "http://worker-gateway:8100/v1/chat/completions"
    )
    assert rdt._model_probe_endpoint("storm") == (
        "http://worker-proxy:8088/v1", "ds-proxy"
    )
    assert rdt._model_probe_endpoint("claude-code") == (
        "http://worker-gateway:8100/v1", "claude-code-gateway"
    )


def test_claude_probe_falls_back_to_the_runner_proxy(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_LOCAL_CCR_URL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CCR_URL", raising=False)
    monkeypatch.setenv("DS_PROXY_URL", "http://worker-proxy:8088/v1")
    assert rdt._model_probe_endpoint("claude-code") == (
        "http://worker-proxy:8088/v1", "claude-code-gateway"
    )


def test_opencode_checks_local_binary_before_requiring_ssh():
    source = (
        Path(rdt.ROOT) / "scripts" / "runners" / "opencode_runner.py"
    ).read_text(encoding="utf-8")
    local = source.index('shutil.which("opencode")')
    remote = source.index('if not SSH_HOST:', local)
    assert local < remote


def test_timeout_override_is_explicitly_nonproduction(monkeypatch):
    monkeypatch.setenv("DRA_WALL_CLOCK_S", "123")
    contract = rdt._timeout_contract()
    assert contract["wall_clock_s"] == 123
    assert "DRA_WALL_CLOCK_S" in contract["operator_overrides"]
    assert contract["production_comparable"] is False
