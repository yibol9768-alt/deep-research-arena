from __future__ import annotations

from dataclasses import replace

import pytest

from src.eval.case_discovery_v3 import (
    AnchorKind,
    CandidateMetrics,
    CandidateSubgraph,
    EligibilityResult,
    GraphAnchor,
    GraphMotif,
)
from src.eval.evidence_graph import (
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SourceType,
)
from src.eval.motif_compiler_v3 import (
    MotifCompilationError,
    compile_motif_views,
    validate_motif_topology,
)


SNAPSHOT = "corpus-v3-motif-test"
GENERATOR_VIEW = {
    "scenario": "Compare two options under a constrained research scenario.",
    "constraints": ["budget_limit", "long_use"],
    "candidate_actions": ["option_a", "option_b"],
    "target": "Explain the evidence and give a constraint-consistent conclusion.",
}


def _node(
    node_id: str,
    node_type: NodeType,
    source_type: SourceType = SourceType.CONCEPT,
    *,
    metadata: dict[str, object] | None = None,
) -> EvidenceNode:
    return EvidenceNode(
        evidence_id=node_id,
        node_type=node_type,
        subject=node_id,
        predicate="supports",
        object=f"value:{node_id}",
        source_url=f"http://localhost:8000/{node_id}",
        source_type=source_type,
        content_sha256="2" * 64,
        corpus_snapshot=SNAPSHOT,
        metadata=metadata or {},
    )


def _parts_for_motif(
    motif: GraphMotif,
) -> tuple[EvidenceGraph, CandidateSubgraph]:
    evidence_one_type = NodeType.ATTRIBUTE
    evidence_two_type = NodeType.ATTRIBUTE
    bridge_type = NodeType.BRIDGE
    nodes = [
        _node("ev_one", evidence_one_type, SourceType.MAGENTO),
        _node("ev_two", evidence_two_type, SourceType.POSTMILL),
        _node("bridge", bridge_type, metadata={"rule_id": "bridge_rule_v1"}),
        _node(
            "decision",
            NodeType.DECISION,
            SourceType.CASE_SPEC,
            metadata={"rule_id": "decision_rule_v1"},
        ),
    ]
    edges = [
        EvidenceEdge("req_bridge_ev", EdgeRelation.REQUIRES, "bridge", "ev_one"),
        EvidenceEdge("req_decision_bridge", EdgeRelation.REQUIRES, "decision", "bridge"),
        EvidenceEdge("req_decision_ev", EdgeRelation.REQUIRES, "decision", "ev_two"),
    ]

    if motif is GraphMotif.CONSTRAINT_MATCH_AND_SELECT:
        nodes.extend(
            [
                _node("option_a", NodeType.ENTITY, SourceType.MAGENTO),
                _node("option_b", NodeType.ENTITY, SourceType.MAGENTO),
                _node("constraint", NodeType.CONSTRAINT, SourceType.CASE_SPEC),
            ]
        )
        edges.extend(
            [
                EvidenceEdge("attr_a", EdgeRelation.HAS_ATTRIBUTE, "option_a", "ev_one"),
                EvidenceEdge("attr_b", EdgeRelation.HAS_ATTRIBUTE, "option_b", "ev_two"),
                EvidenceEdge("satisfies_a", EdgeRelation.SATISFIES, "option_a", "constraint"),
                EvidenceEdge("scope_bridge", EdgeRelation.APPLIES_UNDER, "bridge", "constraint"),
            ]
        )
    elif motif is GraphMotif.CLAIM_VERIFICATION:
        nodes[0] = _node("ev_one", NodeType.ASSERTION, SourceType.WIKIPEDIA)
        nodes[1] = _node("ev_two", NodeType.ASSERTION, SourceType.POSTMILL)
        nodes.append(_node("proposition", NodeType.PROPOSITION, SourceType.CONCEPT))
        edges.extend(
            [
                EvidenceEdge("asserts_claim", EdgeRelation.ASSERTS, "ev_one", "proposition"),
                EvidenceEdge("refutes_claim", EdgeRelation.REFUTES, "ev_two", "proposition"),
            ]
        )
    elif motif is GraphMotif.EVIDENCE_RECONCILIATION:
        nodes.extend(
            [
                _node(
                    "conflict",
                    NodeType.CONTRADICTION,
                    SourceType.CASE_SPEC,
                    metadata={"rule_id": "conflict_scope_rule_v1"},
                ),
                _node("scope", NodeType.CONSTRAINT, SourceType.CASE_SPEC),
            ]
        )
        edges.extend(
            [
                EvidenceEdge("contradicts", EdgeRelation.CONTRADICTS, "ev_one", "ev_two"),
                EvidenceEdge("scope_condition", EdgeRelation.APPLIES_UNDER, "bridge", "scope"),
                EvidenceEdge("conflict_requires", EdgeRelation.REQUIRES, "conflict", "ev_one"),
                EvidenceEdge("decision_conflict", EdgeRelation.REQUIRES, "decision", "conflict"),
            ]
        )
    elif motif is GraphMotif.CAUSAL_OR_EVOLUTION_EXPLANATION:
        nodes[2] = _node(
            "bridge",
            NodeType.MECHANISM,
            SourceType.WIKIPEDIA,
            metadata={"rule_id": "mechanism_rule_v1"},
        )

    graph = EvidenceGraph(SNAPSHOT, tuple(nodes), tuple(edges), ())
    eligibility = EligibilityResult(
        connected=True,
        solvable=True,
        multi_option=True,
        multi_source_role=True,
        decision_relevant=True,
        single_page_sufficient=False,
        critical_node_ablation_pass=True,
    )
    candidate = CandidateSubgraph(
        candidate_id=f"candidate_{motif.value}",
        anchor=GraphAnchor("anchor_test", AnchorKind.MULTI_OPTION_DECISION, ("decision",), ()),
        node_ids=tuple(sorted(node.evidence_id for node in nodes)),
        edge_ids=tuple(sorted(edge.edge_id for edge in edges)),
        critical_node_ids=("ev_one", "ev_two"),
        conclusion_node_ids=("decision",),
        source_roles=("community", "product"),
        topic_cluster="test",
        graph_motif=motif,
        eligibility=eligibility,
        metrics=CandidateMetrics(2, 2, 0, 1, 1.0),
    )
    return graph, candidate


