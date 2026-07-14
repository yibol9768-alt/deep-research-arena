"""Tests for src/eval/report_stubs.classify_report.

Guards the honest-lane-failure contract: every runner-failure placeholder from
the Qwen3-8B partial run is classified as a stub, a genuine markdown report is
"ok", and the two prefix regexes stay importable from their old home in
scripts/build_deep_leaderboard.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.report_stubs import (  # noqa: E402
    classify_report,
    is_stub,
    _RUNNER_FAILURE_PREFIX_RE,
    _RUNNER_EXCEPTION_PREFIX_RE,
)


# Exact stub strings taken verbatim from the 2026-07-06 Qwen3-8B partial run.
_STUB_TIMEOUT = [
    "(opencode timeout after 360s)",
    "(empty flowsearcher report)",
    "(qx-agents produced no report)",
]

_STUB_RUNNER_FAILURE = [
    "(opencode produced no report after 101s, exit=255)\n\n"
    "--- ssh stdout tail ---\n\n\n--- ssh stderr tail ---\n"
    "Connection to orkj647.iego.vip closed by remote host.\n\n\n"
    "--- agent stdout tail ---\n",
    "(claude-code produced no report after 11s, exit=255)\n\n"
    "--- ssh stdout tail ---\n\n\n--- ssh stderr tail ---\n"
    "Connection to orkj647.iego.vip closed by remote host.\n\n\n"
    "--- agent stdout tail ---\n",
    "(DeerFlow produced no report after 1256s, exit=1)",
    "(STORM produced no report after 600s, exit=137)",
]

_STUB_EXCEPTION = [
    "(qx-agents error: ValidationError: 2 validation errors for "
    "KnowledgeGapOutput\nresearch_complete\n  Field required "
    "[type=missing, input_value={'description': 'Output f...tput', "
    "'type': 'object'}, input_type=dict]\n    For further information "
    "visit https://errors.pydantic.dev/2.13/v/missing\noutstanding_gaps\n"
    "  Field required [type=missing, input_value={'description': "
    "'Output f...tput', 'type': 'object'}, input_type=dict]\n    For "
    "further information visit https://errors.pydantic.dev/2.13/v/missing)",
    "(claude-code error: CalledProcessError: Command '['scp', '-o', "
    "'ServerAliveInterval=30', '/tmp/cc_driver_54742c73a178.ps1', "
    "'my5090-win:C:/tools/cc_runner/driver_54742c73a178.ps1']' "
    "returned non-zero exit status 1.)",
    "(qx stderr: Traceback (most recent call last):\n  File \"run.py\", "
    "line 12, in <module>\n    main()\nRuntimeError: boom)",
]

_TOO_SHORT = [
    "\ufeffI'm sorry, but I don't understand what you're asking. "
    "Could you please clarify your question?",
    "\ufeffAPI Error: Unable to connect to API (ConnectionRefused)",
    "",
    "   \n  ",
]


# A genuine ~5KB markdown research report. Headings, prose, a citation link and
# a bulleted list: exactly the shape a real answer takes.
def _real_report() -> str:
    body = (
        "# Evaluating Headphone Purchases: A Buyer's Guide\n\n"
        "When selecting new headphones for a noisy office or a crowded "
        "commute, it helps to separate marketing language from the "
        "engineering that actually matters. This report analyses the key "
        "specifications and explains how to read them.\n\n"
        "## Active Noise Cancellation\n\n"
        "Active noise cancellation (ANC) uses feedforward and feedback "
        "microphones to generate an anti-noise signal. The depth of "
        "cancellation is frequency dependent and is strongest for low "
        "frequency, steady state noise such as engine hum. See the "
        "[measurement writeup](http://localhost:7770/catalog/product/view/id/42) "
        "for a representative curve.\n\n"
        "## Drivers and Frequency Response\n\n"
        "- Dynamic drivers dominate the consumer market and trade cost "
        "for a slightly less controlled treble.\n"
        "- Planar magnetic drivers offer lower distortion but demand more "
        "power and add weight.\n"
        "- A published frequency response chart is more informative than a "
        "single advertised range like 20 Hz to 20 kHz.\n\n"
        "## Codecs and Latency\n\n"
        "Bluetooth codec choice affects both fidelity and latency. AAC and "
        "SBC are universal; LDAC and aptX Adaptive raise the ceiling only "
        "when both endpoints support them.\n\n"
    )
    report = body * 5
    assert len(report) >= 5000
    return report


@pytest.mark.parametrize("text", _STUB_TIMEOUT)
def test_timeout_stubs(text):
    assert classify_report(text) == "stub_timeout"
    assert is_stub(text)


@pytest.mark.parametrize("text", _STUB_RUNNER_FAILURE)
def test_runner_failure_stubs(text):
    assert classify_report(text) == "stub_runner_failure"
    assert is_stub(text)


@pytest.mark.parametrize("text", _STUB_EXCEPTION)
def test_exception_stubs(text):
    assert classify_report(text) == "stub_exception"
    assert is_stub(text)


def test_native_odr_provider_error_is_not_a_report():
    text = (
        "Error generating final report: Error code: 400 - "
        "{'error': {'message': 'ds_proxy smoke budget exhausted: call limit reached'}}"
    )
    assert classify_report(text) == "stub_exception"


@pytest.mark.parametrize("text", _TOO_SHORT)
def test_too_short_stubs(text):
    assert classify_report(text) == "too_short"
    assert is_stub(text)


def test_none_is_too_short():
    assert classify_report(None) == "too_short"
    assert is_stub(None)


def test_every_fixture_stub_is_non_ok():
    for text in (_STUB_TIMEOUT + _STUB_RUNNER_FAILURE + _STUB_EXCEPTION
                 + _TOO_SHORT):
        assert classify_report(text) != "ok", repr(text[:60])


def test_real_report_is_ok():
    report = _real_report()
    assert classify_report(report) == "ok"
    assert not is_stub(report)


def test_short_but_structured_report_is_not_dropped():
    # Under the 100-char floor but carrying a markdown heading: conservative
    # rule keeps it "ok" rather than calling a terse real answer a stub.
    short_md = "# Answer\n\nUse the ANC model; see the chart."
    assert len(short_md) < 100
    assert classify_report(short_md) == "ok"


def test_report_mentioning_error_word_is_not_a_stub():
    # A real report that merely discusses an error must not trip the exception
    # or timeout prefixes: neither is a leading parenthesized runner marker.
    text = (
        "# Findings\n\nThe vendor page returned an error: the checkout API "
        "was unreachable during our test window, which we document below.\n"
    ) * 3
    assert classify_report(text) == "ok"


def test_prefix_regexes_reexported_from_leaderboard():
    # Backward-compatibility: existing imports of the two regexes from the
    # leaderboard module must keep resolving to the same objects.
    from scripts.build_deep_leaderboard import (
        _RUNNER_FAILURE_PREFIX_RE as lb_failure,
        _RUNNER_EXCEPTION_PREFIX_RE as lb_exception,
    )
    assert lb_failure is _RUNNER_FAILURE_PREFIX_RE
    assert lb_exception is _RUNNER_EXCEPTION_PREFIX_RE
