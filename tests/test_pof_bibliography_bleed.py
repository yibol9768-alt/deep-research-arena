"""D4 / audit-F1 regression: reference-list ("[N] <title>" / "[^id]: <url>")
entry heads must NOT serve as proof-of-fetch evidence anchors.

The bug: NUMBERED_INLINE_RE matches the ``[N]`` head of every bibliography
entry, and ``_pof_occurrence_ok`` takes the 400 chars BEFORE that head as the
evidence context. In a reference list those 400 chars are the PREVIOUS entry's
title / result-snippet, so entry N's verbatim page text "bleeds" onto the page
that entry N+1 points at -- a cross-entry false positive (12/12 numbered reports
triggered it, 35.6% of numbered occurrences, audit F1).

Fix: a marker inside a reference region (heading-delimited section, a run of
numbered/footnote reference-definition lines, or a single such line) counts for
the PoF denominator (the page is CITED) but never as an evidence anchor.
"""

from src.eval import decidable_scorer as ds


PAGE_X = "http://localhost:9999/f/headphones/1001"
PAGE_Y = "http://localhost:9999/f/headphones/1002"

# A distinctive verbatim sentence that lives on PAGE_X only.
X_VERBATIM = ("The AKG K371 was praised for its clean neutral sound during an "
              "extended listening demonstration at the downtown audio shop")

CACHE = {
    PAGE_X: {"status": 200,
             "text": "<html><body><p>" + X_VERBATIM + ". It uses a large "
                     "dynamic driver and folds flat for travel.</p></body></html>"},
    PAGE_Y: {"status": 200,
             "text": "<html><body><p>Unrelated forum thread about budget "
                     "cables and adapters, nothing about that model here.</p>"
                     "</body></html>"},
}


def _pof(md):
    sc, detail = ds.score_proof_of_fetch(md, CACHE)
    per = {d["url"]: d for d in detail["per"]}
    return sc, detail, per


def test_cross_entry_bleed_does_not_pass():
    """Entry [1]'s title carries PAGE_X's verbatim text but points at PAGE_Y;
    entry [2] points at PAGE_X. The bugged anchor let entry [1]'s snippet prove
    PAGE_X (cited by [2]). After the fix, PAGE_X has no in-text anchor and is
    checked-and-failed; nothing verbatim-proves it."""
    md = (
        "## Analysis\n\n"
        "Headphones vary widely in build quality and price across brands, and "
        "listener preference matters more than the sticker.\n\n"
        "### Sources\n"
        "[1] " + X_VERBATIM + "\n"
        "    URL: " + PAGE_Y + "\n"
        "[2] Generic bibliography row with no verbatim page text at all.\n"
        "    URL: " + PAGE_X + "\n"
    )
    sc, detail, per = _pof(md)
    # both pages are cited (denominator counts them)
    assert detail["checked"] == 2
    # neither page is verbatim-proven: PAGE_X's only "evidence" was the bled
    # snippet from entry [1], now correctly refused.
    assert detail["passed"] == 0
    assert sc == 0.0
    # PAGE_X is checked-and-failed for lack of an in-text anchor
    px = per[PAGE_X[-60:]]
    assert px["passed"] is False
    assert px["reason"] == "no_inline_anchor"


def test_in_text_numbered_anchor_still_passes():
    """The same verbatim snippet, this time next to an IN-TEXT [3] marker in
    running prose, must still pass -- the fix removes only bibliography-row
    anchors, not legitimate numbered in-text evidence."""
    md = (
        "## Analysis\n\n"
        "A reviewer wrote that " + X_VERBATIM + " [3]. That firsthand demo is "
        "the clearest signal in the thread.\n\n"
        "### Sources\n"
        "[3] AKG K371 demo thread\n"
        "    URL: " + PAGE_X + "\n"
    )
    sc, detail, per = _pof(md)
    assert detail["checked"] == 1
    assert detail["passed"] == 1
    assert sc == 1.0


def test_footnote_definition_line_is_not_an_anchor():
    """A footnote DEFINITION line ``[^a]: <url>`` whose preceding text is the
    prior definition must not anchor. Only the inline ``[^a]`` in prose does."""
    md = (
        "## Notes\n\n"
        "Budget cables get plenty of discussion in the thread.\n\n"
        "[^a]: " + X_VERBATIM + " " + PAGE_Y + "\n"
        "[^b]: plain footnote " + PAGE_X + "\n"
    )
    sc, detail, per = _pof(md)
    assert detail["checked"] == 2
    assert detail["passed"] == 0
    assert sc == 0.0


def test_reference_region_offsets_detects_section_and_entries():
    md = (
        "Intro prose here mentioning a claim [9] inline.\n\n"
        "## References\n"
        "[1] first entry http://localhost:9999/a/1\n"
        "[2] second entry http://localhost:9999/a/2\n"
    )
    spans = ds._reference_region_offsets(md)
    assert spans, "should detect a reference region"
    inline_off = md.index("[9]")
    entry2_off = md.index("[2]")
    assert not ds._offset_in_spans(inline_off, spans)   # in-text marker kept
    assert ds._offset_in_spans(entry2_off, spans)       # ref entry excluded
