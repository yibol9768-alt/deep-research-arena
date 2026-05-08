"""V2 thin wrapper around scripts/runners/ldr_runner.py.

Internals of the V1 runner are NOT modified; this class only adapts the
V1 callable signature ``(intent, model, shim_url, proxy_url) -> str`` to
the V2 :class:`BaseAgent` contract and demotes runner-emitted placeholder
sentinels (``"(local-deep-research error: ...)"``) to a typed error so the
harness skips scoring.
"""
from __future__ import annotations

import time
from typing import Optional  # noqa: F401

from integrations.agents.base import AgentResult, AgentServices, BaseAgent

_PLACEHOLDER_PREFIXES = (
    "(empty ", "(runner error", "(error", "(timeout", "(no output",
    "(qx-agents produced no report", "(local-deep-research error",
    "(co-storm)", "(stuffer baseline error",
)


class LDRAgent(BaseAgent):
    name = "ldr"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        t0 = time.time()
        try:
            from scripts.runners.ldr_runner import run as _run
            md = await _run(intent, services.model, services.search_url, services.llm_url)
        except Exception as e:  # noqa: BLE001
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"{type(e).__name__}: {e}")
        stripped = md.lstrip()
        if any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES) or len(md.strip()) < 50:
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"runner_placeholder: {md[:200]!r}")
        return AgentResult(markdown=md, elapsed_s=time.time() - t0)
