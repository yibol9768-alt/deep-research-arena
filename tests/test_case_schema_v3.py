from __future__ import annotations

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from scripts.compile_case_v3 import (
    compile_case,
    main as compile_main,
    normalize_corpus_registry,
    validate_proof_support_bindings,
    validate_reachability,
)
from scripts.enumerate_cases_v3 import enumerate_validated_candidates
from src.eval.case_schema_v3 import (
    CaseSpec,
    CaseValidationError,
    RequiredProofStepV3,
    decidable_claims_sha256,
    proof_subgraph_fingerprint,
    validate_legacy_case,
    validate_proof_step_case,
)
from src.eval.evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceNode, SupportSpan
from src.tasks.query_renderer_v3 import build_blind_review_packet


H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64


def _source(
    evidence_id: str,
    url: str,
    digest: str,
    span_id: str,
    source_type: str = "concept",
) -> dict:
    return {
        "evidence_id": evidence_id,
        "node_type": "mechanism",
        "subject": evidence_id,
        "predicate": "supports",
        "object": True,
        "source_url": url,
        "source_type": source_type,
        "content_sha256": digest,
        "corpus_snapshot": "corpus-v3-test",
        "search_snippet_support": False,
        "body_support": True,
        "verifier": {
            "kind": "typed_claim",
            "matcher": "normalized_text",
            "accepted_phrases": [f"{evidence_id} supports the conclusion"],
            "accepted_aliases": [evidence_id],
            "normalizers": ["casefold", "whitespace"],
        },
        "support_spans": [
            {
                "support_span_id": span_id,
                "evidence_id": evidence_id,
                "source_url": url,
                "start": 0,
                "end": 8,
                "sha256": digest,
                "support_type": "body",
            }
        ],
        "frozen": True,
        "reachable": True,
    }


def valid_case_dict() -> dict:
    return {
        "task_id": "dra_v3_audio_0001",
        "task_version": 3,
        "case_schema": "evidence_graph_case_v1",
        "evidence_graph": "evidence_graph_v1",
        "observation_semantics": "observation_ledger_v1",
        "scoring_semantics": "verified_slots_v1",
        "headline_metrics": [
            "verified_research_completion_v1",
            "task_solve_rate_v1",
        ],
        "diagnostic_metric": "verified_f1_v1",
        "corpus_snapshot": "corpus-v3-test",
        "cluster_id": "audio_glasses_flight",
        "motif": "comparative_tradeoff",
        "difficulty": {
            "proof_depth": 3,
            "branching_factor": 2,
            "distractor_density": 0.2,
            "contradiction_count": 0,
        },
        "scenario": {
            "context": "A traveler wears glasses and has limited bag space.",
            "objective": "Choose the better form factor for the stated trip.",
            "constraints": ["wears_glasses", "small_bag"],
            "priority_order": ["noise_control", "comfort", "portability"],
            "candidate_actions": ["form_a", "form_b"],
            "constraint_labels": {
                "wears_glasses": "the traveler wears glasses",
                "small_bag": "the bag has little spare space",
            },
            "priority_labels": {
                "noise_control": "engine-noise control",
                "comfort": "long-duration comfort",
                "portability": "portability",
            },
            "candidate_labels": {"form_a": "Form A", "form_b": "Form B"},
        },
        "evidence_sources": [
            _source("ev_seal", "http://localhost:8080/seal", H1, "span_seal"),
            _source(
                "ev_noise",
                "http://localhost:8080/noise",
                H2,
                "span_noise",
                "forum",
            ),
        ],
        "slots": [
            {
                "slot_id": "E1",
                "type": "evidence",
                "required": True,
                "critical": True,
                "claim_id": "ev_seal",
                "verifier": "typed_claim",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "E2",
                "type": "evidence",
                "required": True,
                "critical": True,
                "claim_id": "ev_noise",
                "verifier": "typed_claim",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B1",
                "type": "bridge",
                "required": True,
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "seal_noise_bridge_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B2",
                "type": "bridge",
                "required": True,
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "experience_reconciliation_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B3",
                "type": "bridge",
                "required": True,
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "candidate_synthesis_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "D1",
                "type": "decision",
                "required": True,
                "critical": True,
                "requires": ["B1", "B2", "B3"],
                "rule": "lexicographic_priority_v1",
                "requirement_id": "Q2",
            },
        ],
        "rule_definitions": {
            "seal_noise_bridge_v1": {
                "type": "bridge",
                "matcher": "regex_fullmatch",
                "accepted_regexes": [
                    r"The seal evidence changes the expected noise-control result\."
                ],
                "normalizers": ["casefold", "whitespace"],
            },
            "experience_reconciliation_v1": {
                "type": "bridge",
                "matcher": "regex_fullmatch",
                "accepted_regexes": [
                    r"The concept evidence and experience evidence require reconciliation\."
                ],
                "normalizers": ["casefold", "whitespace"],
            },
            "candidate_synthesis_v1": {
                "type": "bridge",
                "matcher": "regex_fullmatch",
                "accepted_regexes": [
                    r"The reconciled evidence supports a candidate-level comparison\."
                ],
                "normalizers": ["casefold", "whitespace"],
            },
            "lexicographic_priority_v1": {
                "type": "decision",
                "decision_matcher": {
                    "matcher": "regex_fullmatch",
                    "accepted_regexes": [
                        r"Form A is the final conclusion under the stated priorities\."
                    ],
                    "normalizers": ["casefold", "whitespace"],
                },
                "conclusion_matchers": {
                    "form_a": {
                        "matcher": "regex_fullmatch",
                        "accepted_regexes": [
                            r"(?:Form A|choose Form A)(?: is the recommendation)?\."
                        ],
                    }
                },
            },
        },
        "decidable_claims": [
            {
                "claim_id": "wrong_form_b_priority_claim",
                "contradicts_slot_id": "D1",
                "critical": True,
                "rejected_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": [
                        "Form B is the final conclusion under the stated priorities."
                    ],
                    "normalizers": ["casefold", "whitespace"],
                },
            }
        ],
        "research_subgoals": [
            {
                "subgoal_id": "G1",
                "description": "Determine how seal evidence changes the noise-control comparison.",
                "critical": True,
                "requires": ["E1", "E2", "B1"],
                "local_conclusion_slot_id": "B1",
            },
            {
                "subgoal_id": "G2",
                "description": "Reconcile concept evidence with the reported user experience.",
                "critical": True,
                "requires": ["E1", "E2", "B2"],
                "local_conclusion_slot_id": "B2",
            },
            {
                "subgoal_id": "G3",
                "description": "Synthesize both evidence bridges into a candidate comparison.",
                "critical": True,
                "requires": ["E1", "E2", "B3"],
                "local_conclusion_slot_id": "B3",
            },
            {
                "subgoal_id": "G4",
                "description": "Apply the stated priorities to form the final recommendation.",
                "critical": True,
                "requires": ["E1", "E2", "B1", "B2", "B3", "D1"],
                "local_conclusion_slot_id": "D1",
            },
        ],
        "query_requirements": [
            {
                "requirement_id": "Q1",
                "text": "Explain how the two constraints affect the comparison.",
                "slot_ids": ["E1", "E2", "B1", "B2", "B3"],
                "subgoal_ids": ["G1", "G2", "G3"],
                "required": True,
            },
            {
                "requirement_id": "Q2",
                "text": "State one conclusion and justify it using the priority order.",
                "slot_ids": ["E1", "E2", "B1", "B2", "B3", "D1"],
                "subgoal_ids": ["G4"],
                "required": True,
            },
        ],
        "acceptable_conclusions": ["form_a"],
        "query_rendering": {
            "canonical_template": "decision_case_v1",
            "forbidden_leaks": [
                "slot_id",
                "source_url",
                "gold_product",
                "scorer_quota",
            ],
            "gold_terms": ["Private Winner ZX"],
        },
        "oracle": {
            "proof": ["E1", "E2", "B1", "B2", "B3", "D1"],
            "single_page_sufficient": False,
            "minimum_required_evidence_nodes": 2,
            "minimum_reasoning_depth": 2,
            "critical_node_ablation": {
                "E1": {"outcome": "decision_unresolved"},
                "E2": {"outcome": "decision_unresolved"},
            },
        },
    }


