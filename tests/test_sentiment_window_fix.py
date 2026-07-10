"""Regression tests for two buyer_sentiment window-check defects that gate G3
exposed (a corrupted rating stayed covered on 3/100 tasks), both violations of
the scorer's own declared semantics, both red on the pre-fix code:

1. **Count credited as rating.** ``_typed_value_in_window``'s buyer_sentiment
   branch matched ANY standalone number near a rating cue against ``rat`` or
   ``rat/20``. The review COUNT sits inside every oracle-style sentence
   ("... X% positive across N reviews"), within 24 chars of the "positive"
   cue, so whenever ``N == rat/20`` (60%/3rev, 100%/5rev) or ``|N-rat|<=1`` a
   WRONG percentage kept the nugget covered. The function's own comment
   declares "The review COUNT is not the sentiment".

2. **Subject-name identity digits credited as rating.** A written-out product
   title such as "... iWatch SE Series 7 6 5 4 3 2 1 Women" contains
   standalone digits; "4" landed within 24 chars of "rated" and covered an
   80.0% nugget (4 == 80/20) whatever percentage the report stated. The fact
   axis already masks exact-name-span digits before value extraction
   ("identity, not claims"); completeness now applies the same masking.

   2b. **Window-edge blindness.** The +-40 window slice can cut "5 reviews"
   to "5 rev", hiding the count noun from guard (1); the guard therefore
   reads a 16-char tail past the window edge (classification only -- no value
   is extracted from the tail, so it can only remove credit).

Fixtures are the three real tasks G3 caught (0030 / 0044 / 0100) plus
positive controls proving the TRUE rating still covers, and the report cites
store + wiki + forum pages so a per-source parsing asymmetry cannot hide
(HANDOFF trap 1). Deterministic: no network, no clock, no randomness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.eval.decidable_scorer as ds
from src.eval.answer_key import AnswerKey

REPO_ROOT = Path(__file__).resolve().parents[1]

WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Tea"
FORUM = "http://localhost:9999/f/technology/27823"

# (task, expected first-ranked buyer_sentiment object, wrong percentage)
CASES = {
    # count == rat/20 (3 == 60/20): count-as-rating defect
    "dr_cross_deep_0030": ("60.0%/3rev", "97.0"),
    # count == rat/20 (5 == 100/20) AND the count noun is cut by the window
    # edge ("5 rev"): window-edge blindness defect
    "dr_cross_deep_0044": ("100.0%/5rev", "37.0"),
    # subject name carries standalone digits ("Series 7 6 5 4 3 2 1",
    # 4 == 80/20): identity-digit defect
    "dr_cross_deep_0100": ("80.0%/12rev", "17.0"),
}


def _first_sentiment_nugget(tid: str):
    ak = AnswerKey.load(REPO_ROOT / f"data/golden/answer_keys/{tid}.json")
    pool = ds.build_vital_pool(ak)
    n = next((x for x in pool if x.predicate == "buyer_sentiment"), None)
    return ak, n


def _report(nugget, pct: str, nrev: str) -> str:
    """An oracle-style report: the claim sentence plus one wiki and one forum
    citation, so all three sources flow through the same extractor."""
    return (
        "# Report\n\n"
        f"[{nugget.subject}]({nugget.source_url}) is rated {pct}% positive "
        f"across {nrev} reviews on the store product page.\n\n"
        f"Background reading: [tea culture]({WIKI}) and an "
        f"[owner discussion]({FORUM})."
    )


def _covered(report: str, ak) -> int:
    _, detail = ds.score_completeness(report, ak, cache={}, registry=None)
    return detail["covered_by_predicate"].get("buyer_sentiment", 0)


@pytest.mark.parametrize("tid", sorted(CASES))
def test_wrong_sentiment_percentage_is_not_covered(tid):
    """A report stating a WRONG percentage for the nugget's product must not
    cover the nugget, even when the review count or a name digit collides with
    rat/20. Red on the pre-fix scorer for all three tasks."""
    expected_object, wrong_pct = CASES[tid]
    ak, n = _first_sentiment_nugget(tid)
    if n is None or str(n.object) != expected_object:
        pytest.skip(f"{tid} first sentiment nugget changed "
                    f"(got {getattr(n, 'object', None)!r}); re-pin the case")
    nrev = str(n.object).split("/")[1].replace("rev", "")
    assert _covered(_report(n, wrong_pct, nrev), ak) == 0


@pytest.mark.parametrize("tid", sorted(CASES))
def test_true_sentiment_percentage_still_covers(tid):
    """Positive control: the guards must not eat honest coverage -- the TRUE
    percentage in the same phrasing still covers the nugget."""
    expected_object, _ = CASES[tid]
    ak, n = _first_sentiment_nugget(tid)
    if n is None or str(n.object) != expected_object:
        pytest.skip(f"{tid} first sentiment nugget changed "
                    f"(got {getattr(n, 'object', None)!r}); re-pin the case")
    pct, nrev = str(n.object).replace("rev", "").split("%/")
    assert _covered(_report(n, pct, nrev), ak) == 1


def test_five_star_scale_rating_still_covers():
    """The /20 five-star branch itself stays alive: '3.0 out of 5 stars' (with
    a stars cue, not a count noun) covers a 60% nugget."""
    ak, n = _first_sentiment_nugget("dr_cross_deep_0030")
    if n is None or str(n.object) != "60.0%/3rev":
        pytest.skip("task 0030 first sentiment nugget changed; re-pin")
    report = (
        "# Report\n\n"
        f"[{n.subject}]({n.source_url}) is rated 3.0 out of 5 stars by "
        f"buyers on the store page.\n\n"
        f"Background reading: [tea culture]({WIKI}) and an "
        f"[owner discussion]({FORUM})."
    )
    assert _covered(report, ak) == 1
