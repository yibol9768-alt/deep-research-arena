"""Concept completeness requires same-page support and transport provenance."""

from __future__ import annotations

from src.eval.answer_key import AnswerKey, Entity, Nugget
from src.eval.fetch_log import RunEvidence, canonical
from src.eval import decidable_scorer as ds


WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Qi_(standard)"
SHOP = "http://localhost:7770/acme-widget.html"
PAGE = ("The Qi standard transfers electrical power through inductive coupling "
        "between compatible charging devices.")


class Registry:
    loaded = True

    def __init__(self, unknown=False):
        self.unknown = unknown

    def classify(self, url):
        return {"kind": "content", "canonical": url,
                "in_corpus": None if self.unknown else True,
                "reason": "test"}


def concept_key():
    return AnswerKey(task_id="t", vital_nuggets=[Nugget(
        text="Explains Qi", subject="Qi (standard)",
        predicate="concept_coverage", object="Qi (standard)",
        source_url=WIKI, importance="vital")])


def test_url_and_title_shell_do_not_cover_concept():
    report = f"Qi (standard). [Qi (standard)]({WIKI})"
    score, detail = ds.score_completeness(
        report, concept_key(), k_star=1,
        cache={WIKI: {"status": 200, "text": PAGE}}, registry=Registry())
    assert score == 0.0
    assert detail["covered"] == 0


def test_same_page_lexical_support_covers_without_transport():
    report = f"{PAGE} [source]({WIKI})"
    score, detail = ds.score_completeness(
        report, concept_key(), k_star=1,
        cache={WIKI: {"status": 200, "text": PAGE}}, registry=Registry())
    assert score == 1.0
    assert detail["covered_by_predicate"] == {"concept_coverage": 1}


def test_transport_requires_concept_page_actually_fetched():
    report = f"{PAGE} [source]({WIKI})"
    missing = RunEvidence(available=True)
    score, _ = ds.score_completeness(
        report, concept_key(), k_star=1,
        cache={WIKI: {"status": 200, "text": PAGE}}, registry=Registry(),
        evidence=missing)
    assert score == 0.0

    fetched = RunEvidence(available=True)
    fetched.fetched[canonical(WIKI)] = {"status": 200}
    score, _ = ds.score_completeness(
        report, concept_key(), k_star=1,
        cache={WIKI: {"status": 200, "text": PAGE}}, registry=Registry(),
        evidence=fetched)
    assert score == 1.0


def test_transport_truth_uses_provenance_not_guessable_reach():
    key = AnswerKey(task_id="t", relevant_set=[Entity(
        SHOP, "Acme Widget", "shopping_product", {"price": "10.00"})])
    report = f"Acme Widget costs $10.00. Guessed wiki shell [source]({WIKI})."
    out = ds.score_report(
        report, key, {WIKI: {"status": 200, "text": PAGE}},
        registry=Registry(), evidence=RunEvidence(available=True), k_f=1)
    assert out.reach == 1.0
    assert out.detail["gate_semantics"] == "provenance_v2"
    assert out.detail["gate_value"] == 0.0
    assert out.truth == 0.0


def test_unknown_membership_cache_fallback_matches_reach_and_transport():
    cache = {WIKI: {"status": 200, "text": PAGE}}
    reach, _ = ds.score_reachability([WIKI], cache, Registry(unknown=True))
    evidence = RunEvidence(available=True)
    evidence.search_returned.add(canonical(WIKI))
    transport = ds.transport_metrics_for(
        [WIKI], evidence, Registry(unknown=True), cache=cache)
    assert reach == 1.0
    assert transport["fabrication"] == 0.0
    assert transport["provenance"] == 1.0

