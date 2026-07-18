from __future__ import annotations

from src.eval.observation_ledger import ObservationLedger, sha256_text
from src.eval.query_rubric_schema import compile_query_rubric
from src.eval.query_rubric_scorer import (
    aggregate_query_rubric_scores,
    score_query_rubric,
)
from src.eval.url_registry import UrlRegistry


REAL = "http://localhost:9999/f/headphones/42"
FAKE = "http://localhost:9999/f/headphones/99999"
WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Headphones"
BODY = "Several frequent flyers report that glasses arms can weaken the earcup seal."
REGISTRY_HASH = "b" * 64


def _rubric(*, required_roles: tuple[str, ...] = (), minimum_sources: int = 1):
    task = {
        "task_id": "route_a_demo",
        "task_version": 2,
        "intent": "Do glasses affect the headphone seal?",
        "tri_source": {"cluster": "audio", "archetype": "claim-check"},
    }
    atom = {
        "atom_id": "A_seal",
        "atom_type": "dimension",
        "description": "Discuss the glasses and seal interaction.",
        "mention": {"all_term_groups": [["glasses"], ["seal"]]},
        "response_contract": {
            "all_term_groups": [["glasses"], ["seal"]],
            "accepted_regex": ["glasses.{0,100}seal|seal.{0,100}glasses"],
        },
        "evidence": {
            "acceptable_source_roles": ["forums", "wiki"] if required_roles else ["forums"],
            "required_source_roles": list(required_roles),
            "minimum_distinct_sources": minimum_sources,
            "observation_mode": "body",
            "track_discovery": True,
            "relevance_contract": {"all_term_groups": [["glasses"], ["seal"]]},
            "known_support": [{
                "evidence_id": "ev-seal",
                "source_url": REAL,
                "source_role": "forums",
                "support_span_sha256": "a" * 64,
                "approved": True,
            }] + ([{
                "evidence_id": "ev-wiki-seal",
                "source_url": WIKI,
                "source_role": "wiki",
                "support_span_sha256": "d" * 64,
                "approved": True,
            }] if "wiki" in required_roles else []),
        },
        "approved": True,
    }
    return compile_query_rubric(
        task, [atom], status="frozen", reviewers=["reviewer-1"],
        evidence_graph_stamp="graph-demo-v1", corpus_registry_hash=REGISTRY_HASH,
    )


def _registry() -> UrlRegistry:
    return UrlRegistry(
        submissions={"42": "headphones"}, wiki=["Headphones"], wiki_complete=True
    )


def _ledger(*, complete: bool = True, body: str = BODY) -> ObservationLedger:
    records = [
        {
            "run_id": "run-1",
            "event_id": 1,
            "timestamp": 1,
            "event_type": "search_result",
            "url": REAL,
            "content_text": "Frequent flyer discussion about eyeglasses and headphones.",
            "content_sha256": sha256_text("Frequent flyer discussion about eyeglasses and headphones."),
        },
        {
            "run_id": "run-1",
            "event_id": 2,
            "timestamp": 2,
            "event_type": "fetch_body",
            "url": REAL,
            "parent_event_id": 1,
            "http_status": 200,
            "content_text": body,
            "content_sha256": sha256_text(body),
        },
    ]
    return ObservationLedger.from_records(
        records, expected_run_id="run-1", capture_complete=complete
    )