def proof_step_case_dict() -> dict:
    """Explicit new-protocol projection; legacy fixture remains replayable."""

    payload = valid_case_dict()
    payload["scoring_semantics"] = "proof_steps_v1"
    payload["headline_metrics"] = [
        "partial_completion_rate_v1",
        "full_pass_rate_v1",
    ]
    payload.pop("diagnostic_metric")
    payload["diagnostic_metrics"] = [
        "route_coverage_v1",
        "acquisition_diagnostics_v1",
    ]
    payload["motif"] = "constraint_match_and_select"
    scenario = payload.pop("scenario")
    payload["generator_view"] = {
        "scenario": scenario["context"],
        "constraints": scenario["constraints"],
        "candidate_actions": scenario["candidate_actions"],
        "target": scenario["objective"],
    }
    source_by_id = {
        source["evidence_id"]: source for source in payload["evidence_sources"]
    }
    steps = []
    for old in payload.pop("slots"):
        step = {
            "step_id": old["slot_id"],
            "type": old["type"],
            "required": old["required"],
            "vital": old["critical"],
            "requires": old.get("requires", []),
        }
        if "requirement_id" in old:
            step["requirement_id"] = old["requirement_id"]
        if old["type"] == "evidence":
            source = source_by_id[old["claim_id"]]
            step.update(
                {
                    "claim": old["claim_id"],
                    "verifier": old["verifier"],
                    "acceptable_support": {
                        "source_ids": [old["claim_id"]],
                        "source_roles": [source["source_type"]],
                        "support_mode": "body_or_exact_snippet",
                        "condition_match": True,
                    },
                    "provenance_contract": "discovered_then_observed",
                }
            )
        else:
            step["rule"] = old["rule"]
        steps.append(step)
    payload["evaluator_view"] = {
        "propositions": [
            step["claim"] for step in steps if step["type"] == "evidence"
        ],
        "required_proof_steps": steps,
        "final_answer_contract": {
            "unique_product_required": True,
            "must_address_constraints": True,
            "must_explain_tradeoffs": True,
            "must_depend_on_verified_steps": True,
        },
    }
    payload["query_rendering"] = {
        "few_shot_subset": "manual_dev14_examples3_v1",
        "forbidden_leaks": [
            "step_id",
            "source_url",
            "gold_answer",
            "required_step_count",
        ],
        "validation": ["hard_rules", "blind_semantic_alignment"],
        "max_generation_attempts": 3,
    }
    return payload


def passing_blind_review(payload: dict, *, attempt: int = 1) -> dict:
    case = CaseSpec.from_dict(payload)
    packet = build_blind_review_packet(case, attempt=attempt)
    return {
        "schema": "blind_semantic_alignment_review_v1",
        "task_id": case.task_id,
        "attempt": attempt,
        "max_generation_attempts": 3,
        "generator_view_sha256": packet["generator_view_sha256"],
        "query_sha256": packet["query_sha256"],
        "reviewer_id": "human-reviewer-01",
        "faithful": True,
        "natural": True,
        "closed_environment_answerable": True,
        "requires_multi_branch_research": True,
        "passed": True,
    }


def catalog_records() -> list[dict]:
    records = []
    for evidence_id, url, digest, source_type in (
        ("ev_seal", "http://localhost:8080/seal", H1, "concept"),
        ("ev_noise", "http://localhost:8080/noise", H2, "forum"),
    ):
        records.append(
            {
                "evidence_id": evidence_id,
                "node_type": "mechanism",
                "subject": evidence_id,
                "predicate": "supports",
                "object": True,
                "source_url": url,
                "source_type": source_type,
                "content_sha256": digest,
                "corpus_snapshot": "corpus-v3-test",
                "search_snippet_support": False,
                "body_support": True,
                "verifier": {
                    "kind": "typed_claim",
                    "matcher": "normalized_text",
                    "accepted_phrases": [f"{evidence_id} supports the conclusion"],
                    "accepted_aliases": [evidence_id],
                    "normalizers": ["casefold", "whitespace"],
                },
                "metadata": {},
            }
        )
    records.append(
        {
            "evidence_id": "seed_root",
            "node_type": "document",
            "subject": "task start page",
            "predicate": "supports",
            "object": True,
            "source_url": "http://localhost:8080/start",
            "source_type": "concept",
            "content_sha256": H3,
            "corpus_snapshot": "corpus-v3-test",
            "search_snippet_support": False,
            "body_support": True,
            "verifier": {"kind": "typed_claim", "tolerance": None},
            "metadata": {"task_seed": True},
        }
    )
    return records


