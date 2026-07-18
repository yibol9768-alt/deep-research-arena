from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_evidence_graph import INVENTORY_SCHEMA, build_from_path
from src.eval.evidence_graph import (
    DiscoveryMethod,
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceGraphFormatError,
    EvidenceGraphValidationError,
    EvidenceNode,
    FrozenCorpusEntry,
    FrozenCorpusRegistry,
    NodeType,
    SourceType,
    SupportSpan,
    load_evidence_graph_manifest,
    load_graph,
    load_graph_structure,
    save_json,
    save_jsonl,
    sha256_bytes,
    verify_evidence_graph_manifest,
)


SNAPSHOT = "corpus-v3-test"
URL_A = "http://localhost:8090/content/test/A/Acoustic_seal"
URL_B = "http://localhost:9999/f/audio/42/glasses-on-flights"
URL_C = "http://localhost:7770/catalog/product/unused-distractor.html"
BLOB_A = "Header. Eyeglass temples can break an acoustic seal. Footer.".encode()
BLOB_B = "A ten-hour flight was comfortable after reducing clamp pressure.".encode()
BLOB_C = b"Frozen but unused product page."


def _span(blob: bytes, text: bytes) -> tuple[int, int, str]:
    start = blob.index(text)
    end = start + len(text)
    return start, end, sha256_bytes(blob[start:end])


def _valid_parts() -> tuple[
    EvidenceGraph, FrozenCorpusRegistry, dict[str, bytes]
]:
    hash_a = sha256_bytes(BLOB_A)
    hash_b = sha256_bytes(BLOB_B)
    entries = (
        FrozenCorpusEntry(
            "doc_concept_001", URL_A, SourceType.CONCEPT, hash_a, SNAPSHOT
        ),
        FrozenCorpusEntry(
            "doc_forum_001", URL_B, SourceType.FORUM, hash_b, SNAPSHOT
        ),
    )
    registry = FrozenCorpusRegistry(SNAPSHOT, entries)
    nodes = (
        EvidenceNode(
            evidence_id="ev_seal_001",
            node_type=NodeType.MECHANISM,
            subject="eyeglass temples",
            predicate="degrade",
            object="acoustic seal",
            source_url=URL_A,
            source_type=SourceType.CONCEPT,
            content_sha256=hash_a,
            corpus_snapshot=SNAPSHOT,
        ),
        EvidenceNode(
            evidence_id="ev_flight_001",
            node_type=NodeType.EXPERIENCE_CLAIM,
            subject="reduced clamp pressure",
            predicate="improves",
            object="ten-hour flight comfort",
            source_url=URL_B,
            source_type=SourceType.FORUM,
            content_sha256=hash_b,
            corpus_snapshot=SNAPSHOT,
        ),
    )
    seal_start, seal_end, seal_hash = _span(
        BLOB_A, b"Eyeglass temples can break an acoustic seal."
    )
    flight_start, flight_end, flight_hash = _span(
        BLOB_B, b"ten-hour flight was comfortable after reducing clamp pressure"
    )
    spans = (
        SupportSpan(
            "span_seal_001",
            "ev_seal_001",
            URL_A,
            seal_start,
            seal_end,
            seal_hash,
        ),
        SupportSpan(
            "span_flight_001",
            "ev_flight_001",
            URL_B,
            flight_start,
            flight_end,
            flight_hash,
        ),
    )
    edges = (
        EvidenceEdge(
            "edge_support_001",
            EdgeRelation.REQUIRES,
            "ev_flight_001",
            "ev_seal_001",
        ),
        EvidenceEdge(
            "edge_discovery_001",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_flight_001",
            "ev_seal_001",
            discovery_method=DiscoveryMethod.PAGE_LINK,
            discovery_order=1,
        ),
    )
    graph = EvidenceGraph(SNAPSHOT, nodes, edges, spans)
    return graph, registry, {URL_A: BLOB_A, URL_B: BLOB_B}


