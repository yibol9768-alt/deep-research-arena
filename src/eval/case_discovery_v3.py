"""Deterministic B-stage candidate discovery for DRA v3 evidence graphs.

The module implements the corpus-first portion of the redesign plan:

1. find task-valued graph anchors;
2. expand each anchor by a bounded graph distance;
3. apply the six non-negotiable eligibility predicates;
4. retain the non-dominated Pareto front; and
5. select reproducibly inside declared dataset strata.

No weighted score is computed and the seed is never consulted by anchor
discovery, expansion, eligibility, metrics, or Pareto membership.  It is used
only to break ties between already eligible candidates in the same stratum.
The output is a candidate subgraph, not directly scorable gold.  Human
semantic review and the C-stage motif compiler remain separate gates.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.eval.evidence_graph import (
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SourceType,
    canonical_json_bytes,
)


CASE_DISCOVERY_SCHEMA = "graph_candidate_discovery_v1"


class CandidateDiscoveryError(ValueError):
    """Raised when deterministic candidate discovery cannot be replayed."""


class AnchorKind(StrEnum):
    ATTRIBUTE_DIFFERENCE = "attribute_difference"
    CLAIM_CONFLICT = "claim_conflict"
    CONSTRAINT_RELATION = "constraint_relation"
    MULTI_OPTION_DECISION = "multi_option_decision"
    MECHANISM_CHAIN = "mechanism_chain"


class GraphMotif(StrEnum):
    CONSTRAINT_MATCH_AND_SELECT = "constraint_match_and_select"
    CLAIM_VERIFICATION = "claim_verification"
    EVIDENCE_RECONCILIATION = "evidence_reconciliation"
    CAUSAL_OR_EVOLUTION_EXPLANATION = "causal_or_evolution_explanation"
    MULTI_BRANCH_SYNTHESIS = "multi_branch_synthesis"


_PROOF_RELATIONS = {
    EdgeRelation.ASSERTS,
    EdgeRelation.SUPPORTED_BY,
    EdgeRelation.REFUTES,
    EdgeRelation.CONTRADICTS,
    EdgeRelation.APPLIES_UNDER,
    EdgeRelation.REQUIRES,
    EdgeRelation.DERIVES_FROM,
    EdgeRelation.SATISFIES,
    EdgeRelation.VIOLATES,
}
_DEPENDENCY_RELATIONS = {EdgeRelation.REQUIRES, EdgeRelation.DERIVES_FROM}
_CONCLUSION_TYPES = {
    NodeType.DECISION,
    NodeType.BRIDGE,
    NodeType.CONTRADICTION,
    NodeType.CLAIM,
    NodeType.PROPOSITION,
    NodeType.INFERENCE,
}
_EVIDENCE_LEAF_TYPES = {
    NodeType.ATTRIBUTE,
    NodeType.ASSERTION,
    NodeType.PROPOSITION,
    NodeType.EXPERIENCE_CLAIM,
    NodeType.MECHANISM,
    NodeType.CLAIM,
    NodeType.DOCUMENT,
    NodeType.SNIPPET,
}


def _stable_digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _source_role(source_type: SourceType) -> str:
    if source_type in {SourceType.MAGENTO, SourceType.SHOPPING, SourceType.STRUCTURED_DB}:
        return "product"
    if source_type in {SourceType.POSTMILL, SourceType.FORUM}:
        return "community"
    if source_type in {SourceType.WIKIPEDIA, SourceType.CONCEPT}:
        return "concept"
    if source_type is SourceType.SEARCH_RESULT:
        return "discovery"
    return source_type.value


@dataclass(frozen=True, slots=True)
class GraphAnchor:
    anchor_id: str
    kind: AnchorKind
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "kind": self.kind.value,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
        }


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    connected: bool
    solvable: bool
    multi_option: bool
    multi_source_role: bool
    decision_relevant: bool
    single_page_sufficient: bool
    critical_node_ablation_pass: bool

    @property
    def eligible(self) -> bool:
        return (
            self.connected
            and self.solvable
            and self.multi_option
            and self.multi_source_role
            and self.decision_relevant
            and not self.single_page_sufficient
            and self.critical_node_ablation_pass
        )

    @property
    def failed_predicates(self) -> tuple[str, ...]:
        failures: list[str] = []
        for name in (
            "connected",
            "solvable",
            "multi_option",
            "multi_source_role",
            "decision_relevant",
            "critical_node_ablation_pass",
        ):
            if not getattr(self, name):
                failures.append(name)
        if self.single_page_sufficient:
            failures.append("not_single_page_sufficient")
        return tuple(failures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "solvable": self.solvable,
            "multi_option": self.multi_option,
            "multi_source_role": self.multi_source_role,
            "decision_relevant": self.decision_relevant,
            "single_page_sufficient": self.single_page_sufficient,
            "critical_node_ablation_pass": self.critical_node_ablation_pass,
            "eligible": self.eligible,
            "failed_predicates": list(self.failed_predicates),
        }


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    breadth: int
    depth: int
    conflict: int
    alternative_paths: int
    solvability: float

    def pareto_vector(self) -> tuple[float, ...]:
        return (
            float(self.breadth),
            float(self.depth),
            float(self.conflict),
            float(self.alternative_paths),
            self.solvability,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "breadth": self.breadth,
            "depth": self.depth,
            "conflict": self.conflict,
            "alternative_paths": self.alternative_paths,
            "solvability": self.solvability,
        }


@dataclass(frozen=True, slots=True)
class CandidateSubgraph:
    candidate_id: str
    anchor: GraphAnchor
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    critical_node_ids: tuple[str, ...]
    conclusion_node_ids: tuple[str, ...]
    source_roles: tuple[str, ...]
    topic_cluster: str
    graph_motif: GraphMotif
    eligibility: EligibilityResult
    metrics: CandidateMetrics

    @property
    def stratum_key(self) -> tuple[Any, ...]:
        return (
            self.graph_motif.value,
            self.topic_cluster,
            self.metrics.breadth,
            self.metrics.depth,
            self.metrics.conflict > 0,
            self.source_roles,
            self.metrics.alternative_paths,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "anchor": self.anchor.to_dict(),
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "critical_node_ids": list(self.critical_node_ids),
            "conclusion_node_ids": list(self.conclusion_node_ids),
            "source_roles": list(self.source_roles),
            "topic_cluster": self.topic_cluster,
            "graph_motif": self.graph_motif.value,
            "eligibility": self.eligibility.to_dict(),
            "metrics": self.metrics.to_dict(),
            "stratum": {
                "graph_motif": self.graph_motif.value,
                "topic_cluster": self.topic_cluster,
                "breadth": self.metrics.breadth,
                "depth": self.metrics.depth,
                "contradiction_presence": self.metrics.conflict > 0,
                "source_role_combination": list(self.source_roles),
                "alternative_path_count": self.metrics.alternative_paths,
            },
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    anchors: tuple[GraphAnchor, ...]
    expanded_candidates: tuple[CandidateSubgraph, ...]
    eligible_candidates: tuple[CandidateSubgraph, ...]
    pareto_candidates: tuple[CandidateSubgraph, ...]
    selected_candidates: tuple[CandidateSubgraph, ...]
    max_expansion_depth: int
    selection_seed: str
    per_stratum: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovery_schema": CASE_DISCOVERY_SCHEMA,
            "directly_scorable_gold": False,
            "selection_seed_scope": "same_stratum_tie_break_only",
            "weighted_ranking": False,
            "max_expansion_depth": self.max_expansion_depth,
            "selection_seed": self.selection_seed,
            "per_stratum": self.per_stratum,
            "counts": {
                "anchors": len(self.anchors),
                "expanded": len(self.expanded_candidates),
                "eligible": len(self.eligible_candidates),
                "pareto": len(self.pareto_candidates),
                "selected": len(self.selected_candidates),
            },
            "anchors": [anchor.to_dict() for anchor in self.anchors],
            "expanded_candidates": [
                candidate.to_dict() for candidate in self.expanded_candidates
            ],
            "pareto_candidate_ids": [
                candidate.candidate_id for candidate in self.pareto_candidates
            ],
            "selected_candidate_ids": [
                candidate.candidate_id for candidate in self.selected_candidates
            ],
        }


def _make_anchor(
    kind: AnchorKind,
    node_ids: Iterable[str],
    edge_ids: Iterable[str],
) -> GraphAnchor:
    checked_nodes = tuple(sorted(set(node_ids)))
    checked_edges = tuple(sorted(set(edge_ids)))
    digest = _stable_digest(
        {"kind": kind.value, "node_ids": checked_nodes, "edge_ids": checked_edges}
    )[:20]
    return GraphAnchor(f"anchor_{kind.value}_{digest}", kind, checked_nodes, checked_edges)


def identify_anchors(graph: EvidenceGraph) -> tuple[GraphAnchor, ...]:
    """Find only the five task-valued anchor families declared in the plan."""

    nodes = graph.node_by_id
    anchors: dict[tuple[str, tuple[str, ...]], GraphAnchor] = {}

    def add(kind: AnchorKind, node_ids: Iterable[str], edge_ids: Iterable[str]) -> None:
        anchor = _make_anchor(kind, node_ids, edge_ids)
        anchors[(kind.value, anchor.node_ids)] = anchor

    for edge in sorted(graph.edges, key=lambda item: item.edge_id):
        if edge.relation in {EdgeRelation.CONTRADICTS, EdgeRelation.REFUTES}:
            add(AnchorKind.CLAIM_CONFLICT, (edge.source_id, edge.target_id), (edge.edge_id,))
        elif edge.relation in {EdgeRelation.SATISFIES, EdgeRelation.VIOLATES}:
            add(
                AnchorKind.CONSTRAINT_RELATION,
                (edge.source_id, edge.target_id),
                (edge.edge_id,),
            )

    attribute_groups: dict[str, list[EvidenceEdge]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation is EdgeRelation.HAS_ATTRIBUTE:
            target = nodes[edge.target_id]
            attribute_groups[target.predicate].append(edge)
    for edges in attribute_groups.values():
        entity_ids = {edge.source_id for edge in edges if nodes[edge.source_id].node_type is NodeType.ENTITY}
        values = {
            canonical_json_bytes(nodes[edge.target_id].object)
            for edge in edges
        }
        if len(entity_ids) >= 2 and len(values) >= 2:
            add(
                AnchorKind.ATTRIBUTE_DIFFERENCE,
                (*entity_ids, *(edge.target_id for edge in edges)),
                (edge.edge_id for edge in edges),
            )

    incident_proof_edges: dict[str, list[EvidenceEdge]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation in _PROOF_RELATIONS:
            incident_proof_edges[edge.source_id].append(edge)
            incident_proof_edges[edge.target_id].append(edge)
    for node in graph.nodes:
        incident = incident_proof_edges.get(node.evidence_id, [])
        neighbor_ids = {
            edge.target_id if edge.source_id == node.evidence_id else edge.source_id
            for edge in incident
        }
        if node.node_type is NodeType.DECISION and len(neighbor_ids) >= 2:
            add(
                AnchorKind.MULTI_OPTION_DECISION,
                (node.evidence_id, *neighbor_ids),
                (edge.edge_id for edge in incident),
            )
        if node.node_type is NodeType.MECHANISM and len(neighbor_ids) >= 2:
            add(
                AnchorKind.MECHANISM_CHAIN,
                (node.evidence_id, *neighbor_ids),
                (edge.edge_id for edge in incident),
            )

    return tuple(sorted(anchors.values(), key=lambda item: item.anchor_id))


def bounded_expand(
    graph: EvidenceGraph,
    anchor: GraphAnchor,
    *,
    max_depth: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the induced subgraph at undirected distance ``<= max_depth``."""

    if type(max_depth) is not int or max_depth < 0:
        raise CandidateDiscoveryError("max_depth must be a non-negative integer")
    nodes = graph.node_by_id
    unknown = sorted(set(anchor.node_ids) - set(nodes))
    if unknown:
        raise CandidateDiscoveryError(f"anchor references unknown nodes: {unknown}")
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source_id].add(edge.target_id)
        adjacency[edge.target_id].add(edge.source_id)

    reached = set(anchor.node_ids)
    pending: deque[tuple[str, int]] = deque((node_id, 0) for node_id in anchor.node_ids)
    while pending:
        current, distance = pending.popleft()
        if distance >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append((neighbor, distance + 1))
    edge_ids = tuple(
        edge.edge_id
        for edge in sorted(graph.edges, key=lambda item: item.edge_id)
        if edge.source_id in reached and edge.target_id in reached
    )
    return tuple(sorted(reached)), edge_ids


