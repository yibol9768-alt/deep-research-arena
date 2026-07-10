"""Regression tests for the balanced-bracket / stray-bracket citation fix in
``src/verifiers/citation_format.py``.

Two defects are pinned here, each of which silently zeroed a lane's citations:

1. **Nested brackets in the link label.** A product name such as
   ``TAPTES ... Charger [2020 Version] ...`` copied faithfully into a markdown
   label was invisible to the old ``MD_LINK_RE = \\[[^\\]]*\\]\\(...\\)``: the
   label class stopped at the first ``]``, so the whole citation vanished and
   the completeness nugget was scored uncovered. 35 such nuggets across 23 tasks.

2. **A stray, unmatched ``[``.** The first ``iter_markdown_links`` scanner (the
   fix that introduced nested-bracket support) ``return``-ed the instant it hit
   a ``[`` with no balanced closing ``]`` -- dropping EVERY later markdown link
   in the report. A single ``[4/5`` or ``[TODO`` in the prose therefore erased a
   lane's downstream citations. The old ``MD_LINK_RE.finditer`` never had this
   failure mode.

Every fixture spans the three corpus sources (shopping ``:7770`` / wiki
``:8090`` / forum ``:9999``) so a per-source parsing asymmetry cannot hide here
(HANDOFF trap 1). Deterministic: no network, no clock, no randomness.

If either fix is reverted these tests go red.
"""

import re

import pytest

from src.verifiers.citation_format import (
    MD_LINK_RE,
    extract_citations,
    iter_markdown_links,
)

PROD = "http://localhost:7770/taptes-tesla-model-3-wireless-charger-2020-version.html"
WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Wireless_charging"
FORUM = "http://localhost:9999/f/technology/27823"

# The label the old regex could not parse: a balanced ``[2020 Version]`` inside
# it AND a ``(...)`` group, both drawn from a real catalog product name.
BRACKET_LABEL = "TAPTES Tesla Model 3 Wireless Charger [2020 Version] (Before Jun 2020)"

# The exact regex that shipped before the fix, kept here ONLY to document that
# these inputs were genuinely unparseable then. Nothing in production uses it.
_OLD_MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)")


def _urls(text):
    return [link.url for link in iter_markdown_links(text)]


def test_nested_bracket_label_is_parsed_across_sources():
    """A markdown label containing a balanced ``[...]`` is a link on all three
    sources; the old label class matched none of them."""
    for url in (PROD, WIKI, FORUM):
        text = f"See [{BRACKET_LABEL}]({url}) for details."
        assert _urls(text) == [url]
        # The label is preserved whole, brackets and all.
        (link,) = list(iter_markdown_links(text))
        assert link.label == BRACKET_LABEL
        # Pin the regression: the pre-fix regex found nothing here.
        assert _OLD_MD_LINK_RE.search(text) is None


def test_paren_in_url_not_truncated():
    """A destination whose path carries balanced ``(...)`` (Kiwix disambiguation
    slugs) survives intact; the old ``[^)\\s]+`` class chopped it at the first
    ``)``."""
    wiki_paren = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Qi_(standard)"
    text = f"The [Qi standard]({wiki_paren}) governs this."
    assert _urls(text) == [wiki_paren]
    old = _OLD_MD_LINK_RE.search(text)
    assert old is not None and old.group("url") != wiki_paren  # truncated then


def test_adjacent_links_do_not_swallow_each_other():
    """Two back-to-back links (product then forum) both parse, in order."""
    text = f"[pad]({PROD})[thread]({FORUM})"
    assert _urls(text) == [PROD, FORUM]


def test_stray_bracket_does_not_drop_downstream_links():
    """An unmatched ``[`` earlier in the prose must not erase later citations.

    This is the failure mode the first scanner had: it returned on the stray
    ``[`` and yielded nothing. The three real source citations that follow must
    all survive."""
    text = (
        "Buyers rate it [4/5 overall and the pad "
        f"[wireless pad]({PROD}) pairs with the "
        f"[charging article]({WIKI}) and the "
        f"[owner thread]({FORUM}) confirms it."
    )
    assert _urls(text) == [PROD, WIKI, FORUM]


def test_extract_citations_sees_all_sources_with_stray_bracket_and_nested_label():
    """End-to-end through the extractor the scorer actually calls: a report with
    a stray bracket AND a nested-bracket product label still yields one markdown
    citation per source."""
    report = (
        "# Report\n\n"
        "Summary [draft — todo: expand] of findings.\n\n"
        f"The [{BRACKET_LABEL}]({PROD}) is discussed in "
        f"[wireless charging]({WIKI}); owners agree in the "
        f"[community thread]({FORUM})."
    )
    cites = [c for c in extract_citations(report, sandbox_only=False)
             if c.style == "markdown"]
    got = sorted(c.raw_url for c in cites)
    assert got == sorted([PROD, WIKI, FORUM])


def test_scoring_credits_a_bracketed_product_name_nugget():
    """The real payoff: a completeness nugget whose product name carries
    ``[2020 Version]`` is covered when the report cites it under its true name.

    Uses answer key 0019 (a real bracketed buyer_sentiment nugget). Registry is
    loaded read-only; skip cleanly if the frozen corpus is unavailable so the
    test never fails for an infra reason."""
    from src.eval import decidable_scorer as ds
    from src.eval.answer_key import AnswerKey
    from src.eval.closed_world_eval import load_registry

    key_path = "data/golden/answer_keys/dr_cross_deep_0019.json"
    ak = AnswerKey.load(key_path)
    nug = next((n for n in ak.vital_nuggets
                if n.predicate == "buyer_sentiment" and "[" in n.subject
                and "TAPTES" in n.subject), None)
    if nug is None:
        pytest.skip("answer key 0019 no longer carries the bracketed TAPTES nugget")
    try:
        registry = load_registry()
    except Exception as exc:  # pragma: no cover - infra guard
        pytest.skip(f"registry unavailable: {exc}")

    pct = nug.object.split("%")[0]
    report = (
        "# Report\n\n"
        f"[{nug.subject}]({nug.source_url}) is rated {pct}% positive "
        "across 12 reviews on the store page."
    )
    _comp, detail = ds.score_completeness(report, ak, cache={}, registry=registry)
    assert detail["covered_by_predicate"].get("buyer_sentiment", 0) >= 1
