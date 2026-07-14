"""Cross-process admission control for a shared upstream account."""

from __future__ import annotations

import asyncio

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
