from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import scripts.enumerate_cases_v3 as enumeration_cli

from src.eval.case_discovery_v3 import (
    CandidateDiscoveryError,
    CandidateMetrics,
    discover_candidates,
    identify_anchors,
    pareto_front,
    stratified_select,
)
from src.eval.evidence_graph import (
    DiscoveryMethod,
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SourceType,
)


SNAPSHOT = "corpus-v3-discovery-test"


def _node(
    node_id: str,
    node_type: NodeType,
    url: str,
    source_type: SourceType,
    *,
    metadata: dict[str, object] | None = None,
) -> EvidenceNode:
    return EvidenceNode(
        evidence_id=node_id,
        node_type=node_type,
        subject=node_id,
        predicate="supports",
        object=f"value:{node_id}",
        source_url=url,
        source_type=source_type,
        content_sha256="1" * 64,
        corpus_snapshot=SNAPSHOT,
        metadata={"topic_cluster": "audio", **(metadata or {})},
    )


def _eligible_graph(*, single_page: bool = False) -> EvidenceGraph:
    shared = "http://localhost:7770/shared"
    product_url = shared if single_page else "http://localhost:7770/product"
    forum_url = shared if single_page else "http://localhost:9999/forum"
    concept_url = shared if single_page else "http://localhost:8090/concept"
    search_url = "http://localhost:8888/search?q=audio"
    nodes = (
        _node(
            "decision_audio",
            NodeType.DECISION,
            product_url,
            SourceType.CASE_SPEC,
            metadata={"oracle_unique_or_admissible": True},
        ),
        _node("branch_fit", NodeType.BRIDGE, product_url, SourceType.CASE_SPEC),
        _node("branch_noise", NodeType.BRIDGE, concept_url, SourceType.CASE_SPEC),
        _node("ev_product", NodeType.ATTRIBUTE, product_url, SourceType.MAGENTO),
        _node("ev_forum", NodeType.EXPERIENCE_CLAIM, forum_url, SourceType.POSTMILL),
        _node("ev_concept", NodeType.MECHANISM, concept_url, SourceType.WIKIPEDIA),
        _node("search_audio", NodeType.SEARCH_RESULT, search_url, SourceType.SEARCH_RESULT),
    )
    edges = (
        EvidenceEdge("req_decision_fit", EdgeRelation.REQUIRES, "decision_audio", "branch_fit"),
        EvidenceEdge("req_decision_noise", EdgeRelation.REQUIRES, "decision_audio", "branch_noise"),
        EvidenceEdge("req_fit_product", EdgeRelation.REQUIRES, "branch_fit", "ev_product"),
        EvidenceEdge("req_fit_forum", EdgeRelation.REQUIRES, "branch_fit", "ev_forum"),
        EvidenceEdge("req_noise_concept", EdgeRelation.REQUIRES, "branch_noise", "ev_concept"),
        EvidenceEdge(
            "discover_product",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_product",
            "search_audio",
            discovery_method=DiscoveryMethod.SEARCH_RESULT,
        ),
        EvidenceEdge(
            "discover_forum",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_forum",
            "search_audio",
            discovery_method=DiscoveryMethod.SEARCH_RESULT,
        ),
        EvidenceEdge(
            "discover_concept",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_concept",
            "search_audio",
            discovery_method=DiscoveryMethod.SEARCH_RESULT,
        ),
    )
    return EvidenceGraph(SNAPSHOT, nodes, edges, ())


def test_anchor_expansion_hard_gates_and_metrics_are_replayable() -> None:
    graph = _eligible_graph()

    first = discover_candidates(graph, max_depth=2, per_stratum=1, seed="seed-a")
    second = discover_candidates(graph, max_depth=2, per_stratum=1, seed="seed-a")

    assert first.to_dict() == second.to_dict()
    assert len(identify_anchors(graph)) == 1
    assert len(first.eligible_candidates) == 1
    candidate = first.eligible_candidates[0]
    assert candidate.eligibility.eligible is True
    assert candidate.critical_node_ids == ("ev_concept", "ev_forum", "ev_product")
    assert candidate.source_roles == ("community", "concept", "product")
    assert candidate.metrics.breadth == 3
    assert candidate.metrics.depth == 2
    assert candidate.metrics.solvability == 1.0
    assert candidate.graph_motif.value == "multi_branch_synthesis"
    assert first.to_dict()["weighted_ranking"] is False
    assert first.to_dict()["selection_seed_scope"] == "same_stratum_tie_break_only"


def test_normalized_proposition_can_be_an_ablation_sensitive_evidence_leaf() -> None:
    graph = _eligible_graph()
    nodes = tuple(
        replace(node, node_type=NodeType.PROPOSITION)
        if node.evidence_id == "ev_forum"
        else node
        for node in graph.nodes
    )
    proposition_graph = EvidenceGraph(
        graph.corpus_snapshot,
        nodes,
        graph.edges,
        graph.support_spans,
    )

    candidate = discover_candidates(
        proposition_graph, max_depth=2
    ).eligible_candidates[0]

    assert "ev_forum" in candidate.critical_node_ids
    assert candidate.eligibility.critical_node_ablation_pass is True


def test_single_page_candidate_is_rejected_before_pareto() -> None:
    result = discover_candidates(_eligible_graph(single_page=True), max_depth=2)

    assert result.eligible_candidates == ()
    candidate = result.expanded_candidates[0]
    assert candidate.eligibility.single_page_sufficient is True
    assert "not_single_page_sufficient" in candidate.eligibility.failed_predicates
    assert result.pareto_candidates == ()


def test_pareto_front_uses_five_dimensions_without_a_weighted_score() -> None:
    base = discover_candidates(_eligible_graph(), max_depth=2).eligible_candidates[0]
    dominated = replace(
        base,
        candidate_id="candidate_dominated",
        metrics=CandidateMetrics(2, 2, 0, 1, 1.0),
    )
    wide = replace(
        base,
        candidate_id="candidate_wide",
        metrics=CandidateMetrics(5, 2, 0, 1, 1.0),
    )
    deep_conflict = replace(
        base,
        candidate_id="candidate_deep_conflict",
        metrics=CandidateMetrics(3, 4, 1, 2, 1.0),
    )

    result = pareto_front((dominated, deep_conflict, wide))

    assert {candidate.candidate_id for candidate in result} == {
        "candidate_deep_conflict",
        "candidate_wide",
    }


def test_seed_only_breaks_ties_inside_an_exact_stratum() -> None:
    base = discover_candidates(_eligible_graph(), max_depth=2).eligible_candidates[0]
    rows = tuple(replace(base, candidate_id=f"candidate_{index}") for index in range(5))

    first = stratified_select(rows, per_stratum=2, seed="fixed")
    replay = stratified_select(tuple(reversed(rows)), per_stratum=2, seed="fixed")

    assert first == replay
    assert len(first) == 2
    with pytest.raises(CandidateDiscoveryError, match="positive integer"):
        stratified_select(rows, per_stratum=0, seed="fixed")


def test_enumerator_exposes_discovery_as_a_non_gold_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        enumeration_cli,
        "load_graph_structure",
        lambda _path: _eligible_graph(),
    )
    output = tmp_path / "candidates.json"

    assert enumeration_cli.main(
        [
            "--discover-graph-dir",
            str(tmp_path / "graph"),
            "--max-expansion-depth",
            "2",
            "--out",
            str(output),
        ]
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["discovery_schema"] == "graph_candidate_discovery_v1"
    assert payload["directly_scorable_gold"] is False
    assert payload["counts"]["selected"] == 1
