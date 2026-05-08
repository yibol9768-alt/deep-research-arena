"""V2 wrappers for the three sanity baselines.

Each baseline already exposes the V1 module-level coroutine

    async def run(intent, model, shim_url, proxy_url) -> str

inside its own module (``random.py``, ``stuffer.py``, ``golden_dump.py``).
The classes below are thin shims that adapt the V1 signature to the V2
:class:`BaseAgent` contract: they unpack :class:`AgentServices` into the
four positional arguments the existing module functions expect, time the
call, and wrap the result string in :class:`AgentResult`.

Internals of ``random.py`` / ``stuffer.py`` / ``golden_dump.py`` are NOT
modified.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from integrations.agents.base import AgentResult, AgentServices, BaseAgent

# The shared V1 signature every baseline module exports.
_V1Run = Callable[[str, str, str, str], Awaitable[str]]


async def _invoke(v1_run: _V1Run, intent: str, services: AgentServices) -> AgentResult:
    """Adapt a V1 baseline coroutine to the V2 :class:`AgentResult` contract.

    Errors raised by the underlying baseline are caught and surfaced via
    :attr:`AgentResult.error`; markdown is left empty on failure so the
    harness writes a ``.md.error`` companion file and skips scoring.
    Baselines that signal failure via a sentinel ``"(... error: ...)"``
    string are passed through verbatim — the harness already understands
    that idiom from V1.
    """
    t0 = time.time()
    try:
        text = await v1_run(intent, services.model, services.search_url, services.llm_url)
        return AgentResult(markdown=text, elapsed_s=time.time() - t0)
    except Exception as exc:  # noqa: BLE001 — baselines must never crash the harness
        return AgentResult(
            markdown="",
            elapsed_s=time.time() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )


class RandomBaselineAgent(BaseAgent):
    """Wrap :mod:`integrations.agents.baselines.random` for V2 dispatch."""

    name = "baseline-random"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        from . import random as _r
        return await _invoke(_r.run, intent, services)


class StufferBaselineAgent(BaseAgent):
    """Wrap :mod:`integrations.agents.baselines.stuffer` for V2 dispatch."""

    name = "baseline-stuffer"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        from . import stuffer as _s
        return await _invoke(_s.run, intent, services)


class GoldenDumpBaselineAgent(BaseAgent):
    """Wrap :mod:`integrations.agents.baselines.golden_dump` for V2 dispatch."""

    name = "baseline-golden-dump"
    venv = None

    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        from . import golden_dump as _g
        return await _invoke(_g.run, intent, services)


__all__ = [
    "RandomBaselineAgent",
    "StufferBaselineAgent",
    "GoldenDumpBaselineAgent",
]
