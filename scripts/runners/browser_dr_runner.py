"""Browser acquisition runner for the main Deep Research benchmark.

This file is the V1 bridge for the typed ``browser-dr`` adapter registered in
``integrations.agents``. The important design choice is that browser acquisition
is not a parallel harness: it returns the same markdown report string expected
by ``scripts/run_deep_task.py``, then the existing scorer and leaderboard handle
it exactly like every other framework.

The adapter itself lives at ``integrations/agents/browser_dr/agent.py``. It
drives ``ResearchEnv`` over ``BrowserSandboxBackend`` so pages are fetched by a
real Playwright browser and read through DOM ``innerText``. Search breadth may
still delegate to the local shim, but evidence pages are opened in the browser.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

AGENT_NAME = "browser-dr"

# Standalone acquisition-modality pilot, not a framework x backbone lane. The
# adapter currently constructs BrowserDRAgent without injecting a model policy;
# BrowserDRAgent therefore uses MockPolicy and never calls the requested
# ``model``. Registering it on a DeepSeek/Qwen/GLM board would mislabel a
# deterministic baseline as that backbone. Keep the runner directly callable
# for browser-modality tests until a real policy is injected and identity-probed.
BENCHMARK_ENABLED = False
BENCHMARK_DISABLED_REASON = "default BrowserDRAgent uses MockPolicy and ignores requested backbone"

# The runner only constructs localhost sandbox hosts and passes the shim/proxy
# endpoints supplied by run_deep_task.py. BrowserSandboxBackend resolves the
# three sandbox sentinels to these hosts and never needs open-web access.
STRICT_SANDBOX_ELIGIBLE = True

DEFAULT_TIMEOUT_S = 1800


def _sandbox_hosts_from_env() -> dict[str, str]:
    """Return bare host:port values for AgentServices.sandbox_hosts."""
    defaults = {
        "shopping": "localhost:7770",
        "reddit": "localhost:9999",
        "wiki": "localhost:8090",
    }
    env_keys = {
        "shopping": "SHOPPING",
        "reddit": "REDDIT",
        "wiki": "WIKIPEDIA",
    }
    hosts: dict[str, str] = {}
    for slug, env_key in env_keys.items():
        raw = os.environ.get(env_key) or defaults[slug]
        value = str(raw).strip()
        if value.startswith("http://"):
            value = value[len("http://") :]
        elif value.startswith("https://"):
            value = value[len("https://") :]
        hosts[slug] = value.rstrip("/")
    return hosts


def _format_error(error: str) -> str:
    return f"(browser-dr error: {error})"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    strict_sandbox: bool = False,
) -> str:
    """Run the browser-dr adapter and return leaderboard markdown.

    Args:
        intent: Research brief after ``run_deep_task.py`` resolves sandbox
            placeholders and language instructions.
        model: Backbone model name. The default browser policy is deterministic
            and offline-safe, but a future injected policy uses this field.
        shim_url: Local search shim base, used for SERP breadth.
        proxy_url: Local OpenAI-compatible LLM proxy.
        timeout_s: Hard timeout around the adapter run.
        strict_sandbox: Accepted for the V1 runner contract. The global shim
            strict mode is already set by ``run_deep_task.py`` when requested.

    Returns:
        Markdown report on success. On adapter failure, returns a short
        ``(browser-dr error: ...)`` placeholder so existing scoring and
        leaderboard degenerate filters can exclude the run without changing the
        public score schema.
    """
    del strict_sandbox  # The adapter receives only sandbox hosts and local URLs.

    try:
        from integrations.agents import get_agent
        from integrations.agents.base import AgentResult, AgentServices
    except Exception as exc:  # pragma: no cover - defensive boot guard
        return _format_error(f"{type(exc).__name__}: {exc}")

    services = AgentServices(
        search_url=shim_url,
        llm_url=proxy_url,
        llm_key=os.environ.get("OPENAI_API_KEY") or "anything",
        sandbox_hosts=_sandbox_hosts_from_env(),
        model=model or "deepseek-v4-flash",
    )

    async def _invoke() -> Any:
        agent = get_agent(AGENT_NAME)
        return await agent.run(intent, services)

    try:
        result = await asyncio.wait_for(_invoke(), timeout=float(timeout_s))
    except asyncio.TimeoutError:
        return _format_error(f"TimeoutError: exceeded {timeout_s}s")
    except Exception as exc:
        return _format_error(f"{type(exc).__name__}: {exc}")

    if not isinstance(result, AgentResult):
        return _format_error(f"invalid AgentResult: {type(result).__name__}")
    if result.error:
        return _format_error(str(result.error))

    markdown = str(result.markdown or "").strip()
    if not markdown:
        return _format_error("empty markdown")
    return markdown