def _connected(node_ids: Sequence[str], edges: Sequence[EvidenceEdge]) -> bool:
    if not node_ids:
        return False
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source_id].add(edge.target_id)
        adjacency[edge.target_id].add(edge.source_id)
    reached = {node_ids[0]}
    pending = [node_ids[0]]
    while pending:
        current = pending.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return reached == set(node_ids)


def _dependency_shape(
    nodes: Mapping[str, EvidenceNode],
    edges: Sequence[EvidenceEdge],
) -> tuple[tuple[str, ...], tuple[str, ...], int, bool]:
    dependencies: dict[str, set[str]] = defaultdict(set)
    required_as_premise: set[str] = set()
    for edge in edges:
        if edge.relation in _DEPENDENCY_RELATIONS:
            dependencies[edge.source_id].add(edge.target_id)
            required_as_premise.add(edge.target_id)
    conclusions = tuple(
        sorted(
            node_id
            for node_id, node in nodes.items()
            if node.node_type in _CONCLUSION_TYPES
            and dependencies.get(node_id)
            and node_id not in required_as_premise
        )
    )
    if not conclusions:
        return (), (), 0, False

    leaves: set[str] = set()
    cycle = False
    memo_depth: dict[str, int] = {}

    def visit(node_id: str, active: set[str]) -> int:
        nonlocal cycle
        if node_id in memo_depth:
            return memo_depth[node_id]
        if node_id in active:
            cycle = True
            return 0
        required = dependencies.get(node_id, set())
        if not required:
            if nodes[node_id].node_type in _EVIDENCE_LEAF_TYPES:
                leaves.add(node_id)
            memo_depth[node_id] = 0
            return 0
        next_active = {*active, node_id}
        value = 1 + max(visit(child, next_active) for child in sorted(required))
        memo_depth[node_id] = value
        return value

    depth = max(visit(conclusion, set()) for conclusion in conclusions)
    return conclusions, tuple(sorted(leaves)), depth, not cycle


