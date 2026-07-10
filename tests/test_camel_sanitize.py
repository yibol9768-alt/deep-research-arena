"""Regression: the camel-ai report sanitizer strips only BALANCED framework XML
marker pairs. An UNCLOSED ``<think>`` / ``<tool_call>`` / ``<tool_response>``
opener must be left in place, NOT deleted-to-EOF.

The old ``_sanitize_camel_report`` ran, after the balanced-pair passes, a
``<think\\b[^>]*>.*`` DOTALL strip for each dangling opener. A single reasoning
tag left open mid-report therefore erased the entire report body below it,
turning a real, scored camel report into a truncated stub -- a harness-inflicted
zero, not camel's own weakness.

Every fixture spans the three corpus sources (shopping ``:7770`` / wiki
``:8090`` / forum ``:9999``) so a per-source asymmetry cannot hide (HANDOFF
trap 1). Deterministic: no network, no clock, no randomness.
"""

from scripts.run_deep_task import _sanitize_camel_report

PROD = "http://localhost:7770/sony-wh1000xm5.html"
WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth"
FORUM = "http://localhost:9999/f/headphones/27823"


def test_balanced_think_block_is_stripped():
    text = f"Intro. <think>private reasoning</think> Body cites {PROD}."
    out = _sanitize_camel_report(text)
    assert "private reasoning" not in out and "<think>" not in out
    assert PROD in out and out.startswith("Intro.")


def test_unclosed_think_preserves_the_whole_body_across_sources():
    """A single unclosed ``<think>`` in the MIDDLE. The old ``.*``-to-EOF strip
    deleted everything after it; the fix keeps the body and all three citations."""
    text = (
        "# Report\n\nSummary of findings.\n\n"
        "<think>I should compare the products but never close this tag\n\n"
        f"The {PROD} beats alternatives; the {WIKI} explains the codec and "
        f"the {FORUM} owners agree it is the best pick."
    )
    out = _sanitize_camel_report(text)
    for url in (PROD, WIKI, FORUM):
        assert url in out, f"{url} was deleted by the unclosed-tag strip"
    assert "owners agree it is the best pick" in out


def test_unclosed_tool_call_and_response_also_preserve_the_body():
    for opener in ("<tool_call>", "<tool_response>"):
        text = f"Analysis of the market. {opener} dangling scaffold\n\nConclusion cites {FORUM}."
        out = _sanitize_camel_report(text)
        assert FORUM in out and "Conclusion cites" in out


def test_balanced_pairs_stripped_but_later_body_survives():
    text = (
        f"<think>reasoning</think>\n\nThe {PROD} is discussed; "
        f"<tool_call>{{...}}</tool_call>\n\nand {WIKI} confirms it."
    )
    out = _sanitize_camel_report(text)
    assert "reasoning" not in out
    assert PROD in out and WIKI in out and "confirms it" in out