def test_valid_graph_round_trips_and_has_stable_stamps(tmp_path: Path) -> None:
    graph, registry, blobs = _valid_parts()

    assert graph.validate(blob_loader=blobs, corpus_membership=registry) is graph
    assert graph.graph_stamp.startswith("evidence-graph-v1:sha256:")
    assert len(graph.graph_sha256) == 64
    assert graph.graph_hash == graph.graph_sha256
    assert graph.graph_stamp.endswith(graph.graph_sha256)
    assert graph.corpus_stamp.startswith("graph-corpus-v1:sha256:")
    assert len(graph.corpus_sha256) == 64
    assert registry.corpus_stamp.startswith("corpus-registry-v1:sha256:")
    assert len(registry.corpus_sha256) == 64
    assert graph.nodes[0].source_identity.startswith("source:sha256:")
    assert graph.discoverability_edges[0].grants_discovery_license is True

    graph.save(tmp_path, blob_loader=blobs, corpus_membership=registry)
    # The independently persisted registry is used when no hook is passed.
    loaded = load_graph(tmp_path, blob_loader=blobs)
    structure_only = load_graph_structure(tmp_path)

    assert loaded.graph_stamp == graph.graph_stamp
    assert structure_only.graph_stamp == graph.graph_stamp
    assert loaded.corpus_stamp == graph.corpus_stamp
    assert {node.evidence_id for node in loaded.nodes} == {
        "ev_seal_001",
        "ev_flight_001",
    }
    manifest = load_evidence_graph_manifest(tmp_path)
    assert manifest["evidence_graph_hash"] == graph.graph_sha256
    assert manifest["corpus_registry_hash"] == registry.corpus_sha256
    assert "timestamp" not in manifest


def test_tampered_whole_blob_hash_fails_closed() -> None:
    graph, registry, blobs = _valid_parts()
    tampered = dict(blobs)
    tampered[URL_A] = BLOB_A + b" tampered"

    with pytest.raises(EvidenceGraphValidationError, match="content_sha256"):
        graph.validate(blob_loader=tampered, corpus_membership=registry)


def test_tampered_support_span_hash_fails_closed() -> None:
    graph, registry, blobs = _valid_parts()
    bad_span = SupportSpan(
        support_span_id=graph.support_spans[0].support_span_id,
        evidence_id=graph.support_spans[0].evidence_id,
        source_url=graph.support_spans[0].source_url,
        start=graph.support_spans[0].start,
        end=graph.support_spans[0].end,
        sha256="0" * 64,
    )
    tampered = EvidenceGraph(
        graph.corpus_snapshot,
        graph.nodes,
        graph.edges,
        (bad_span, graph.support_spans[1]),
    )

    with pytest.raises(EvidenceGraphValidationError, match="selected frozen bytes"):
        tampered.validate(blob_loader=blobs, corpus_membership=registry)


def _assertion_proposition_parts() -> tuple[
    EvidenceNode,
    EvidenceNode,
    SupportSpan,
    FrozenCorpusRegistry,
    dict[str, bytes],
]:
    content_hash = sha256_bytes(BLOB_A)
    assertion = EvidenceNode(
        evidence_id="assert_seal_001",
        node_type=NodeType.ASSERTION,
        subject="concept page",
        predicate="asserts",
        object="eyeglass temples can break an acoustic seal",
        source_url=URL_A,
        source_type=SourceType.CONCEPT,
        content_sha256=content_hash,
        corpus_snapshot=SNAPSHOT,
    )
    proposition = EvidenceNode(
        evidence_id="prop_seal_001",
        node_type=NodeType.PROPOSITION,
        subject="eyeglass temples",
        predicate="degrade",
        object="acoustic seal",
        source_url=URL_A,
        source_type=SourceType.CONCEPT,
        content_sha256=content_hash,
        corpus_snapshot=SNAPSHOT,
    )
    start, end, span_hash = _span(
        BLOB_A, b"Eyeglass temples can break an acoustic seal."
    )
    span = SupportSpan(
        "span_assert_seal_001",
        assertion.evidence_id,
        URL_A,
        start,
        end,
        span_hash,
    )
    registry = FrozenCorpusRegistry(
        SNAPSHOT,
        (
            FrozenCorpusEntry(
                "doc_assertion_001",
                URL_A,
                SourceType.CONCEPT,
                content_hash,
                SNAPSHOT,
            ),
        ),
    )
    return assertion, proposition, span, registry, {URL_A: BLOB_A}