def support_spans() -> list[dict]:
    return [
        {
            "support_span_id": "span_seal",
            "evidence_id": "ev_seal",
            "source_url": "http://localhost:8080/seal",
            "start": 0,
            "end": 8,
            "sha256": H1,
            "support_type": "body",
            "metadata": {},
        },
        {
            "support_span_id": "span_noise",
            "evidence_id": "ev_noise",
            "source_url": "http://localhost:8080/noise",
            "start": 0,
            "end": 8,
            "sha256": H2,
            "support_type": "body",
            "metadata": {},
        },
    ]


def corpus_registry() -> dict:
    # The third page has no case claim node.  It must still survive compilation
    # so a citation to it is real-but-unused rather than fabricated.
    return {
        "version": "frozen_corpus_registry_v1",
        "corpus_snapshot": "corpus-v3-test",
        "entries": [
            {
                "registry_id": "page_seal",
                "source_url": "http://localhost:8080/seal",
                "source_type": "concept",
                "content_sha256": H1,
                "corpus_snapshot": "corpus-v3-test",
                "in_corpus": True,
                "metadata": {},
            },
            {
                "registry_id": "page_noise",
                "source_url": "http://localhost:8080/noise",
                "source_type": "forum",
                "content_sha256": H2,
                "corpus_snapshot": "corpus-v3-test",
                "in_corpus": True,
                "metadata": {},
            },
            {
                "registry_id": "page_start",
                "source_url": "http://localhost:8080/start",
                "source_type": "concept",
                "content_sha256": H3,
                "corpus_snapshot": "corpus-v3-test",
                "in_corpus": True,
                "metadata": {},
            },
            {
                "registry_id": "page_unused",
                "source_url": "http://localhost:8080/real-but-unused",
                "source_type": "forum",
                "content_sha256": H4,
                "corpus_snapshot": "corpus-v3-test",
                "in_corpus": True,
                "metadata": {},
            },
        ],
    }


def graph_edges() -> list[dict]:
    # EvidenceGraph defines X DISCOVERABLE_FROM Y as a licensed Y -> X step.
    return [
        {
            "edge_id": "edge_start_seal",
            "relation": "DISCOVERABLE_FROM",
            "source_id": "ev_seal",
            "target_id": "seed_root",
            "discovery_method": "L",
            "discovery_order": 1,
            "metadata": {},
        },
        {
            "edge_id": "edge_seal_noise",
            "relation": "DISCOVERABLE_FROM",
            "source_id": "ev_noise",
            "target_id": "ev_seal",
            "discovery_method": "L",
            "discovery_order": 2,
            "metadata": {},
        },
    ]


def reachability_manifest() -> dict:
    graph = EvidenceGraph(
        corpus_snapshot="corpus-v3-test",
        nodes=tuple(EvidenceNode.from_dict(row) for row in catalog_records()),
        edges=tuple(EvidenceEdge.from_dict(row) for row in graph_edges()),
        support_spans=tuple(SupportSpan.from_dict(row) for row in support_spans()),
    )
    return {
        "schema": "case_reachability_manifest_v1",
        "complete": True,
        "corpus_snapshot": "corpus-v3-test",
        "evidence_graph_sha256": graph.graph_sha256,
        "root_node_ids": ["seed_root"],
    }


def test_valid_case_round_trip_and_version_stamps() -> None:
    case = CaseSpec.from_dict(valid_case_dict())
    assert case.minimum_reasoning_depth == 2
    assert case.validation_report()["minimum_required_evidence_nodes"] == 2
    assert CaseSpec.from_dict(case.to_dict()).to_dict() == case.to_dict()
    assert case.to_dict()["scoring_semantics"] == "verified_slots_v1"


def test_explicit_dual_view_protocol_and_legacy_replay_are_separate() -> None:
    legacy = validate_legacy_case(valid_case_dict())
    assert legacy.slots == legacy.evaluator_view.required_proof_steps

    proof_case = validate_proof_step_case(proof_step_case_dict())
    protocol = proof_case.protocol_dict()
    assert protocol["scoring_semantics"] == "proof_steps_v1"
    assert protocol["headline_metrics"] == [
        "partial_completion_rate_v1",
        "full_pass_rate_v1",
    ]
    assert protocol["diagnostic_metrics"] == [
        "route_coverage_v1",
        "acquisition_diagnostics_v1",
    ]
    assert "diagnostic_metric" not in protocol
    assert "generator_view" in protocol
    assert "evaluator_view" in protocol
    assert "scenario" not in protocol
    assert "slots" not in protocol
    assert protocol["evaluator_view"]["required_proof_steps"][0]["step_id"] == "E1"
    assert "slot_id" not in repr(protocol["evaluator_view"])
    assert CaseSpec.from_dict(protocol).protocol_dict() == protocol


def test_proposition_step_accepts_multiple_bound_equivalent_sources() -> None:
    payload = proof_step_case_dict()
    alternate = _source(
        "ev_seal_alt",
        "http://localhost:8080/seal-equivalent",
        H3,
        "span_seal_alt",
    )
    alternate["verifier"]["accepted_phrases"] = [
        "an equivalent page supports the seal proposition"
    ]
    payload["evidence_sources"].append(alternate)
    evaluator = payload["evaluator_view"]
    evaluator["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = next(
        step
        for step in evaluator["required_proof_steps"]
        if step["step_id"] == "E1"
    )
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["source_ids"] = [
        "ev_seal",
        "ev_seal_alt",
    ]
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"

    case = validate_proof_step_case(payload)

    assert case.slot_map["E1"].claim_id == "P_SEAL"
    assert case.slot_map["E1"].support_source_ids == (
        "ev_seal",
        "ev_seal_alt",
    )
    assert case.critical_support_source_ids == [
        "ev_noise",
        "ev_seal",
        "ev_seal_alt",
    ]
    assert case.validation_report()["critical_evidence_pages"] == [
        "http://localhost:8080/noise",
        "http://localhost:8080/seal",
        "http://localhost:8080/seal-equivalent",
    ]


def test_case_rejects_when_one_alternative_page_can_cover_every_vital_step() -> None:
    payload = proof_step_case_dict()
    shared_page = _source(
        "ev_seal_on_noise_page",
        "http://localhost:8080/noise",
        H3,
        "span_seal_on_noise_page",
    )
    payload["evidence_sources"].append(shared_page)
    e1 = next(
        step
        for step in payload["evaluator_view"]["required_proof_steps"]
        if step["step_id"] == "E1"
    )
    payload["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["source_ids"] = [
        "ev_seal",
        "ev_seal_on_noise_page",
    ]
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"

    with pytest.raises(ValidationError, match="single-page case rejected"):
        validate_proof_step_case(payload)


