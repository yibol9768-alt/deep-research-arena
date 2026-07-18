#!/usr/bin/env python3
"""Compile one validated v3 case draft into private gold and a public task.

Formal compilation is fail-closed.  It requires both an external evidence
catalog and a complete frozen-corpus URL registry.  ``--validate-draft`` is the
only mode that may run without those inputs, and it never writes a formal case.

Examples:

    python3 scripts/compile_case_v3.py draft.json --validate-draft

    python3 scripts/compile_case_v3.py draft.json \
      --evidence-catalog data/evidence_graph/snapshot/ \
      --corpus-registry data/evidence_graph/snapshot/corpus_registry.json \
      --case-out data/golden/cases_v3/dra_v3_audio_0001.json \
      --task-out data/tasks/deep_research/v3/dra_v3_audio_0001.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.case_schema_v3 import (
    PROOF_STEP_SCORING_SEMANTICS,
    CaseSpecV3,
    CaseValidationError,
    decidable_claims_sha256,
    load_catalog_records,
    normalize_catalog_records,
    proof_subgraph_fingerprint,
    validate_catalog_bindings,
    validate_case,
)
from src.eval.evidence_graph import (
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SupportSpan,
)
from src.tasks.query_renderer_v3 import (
    BlindSemanticReviewRecordV3,
    assert_query_case_alignment,
    build_blind_review_packet,
    render_task,
)
from src.tasks.human_query_pipeline_v3 import (
    HumanQueryReleaseV1,
    artifact_sha256 as query_artifact_sha256,
    validate_human_query_release,
)


CORPUS_REGISTRY_SCHEMA = "frozen_corpus_registry_v1"
REACHABILITY_MANIFEST_SCHEMA = "case_reachability_manifest_v1"
_SEMANTIC_SUPPORT_RELATIONS = {
    EdgeRelation.ASSERTS,
    EdgeRelation.SUPPORTED_BY,
    EdgeRelation.REFUTES,
}


def _canonical_hash(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _records_hash(records: Iterable[Mapping[str, Any]], id_field: str) -> str:
    normalized = [dict(record) for record in records]
    normalized.sort(key=lambda record: str(record.get(id_field) or ""))
    return _canonical_hash(normalized)


def _registry_hash(registry: Mapping[str, Any]) -> str:
    payload = dict(registry)
    if isinstance(payload.get("entries"), list):
        payload["entries"] = sorted(
            [dict(entry) for entry in payload["entries"]],
            key=lambda entry: str(entry.get("registry_id") or entry.get("source_url") or ""),
        )
    if isinstance(payload.get("corpus_urls"), list):
        payload["corpus_urls"] = sorted(payload["corpus_urls"])
    if isinstance(payload.get("urls"), list):
        payload["urls"] = sorted(payload["urls"])
    return _canonical_hash(payload)


def _reachability_manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    if isinstance(payload.get("root_node_ids"), list):
        payload["root_node_ids"] = sorted(payload["root_node_ids"])
    return _canonical_hash(payload)


def _declared_conditions(
    graph: EvidenceGraph,
    node_id: str,
    *,
    semantic_edge: EvidenceEdge | None = None,
) -> set[str]:
    """Return exact graph-authored applicability conditions for one atom."""

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
            raise CaseValidationError(
                f"node {node_id!r} conditions must be a string or string list"
            )
    unknown = sorted(conditions - set(graph.node_by_id))
    if unknown:
        raise CaseValidationError(
            f"node {node_id!r} references unknown conditions: {unknown}"
        )
    wrong_type = sorted(
        condition_id
        for condition_id in conditions
        if graph.node_by_id[condition_id].node_type is not NodeType.CONSTRAINT
    )
    if wrong_type:
        raise CaseValidationError(
            f"node {node_id!r} applicability targets are not constraints: "
            f"{wrong_type}"
        )
    return conditions


def validate_proof_support_bindings(
    case: CaseSpecV3,
    graph: EvidenceGraph,
) -> None:
    """Bind every proof alternative to its proposition in the frozen graph.

    Source role and verifier kind are necessary constraints, but neither proves
    that a page actually supports the proposition.  Formal compilation
    therefore requires a typed semantic edge for every alternative and exact
    applicability-condition agreement.  A typed evidence node may bind to
    itself for the legacy attribute-shaped representation.
    """

    if case.scoring_semantics != PROOF_STEP_SCORING_SEMANTICS:
        return
    nodes = graph.node_by_id
    for step in case.slots:
        if step.type != "evidence":
            continue
        assert step.claim_id is not None
        claim_id = step.claim_id
        if claim_id not in nodes:
            raise CaseValidationError(
                f"proof step {step.step_id} proposition {claim_id!r} is absent "
                "from the frozen evidence graph"
            )
        claim_node = nodes[claim_id]
        assert step.acceptable_support is not None
        declared_relation = step.acceptable_support.support_relation
        for source_id in step.support_source_ids:
            if source_id not in nodes:
                raise CaseValidationError(
                    f"proof step {step.step_id} source {source_id!r} is absent "
                    "from the frozen evidence graph"
                )
            if source_id == claim_id:
                if declared_relation != "SELF":
                    raise CaseValidationError(
                        f"proof step {step.step_id} self-bound source requires "
                        "support_relation=SELF"
                    )
                continue
            if claim_node.node_type is not NodeType.PROPOSITION:
                raise CaseValidationError(
                    f"proof step {step.step_id} separates claim {claim_id!r} "
                    "from its source, so the claim must be a proposition node"
                )
            semantic_edges = [
                edge
                for edge in graph.edges
                if edge.relation.value == declared_relation
                and edge.relation in _SEMANTIC_SUPPORT_RELATIONS
                and {edge.source_id, edge.target_id} == {source_id, claim_id}
                and (
                    edge.relation is not EdgeRelation.ASSERTS
                    or (
                        edge.source_id == source_id
                        and edge.target_id == claim_id
                    )
                )
            ]
            if len(semantic_edges) != 1:
                raise CaseValidationError(
                    f"proof step {step.step_id} support source {source_id!r} "
                    f"must have exactly one {declared_relation} edge "
                    f"to proposition {claim_id!r}; found {len(semantic_edges)}"
                )
            semantic_edge = semantic_edges[0]
            claim_conditions = _declared_conditions(graph, claim_id)
            source_conditions = _declared_conditions(
                graph,
                source_id,
                semantic_edge=semantic_edge,
            )
            if source_conditions != claim_conditions:
                raise CaseValidationError(
                    f"proof step {step.step_id} source {source_id!r} condition "
                    f"scope {sorted(source_conditions)} does not exactly match "
                    f"proposition {claim_id!r} scope {sorted(claim_conditions)}"
                )


def _load_json_or_jsonl(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        rows: list[Any] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CaseValidationError(
                    f"invalid JSON on {path}:{line_number}: {exc}"
                ) from exc
        return rows
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_container(path: str | Path) -> tuple[list[dict[str, Any]], Any]:
    source = Path(path)
    if source.is_dir():
        nodes_path = source / "nodes.jsonl"
        if not nodes_path.is_file():
            raise CaseValidationError(f"catalog directory has no nodes.jsonl: {source}")
        records = load_catalog_records(nodes_path)
        # Optional manifest/container may carry the independent full URL set.
        for name in ("corpus_registry.json", "catalog.json", "manifest.json"):
            candidate = source / name
            if candidate.is_file():
                return records, _load_json_or_jsonl(candidate)
        return records, None
    if not source.is_file():
        raise CaseValidationError(f"evidence catalog does not exist: {source}")
    raw = _load_json_or_jsonl(source)
    return normalize_catalog_records(raw), raw


def _load_support_spans(
    catalog_path: str | Path,
    explicit_path: str | Path | None = None,
) -> list[dict[str, Any]] | None:
    if explicit_path is not None:
        source = Path(explicit_path)
    else:
        catalog = Path(catalog_path)
        source = catalog / "support_spans.jsonl" if catalog.is_dir() else Path("")
    if not source or not source.is_file():
        return None
    raw = _load_json_or_jsonl(source)
    if isinstance(raw, Mapping):
        for key in ("support_spans", "spans", "records"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list) or not all(isinstance(row, Mapping) for row in raw):
        raise CaseValidationError("support-span catalog must be a JSON/JSONL object list")
    return [dict(row) for row in raw]


def _load_graph_edges(
    catalog_path: str | Path,
    explicit_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    if explicit_path is not None:
        source = Path(explicit_path)
    else:
        catalog = Path(catalog_path)
        source = catalog / "edges.jsonl" if catalog.is_dir() else Path("")
    if not source or not source.is_file():
        raise CaseValidationError(
            "formal compile requires evidence graph edges (use --graph-edges)"
        )
    raw = _load_json_or_jsonl(source)
    if isinstance(raw, Mapping):
        for key in ("edges", "records"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list) or not all(isinstance(row, Mapping) for row in raw):
        raise CaseValidationError("evidence graph edges must be a JSON/JSONL object list")
    if not raw:
        raise CaseValidationError("evidence graph edges cannot be empty for formal compile")
    return [dict(row) for row in raw]


def load_reachability_manifest(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise CaseValidationError(f"reachability manifest does not exist: {source}")
    raw = _load_json_or_jsonl(source)
    if not isinstance(raw, Mapping):
        raise CaseValidationError("reachability manifest must be a JSON object")
    return raw


def validate_reachability(
    case: CaseSpecV3,
    *,
    catalog_records: Iterable[Mapping[str, Any]],
    graph_edges: Iterable[Mapping[str, Any]],
    support_span_records: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify every critical evidence node is discoverable from explicit roots."""

    if manifest.get("schema") != REACHABILITY_MANIFEST_SCHEMA:
        raise CaseValidationError(
            f"reachability manifest schema must be {REACHABILITY_MANIFEST_SCHEMA!r}"
        )
    if manifest.get("complete") is not True:
        raise CaseValidationError("reachability manifest must declare complete=true")
    if manifest.get("corpus_snapshot") != case.corpus_snapshot:
        raise CaseValidationError("reachability manifest corpus snapshot mismatch")
    root_ids = manifest.get("root_node_ids")
    if not isinstance(root_ids, list) or not root_ids or not all(
        isinstance(value, str) for value in root_ids
    ):
        raise CaseValidationError(
            "reachability manifest requires non-empty explicit root_node_ids"
        )
    if len(set(root_ids)) != len(root_ids):
        raise CaseValidationError("reachability manifest root_node_ids must be unique")

    records = [dict(record) for record in catalog_records]
    edges = [dict(edge) for edge in graph_edges]
    spans = [dict(span) for span in support_span_records]
    if not edges:
        raise CaseValidationError("formal reachability cannot be proven without graph edges")
    try:
        graph = EvidenceGraph(
            corpus_snapshot=case.corpus_snapshot,
            nodes=tuple(EvidenceNode.from_dict(record) for record in records),
            edges=tuple(EvidenceEdge.from_dict(edge) for edge in edges),
            support_spans=tuple(SupportSpan.from_dict(span) for span in spans),
        )
    except Exception as exc:
        raise CaseValidationError(f"invalid evidence graph for reachability: {exc}") from exc
    expected_hash = manifest.get("evidence_graph_sha256")
    if not isinstance(expected_hash, str) or expected_hash != graph.graph_sha256:
        raise CaseValidationError(
            "reachability manifest evidence_graph_sha256 does not bind the supplied graph"
        )
    validate_proof_support_bindings(case, graph)
    critical_support_source_ids = case.critical_support_source_ids
    critical_set = set(critical_support_source_ids)
    seed_edge_roots = {
        edge.source_id
        for edge in graph.discoverability_edges
        if edge.discovery_method is not None and edge.discovery_method.value == "SEED"
    }
    allowed_roots: set[str] = set(seed_edge_roots)
    for node in graph.nodes:
        if node.node_type.value == "search_result" or node.metadata.get(
            "task_seed"
        ) is True or node.metadata.get("discovery_root_policy") in {
            "task_seed",
            "search_result",
        }:
            allowed_roots.add(node.evidence_id)
    forbidden_critical_roots = sorted(set(root_ids) & critical_set)
    if forbidden_critical_roots:
        raise CaseValidationError(
            "critical evidence cannot be declared as a discovery root: "
            f"{forbidden_critical_roots}"
        )
    invalid_roots = sorted(set(root_ids) - allowed_roots)
    if invalid_roots:
        raise CaseValidationError(
            "reachability roots must be SEARCH_RESULT nodes, TASK_SEED edge sources, "
            f"or nodes with explicit task-seed metadata: {invalid_roots}"
        )
    try:
        reached = graph.require_discoverable(
            critical_support_source_ids,
            root_ids,
            # Formal cases use only the explicit roots declared in the manifest.
            include_seed_roots=False,
            include_search_result_roots=False,
        )
    except Exception as exc:
        raise CaseValidationError(f"critical evidence reachability failed: {exc}") from exc
    return {
        "schema": REACHABILITY_MANIFEST_SCHEMA,
        "evidence_graph_sha256": graph.graph_sha256,
        "root_node_ids": sorted(root_ids),
        "root_source_urls": sorted(
            {graph.node_by_id[root_id].source_url for root_id in root_ids}
        ),
        "critical_evidence_node_ids": critical_support_source_ids,
        "reachable_node_ids": list(reached),
    }