def test_assertion_to_proposition_is_source_span_grounded() -> None:
    assertion, proposition, span, registry, blobs = _assertion_proposition_parts()
    graph = EvidenceGraph(
        SNAPSHOT,
        (assertion, proposition),
        (
            EvidenceEdge(
                "edge_asserts_seal_001",
                EdgeRelation.ASSERTS,
                assertion.evidence_id,
                proposition.evidence_id,
            ),
        ),
        (span,),
    )

    assert graph.validate(blob_loader=blobs, corpus_membership=registry) is graph


def test_assertion_without_span_and_ungrounded_proposition_fail_closed() -> None:
    assertion, proposition, _span_record, registry, blobs = _assertion_proposition_parts()
    missing_span = EvidenceGraph(
        SNAPSHOT,
        (assertion, proposition),
        (
            EvidenceEdge(
                "edge_asserts_seal_001",
                EdgeRelation.ASSERTS,
                assertion.evidence_id,
                proposition.evidence_id,
            ),
        ),
        (),
    )
    with pytest.raises(EvidenceGraphValidationError, match="assertion nodes require"):
        missing_span.validate(blob_loader=blobs, corpus_membership=registry)

    proposition_only = EvidenceGraph(SNAPSHOT, (proposition,), (), ())
    with pytest.raises(EvidenceGraphValidationError, match="lack a source-backed"):
        proposition_only.validate(blob_loader=blobs, corpus_membership=registry)


def test_asserts_cannot_turn_a_non_proposition_into_global_truth() -> None:
    assertion, proposition, span, registry, blobs = _assertion_proposition_parts()
    invalid = EvidenceGraph(
        SNAPSHOT,
        (assertion, proposition),
        (
            EvidenceEdge(
                "edge_bad_asserts_001",
                EdgeRelation.ASSERTS,
                proposition.evidence_id,
                assertion.evidence_id,
            ),
        ),
        (span,),
    )
    with pytest.raises(EvidenceGraphValidationError, match="target a proposition"):
        invalid.validate(blob_loader=blobs, corpus_membership=registry)


def test_dangling_edge_endpoint_is_rejected() -> None:
    graph, registry, blobs = _valid_parts()
    dangling = EvidenceGraph(
        graph.corpus_snapshot,
        graph.nodes,
        (
            EvidenceEdge(
                "edge_dangling_001",
                EdgeRelation.REQUIRES,
                "ev_flight_001",
                "missing_node_001",
            ),
        ),
        graph.support_spans,
    )

    with pytest.raises(EvidenceGraphValidationError, match="dangling endpoint"):
        dangling.validate(blob_loader=blobs, corpus_membership=registry)


def test_blob_existence_does_not_establish_corpus_membership() -> None:
    graph, _registry, blobs = _valid_parts()

    with pytest.raises(EvidenceGraphValidationError, match="frozen-corpus member"):
        graph.validate(blob_loader=blobs, corpus_membership={URL_B})
    with pytest.raises(EvidenceGraphValidationError, match="required independently"):
        graph.validate(blob_loader=blobs, corpus_membership=None)


