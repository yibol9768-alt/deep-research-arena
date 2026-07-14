"""Progress signals used by the uniform infrastructure-stall watchdog."""

from __future__ import annotations

from scripts.run_deep_task import _StallWatchdog


class _Response:
    def json(self):
        return {
            "usage_log_bytes": 8910,
            "smoke_budget": {
                "accepted_calls": 23,
                "observed_total_tokens": 4567,
            }
        }


class _Session:
    trust_env = True
    requested = []

    def get(self, url, timeout):
        self.requested.append((url, timeout, self.trust_env))
        return _Response()


def test_watchdog_uses_dsproxy_health_when_host_usage_path_is_hidden(
    monkeypatch,
):
    import requests

    _Session.requested = []
    monkeypatch.setattr(requests, "Session", _Session)
    watchdog = _StallWatchdog(
        stall_timeout_s=900,
        wall_clock_s=None,
        shim_url="http://127.0.0.1:1",
        egress_url=None,
        dsproxy_url="http://10.240.1.1:18510/v1",
        usage_log="/host/path/not-mounted-in-worker.jsonl",
        meta_writer=lambda *args: None,
        t0=0,
    )

    progress = watchdog._progress()

    assert progress[-3:] == (23, 4567, 8910)
    assert _Session.requested == [
        ("http://10.240.1.1:18510/healthz", 5, False),
    ]
