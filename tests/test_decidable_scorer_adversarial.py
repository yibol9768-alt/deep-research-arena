"""Adversarial regressions for structured fact binding and volume."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.eval.answer_key import AnswerKey, Entity
from src.eval import decidable_scorer as ds


U1 = "http://localhost:7770/acme-alpha.html"
U2 = "http://localhost:7770/acme-beta.html"
N1 = ("Acme Professional Studio Monitor Speaker System Model Alpha Black "
      "with 7.2 Channels and 2 RP-8000F Towers")
N2 = ("Acme Professional Studio Monitor Speaker System Model Beta Red "
      "with 5.1 Channels and 4 RP-600M Towers")


@pytest.fixture
def key():
    return AnswerKey(task_id="t", relevant_set=[
        Entity(U1, N1, "shopping_product", {"price": "1769.00", "rating": "4.5"}),
        Entity(U2, N2, "shopping_product", {"price": "999.00", "rating": "4.1"}),
    ])


def test_exact_long_name_and_db_price_do_not_cross_bind(key):
    report = f"{N1} is priced at $1,769.00."
    _score, d = ds.score_fact_support(report, key)
    assert (d["supported"], d["contradicted"], d["unbound"]) == (1, 0, 0)


def test_numbers_inside_plain_product_name_are_not_claims(key):
    report = f"{N1} is priced at $1,769.00."
    _score, d = ds.score_fact_support(report, key)
    assert d["claims_tested"] == 1
    assert d["sample"][0][2] == "1,769.00"


def test_ambiguous_shared_prefix_is_unbound(key):
    report = "Acme Professional Studio Monitor Speaker System costs $1769.00."
    _score, d = ds.score_fact_support(report, key)
    assert d["claims_tested"] == 0
    assert d["unbound"] >= 1


def test_unique_link_binds_price_and_rating_consistently(key):
    report = f"[This exact item]({U1}) costs $1,769.00 | rating 4.5/5."
    _score, d = ds.score_fact_support(report, key)
    assert d["supported"] == 2
    assert d["contradicted"] == 0
    assert {row[1] for row in d["sample"]} == {"price", "rating"}


def test_unique_link_does_not_steal_an_explicit_second_product(key):
    report = (
        f"[{N1}]({U1}) costs $1,769.00; "
        f"{N2} costs $999.00."
    )
    _score, d = ds.score_fact_support(report, key)
    assert (d["supported"], d["contradicted"]) == (2, 0)


def test_nearest_product_beats_a_longer_farther_name():
    long_name = (
        "Acme Ultra Long Professional Studio Monitor Speaker System Model "
        "Alpha Black Special Edition Deluxe Bundle"
    )
    short_name = "Beta Compact Speaker"
    local_key = AnswerKey(task_id="nearest", relevant_set=[
        Entity(U1, long_name, "shopping_product", {"price": "1769.00"}),
        Entity(U2, short_name, "shopping_product", {"price": "999.00"}),
    ])
    report = f"{long_name}; {short_name} costs $999.00."
    _score, d = ds.score_fact_support(report, local_key)
    assert (d["supported"], d["contradicted"]) == (1, 0)


def test_rating_fraction_and_denominator_are_never_prices(key):
    report = f"| [{N1}]({U1}) | $1,769.00 | 4.5/5 |"
    _score, d = ds.score_fact_support(report, key)
    assert d["supported"] == 2
    assert d["contradicted"] == 0
    assert d["claims_tested"] == 2


def test_completeness_accepts_thousands_formatted_price():
    nugget = SimpleNamespace(predicate="price", object="1769.00")
    assert ds._typed_value_in_window("priced at $1,769.00", nugget)


def test_distinct_claims_are_deduplicated_and_false_claims_buy_no_recall(key):
    one = f"[{N1}]({U1}) costs $1,769.00."
    wrong = f"[{N1}]({U1}) costs $123.45."
    _s, d = ds.score_fact_support("\n".join([one, one, wrong, wrong]), key)
    assert d["supported"] == 1
    assert d["contradicted"] == 1
    assert d["duplicate_claims_ignored"] == 2
    assert d["claims_tested"] == 2
    assert d["recall_vol"] == pytest.approx(0.1)

    _s2, d2 = ds.score_fact_support("\n".join([wrong, wrong]), key)
    assert d2["supported"] == 0
    assert d2["recall_vol"] == 0.0


def test_tolerance_variants_of_one_fact_cannot_fill_recall_volume():
    name = "Acme Unique Product Alpha"
    local_key = AnswerKey(task_id="tolerance", relevant_set=[
        Entity(U1, name, "shopping_product", {"price": "1769.00"}),
    ])
    report = "\n".join(
        f"{name} costs ${value:.2f}."
        for value in (1752, 1755, 1758, 1761, 1764,
                      1767, 1770, 1773, 1776, 1779)
    )
    score, detail = ds.score_fact_support(report, local_key)
    assert detail["supported"] == 10
    assert detail["distinct_supported_facts"] == 1
    assert detail["recall_vol"] == pytest.approx(0.1)
    assert score < 0.2
