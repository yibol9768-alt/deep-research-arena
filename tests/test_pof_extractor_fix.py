"""Regression tests for the proof-of-fetch extractor fix (E-3 §6 / E1a).

Locks the P0 behaviour: PoF must share ``citation_format.extract_citations``
with reachability (so numbered / bare / footnote citations are no longer
invisible), aggregate PAGE-LEVEL any-occurrence, anchor evidence at the in-text
marker (not the bibliography line), and keep the verbatim judge's fabrication
resistance intact.

No sandbox / big-cache dependency: a tiny synthetic status-200 page cache is
built inline, so these replay byte-for-byte.
"""

from __future__ import annotations

from src.eval import decidable_scorer as ds
from src.eval.decidable_scorer import score_proof_of_fetch, _cited_urls


# A distinctive verbatim page. The quoted run below appears here word for word.
_PAGE_A = (
    "The Superlux HD681 sounded really shrill and plasticky after only three "
    "months of daily use, and the pads started rubbing against my skin. "
    "Community members still recommend it as a budget option despite the "
    "harsh treble and the thin, uncomfortable headband."
)
_PAGE_B = (
    "The AKG K371 was praised for its balanced sound quality during a short "
    "demo at the local shop, with a warm low end and a natural midrange that "
    "reviewers found pleasant for long listening sessions."
)
URL_A = "http://localhost:9999/f/headphones/100"
URL_B = "http://localhost:9999/f/headphones/200"


def _cache() -> dict:
    return {
        URL_A: {"status": 200, "text": _PAGE_A},
        URL_B: {"status": 200, "text": _PAGE_B},
    }


def _stats(cache):
    return ds.build_page_stats(cache)


# ---------------------------------------------------------------------------
# 1. numbered-citation report earns PoF (the headline LDR/STORM bug)
# ---------------------------------------------------------------------------

def test_numbered_citation_report_gets_pof():
    cache = _cache()
    md = (
        "The user found the Superlux HD681 sounded really shrill and plasticky "
        "after only three months of daily use [1]. On the other hand the AKG "
        "K371 was praised for its balanced sound quality during a short demo "
        "at the local shop [2].\n\n"
        "### Sources\n"
        "[1] r/headphones: Superlux review\n"
        "   URL: " + URL_A + "\n"
        "[2] r/headphones: AKG demo notes\n"
        "   URL: " + URL_B + "\n"
    )
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 2, det
    assert det["passed"] == 2, det
    assert score == 1.0


def test_two_line_sources_table_resolves_urls():
    # the LDR '[N] title' then 'URL: ...' two-line block must map [N] -> url.
    cache = _cache()
    md = (
        "Superlux HD681 sounded really shrill and plasticky after only three "
        "months [1].\n\n### Sources\n[1] r/headphones: review\n   URL: "
        + URL_A + "\n"
    )
    assert URL_A in set(_cited_urls(md))
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["passed"] == 1 and det["checked"] == 1


# ---------------------------------------------------------------------------
# 2. bare URL is picked up (counts toward reach via the shared extractor)
# ---------------------------------------------------------------------------

def test_bare_url_is_extracted_for_reach():
    md = ("The pads started rubbing against my skin, the reviewer noted.\n"
          "Source page: " + URL_A + "\n")
    assert URL_A in set(_cited_urls(md))


def test_bare_inline_url_earns_pof():
    cache = _cache()
    md = ("The AKG K371 was praised for its balanced sound quality during a "
          "short demo at the local shop " + URL_B + "\n")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 1 and det["passed"] == 1


# ---------------------------------------------------------------------------
# 3. fabricated / cross-page citations still score 0 (FPR guard)
# ---------------------------------------------------------------------------

def test_fabricated_quote_scores_zero():
    cache = _cache()
    md = ("The driver array sustains 4821 kHz across 92 hours of continuous "
          "operation, per the teardown [1].\n\n### Sources\n"
          "[1] spec sheet\n   URL: " + URL_A + "\n")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 1
    assert det["passed"] == 0
    assert score == 0.0


def test_cross_page_attribution_scores_zero():
    # verbatim text from page A, but cited to page B -> not proof of reading B.
    cache = _cache()
    md = ("Superlux HD681 sounded really shrill and plasticky after only three "
          "months of daily use [1].\n\n### Sources\n[1] wrong page\n   URL: "
          + URL_B + "\n")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["passed"] == 0


# ---------------------------------------------------------------------------
# 4. bibliography-only citation (no in-text anchor) is checked-and-failed
# ---------------------------------------------------------------------------

def test_reference_only_url_is_checked_and_failed():
    # A numbered '[1]' reference line IS an anchor (its preceding prose is the
    # body claim), so a bibliography whose body says nothing about the page
    # still fails on evidence, not by vanishing from the denominator.
    cache = _cache()
    md = ("Headphones are a mature product category and many people enjoy "
          "music on the go.\n\n### Sources\n[1] r/headphones\n   URL: "
          + URL_A + "\n")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 1
    assert det["passed"] == 0
    assert score == 0.0


def test_source_only_url_has_no_inline_anchor():
    # URL appears ONLY behind a bare 'URL:' bibliography line with NO numbered
    # marker anywhere -> pure reference form, not an evidence anchor: checked
    # (cited, page has text) but failed with reason no_inline_anchor.
    cache = _cache()
    md = ("Headphones are a mature product category and many people enjoy "
          "music on the go.\n\nSources:\nURL: " + URL_A + "\n")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 1
    assert det["passed"] == 0
    assert any(p.get("reason") == "no_inline_anchor" for p in det["per"])


# ---------------------------------------------------------------------------
# 5. page-level any-occurrence: a repeated marker is not diluted to 0
# ---------------------------------------------------------------------------

def test_page_level_any_occurrence_not_diluted():
    cache = _cache()
    # [1] appears three times: once hugging the verbatim quote, twice in bare
    # enumerations with no supporting prose. Page-level any-occurrence must
    # still pass the page (the old per-marker mean would drag it toward 0).
    md = (
        "Recommended shortlist below (see [1], [1], [1]).\n\n"
        "The Superlux HD681 sounded really shrill and plasticky after only "
        "three months of daily use [1].\n\n"
        "### Sources\n[1] r/headphones\n   URL: " + URL_A + "\n"
    )
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["checked"] == 1
    assert det["passed"] == 1
    assert score == 1.0


# ---------------------------------------------------------------------------
# 6. markdown parity: the incumbent single-markdown path is unchanged
# ---------------------------------------------------------------------------

def test_markdown_citation_still_scores():
    cache = _cache()
    md = ('The page notes the pads started rubbing against my skin and the '
          'harsh treble ([source](' + URL_A + ")).")
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["passed"] == 1 and det["checked"] == 1


def test_slug_padding_alone_does_not_pass():
    # pasting the URL slug tokens as prose next to the link is not proof.
    cache = {URL_A: {"status": 200, "text": _PAGE_A}}
    md = "f headphones 100 localhost ([source](" + URL_A + "))."
    score, det = score_proof_of_fetch(md, cache, page_stats=_stats(cache))
    assert det["passed"] == 0