def _semantic_support_graph(
    *,
    support_source_id: str,
    relation: str = "SUPPORTED_BY",
    claim_condition: bool = False,
    source_condition: bool = False,
) -> EvidenceGraph:
    records = catalog_records()
    records.append(
        {
            "evidence_id": "P_SEAL",
            "node_type": "proposition",
            "subject": "seal performance",
            "predicate": "supports",
            "object": True,
            "source_url": "http://localhost:8080/proposition/seal",
            "source_type": "concept",
            "content_sha256": H4,
            "corpus_snapshot": "corpus-v3-test",
            "search_snippet_support": False,
            "body_support": True,
            "verifier": {"kind": "typed_claim", "tolerance": None},
            "metadata": {},
        }
    )
    if claim_condition or source_condition:
        records.append(
            {
                "evidence_id": "COND_LONG_USE",
                "node_type": "constraint",
                "subject": "long use",
                "predicate": "applies_under",
                "object": True,
                "source_url": "http://localhost:8080/condition/long-use",
                "source_type": "case_spec",
                "content_sha256": H4,
                "corpus_snapshot": "corpus-v3-test",
                "search_snippet_support": False,
                "body_support": True,
                "verifier": {"kind": "typed_claim", "tolerance": None},
                "metadata": {},
            }
        )
    edges = graph_edges()
    edges.append(
        {
            "edge_id": "edge_seal_semantic_support",
            "relation": relation,
            "source_id": "P_SEAL",
            "target_id": support_source_id,
            "metadata": {},
        }
    )
    if claim_condition:
        edges.append(
            {
                "edge_id": "edge_claim_long_use",
                "relation": "APPLIES_UNDER",
                "source_id": "P_SEAL",
                "target_id": "COND_LONG_USE",
                "metadata": {},
            }
        )
    if source_condition:
        edges.append(
            {
                "edge_id": "edge_source_long_use",
                "relation": "APPLIES_UNDER",
                "source_id": support_source_id,
                "target_id": "COND_LONG_USE",
                "metadata": {},
            }
        )
    return EvidenceGraph(
        corpus_snapshot="corpus-v3-test",
        nodes=tuple(EvidenceNode.from_dict(row) for row in records),
        edges=tuple(EvidenceEdge.from_dict(row) for row in edges),
        support_spans=tuple(
            SupportSpan.from_dict(row) for row in support_spans()
        ),
    )


def test_formal_semantic_binding_rejects_unrelated_listed_source() -> None:
    payload = proof_step_case_dict()
    payload["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = next(
        step
        for step in payload["evaluator_view"]["required_proof_steps"]
        if step["step_id"] == "E1"
    )
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"
    case = validate_proof_step_case(payload)

    validate_proof_support_bindings(
        case,
        _semantic_support_graph(support_source_id="ev_seal"),
    )
    with pytest.raises(CaseValidationError, match="must have exactly one"):
        validate_proof_support_bindings(
            case,
            _semantic_support_graph(support_source_id="ev_noise"),
        )

    wrong_relation = deepcopy(payload)
    wrong_relation["evaluator_view"]["required_proof_steps"][0][
        "acceptable_support"
    ]["support_relation"] = "ASSERTS"
    with pytest.raises(CaseValidationError, match="exactly one ASSERTS"):
        validate_proof_support_bindings(
            validate_proof_step_case(wrong_relation),
            _semantic_support_graph(support_source_id="ev_seal"),
        )