def _infer_motif(
    nodes: Mapping[str, EvidenceNode],
    edges: Sequence[EvidenceEdge],
    *,
    depth: int,
) -> GraphMotif:
    node_types = {node.node_type for node in nodes.values()}
    relations = {edge.relation for edge in edges}
    entity_count = sum(node.node_type is NodeType.ENTITY for node in nodes.values())
    if (
        NodeType.CONTRADICTION in node_types
        and NodeType.CONSTRAINT in node_types
        and (NodeType.BRIDGE in node_types or NodeType.DECISION in node_types)
    ):
        return GraphMotif.EVIDENCE_RECONCILIATION
    if (
        NodeType.CONSTRAINT in node_types
        and NodeType.DECISION in node_types
        and entity_count >= 2
    ):
        return GraphMotif.CONSTRAINT_MATCH_AND_SELECT
    if (
        (NodeType.CLAIM in node_types or NodeType.PROPOSITION in node_types)
        and EdgeRelation.REFUTES in relations
        and (
            EdgeRelation.SUPPORTED_BY in relations
            or EdgeRelation.ASSERTS in relations
        )
    ):
        return GraphMotif.CLAIM_VERIFICATION
    mechanism_is_inference = any(
        nodes[edge.source_id].node_type is NodeType.MECHANISM
        and edge.relation in _DEPENDENCY_RELATIONS
        for edge in edges
    )
    if mechanism_is_inference and depth >= 2:
        return GraphMotif.CAUSAL_OR_EVOLUTION_EXPLANATION
    return GraphMotif.MULTI_BRANCH_SYNTHESIS


