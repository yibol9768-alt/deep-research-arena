"""V2 thin wrapper around scripts/run_deep_task._run_flowsearcher_ds.

The V1 inline helper takes ``(intent, model)`` and reads ``SHIM_URL`` /
``DS_PROXY_URL`` from process env (plus ``_FLOWSEARCHER_TASK_ID`` set by
the V1 main()).  This wrapper plants the standard env vars from
:class:`AgentServices` before invoking; V1 internals untouched.

NOTE on class name: the registry registers this slug under
``FlowSearcherDSAgent`` (capital 'S' in 'Searcher'), so we match that
spelling exactly so :func:`integrations.agents.get_agent` can resolve it.
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


class FlowSearcherDSAgent(BaseAgent):
    name = "flowsearcher-ds"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        t0 = time.time()
        try:
            from scripts.run_deep_task import _run_flowsearcher_ds as _run
            os.environ["SHIM_URL"] = services.search_url
            os.environ["DS_PROXY_URL"] = services.llm_url
            md = await _run(intent, services.model)
        except Exception as e:  # noqa: BLE001
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"{type(e).__name__}: {e}")
        stripped = md.lstrip()
        if any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES) or len(md.strip()) < 50:
            return AgentResult(markdown="", elapsed_s=time.time() - t0,
                               error=f"runner_placeholder: {md[:200]!r}")
        return AgentResult(markdown=md, elapsed_s=time.time() - t0)
