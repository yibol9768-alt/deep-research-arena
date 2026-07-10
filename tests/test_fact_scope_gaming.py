"""Fact-volume credit must stay inside the task-ranked gold scope."""

from __future__ import annotations

from pathlib import Path

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey
from src.verifiers.citation_format import canonicalize_url


ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0002.json"


def _scope(ak):
    scoped_urls = {
        canonicalize_url(n.source_url)
        for n in ak.vital_nuggets + ak.useful_nuggets
        if n.predicate in {"buyer_sentiment", "price", "rating"}
    }
    priced = [e for e in ak.relevant_set if (e.facts or {}).get("price") is not None]
    inside = [e for e in priced if canonicalize_url(e.url) in scoped_urls]
    outside = [e for e in priced if canonicalize_url(e.url) not in scoped_urls]
    assert inside and len(outside) >= 10
    return inside, outside


def _price_claim(entity) -> str:
    price = float(entity.facts["price"])
    return f"[{entity.name}]({entity.url}) is priced at ${price:.2f}."


def test_task_scoped_correct_fact_earns_recall_credit():
    ak = AnswerKey.load(KEY)
    inside, _outside = _scope(ak)

    score, detail = ds.score_fact_support(_price_claim(inside[0]), ak)

    assert detail["supported"] == 1
    assert detail["supported_out_of_scope"] == 0
    assert detail["distinct_supported_facts"] == 1
    assert score > 0


def test_ten_unrelated_catalog_prices_cannot_fill_fact_recall():
    ak = AnswerKey.load(KEY)
    _inside, outside = _scope(ak)
    report = "\n".join(_price_claim(e) for e in outside[:10])

    score, detail = ds.score_fact_support(report, ak)

    assert detail["claims_tested"] == 10
    assert detail["supported"] == 10
    assert detail["supported_out_of_scope"] == 10
    assert detail["distinct_supported_facts"] == 0
    assert detail["recall_vol"] == 0.0
    assert score == 0.0