def _topic_cluster(nodes: Mapping[str, EvidenceNode]) -> str:
    values = {
        value
        for node in nodes.values()
        for key in ("topic_cluster", "cluster_id")
        if isinstance((value := node.metadata.get(key)), str) and value.strip()
    }
    if len(values) == 1:
        return next(iter(values))
    if not values:
        return "unassigned"
    return "conflict:" + _stable_digest(sorted(values))[:16]


def _alternative_path_count(
    nodes: Mapping[str, EvidenceNode], edges: Sequence[EvidenceEdge]
) -> int:
    support_sources: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.relation not in {
            EdgeRelation.ASSERTS,
            EdgeRelation.SUPPORTED_BY,
            EdgeRelation.REFUTES,
        }:
            continue
        source = nodes[edge.source_id]
        target = nodes[edge.target_id]
        if source.node_type is NodeType.PROPOSITION:
            support_sources[source.evidence_id].add(target.source_url)
        elif target.node_type is NodeType.PROPOSITION:
            support_sources[target.evidence_id].add(source.source_url)
    alternatives = sum(max(0, len(urls) - 1) for urls in support_sources.values())
    return 1 + alternatives if support_sources else 1


def evaluate_candidate(
    graph: EvidenceGraph,
    anchor: GraphAnchor,
    node_ids: Sequence[str],
    edge_ids: Sequence[str],
) -> CandidateSubgraph:
    """Compute eligibility and the five unweighted Pareto dimensions."""

    graph_nodes = graph.node_by_id
    graph_edges = {edge.edge_id: edge for edge in graph.edges}
    nodes = {node_id: graph_nodes[node_id] for node_id in node_ids}
    edges = tuple(graph_edges[edge_id] for edge_id in edge_ids)
    conclusions, dependency_leaves, depth, acyclic = _dependency_shape(nodes, edges)

    explicitly_critical = {
        node_id
        for node_id, node in nodes.items()
        if node.metadata.get("critical") is True or node.metadata.get("vital") is True
    }
    critical = tuple(sorted(set(dependency_leaves) | explicitly_critical))
    source_roles = tuple(
        sorted(
            {
                _source_role(nodes[node_id].source_type)
                for node_id in critical
                if nodes[node_id].node_type is not NodeType.SEARCH_RESULT
            }
        )
    )
    critical_urls = {nodes[node_id].source_url for node_id in critical}

    discovery_roots = tuple(
        sorted(
            node_id
            for node_id, node in nodes.items()
            if node.metadata.get("discovery_root") is True
        )
    )
    reachable = set(
        graph.discoverable_node_ids(
            discovery_roots,
            include_seed_roots=True,
            include_search_result_roots=True,
        )
    )
    critical_reachable = set(critical) <= reachable
    admissible = bool(conclusions) and all(
        nodes[node_id].metadata.get("oracle_unique_or_admissible") is True
        for node_id in conclusions
    )
    solvability = (
        len(set(critical) & reachable) / len(critical)
        if critical
        else 0.0
    )
    if not admissible or not acyclic:
        solvability = 0.0

    relations = {edge.relation for edge in edges}
    entity_count = sum(node.node_type is NodeType.ENTITY for node in nodes.values())
    support_directions = {
        edge.relation
        for edge in edges
        if edge.relation in {EdgeRelation.SUPPORTED_BY, EdgeRelation.ASSERTS, EdgeRelation.REFUTES}
    }
    dependency_branches = max(
        (
            sum(
                edge.relation in _DEPENDENCY_RELATIONS and edge.source_id == conclusion
                for edge in edges
            )
            for conclusion in conclusions
        ),
        default=0,
    )
    multi_option = (
        entity_count >= 2
        or dependency_branches >= 2
        or (
            EdgeRelation.REFUTES in support_directions
            and bool(support_directions - {EdgeRelation.REFUTES})
        )
    )
    decision_relevant = bool(conclusions) and (
        any(nodes[node_id].node_type is NodeType.DECISION for node_id in conclusions)
        or EdgeRelation.CONTRADICTS in relations
        or EdgeRelation.REFUTES in relations
        or dependency_branches >= 2
    )
    critical_ablation = (
        len(critical) >= 2
        and set(explicitly_critical) <= set(dependency_leaves)
        and all(node_id in dependency_leaves for node_id in critical)
    )
    eligibility = EligibilityResult(
        connected=_connected(tuple(node_ids), edges),
        solvable=(
            len(critical) >= 2
            and depth >= 2
            and critical_reachable
            and admissible
            and acyclic
        ),
        multi_option=multi_option,
        multi_source_role=len(source_roles) >= 2,
        decision_relevant=decision_relevant,
        single_page_sufficient=len(critical_urls) <= 1,
        critical_node_ablation_pass=critical_ablation,
    )
    breadth = max(len(critical), len(source_roles), entity_count, dependency_branches)
    conflict = sum(
        edge.relation in {EdgeRelation.CONTRADICTS, EdgeRelation.REFUTES}
        for edge in edges
    )
    metrics = CandidateMetrics(
        breadth=breadth,
        depth=depth,
        conflict=conflict,
        alternative_paths=_alternative_path_count(nodes, edges),
        solvability=solvability,
    )
    motif = _infer_motif(nodes, edges, depth=depth)
    identity = {
        "anchor_id": anchor.anchor_id,
        "node_ids": sorted(node_ids),
        "edge_ids": sorted(edge_ids),
        "graph_stamp": graph.graph_stamp,
    }
    return CandidateSubgraph(
        candidate_id=f"candidate_{_stable_digest(identity)[:24]}",
        anchor=anchor,
        node_ids=tuple(sorted(node_ids)),
        edge_ids=tuple(sorted(edge_ids)),
        critical_node_ids=critical,
        conclusion_node_ids=conclusions,
        source_roles=source_roles,
        topic_cluster=_topic_cluster(nodes),
        graph_motif=motif,
        eligibility=eligibility,
        metrics=metrics,
    )


