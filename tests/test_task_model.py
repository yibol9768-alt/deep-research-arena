"""Regression tests for the v1 `Task` model in src.models.task.

These guard against the pydantic V2-deprecated, V3-removed spellings that
would crash importing src.models (and therefore the whole models package).
We promote PydanticDeprecatedSince20 to an error so that any reintroduced
deprecated construct (min_items/max_items, class-based Config, etc.) fails
the test at import time rather than silently shipping a future hard break.
"""

import importlib
import sys
import warnings
from pathlib import Path

import pytest
from pydantic import PydanticDeprecatedSince20, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_task_module_imports_without_pydantic_deprecations():
    """Importing the module must not trigger any pydantic V2 deprecation.

    A fresh import is forced so the module body re-executes under the strict
    warning filter, which is where deprecated Field/Config spellings would
    fire and (on a V3 upgrade) become a hard ImportError.
    """
    for name in list(sys.modules):
        if name == "src.models.task" or name.startswith("src.models.task."):
            del sys.modules[name]
    with warnings.catch_warnings():
        warnings.simplefilter("error", PydanticDeprecatedSince20)
        importlib.import_module("src.models.task")


def test_goals_length_constraints_enforced():
    from src.models.task import Goal, StructuredInstruction

    goal = Goal(id="goal_a1", description="d")

    # min_length=1: empty list rejected.
    with pytest.raises(ValidationError):
        StructuredInstruction(goals=[])

    # max_length=5: six goals rejected.
    with pytest.raises(ValidationError):
        StructuredInstruction(goals=[goal] * 6)

    # A valid count is accepted unchanged.
    instr = StructuredInstruction(goals=[goal, goal])
    assert len(instr.goals) == 2


def test_output_format_examples_min_length_enforced():
    from src.models.task import OutputFormatSpec

    with pytest.raises(ValidationError):
        OutputFormatSpec(type="object", properties={}, required=[], examples=[])

    spec = OutputFormatSpec(
        type="object", properties={}, required=[], examples=[{"k": "v"}]
    )
    assert len(spec.examples) == 1


def test_noise_profile_latency_exact_length_enforced():
    from src.models.task import NoiseProfile

    # Exactly two entries required (min_length=2, max_length=2).
    with pytest.raises(ValidationError):
        NoiseProfile(name="clean", network_latency_ms=[1], request_timeout_probability=0.0)
    with pytest.raises(ValidationError):
        NoiseProfile(
            name="clean", network_latency_ms=[1, 2, 3], request_timeout_probability=0.0
        )

    np = NoiseProfile(
        name="clean", network_latency_ms=[10, 50], request_timeout_probability=0.0
    )
    assert np.network_latency_ms == [10, 50]
