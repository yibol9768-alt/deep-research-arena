"""G0: no lane carries a hidden comparative wall clock (SPEC_ISSUES §2, WF).

The protocol (config/lane_protocol.yaml `budget`) declares `wall_clock_s: null`:
no comparative outer wall clock; the shared no-progress watchdog owns
termination and a kill is `stalled` (infra, rerunnable), never a framework
failure. Four runner modules nonetheless hardcoded their own hard wall
(tongyi-dr / deepagents / ldr at 1800s, local-deep-researcher at 1200s), and
run_deep_task's MANUAL dispatch wrappers pass no timeout_s, so those module
defaults governed formal runs: on a slow backbone the subprocess was killed and
the lane scored as having delivered nothing -- an UNDECLARED protocol difference
(gate G0) and a false accusation (the wall punished the backbone's token rate,
not the framework).

Red-on-old proof: before the fix each module's DEFAULT_TIMEOUT_S was the
integer literal (1800/1200), so every assertion against
_budget.native_timeout_default() (None under the protocol default) fails on the
old code.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runners import _budget  # noqa: E402

# The four offenders named by the audit (SPEC_ISSUES §2 first entry). Other
# lanes either resolve through run_deep_task's _wrap_runner (which passes
# timeout_s explicitly) or their inline _native_timeout_s(...) call.
OFFENDER_MODULES = [
    "scripts.runners.tongyi_runner",
    "scripts.runners.deepagents_runner",
    "scripts.runners.ldr_runner",
    "scripts.runners.local_deep_researcher_runner",
]


def _import(name):
    __import__(name)
    return sys.modules[name]


def test_protocol_declares_no_comparative_wall_clock():
    """The declaration this file enforces: wall_clock_s is null."""
    doc = yaml.safe_load((ROOT / "config" / "lane_protocol.yaml").read_text())
    assert doc["budget"]["wall_clock_s"] is None


@pytest.mark.parametrize("modname", OFFENDER_MODULES)
def test_runner_default_wall_clock_is_the_shared_uniform_default(modname):
    """DEFAULT_TIMEOUT_S must be the uniform _budget default, not a lane literal.

    Equality with native_timeout_default() (not a bare `is None`) keeps the test
    meaningful even when an operator exports DRA_WALL_CLOCK_S globally: the
    invariant is UNIFORMITY with the shared policy, and the policy itself is
    pinned to null by test_protocol_declares_no_comparative_wall_clock.
    """
    mod = _import(modname)
    assert mod.DEFAULT_TIMEOUT_S == _budget.native_timeout_default(), (
        f"{modname}.DEFAULT_TIMEOUT_S={mod.DEFAULT_TIMEOUT_S!r} is a hidden "
        "per-lane wall clock; the protocol declares wall_clock_s: null")


@pytest.mark.parametrize("modname", OFFENDER_MODULES)
def test_run_signature_default_is_no_wall_clock(modname):
    """run_deep_task's manual wrappers omit timeout_s, so the run() signature
    default IS the formal-run behaviour. It must be the shared default."""
    mod = _import(modname)
    default = inspect.signature(mod.run).parameters["timeout_s"].default
    assert default == _budget.native_timeout_default(), (
        f"{modname}.run(timeout_s=...) defaults to {default!r}; formal runs "
        "dispatch without timeout_s, so this default is an undeclared hard wall")


@pytest.mark.parametrize("modname", OFFENDER_MODULES)
def test_no_hardcoded_wall_clock_when_env_unset(modname):
    """Under the shipped protocol (wall_clock_s: null) and a clean environment,
    the resolved default is None: subprocess.run receives timeout=None and only
    the watchdog can terminate the lane."""
    if os.environ.get("DRA_WALL_CLOCK_S"):
        pytest.skip("operator set a global wall clock; uniformity tests cover this")
    mod = _import(modname)
    assert mod.DEFAULT_TIMEOUT_S is None
