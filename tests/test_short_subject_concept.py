"""Ruling #5 (docs/SPEC_DECISIONS.md lane addendum): the short-topic concept
deadlock is an implementation bug, not the spec's intent. A concept whose whole
subject is a short common word ("Tea", a single 3-char token) has no strong
identity token, so ``_subject_discussed``'s strong-token rule scored it "not
discussed" for EVERY report -- including a perfect oracle that quotes and cites
the page. The fix falls back to WORD-BOUNDARY exact matching for all-short-token
subjects: a genuinely discussed short concept is credited, a substring collision
("tea" inside "team") is not.

Fixture spans all three sources (shopping 7770 / wiki 8090 / forum 9999).
"""

from __future__ import annotations

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey, Entity, Nugget
from src.eval.url_registry import UrlRegistry

REG = UrlRegistry.load()

PRODUCT = "http://localhost:7770/twinings-english-breakfast.html"
WIKI_TEA = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Tea"
# The concept ("Tea") is the ruling #5 focus. The corpus has no /f/tea threads,
# so the third source is a real in-corpus headphones thread (spanning shopping /
# wiki / forum is what the fixture requires, not thematic coherence).
FORUM = "http://localhost:9999/f/headphones/20234"

TEA_PAGE = (
    "Tea is an aromatic beverage prepared by pouring hot or boiling water over "
    "cured or fresh leaves of Camellia sinensis, an evergreen shrub native to "
    "East Asia. After water it is the most widely consumed drink in the world. "
    "There are many different types of tea, some of which have a cooling, "
    "slightly bitter and astringent flavour, while others have profoundly "
    "different profiles that include sweet, nutty, floral or grassy notes. Tea "
    "originated in the region encompassing present-day southwest China and "
    "north Myanmar, where it was used as a medicinal drink by many ethnic groups."
)
FORUM_PAGE = (
    "Owners say active noise cancellation helps bus commuters and noisy office "
    "workers hear their music clearly at lower volumes. Long listening sessions "
    "can still feel uncomfortable around the ears after several hours, and most "
    "agree the isolation is worth the occasional pressure on a long commute."
)

# The concept quote sits in prose directly before its citation (a quote inside a
# link label is stripped by the verbatim judge). The link label "Tea" makes the
# short subject discoverable at a word boundary in the visible prose.
REPORT = (
    f"The Twinings English Breakfast sells for $6.49 [spec]({PRODUCT}).\n\n"
    f"{TEA_PAGE} [Tea]({WIKI_TEA})\n\n"
    f"{FORUM_PAGE} [thread]({FORUM})"
)

CACHE = {
    WIKI_TEA: {"status": 200, "text": TEA_PAGE},
    FORUM: {"status": 200, "text": FORUM_PAGE},
}


def _key() -> AnswerKey:
    return AnswerKey(
        task_id="tea",
        relevant_set=[
            Entity(PRODUCT, "Twinings English Breakfast", "shopping_product",
                   {"price": "6.49"}),
        ],
        vital_nuggets=[
            Nugget(text="price", subject="Twinings English Breakfast",
                   predicate="price", object="6.49", source_url=PRODUCT,
                   importance="vital"),
            Nugget(text="concept", subject="Tea", predicate="concept_coverage",
                   object="Tea", source_url=WIKI_TEA, importance="vital"),
        ],
        metadata={
            "forums": ["headphones"],
            "forum_core_keywords": ["headphones", "audio"],
            "forum_query_keywords": ["noise", "cancellation", "bus", "office"],
        },
    )


def test_subject_discussed_word_boundary_for_short_subject():
    # word-boundary match credits a genuinely discussed short concept ...
    assert ds._subject_discussed("we brewed some tea this morning", ["tea"]) is True
    # ... but a substring collision ("tea" inside "team"/"steam") does not
    assert ds._subject_discussed("the team won the match", ["tea"]) is False
    assert ds._subject_discussed("a cloud of steam rose", ["tea"]) is False


def test_short_subject_concept_earns_completeness_credit():
    """Red on old code: 'Tea' had no strong token, so the concept slot scored 0
    for the oracle-style report. Now it is credited."""
    score, det = ds.score_completeness(REPORT, _key(), k_star=3, cache=CACHE,
                                       registry=REG)
    assert det["covered_by_predicate"].get("concept_coverage", 0) == 1
    assert det["covered"] == 3  # product + concept + forum
    assert score == 1.0


def test_short_subject_concept_still_needs_a_real_quote():
    """Guard: the fix does not credit a URL/title shell. A report that names Tea
    but quotes nothing earns no concept credit."""
    shell = (
        f"The Twinings English Breakfast sells for $6.49 [spec]({PRODUCT}).\n\n"
        f"Tea exists as a topic. [Tea]({WIKI_TEA})\n\n"
        f"{FORUM_PAGE} [thread]({FORUM})"
    )
    _score, det = ds.score_completeness(shell, _key(), k_star=3, cache=CACHE,
                                        registry=REG)
    assert det["covered_by_predicate"].get("concept_coverage", 0) == 0
