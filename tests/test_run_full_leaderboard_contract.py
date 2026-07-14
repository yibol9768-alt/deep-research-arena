from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_full_leaderboard.sh"


def _run_until_queue_check(tmp_path: Path, **updates: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for name in (
        "DRA_EGRESS_ENFORCED",
        "DRA_EGRESS_PORT",
        "DRA_QX_ADAPTER_PORT",
        "SHOPPING",
        "REDDIT",
        "WIKIPEDIA",
    ):
        env.pop(name, None)
    env.update({
        "PYTHON": sys.executable,
        "DEEP_RESULTS_ROOT": str(tmp_path / "runs"),
        "RUN_SET_ID": "shell-contract",
        "BACKBONE": "model-a",
        **updates,
    })
    return subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path / "missing-queue.tsv")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_formal_shell_does_not_require_operator_enforcement_claim(tmp_path):
    result = _run_until_queue_check(tmp_path)
    assert result.returncode == 2
    assert "queue file" in result.stderr


@pytest.mark.parametrize("value", ["1", "true", "TrUe", "yes", "ON"])
def test_formal_shell_ignores_operator_truthy_enforcement(value, tmp_path):
    result = _run_until_queue_check(tmp_path, DRA_EGRESS_ENFORCED=value)
    assert result.returncode == 2
    assert "queue file" in result.stderr


def test_formal_shell_rejects_retired_store_port_17770(tmp_path):
    result = _run_until_queue_check(
        tmp_path,
        DRA_EGRESS_ENFORCED="1",
        SHOPPING="http://localhost:17770",
    )
    assert result.returncode == 6
    assert "retired internal port 17770" in result.stderr


def test_shell_owns_one_separate_egress_recorder_per_worker():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "EGRESS_PORT=${DRA_EGRESS_PORT:-$((18099 + WORKER_ID))}" in text
    assert "QX_ADAPTER_PORT=${DRA_QX_ADAPTER_PORT:-$((19000 + WORKER_ID))}" in text
    assert "export DRA_QX_ADAPTER_PORT=$QX_ADAPTER_PORT" in text
    assert "export SHIM_EVIDENCE_DIR=${SHIM_EVIDENCE_DIR:-${EVIDENCE_ROOT}/worker-${WORKER_ID}}" in text
    assert "export DRA_EGRESS_EVIDENCE_DIR=${EVIDENCE_ROOT}/egress-worker-${WORKER_ID}" in text
    assert 'SHIM_EVIDENCE_DIR="$DRA_EGRESS_EVIDENCE_DIR" \\\nSHIM_EVIDENCE=1 \\' in text
    assert '"$PYTHON" -m integrations.egress_proxy.app' in text
    assert "CANONICAL_SHIM_EVIDENCE_DIR=$SHIM_EVIDENCE_DIR" in text
    assert (
        'DRA_EGRESS_CANONICAL_EVIDENCE_DIR="$CANONICAL_SHIM_EVIDENCE_DIR"'
        in text
    )
    assert "trap cleanup_production_boundary EXIT" in text


def test_shell_starts_owned_door_only_after_manifest_and_checks_readiness():
    text = SCRIPT.read_text(encoding="utf-8")
    manifest_verify = text.index("--compare-current-env")
    launch = text.index('"$PYTHON" -m integrations.egress_proxy.app')
    shim_status = text.index("SHIM_STATUS=$(curl")
    assert manifest_verify < launch < shim_status
    assert 'sock.bind((sys.argv[1], int(sys.argv[2])))' in text
    assert "curl --noproxy '*'" in text
    assert 'health.get("recording") is True' in text
    assert 'health.get("active_run") is None' in text
    assert 'health.get("server_merge") is True' in text


def test_shell_requires_kernel_boundary_not_a_boolean():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "unset DRA_EGRESS_ENFORCED DRA_ISOLATION_ACTIVE DRA_ISOLATION_PROOF" in text
    assert "production_isolation.py setup" in text
    assert "production_isolation.py probe" in text
    assert "production_isolation.py exec" in text
    assert "production_isolation.py verify-meta" in text
    assert "production_isolation.py audit-meta" in text
    assert "production_isolation.py cleanup" in text
    assert text.index("production_isolation.py probe") < text.index(
        "export DRA_EGRESS_ENFORCED=1"
    )


def test_shell_origin_contract_separates_corpus_from_services():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DS_PROXY_URL=${DS_PROXY_URL:-http://localhost:8100/v1}" in text
    assert 'export DRA_EGRESS_CORPUS=${ORIGIN_OUTPUT%%$\'\\n\'*}' in text
    assert 'export DRA_EGRESS_SERVICES=${ORIGIN_OUTPUT#*$\'\\n\'}' in text
    assert 'for port in [8100, *range(3461, 3464), *range(3470, 3490), qx_port]' in text
    assert 'out.add(f"localhost:{port}")' in text
    assert 'out.add(f"127.0.0.1:{port}")' in text
    assert "egress corpus/service origins overlap" in text


def test_shell_selects_composite_runtime_and_checks_queued_imports():
    text = SCRIPT.read_text(encoding="utf-8")
    assert ".venv-dra-runtime/bin/python" in text
    assert ".venv-camel/bin/python" in text
    for module in ("camel", "open_deep_research", "smolagents", "dspy"):
        assert f"RUNTIME_MODULES+=({module})" in text


def test_odr_uses_attested_worktree_source_not_stale_editable_checkout():
    task_runner = (ROOT / "scripts" / "run_deep_task.py").read_text(
        encoding="utf-8"
    )
    source_decl = task_runner.index(
        'ODR_SOURCE_ROOT = ROOT / "third_party" / '
        '"langchain-open-deep-research" / "src"'
    )
    path_insert = task_runner.index("sys.path.insert(0, odr_source)")
    native_import = task_runner.index(
        "import open_deep_research.deep_researcher as odr"
    )
    assert source_decl < path_insert < native_import


def test_shell_binds_nonpass_outcomes_before_final_audit():
    text = SCRIPT.read_text(encoding="utf-8")
    run_failed = text.index('if [ "$run_rc" -ne 0 ]')
    bind_outcome = text.index('scripts/verify_run_set.py bind-outcome', run_failed)
    final_audit = text.index('scripts/verify_run_set.py audit', bind_outcome)
    assert run_failed < bind_outcome < final_audit
    assert "OUTCOME_STATUS=stalled" in text
    assert "OUTCOME_STATUS=timeout" in text
    assert "OUTCOME_STATUS=infra_abort" in text


def test_shell_uses_long_service_timeout_without_weakening_corpus_timeout():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'DRA_MODEL_PROBE_TIMEOUT_S=${DRA_MODEL_PROBE_TIMEOUT_S:-360}' in text
    assert 'DRA_EGRESS_SERVICE_READ_TIMEOUT_S=${DRA_EGRESS_SERVICE_READ_TIMEOUT_S:-600}' in text


def test_stdout_sensitive_control_plane_uses_quiet_stdlib_python():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CONTROL_PYTHON=${DRA_CONTROL_PYTHON:-python3}' in text
    assert 'ORIGIN_OUTPUT=$("$CONTROL_PYTHON" -' in text
    assert 'ISOLATION_TOKEN=$("$CONTROL_PYTHON" -' in text
    assert 'PROOF_PATH=$("$CONTROL_PYTHON" scripts/production_isolation.py probe' in text