def pareto_front(candidates: Iterable[CandidateSubgraph]) -> tuple[CandidateSubgraph, ...]:
    """Return all non-dominated eligible candidates without scalarization."""

    rows = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if any(not candidate.eligibility.eligible for candidate in rows):
        raise CandidateDiscoveryError("Pareto input must contain eligible candidates only")

    def dominates(left: CandidateSubgraph, right: CandidateSubgraph) -> bool:
        left_vector = left.metrics.pareto_vector()
        right_vector = right.metrics.pareto_vector()
        return all(a >= b for a, b in zip(left_vector, right_vector)) and any(
            a > b for a, b in zip(left_vector, right_vector)
        )

    return tuple(
        candidate
        for candidate in rows
        if not any(
            other.candidate_id != candidate.candidate_id and dominates(other, candidate)
            for other in rows
        )
    )


def stratified_select(
    candidates: Iterable[CandidateSubgraph],
    *,
    per_stratum: int,
    seed: str,
) -> tuple[CandidateSubgraph, ...]:
    """Select inside exact strata with a seed used only as a tie breaker."""

    if type(per_stratum) is not int or per_stratum <= 0:
        raise CandidateDiscoveryError("per_stratum must be a positive integer")
    if not isinstance(seed, str) or not seed:
        raise CandidateDiscoveryError("seed must be a non-empty string")
    strata: dict[tuple[Any, ...], list[CandidateSubgraph]] = defaultdict(list)
    for candidate in candidates:
        if not candidate.eligibility.eligible:
            raise CandidateDiscoveryError("strata input must contain eligible candidates only")
        strata[candidate.stratum_key].append(candidate)
    selected: list[CandidateSubgraph] = []
    for key in sorted(strata, key=repr):
        rows = sorted(
            strata[key],
            key=lambda item: (
                hashlib.sha256(
                    f"{seed}\0{item.candidate_id}".encode("utf-8")
                ).hexdigest(),
                item.candidate_id,
            ),
        )
        selected.extend(rows[:per_stratum])
    return tuple(sorted(selected, key=lambda item: item.candidate_id))