def test_formal_semantic_binding_requires_exact_condition_scope() -> None:
    payload = proof_step_case_dict()
    payload["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = payload["evaluator_view"]["required_proof_steps"][0]
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"
    case = validate_proof_step_case(payload)

    validate_proof_support_bindings(
        case,
        _semantic_support_graph(
            support_source_id="ev_seal",
            claim_condition=True,
            source_condition=True,
        ),
    )
    with pytest.raises(CaseValidationError, match="does not exactly match"):
        validate_proof_support_bindings(
            case,
            _semantic_support_graph(
                support_source_id="ev_seal",
                claim_condition=True,
                source_condition=False,
            ),
        )


def test_formal_reachability_covers_every_equivalent_support_source() -> None:
    payload = proof_step_case_dict()
    alternate = _source(
        "ev_seal_alt",
        "http://localhost:8080/seal-equivalent",
        H3,
        "span_seal_alt",
    )
    payload["evidence_sources"].append(alternate)
    payload["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = payload["evaluator_view"]["required_proof_steps"][0]
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["source_ids"] = ["ev_seal", "ev_seal_alt"]
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"
    case = validate_proof_step_case(payload)

    alternate_record = {
        key: value
        for key, value in alternate.items()
        if key not in {"support_spans", "frozen", "reachable"}
    }
    alternate_record["metadata"] = {}
    records = [
        *catalog_records(),
        alternate_record,
        {
            "evidence_id": "P_SEAL",
            "node_type": "proposition",
            "subject": "seal performance",
            "predicate": "supports",
            "object": True,
            "source_url": "http://localhost:8080/proposition/seal",
            "source_type": "concept",
            "content_sha256": H4,
            "corpus_snapshot": "corpus-v3-test",
            "search_snippet_support": False,
            "body_support": True,
            "verifier": {"kind": "typed_claim", "tolerance": None},
            "metadata": {},
        },
    ]
    spans = [*support_spans(), {**alternate["support_spans"][0], "metadata": {}}]
    edges = [
        *graph_edges(),
        {
            "edge_id": "edge_prop_seal",
            "relation": "SUPPORTED_BY",
            "source_id": "P_SEAL",
            "target_id": "ev_seal",
            "metadata": {},
        },
        {
            "edge_id": "edge_prop_seal_alt",
            "relation": "SUPPORTED_BY",
            "source_id": "P_SEAL",
            "target_id": "ev_seal_alt",
            "metadata": {},
        },
        {
            "edge_id": "edge_discover_seal_alt",
            "relation": "DISCOVERABLE_FROM",
            "source_id": "ev_seal_alt",
            "target_id": "ev_seal",
            "discovery_method": "L",
            "discovery_order": 3,
            "metadata": {},
        },
    ]

    def manifest_for(edge_rows: list[dict]) -> dict:
        graph = EvidenceGraph(
            corpus_snapshot="corpus-v3-test",
            nodes=tuple(EvidenceNode.from_dict(row) for row in records),
            edges=tuple(EvidenceEdge.from_dict(row) for row in edge_rows),
            support_spans=tuple(SupportSpan.from_dict(row) for row in spans),
        )
        return {
            "schema": "case_reachability_manifest_v1",
            "complete": True,
            "corpus_snapshot": "corpus-v3-test",
            "evidence_graph_sha256": graph.graph_sha256,
            "root_node_ids": ["seed_root"],
        }

    reached = validate_reachability(
        case,
        catalog_records=records,
        graph_edges=edges,
        support_span_records=spans,
        manifest=manifest_for(edges),
    )
    assert reached["critical_evidence_node_ids"] == [
        "ev_noise",
        "ev_seal",
        "ev_seal_alt",
    ]

    unreachable_edges = [
        edge
        for edge in edges
        if edge["edge_id"] != "edge_discover_seal_alt"
    ]
    with pytest.raises(CaseValidationError, match="reachability failed"):
        validate_reachability(
            case,
            catalog_records=records,
            graph_edges=unreachable_edges,
            support_span_records=spans,
            manifest=manifest_for(unreachable_edges),
        )


def test_required_non_vital_step_is_valid_but_vital_optional_is_not() -> None:
    step = RequiredProofStepV3.model_validate(
        {
            "step_id": "E_optional_full_gate",
            "type": "evidence",
            "required": True,
            "vital": False,
            "claim": "P_DIAGNOSTIC",
            "verifier": "typed_claim",
            "acceptable_support": {
                "source_ids": ["P_DIAGNOSTIC"],
                "source_roles": ["concept"],
                "support_mode": "body",
                "condition_match": True,
            },
            "provenance_contract": "discovered_then_observed",
        }
    )
    assert step.required is True
    assert step.vital is False

    with pytest.raises(ValidationError, match="vital proof step"):
        RequiredProofStepV3.model_validate(
            {
                **step.model_dump(mode="json", by_alias=True),
                "required": False,
                "vital": True,
            }
        )


@pytest.mark.parametrize(
    "motif",
    [
        "constraint_match_and_select",
        "claim_verification",
        "evidence_reconciliation",
        "causal_or_evolution_explanation",
        "multi_branch_synthesis",
    ],
)
def test_five_graph_native_motifs_are_accepted(motif: str) -> None:
    payload = proof_step_case_dict()
    payload["motif"] = motif
    assert CaseSpec.from_dict(payload).motif == motif


def test_concept_role_accepts_wikipedia_implementation_alias() -> None:
    payload = proof_step_case_dict()
    payload["evidence_sources"][0]["source_type"] = "wikipedia"

    case = validate_proof_step_case(payload)

    assert case.evidence_source_map["ev_seal"].source_type == "wikipedia"


@pytest.mark.parametrize(
    "old_motif",
    [
        "constraint_filter",
        "mechanism_application",
        "claim_reconciliation",
        "comparative_tradeoff",
        "counterexample_revision",
    ],
)
def test_retired_semantic_motifs_are_rejected(old_motif: str) -> None:
    payload = proof_step_case_dict()
    payload["motif"] = old_motif
    with pytest.raises(ValidationError, match="motif"):
        CaseSpec.from_dict(payload)


def test_proof_step_semantics_reject_legacy_shape_and_missing_views() -> None:
    legacy_shape = valid_case_dict()
    legacy_shape["scoring_semantics"] = "proof_steps_v1"
    with pytest.raises(ValidationError, match="legacy top-level scenario"):
        CaseSpec.from_dict(legacy_shape)

    missing_generator = proof_step_case_dict()
    missing_generator.pop("generator_view")
    with pytest.raises(ValidationError, match="explicit generator_view"):
        CaseSpec.from_dict(missing_generator)

    missing_evaluator = proof_step_case_dict()
    missing_evaluator.pop("evaluator_view")
    with pytest.raises(ValidationError, match="required_proof_steps"):
        CaseSpec.from_dict(missing_evaluator)


@pytest.mark.parametrize(
    "leak",
    [
        "Use http://localhost:8080/seal.",
        "Complete evaluator step E1.",
        "Use proposition ev_seal.",
        "The answer condition is secret_noise_branch.",
    ],
)
def test_generator_view_rejects_private_url_step_and_answer_material(leak: str) -> None:
    payload = proof_step_case_dict()
    if "secret_noise_branch" in leak:
        payload["acceptable_conclusions"] = [
            {
                "answer": "form_a",
                "when": "secret_noise_branch",
                "required_tradeoffs": ["bulk"],
            },
            {
                "answer": "form_b",
                "when": "other_branch",
                "required_tradeoffs": ["fit"],
            },
        ]
        payload["evaluator_view"]["final_answer_contract"][
            "unique_product_required"
        ] = False
    payload["generator_view"]["target"] = leak
    with pytest.raises(ValidationError, match="GeneratorView"):
        CaseSpec.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_version", 2),
        ("case_schema", "legacy"),
        ("evidence_graph", "unknown"),
        ("observation_semantics", "unknown"),
        ("scoring_semantics", "quality_v2"),
    ],
)
def test_wrong_version_stamps_rejected(field: str, value: object) -> None:
    payload = valid_case_dict()
    payload[field] = value
    with pytest.raises(ValidationError):
        CaseSpec.from_dict(payload)


def test_cycle_is_rejected_as_invalid_dag() -> None:
    payload = valid_case_dict()
    payload["slots"][2]["requires"] = ["B2"]
    payload["slots"][3]["requires"] = ["B1"]
    with pytest.raises(ValidationError, match="cycle"):
        CaseSpec.from_dict(payload)