def test_fetch_event_cannot_be_a_discoverability_license() -> None:
    with pytest.raises(EvidenceGraphFormatError, match="never licenses URL discovery"):
        EvidenceEdge(
            "edge_bad_fetch_001",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_flight_001",
            "ev_seal_001",
            discovery_method=DiscoveryMethod.FETCH_BODY,
        )


def test_discoverability_closure_fails_when_critical_edge_is_cut() -> None:
    graph, registry, blobs = _valid_parts()
    graph.validate(blob_loader=blobs, corpus_membership=registry)

    assert graph.discoverable_node_ids(["ev_seal_001"]) == (
        "ev_flight_001",
        "ev_seal_001",
    )
    assert graph.require_discoverable(
        ["ev_flight_001"], ["ev_seal_001"]
    ) == ("ev_flight_001", "ev_seal_001")

    cut_graph = EvidenceGraph(
        graph.corpus_snapshot,
        graph.nodes,
        tuple(
            edge
            for edge in graph.edges
            if edge.relation is not EdgeRelation.DISCOVERABLE_FROM
        ),
        graph.support_spans,
    )
    cut_graph.validate(blob_loader=blobs, corpus_membership=registry)
    # REQUIRES is a proof dependency, never a discovery license.
    assert cut_graph.discoverable_node_ids(["ev_seal_001"]) == ("ev_seal_001",)
    with pytest.raises(EvidenceGraphValidationError, match="unreachable.*ev_flight_001"):
        cut_graph.require_discoverable(["ev_flight_001"], ["ev_seal_001"])


