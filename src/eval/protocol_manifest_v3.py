"""Formal, content-addressed protocol manifests for DRA v3 panels.

The evidence-graph manifest commits the graph and the complete frozen-corpus
registry.  A protocol manifest adds the exact compiled case files and the
exact public rendered tasks to that commitment.  It contains no
timestamps or filesystem paths, so the same artifact set produces identical
bytes regardless of input order or checkout location.

Case hashes are hashes of the exact file bytes, not hashes of a normalized
model dump.  Reformatting a compiled case is therefore protocol drift and must
be reviewed and re-stamped rather than silently accepted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from src.eval.case_schema_v3 import (
    CaseSpecV3,
    CaseValidationError,
    SUPPORTED_MOTIFS,
    proof_subgraph_fingerprint,
    validate_catalog_bindings,
)
from src.eval.evidence_graph import (
    EDGES_FILENAME,
    EVIDENCE_GRAPH_MANIFEST_VERSION,
    NODES_FILENAME,
    SUPPORT_SPANS_FILENAME,
    DiscoveryMethod,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeType,
    SupportSpan,
    canonical_json_bytes,
    load_corpus_registry,
    load_json,
    load_jsonl,
    save_json,
    verify_evidence_graph_manifest,
)
from src.eval.protocol_v3 import protocol_stamp, validate_protocol
from src.tasks.query_renderer_v3 import (
    QueryAcceptanceRecordV3,
    assert_query_accepted,
    assert_query_case_alignment,
    build_hard_rule_pass_record,
    render_task,
    validate_blind_semantic_review,
)


PROTOCOL_MANIFEST_SCHEMA = "dra_v3_protocol_manifest_v1"
SCORER_IMPLEMENTATION_FILES = (
    "src/eval/case_schema_v3.py",
    "src/eval/evidence_graph.py",
    "src/eval/observation_ledger.py",
    "src/eval/protocol_manifest_v3.py",
    "src/eval/protocol_v3.py",
    "src/eval/slot_scorer.py",
    "src/tasks/query_renderer_v3.py",
    "src/verifiers/citation_format.py",
)
_SHA256_CHARS = frozenset("0123456789abcdef")
_TOP_LEVEL_FIELDS = {
    "schema",
    "protocols",
    "task_ids",
    "task_clusters",
    "task_contracts",
    "proof_subgraph_fingerprints",
    "case_hashes",
    "public_task_hashes",
    "evidence_graph_artifact",
    "scorer_implementation_sha256",
    "manifest_sha256",
}
_GRAPH_FIELDS = {
    "manifest_schema",
    "evidence_graph_hash",
    "corpus_registry_hash",
    "graph_corpus_hash",
    "counts",
}
_GRAPH_COUNT_FIELDS = {"registry_entries", "nodes", "edges", "support_spans"}
_TASK_CONTRACT_FIELDS = {
    "cluster_id",
    "motif",
    "declared_proof_depth",
    "minimum_reasoning_depth",
    "required_research_subgoals",
    "cross_source_bridges",
    "single_page_sufficient",
}
# Historical ``verified_slots_v1`` manifests used this motif vocabulary.  The
# proof-step redesign deliberately introduced a new vocabulary, but old formal
# manifests remain replay artifacts and therefore must continue to validate.
_LEGACY_SUPPORTED_MOTIFS = {
    "constraint_filter",
    "mechanism_application",
    "claim_reconciliation",
    "comparative_tradeoff",
    "counterexample_revision",
}


class ProtocolManifestV3Error(ValueError):
    """Raised when a panel cannot be bound to one exact formal protocol."""


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_CHARS for character in value)
    )


def sha256_file(path: str | Path) -> str:
    """Hash the exact bytes of one regular artifact file."""

    source = Path(path)
    if not source.is_file():
        raise ProtocolManifestV3Error(f"artifact is not a file: {source}")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ProtocolManifestV3Error(f"cannot read artifact {source}: {exc}") from exc
    return digest.hexdigest()


def scorer_implementation_sha256(root: str | Path | None = None) -> str:
    """Hash the exact local code bytes that define formal v3 scoring.

    The fixed file list is part of the protocol contract.  Any change to the
    case validator, ledger semantics, protocol validator, scorer, or citation
    parser therefore invalidates an old formal manifest and requires a new
    stamp instead of silently mixing implementations under one semantics name.
    """

    repository = (
        Path(root)
        if root is not None
        else Path(__file__).resolve().parents[2]
    )
    hashes: dict[str, str] = {}
    for relative_path in SCORER_IMPLEMENTATION_FILES:
        source = repository / relative_path
        if not source.is_file():
            raise ProtocolManifestV3Error(
                f"formal scorer implementation file is missing: {relative_path}"
            )
        hashes[relative_path] = sha256_file(source)
    return hashlib.sha256(canonical_json_bytes(hashes)).hexdigest()


def _self_hash(payload: Mapping[str, Any]) -> str:
    without_self = {
        key: value for key, value in payload.items() if key != "manifest_sha256"
    }
    return hashlib.sha256(canonical_json_bytes(without_self)).hexdigest()


def _records_hash(records: Iterable[Mapping[str, Any]], id_field: str) -> str:
    normalized = [dict(record) for record in records]
    normalized.sort(key=lambda record: str(record.get(id_field) or ""))
    return hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()


def _path_list(
    paths: Iterable[str | Path] | str | Path | None,
) -> list[Path]:
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ProtocolManifestV3Error(f"{label} is not a file: {path}")
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise ProtocolManifestV3Error(f"{label} must be a JSON object: {path}")
    return raw


def _load_hashed_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    """Load and hash one stable file, rejecting concurrent artifact changes."""

    before = sha256_file(path)
    raw = _load_object(path, label=label)
    after = sha256_file(path)
    if before != after:
        raise ProtocolManifestV3Error(
            f"{label} changed while the protocol manifest was being built: {path}"
        )
    return raw, before


def _load_compiled_cases(
    case_paths: Iterable[str | Path] | str | Path,
    *,
    corpus_snapshot: str,
    evidence_graph_hash: str,
    corpus_registry_hash: str,
    corpus_urls: set[str],
    graph: EvidenceGraph,
    catalog_records: list[dict[str, Any]],
    support_span_records: list[dict[str, Any]],
    graph_edge_records: list[dict[str, Any]],
) -> tuple[dict[str, CaseSpecV3], dict[str, str]]:
    paths = _path_list(case_paths)
    if not paths:
        raise ProtocolManifestV3Error("at least one compiled CaseSpecV3 JSON is required")

    cases: dict[str, CaseSpecV3] = {}
    case_hashes: dict[str, str] = {}
    for path in paths:
        raw, exact_hash = _load_hashed_object(path, label="compiled case")
        required_formal_fields = (
            "formal_bindings",
            "corpus_registry_urls",
            "corpus_registry_hash",
            "discovery_root_urls",
        )
        missing_formal = [
            field_name
            for field_name in required_formal_fields
            if raw.get(field_name) is None
        ]
        if missing_formal:
            raise ProtocolManifestV3Error(
                f"case {raw.get('task_id', path.name)} is not formally compiled: "
                f"missing {missing_formal}"
            )
        if raw.get("corpus_snapshot") != corpus_snapshot:
            raise ProtocolManifestV3Error(
                f"case {raw.get('task_id', path.name)} snapshot "
                f"{raw.get('corpus_snapshot')!r} does not match graph snapshot "
                f"{corpus_snapshot!r}"
            )
        try:
            case = CaseSpecV3.from_dict(raw)
        except Exception as exc:
            raise ProtocolManifestV3Error(f"invalid CaseSpecV3 {path}: {exc}") from exc
        if case.task_id in cases:
            raise ProtocolManifestV3Error(
                f"duplicate compiled case task_id: {case.task_id}"
            )
        if case.formal_bindings is None:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} is not formally compiled: formal_bindings missing"
            )
        if case.corpus_registry_urls is None:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} is not formally compiled: "
                "corpus_registry_urls missing"
            )
        if case.corpus_snapshot != corpus_snapshot:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} snapshot {case.corpus_snapshot!r} does not match "
                f"graph snapshot {corpus_snapshot!r}"
            )
        bindings = case.formal_bindings
        if bindings.evidence_graph_sha256 != evidence_graph_hash:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} was compiled against a different evidence graph"
            )
        if bindings.corpus_registry_sha256 != corpus_registry_hash:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} was compiled against a different corpus registry"
            )
        if case.corpus_registry_hash != corpus_registry_hash:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} top-level corpus_registry_hash does not match "
                "the typed registry"
            )

        expected_binding_hashes = {
            "evidence_catalog_sha256": _records_hash(
                catalog_records, "evidence_id"
            ),
            "support_spans_sha256": _records_hash(
                support_span_records, "support_span_id"
            ),
            "graph_edges_sha256": _records_hash(graph_edge_records, "edge_id"),
        }
        for field_name, expected_hash in expected_binding_hashes.items():
            if getattr(bindings, field_name) != expected_hash:
                raise ProtocolManifestV3Error(
                    f"case {case.task_id} formal_bindings.{field_name} does not "
                    "match the verified graph artifact"
                )

        case_urls = set(case.corpus_registry_urls)
        if case_urls != corpus_urls:
            missing = sorted(corpus_urls - case_urls)
            extra = sorted(case_urls - corpus_urls)
            raise ProtocolManifestV3Error(
                f"case {case.task_id} corpus_registry_urls is not the exact complete "
                "registry; "
                f"missing={missing}, extra={extra}"
            )
        try:
            validate_catalog_bindings(
                case,
                catalog_records,
                support_span_records=support_span_records,
            )
        except CaseValidationError as exc:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} no longer matches the typed evidence graph: {exc}"
            ) from exc

        critical_node_ids = case.critical_support_source_ids
        root_ids = list(bindings.root_node_ids)
        if root_ids != sorted(root_ids):
            raise ProtocolManifestV3Error(
                f"case {case.task_id} formal discovery roots are not canonical"
            )
        critical_root_ids = sorted(set(root_ids) & set(critical_node_ids))
        if critical_root_ids:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} declares critical evidence as discovery roots: "
                f"{critical_root_ids}"
            )
        seed_edge_roots = {
            edge.source_id
            for edge in graph.discoverability_edges
            if edge.discovery_method is DiscoveryMethod.TASK_SEED
        }
        allowed_roots = set(seed_edge_roots)
        for node in graph.nodes:
            if (
                node.node_type is NodeType.SEARCH_RESULT
                or node.metadata.get("task_seed") is True
                or node.metadata.get("discovery_root_policy")
                in {"task_seed", "search_result"}
            ):
                allowed_roots.add(node.evidence_id)
        invalid_roots = sorted(set(root_ids) - allowed_roots)
        if invalid_roots:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} contains unlicensed discovery roots: "
                f"{invalid_roots}"
            )
        try:
            reached = graph.require_discoverable(
                critical_node_ids,
                root_ids,
                include_seed_roots=False,
                include_search_result_roots=False,
            )
        except Exception as exc:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} critical evidence is not reachable: {exc}"
            ) from exc
        if list(bindings.reachable_node_ids) != list(reached):
            raise ProtocolManifestV3Error(
                f"case {case.task_id} formal reachable_node_ids does not equal the "
                "recomputed discovery closure"
            )
        root_urls = sorted(
            {graph.node_by_id[root_id].source_url for root_id in root_ids}
        )
        if case.discovery_root_urls != root_urls:
            raise ProtocolManifestV3Error(
                f"case {case.task_id} discovery_root_urls does not match its licensed "
                "root nodes"
            )

        cases[case.task_id] = case
        case_hashes[case.task_id] = exact_hash
    return cases, {task_id: case_hashes[task_id] for task_id in sorted(case_hashes)}


def _load_public_tasks(
    public_task_paths: Iterable[str | Path] | str | Path | None,
    cases: Mapping[str, CaseSpecV3],
) -> dict[str, str]:
    paths = _path_list(public_task_paths)
    if not paths:
        raise ProtocolManifestV3Error(
            "formal protocol manifest requires one exact public task per case"
        )

    hashes: dict[str, str] = {}
    for path in paths:
        task, exact_hash = _load_hashed_object(path, label="public task")
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ProtocolManifestV3Error(f"public task has no task_id: {path}")
        if task_id in hashes:
            raise ProtocolManifestV3Error(f"duplicate public task task_id: {task_id}")
        case = cases.get(task_id)
        if case is None:
            raise ProtocolManifestV3Error(
                f"public task {task_id} has no corresponding compiled case"
            )
        if case.scoring_semantics == "proof_steps_v1":
            query = task.get("intent")
            if not isinstance(query, str) or not query:
                raise ProtocolManifestV3Error(
                    f"public task {task_id} has no query text"
                )
            validation = task.get("query_validation")
            if not isinstance(validation, Mapping):
                raise ProtocolManifestV3Error(
                    f"public task {task_id} lacks query acceptance evidence"
                )
            try:
                acceptance = QueryAcceptanceRecordV3.model_validate(
                    dict(validation)
                )
                assert_query_accepted(acceptance)
                expected_hard_rules = build_hard_rule_pass_record(
                    case,
                    query,
                    attempt=acceptance.attempt,
                )
                if acceptance.hard_rules != expected_hard_rules:
                    raise ProtocolManifestV3Error(
                        "stored hard-rule record does not bind the exact public query"
                    )
                validate_blind_semantic_review(
                    case,
                    query,
                    acceptance.blind_semantic_alignment,
                )
                expected = render_task(
                    case,
                    query_text=query,
                    blind_review_record=acceptance.blind_semantic_alignment,
                    attempt=acceptance.attempt,
                )
            except Exception as exc:
                raise ProtocolManifestV3Error(
                    f"public task {task_id} query was not accepted: {exc}"
                ) from exc
            comparable_task = {
                key: value for key, value in task.items() if key != "query_validation"
            }
            comparable_expected = {
                key: value for key, value in expected.items() if key != "query_validation"
            }
        else:
            expected = render_task(case)
            comparable_task = task
            comparable_expected = expected
        if comparable_task != comparable_expected:
            missing = sorted(set(expected) - set(task))
            extra = sorted(set(task) - set(expected))
            changed = sorted(
                key
                for key in set(task) & set(expected)
                if key != "query_validation" or case.scoring_semantics != "proof_steps_v1"
                if task.get(key) != expected.get(key)
            )
            raise ProtocolManifestV3Error(
                f"public task {task_id} is not the exact leak-free rendering; "
                f"missing={missing}, extra={extra}, changed={changed}"
            )
        try:
            assert_query_case_alignment(case, task)
        except Exception as exc:
            raise ProtocolManifestV3Error(
                f"public task {task_id} is not query-case aligned: {exc}"
            ) from exc
        hashes[task_id] = exact_hash

    missing = sorted(set(cases) - set(hashes))
    if missing:
        raise ProtocolManifestV3Error(
            "public tasks were supplied but do not cover the complete case set; "
            f"missing={missing}"
        )
    return {task_id: hashes[task_id] for task_id in sorted(hashes)}


def build_v3_protocol_manifest(
    graph_directory: str | Path,
    case_paths: Iterable[str | Path] | str | Path,
    *,
    public_task_paths: Iterable[str | Path] | str | Path | None = None,
) -> dict[str, Any]:
    """Build a formal protocol manifest from already-frozen artifacts.

    ``verify_evidence_graph_manifest`` is intentionally the first gate.  The
    protocol builder never blesses a loose nodes file or a case-local URL list
    as a frozen corpus.
    """

    graph_directory = Path(graph_directory)
    graph_manifest = verify_evidence_graph_manifest(graph_directory)
    registry = load_corpus_registry(graph_directory)
    corpus_snapshot = str(graph_manifest["corpus_snapshot"])
    evidence_graph_hash = str(graph_manifest["evidence_graph_hash"])
    corpus_registry_hash = str(graph_manifest["corpus_registry_hash"])
    if registry.corpus_snapshot != corpus_snapshot:
        raise ProtocolManifestV3Error(
            "typed corpus registry snapshot does not match graph manifest"
        )
    if registry.corpus_sha256 != corpus_registry_hash:
        raise ProtocolManifestV3Error(
            "typed corpus registry hash does not match graph manifest"
        )

    catalog_records = load_jsonl(graph_directory / NODES_FILENAME)
    support_span_records = load_jsonl(graph_directory / SUPPORT_SPANS_FILENAME)
    graph_edge_records = load_jsonl(graph_directory / EDGES_FILENAME)
    try:
        graph = EvidenceGraph(
            corpus_snapshot=corpus_snapshot,
            nodes=tuple(EvidenceNode.from_dict(record) for record in catalog_records),
            edges=tuple(EvidenceEdge.from_dict(record) for record in graph_edge_records),
            support_spans=tuple(
                SupportSpan.from_dict(record) for record in support_span_records
            ),
        )
    except Exception as exc:
        raise ProtocolManifestV3Error(
            f"verified graph records could not be reconstructed: {exc}"
        ) from exc
    if graph.graph_sha256 != evidence_graph_hash:
        raise ProtocolManifestV3Error(
            "reconstructed evidence graph hash does not match its verified manifest"
        )
    registry_urls = {entry.source_url for entry in registry.entries}
    cases, case_hashes = _load_compiled_cases(
        case_paths,
        corpus_snapshot=corpus_snapshot,
        evidence_graph_hash=evidence_graph_hash,
        corpus_registry_hash=corpus_registry_hash,
        corpus_urls=registry_urls,
        graph=graph,
        catalog_records=catalog_records,
        support_span_records=support_span_records,
        graph_edge_records=graph_edge_records,
    )
    task_ids = sorted(cases)
    scoring_semantics_values = {
        str(case.scoring_semantics) for case in cases.values()
    }
    if len(scoring_semantics_values) != 1:
        raise ProtocolManifestV3Error(
            "compiled cases must use one scoring_semantics per protocol manifest"
        )
    scoring_semantics = next(iter(scoring_semantics_values))
    public_task_hashes = _load_public_tasks(public_task_paths, cases)
    protocols = protocol_stamp(
        corpus_snapshot=corpus_snapshot,
        task_ids=task_ids,
        case_hashes=case_hashes,
        public_task_hashes=public_task_hashes,
        evidence_graph_hash=evidence_graph_hash,
        corpus_registry_hash=corpus_registry_hash,
        scoring_semantics=scoring_semantics,
    )
    counts = graph_manifest["counts"]
    if not isinstance(counts, Mapping):
        raise ProtocolManifestV3Error("verified graph manifest has invalid counts")
    payload: dict[str, Any] = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": protocols,
        "task_ids": task_ids,
        "task_clusters": {
            task_id: cases[task_id].cluster_id for task_id in task_ids
        },
        "task_contracts": {
            task_id: {
                "cluster_id": cases[task_id].cluster_id,
                "motif": cases[task_id].motif,
                "declared_proof_depth": cases[task_id].difficulty.proof_depth,
                "minimum_reasoning_depth": cases[task_id].minimum_reasoning_depth,
                "required_research_subgoals": len(
                    cases[task_id].research_subgoals
                ),
                "cross_source_bridges": cases[task_id].cross_source_bridge_count,
                "single_page_sufficient": cases[
                    task_id
                ].oracle.single_page_sufficient,
            }
            for task_id in task_ids
        },
        "proof_subgraph_fingerprints": {
            task_id: proof_subgraph_fingerprint(cases[task_id])
            for task_id in task_ids
        },
        "case_hashes": case_hashes,
        "public_task_hashes": public_task_hashes,
        "scorer_implementation_sha256": scorer_implementation_sha256(),
        "evidence_graph_artifact": {
            "manifest_schema": graph_manifest["version"],
            "evidence_graph_hash": evidence_graph_hash,
            "corpus_registry_hash": corpus_registry_hash,
            "graph_corpus_hash": graph_manifest["graph_corpus_hash"],
            "counts": dict(counts),
        },
    }
    payload["manifest_sha256"] = _self_hash(payload)
    return validate_v3_protocol_manifest(payload)


def validate_v3_protocol_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a manifest's schema, protocol stamp, and self-hash."""

    if not isinstance(manifest, Mapping):
        raise ProtocolManifestV3Error("protocol manifest must be a JSON object")
    raw = dict(manifest)
    if set(raw) != _TOP_LEVEL_FIELDS:
        missing = sorted(_TOP_LEVEL_FIELDS - set(raw))
        extra = sorted(set(raw) - _TOP_LEVEL_FIELDS)
        raise ProtocolManifestV3Error(
            f"protocol manifest fields are not exact; missing={missing}, extra={extra}"
        )
    if raw["schema"] != PROTOCOL_MANIFEST_SCHEMA:
        raise ProtocolManifestV3Error(
            f"protocol manifest schema must be {PROTOCOL_MANIFEST_SCHEMA!r}"
        )
    claimed_self_hash = raw["manifest_sha256"]
    if not _is_sha256(claimed_self_hash):
        raise ProtocolManifestV3Error("manifest_sha256 must be lowercase SHA-256")
    expected_self_hash = _self_hash(raw)
    if claimed_self_hash != expected_self_hash:
        raise ProtocolManifestV3Error(
            "manifest_sha256 does not match the protocol manifest payload"
        )
    scorer_hash = raw["scorer_implementation_sha256"]
    if not _is_sha256(scorer_hash):
        raise ProtocolManifestV3Error(
            "scorer_implementation_sha256 must be lowercase SHA-256"
        )
    current_scorer_hash = scorer_implementation_sha256()
    if scorer_hash != current_scorer_hash:
        raise ProtocolManifestV3Error(
            "formal scorer implementation bytes have drifted; rebuild and "
            "re-stamp the protocol manifest"
        )

    task_ids = raw["task_ids"]
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or any(not isinstance(task_id, str) or not task_id for task_id in task_ids)
    ):
        raise ProtocolManifestV3Error("task_ids must be a non-empty string list")
    if task_ids != sorted(set(task_ids)):
        raise ProtocolManifestV3Error("task_ids must be unique and sorted")

    case_hashes = raw["case_hashes"]
    task_clusters = raw["task_clusters"]
    task_contracts = raw["task_contracts"]
    proof_fingerprints = raw["proof_subgraph_fingerprints"]
    public_hashes = raw["public_task_hashes"]
    if not isinstance(case_hashes, Mapping) or set(case_hashes) != set(task_ids):
        raise ProtocolManifestV3Error(
            "case_hashes keys must exactly equal the declared task_ids"
        )
    if any(not _is_sha256(value) for value in case_hashes.values()):
        raise ProtocolManifestV3Error("case_hashes values must be lowercase SHA-256")
    if not isinstance(task_clusters, Mapping) or set(task_clusters) != set(task_ids):
        raise ProtocolManifestV3Error(
            "task_clusters keys must exactly equal the declared task_ids"
        )
    if any(
        not isinstance(value, str) or not value for value in task_clusters.values()
    ):
        raise ProtocolManifestV3Error("task_clusters values must be non-empty strings")
    if not isinstance(proof_fingerprints, Mapping) or set(proof_fingerprints) != set(
        task_ids
    ):
        raise ProtocolManifestV3Error(
            "proof_subgraph_fingerprints keys must exactly equal the declared task_ids"
        )
    if any(not _is_sha256(value) for value in proof_fingerprints.values()):
        raise ProtocolManifestV3Error(
            "proof_subgraph_fingerprints values must be lowercase SHA-256"
        )
    clusters_by_fingerprint: dict[str, set[str]] = {}
    for task_id, fingerprint in proof_fingerprints.items():
        clusters_by_fingerprint.setdefault(str(fingerprint), set()).add(
            str(task_clusters[task_id])
        )
    split_fingerprints = {
        fingerprint: sorted(clusters)
        for fingerprint, clusters in clusters_by_fingerprint.items()
        if len(clusters) > 1
    }
    if split_fingerprints:
        raise ProtocolManifestV3Error(
            "identical proof subgraphs cannot be split across cluster_ids: "
            f"{split_fingerprints}"
        )
    if not isinstance(task_contracts, Mapping) or set(task_contracts) != set(task_ids):
        raise ProtocolManifestV3Error(
            "task_contracts keys must exactly equal the declared task_ids"
        )
    protocols = raw["protocols"]
    if not isinstance(protocols, Mapping):
        raise ProtocolManifestV3Error("protocols must be an object")
    scoring_semantics = protocols.get("scoring_semantics")
    # During the dual-path migration, newly serialized legacy cases may carry
    # the clearer proof-motif labels while historical legacy manifests retain
    # their original labels.  Both are replay-safe only on the legacy path;
    # proof_steps_v1 accepts solely the new frozen vocabulary.
    allowed_motifs = (
        SUPPORTED_MOTIFS
        if scoring_semantics == "proof_steps_v1"
        else SUPPORTED_MOTIFS | _LEGACY_SUPPORTED_MOTIFS
    )
    for task_id, contract in task_contracts.items():
        if not isinstance(contract, Mapping) or set(contract) != _TASK_CONTRACT_FIELDS:
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] fields do not match the formal schema"
            )
        if contract["cluster_id"] != task_clusters[task_id]:
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] cluster_id disagrees with task_clusters"
            )
        if contract["motif"] not in allowed_motifs:
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] motif is not a supported proof motif"
            )
        for field_name in ("declared_proof_depth", "minimum_reasoning_depth"):
            if type(contract[field_name]) is not int or contract[field_name] < 2:
                raise ProtocolManifestV3Error(
                    f"task_contracts[{task_id}].{field_name} must be at least 2"
                )
        if (
            type(contract["required_research_subgoals"]) is not int
            or contract["required_research_subgoals"] < 4
        ):
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] must have at least four research subgoals"
            )
        if (
            type(contract["cross_source_bridges"]) is not int
            or contract["cross_source_bridges"] < 2
        ):
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] must have at least two cross-source bridges"
            )
        if contract["single_page_sufficient"] is not False:
            raise ProtocolManifestV3Error(
                f"task_contracts[{task_id}] must reject single-page-sufficient cases"
            )
    if not isinstance(public_hashes, Mapping):
        raise ProtocolManifestV3Error("public_task_hashes must be an object")
    if set(public_hashes) != set(task_ids):
        raise ProtocolManifestV3Error(
            "public_task_hashes must cover every declared task_id"
        )
    if any(not _is_sha256(value) for value in public_hashes.values()):
        raise ProtocolManifestV3Error(
            "public_task_hashes values must be lowercase SHA-256"
        )

    graph = raw["evidence_graph_artifact"]
    if not isinstance(graph, Mapping) or set(graph) != _GRAPH_FIELDS:
        raise ProtocolManifestV3Error(
            f"evidence_graph_artifact fields must be exactly {sorted(_GRAPH_FIELDS)}"
        )
    if graph["manifest_schema"] != EVIDENCE_GRAPH_MANIFEST_VERSION:
        raise ProtocolManifestV3Error("evidence graph manifest schema mismatch")
    for field_name in (
        "evidence_graph_hash",
        "corpus_registry_hash",
        "graph_corpus_hash",
    ):
        if not _is_sha256(graph[field_name]):
            raise ProtocolManifestV3Error(
                f"evidence_graph_artifact.{field_name} must be lowercase SHA-256"
            )
    counts = graph["counts"]
    if not isinstance(counts, Mapping) or set(counts) != _GRAPH_COUNT_FIELDS:
        raise ProtocolManifestV3Error("evidence graph counts are incomplete")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ProtocolManifestV3Error(
            "evidence graph counts must be non-negative integers"
        )

    try:
        validate_protocol(protocols, formal=True)
    except ValueError as exc:
        raise ProtocolManifestV3Error(str(exc)) from exc
    expected_protocols = protocol_stamp(
        corpus_snapshot=str(protocols.get("corpus_snapshot") or ""),
        task_ids=task_ids,
        case_hashes={str(key): str(value) for key, value in case_hashes.items()},
        public_task_hashes={
            str(key): str(value) for key, value in public_hashes.items()
        },
        evidence_graph_hash=str(graph["evidence_graph_hash"]),
        corpus_registry_hash=str(graph["corpus_registry_hash"]),
        scoring_semantics=str(protocols.get("scoring_semantics") or ""),
    )
    if dict(protocols) != expected_protocols:
        raise ProtocolManifestV3Error(
            "protocols block does not exactly bind the declared graph, registry, and cases"
        )

    return raw


