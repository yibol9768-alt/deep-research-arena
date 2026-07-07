"""Regression tests for score_fact_support: numbers inside a markdown link
label are subject identity (pack counts, size tokens), never claim VALUES.

Repro of the G-F6 tail bug: a product whose NAME ends in "(Pack of 3)" was
cited with a correct prose price. The trailing "3" sat inside the price-cue
window and got extracted as a phantom price claim, contradicting DB truth and
dropping a perfectly correct sentence to precision 0.5. The fix masks standalone
numbers inside a [label](url) while keeping the label words for subject binding.

Offline: only the shipped answer key is loaded; no network / DB.
"""

from __future__ import annotations

from pathlib import Path

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0002.json"


def _priced_entity(ak):
    """The first relevant entity that carries a DB price, selected
    programmatically so a name change in the answer key does not break the
    test. This entity's name ends in a parenthetical pack count."""
    return [e for e in ak.relevant_set if (e.facts or {}).get("price")][0]


def test_label_number_not_extracted_as_price():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    sent = f"The [{e.name}]({e.url}) is priced at $5.20."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["claims_tested"] == 1
    assert det["supported"] == 1
    assert det["contradicted"] == 0
    # the pack count "3" from the name must not surface as a claim value
    assert all(row[2] != "3" for row in det["sample"])


def test_wrong_prose_price_contradicts_without_label_number():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    sent = f"The [{e.name}]({e.url}) is priced at $9999.99."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["contradicted"] >= 1
    # the only tested claim is the wrong prose price, never a label number
    assert all(row[2] != "3" for row in det["sample"])
    assert any(row[2] == "9999.99" for row in det["sample"])


def test_link_plus_prose_without_number_tests_nothing():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    sent = f"The [{e.name}]({e.url}) is a solid pick for the office."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["claims_tested"] == 0