def normalize_corpus_registry(
    payload: Any,
    *,
    expected_snapshot: str,
) -> list[str]:
    """Validate an explicitly complete frozen-corpus URL registry.

    A bare URL list is intentionally insufficient for formal compilation: it
    cannot distinguish a complete registry from a hand-picked task subset.
    The registry must be an object with ``complete: true`` (or
    ``corpus_registry_complete: true``), an exact snapshot stamp, and a URL
    list under ``corpus_urls`` or ``urls``.
    """

    if not isinstance(payload, Mapping):
        raise CaseValidationError(
            "formal corpus registry must be an object declaring completeness"
        )
    if isinstance(payload.get("corpus_registry"), Mapping):
        payload = payload["corpus_registry"]

    # The evidence_graph module's typed registry is complete by construction:
    # version + exact entries + explicit in_corpus=true.  A simpler URL-only
    # manifest must instead say complete=true itself.
    typed_registry = payload.get("version") == CORPUS_REGISTRY_SCHEMA and isinstance(
        payload.get("entries"), list
    )
    complete = typed_registry or payload.get("complete") is True or payload.get(
        "corpus_registry_complete"
    ) is True
    if not complete:
        raise CaseValidationError(
            "corpus registry must be a typed frozen_corpus_registry_v1 or "
            "explicitly declare complete=true"
        )
    schema = payload.get("registry_schema") or payload.get("schema") or payload.get("version")
    if schema is not None and schema != CORPUS_REGISTRY_SCHEMA:
        raise CaseValidationError(
            f"unsupported corpus registry schema {schema!r}; expected {CORPUS_REGISTRY_SCHEMA!r}"
        )
    snapshot = payload.get("corpus_snapshot")
    if snapshot != expected_snapshot:
        raise CaseValidationError(
            f"corpus registry snapshot {snapshot!r} does not match {expected_snapshot!r}"
        )
    urls = payload.get("corpus_urls")
    if urls is None:
        urls = payload.get("urls")
    if typed_registry:
        entries = payload["entries"]
        assert isinstance(entries, list)
        urls = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                raise CaseValidationError(f"corpus registry entry {index} is not an object")
            if entry.get("in_corpus") is not True:
                raise CaseValidationError(
                    f"corpus registry entry {index} must declare in_corpus=true"
                )
            if entry.get("corpus_snapshot") != expected_snapshot:
                raise CaseValidationError(
                    f"corpus registry entry {index} has a different snapshot"
                )
            for field_name in ("source_url", "source_type", "content_sha256", "registry_id"):
                if not isinstance(entry.get(field_name), str) or not entry[field_name]:
                    raise CaseValidationError(
                        f"corpus registry entry {index} lacks {field_name}"
                    )
            urls.append(entry["source_url"])
    if not isinstance(urls, list) or not urls or not all(isinstance(url, str) for url in urls):
        raise CaseValidationError("complete corpus registry requires a non-empty URL list")
    if len(set(urls)) != len(urls):
        raise CaseValidationError("complete corpus registry contains duplicate URLs")
    # Reuse CaseSpec's strict absolute-URL and membership checks by applying the
    # registry to a copy during compile_case below.
    return sorted(urls)