def discover_candidates(
    graph: EvidenceGraph,
    *,
    max_depth: int = 3,
    per_stratum: int = 1,
    seed: str = "dra-v3-strata-v1",
) -> DiscoveryResult:
    """Run the complete deterministic B-stage candidate discovery pipeline."""

    anchors = identify_anchors(graph)
    expanded = tuple(
        evaluate_candidate(
            graph,
            anchor,
            *bounded_expand(graph, anchor, max_depth=max_depth),
        )
        for anchor in anchors
    )
    eligible = tuple(candidate for candidate in expanded if candidate.eligibility.eligible)
    pareto = pareto_front(eligible)
    selected = stratified_select(pareto, per_stratum=per_stratum, seed=seed)
    return DiscoveryResult(
        anchors=anchors,
        expanded_candidates=expanded,
        eligible_candidates=eligible,
        pareto_candidates=pareto,
        selected_candidates=selected,
        max_expansion_depth=max_depth,
        selection_seed=seed,
        per_stratum=per_stratum,
    )


__all__ = [
    "AnchorKind",
    "CASE_DISCOVERY_SCHEMA",
    "CandidateDiscoveryError",
    "CandidateMetrics",
    "CandidateSubgraph",
    "DiscoveryResult",
    "EligibilityResult",
    "GraphAnchor",
    "GraphMotif",
    "bounded_expand",
    "discover_candidates",
    "evaluate_candidate",
    "identify_anchors",
    "pareto_front",
    "stratified_select",
]
