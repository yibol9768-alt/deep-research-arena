"""Regression tests for the tongyi-dr adapter driver.

The reimplemented ReAct loop retries every LLM call. When the retries are
exhausted the old ``call_llm`` RETURNED the sentinel string
``"Error: LLM call failed after retries."``. That string was appended to the
message history as an assistant turn and fed back into the loop, and (being the
last assistant content) could surface in the scored report. A transport outage
was thereby scored as camel-... no -- as tongyi's own low-quality output.

``call_llm`` now RAISES on exhaustion, so the driver crashes with no report
sentinel and the outer runner records a tongyi-dr infra failure, the same
failure semantics as every other lane. These tests pin that behaviour by
extracting the generated ``call_llm`` and driving it with a client that always
fails.

Deterministic: no network, no real sleeping (``time`` is stubbed).
"""

from __future__ import annotations

import ast

import pytest

from scripts.runners import tongyi_runner as tr


def _driver_source() -> str:
    return tr._build_driver_script(
        intent="compare noise-cancelling headphones",
        shim_url="http://localhost:8081",
        proxy_url="http://localhost:8100/v1",
        model="deepseek-v4-flash",
    )


def test_driver_is_valid_python():
    ast.parse(_driver_source())


def test_driver_never_returns_the_error_sentinel():
    """The failure path must not hand the loop a fake model turn."""
    src = _driver_source()
    assert "Error: LLM call failed after retries." not in src


def _extract_call_llm(src: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "call_llm":
            seg = ast.get_source_segment(src, node)
            assert seg is not None
            return seg
    raise AssertionError("call_llm not found in generated driver")


class _AlwaysFailClient:
    class chat:  # noqa: N801 - mirrors the openai client shape
        class completions:  # noqa: N801
            @staticmethod
            def create(**_kw):
                raise RuntimeError("upstream 503")


class _NoSleep:
    @staticmethod
    def sleep(_s):
        return None


class _Rand:
    @staticmethod
    def uniform(_a, _b):
        return 0.0


def test_call_llm_raises_when_retries_exhausted():
    """Exhausted retries must RAISE (infra failure), never return a string that
    could enter the scored report."""
    src = _extract_call_llm(_driver_source())
    ns: dict = {
        "_client": _AlwaysFailClient(),
        "MODEL": "deepseek-v4-flash",
        "time": _NoSleep(),
        "random": _Rand(),
        "print": lambda *a, **k: None,
    }
    exec(src, ns)  # noqa: S102 - executing our own generated code under test
    call_llm = ns["call_llm"]
    with pytest.raises(RuntimeError):
        call_llm([{"role": "user", "content": "hi"}], max_retries=2)
