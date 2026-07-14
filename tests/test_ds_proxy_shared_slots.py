"""Cross-process admission control for a shared upstream account."""

from __future__ import annotations

import asyncio
import ipaddress
import json

from integrations.ds_proxy import app


def test_shared_upstream_slot_serializes_callers(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SHARED_SLOTS_DIR", str(tmp_path / "slots"))
    monkeypatch.setattr(app, "SHARED_SLOTS", 1)
    monkeypatch.setattr(app, "SHARED_SLOT_POLL_S", 0.01)

    async def exercise():
        first = await app._shared_slot_acquire()
        waiter = asyncio.create_task(app._shared_slot_acquire())
        await asyncio.sleep(0.04)
        assert not waiter.done()
        app._shared_slot_release(first)
        second = await asyncio.wait_for(waiter, timeout=1)
        app._shared_slot_release(second)

    asyncio.run(exercise())


def test_shared_upstream_slot_disabled(monkeypatch):
    monkeypatch.setattr(app, "SHARED_SLOTS", 0)
    assert asyncio.run(app._shared_slot_acquire()) is None


def test_smoke_budget_stops_after_calls_and_tokens(monkeypatch):
    monkeypatch.setattr(app, "MAX_CALLS", 2)
    monkeypatch.setattr(app, "MAX_TOTAL_TOKENS", 10)
    monkeypatch.setattr(app, "_ACCEPTED_CALLS", 0)
    monkeypatch.setattr(app, "_OBSERVED_TOTAL_TOKENS", 0)

    assert app._budget_admit() is None
    app._budget_record_tokens({"prompt_tokens": 4, "completion_tokens": 1})
    assert app._budget_admit() is None
    app._budget_record_tokens({"total_tokens": 7})
    assert "call limit" in (app._budget_admit() or "")

    monkeypatch.setattr(app, "MAX_CALLS", 0)
    assert "token limit" in (app._budget_admit() or "")


def test_client_network_gate_allows_only_declared_worker_cidr(monkeypatch):
    monkeypatch.setattr(app, "ALLOWED_CLIENT_NETWORKS", (
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.240.0.0/16"),
    ))
    assert app._client_ip_allowed("127.0.0.1")
    assert app._client_ip_allowed("10.240.23.2")
    assert not app._client_ip_allowed("172.30.0.1")
    assert not app._client_ip_allowed("not-an-ip")


def test_usage_write_keeps_admission_context_after_bracket_closes(
    tmp_path, monkeypatch,
):
    usage = tmp_path / "usage.jsonl"
    monkeypatch.setattr(app, "USAGE_LOG", str(usage))
    monkeypatch.setattr(app, "_RUN_CTX", {})

    admitted = {"run_id": "run-before-close", "lane": "qx-agents"}
    app._usage_write(
        {"model": "gpt-5.6-luna", "total_tokens": 17},
        run_ctx=admitted,
    )

    row = json.loads(usage.read_text())
    assert row["run_id"] == "run-before-close"
    assert row["lane"] == "qx-agents"
    assert row["total_tokens"] == 17