def test_single_page_and_one_critical_evidence_are_rejected() -> None:
    same_page = valid_case_dict()
    same_page["evidence_sources"][1]["source_url"] = same_page["evidence_sources"][0][
        "source_url"
    ]
    same_page["evidence_sources"][1]["support_spans"][0]["source_url"] = same_page[
        "evidence_sources"
    ][0]["source_url"]
    with pytest.raises(ValidationError, match="single-page"):
        CaseSpec.from_dict(same_page)

    one_critical = valid_case_dict()
    one_critical["slots"][1]["critical"] = False
    one_critical["slots"][1]["required"] = False
    one_critical["slots"][1].pop("requirement_id")
    one_critical["slots"][2]["requires"] = ["E1"]
    one_critical["slots"][3]["requires"] = ["E1"]
    one_critical["slots"][4]["requires"] = ["E1"]
    one_critical["query_requirements"][0]["slot_ids"] = ["E1", "B1", "B2", "B3"]
    one_critical["query_requirements"][1]["slot_ids"] = [
        "E1",
        "B1",
        "B2",
        "B3",
        "D1",
    ]
    for subgoal in one_critical["research_subgoals"]:
        subgoal["requires"].remove("E2")
    one_critical["oracle"]["proof"] = ["E1", "B1", "B2", "B3", "D1"]
    del one_critical["oracle"]["minimum_required_evidence_nodes"]
    one_critical["oracle"]["critical_node_ablation"] = {
        "E1": {"outcome": "decision_unresolved"}
    }
    with pytest.raises(ValidationError, match="at least two critical evidence"):
        CaseSpec.from_dict(one_critical)


def test_conditional_admissible_alternatives_are_explicit() -> None:
    payload = valid_case_dict()
    payload["acceptable_conclusions"] = [
        {
            "answer": "form_a",
            "when": "noise_control_remains_first",
            "required_tradeoffs": ["bulk"],
        },
        {
            "answer": "form_b",
            "when": "portability_becomes_hard_constraint",
            "required_tradeoffs": ["fit_risk"],
        },
    ]
    payload["rule_definitions"]["lexicographic_priority_v1"] = {
        "type": "decision",
        "decision_matcher": {
            "matcher": "normalized_text",
            "accepted_phrases": ["Choose Form A or Form B under an admissible branch."]
        },
        "conclusion_matchers": {
            "form_a": {
                "matcher": "normalized_text",
                "accepted_phrases": ["Form A"],
            },
            "form_b": {
                "matcher": "normalized_text",
                "accepted_phrases": ["Form B"],
            },
        },
        "admissible_conditions": [
            {
                "answer": "form_a",
                "when": "noise_control_remains_first",
                "condition_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["noise control remains first"]
                },
                "tradeoff_matchers": {
                    "bulk": {
                        "matcher": "normalized_text",
                        "accepted_phrases": ["Form A is bulkier"],
                    }
                },
            },
            {
                "answer": "form_b",
                "when": "portability_becomes_hard_constraint",
                "condition_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": ["portability is a hard constraint"]
                },
                "tradeoff_matchers": {
                    "fit_risk": {
                        "matcher": "normalized_text",
                        "accepted_phrases": ["Form B has fit risk"],
                    }
                },
            },
        ],
    }
    case = CaseSpec.from_dict(payload)
    assert {item.answer for item in case.acceptable_conclusions} == {"form_a", "form_b"}

    payload["acceptable_conclusions"] = ["form_a", "form_b"]
    with pytest.raises(ValidationError, match="explicit conditional"):
        CaseSpec.from_dict(payload)


def test_query_slot_mapping_and_semantic_ablation_are_required() -> None:
    missing_mapping = valid_case_dict()
    missing_mapping["query_requirements"][0]["slot_ids"].remove("E2")
    missing_mapping["query_requirements"][1]["slot_ids"].remove("E2")
    with pytest.raises(ValidationError, match="without all of its slots"):
        CaseSpec.from_dict(missing_mapping)

    missing_ablation = valid_case_dict()
    del missing_ablation["oracle"]["critical_node_ablation"]["E2"]
    with pytest.raises(ValidationError, match="critical_node_ablation"):
        CaseSpec.from_dict(missing_ablation)

    unchanged = valid_case_dict()
    unchanged["oracle"]["critical_node_ablation"]["E1"] = {
        "outcome": "admissible_set_changed",
        "admissible_set_before": ["form_a"],
        "admissible_set_after": ["form_a"],
    }
    with pytest.raises(ValidationError, match="must change"):
        CaseSpec.from_dict(unchanged)


def test_bridge_and_decision_rules_require_typed_positive_matchers() -> None:
    missing = valid_case_dict()
    del missing["rule_definitions"]["seal_noise_bridge_v1"]
    with pytest.raises(ValidationError, match="undefined rules"):
        CaseSpec.from_dict(missing)

    wrong_type = valid_case_dict()
    wrong_type["rule_definitions"]["seal_noise_bridge_v1"] = {
        "type": "decision",
        "decision_matcher": {
            "matcher": "normalized_text",
            "accepted_phrases": ["a decision"],
        },
        "conclusion_matchers": {
            "form_a": {
                "matcher": "normalized_text",
                "accepted_phrases": ["Form A"],
            }
        },
    }
    with pytest.raises(ValidationError, match="references decision rule"):
        CaseSpec.from_dict(wrong_type)

    no_positive = valid_case_dict()
    no_positive["evidence_sources"][0]["verifier"] = {
        "kind": "typed_claim",
        "matcher": "normalized_text",
    }
    with pytest.raises(ValidationError, match="positive phrases or regexes"):
        CaseSpec.from_dict(no_positive)


def test_deep_research_subgoal_and_cross_source_gates() -> None:
    too_narrow = valid_case_dict()
    too_narrow["research_subgoals"] = too_narrow["research_subgoals"][:3]
    with pytest.raises(ValidationError, match="at least 4 items"):
        CaseSpec.from_dict(too_narrow)

    fact_leaf = valid_case_dict()
    fact_leaf["research_subgoals"][0]["requires"] = ["E1", "E2"]
    with pytest.raises(ValidationError, match="fact leaf"):
        CaseSpec.from_dict(fact_leaf)

    bad_local_conclusion = valid_case_dict()
    bad_local_conclusion["research_subgoals"][0]["local_conclusion_slot_id"] = "E1"
    with pytest.raises(ValidationError, match="bridge or decision"):
        CaseSpec.from_dict(bad_local_conclusion)

    duplicate_local_conclusion = valid_case_dict()
    duplicate_local_conclusion["research_subgoals"][1][
        "local_conclusion_slot_id"
    ] = "B1"
    duplicate_local_conclusion["research_subgoals"][1]["requires"] = [
        "E1",
        "E2",
        "B1",
    ]
    with pytest.raises(ValidationError, match="local conclusion slots"):
        CaseSpec.from_dict(duplicate_local_conclusion)

    one_source_role = valid_case_dict()
    one_source_role["evidence_sources"][1]["source_type"] = "concept"
    with pytest.raises(ValidationError, match="cross-source bridges"):
        CaseSpec.from_dict(one_source_role)

    same_family_aliases = valid_case_dict()
    same_family_aliases["evidence_sources"][0]["source_type"] = "concept"
    same_family_aliases["evidence_sources"][1]["source_type"] = "wikipedia"
    with pytest.raises(ValidationError, match="cross-source bridges"):
        CaseSpec.from_dict(same_family_aliases)

    discovery_only = valid_case_dict()
    discovery_only["evidence_sources"][1]["source_type"] = "search_result"
    with pytest.raises(ValidationError, match="discovery-only"):
        CaseSpec.from_dict(discovery_only)

    missing_subgoal_mapping = valid_case_dict()
    missing_subgoal_mapping["query_requirements"][0]["subgoal_ids"].remove("G3")
    with pytest.raises(ValidationError, match="no query requirement mapping"):
        CaseSpec.from_dict(missing_subgoal_mapping)


