"""C-stage graph motif compiler for DRA v3.

The compiler consumes one eligible B-stage subgraph and emits the two views
that form the common source for query generation and proof-step scoring.  It
derives evaluator obligations from graph topology and frozen node metadata.
It never invents evidence text, URLs, rules, conditions, or answer labels.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.eval.case_discovery_v3 import CandidateSubgraph, GraphMotif
from src.eval.evidence_graph import (
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SourceType,
    canonical_json_bytes,
    sha256_bytes,
)


MOTIF_COMPILATION_SCHEMA = "graph_motif_compilation_v1"
_DEPENDENCY_RELATIONS = {EdgeRelation.REQUIRES, EdgeRelation.DERIVES_FROM}
_PRIVATE_GENERATOR_KEYS = {
    "evaluator_view",
    "propositions",
    "required_proof_steps",
    "proof_steps",
    "step_id",
    "source_url",
    "oracle",
    "gold_answer",
    "acceptable_conclusions",
    "scorer",
}
_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")


class MotifCompilationError(ValueError):
    """Raised when a candidate cannot be compiled without inventing gold."""


def _source_role(source_type: SourceType) -> str:
    if source_type in {SourceType.MAGENTO, SourceType.SHOPPING, SourceType.STRUCTURED_DB}:
        return "product"
    if source_type in {SourceType.POSTMILL, SourceType.FORUM}:
        return "community"
    if source_type in {SourceType.WIKIPEDIA, SourceType.CONCEPT}:
        return "concept"
    return source_type.value


def _validate_generator_view(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"scenario", "constraints", "candidate_actions", "target"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing or unknown:
        raise MotifCompilationError(
            f"GeneratorView fields mismatch; missing={missing}, unknown={unknown}"
        )
    scenario = value["scenario"]
    target = value["target"]
    constraints = value["constraints"]
    actions = value["candidate_actions"]
    if not isinstance(scenario, str) or not scenario.strip():
        raise MotifCompilationError("GeneratorView scenario must be non-empty text")
    if not isinstance(target, str) or not target.strip():
        raise MotifCompilationError("GeneratorView target must be non-empty text")
    for label, rows, minimum in (
        ("constraints", constraints, 1),
        ("candidate_actions", actions, 2),
    ):
        if (
            not isinstance(rows, list)
            or len(rows) < minimum
            or not all(isinstance(row, str) and row.strip() for row in rows)
            or len(set(rows)) != len(rows)
        ):
            raise MotifCompilationError(
                f"GeneratorView {label} must contain {minimum}+ unique non-empty strings"
            )
    payload = {
        "scenario": scenario.strip(),
        "constraints": list(constraints),
        "candidate_actions": list(actions),
        "target": target.strip(),
    }
    folded = canonical_json_bytes(payload).decode("utf-8").casefold()
    if _URL_RE.search(folded):
        raise MotifCompilationError("GeneratorView must not contain URLs")
    leaked = sorted(key for key in _PRIVATE_GENERATOR_KEYS if key in folded)
    if leaked:
        raise MotifCompilationError(
            f"GeneratorView contains evaluator/scorer vocabulary: {leaked}"
        )
    return payload


def _candidate_graph(
    graph: EvidenceGraph, candidate: CandidateSubgraph
) -> tuple[dict[str, EvidenceNode], tuple[EvidenceEdge, ...]]:
    if not candidate.eligibility.eligible:
        raise MotifCompilationError("C-stage compilation requires an eligible B-stage candidate")
    if candidate.topic_cluster == "unassigned" or candidate.topic_cluster.startswith(
        "conflict:"
    ):
        raise MotifCompilationError(
            "C-stage compilation requires one unambiguous pre-authored topic_cluster"
        )
    graph_nodes = graph.node_by_id
    graph_edges = {edge.edge_id: edge for edge in graph.edges}
    missing_nodes = sorted(set(candidate.node_ids) - set(graph_nodes))
    missing_edges = sorted(set(candidate.edge_ids) - set(graph_edges))
    if missing_nodes or missing_edges:
        raise MotifCompilationError(
            f"candidate references unknown graph records; nodes={missing_nodes}, edges={missing_edges}"
        )
    nodes = {node_id: graph_nodes[node_id] for node_id in candidate.node_ids}
    edges = tuple(graph_edges[edge_id] for edge_id in candidate.edge_ids)
    escaped = sorted(
        edge.edge_id
        for edge in edges
        if edge.source_id not in nodes or edge.target_id not in nodes
    )
    if escaped:
        raise MotifCompilationError(f"candidate edges escape the selected node set: {escaped}")
    return nodes, edges


def _dependency_contract(
    candidate: CandidateSubgraph,
    nodes: Mapping[str, EvidenceNode],
    edges: Sequence[EvidenceEdge],
) -> tuple[dict[str, set[str]], dict[str, int]]:
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.relation in _DEPENDENCY_RELATIONS:
            dependencies[edge.source_id].add(edge.target_id)
    conclusions = set(candidate.conclusion_node_ids)
    if len(conclusions) != 1:
        raise MotifCompilationError("motif compiler requires exactly one final conclusion node")
    conclusion = next(iter(conclusions))
    if nodes[conclusion].node_type is not NodeType.DECISION:
        raise MotifCompilationError("the final conclusion must be an explicit decision node")

    depth_by_node: dict[str, int] = {}
    active: set[str] = set()

    def visit(node_id: str) -> int:
        if node_id in depth_by_node:
            return depth_by_node[node_id]
        if node_id in active:
            raise MotifCompilationError("proof dependency graph contains a cycle")
        active.add(node_id)
        required = dependencies.get(node_id, set())
        depth = 0 if not required else 1 + max(visit(child) for child in sorted(required))
        active.remove(node_id)
        depth_by_node[node_id] = depth
        return depth

    visit(conclusion)
    closure = set(depth_by_node)
    if not set(candidate.critical_node_ids) <= closure:
        missing = sorted(set(candidate.critical_node_ids) - closure)
        raise MotifCompilationError(
            f"critical evidence is outside the final proof dependency closure: {missing}"
        )
    leaves = {node_id for node_id in closure if not dependencies.get(node_id)}
    if leaves != set(candidate.critical_node_ids):
        raise MotifCompilationError(
            "critical evidence must exactly equal the ablation-sensitive proof leaves; "
            f"critical={sorted(candidate.critical_node_ids)}, leaves={sorted(leaves)}"
        )
    if len(leaves) < 2 or depth_by_node[conclusion] < 2:
        raise MotifCompilationError("compiled motif is not a multi-hop proof DAG")
    return dependencies, depth_by_node


def _topology_checks(
    motif: GraphMotif,
    candidate: CandidateSubgraph,
    nodes: Mapping[str, EvidenceNode],
    edges: Sequence[EvidenceEdge],
    dependencies: Mapping[str, set[str]],
) -> dict[str, bool]:
    node_types = {node.node_type for node in nodes.values()}
    relations = {edge.relation for edge in edges}
    decision = candidate.conclusion_node_ids[0]
    direct_branches = len(dependencies.get(decision, set()))
    checks: dict[str, bool]
    if motif is GraphMotif.CONSTRAINT_MATCH_AND_SELECT:
        checks = {
            "has_user_constraint": NodeType.CONSTRAINT in node_types,
            "has_attributes": NodeType.ATTRIBUTE in node_types,
            "has_multiple_options": sum(
                node.node_type is NodeType.ENTITY for node in nodes.values()
            )
            >= 2,
            "has_constraint_relation": bool(
                relations
                & {
                    EdgeRelation.SATISFIES,
                    EdgeRelation.VIOLATES,
                }
            ),
            "has_decision": NodeType.DECISION in node_types,
        }
    elif motif is GraphMotif.CLAIM_VERIFICATION:
        checks = {
            "has_normalized_claim": bool(
                node_types & {NodeType.PROPOSITION, NodeType.CLAIM}
            ),
            "has_support": bool(
                relations & {EdgeRelation.ASSERTS, EdgeRelation.SUPPORTED_BY}
            ),
            "has_refutation": EdgeRelation.REFUTES in relations,
            "has_decision": NodeType.DECISION in node_types,
        }
    elif motif is GraphMotif.EVIDENCE_RECONCILIATION:
        checks = {
            "has_conflict": (
                EdgeRelation.CONTRADICTS in relations
                or NodeType.CONTRADICTION in node_types
            ),
            "has_scope_condition": (
                NodeType.CONSTRAINT in node_types
                and EdgeRelation.APPLIES_UNDER in relations
            ),
            "has_reconciliation_bridge": NodeType.BRIDGE in node_types,
            "has_decision": NodeType.DECISION in node_types,
        }
    elif motif is GraphMotif.CAUSAL_OR_EVOLUTION_EXPLANATION:
        mechanism_nodes = {
            node_id
            for node_id, node in nodes.items()
            if node.node_type is NodeType.MECHANISM
        }
        checks = {
            "has_mechanism": bool(mechanism_nodes),
            "mechanism_is_derived": any(
                dependencies.get(node_id) for node_id in mechanism_nodes
            ),
            "has_state_or_proposition": bool(
                node_types & {NodeType.ATTRIBUTE, NodeType.PROPOSITION, NodeType.CLAIM}
            ),
            "has_decision": NodeType.DECISION in node_types,
        }
    else:
        checks = {
            "has_multiple_independent_branches": direct_branches >= 2,
            "has_synthesized_decision": NodeType.DECISION in node_types,
        }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise MotifCompilationError(
            f"{motif.value} topology failed required checks: {failed}"
        )
    return checks


def validate_motif_topology(
    graph: EvidenceGraph,
    candidate: CandidateSubgraph,
) -> dict[str, bool]:
    """Validate one candidate against its exact graph-native motif topology."""

    nodes, edges = _candidate_graph(graph, candidate)
    dependencies, _ = _dependency_contract(candidate, nodes, edges)
    return _topology_checks(
        candidate.graph_motif,
        candidate,
        nodes,
        edges,
        dependencies,
    )


def _bound_proposition(
    node_id: str,
    nodes: Mapping[str, EvidenceNode],
    edges: Sequence[EvidenceEdge],
) -> str:
    node = nodes[node_id]
    declared = node.metadata.get("proposition_id")
    if isinstance(declared, str) and declared:
        if declared not in nodes or nodes[declared].node_type is not NodeType.PROPOSITION:
            raise MotifCompilationError(
                f"{node_id} declares unknown/non-proposition proposition_id {declared!r}"
            )
        return declared
    if node.node_type is NodeType.PROPOSITION:
        return node_id
    candidates: set[str] = set()
    for edge in edges:
        if edge.relation not in {
            EdgeRelation.ASSERTS,
            EdgeRelation.SUPPORTED_BY,
            EdgeRelation.REFUTES,
        }:
            continue
        if edge.source_id == node_id and nodes[edge.target_id].node_type is NodeType.PROPOSITION:
            candidates.add(edge.target_id)
        if edge.target_id == node_id and nodes[edge.source_id].node_type is NodeType.PROPOSITION:
            candidates.add(edge.source_id)
    if len(candidates) == 1:
        return next(iter(candidates))
    if not candidates and node.node_type is NodeType.ATTRIBUTE:
        # Structured attributes already carry a normalized typed proposition.
        return node_id
    raise MotifCompilationError(
        f"critical node {node_id} must bind exactly one normalized proposition; "
        f"found {sorted(candidates)}"
    )


def _condition_signature(
    graph: EvidenceGraph,
    node_id: str,
    *,
    semantic_edge: EvidenceEdge | None = None,
) -> tuple[str, ...]:
    node = graph.node_by_id[node_id]
    conditions = {
        edge.target_id
        for edge in graph.edges
        if edge.relation is EdgeRelation.APPLIES_UNDER
        and edge.source_id == node_id
    }
    for owner in (node.metadata, semantic_edge.metadata if semantic_edge else {}):
        raw = owner.get("condition_ids", owner.get("conditions", []))
        if isinstance(raw, str):
            conditions.add(raw)
        elif isinstance(raw, list):
            conditions.update(str(value) for value in raw if str(value))
        elif raw not in (None, []):
            raise MotifCompilationError(
                f"node {node_id} conditions must be a string or string list"
            )
    unknown = sorted(conditions - set(graph.node_by_id))
    if unknown:
        raise MotifCompilationError(
            f"node {node_id} references unknown conditions: {unknown}"
        )
    wrong_type = sorted(
        condition_id
        for condition_id in conditions
        if graph.node_by_id[condition_id].node_type is not NodeType.CONSTRAINT
    )
    if wrong_type:
        raise MotifCompilationError(
            f"node {node_id} applicability targets are not constraints: {wrong_type}"
        )
    return tuple(sorted(conditions))


def _semantic_support_binding(
    graph: EvidenceGraph,
    source_id: str,
    proposition_id: str,
) -> tuple[str, str, tuple[str, ...]]:
    if source_id == proposition_id:
        return (
            "SELF",
            "self",
            _condition_signature(graph, source_id),
        )
    candidates = [
        edge
        for edge in graph.edges
        if edge.relation
        in {
            EdgeRelation.ASSERTS,
            EdgeRelation.SUPPORTED_BY,
            EdgeRelation.REFUTES,
        }
        and {edge.source_id, edge.target_id} == {source_id, proposition_id}
        and (
            edge.relation is not EdgeRelation.ASSERTS
            or (
                edge.source_id == source_id
                and edge.target_id == proposition_id
            )
        )
    ]
    if len(candidates) != 1:
        raise MotifCompilationError(
            f"support node {source_id} must have exactly one typed semantic edge "
            f"to proposition {proposition_id}; found {len(candidates)}"
        )
    edge = candidates[0]
    direction = (
        "source_to_proposition"
        if edge.source_id == source_id
        else "proposition_to_source"
    )
    return (
        edge.relation.value,
        direction,
        _condition_signature(graph, source_id, semantic_edge=edge),
    )


def _declared_source_roles(
    source: EvidenceNode,
    proposition: EvidenceNode,
) -> set[str]:
    for owner in (source.metadata, proposition.metadata):
        raw = owner.get(
            "acceptable_source_roles",
            owner.get("source_roles"),
        )
        if raw is None:
            continue
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise MotifCompilationError(
                "acceptable_source_roles must be a non-empty string list"
            )
        roles = {str(value) for value in values}
        if not roles:
            raise MotifCompilationError(
                "acceptable_source_roles must not be empty"
            )
        return roles
    return {_source_role(source.source_type)}


def _equivalent_support_binding(
    graph: EvidenceGraph,
    source_id: str,
    proposition_id: str,
) -> tuple[list[str], list[str], str, str]:
    """Compile graph-verified alternatives with identical support semantics."""

    nodes = graph.node_by_id
    source = nodes[source_id]
    proposition = nodes[proposition_id]
    relation, direction, conditions = _semantic_support_binding(
        graph,
        source_id,
        proposition_id,
    )
    verifier_kind = source.verifier.get("kind")
    allowed_roles = _declared_source_roles(source, proposition)
    equivalent_ids: list[str] = []
    for candidate in graph.nodes:
        candidate_role = _source_role(candidate.source_type)
        if candidate_role not in allowed_roles:
            continue
        if candidate.verifier.get("kind") != verifier_kind:
            continue
        try:
            candidate_binding = _semantic_support_binding(
                graph,
                candidate.evidence_id,
                proposition_id,
            )
        except MotifCompilationError:
            continue
        if candidate_binding != (relation, direction, conditions):
            continue
        equivalent_ids.append(candidate.evidence_id)
    if source_id not in equivalent_ids:
        raise MotifCompilationError(
            f"critical support node {source_id} failed its own equivalence signature"
        )
    equivalent_ids.sort()
    roles = sorted({_source_role(nodes[node_id].source_type) for node_id in equivalent_ids})
    has_body = any(nodes[node_id].body_support for node_id in equivalent_ids)
    has_snippet = any(
        nodes[node_id].search_snippet_support for node_id in equivalent_ids
    )
    if has_body and has_snippet:
        support_mode = "body_or_exact_snippet"
    elif has_body:
        support_mode = "body"
    else:
        support_mode = "exact_snippet"
    return equivalent_ids, roles, relation, support_mode


@dataclass(frozen=True, slots=True)
class MotifCompilation:
    candidate_id: str
    graph_motif: GraphMotif
    generator_view: Mapping[str, Any]
    evaluator_view: Mapping[str, Any]
    graph_node_to_step_id: Mapping[str, str]
    topology_checks: Mapping[str, bool]
    compilation_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "motif_compilation_schema": MOTIF_COMPILATION_SCHEMA,
            "candidate_id": self.candidate_id,
            "graph_motif": self.graph_motif.value,
            "generator_view": dict(self.generator_view),
            "evaluator_view": dict(self.evaluator_view),
            "graph_node_to_step_id": dict(self.graph_node_to_step_id),
            "topology_checks": dict(self.topology_checks),
            "compilation_sha256": self.compilation_sha256,
            "directly_scorable_gold": False,
        }


def compile_motif_views(
    graph: EvidenceGraph,
    candidate: CandidateSubgraph,
    *,
    generator_view: Mapping[str, Any],
) -> MotifCompilation:
    """Compile graph topology into leak-separated generator/evaluator views."""

    nodes, edges = _candidate_graph(graph, candidate)
    dependencies, depth_by_node = _dependency_contract(candidate, nodes, edges)
    checks = _topology_checks(
        candidate.graph_motif,
        candidate,
        nodes,
        edges,
        dependencies,
    )
    public_view = _validate_generator_view(generator_view)

    critical_ids = sorted(candidate.critical_node_ids)
    derived_ids = sorted(
        (set(depth_by_node) - set(critical_ids)),
        key=lambda node_id: (depth_by_node[node_id], node_id),
    )
    node_to_step: dict[str, str] = {
        node_id: f"E{index}"
        for index, node_id in enumerate(critical_ids, 1)
    }
    bridge_index = 0
    decision_index = 0
    for node_id in derived_ids:
        if nodes[node_id].node_type is NodeType.DECISION:
            decision_index += 1
            node_to_step[node_id] = f"D{decision_index}"
        else:
            bridge_index += 1
            node_to_step[node_id] = f"B{bridge_index}"

    steps: list[dict[str, Any]] = []
    propositions: list[str] = []
    for node_id in critical_ids:
        node = nodes[node_id]
        proposition = _bound_proposition(node_id, nodes, edges)
        propositions.append(proposition)
        verifier_kind = node.verifier.get("kind")
        if not isinstance(verifier_kind, str) or not verifier_kind:
            raise MotifCompilationError(f"critical node {node_id} lacks verifier.kind")
        (
            support_source_ids,
            support_roles,
            support_relation,
            support_mode,
        ) = _equivalent_support_binding(graph, node_id, proposition)
        steps.append(
            {
                "step_id": node_to_step[node_id],
                "type": "evidence",
                "required": True,
                "vital": True,
                "claim": proposition,
                "verifier": verifier_kind,
                "acceptable_support": {
                    "source_ids": support_source_ids,
                    "source_roles": support_roles,
                    "support_relation": support_relation,
                    "support_mode": support_mode,
                    "condition_match": True,
                },
                "provenance_contract": "discovered_then_observed",
            }
        )
    for node_id in derived_ids:
        node = nodes[node_id]
        rule = node.metadata.get("rule_id", node.metadata.get("rule"))
        if not isinstance(rule, str) or not rule:
            raise MotifCompilationError(
                f"derived proof node {node_id} requires a pre-authored deterministic rule_id"
            )
        required = sorted(
            (node_to_step[dependency] for dependency in dependencies[node_id]),
            key=lambda value: (value[0], int(value[1:])),
        )
        steps.append(
            {
                "step_id": node_to_step[node_id],
                "type": (
                    "decision" if node.node_type is NodeType.DECISION else "bridge"
                ),
                "required": True,
                "vital": True,
                "requires": required,
                "rule": rule,
            }
        )
    if len(steps) < 4:
        raise MotifCompilationError("formal motif needs at least four required proof steps")

    evaluator_view = {
        "propositions": sorted(set(propositions)),
        "required_proof_steps": steps,
        "final_answer_contract": {
            "unique_product_required": False,
            "must_address_constraints": True,
            "must_explain_tradeoffs": True,
            "must_depend_on_verified_steps": True,
        },
    }
    digest_payload = {
        "schema": MOTIF_COMPILATION_SCHEMA,
        "graph_stamp": graph.graph_stamp,
        "candidate_id": candidate.candidate_id,
        "graph_motif": candidate.graph_motif.value,
        "generator_view": public_view,
        "evaluator_view": evaluator_view,
        "graph_node_to_step_id": node_to_step,
        "topology_checks": checks,
    }
    return MotifCompilation(
        candidate_id=candidate.candidate_id,
        graph_motif=candidate.graph_motif,
        generator_view=public_view,
        evaluator_view=evaluator_view,
        graph_node_to_step_id=node_to_step,
        topology_checks=checks,
        compilation_sha256=sha256_bytes(canonical_json_bytes(digest_payload)),
    )


__all__ = [
    "MOTIF_COMPILATION_SCHEMA",
    "MotifCompilation",
    "MotifCompilationError",
    "compile_motif_views",
    "validate_motif_topology",
]
