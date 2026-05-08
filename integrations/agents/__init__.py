"""V2 agent registry for the Deep Research benchmark.

Maps canonical leaderboard slugs (e.g. ``"camel-ai"``, ``"baseline-random"``)
to ``(module_path, class_name)`` tuples. Resolution is lazy: importing this
package does NOT import any framework adapter, so a missing ``.venv-storm``
or unavailable ``knowledge_storm`` does not break harness boot.

Use :func:`get_agent` to instantiate an agent by slug::

    from integrations.agents import get_agent
    agent = get_agent("camel-ai")
    result = await agent.run(intent, services)
"""

from __future__ import annotations

import importlib
from typing import Dict, Tuple, Type

from integrations.agents.base import AgentResult, AgentServices, BaseAgent

# Registry of slug -> (module_path, class_name).
# Populated lazily: importing this module does NOT import the targets.
REGISTRY: Dict[str, Tuple[str, str]] = {}


def _register(name: str, module_path: str, class_name: str) -> None:
    """Register an agent slug pointing at a (module, class) pair.

    No import happens here; the target module is loaded only when
    :func:`get_agent` is called for ``name``.
    """
    REGISTRY[name] = (module_path, class_name)


def get_agent_class(name: str) -> "type[BaseAgent]":
    """Resolve ``name`` to the registered :class:`BaseAgent` subclass.

    Use this when you want to inspect the class (for ``cls.name``) without
    instantiating. ``get_agent`` returns an instance.
    """
    if name not in REGISTRY:
        raise KeyError(
            f"agent '{name}' not registered; known slugs: {sorted(REGISTRY)}"
        )
    module_path, class_name = REGISTRY[name]
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def get_agent(name: str) -> BaseAgent:
    """Resolve ``name`` to a fresh :class:`BaseAgent` instance.

    Args:
        name: The canonical leaderboard slug (e.g. ``"camel-ai"``).

    Returns:
        A new instance of the registered :class:`BaseAgent` subclass.

    Raises:
        KeyError: if ``name`` is not registered.
        ImportError: if the target module cannot be imported (e.g. its
            framework dependencies are not installed in the active venv).
        AttributeError: if the module exists but does not define the
            registered class name.
    """
    return get_agent_class(name)()


def list_agents() -> list[str]:
    """Return all registered slugs in deterministic alphabetical order."""
    return sorted(REGISTRY)


# ---------------------------------------------------------------------------
# Framework adapters (10 frameworks). Modules are placeholders; they will be
# created in a later stage when each framework gets ported to the V2 contract.
# ---------------------------------------------------------------------------
_register("camel-ai",        "integrations.agents.camel_ai.agent",        "CamelAIAgent")
_register("deerflow",        "integrations.agents.deerflow.agent",        "DeerflowAgent")
_register("flowsearcher-ds", "integrations.agents.flowsearcher_ds.agent", "FlowSearcherDSAgent")
_register("gpt-researcher",  "integrations.agents.gpt_researcher.agent",  "GPTResearcherAgent")
_register("ii-researcher",   "integrations.agents.ii_researcher.agent",   "IIResearcherAgent")
_register("langchain-odr",   "integrations.agents.langchain_odr.agent",   "LangchainODRAgent")
_register("ldr",             "integrations.agents.ldr.agent",             "LDRAgent")
_register("qx-agents",       "integrations.agents.qx_agents.agent",       "QXAgentsAgent")
_register("smolagents",      "integrations.agents.smolagents.agent",      "SmolagentsAgent")
_register("storm",           "integrations.agents.storm.agent",           "StormAgent")

# ---------------------------------------------------------------------------
# Sanity baselines. These are real (already implemented) and live in
# integrations/agents/baselines/agent.py as thin V2 wrappers.
# ---------------------------------------------------------------------------
_register("baseline-random",      "integrations.agents.baselines.agent", "RandomBaselineAgent")
_register("baseline-stuffer",     "integrations.agents.baselines.agent", "StufferBaselineAgent")
_register("baseline-golden-dump", "integrations.agents.baselines.agent", "GoldenDumpBaselineAgent")


__all__ = [
    "AgentResult",
    "AgentServices",
    "BaseAgent",
    "REGISTRY",
    "get_agent",
    "list_agents",
]
