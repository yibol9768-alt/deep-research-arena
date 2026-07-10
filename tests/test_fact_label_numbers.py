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

import re
from pathlib import Path

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey
from src.verifiers.citation_format import canonicalize_url

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0002.json"

_NAME_NUM_RE = re.compile(r"(?<![\w.])\d+(?![\w.])")


def _priced_entity(ak):
    """An in-scope, DB-priced entity whose name ends in a parenthetical pack
    count, selected programmatically so an answer-key name change does not break
    the test. In-scope (its URL is a ranked price/rating/sentiment nugget) so
    ruling #3 (docs/SPEC_DECISIONS.md) does not withdraw its correct price from
    `tested`; the trailing pack-count digit is the label number the masking fix
    must never extract as a price value."""
    scoped = {canonicalize_url(n.source_url)
              for n in ak.vital_nuggets + ak.useful_nuggets
              if n.predicate in {"buyer_sentiment", "price", "rating"}}
    priced = [e for e in ak.relevant_set
              if (e.facts or {}).get("price")
              and canonicalize_url(e.url) in scoped]
    packs = [e for e in priced
             if re.search(r"\(pack of \d+\)\s*$", e.name, re.IGNORECASE)]
    return (packs or priced)[0]


def _name_numbers(e) -> set[str]:
    return set(_NAME_NUM_RE.findall(e.name))


def test_label_number_not_extracted_as_price():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    price = float(e.facts["price"])
    sent = f"The [{e.name}]({e.url}) is priced at ${price:.2f}."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["claims_tested"] == 1
    assert det["supported"] == 1
    assert det["contradicted"] == 0
    # no standalone number from the NAME (pack count, count box) may surface as
    # a claim value
    name_nums = _name_numbers(e)
    assert all(row[2] not in name_nums for row in det["sample"])


def test_wrong_prose_price_contradicts_without_label_number():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    sent = f"The [{e.name}]({e.url}) is priced at $9999.99."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["contradicted"] >= 1
    # the only tested claim is the wrong prose price, never a label number
    name_nums = _name_numbers(e)
    assert all(row[2] not in name_nums for row in det["sample"])
    assert any(row[2] == "9999.99" for row in det["sample"])


def test_link_plus_prose_without_number_tests_nothing():
    ak = AnswerKey.load(ANSWER_KEY)
    e = _priced_entity(ak)
    sent = f"The [{e.name}]({e.url}) is a solid pick for the office."
    _score, det = ds.score_fact_support(sent, ak)
    assert det["claims_tested"] == 0