def save_v3_protocol_manifest(
    manifest: Mapping[str, Any], path: str | Path
) -> None:
    """Validate and atomically save canonical protocol-manifest bytes."""

    save_json(path, validate_v3_protocol_manifest(manifest))


def write_v3_protocol_manifest(
    graph_directory: str | Path,
    case_paths: Iterable[str | Path] | str | Path,
    output_path: str | Path,
    *,
    public_task_paths: Iterable[str | Path] | str | Path | None = None,
) -> dict[str, Any]:
    """Build and save a formal manifest, returning the validated object."""

    manifest = build_v3_protocol_manifest(
        graph_directory,
        case_paths,
        public_task_paths=public_task_paths,
    )
    save_v3_protocol_manifest(manifest, output_path)
    return manifest


def load_v3_protocol_manifest(path: str | Path) -> dict[str, Any]:
    """Strictly load and validate a protocol manifest."""

    source = Path(path)
    raw = _load_object(source, label="protocol manifest")
    return validate_v3_protocol_manifest(raw)


def verify_v3_protocol_manifest(
    manifest_path: str | Path,
    graph_directory: str | Path,
    case_paths: Iterable[str | Path] | str | Path,
    *,
    public_task_paths: Iterable[str | Path] | str | Path | None = None,
) -> dict[str, Any]:
    """Verify an existing manifest against every currently supplied artifact."""

    source = Path(manifest_path)
    manifest = load_v3_protocol_manifest(source)
    try:
        actual_bytes = source.read_bytes()
    except OSError as exc:
        raise ProtocolManifestV3Error(f"cannot read protocol manifest {source}: {exc}") from exc
    expected_bytes = canonical_json_bytes(manifest) + b"\n"
    if actual_bytes != expected_bytes:
        raise ProtocolManifestV3Error(
            "protocol manifest bytes are non-canonical or have drifted"
        )

    expected = build_v3_protocol_manifest(
        graph_directory,
        case_paths,
        public_task_paths=public_task_paths,
    )
    if manifest != expected:
        differing = sorted(
            key
            for key in set(manifest) | set(expected)
            if manifest.get(key) != expected.get(key)
        )
        raise ProtocolManifestV3Error(
            "protocol manifest does not match current artifacts; differing fields: "
            + ", ".join(differing)
        )
    return manifest


# Concise aliases for callers that already import from a v3-specific module.
build_protocol_manifest = build_v3_protocol_manifest
load_protocol_manifest = load_v3_protocol_manifest
save_protocol_manifest = save_v3_protocol_manifest
verify_protocol_manifest = verify_v3_protocol_manifest


__all__ = [
    "PROTOCOL_MANIFEST_SCHEMA",
    "ProtocolManifestV3Error",
    "build_protocol_manifest",
    "build_v3_protocol_manifest",
    "load_protocol_manifest",
    "load_v3_protocol_manifest",
    "save_protocol_manifest",
    "save_v3_protocol_manifest",
    "scorer_implementation_sha256",
    "SCORER_IMPLEMENTATION_FILES",
    "sha256_file",
    "validate_v3_protocol_manifest",
    "verify_protocol_manifest",
    "verify_v3_protocol_manifest",
    "write_v3_protocol_manifest",
]