def test_dual_headline_and_diagnostic_metric_stamps_are_exact() -> None:
    wrong_order = valid_case_dict()
    wrong_order["headline_metrics"].reverse()
    with pytest.raises(ValidationError, match="headline_metrics"):
        CaseSpec.from_dict(wrong_order)

    legacy = valid_case_dict()
    legacy.pop("headline_metrics")
    legacy.pop("diagnostic_metric")
    legacy["headline_metric"] = "task_solve_rate_v1"
    legacy["partial_metric"] = "verified_f1_v1"
    with pytest.raises(ValidationError):
        CaseSpec.from_dict(legacy)


def test_unknown_or_unfrozen_evidence_is_rejected() -> None:
    unknown = valid_case_dict()
    unknown["slots"][0]["claim_id"] = "invented_claim"
    with pytest.raises(ValidationError, match="unknown/fabricated"):
        CaseSpec.from_dict(unknown)

    not_frozen = valid_case_dict()
    not_frozen["evidence_sources"][0]["frozen"] = False
    with pytest.raises(ValidationError):
        CaseSpec.from_dict(not_frozen)


def test_decidable_negatives_and_optional_diagnostics_are_strict() -> None:
    unbound = valid_case_dict()
    unbound["decidable_claims"][0]["contradicts_slot_id"] = "missing_slot"
    with pytest.raises(ValidationError, match="not bound to a known slot"):
        CaseSpec.from_dict(unbound)

    wrong_criticality = valid_case_dict()
    wrong_criticality["decidable_claims"][0]["critical"] = False
    with pytest.raises(ValidationError, match="critical flag disagrees"):
        CaseSpec.from_dict(wrong_criticality)

    missing_matcher_mode = valid_case_dict()
    missing_matcher_mode["decidable_claims"][0]["rejected_matcher"].pop("matcher")
    with pytest.raises(ValidationError):
        CaseSpec.from_dict(missing_matcher_mode)

    optional = valid_case_dict()
    optional["evidence_sources"].append(
        _source(
            "ev_optional",
            "http://localhost:8080/optional",
            H3,
            "span_optional",
        )
    )
    optional["slots"].append(
        {
            "slot_id": "E_optional",
            "type": "evidence",
            "required": False,
            "critical": False,
            "claim_id": "ev_optional",
            "verifier": "typed_claim",
        }
    )
    assert CaseSpec.from_dict(optional).slot_map["E_optional"].required is False

    inconsistent = deepcopy(optional)
    inconsistent["slots"][-1]["required"] = True
    with pytest.raises(ValidationError, match="required == critical"):
        CaseSpec.from_dict(inconsistent)


def test_formal_compile_requires_catalog_match_and_complete_registry() -> None:
    case_gold, task = compile_case(
        valid_case_dict(),
        catalog_records=catalog_records(),
        corpus_registry=corpus_registry(),
        support_span_records=support_spans(),
        graph_edges=graph_edges(),
        reachability_manifest=reachability_manifest(),
    )
    assert task["task_id"] == case_gold["task_id"]
    assert "http://localhost:8080/real-but-unused" in case_gold[
        "corpus_registry_urls"
    ]
    assert case_gold["corpus_registry_hash"] == case_gold["formal_bindings"][
        "corpus_registry_sha256"
    ]
    assert case_gold["discovery_root_urls"] == ["http://localhost:8080/start"]
    assert case_gold["formal_bindings"]["formal"] is True
    assert case_gold["formal_bindings"]["root_node_ids"] == ["seed_root"]
    assert case_gold["formal_bindings"]["decidable_claims_sha256"] == (
        decidable_claims_sha256(CaseSpec.from_dict(case_gold))
    )
    assert case_gold["formal_bindings"]["proof_subgraph_sha256"] == (
        proof_subgraph_fingerprint(CaseSpec.from_dict(case_gold))
    )
    assert "corpus_registry_urls" not in task
    assert "formal_bindings" not in task
    assert "evidence_sources" not in task

    mutated_negative = deepcopy(case_gold)
    mutated_negative["decidable_claims"][0]["rejected_matcher"][
        "accepted_phrases"
    ] = ["A post-compile mutation"]
    with pytest.raises(ValidationError, match="decidable_claims_sha256"):
        CaseSpec.from_dict(mutated_negative)

    mismatch = catalog_records()
    mismatch[0]["content_sha256"] = "f" * 64
    with pytest.raises(CaseValidationError, match="catalog mismatch"):
        compile_case(
            valid_case_dict(),
            catalog_records=mismatch,
            corpus_registry=corpus_registry(),
            support_span_records=support_spans(),
            graph_edges=graph_edges(),
            reachability_manifest=reachability_manifest(),
        )

    with pytest.raises(CaseValidationError, match="complete"):
        normalize_corpus_registry(
            {
                "corpus_snapshot": "corpus-v3-test",
                "corpus_urls": ["http://localhost:8080/seal"],
            },
            expected_snapshot="corpus-v3-test",
        )

    critical_root = reachability_manifest()
    critical_root["root_node_ids"] = ["ev_seal"]
    with pytest.raises(CaseValidationError, match="critical evidence cannot"):
        compile_case(
            valid_case_dict(),
            catalog_records=catalog_records(),
            corpus_registry=corpus_registry(),
            support_span_records=support_spans(),
            graph_edges=graph_edges(),
            reachability_manifest=critical_root,
        )


