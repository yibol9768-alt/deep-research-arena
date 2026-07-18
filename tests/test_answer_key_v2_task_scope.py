import pytest

from scripts.build_answer_keys_v2 import build_key, scope_gold_contradictions


def _product(slug, name):
    return {
        "url": f"http://localhost:7770/{slug}.html",
        "name": name,
        "facts": {},
    }


def _sent(slug, name, rating, reviews):
    return {
        "url_key": slug,
        "name": name,
        "rating_pct": rating,
        "n_reviews": reviews,
        "complaint_terms": [],
    }


def test_vital_product_override_is_exact_ordered_and_auditable():
    products = [
        _product("generic", "Generic Headphones"),
        _product("over-ear", "Acme ANC Over-Ear"),
        _product("earbuds", "Acme ANC Earbuds"),
    ]
    sent = {
        "generic": _sent("generic", "Generic Headphones", 90.0, 100),
        "over-ear": _sent("over-ear", "Acme ANC Over-Ear", 80.0, 12),
        "earbuds": _sent("earbuds", "Acme ANC Earbuds", 70.0, 11),
    }
    urls = [products[2]["url"], products[1]["url"]]
    spec = {
        "cluster": "headphones_audio",
        "archetype": "use-case-fit",
        "intent": "Choose ANC headphones or earbuds for a flight",
        "vital_product_urls": urls,
        "wiki_topics": [],
    }

    key = build_key("task", spec, products, sent)

    assert [n.source_url for n in key.vital_nuggets] == urls
    assert key.metadata["vital_product_override"] is True
    assert key.metadata["vital_product_count"] == 2
    assert key.useful_nuggets[0].source_url == products[0]["url"]


def test_vital_product_override_fails_closed_on_unknown_or_unreviewed_url():
    products = [_product("known", "Known ANC Headphones")]
    sent = {"known": _sent("known", "Known ANC Headphones", 80.0, 12)}
    spec = {
        "cluster": "headphones_audio",
        "intent": "ANC headphones",
        "vital_product_urls": ["http://localhost:7770/missing.html"],
    }

    with pytest.raises(ValueError, match="vital_product_urls missing"):
        build_key("task", spec, products, sent)


def test_contradiction_scope_vital_drops_unrelated_cluster_products():
    products = [
        _product("chosen", "Chosen ANC Headphones"),
        _product("soundbar", "Unrelated Soundbar"),
    ]
    sent = {
        "chosen": _sent("chosen", "Chosen ANC Headphones", 80.0, 12),
        "soundbar": _sent("soundbar", "Unrelated Soundbar", 70.0, 12),
    }
    key = build_key("task", {
        "cluster": "headphones_audio",
        "intent": "ANC headphones",
        "vital_product_urls": [products[0]["url"]],
    }, products, sent)
    candidates = [
        {"product_url": products[0]["url"], "candidate_id": "keep"},
        {"product_url": products[1]["url"], "candidate_id": "drop"},
    ]

    scoped = scope_gold_contradictions(
        key, candidates, {"contradictions_product_scope": "vital"}
    )

    assert [row["candidate_id"] for row in scoped] == ["keep"]
    assert scope_gold_contradictions(key, candidates, {}) == candidates