def test_manifest_verifier_rejects_manifest_hash_and_graph_file_drift(
    tmp_path: Path,
) -> None:
    graph, registry, blobs = _valid_parts()

    hash_drift = tmp_path / "hash-drift"
    graph.save(hash_drift, blob_loader=blobs, corpus_membership=registry)
    assert verify_evidence_graph_manifest(hash_drift)["evidence_graph_hash"] == (
        graph.graph_sha256
    )
    manifest = json.loads((hash_drift / "manifest.json").read_text(encoding="utf-8"))
    manifest["evidence_graph_hash"] = "0" * 64
    manifest["graph_stamp"] = f"evidence-graph-v1:sha256:{'0' * 64}"
    save_json(hash_drift / "manifest.json", manifest)
    with pytest.raises(EvidenceGraphValidationError, match="does not match graph/registry"):
        verify_evidence_graph_manifest(hash_drift)

    file_drift = tmp_path / "file-drift"
    graph.save(file_drift, blob_loader=blobs, corpus_membership=registry)
    node_records = [
        json.loads(line)
        for line in (file_drift / "nodes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    node_records[0]["subject"] = "tampered but schema-valid subject"
    save_jsonl(file_drift / "nodes.jsonl", node_records)
    with pytest.raises(EvidenceGraphValidationError, match="does not match graph/registry"):
        verify_evidence_graph_manifest(file_drift)

    name_drift = tmp_path / "name-drift"
    graph.save(name_drift, blob_loader=blobs, corpus_membership=registry)
    manifest = json.loads((name_drift / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["nodes"] = "different.jsonl"
    save_json(name_drift / "manifest.json", manifest)
    with pytest.raises(EvidenceGraphFormatError, match="manifest.files"):
        verify_evidence_graph_manifest(name_drift)


def _inventory(tmp_path: Path, *, reverse: bool) -> dict[str, object]:
    (tmp_path / "blobs").mkdir(exist_ok=True)
    (tmp_path / "blobs" / "concept.bin").write_bytes(BLOB_A)
    (tmp_path / "blobs" / "forum.bin").write_bytes(BLOB_B)
    (tmp_path / "blobs" / "unused.bin").write_bytes(BLOB_C)
    seal_start, seal_end, seal_hash = _span(
        BLOB_A, b"Eyeglass temples can break an acoustic seal."
    )
    flight_start, flight_end, flight_hash = _span(
        BLOB_B, b"ten-hour flight was comfortable after reducing clamp pressure"
    )
    documents = [
        {
            "registry_id": "doc_concept_001",
            "source_url": URL_A,
            "source_type": "concept",
            "content_sha256": sha256_bytes(BLOB_A),
            "blob_path": "blobs/concept.bin",
            "in_corpus": True,
        },
        {
            "registry_id": "doc_forum_001",
            "source_url": URL_B,
            "source_type": "forum",
            "content_sha256": sha256_bytes(BLOB_B),
            "blob_path": "blobs/forum.bin",
            "in_corpus": True,
        },
        {
            "registry_id": "doc_unused_001",
            "source_url": URL_C,
            "source_type": "shopping",
            "content_sha256": sha256_bytes(BLOB_C),
            "blob_path": "blobs/unused.bin",
            "in_corpus": True,
        },
    ]
    nodes = [
        {
            "evidence_id": "ev_seal_001",
            "node_type": "mechanism",
            "subject": "eyeglass temples",
            "predicate": "degrade",
            "object": "acoustic seal",
            "source_url": URL_A,
            "support_spans": [
                {
                    "support_span_id": "span_seal_001",
                    "start": seal_start,
                    "end": seal_end,
                    "sha256": seal_hash,
                    "support_type": "body",
                }
            ],
        },
        {
            "evidence_id": "ev_flight_001",
            "node_type": "experience_claim",
            "subject": "reduced clamp pressure",
            "predicate": "improves",
            "object": "ten-hour flight comfort",
            "source_url": URL_B,
        },
    ]
    spans = [
        {
            "support_span_id": "span_flight_001",
            "evidence_id": "ev_flight_001",
            "start": flight_start,
            "end": flight_end,
            "sha256": flight_hash,
            "support_type": "body",
        }
    ]
    edges = [
        {
            "edge_id": "edge_support_001",
            "relation": "REQUIRES",
            "source_id": "ev_flight_001",
            "target_id": "ev_seal_001",
        },
        {
            "edge_id": "edge_discovery_001",
            "relation": "DISCOVERABLE_FROM",
            "source_id": "ev_flight_001",
            "target_id": "ev_seal_001",
            "discovery_method": "search_result",
            "discovery_order": 0,
        },
    ]
    if reverse:
        documents.reverse()
        nodes.reverse()
        edges.reverse()
    return {
        "schema_version": INVENTORY_SCHEMA,
        "corpus_snapshot": SNAPSHOT,
        "documents": documents,
        "nodes": nodes,
        "edges": edges,
        "support_spans": spans,
    }


def test_inventory_build_is_byte_deterministic(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_inventory = _inventory(first_root, reverse=False)
    second_inventory = _inventory(second_root, reverse=True)
    first_spec = first_root / "inventory.json"
    second_spec = second_root / "inventory.jsonl"
    first_spec.write_text(json.dumps(first_inventory, ensure_ascii=False), encoding="utf-8")
    jsonl_records = [
        {
            "record_type": "meta",
            "schema_version": second_inventory["schema_version"],
            "corpus_snapshot": second_inventory["corpus_snapshot"],
        },
        *(
            {"record_type": "document", **record}
            for record in second_inventory["documents"]
        ),
        *(
            {"record_type": "node", **record}
            for record in second_inventory["nodes"]
        ),
        *(
            {"record_type": "edge", **record}
            for record in second_inventory["edges"]
        ),
        *(
            {"record_type": "support_span", **record}
            for record in second_inventory["support_spans"]
        ),
    ]
    second_spec.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in jsonl_records)
        + "\n",
        encoding="utf-8",
    )

    first_summary = build_from_path(first_spec, first_root / "out")
    second_summary = build_from_path(second_spec, second_root / "out")

    for filename in (
        "nodes.jsonl",
        "edges.jsonl",
        "support_spans.jsonl",
        "corpus_registry.json",
        "manifest.json",
    ):
        assert (first_root / "out" / filename).read_bytes() == (
            second_root / "out" / filename
        ).read_bytes()
    assert first_summary["graph_stamp"] == second_summary["graph_stamp"]
    assert first_summary["registry_stamp"] == second_summary["registry_stamp"]
    assert len(first_summary["evidence_graph_hash"]) == 64
    persisted_registry = json.loads(
        (first_root / "out" / "corpus_registry.json").read_text(encoding="utf-8")
    )
    assert persisted_registry["version"] == "frozen_corpus_registry_v1"
    assert len(persisted_registry["entries"]) == 3
    assert {entry["source_url"] for entry in persisted_registry["entries"]} - {
        node["source_url"] for node in first_inventory["nodes"]
    } == {URL_C}
    persisted_manifest = json.loads(
        (first_root / "out" / "manifest.json").read_text(encoding="utf-8")
    )
    assert persisted_manifest["evidence_graph_hash"] == first_summary[
        "evidence_graph_hash"
    ]
    assert persisted_manifest["corpus_registry_hash"] == first_summary[
        "registry_sha256"
    ]
    assert persisted_manifest["counts"] == {
        "registry_entries": 3,
        "nodes": 2,
        "edges": 2,
        "support_spans": 2,
    }
    assert all("/" not in value for value in persisted_manifest["files"].values())


def test_inventory_rejects_blob_without_explicit_membership(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path, reverse=False)
    inventory["documents"][0]["in_corpus"] = False  # type: ignore[index]
    spec = tmp_path / "inventory.json"
    spec.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(EvidenceGraphFormatError, match="explicitly true"):
        build_from_path(spec, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_inventory_compiles_unique_exact_quote_to_byte_span(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path, reverse=False)
    quote = "Eyeglass temples can break an acoustic seal."
    nested = inventory["nodes"][0]["support_spans"][0]  # type: ignore[index]
    nested.pop("start")
    nested.pop("end")
    nested.pop("sha256")
    nested["exact_quote"] = quote
    spec = tmp_path / "inventory.json"
    spec.write_text(json.dumps(inventory), encoding="utf-8")

    summary = build_from_path(spec, tmp_path / "out")
    spans = [
        json.loads(line)
        for line in (tmp_path / "out" / "support_spans.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    compiled = next(span for span in spans if span["support_span_id"] == "span_seal_001")
    expected = quote.encode("utf-8")
    assert BLOB_A[compiled["start"] : compiled["end"]] == expected
    assert compiled["sha256"] == sha256_bytes(expected)
    assert compiled["metadata"] == {
        "offset_origin": "exact_quote_v1",
        "quote_occurrence": 0,
    }
    assert summary["support_spans"] == 2


def test_inventory_exact_quote_is_fail_closed_for_ambiguity_and_drift(
    tmp_path: Path,
) -> None:
    inventory = _inventory(tmp_path, reverse=False)
    repeated = "flight"
    nested = inventory["nodes"][0]["support_spans"][0]  # type: ignore[index]
    nested.clear()
    nested.update(
        {
            "support_span_id": "span_seal_001",
            "exact_quote": repeated,
            "support_type": "body",
        }
    )
    # Put a repeated review phrase in the same exact frozen document.
    concept_path = tmp_path / "blobs" / "concept.bin"
    repeated_blob = BLOB_A + b" flight flight"
    concept_path.write_bytes(repeated_blob)
    inventory["documents"][0]["content_sha256"] = sha256_bytes(repeated_blob)  # type: ignore[index]
    spec = tmp_path / "inventory.json"
    spec.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(EvidenceGraphFormatError, match="declare zero-based occurrence"):
        build_from_path(spec, tmp_path / "ambiguous")

    nested["occurrence"] = 1
    nested["start"] = 0
    spec.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(EvidenceGraphFormatError, match="conflicts with registry value"):
        build_from_path(spec, tmp_path / "drift")