def load_corpus_registry(
    path: str | Path,
    *,
    expected_snapshot: str,
) -> tuple[list[str], Mapping[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise CaseValidationError(f"corpus registry does not exist: {source}")
    raw = _load_json_or_jsonl(source)
    urls = normalize_corpus_registry(raw, expected_snapshot=expected_snapshot)
    assert isinstance(raw, Mapping)
    return urls, raw


def validate_registry_membership(
    case: CaseSpecV3,
    registry: Mapping[str, Any],
) -> None:
    """Cross-check exact type/hash/snapshot when a typed registry is supplied."""

    payload: Mapping[str, Any] = registry
    if isinstance(payload.get("corpus_registry"), Mapping):
        payload = payload["corpus_registry"]
    if payload.get("version") != CORPUS_REGISTRY_SCHEMA:
        # A complete explicit URL allowlist is still an independent R_i
        # membership declaration.  Claim hash/type remain pinned by catalog.
        return
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise CaseValidationError("typed corpus registry requires entries")
    by_url = {
        str(entry.get("source_url")): entry
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("source_url"), str)
    }
    for source in case.evidence_sources:
        entry = by_url.get(source.source_url)
        if entry is None:
            raise CaseValidationError(
                f"evidence URL is not an exact typed registry member: {source.source_url}"
            )
        expected = {
            "source_type": source.source_type,
            "content_sha256": source.content_sha256,
            "corpus_snapshot": source.corpus_snapshot,
            "in_corpus": True,
        }
        mismatches = {
            key: (expected_value, entry.get(key))
            for key, expected_value in expected.items()
            if entry.get(key) != expected_value
        }
        if mismatches:
            raise CaseValidationError(
                f"typed corpus registry identity mismatch for {source.source_url}: {mismatches}"
            )


def validate_draft(payload: Mapping[str, Any] | CaseSpecV3) -> dict[str, Any]:
    """Run structural checks only and explicitly report non-formal status."""

    case = validate_case(payload)
    report = case.validation_report()
    report.update(
        {
            "formal": False,
            "reason": "external evidence catalog and complete corpus registry not checked",
            "case_sha256": case.sha256(),
        }
    )
    return report


def compile_case(
    payload: Mapping[str, Any] | CaseSpecV3,
    *,
    catalog_records: Iterable[Mapping[str, Any]],
    corpus_registry: Mapping[str, Any],
    support_span_records: Iterable[Mapping[str, Any]],
    graph_edges: Iterable[Mapping[str, Any]],
    reachability_manifest: Mapping[str, Any],
    blind_review_record: BlindSemanticReviewRecordV3 | Mapping[str, Any] | None = None,
    query_attempt: int = 1,
    require_query_acceptance: bool = False,
    query_text: str | None = None,
    query_authoring_policy: Literal[
        "legacy_query_path_v1",
        "human_query_pipeline_v1",
    ] = "legacy_query_path_v1",
    query_release_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(private_case_gold, public_rendered_task)`` after formal gates.

    Candidate enumeration may leave the public task in
    ``pending_blind_review`` state.  A publication caller sets
    ``require_query_acceptance=True`` and supplies a human blind-review record;
    the compiler never invents that judgment.
    """

    draft = validate_case(payload)
    if draft.formal_bindings is not None:
        raise CaseValidationError(
            "case draft already contains formal_bindings; formal compiler must create them"
        )
    records = [dict(record) for record in catalog_records]
    spans = [dict(record) for record in support_span_records]
    edges = [dict(record) for record in graph_edges]
    if not spans:
        raise CaseValidationError("formal compile requires support-span records")
    validate_catalog_bindings(
        draft,
        records,
        support_span_records=spans,
    )
    reachability = validate_reachability(
        draft,
        catalog_records=records,
        graph_edges=edges,
        support_span_records=spans,
        manifest=reachability_manifest,
    )
    corpus_urls = normalize_corpus_registry(
        corpus_registry,
        expected_snapshot=draft.corpus_snapshot,
    )
    validate_registry_membership(draft, corpus_registry)
    missing_sources = sorted(
        {source.source_url for source in draft.evidence_sources} - set(corpus_urls)
    )
    if missing_sources:
        raise CaseValidationError(
            f"case evidence URLs are absent from complete corpus registry: {missing_sources}"
        )

    if require_query_acceptance and blind_review_record is None:
        raise CaseValidationError(
            "formal query publication requires a manual blind-review record"
        )
    compiled_payload = (
        draft.protocol_dict()
        if draft.scoring_semantics == PROOF_STEP_SCORING_SEMANTICS
        else draft.to_dict()
    )
    registry_hash = _registry_hash(corpus_registry)
    compiled_payload["corpus_registry_urls"] = corpus_urls
    compiled_payload["corpus_registry_hash"] = registry_hash
    compiled_payload["discovery_root_urls"] = reachability["root_source_urls"]
    compiled_payload["formal_bindings"] = {
        "formal": True,
        "evidence_catalog_sha256": _records_hash(records, "evidence_id"),
        "support_spans_sha256": _records_hash(spans, "support_span_id"),
        "graph_edges_sha256": _records_hash(edges, "edge_id"),
        "evidence_graph_sha256": reachability["evidence_graph_sha256"],
        "corpus_registry_sha256": registry_hash,
        "reachability_manifest_sha256": _reachability_manifest_hash(
            reachability_manifest
        ),
        "decidable_claims_sha256": decidable_claims_sha256(draft),
        "proof_subgraph_sha256": proof_subgraph_fingerprint(draft),
        "query_authoring_policy": query_authoring_policy,
        "query_release_sha256": query_release_sha256,
        "root_node_ids": reachability["root_node_ids"],
        "critical_evidence_node_ids": reachability["critical_evidence_node_ids"],
        "reachable_node_ids": reachability["reachable_node_ids"],
    }
    compiled = CaseSpecV3.from_dict(compiled_payload)
    task = render_task(
        compiled,
        blind_review_record=blind_review_record,
        attempt=query_attempt,
        query_text=query_text,
    )
    assert_query_case_alignment(compiled, task)
    case_output = (
        compiled.protocol_dict()
        if compiled.scoring_semantics == PROOF_STEP_SCORING_SEMANTICS
        else compiled.to_dict()
    )
    return case_output, task


def compile_case_bundle(
    payload: Mapping[str, Any] | CaseSpecV3,
    *,
    catalog_records: Iterable[Mapping[str, Any]],
    corpus_registry: Mapping[str, Any],
    support_span_records: Iterable[Mapping[str, Any]],
    graph_edges: Iterable[Mapping[str, Any]],
    reachability_manifest: Mapping[str, Any],
    blind_review_record: BlindSemanticReviewRecordV3 | Mapping[str, Any] | None = None,
    query_attempt: int = 1,
    require_query_acceptance: bool = False,
    query_text: str | None = None,
    query_authoring_policy: Literal[
        "legacy_query_path_v1",
        "human_query_pipeline_v1",
    ] = "legacy_query_path_v1",
    query_release_sha256: str | None = None,
) -> dict[str, Any]:
    """Compile and return outputs plus non-agent-facing reproducibility hashes."""

    records = [dict(record) for record in catalog_records]
    spans = [dict(record) for record in support_span_records]
    edges = [dict(record) for record in graph_edges]
    case_gold, task = compile_case(
        payload,
        catalog_records=records,
        corpus_registry=corpus_registry,
        support_span_records=spans,
        graph_edges=edges,
        reachability_manifest=reachability_manifest,
        blind_review_record=blind_review_record,
        query_attempt=query_attempt,
        require_query_acceptance=require_query_acceptance,
        query_text=query_text,
        query_authoring_policy=query_authoring_policy,
        query_release_sha256=query_release_sha256,
    )
    reachability = validate_reachability(
        CaseSpecV3.from_dict(case_gold),
        catalog_records=records,
        graph_edges=edges,
        support_span_records=spans,
        manifest=reachability_manifest,
    )
    return {
        "formal": True,
        "case_gold": case_gold,
        "rendered_task": task,
        "validation": {
            **CaseSpecV3.from_dict(case_gold).validation_report(),
            "formal_catalog_validated": True,
            "complete_corpus_registry_validated": True,
            "case_sha256": _canonical_hash(case_gold),
            "catalog_sha256": _records_hash(records, "evidence_id"),
            "support_spans_sha256": _records_hash(spans, "support_span_id"),
            "graph_edges_sha256": _records_hash(edges, "edge_id"),
            "reachability_manifest_sha256": _reachability_manifest_hash(
                reachability_manifest
            ),
            "reachability": reachability,
            "corpus_registry_sha256": _registry_hash(corpus_registry),
            "query_validation": task["query_validation"],
            "query_authoring_policy": query_authoring_policy,
            "query_release_sha256": query_release_sha256,
        },
    }


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", help="candidate case draft JSON")
    parser.add_argument(
        "--validate-draft",
        action="store_true",
        help="only run structural validation; never writes formal outputs",
    )
    parser.add_argument("--evidence-catalog", help="frozen nodes JSON/JSONL or graph directory")
    parser.add_argument(
        "--support-spans",
        help="support spans JSON/JSONL (auto-detected in a graph directory)",
    )
    parser.add_argument(
        "--graph-edges",
        help="evidence graph edges JSON/JSONL (auto-detected in a graph directory)",
    )
    parser.add_argument(
        "--reachability-manifest",
        help="explicit task seed/search-result roots bound to the evidence graph hash",
    )
    parser.add_argument(
        "--corpus-registry",
        help=(
            "complete frozen corpus registry; may be omitted only when the "
            "catalog JSON/container itself declares corpus_urls + complete=true"
        ),
    )
    parser.add_argument("--case-out", "--gold-out", dest="case_out")
    parser.add_argument("--task-out")
    parser.add_argument(
        "--blind-review-record",
        help=(
            "manual blind semantic-alignment JSON record; required when "
            "publishing a proof_steps_v1 task"
        ),
    )
    parser.add_argument(
        "--review-packet-out",
        help=(
            "write a GeneratorView-only blind-review packet and stop; this "
            "never writes formal case/task outputs"
        ),
    )
    parser.add_argument(
        "--query-attempt",
        type=int,
        default=1,
        help="query attempt number under the frozen three-attempt policy",
    )
    parser.add_argument(
        "--query-file",
        help=(
            "UTF-8 natural query generated only from GeneratorView; when omitted, "
            "use the deterministic canonical renderer"
        ),
    )
    parser.add_argument(
        "--query-release-certificate",
        help=(
            "human_query_pipeline_v1 certificate containing the approved graph "
            "annotation, human few-shot provenance, registered API generation "
            "record, and blind human review; this is the formal authoring path"
        ),
    )
    parser.add_argument("--print", dest="print_payload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    draft_path = Path(args.draft)
    if not draft_path.is_file():
        raise SystemExit(f"draft does not exist: {draft_path}")
    raw_draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(raw_draft, Mapping):
        raise SystemExit("case draft must be a JSON object")

    query_release: HumanQueryReleaseV1 | None = None
    query_attempt = args.query_attempt
    query_text: str | None = None
    if args.query_release_certificate:
        if args.query_file or args.blind_review_record:
            raise SystemExit(
                "--query-release-certificate cannot be combined with "
                "--query-file or --blind-review-record"
            )
        release_path = Path(args.query_release_certificate)
        if not release_path.is_file():
            raise SystemExit(f"query release certificate does not exist: {release_path}")
        try:
            raw_release = json.loads(release_path.read_text(encoding="utf-8"))
            if not isinstance(raw_release, Mapping):
                raise CaseValidationError(
                    "query release certificate must be a JSON object"
                )
            query_release = validate_human_query_release(raw_release, raw_draft)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            print(f"case compilation failed: invalid query release: {exc}", file=sys.stderr)
            return 2
        query_text = query_release.query
        query_attempt = query_release.generation.attempt
    elif args.query_file:
        query_path = Path(args.query_file)
        if not query_path.is_file():
            raise SystemExit(f"query file does not exist: {query_path}")
        query_text = query_path.read_text(encoding="utf-8")
        if query_text.endswith("\n"):
            query_text = query_text[:-1]

    try:
        if args.validate_draft:
            if args.case_out or args.task_out or query_release is not None:
                raise CaseValidationError(
                    "--validate-draft cannot write outputs or consume a query release"
                )
            report = validate_draft(raw_draft)
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.review_packet_out:
            if (
                args.case_out
                or args.task_out
                or args.blind_review_record
                or query_release is not None
            ):
                raise CaseValidationError(
                    "--review-packet-out cannot write formal outputs or consume "
                    "a review/release"
                )
            case = validate_case(raw_draft)
            packet = build_blind_review_packet(
                case,
                attempt=query_attempt,
                query_text=query_text,
            )
            _write_json(args.review_packet_out, packet)
            print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if not args.evidence_catalog:
            raise CaseValidationError("formal compile requires --evidence-catalog")
        if not args.case_out or not args.task_out:
            raise CaseValidationError("formal compile requires --case-out and --task-out")

        case = validate_case(raw_draft)
        records, catalog_container = _catalog_container(args.evidence_catalog)
        spans = _load_support_spans(args.evidence_catalog, args.support_spans)
        if spans is None:
            raise CaseValidationError(
                "formal compile requires support spans (use --support-spans)"
            )
        edges = _load_graph_edges(args.evidence_catalog, args.graph_edges)
        if not args.reachability_manifest:
            raise CaseValidationError("formal compile requires --reachability-manifest")
        reachability_manifest = load_reachability_manifest(args.reachability_manifest)
        if query_release is not None and (
            reachability_manifest.get("evidence_graph_sha256")
            != query_release.evidence_graph_sha256
        ):
            raise CaseValidationError(
                "query release certificate binds a different evidence graph than "
                "the formal reachability manifest"
            )
        if args.corpus_registry:
            _, registry_payload = load_corpus_registry(
                args.corpus_registry,
                expected_snapshot=case.corpus_snapshot,
            )
        elif isinstance(catalog_container, Mapping):
            # A catalog container can serve both purposes only with the same
            # explicit completeness and snapshot contract.
            normalize_corpus_registry(
                catalog_container,
                expected_snapshot=case.corpus_snapshot,
            )
            registry_payload = catalog_container
        else:
            raise CaseValidationError(
                "formal compile requires --corpus-registry or a catalog container "
                "with complete frozen corpus_urls"
            )

        blind_review: Mapping[str, Any] | None = None
        if query_release is not None:
            blind_review = query_release.blind_review.review.model_dump(
                mode="json", by_alias=True
            )
        elif args.blind_review_record:
            review_path = Path(args.blind_review_record)
            if not review_path.is_file():
                raise CaseValidationError(
                    f"blind review record does not exist: {review_path}"
                )
            raw_review = json.loads(review_path.read_text(encoding="utf-8"))
            if not isinstance(raw_review, Mapping):
                raise CaseValidationError("blind review record must be a JSON object")
            blind_review = raw_review
        require_query_acceptance = (
            case.scoring_semantics == PROOF_STEP_SCORING_SEMANTICS
        )
        if require_query_acceptance and blind_review is None:
            raise CaseValidationError(
                "proof_steps_v1 publication requires --blind-review-record; "
                "use --review-packet-out for the manual review step"
            )

        bundle = compile_case_bundle(
            case,
            catalog_records=records,
            corpus_registry=registry_payload,
            support_span_records=spans,
            graph_edges=edges,
            reachability_manifest=reachability_manifest,
            blind_review_record=blind_review,
            query_attempt=query_attempt,
            require_query_acceptance=require_query_acceptance,
            query_text=query_text,
            query_authoring_policy=(
                "human_query_pipeline_v1"
                if query_release is not None
                else "legacy_query_path_v1"
            ),
            query_release_sha256=(
                query_artifact_sha256(query_release)
                if query_release is not None
                else None
            ),
        )
        _write_json(args.case_out, bundle["case_gold"])
        _write_json(args.task_out, bundle["rendered_task"])
        summary = {
            "formal": True,
            "task_id": case.task_id,
            "case_out": str(Path(args.case_out)),
            "task_out": str(Path(args.task_out)),
            "query_authoring_policy": (
                "human_query_pipeline_v1"
                if query_release is not None
                else "legacy_query_path_v1"
            ),
            "query_release_sha256": (
                bundle["validation"]["query_release_sha256"]
            ),
            "validation": bundle["validation"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        if args.print_payload:
            print(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (CaseValidationError, ValueError, TypeError) as exc:
        print(f"case compilation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CORPUS_REGISTRY_SCHEMA",
    "REACHABILITY_MANIFEST_SCHEMA",
    "compile_case",
    "compile_case_bundle",
    "load_corpus_registry",
    "load_reachability_manifest",
    "main",
    "normalize_corpus_registry",
    "validate_reachability",
    "validate_draft",
    "validate_registry_membership",
]