@pytest.mark.parametrize("motif", list(GraphMotif))
def test_all_five_graph_native_motifs_compile_positive(motif: GraphMotif) -> None:
    graph, candidate = _parts_for_motif(motif)

    checks = validate_motif_topology(graph, candidate)
    compiled = compile_motif_views(graph, candidate, generator_view=GENERATOR_VIEW)

    assert all(checks.values())
    assert compiled.graph_motif is motif
    assert compiled.generator_view == GENERATOR_VIEW
    assert "required_proof_steps" not in compiled.generator_view
    assert len(compiled.evaluator_view["required_proof_steps"]) >= 4
    assert compiled.evaluator_view["final_answer_contract"] == {
        "unique_product_required": False,
        "must_address_constraints": True,
        "must_explain_tradeoffs": True,
        "must_depend_on_verified_steps": True,
    }
    assert len(compiled.compilation_sha256) == 64
    assert compiled.to_dict()["directly_scorable_gold"] is False


@pytest.mark.parametrize(
    ("motif", "edge_to_remove"),
    [
        (GraphMotif.CONSTRAINT_MATCH_AND_SELECT, "satisfies_a"),
        (GraphMotif.CLAIM_VERIFICATION, "refutes_claim"),
        (GraphMotif.EVIDENCE_RECONCILIATION, "scope_condition"),
        (GraphMotif.CAUSAL_OR_EVOLUTION_EXPLANATION, "req_bridge_ev"),
        (GraphMotif.MULTI_BRANCH_SYNTHESIS, "req_decision_ev"),
    ],
)
def test_all_five_graph_native_motifs_fail_when_topology_is_cut(
    motif: GraphMotif, edge_to_remove: str
) -> None:
    graph, candidate = _parts_for_motif(motif)
    cut_graph = EvidenceGraph(
        graph.corpus_snapshot,
        graph.nodes,
        tuple(edge for edge in graph.edges if edge.edge_id != edge_to_remove),
        graph.support_spans,
    )
    cut_candidate = replace(
        candidate,
        edge_ids=tuple(
            edge_id for edge_id in candidate.edge_ids if edge_id != edge_to_remove
        ),
    )

    with pytest.raises(MotifCompilationError):
        compile_motif_views(cut_graph, cut_candidate, generator_view=GENERATOR_VIEW)


def test_generator_view_rejects_private_gold_leak() -> None:
    graph, candidate = _parts_for_motif(GraphMotif.MULTI_BRANCH_SYNTHESIS)
    leaking = {**GENERATOR_VIEW, "target": "Use required_proof_steps E1 and E2."}

    with pytest.raises(MotifCompilationError, match="evaluator/scorer"):
        compile_motif_views(graph, candidate, generator_view=leaking)


def test_compiler_aggregates_only_same_relation_and_condition_alternatives() -> None:
    graph, candidate = _parts_for_motif(GraphMotif.CLAIM_VERIFICATION)
    nodes = (
        *graph.nodes,
        _node("ev_one_alt", NodeType.ASSERTION, SourceType.WIKIPEDIA),
        _node("ev_wrong_polarity", NodeType.ASSERTION, SourceType.WIKIPEDIA),
        _node("ev_wrong_scope", NodeType.ASSERTION, SourceType.WIKIPEDIA),
        _node("alt_scope", NodeType.CONSTRAINT, SourceType.CASE_SPEC),
    )
    edges = (
        *graph.edges,
        EvidenceEdge(
            "asserts_claim_alt",
            EdgeRelation.ASSERTS,
            "ev_one_alt",
            "proposition",
        ),
        EvidenceEdge(
            "refutes_claim_wrong_polarity",
            EdgeRelation.REFUTES,
            "ev_wrong_polarity",
            "proposition",
        ),
        EvidenceEdge(
            "asserts_claim_wrong_scope",
            EdgeRelation.ASSERTS,
            "ev_wrong_scope",
            "proposition",
        ),
        EvidenceEdge(
            "wrong_scope_condition",
            EdgeRelation.APPLIES_UNDER,
            "ev_wrong_scope",
            "alt_scope",
        ),
    )
    expanded_graph = EvidenceGraph(SNAPSHOT, tuple(nodes), tuple(edges), ())

    compiled = compile_motif_views(
        expanded_graph,
        candidate,
        generator_view=GENERATOR_VIEW,
    )
    steps = compiled.evaluator_view["required_proof_steps"]
    asserted = next(step for step in steps if step.get("step_id") == "E1")
    refuted = next(step for step in steps if step.get("step_id") == "E2")

    assert asserted["acceptable_support"] == {
        "source_ids": ["ev_one", "ev_one_alt"],
        "source_roles": ["concept"],
        "support_relation": "ASSERTS",
        "support_mode": "body",
        "condition_match": True,
    }
    assert refuted["acceptable_support"]["source_ids"] == ["ev_two"]
    assert refuted["acceptable_support"]["support_relation"] == "REFUTES"
