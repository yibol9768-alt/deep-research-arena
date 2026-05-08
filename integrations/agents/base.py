"""V2 agent contract for the Deep Research benchmark.

This module defines the canonical surface every agent (open-source framework
adapter or sanity baseline) implements when it wants to appear on the DR
leaderboard. The V1 contract was an unbound module-level coroutine::

    async def run(intent, model, shim_url, proxy_url) -> str

V2 wraps that signature in a ``BaseAgent`` class so that the harness can:

* discover agents by canonical leaderboard slug (``BaseAgent.name``);
* hand each agent a typed ``AgentServices`` payload (search URL, LLM URL,
  per-sandbox HTTP hosts, optional venv path) instead of four positional args;
* receive a typed ``AgentResult`` (markdown plus elapsed time, error sentinel,
  free-form metadata) so the runner can write ``.md.error`` files on failure
  and skip scoring without monkey-patching error strings into the report.

Internals of existing ``scripts/runners/*_runner.py`` modules stay 100%
unchanged. Each V2 agent class is a thin shim that unpacks ``AgentServices``
into the V1 signature its underlying runner already speaks.

CONTRIBUTING: writing a third-party agent
-----------------------------------------

Drop a new module under ``integrations/agents/<your_slug>/agent.py`` whose
class subclasses :class:`BaseAgent` and is registered in
``integrations/agents/__init__.py``::

    # integrations/agents/myframework/agent.py
    from __future__ import annotations
    import time
    import httpx
    from integrations.agents.base import AgentResult, AgentServices, BaseAgent

    class MyFrameworkAgent(BaseAgent):
        name = "myframework"          # canonical leaderboard slug
        venv = None                   # set to Path("/.venv-myfw") for subprocess agents

        async def run(self, intent: str, services: AgentServices) -> AgentResult:
            t0 = time.time()
            try:
                # Route every search through services.search_url (Tavily-compat)
                # and every LLM call through services.llm_url with services.llm_key.
                async with httpx.AsyncClient() as cli:
                    resp = await cli.post(
                        f"{services.llm_url}/chat/completions",
                        headers={"Authorization": f"Bearer {services.llm_key}"},
                        json={"model": services.model, "messages": [...]},
                    )
                report_md = my_framework_pipeline(intent, resp.json())
                return AgentResult(markdown=report_md, elapsed_s=time.time() - t0)
            except Exception as e:
                return AgentResult(markdown="", elapsed_s=time.time() - t0,
                                   error=f"{type(e).__name__}: {e}")

Then register the slug in ``integrations/agents/__init__.py``::

    _register("myframework", "integrations.agents.myframework.agent",
              "MyFrameworkAgent")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentServices:
    """Endpoints and secrets passed to an agent's ``run()`` method.

    Attributes:
        search_url: Tavily/Brave/Serper/DDG/SearxNG-compatible search shim
            (e.g. ``http://localhost:8081``). Every web search the agent
            performs MUST be routed here.
        llm_url: OpenAI- and Anthropic-compatible LLM passthrough
            (e.g. ``http://localhost:8081/llm``). Every model call MUST go
            through this endpoint so the harness can meter tokens.
        llm_key: Opaque bearer token for ``llm_url``. The gateway accepts
            any non-empty string; the agent must still send it in the
            ``Authorization`` header for SDK compatibility.
        sandbox_hosts: Direct host:port mapping for the three sandbox
            backends. Agents normally do NOT hit these directly; they exist
            for adapters that need to construct canonical URLs offline
            (e.g. ``{"shopping": "localhost:7770", "reddit": "localhost:9999",
            "wiki": "localhost:8090"}``).
        model: Backbone model name forwarded to ``llm_url``. Defaults to
            ``deepseek-v4-flash``; the DS proxy will inject
            ``thinking:disabled`` automatically.
        venv: Path to the framework's own venv when the agent runs as a
            subprocess. ``None`` for in-process agents.
    """

    search_url: str
    llm_url: str
    llm_key: str
    sandbox_hosts: dict
    model: str = "deepseek-v4-flash"
    venv: Optional[Path] = None


@dataclass
class AgentResult:
    """Return value of :meth:`BaseAgent.run`.

    Attributes:
        markdown: The final report as markdown text. ``""`` (empty string)
            iff the runner errored; in that case the harness writes a
            ``.md.error`` companion file and skips scoring.
        elapsed_s: Wall-clock seconds spent inside ``run()``. The runner
            should set this; the harness does not override it.
        error: Human-readable failure description, e.g.
            ``"TimeoutError: subprocess after 1500s"``. ``None`` on success.
        metadata: Free-form per-agent telemetry: token usage, cost, retry
            count, intermediate file paths, etc. Survives into the leaderboard
            ``.meta.json`` sidecar untouched.
    """

    markdown: str
    elapsed_s: float = 0.0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class every benchmark agent subclasses.

    Subclasses MUST set the ``name`` class attribute to their canonical
    leaderboard slug (matches the filename pattern
    ``data/results/deep/<name>__<task>_matrix.md``).

    Subclasses SHOULD set the ``venv`` class attribute to a Path if the
    framework launches a subprocess in its own virtualenv; in-process
    agents leave it as ``None``.
    """

    # Canonical leaderboard slug. MUST be overridden by subclasses; we
    # deliberately do not provide a default so a missing override raises
    # AttributeError early instead of silently writing to a wrong path.
    name: str

    # Optional path to the framework's own venv. Subprocess agents set this
    # so the harness can sanity-check that the venv exists before launching.
    venv: Optional[Path] = None

    @abstractmethod
    async def run(self, intent: str, services: AgentServices) -> AgentResult:
        """Execute the deep-research task for ``intent``.

        Args:
            intent: The research query / task description (raw, untruncated).
            services: Endpoints and secrets the agent must use for search
                and LLM calls. See :class:`AgentServices`.

        Returns:
            An :class:`AgentResult`. On failure, populate ``error`` and
            leave ``markdown`` empty; do NOT raise out of ``run()`` because
            the harness uses the typed result to decide whether to score.
        """
        raise NotImplementedError
