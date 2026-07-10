"""Run-bracketed token attribution (integrations/ds_proxy/app.py).

Why this is not covered by the old timeline slicing: the aggregator used to cut a
serial `/_mark` timeline into runs. The harness is not serial (measured max
concurrency 2), so two workers interleaved marks in one log. It only ever worked
because the two workers used different `model` values; #39 is single-backbone,
where that accident vanishes. The fix stamps every usage record with the open
run's identity and refuses to open a second run over the first.

USAGE_LOG is a module-level constant read inside `_usage_write`, so the tests
monkeypatch the module attribute, not an env var.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import integrations.ds_proxy.app as app  # noqa: E402


@pytest.fixture
def usage_log(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setattr(app, "USAGE_LOG", str(log))
    monkeypatch.delenv("DRA_WORKER_ID", raising=False)
    app._run_ctx_clear()  # module-global _RUN_CTX persists across tests
    yield log
    app._run_ctx_clear()


def _read(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


# --- bracket lifecycle -----------------------------------------------------

def test_open_bracket_stamps_records(usage_log):
    app._run_ctx_set({"run_id": "r1", "lane": "storm", "task": "t7", "backbone": "qwen"})
    app._usage_write({"model": "qwen", "total_tokens": 42})
    rec = _read(usage_log)[-1]
    assert rec["run_id"] == "r1"
    assert rec["lane"] == "storm"
    assert rec["task"] == "t7"
    assert rec["backbone"] == "qwen"
    assert rec["total_tokens"] == 42


def test_clear_bracket_stops_stamping(usage_log):
    app._run_ctx_set({"run_id": "r1", "lane": "storm"})
    app._run_ctx_clear()
    app._usage_write({"model": "qwen", "total_tokens": 5})
    rec = _read(usage_log)[-1]
    assert "run_id" not in rec
    assert "lane" not in rec


def test_agent_and_task_id_aliases_are_accepted(usage_log):
    # The runner may pass lane as `agent` and task as `task_id`.
    app._run_ctx_set({"run_id": "r1", "agent": "deerflow", "task_id": "t3"})
    app._usage_write({"model": "qwen"})
    rec = _read(usage_log)[-1]
    assert rec["lane"] == "deerflow"
    assert rec["task"] == "t3"


# --- reentrancy: the #39 regression ----------------------------------------

def test_second_run_id_cannot_open_over_first(usage_log):
    app._run_ctx_set({"run_id": "r1", "backbone": "qwen"})
    with pytest.raises(app.RunAlreadyActive):
        app._run_ctx_set({"run_id": "r2", "backbone": "qwen"})
    # The first run stays open and keeps owning the token stream. Under #39 both
    # workers share one `model`, so only this refusal keeps their tokens apart.
    assert app._run_ctx()["run_id"] == "r1"


def test_same_run_id_reopen_is_allowed(usage_log):
    app._run_ctx_set({"run_id": "r1", "lane": "storm"})
    ctx = app._run_ctx_set({"run_id": "r1", "task": "t9"})
    assert ctx["run_id"] == "r1"
    # Re-opening the same run replaces context (clear+update), so the newly
    # supplied task is present.
    assert ctx.get("task") == "t9"


def test_run_id_is_required(usage_log):
    with pytest.raises(ValueError):
        app._run_ctx_set({"lane": "storm"})


def test_reopen_after_clear_succeeds(usage_log):
    app._run_ctx_set({"run_id": "r1"})
    app._run_ctx_clear()
    ctx = app._run_ctx_set({"run_id": "r2"})  # must not still see r1 as open
    assert ctx["run_id"] == "r2"


def test_end_marker_must_own_the_open_run(usage_log):
    client = TestClient(app.app)
    assert client.post("/_mark", json={"phase": "start", "run_id": "owner"}).status_code == 200
    missing = client.post("/_mark", json={"phase": "end"})
    assert missing.status_code == 400
    wrong = client.post("/_mark", json={"phase": "end", "run_id": "sibling"})
    assert wrong.status_code == 409
    assert app._run_ctx()["run_id"] == "owner", "foreign end cleared the owner's bracket"
    assert client.post("/_mark", json={"phase": "end", "run_id": "owner"}).status_code == 200
    assert app._run_ctx() == {}


# --- disabled logging is a silent no-op ------------------------------------

def test_no_write_when_usage_log_unset(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setattr(app, "USAGE_LOG", "")
    app._run_ctx_clear()
    app._run_ctx_set({"run_id": "r1"})
    app._usage_write({"model": "qwen"})
    assert not log.exists()
    app._run_ctx_clear()