def test_new_formal_compile_emits_only_dual_view_and_requires_blind_review() -> None:
    payload = proof_step_case_dict()
    common = {
        "catalog_records": catalog_records(),
        "corpus_registry": corpus_registry(),
        "support_span_records": support_spans(),
        "graph_edges": graph_edges(),
        "reachability_manifest": reachability_manifest(),
    }
    with pytest.raises(CaseValidationError, match="manual blind-review"):
        compile_case(payload, require_query_acceptance=True, **common)

    case_gold, task = compile_case(
        payload,
        blind_review_record=passing_blind_review(payload),
        require_query_acceptance=True,
        **common,
    )
    assert "generator_view" in case_gold
    assert "evaluator_view" in case_gold
    assert "scenario" not in case_gold
    assert "slots" not in case_gold
    steps = case_gold["evaluator_view"]["required_proof_steps"]
    assert steps[0]["step_id"] == "E1"
    assert "slot_id" not in repr(steps)
    assert task["query_validation"]["disposition"] == "accepted"
    assert "evaluator_view" not in task


def test_enumerator_hash_is_order_stable_and_shared_proof_requires_one_cluster() -> None:
    first = valid_case_dict()
    second = deepcopy(first)
    second["task_id"] = "dra_v3_audio_0002"

    common = {
        "catalog_records": catalog_records(),
        "corpus_registry": corpus_registry(),
        "support_span_records": support_spans(),
        "graph_edges": graph_edges(),
        "reachability_manifest": reachability_manifest(),
    }
    forward = enumerate_validated_candidates([first, second], **common)
    reverse = enumerate_validated_candidates([second, first], **common)
    assert forward.to_dict()["task_set_sha256"] == reverse.to_dict()["task_set_sha256"]
    assert forward.to_dict()["directly_scorable_gold"] is False
    assert len(forward.cases) == 2

    second["cluster_id"] = "incorrect_independent_cluster"
    conflict = enumerate_validated_candidates([first, second], **common)
    assert conflict.cases == ()
    assert len(conflict.rejections) == 2
    assert all("shared critical proof subgraph" in row.error for row in conflict.rejections)


def test_proof_fingerprint_ignores_slot_ids_and_public_paraphrase() -> None:
    original = valid_case_dict()
    renamed = deepcopy(original)
    renamed["scenario"]["context"] = "Paraphrased public scenario text."
    renamed["query_requirements"][0]["text"] = "Paraphrased deliverable text."
    id_map = {
        "E1": "EvidenceA",
        "E2": "EvidenceB",
        "B1": "BridgeA",
        "B2": "BridgeB",
        "B3": "BridgeC",
        "D1": "DecisionA",
    }
    for slot in renamed["slots"]:
        slot["slot_id"] = id_map[slot["slot_id"]]
        slot["requires"] = [id_map[value] for value in slot.get("requires", [])]
    for requirement in renamed["query_requirements"]:
        requirement["slot_ids"] = [id_map[value] for value in requirement["slot_ids"]]
    for subgoal in renamed["research_subgoals"]:
        subgoal["requires"] = [id_map[value] for value in subgoal["requires"]]
        subgoal["local_conclusion_slot_id"] = id_map[
            subgoal["local_conclusion_slot_id"]
        ]
    renamed["decidable_claims"][0]["contradicts_slot_id"] = "DecisionA"
    renamed["oracle"]["proof"] = [id_map[value] for value in renamed["oracle"]["proof"]]
    renamed["oracle"]["critical_node_ablation"] = {
        id_map[key]: value
        for key, value in renamed["oracle"]["critical_node_ablation"].items()
    }

    assert proof_subgraph_fingerprint(original) == proof_subgraph_fingerprint(renamed)


def test_proof_fingerprint_is_order_stable_but_binds_alternative_sources() -> None:
    payload = proof_step_case_dict()
    payload["evidence_sources"].append(
        _source(
            "ev_seal_alt",
            "http://localhost:8080/seal-equivalent",
            H3,
            "span_seal_alt",
        )
    )
    payload["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = payload["evaluator_view"]["required_proof_steps"][0]
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["source_ids"] = ["ev_seal", "ev_seal_alt"]
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"

    original = validate_proof_step_case(payload)
    reordered_payload = deepcopy(payload)
    reordered_payload["evaluator_view"]["required_proof_steps"][0][
        "acceptable_support"
    ]["source_ids"].reverse()
    reordered = validate_proof_step_case(reordered_payload)
    fewer_payload = deepcopy(payload)
    fewer_payload["evidence_sources"] = [
        source
        for source in fewer_payload["evidence_sources"]
        if source["evidence_id"] != "ev_seal_alt"
    ]
    fewer_payload["evaluator_view"]["required_proof_steps"][0][
        "acceptable_support"
    ]["source_ids"] = ["ev_seal"]
    fewer = validate_proof_step_case(fewer_payload)

    assert proof_subgraph_fingerprint(original) == proof_subgraph_fingerprint(
        reordered
    )
    assert proof_subgraph_fingerprint(original) != proof_subgraph_fingerprint(
        fewer
    )


def test_graph_directory_cli_prefers_full_registry_over_graph_manifest(tmp_path) -> None:
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    for name, rows in (
        ("nodes.jsonl", catalog_records()),
        ("edges.jsonl", graph_edges()),
        ("support_spans.jsonl", support_spans()),
    ):
        (graph_dir / name).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    # This file intentionally is not a corpus registry.  The CLI must select
    # corpus_registry.json first when both coexist in a real graph directory.
    (graph_dir / "manifest.json").write_text(
        json.dumps({"version": "evidence_graph_manifest_v1"}), encoding="utf-8"
    )
    (graph_dir / "corpus_registry.json").write_text(
        json.dumps(corpus_registry()), encoding="utf-8"
    )
    draft = tmp_path / "draft.json"
    reachability = tmp_path / "reachability.json"
    case_out = tmp_path / "case.json"
    task_out = tmp_path / "task.json"
    draft.write_text(json.dumps(valid_case_dict()), encoding="utf-8")
    reachability.write_text(json.dumps(reachability_manifest()), encoding="utf-8")

    assert compile_main(
        [
            str(draft),
            "--evidence-catalog",
            str(graph_dir),
            "--reachability-manifest",
            str(reachability),
            "--case-out",
            str(case_out),
            "--task-out",
            str(task_out),
        ]
    ) == 0
    compiled = json.loads(case_out.read_text(encoding="utf-8"))
    assert compiled["formal_bindings"]["formal"] is True
    assert "http://localhost:8080/real-but-unused" in compiled[
        "corpus_registry_urls"
    ]
