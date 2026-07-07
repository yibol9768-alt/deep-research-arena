"""Regression tests for the --strict-sandbox forwarding contract.

Bug fixed here: the manual in-process wrappers ``_run_storm`` and
``_run_deerflow`` in :mod:`scripts.run_deep_task` did NOT accept or forward a
``strict_sandbox`` kwarg, even though their underlying runner modules declare
``STRICT_SANDBOX_ELIGIBLE = True`` and expose a ``strict_sandbox`` parameter on
``run()``. Because ``_MANUAL_RUNNERS`` wins over the registry, the kwarg was
silently dropped: ``main()`` would forward nothing, the strict HTTP gate was
never installed, yet the .meta.json still recorded ``strict_sandbox: true``.

These tests pin three properties:

1. ``_run_storm`` / ``_run_deerflow`` expose ``strict_sandbox`` so
   ``_runner_supports_strict`` returns True for them.
2. The wrappers actually forward the flag's value to the underlying
   ``run()`` (storm_runner.run / deerflow_runner.run).
3. ``main()`` never records ``strict_sandbox: true`` for a run whose runner
   cannot accept the kwarg: if an eligible runner does not expose it, the run
   is refused (fail loud) rather than silently recorded as enforced.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
import types
from pathlib import Path

import pytest

# Make the repo root importable regardless of pytest invocation cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_deep_task as rdt  # noqa: E402


# ---------------------------------------------------------------------------
# Property 1: the manual wrappers expose strict_sandbox.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("wrapper_name", ["_run_storm", "_run_deerflow"])
def test_manual_wrapper_exposes_strict_sandbox(wrapper_name):
    wrapper = getattr(rdt, wrapper_name)
    params = inspect.signature(wrapper).parameters
    assert "strict_sandbox" in params, (
        f"{wrapper_name} must accept a strict_sandbox kwarg so the strict "
        "HTTP gate is installed"
    )
    # And the dispatch helper main() relies on must agree.
    assert rdt._runner_supports_strict(wrapper) is True, (
        f"_runner_supports_strict must report {wrapper_name} as strict-capable"
    )


# ---------------------------------------------------------------------------
# Property 2: the wrappers forward the flag to the underlying run().
# We stub the runner module in sys.modules so the lazy `from ... import run`
# inside the wrapper resolves to our recorder. storm_runner pulls in dspy and
# deerflow_runner pulls in framework deps at import time, so stubbing is the
# only venv-free way to exercise these.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "wrapper_name,module_name",
    [
        ("_run_storm", "scripts.runners.storm_runner"),
        ("_run_deerflow", "scripts.runners.deerflow_runner"),
    ],
)
@pytest.mark.parametrize("strict_value", [True, False])
def test_wrapper_forwards_strict_sandbox(monkeypatch, wrapper_name,
                                         module_name, strict_value):
    captured: dict = {}

    # The fake report must clear is_weak_report (>=3000 chars, >=3 sandbox
    # URLs): since the evidence-fallback gate landed, _run_deerflow answers a
    # weak native report with an honest per-lane error stub in benchmark mode,
    # and this test pins pass-through of a GOOD report plus kwarg forwarding.
    fake_report = (
        "# fake report\n\n"
        "Evidence: [p1](http://localhost:7770/p1.html), "
        "[t2](http://localhost:9999/t2.html), "
        "[w3](http://localhost:8090/w3.html).\n\n"
        + ("body paragraph with enough length to clear the weak-report floor. " * 60)
    )

    async def _recording_run(**kwargs):
        captured.update(kwargs)
        return fake_report

    monkeypatch.delitem(sys.modules, module_name, raising=False)
    stub = types.SimpleNamespace(run=_recording_run)
    monkeypatch.setitem(sys.modules, module_name, stub)

    wrapper = getattr(rdt, wrapper_name)
    out = asyncio.run(wrapper("intent", "deepseek-v4", strict_sandbox=strict_value))

    assert out == fake_report
    assert captured.get("strict_sandbox") == strict_value, (
        f"{wrapper_name} dropped strict_sandbox={strict_value}; "
        f"underlying run() saw {captured.get('strict_sandbox')!r}"
    )
    # The wrapper must also forward the core identifiers unchanged.
    assert captured.get("intent") == "intent"
    assert captured.get("model") == "deepseek-v4"


def test_wrapper_defaults_strict_sandbox_false(monkeypatch):
    """Omitting the kwarg keeps the closed-book gate OFF (no silent enable)."""
    captured: dict = {}

    async def _recording_run(**kwargs):
        captured.update(kwargs)
        return "# fake report\n\nbody"

    monkeypatch.delitem(sys.modules, "scripts.runners.storm_runner",
                        raising=False)
    monkeypatch.setitem(sys.modules, "scripts.runners.storm_runner",
                        types.SimpleNamespace(run=_recording_run))

    asyncio.run(rdt._run_storm("intent", "deepseek-v4"))
    assert captured.get("strict_sandbox") is False


# ---------------------------------------------------------------------------
# Property 3: main() never records strict_sandbox=true for an unenforced run.
# A runner that is eligible (or eligibility-unknown) but whose callable cannot
# accept the kwarg must cause main() to refuse the run, not silently record it.
# We assert this on the dispatch invariant directly without spinning up the
# full main() (which sets up shims/backbones).
# ---------------------------------------------------------------------------
def test_eligible_runner_must_support_kwarg():
    """Every strict-eligible manual runner must actually accept the kwarg.

    This is the invariant main() now enforces (refuse rather than record a
    false strict_sandbox=true). storm and deerflow are eligible, so they must
    pass _runner_supports_strict.
    """
    for name in ("storm", "deerflow"):
        eligible = rdt._runner_module_strict_eligible(name)
        # eligible may be True (module flag) or None (registry unavailable in
        # this venv); in neither case may the run be silently recorded.
        runner = rdt.RUNNERS[name]
        assert eligible is not False
        assert rdt._runner_supports_strict(runner) is True, (
            f"{name} is eligible but its runner cannot accept strict_sandbox; "
            "main() would either drop the flag silently or refuse the run"
        )


def test_main_refuses_eligible_runner_without_kwarg(monkeypatch, tmp_path):
    """If an eligible runner cannot accept strict_sandbox, main() refuses.

    Simulates the precise bug condition: eligibility says go, but the runner
    callable lacks the kwarg. main() must NOT write strict_sandbox=true for an
    unenforced run; it must set an error and refuse.
    """
    import json

    async def _no_kwarg_runner(intent, model):  # NB: no strict_sandbox param
        return "# report\n\nbody"

    # Force a runner that is eligible but cannot honour the kwarg.
    monkeypatch.setitem(rdt.RUNNERS, "_test_eligible_no_kwarg", _no_kwarg_runner)
    monkeypatch.setattr(
        rdt, "_runner_module_strict_eligible",
        lambda name: True if name == "_test_eligible_no_kwarg" else None,
    )
    # Neutralise environment setup and IO side effects.
    monkeypatch.setattr(rdt, "_setup_ds_backbone", lambda *a, **k: None)
    monkeypatch.setattr(rdt, "_setup_sandbox_shim", lambda *a, **k: None)
    monkeypatch.setattr(rdt, "_load_task", lambda task: {"intent": "x"})
    monkeypatch.setattr(rdt, "_resolve_intent", lambda cfg: "x")
    monkeypatch.setattr(rdt, "OUT_DIR", tmp_path)

    argv = [
        "run_deep_task.py",
        "--agent", "_test_eligible_no_kwarg",
        "--task", "dummy",
        "--strict-sandbox",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    rc = asyncio.run(rdt.main())

    meta_files = list(tmp_path.glob("*.meta.json"))
    assert meta_files, "main() should have written a meta.json"
    meta = json.loads(meta_files[0].read_text())
    assert meta["error"], "an unenforceable strict run must carry an error"
    assert "strict" in meta["error"].lower()
    assert rc == 1
