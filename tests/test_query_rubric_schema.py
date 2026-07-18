from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.eval.query_rubric_schema import (
    RubricValidationError,
    audit_known_support_directory,
    compile_query_rubric,
    query_sha256,
)


def _task() -> dict:
    return {
        "task_id": "route_a_demo",
        "task_version": 2,
        "intent": "Do glasses affect the headphone seal?",
        "tri_source": {"cluster": "audio", "archetype": "claim-check"},
        # Deliberately stale. The compiler must not consume it.
        "synthesis_requirements": {"required_output": ["buy_a_keyboard"]},
    }


def _atom() -> dict:
    return {
        "atom_id": "A_seal",
        "atom_type": "dimension",
        "description": "Discuss the glasses and seal interaction.",
        "required": True,
        "mention": {"all_term_groups": [["glasses"], ["seal"]]},
        "response_contract": {
            "all_term_groups": [["glasses"], ["seal"]],
            "accepted_regex": ["glasses.{0,80}seal|seal.{0,80}glasses"],
        },
        "evidence": {
            "acceptable_source_roles": ["forums"],
            "minimum_distinct_sources": 1,
            "observation_mode": "body",
            "track_discovery": True,
            "relevance_contract": {"all_term_groups": [["glasses"], ["seal"]]},
            "known_support": [{
                "evidence_id": "ev-seal",
                "source_url": "http://localhost:9999/f/headphones/42",
                "source_role": "forums",
                "support_span_sha256": "a" * 64,
                "approved": True,
            }],
        },
        "approved": True,
    }


def test_compiler_freezes_exact_query_and_ignores_stale_synthesis_fields() -> None:
    rubric = compile_query_rubric(
        _task(), [_atom()], status="frozen", reviewers=["reviewer-1"],
        evidence_graph_stamp="graph-demo-v1", corpus_registry_hash="b" * 64,
    )
    payload = rubric.to_dict()

    assert payload["query_sha256"] == query_sha256(_task()["intent"])
    assert payload["atoms"][0]["atom_id"] == "A_seal"
    assert "buy_a_keyboard" not in str(payload)
    assert payload["rubric_sha256"] == rubric.content_sha256


def test_frozen_rubric_requires_reviewed_atoms_and_named_reviewer() -> None:
    atom = _atom()
    atom["approved"] = False
    with pytest.raises(RubricValidationError, match="all atoms must be approved"):
        compile_query_rubric(
            _task(), [atom], status="frozen", reviewers=["r"],
            evidence_graph_stamp="g", corpus_registry_hash="b" * 64,
        )

    with pytest.raises(RubricValidationError, match="named reviewer"):
        compile_query_rubric(_task(), [_atom()], status="frozen")


def test_route_a_forbids_atom_weights_and_detects_query_tampering() -> None:
    atom = _atom()
    atom["weight"] = 0.7
    with pytest.raises(RubricValidationError, match="weights are forbidden"):
        compile_query_rubric(_task(), [atom])

    rubric = compile_query_rubric(
        _task(), [_atom()], status="frozen", reviewers=["r"],
        evidence_graph_stamp="graph-demo-v1", corpus_registry_hash="b" * 64,
    ).to_dict()
    tampered = deepcopy(rubric)
    tampered["query"] += " Changed after freezing."
    with pytest.raises(RubricValidationError, match="query_sha256"):
        from src.eval.query_rubric_schema import QueryRubric

        QueryRubric.from_dict(tampered)


def test_frozen_rubric_requires_a_non_binding_support_witness() -> None:
    atom = _atom()
    atom["evidence"]["known_support"] = []
    with pytest.raises(RubricValidationError, match="known_support witnesses"):
        compile_query_rubric(
            _task(), [atom], status="frozen", reviewers=["r"],
            evidence_graph_stamp="graph-demo-v1", corpus_registry_hash="b" * 64,
        )


def test_known_support_witness_replays_against_graph_span_and_registry(tmp_path) -> None:
    rubric = compile_query_rubric(
        _task(), [_atom()], status="frozen", reviewers=["r"],
        evidence_graph_stamp="graph-demo-v1", corpus_registry_hash="b" * 64,
    )
    url = "http://localhost:9999/f/headphones/42"
    (tmp_path / "nodes.jsonl").write_text(json.dumps({
        "evidence_id": "ev-seal",
        "source_url": url,
        "source_type": "postmill",
    }) + "\n", encoding="utf-8")
    (tmp_path / "support_spans.jsonl").write_text(json.dumps({
        "evidence_id": "ev-seal",
        "source_url": url,
        "sha256": "a" * 64,
    }) + "\n", encoding="utf-8")
    (tmp_path / "corpus_registry.json").write_text(json.dumps({
        "entries": [{"source_url": url, "in_corpus": True}],
    }), encoding="utf-8")

    audit = audit_known_support_directory(rubric, tmp_path)
    assert audit["status"] == "passed"
    assert audit["checked_witnesses"] == 1

    (tmp_path / "support_spans.jsonl").write_text(json.dumps({
        "evidence_id": "ev-seal",
        "source_url": url,
        "sha256": "c" * 64,
    }) + "\n", encoding="utf-8")
    failed = audit_known_support_directory(rubric, tmp_path)
    assert failed["status"] == "failed"
    assert "witness_support_span_mismatch" in failed["reason_codes"]


def test_frozen_cross_source_atom_requires_a_witness_for_each_required_role() -> None:
    atom = _atom()
    atom["evidence"]["acceptable_source_roles"] = ["forums", "wiki"]
    atom["evidence"]["required_source_roles"] = ["forums", "wiki"]
    with pytest.raises(RubricValidationError, match="required roles"):
        compile_query_rubric(
            _task(), [atom], status="frozen", reviewers=["r"],
            evidence_graph_stamp="graph-demo-v1", corpus_registry_hash="b" * 64,
        )
