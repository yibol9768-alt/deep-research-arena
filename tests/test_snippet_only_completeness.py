"""Ruling #1 (docs/SPEC_DECISIONS.md, SPEC_ISSUES section 1 first entry):
completeness's fetch requirement is EXEMPTED for a lane that declares
``fetch_mode: none`` (storm / langchain-odr / co-storm read no pages by
architecture). Such a lane obtains facts from search snippets; its pof is
already 0-honest and grounding is metered by pof/reach, so charging completeness
a fetch it cannot make would rank "has a page-read tool", not the answer.

The scenario below is the SAME impeccable, three-source report scored against a
HEALTHY, observable transport log whose ``fetched_ok`` is empty (a snippet-only
lane searches but never fetches). On a page-reading lane that transport is
usable and the empty ``fetched_ok`` is an EARNED miss -- the strict control
``test_usable_transport_still_requires_the_fetch_not_weakened`` in
test_gate_withhold.py pins exactly that. Here the lane is declared
``fetch_mode:none``, so the requirement drops and coverage falls back to the
cache-quote criterion, exactly as the L3 off-shim/damaged fallback does.

Red on the pre-ruling scorer: it keyed the concept/forum fetch requirement on
transport usability alone, so a snippet-only lane's impeccable, quoted, in-cache
concept and forum slots scored 0 while its pof was (honestly) 0. Fixture spans
all three sources (shopping 7770 / wiki 8090 / forum 9999).
"""

from __future__ import annotations

from src.eval import decidable_scorer as ds
from src.eval.fetch_log import RunEvidence, canonical
from src.eval.url_registry import UrlRegistry

from tests.test_gate_withhold import (
    CACHE_FULL,
    FORUM,
    PRODUCT,
    REPORT,
    WIKI,
    three_source_key,
)

REG = UrlRegistry.load()


def _searched_only_evidence() -> RunEvidence:
    """Healthy, observable log: the lane searched (so transport IS usable) but
    fetched no pages -- the snippet-only shape. On a page-reading lane this
    empty ``fetched_ok`` is an earned miss; a fetch_mode:none lane is exempt."""
    ev = RunEvidence(available=True, fetch_observable=True)
    ev.searched = {canonical(PRODUCT), canonical(WIKI), canonical(FORUM)}
    # no ev.fetched entries: fetched_ok is empty
    return ev


def test_page_reading_lane_still_requires_the_fetch_control():
    """Control: with no fetch_mode declaration (a page-reading lane) the healthy
    empty fetched_ok is an earned miss -- concept and forum score 0."""
    ev = _searched_only_evidence()
    score, det = ds.score_completeness(
        REPORT, three_source_key(), k_star=3, cache=CACHE_FULL, registry=REG,
        evidence=ev)
    assert det["concept_transport_required"] is True
    assert det["fetch_mode_none_exempt"] is False
    assert det["covered_by_predicate"].get("concept_coverage", 0) == 0
    assert det["forum_covered"] is False
    assert det["covered"] == 1  # only the product price nugget
    assert score < 1.0


def test_fetch_mode_none_lane_is_exempt_and_falls_back_to_cache_quote():
    """Ruling #1: the SAME report on a declared fetch_mode:none lane earns the
    concept and forum slots via the cache-quote fallback. Red on old code."""
    ev = _searched_only_evidence()
    score, det = ds.score_completeness(
        REPORT, three_source_key(), k_star=3, cache=CACHE_FULL, registry=REG,
        evidence=ev, lane_fetch_mode="none")
    assert det["concept_transport_required"] is False
    assert det["fetch_mode_none_exempt"] is True
    assert det["covered_by_predicate"]["concept_coverage"] == 1
    assert det["forum_covered"] is True
    assert det["covered"] == 3  # product + concept + forum
    assert score == 1.0


def test_exemption_reaches_score_report_via_lane_fetch_mode():
    """score_report threads lane_fetch_mode to completeness; the board reads the
    lane's declared fetch_mode from lane_protocol.yaml and passes it here."""
    ev = _searched_only_evidence()
    out = ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                          evidence=ev, k_star=3, lane_fetch_mode="none")
    cd = out.detail["completeness"]
    assert cd["fetch_mode_none_exempt"] is True
    assert cd["covered"] == 3
    assert out.completeness == 1.0


def test_only_the_string_none_is_exempt_not_none_default():
    """A lane that did not declare fetch_mode (default None) is NOT exempt: the
    exemption keys strictly on the string 'none', never on a missing value."""
    assert ds._fetch_mode_none("none") is True
    assert ds._fetch_mode_none(None) is False
    assert ds._fetch_mode_none("direct_requests") is False
    assert ds._fetch_mode_none("shim_extract") is False