def test_grounded_atom_passes_and_fake_url_is_reported_separately() -> None:
    report = (
        f"Glasses can weaken the seal on an earcup [{1}]({REAL}).\n\n"
        f"An unrelated bibliography entry points elsewhere [x]({FAKE})."
    )
    result = score_query_rubric(
        _rubric(), report, _ledger(), _registry(), expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["status"] == "ok"
    assert result["requirement_coverage"] == 1.0
    assert result["grounded_requirement_coverage"] == 1.0
    assert result["url_fabrication_rate"] == 0.5
    assert result["integrity_clean"] is False
    assert result["atom_results"][0]["passed"] is True


def test_thought_only_counts_as_mention_not_grounded_completion() -> None:
    result = score_query_rubric(
        _rubric(),
        "Glasses can weaken the seal on an earcup.",
        _ledger(),
        _registry(),
        expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["requirement_coverage"] == 1.0
    assert result["grounded_requirement_coverage"] == 0.0
    assert result["integrity_clean"] is None
    assert result["atom_results"][0]["reason_codes"] == ["no_local_citation"]


def test_distant_citation_in_a_long_paragraph_is_not_locally_bound() -> None:
    report = (
        "Glasses can weaken the seal on an earcup. "
        + ("unrelated filler " * 100)
        + f"[source]({REAL})."
    )
    result = score_query_rubric(
        _rubric(), report, _ledger(), _registry(), expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["requirement_coverage"] == 1.0
    assert result["grounded_requirement_coverage"] == 0.0
    assert result["atom_results"][0]["citation_bound"] is False


def test_support_terms_scattered_across_a_page_do_not_form_support() -> None:
    scattered = "glasses " + ("unrelated " * 300) + "seal"
    report = f"Glasses can weaken the seal [source]({REAL})."
    result = score_query_rubric(
        _rubric(), report, _ledger(body=scattered), _registry(),
        expected_run_id="run-1", corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["grounded_requirement_coverage"] == 0.0
    assert result["atom_results"][0]["relevant_evidence_observed"] is False


def test_fabricated_citation_cannot_support_an_atom() -> None:
    report = f"Glasses can weaken the seal on an earcup [source]({FAKE})."
    result = score_query_rubric(
        _rubric(), report, _ledger(), _registry(), expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["grounded_requirement_coverage"] == 0.0
    assert result["url_fabrication_rate"] == 1.0
    assert "citation_not_acceptable_source" in result["atom_results"][0]["reason_codes"]


def test_required_source_roles_cannot_be_replaced_by_more_of_one_role() -> None:
    report = f"Glasses can weaken the seal [source]({REAL})."
    result = score_query_rubric(
        _rubric(required_roles=("forums", "wiki"), minimum_sources=2),
        report,
        _ledger(),
        _registry(),
        expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    atom = result["atom_results"][0]
    assert result["grounded_requirement_coverage"] == 0.0
    assert atom["observed_source_roles"] == ["forums"]
    assert "required_source_roles_missing" in atom["reason_codes"]


def test_direct_fetch_counts_as_observed_but_discovery_is_a_diagnostic() -> None:
    body_only = ObservationLedger.from_records(
        [{
            "run_id": "run-1",
            "event_id": 1,
            "timestamp": 1,
            "event_type": "fetch_body",
            "url": REAL,
            "http_status": 200,
            "content_text": BODY,
            "content_sha256": sha256_text(BODY),
        }],
        expected_run_id="run-1",
        capture_complete=True,
    )
    report = f"Glasses can weaken the seal on an earcup [source]({REAL})."
    result = score_query_rubric(
        _rubric(), report, body_only, _registry(), expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["grounded_requirement_coverage"] == 1.0
    assert result["acquisition_trace_coverage"] == 0.0
    assert result["atom_results"][0]["support_checks"][0]["supported"] is True
    assert result["atom_results"][0]["support_checks"][0]["discovery_traced"] is False


def test_incomplete_capture_is_withheld_not_converted_to_zero() -> None:
    result = score_query_rubric(
        _rubric(),
        f"Glasses weaken the seal [source]({REAL}).",
        _ledger(complete=False),
        _registry(),
        expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )

    assert result["status"] == "withheld"
    assert result["grounded_requirement_coverage"] is None
    assert "observation_capture_incomplete" in result["reason_codes"]


def test_frozen_rubric_refuses_a_different_registry_snapshot() -> None:
    result = score_query_rubric(
        _rubric(),
        f"Glasses weaken the seal [source]({REAL}).",
        _ledger(),
        _registry(),
        expected_run_id="run-1",
        corpus_registry_hash="c" * 64,
    )

    assert result["status"] == "withheld"
    assert result["reason_codes"] == ["corpus_registry_hash_mismatch"]


def test_aggregate_keeps_breadth_and_url_integrity_as_separate_columns() -> None:
    good = score_query_rubric(
        _rubric(),
        f"Glasses can weaken the seal [source]({REAL}).",
        _ledger(),
        _registry(),
        expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )
    thought_only = score_query_rubric(
        _rubric(), "Glasses can weaken the seal.", _ledger(), _registry(), expected_run_id="run-1",
        corpus_registry_hash=REGISTRY_HASH,
    )
    agg = aggregate_query_rubric_scores([good, thought_only])

    assert agg["macro_grounded_requirement_coverage"] == 0.5
    assert agg["macro_requirement_coverage"] == 1.0
    assert agg["url_fabrication_rate"] == 0.0
    assert agg["integrity_clean_rate"] == 1.0
    assert "quality" not in agg
