"""V2 thin wrapper around scripts/run_deep_task._run_gpt_researcher.

The V1 inline helper takes only ``(intent,)`` and reads everything else
(``SHIM_URL``, ``DS_PROXY_URL``, ``OPENAI_BASE_URL``, etc.) from process
env.  This wrapper plants the env vars from :class:`AgentServices` before
invoking; V1 internals untouched.
"""
from __future__ import annotations

import os
import time
from typing import Optional  # noqa: F401

from integrations.agents.base import AgentResult, AgentServices, BaseAgent

_PLACEHOLDER_PREFIXES = (
    "(empty ", "(runner error", "(error", "(timeout", "(no output",
    "(qx-agents produced no report", "(local-deep-research error",
    "(co-storm)", "(stuffer baseline error",
)


class GPTResearcherAgent(BaseAgent):
    name = "gpt-researcher"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        t0 = time.time()
        try:
            from scripts.run_deep_task import _run_gpt_researcher as _run
            os.environ["SHIM_URL"] = services.search_url
            os.environ["DS_PROXY_URL"] = services.llm_url
            os.environ["GPTR_SHIM_URL"] = services.search_url
            md = await _run(intent)
        except Exception as e:  # noqa: BLE001
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"{type(e).__name__}: {e}")
        stripped = md.lstrip()
        if any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES) or len(md.strip()) < 50:
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"runner_placeholder: {md[:200]!r}")
        return AgentResult(markdown=md, elapsed_s=time.time() - t0)
