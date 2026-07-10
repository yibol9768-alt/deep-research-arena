"""Structured recall credit must be bound to its own inline source."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey


ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0002.json"


def _key_and_entity():
    key = AnswerKey.load(KEY_PATH)
    by_url = {e.url: e for e in key.relevant_set}
    nugget = next(n for n in key.vital_nuggets if n.predicate == "buyer_sentiment")
    entity = by_url[nugget.source_url]
    return key, nugget, entity


def _claim(entity, *, cite: bool) -> str:
    subject = f"[{entity.name}]({entity.url})" if cite else entity.name
    return f"{subject} is priced at ${float(entity.facts['price']):.2f}."


def test_uncited_correct_price_is_diagnostic_but_cannot_fill_fact_recall():
    key, _nugget, entity = _key_and_entity()
    score, detail = ds.score_fact_support(_claim(entity, cite=False), key)
    assert detail["supported"] == 1
    assert detail["supported_uncited"] == 1
    assert detail["distinct_supported_facts"] == 0
    assert detail["recall_vol"] == 0.0
    assert score == 0.0


def test_same_product_inline_citation_unlocks_fact_recall():
    key, _nugget, entity = _key_and_entity()
    score, detail = ds.score_fact_support(_claim(entity, cite=True), key)
    assert detail["supported"] == 1
    assert detail["supported_uncited"] == 0
    assert detail["distinct_supported_facts"] == 1
    assert score > 0.0


def test_reference_list_source_does_not_unlock_fact_recall():
    key, _nugget, entity = _key_and_entity()
    report = (
        _claim(entity, cite=False)
        + f"\n\n## References\n\n- [{entity.name}]({entity.url})"
    )
    score, detail = ds.score_fact_support(report, key)
    assert detail["supported"] == 1
    assert detail["supported_uncited"] == 1
    assert detail["distinct_supported_facts"] == 0
    assert score == 0.0


def test_detached_inline_source_does_not_unlock_fact_recall():
    key, _nugget, entity = _key_and_entity()
    report = (
        f"[Catalog source for later claims]({entity.url}).\n\n"
        + _claim(entity, cite=False)
    )
    score, detail = ds.score_fact_support(report, key)
    assert detail["supported"] == 1
    assert detail["supported_uncited"] == 1
    assert detail["distinct_supported_facts"] == 0
    assert score == 0.0


def _buyer_report(nugget, *, cite: bool) -> str:
    rating = str(nugget.object).split("%/", 1)[0]
    source = f" [listing]({nugget.source_url})" if cite else ""
    return f"{nugget.subject} is rated {rating}% positive.{source}"


def _buyer_key(key, nugget) -> AnswerKey:
    return AnswerKey(
        task_id=key.task_id,
        relevant_set=key.relevant_set,
        vital_nuggets=[nugget],
        metadata={"inline_nugget_citation_required": True},
    )


def test_uncited_structured_nugget_does_not_cover_completeness():
    key, nugget, _entity = _key_and_entity()
    score, detail = ds.score_completeness(
        _buyer_report(nugget, cite=False), _buyer_key(key, nugget),
        k_star=1, pool_size=1,
    )
    assert score == 0.0
    assert detail["covered"] == 0


def test_inline_nugget_source_covers_and_transport_must_include_same_page():
    key, nugget, _entity = _key_and_entity()
    report = _buyer_report(nugget, cite=True)
    scoped = _buyer_key(key, nugget)

    score, detail = ds.score_completeness(report, scoped, k_star=1, pool_size=1)
    assert score == 1.0
    assert detail["covered"] == 1

    missing = SimpleNamespace(available=True, fetched_ok=set())
    score_missing, _ = ds.score_completeness(
        report, scoped, k_star=1, pool_size=1, evidence=missing,
    )
    assert score_missing == 0.0

    fetched = SimpleNamespace(available=True, fetched_ok={nugget.source_url})
    score_fetched, _ = ds.score_completeness(
        report, scoped, k_star=1, pool_size=1, evidence=fetched,
    )
    assert score_fetched == 1.0


def test_detached_nugget_source_does_not_cover_completeness():
    key, nugget, _entity = _key_and_entity()
    report = (
        f"[Catalog source for later claims]({nugget.source_url})\n\n"
        + _buyer_report(nugget, cite=False)
    )
    score, detail = ds.score_completeness(
        report, _buyer_key(key, nugget), k_star=1, pool_size=1,
    )
    assert score == 0.0
    assert detail["covered"] == 0
