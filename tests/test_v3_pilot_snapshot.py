from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_evidence_graph import build_from_path, compile_inventory, load_inventory
from src.eval.evidence_graph import verify_evidence_graph_manifest
from src.eval.observation_ledger import load_observation_ledger


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/evidence_graph/dra-v3-pilot-my5090-20260715-r2"
CAPTURE = (
    ROOT
    / "data/evidence_graph/captures"
    / "v3-corpus-audio-glasses-20260715-r2-20260716T034336Z"
)
RUN_ID = "v3-corpus-audio-glasses-20260715-r2"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_pilot_snapshot_identity_and_blobs_are_frozen() -> None:
    identity = _json(SNAPSHOT / "snapshot_identity.json")
    inventory = _json(SNAPSHOT / "inventory.json")

    assert identity["corpus_snapshot"] == inventory["corpus_snapshot"]
    assert identity["status"] == "machine_draft_pending_human_review"
    assert identity["eligible_for_case_generation"] is False
    assert identity["services"]["concept"]["zim_sha256"] == (
        "0d0ff0cff37953886edca65a1fd5809eb77c96346d85c0fdd7f34eac55a1996e"
    )
    assert identity["observations"] == {
        "legacy_rows": 16,
        "normalized_events": 593,
        "search_result_events": 48,
        "extracted_body_events": 10,
        "page_link_events": 535,
        "search_responses": 4,
        "successful_body_fetches": 10,
        "failed_body_fetches": 0,
        "complete": True,
        "fatal_issue_codes": [],
    }

    documents = inventory["documents"]
    assert isinstance(documents, list)
    assert len(documents) == 14
    for document in documents:
        assert isinstance(document, dict)
        digest = document["content_sha256"]
        blob = SNAPSHOT / str(document["blob_path"])
        assert blob.name == digest
        assert hashlib.sha256(blob.read_bytes()).hexdigest() == digest


def test_pilot_snapshot_capture_replays_complete_sfl_ordering() -> None:
    ledger = load_observation_ledger(
        CAPTURE / "observations_legacy.jsonl",
        expected_run_id=RUN_ID,
    )
    assert ledger.complete
    assert len(ledger.events) == 593
    assert not ledger.withhold_reason_codes

    headphones_url = "http://localhost:8090/content/wikipedia_en_all_nopic/Headphones"
    body_events = [
        event
        for event in ledger.events
        if event.event_type == "extracted_body"
        and event.canonical_url == headphones_url
    ]
    link_events = [
        event
        for event in ledger.events
        if event.event_type == "page_link"
        and event.canonical_url == headphones_url
    ]
    assert [event.event_id for event in body_events] == [293]
    assert {event.event_id for event in link_events} >= {70, 201}
    assert min(event.event_id for event in link_events) < body_events[0].event_id


def test_pilot_graph_compiles_and_every_registered_body_is_discoverable() -> None:
    inventory = load_inventory(SNAPSHOT / "inventory.json")
    graph, _, _ = compile_inventory(inventory, blob_root=SNAPSHOT)
    document_ids = [
        node.evidence_id for node in graph.nodes if node.node_type.value == "document"
    ]
    reached = graph.require_discoverable(document_ids)

    assert len(graph.nodes) == 60
    assert len(graph.edges) == 35
    assert len(graph.support_spans) == 28
    assert set(document_ids) <= set(reached)
    assert all(
        edge.discovery_method is None or edge.discovery_method.value in {"S", "L"}
        for edge in graph.edges
    )

    headphones_discovery = [
        edge
        for edge in graph.discoverability_edges
        if edge.source_id == "doc_wiki_headphones"
    ]
    assert {edge.discovery_method.value for edge in headphones_discovery} == {"L"}
    assert {edge.discovery_order for edge in headphones_discovery} == {70, 201}


def test_pilot_draft_does_not_promote_missing_glasses_seal_claim() -> None:
    inventory = _json(SNAPSHOT / "inventory.json")
    assert inventory["metadata"]["eligible_for_case_generation"] is False
    gaps = inventory["metadata"]["evidence_gaps"]
    assert any("eyeglass temples" in gap for gap in gaps)
    assert any("long-haul flight" in gap for gap in gaps)

    propositions = [
        node
        for node in inventory["nodes"]
        if node.get("node_type") == "proposition"
    ]
    semantic_payloads = [
        json.dumps(
            {
                "subject": node["subject"],
                "predicate": node["predicate"],
                "object": node["object"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).lower()
        for node in propositions
    ]
    assert not any("eyeglass temples" in payload for payload in semantic_payloads)

    scoped_forum = {
        node["evidence_id"]: node["metadata"]["scope"]
        for node in propositions
        if node["evidence_id"].startswith("prop_forum_")
    }
    assert scoped_forum == {
        "prop_forum_glasses_pain": "single_user_report",
        "prop_forum_white_noise_symptoms": "single_user_report",
    }
    assert not any(node.get("node_type") == "decision" for node in inventory["nodes"])


def test_pilot_checked_in_graph_is_a_deterministic_build(tmp_path: Path) -> None:
    expected = verify_evidence_graph_manifest(SNAPSHOT)
    summary = build_from_path(
        SNAPSHOT / "inventory.json",
        tmp_path,
        blob_root=SNAPSHOT,
    )
    assert summary["evidence_graph_hash"] == expected["evidence_graph_hash"]
    assert summary["registry_sha256"] == expected["corpus_registry_hash"]
    assert expected["counts"] == {
        "registry_entries": 14,
        "nodes": 60,
        "edges": 35,
        "support_spans": 28,
    }

    for filename in (
        "nodes.jsonl",
        "edges.jsonl",
        "support_spans.jsonl",
        "corpus_registry.json",
        "manifest.json",
    ):
        assert (tmp_path / filename).read_bytes() == (SNAPSHOT / filename).read_bytes()
