from __future__ import annotations

import asyncio
from typing import Any

from integrations.agents.base import AgentResult
from scripts import plan_full_leaderboard
from scripts.runners import browser_dr_runner
from scripts.runners.registry import discover


def test_browser_dr_runner_is_discovered_by_main_registry() -> None:
    runners, errors = discover()

    assert "browser-dr" in runners
    assert "browser_dr_runner" not in errors
    assert runners["browser-dr"].__module__ == "scripts.runners.browser_dr_runner"


def test_browser_dr_is_in_default_full_leaderboard_queue() -> None:
    assert "browser-dr" in plan_full_leaderboard.DEFAULT_AGENTS


def test_browser_dr_runner_returns_adapter_markdown(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeBrowserAgent:
        async def run(self, intent: str, services: Any) -> AgentResult:
            captured["intent"] = intent
            captured["services"] = services
            return AgentResult(
                markdown=(
                    "# Browser Report\n\n"
                    "The browser opened the sandbox page and cited it "
                    "[product](http://localhost:7770/product.html).\n"
                ),
                elapsed_s=0.2,
                metadata={"modality": "browser"},
            )

    import integrations.agents as agents

    monkeypatch.setattr(agents, "get_agent", lambda name: FakeBrowserAgent())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SHOPPING", "http://localhost:7770/")
    monkeypatch.setenv("REDDIT", "http://localhost:9999/")
    monkeypatch.setenv("WIKIPEDIA", "http://localhost:8090/")

    out = asyncio.run(
        browser_dr_runner.run(
            "compare sandbox evidence",
            "deepseek-v4-flash",
            "http://localhost:8081",
            "http://localhost:8088/v1",
            strict_sandbox=True,
        )
    )

    assert out.startswith("# Browser Report")
    assert captured["intent"] == "compare sandbox evidence"
    services = captured["services"]
    assert services.search_url == "http://localhost:8081"
    assert services.llm_url == "http://localhost:8088/v1"
    assert services.llm_key == "test-key"
    assert services.model == "deepseek-v4-flash"
    assert services.sandbox_hosts == {
        "shopping": "localhost:7770",
        "reddit": "localhost:9999",
        "wiki": "localhost:8090",
    }


def test_browser_dr_runner_errors_become_degenerate_placeholder(monkeypatch) -> None:
    class FakeFailingAgent:
        async def run(self, intent: str, services: Any) -> AgentResult:
            return AgentResult(
                markdown="",
                elapsed_s=0.0,
                error="ImportError: playwright not installed",
                metadata={"modality": "browser"},
            )

    import integrations.agents as agents

    monkeypatch.setattr(agents, "get_agent", lambda name: FakeFailingAgent())

    out = asyncio.run(
        browser_dr_runner.run(
            "intent",
            "deepseek-v4-flash",
            "http://localhost:8081",
            "http://localhost:8088/v1",
        )
    )

    assert out == "(browser-dr error: ImportError: playwright not installed)"
