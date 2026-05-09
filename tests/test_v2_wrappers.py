"""Unit tests for the 10 V2 BaseAgent framework wrappers.

These tests verify the *adapter* behaviour of every wrapper class registered
under :mod:`integrations.agents` WITHOUT actually invoking the underlying
research framework (no dspy, no langchain, no subprocess venv needed).

Strategy
--------
Each wrapper does a *lazy* ``from <upstream_module> import <callable>`` inside
its async ``run()`` body, then awaits the callable. We swap the upstream
callable with a fake before invoking the wrapper:

* For modules that import cleanly on Mac (deerflow / ldr / qx runners and
  ``scripts.run_deep_task``) we use :func:`pytest.MonkeyPatch.setattr` on the
  dotted-path string so the lazy ``from`` resolves to the fake.
* ``scripts.runners.storm_runner`` pulls in :mod:`dspy` at import time, which
  is only installed in storm's separate venv. We pre-populate
  ``sys.modules["scripts.runners.storm_runner"]`` with a
  :class:`types.SimpleNamespace` whose ``run`` attribute is the fake; that
  short-circuits the lazy import entirely.

Each agent gets three cases:

a) success: fake returns a >=1000-char realistic markdown report
   ⇒ ``result.markdown`` equals that text, ``result.error`` is ``None``.
b) placeholder: fake returns ``"(empty storm output)"``
   ⇒ ``result.error.startswith("runner_placeholder:")``, markdown is empty.
c) raise: fake raises ``RuntimeError("boom")``
   ⇒ ``result.error.startswith("RuntimeError:")``, markdown is empty.

Total: 10 agents * 3 cases = 30 tests.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

# Make the repo root importable regardless of pytest invocation cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.agents.base import AgentServices  # noqa: E402


# ---------------------------------------------------------------------------
# Per-agent configuration: slug -> (wrapper_module, wrapper_class,
# upstream_dotted_path, needs_sys_modules_stub).
# ``upstream_dotted_path`` is what the wrapper's lazy ``from`` resolves to
# (e.g. ``scripts.runners.storm_runner.run`` or
# ``scripts.run_deep_task._run_camel``).  When ``needs_sys_modules_stub`` is
# True, we install the upstream module as a SimpleNamespace in ``sys.modules``
# rather than monkeypatching a real module attribute.
# ---------------------------------------------------------------------------
AGENT_TABLE = [
    # (slug, wrapper_module, wrapper_class, upstream_module, upstream_attr,
    #  needs_stub)
    ("camel-ai",
     "integrations.agents.camel_ai.agent", "CamelAIAgent",
     "scripts.run_deep_task", "_run_camel", False),
    ("deerflow",
     "integrations.agents.deerflow.agent", "DeerflowAgent",
     "scripts.runners.deerflow_runner", "run", False),
    ("flowsearcher-ds",
     "integrations.agents.flowsearcher_ds.agent", "FlowSearcherDSAgent",
     "scripts.run_deep_task", "_run_flowsearcher_ds", False),
    ("gpt-researcher",
     "integrations.agents.gpt_researcher.agent", "GPTResearcherAgent",
     "scripts.run_deep_task", "_run_gpt_researcher", False),
    ("ii-researcher",
     "integrations.agents.ii_researcher.agent", "IIResearcherAgent",
     "scripts.run_deep_task", "_run_ii_researcher", False),
    ("langchain-odr",
     "integrations.agents.langchain_odr.agent", "LangchainODRAgent",
     "scripts.run_deep_task", "_run_langchain_odr", False),
    ("ldr",
     "integrations.agents.ldr.agent", "LDRAgent",
     "scripts.runners.ldr_runner", "run", False),
    ("qx-agents",
     "integrations.agents.qx_agents.agent", "QXAgentsAgent",
     "scripts.runners.qx_runner", "run", False),
    ("smolagents",
     "integrations.agents.smolagents.agent", "SmolagentsAgent",
     "scripts.run_deep_task", "_run_smolagents", False),
    # storm imports dspy at module top => we MUST stub via sys.modules.
    ("storm",
     "integrations.agents.storm.agent", "StormAgent",
     "scripts.runners.storm_runner", "run", True),
]


# Fixed services payload reused by every test. The wrappers don't actually
# touch the sandbox, so the URLs only need to be syntactically valid.
def _make_services() -> AgentServices:
    return AgentServices(
        search_url="http://localhost:8081",
        llm_url="http://localhost:8088/v1",
        llm_key="anything",
        sandbox_hosts={
            "shopping": "localhost:7770",
            "reddit": "localhost:9999",
            "wiki": "localhost:8090",
        },
        model="deepseek-v4-flash",
    )


# Realistic markdown report >= 1000 chars with sandbox citations so that the
# wrappers' length and prefix gates accept it as success.
_GOOD_REPORT = (
    "# Cross-Site Synthesis: Sony WH-1000XM5 vs Bose QC45\n\n"
    "## Executive summary\n\n"
    "Both flagship over-ear noise-cancelling headphones target the premium\n"
    "audiophile commuter market. Across our shopping, Reddit, and Wikipedia\n"
    "evidence we find Sony leads on adaptive ANC ([Sony product page]"
    "(http://localhost:7770/sony-wh1000xm5.html)) while Bose retains an\n"
    "edge on call quality per multiple [r/headphones threads]"
    "(http://localhost:9999/forums/headphones/t/123).\n\n"
    "## 1. Active noise cancellation\n\n"
    "Sony's eight-microphone array combined with the QN1 processor produces\n"
    "the deepest low-frequency attenuation we measured ([Sony spec sheet]"
    "(http://localhost:7770/sony-wh1000xm5-specs.html)).\n\n"
    "Bose's CustomTune algorithm calibrates ANC to ear shape on each fit\n"
    "([Bose support page](http://localhost:7770/bose-qc45.html)).\n\n"
    "## 2. Battery life\n\n"
    "Sony advertises 30 h ANC-on, Bose 24 h ANC-on. Wikipedia's overview\n"
    "of [active noise control](http://localhost:8090/wiki/Active_noise_control)\n"
    "explains the underlying tradeoff between processing power and runtime.\n\n"
    "## 3. Reddit sentiment\n\n"
    "Across 50 sampled r/headphones threads from the past 12 months, Sony\n"
    "is preferred for travel ([thread 451]"
    "(http://localhost:9999/forums/headphones/t/451)) while Bose is\n"
    "preferred for office calls ([thread 612]"
    "(http://localhost:9999/forums/headphones/t/612)).\n\n"
    "## 4. Conclusion\n\n"
    "If ANC depth and codec support are the buyer's priority, Sony wins.\n"
    "If lightweight comfort and call clarity matter more, Bose wins.\n"
)
assert len(_GOOD_REPORT) >= 1000, "fixture report must be >=1000 chars"


def _make_fake_success():
    async def _fake(*args, **kwargs):
        return _GOOD_REPORT
    return _fake


def _make_fake_placeholder():
    async def _fake(*args, **kwargs):
        return "(empty storm output)"
    return _fake


def _make_fake_raise():
    async def _fake(*args, **kwargs):
        raise RuntimeError("boom")
    return _fake


def _install_upstream(monkeypatch, upstream_module: str, upstream_attr: str,
                     fake_callable, needs_stub: bool) -> None:
    """Plant ``fake_callable`` so the wrapper's lazy import resolves to it.

    For modules that fail to import outside their own venv (e.g. storm pulls
    in :mod:`dspy`) we install a :class:`types.SimpleNamespace` directly into
    ``sys.modules``; the wrapper's ``from X import Y`` then sees the stub and
    never tries to execute the real module body.
    """
    if needs_stub:
        # Drop any half-loaded module first so we own the slot cleanly.
        monkeypatch.delitem(sys.modules, upstream_module, raising=False)
        stub = types.SimpleNamespace(**{upstream_attr: fake_callable})
        monkeypatch.setitem(sys.modules, upstream_module, stub)
    else:
        importlib.import_module(upstream_module)
        monkeypatch.setattr(f"{upstream_module}.{upstream_attr}",
                            fake_callable)


def _instantiate_agent(wrapper_module: str, wrapper_class: str):
    mod = importlib.import_module(wrapper_module)
    cls = getattr(mod, wrapper_class)
    return cls()


# ---------------------------------------------------------------------------
# Parametrised tests. ``ids`` produces clean labels like
# ``test_wrapper_success[storm]`` / ``test_wrapper_placeholder[camel-ai]`` etc.
# ---------------------------------------------------------------------------
_PARAMS = [
    pytest.param(*row, id=row[0]) for row in AGENT_TABLE
]


@pytest.mark.parametrize(
    "slug,wrapper_module,wrapper_class,upstream_module,upstream_attr,needs_stub",
    _PARAMS,
)
def test_wrapper_success(monkeypatch, slug, wrapper_module, wrapper_class,
                         upstream_module, upstream_attr, needs_stub):
    """Real-looking 1000-char report flows through unchanged."""
    _install_upstream(monkeypatch, upstream_module, upstream_attr,
                      _make_fake_success(), needs_stub)
    agent = _instantiate_agent(wrapper_module, wrapper_class)
    services = _make_services()

    result = asyncio.run(agent.run("test intent for " + slug, services))

    assert result.error is None, (
        f"{slug}: expected success but got error={result.error!r}"
    )
    assert result.markdown == _GOOD_REPORT, (
        f"{slug}: wrapper mutated the upstream markdown"
    )
    assert "Sony" in result.markdown
    assert result.elapsed_s >= 0.0


@pytest.mark.parametrize(
    "slug,wrapper_module,wrapper_class,upstream_module,upstream_attr,needs_stub",
    _PARAMS,
)
def test_wrapper_placeholder(monkeypatch, slug, wrapper_module, wrapper_class,
                             upstream_module, upstream_attr, needs_stub):
    """Runner placeholder sentinel is demoted to a typed error."""
    _install_upstream(monkeypatch, upstream_module, upstream_attr,
                      _make_fake_placeholder(), needs_stub)
    agent = _instantiate_agent(wrapper_module, wrapper_class)
    services = _make_services()

    result = asyncio.run(agent.run("test intent for " + slug, services))

    assert result.markdown == "", (
        f"{slug}: placeholder must produce empty markdown, "
        f"got {result.markdown!r}"
    )
    assert result.error is not None, (
        f"{slug}: placeholder must set an error string"
    )
    assert result.error.startswith("runner_placeholder:"), (
        f"{slug}: error prefix mismatch, got {result.error!r}"
    )


@pytest.mark.parametrize(
    "slug,wrapper_module,wrapper_class,upstream_module,upstream_attr,needs_stub",
    _PARAMS,
)
def test_wrapper_raises(monkeypatch, slug, wrapper_module, wrapper_class,
                        upstream_module, upstream_attr, needs_stub):
    """Underlying exception is caught and surfaced as ``error``."""
    _install_upstream(monkeypatch, upstream_module, upstream_attr,
                      _make_fake_raise(), needs_stub)
    agent = _instantiate_agent(wrapper_module, wrapper_class)
    services = _make_services()

    result = asyncio.run(agent.run("test intent for " + slug, services))

    assert result.markdown == "", (
        f"{slug}: failed run must produce empty markdown"
    )
    assert result.error is not None, (
        f"{slug}: failed run must set an error string"
    )
    assert result.error.startswith("RuntimeError:"), (
        f"{slug}: expected RuntimeError prefix, got {result.error!r}"
    )
    assert "boom" in result.error, (
        f"{slug}: original error message should be preserved, "
        f"got {result.error!r}"
    )
