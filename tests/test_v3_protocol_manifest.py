from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_v3_protocol_manifest import main as manifest_cli
from src.eval.case_schema_v3 import (
    CaseSpecV3,
    decidable_claims_sha256,
    proof_subgraph_fingerprint,
)
from src.eval.evidence_graph import (
    DiscoveryMethod,
    EdgeRelation,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    FrozenCorpusEntry,
    FrozenCorpusRegistry,
    NodeType,
    SourceType,
    SupportSpan,
    canonical_json_bytes,
    save_json,
    sha256_bytes,
)
from src.eval.protocol_manifest_v3 import (
    ProtocolManifestV3Error,
    _load_public_tasks,
    build_v3_protocol_manifest,
    load_v3_protocol_manifest,
    save_v3_protocol_manifest,
    sha256_file,
    validate_v3_protocol_manifest,
    verify_v3_protocol_manifest,
)
from src.tasks.query_renderer_v3 import build_blind_review_packet, render_task
from test_case_schema_v3 import proof_step_case_dict, valid_case_dict


SNAPSHOT = "corpus-v3-protocol-test"
URL_ROOT = "http://localhost:8090/start"
URL_SEAL = "http://localhost:8090/seal"
URL_NOISE = "http://localhost:8090/noise"
URL_UNUSED = "http://localhost:9999/real-but-unused"


def _records_hash(records: list[dict], id_field: str) -> str:
    records = sorted(records, key=lambda record: str(record.get(id_field) or ""))
    return sha256_bytes(canonical_json_bytes(records))


def _case_source(node: EvidenceNode, span: SupportSpan) -> dict:
    return {
        "evidence_id": node.evidence_id,
        "node_type": node.node_type.value,
        "subject": node.subject,
        "predicate": node.predicate,
        "object": node.object,
        "source_url": node.source_url,
        "source_type": node.source_type.value,
        "content_sha256": node.content_sha256,
        "corpus_snapshot": node.corpus_snapshot,
        "search_snippet_support": node.search_snippet_support,
        "body_support": node.body_support,
        "verifier": dict(node.verifier),
        "support_spans": [
            {
                "support_span_id": span.support_span_id,
                "evidence_id": span.evidence_id,
                "source_url": span.source_url,
                "start": span.start,
                "end": span.end,
                "sha256": span.sha256,
                "support_type": span.support_type.value,
            }
        ],
        "frozen": True,
        "reachable": True,
    }


def _make_artifact_set(tmp_path: Path) -> dict[str, object]:
    blobs = {
        URL_ROOT: b"Start page with licensed evidence links.",
        URL_SEAL: b"Eyeglass temples can degrade an acoustic seal.",
        URL_NOISE: b"Low-frequency aircraft noise is addressed by ANC.",
        URL_UNUSED: b"A frozen but case-irrelevant forum page.",
    }
    base = valid_case_dict()
    seal_verifier = base["evidence_sources"][0]["verifier"]
    noise_verifier = base["evidence_sources"][1]["verifier"]
    nodes = (
        EvidenceNode(
            "seed_root",
            NodeType.DOCUMENT,
            "task start page",
            "links_to",
            "evidence pages",
            URL_ROOT,
            SourceType.CONCEPT,
            sha256_bytes(blobs[URL_ROOT]),
            SNAPSHOT,
            verifier={"kind": "typed_claim"},
            metadata={"task_seed": True},
        ),
        EvidenceNode(
            "ev_seal",
            NodeType.MECHANISM,
            "ev_seal",
            "supports",
            True,
            URL_SEAL,
            SourceType.CONCEPT,
            sha256_bytes(blobs[URL_SEAL]),
            SNAPSHOT,
            verifier=seal_verifier,
        ),
        EvidenceNode(
            "ev_noise",
            NodeType.MECHANISM,
            "ev_noise",
            "supports",
            True,
            URL_NOISE,
            SourceType.FORUM,
            sha256_bytes(blobs[URL_NOISE]),
            SNAPSHOT,
            verifier=noise_verifier,
        ),
    )
    spans = (
        SupportSpan(
            "span_seal",
            "ev_seal",
            URL_SEAL,
            0,
            len(blobs[URL_SEAL]),
            sha256_bytes(blobs[URL_SEAL]),
        ),
        SupportSpan(
            "span_noise",
            "ev_noise",
            URL_NOISE,
            0,
            len(blobs[URL_NOISE]),
            sha256_bytes(blobs[URL_NOISE]),
        ),
    )
    edges = (
        EvidenceEdge(
            "edge_root_seal",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_seal",
            "seed_root",
            discovery_method=DiscoveryMethod.PAGE_LINK,
            discovery_order=1,
        ),
        EvidenceEdge(
            "edge_seal_noise",
            EdgeRelation.DISCOVERABLE_FROM,
            "ev_noise",
            "ev_seal",
            discovery_method=DiscoveryMethod.PAGE_LINK,
            discovery_order=2,
        ),
    )
    registry = FrozenCorpusRegistry(
        SNAPSHOT,
        (
            FrozenCorpusEntry(
                "page_root",
                URL_ROOT,
                SourceType.CONCEPT,
                sha256_bytes(blobs[URL_ROOT]),
                SNAPSHOT,
            ),
            FrozenCorpusEntry(
                "page_seal",
                URL_SEAL,
                SourceType.CONCEPT,
                sha256_bytes(blobs[URL_SEAL]),
                SNAPSHOT,
            ),
            FrozenCorpusEntry(
                "page_noise",
                URL_NOISE,
                SourceType.FORUM,
                sha256_bytes(blobs[URL_NOISE]),
                SNAPSHOT,
            ),
            FrozenCorpusEntry(
                "page_unused",
                URL_UNUSED,
                SourceType.FORUM,
                sha256_bytes(blobs[URL_UNUSED]),
                SNAPSHOT,
            ),
        ),
    )
    graph = EvidenceGraph(SNAPSHOT, nodes, edges, spans)
    graph_dir = tmp_path / "graph"
    graph.save(graph_dir, blob_loader=blobs, corpus_membership=registry)

    case_paths: list[Path] = []
    public_paths: list[Path] = []
    node_by_id = {node.evidence_id: node for node in nodes}
    span_by_id = {span.evidence_id: span for span in spans}
    for number in (1, 2):
        payload = valid_case_dict()
        payload.pop("headline_metric", None)
        payload.pop("partial_metric", None)
        payload["headline_metrics"] = [
            "verified_research_completion_v1",
            "task_solve_rate_v1",
        ]
        payload["diagnostic_metric"] = "verified_f1_v1"
        payload["task_id"] = f"dra_v3_audio_{number:04d}"
        payload["corpus_snapshot"] = SNAPSHOT
        payload["evidence_sources"] = [
            _case_source(node_by_id["ev_seal"], span_by_id["ev_seal"]),
            _case_source(node_by_id["ev_noise"], span_by_id["ev_noise"]),
        ]
        payload["slots"] = [
            {
                "slot_id": "E1",
                "type": "evidence",
                "critical": True,
                "claim_id": "ev_seal",
                "verifier": "typed_claim",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "E2",
                "type": "evidence",
                "critical": True,
                "claim_id": "ev_noise",
                "verifier": "typed_claim",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B1",
                "type": "bridge",
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "seal_noise_bridge_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B2",
                "type": "bridge",
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "comfort_tradeoff_bridge_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "B3",
                "type": "bridge",
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": "experience_reconciliation_v1",
                "requirement_id": "Q1",
            },
            {
                "slot_id": "D1",
                "type": "decision",
                "critical": True,
                "requires": ["B1", "B2", "B3"],
                "rule": "lexicographic_priority_v1",
                "requirement_id": "Q1",
            },
        ]
        for slot in payload["slots"]:
            slot["required"] = True
        payload["rule_definitions"] = {
            "seal_noise_bridge_v1": {
                "type": "bridge",
                "matcher": "normalized_text",
                "accepted_phrases": ["Seal evidence determines the noise result."],
                "normalizers": ["casefold", "whitespace"],
            },
            "comfort_tradeoff_bridge_v1": {
                "type": "bridge",
                "matcher": "normalized_text",
                "accepted_phrases": ["Comfort evidence determines the tradeoff."],
                "normalizers": ["casefold", "whitespace"],
            },
            "experience_reconciliation_v1": {
                "type": "bridge",
                "matcher": "normalized_text",
                "accepted_phrases": [
                    "Experience evidence resolves the remaining conflict."
                ],
                "normalizers": ["casefold", "whitespace"],
            },
            "lexicographic_priority_v1": {
                "type": "decision",
                "decision_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": [
                        "Form A is the final conclusion under the stated priorities."
                    ],
                    "normalizers": ["casefold", "whitespace"],
                },
                "conclusion_matchers": {
                    "form_a": {
                        "matcher": "normalized_text",
                        "accepted_phrases": ["Form A", "choose Form A"],
                        "normalizers": ["casefold", "whitespace"],
                    }
                },
            },
        }
        payload["research_subgoals"] = [
            {
                "subgoal_id": "G1",
                "description": "Resolve the seal and noise mechanism.",
                "critical": True,
                "requires": ["E1", "E2", "B1"],
                "local_conclusion_slot_id": "B1",
            },
            {
                "subgoal_id": "G2",
                "description": "Resolve the comfort tradeoff.",
                "critical": True,
                "requires": ["E1", "E2", "B2"],
                "local_conclusion_slot_id": "B2",
            },
            {
                "subgoal_id": "G3",
                "description": "Reconcile the remaining experience conflict.",
                "critical": True,
                "requires": ["E1", "E2", "B3"],
                "local_conclusion_slot_id": "B3",
            },
            {
                "subgoal_id": "G4",
                "description": "Apply all mechanisms to the final decision.",
                "critical": True,
                "requires": ["E1", "E2", "B1", "B2", "B3", "D1"],
                "local_conclusion_slot_id": "D1",
            },
        ]
        payload["decidable_claims"] = [
            {
                "claim_id": "neg_seal_unaffected",
                "contradicts_slot_id": "E1",
                "critical": True,
                "rejected_matcher": {
                    "matcher": "normalized_text",
                    "accepted_phrases": [
                        "Eyeglass temples never affect an acoustic seal."
                    ],
                    "normalizers": ["casefold", "whitespace"],
                },
            }
        ]
        payload["query_requirements"] = [
            {
                "requirement_id": "Q1",
                "text": (
                    "Resolve all four local research questions and justify one "
                    "conclusion using the priority order."
                ),
                "slot_ids": ["E1", "E2", "B1", "B2", "B3", "D1"],
                "subgoal_ids": ["G1", "G2", "G3", "G4"],
                "required": True,
            }
        ]
        payload["oracle"] = {
            "proof": ["E1", "E2", "B1", "B2", "B3", "D1"],
            "single_page_sufficient": False,
            "minimum_required_evidence_nodes": 2,
            "minimum_reasoning_depth": 2,
            "critical_node_ablation": {
                "E1": {"outcome": "decision_unresolved"},
                "E2": {"outcome": "decision_unresolved"},
            },
        }
        draft = CaseSpecV3.from_dict(payload)
        payload["corpus_registry_urls"] = sorted(blobs)
        payload["corpus_registry_hash"] = registry.corpus_sha256
        payload["discovery_root_urls"] = [URL_ROOT]
        payload["formal_bindings"] = {
            "formal": True,
            "evidence_catalog_sha256": _records_hash(
                [node.to_dict() for node in nodes], "evidence_id"
            ),
            "support_spans_sha256": _records_hash(
                [span.to_dict() for span in spans], "support_span_id"
            ),
            "graph_edges_sha256": _records_hash(
                [edge.to_dict() for edge in edges], "edge_id"
            ),
            "evidence_graph_sha256": graph.graph_sha256,
            "corpus_registry_sha256": registry.corpus_sha256,
            "reachability_manifest_sha256": "4" * 64,
            "decidable_claims_sha256": decidable_claims_sha256(draft),
            "proof_subgraph_sha256": proof_subgraph_fingerprint(draft),
            "root_node_ids": ["seed_root"],
            "critical_evidence_node_ids": ["ev_noise", "ev_seal"],
            "reachable_node_ids": ["ev_noise", "ev_seal", "seed_root"],
        }
        case = CaseSpecV3.from_dict(payload)
        case_path = tmp_path / f"case-{number}.json"
        public_path = tmp_path / f"task-{number}.json"
        save_json(case_path, case.to_dict())
        save_json(public_path, render_task(case))
        case_paths.append(case_path)
        public_paths.append(public_path)
    return {
        "graph_dir": graph_dir,
        "case_paths": case_paths,
        "public_paths": public_paths,
        "graph": graph,
        "registry": registry,
    }


def test_manifest_is_formal_deterministic_and_input_order_independent(
    tmp_path: Path,
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    graph_dir = artifacts["graph_dir"]
    cases = artifacts["case_paths"]
    tasks = artifacts["public_paths"]
    assert isinstance(cases, list) and isinstance(tasks, list)

    forward = build_v3_protocol_manifest(
        graph_dir, cases, public_task_paths=tasks
    )
    reverse = build_v3_protocol_manifest(
        graph_dir,
        list(reversed(cases)),
        public_task_paths=list(reversed(tasks)),
    )

    assert canonical_json_bytes(forward) == canonical_json_bytes(reverse)
    assert forward["task_ids"] == ["dra_v3_audio_0001", "dra_v3_audio_0002"]
    assert len(set(forward["proof_subgraph_fingerprints"].values())) == 1
    assert forward["protocols"]["case_set_hash"]
    assert forward["protocols"]["public_task_set_hash"]
    assert forward["protocols"]["headline_metrics"] == [
        "verified_research_completion_v1",
        "task_solve_rate_v1",
    ]
    assert forward["protocols"]["diagnostic_metric"] == "verified_f1_v1"
    assert forward["protocols"]["corpus_registry_hash"] == artifacts[
        "registry"
    ].corpus_sha256
    assert forward["protocols"]["evidence_graph_hash"] == artifacts[
        "graph"
    ].graph_sha256
    assert forward["task_contracts"]["dra_v3_audio_0001"] == {
        "cluster_id": "audio_glasses_flight",
        "motif": "comparative_tradeoff",
        "declared_proof_depth": 3,
        "minimum_reasoning_depth": 2,
        "required_research_subgoals": 4,
        "cross_source_bridges": 3,
        "single_page_sufficient": False,
    }
    manifest_text = canonical_json_bytes(forward).decode("utf-8")
    assert str(tmp_path) not in manifest_text
    assert "timestamp" not in manifest_text

    target = tmp_path / "protocol.json"
    save_v3_protocol_manifest(forward, target)
    assert target.read_bytes() == canonical_json_bytes(forward) + b"\n"
    assert load_v3_protocol_manifest(target) == forward
    assert verify_v3_protocol_manifest(
        target, graph_dir, cases, public_task_paths=tasks
    ) == forward


@pytest.mark.parametrize("missing_field", ["formal_bindings", "corpus_registry_urls"])
def test_missing_or_uncompiled_case_is_rejected(
    tmp_path: Path, missing_field: str
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    case_path = artifacts["case_paths"][0]
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload.pop(missing_field)
    if missing_field == "formal_bindings":
        payload.pop("corpus_registry_urls")
        payload.pop("corpus_registry_hash")
        payload.pop("discovery_root_urls")
    save_json(case_path, payload)

    with pytest.raises(ProtocolManifestV3Error, match="not formally compiled"):
        build_v3_protocol_manifest(artifacts["graph_dir"], [case_path])


def test_case_registry_must_equal_complete_typed_registry(tmp_path: Path) -> None:
    artifacts = _make_artifact_set(tmp_path)
    case_path = artifacts["case_paths"][0]
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["corpus_registry_urls"].remove(URL_UNUSED)
    save_json(case_path, payload)

    with pytest.raises(ProtocolManifestV3Error, match="exact complete registry"):
        build_v3_protocol_manifest(artifacts["graph_dir"], [case_path])


def test_duplicate_tasks_and_cross_snapshot_cases_are_rejected(tmp_path: Path) -> None:
    artifacts = _make_artifact_set(tmp_path)
    case_path = artifacts["case_paths"][0]
    with pytest.raises(ProtocolManifestV3Error, match="duplicate.*task_id"):
        build_v3_protocol_manifest(artifacts["graph_dir"], [case_path, case_path])

    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["corpus_snapshot"] = "different-snapshot"
    for source in payload["evidence_sources"]:
        source["corpus_snapshot"] = "different-snapshot"
    save_json(case_path, payload)
    with pytest.raises(ProtocolManifestV3Error, match="does not match graph snapshot"):
        build_v3_protocol_manifest(artifacts["graph_dir"], [case_path])


def test_identical_proof_subgraph_cannot_be_split_across_clusters(
    tmp_path: Path,
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    second_case_path = artifacts["case_paths"][1]
    second_case = json.loads(second_case_path.read_text(encoding="utf-8"))
    second_case["cluster_id"] = "incorrectly_split_cluster"
    save_json(second_case_path, second_case)
    save_json(
        artifacts["public_paths"][1],
        render_task(CaseSpecV3.from_dict(second_case)),
    )

    with pytest.raises(ProtocolManifestV3Error, match="split across cluster_ids"):
        build_v3_protocol_manifest(
            artifacts["graph_dir"],
            artifacts["case_paths"],
            public_task_paths=artifacts["public_paths"],
        )


def test_public_query_case_misalignment_and_partial_task_set_are_rejected(
    tmp_path: Path,
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    with pytest.raises(ProtocolManifestV3Error, match="requires one exact public task"):
        build_v3_protocol_manifest(
            artifacts["graph_dir"], artifacts["case_paths"]
        )
    with pytest.raises(ProtocolManifestV3Error, match="do not cover"):
        build_v3_protocol_manifest(
            artifacts["graph_dir"],
            artifacts["case_paths"],
            public_task_paths=[artifacts["public_paths"][0]],
        )

    public_path = artifacts["public_paths"][0]
    task = json.loads(public_path.read_text(encoding="utf-8"))
    task["query_contract"]["constraints"][0]["text"] = "drifted constraint"
    save_json(public_path, task)
    with pytest.raises(ProtocolManifestV3Error, match="exact leak-free rendering"):
        build_v3_protocol_manifest(
            artifacts["graph_dir"],
            [artifacts["case_paths"][0]],
            public_task_paths=[public_path],
        )

    # An otherwise aligned task may not carry extra private/gold fields.
    clean_case = CaseSpecV3.load(artifacts["case_paths"][1])
    leaked_task = render_task(clean_case)
    leaked_task["evidence_sources"] = clean_case.to_dict()["evidence_sources"]
    leaked_path = tmp_path / "leaked-task.json"
    save_json(leaked_path, leaked_task)
    with pytest.raises(ProtocolManifestV3Error, match="extra=.*evidence_sources"):
        build_v3_protocol_manifest(
            artifacts["graph_dir"],
            [artifacts["case_paths"][1]],
            public_task_paths=[leaked_path],
        )


@pytest.mark.parametrize(
    ("field_name", "replacement", "message"),
    [
        ("evidence_catalog_sha256", "f" * 64, "does not match the verified graph"),
        (
            "reachable_node_ids",
            ["ev_noise", "ev_seal", "fake_node", "seed_root"],
            "does not equal the recomputed discovery closure",
        ),
        ("root_node_ids", ["ev_seal"], "critical evidence as discovery roots"),
    ],
)
def test_handwritten_formal_bindings_cannot_bypass_graph_recomputation(
    tmp_path: Path, field_name: str, replacement: object, message: str
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    case_path = artifacts["case_paths"][0]
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["formal_bindings"][field_name] = replacement
    if field_name == "root_node_ids":
        payload["discovery_root_urls"] = [URL_SEAL]
    save_json(case_path, payload)
    with pytest.raises(ProtocolManifestV3Error, match=message):
        build_v3_protocol_manifest(artifacts["graph_dir"], [case_path])


def test_verify_rejects_exact_case_task_graph_and_registry_drift(
    tmp_path: Path,
) -> None:
    # Exact case-byte drift, including semantically irrelevant whitespace.
    case_set = _make_artifact_set(tmp_path / "case-drift")
    case_manifest = tmp_path / "case-drift.json"
    manifest = build_v3_protocol_manifest(
        case_set["graph_dir"],
        case_set["case_paths"],
        public_task_paths=case_set["public_paths"],
    )
    save_v3_protocol_manifest(manifest, case_manifest)
    case_set["case_paths"][0].write_bytes(
        case_set["case_paths"][0].read_bytes() + b"\n"
    )
    with pytest.raises(ProtocolManifestV3Error, match="does not match current artifacts"):
        verify_v3_protocol_manifest(
            case_manifest,
            case_set["graph_dir"],
            case_set["case_paths"],
            public_task_paths=case_set["public_paths"],
        )

    # Public task formatting is also exact once public artifacts are bound.
    task_set = _make_artifact_set(tmp_path / "task-drift")
    task_manifest = tmp_path / "task-drift.json"
    save_v3_protocol_manifest(
        build_v3_protocol_manifest(
            task_set["graph_dir"],
            task_set["case_paths"],
            public_task_paths=task_set["public_paths"],
        ),
        task_manifest,
    )
    task_set["public_paths"][0].write_bytes(
        task_set["public_paths"][0].read_bytes() + b"\n"
    )
    with pytest.raises(ProtocolManifestV3Error, match="does not match current artifacts"):
        verify_v3_protocol_manifest(
            task_manifest,
            task_set["graph_dir"],
            task_set["case_paths"],
            public_task_paths=task_set["public_paths"],
        )

    # Graph and registry artifacts are first rejected by their own verifier.
    graph_set = _make_artifact_set(tmp_path / "graph-drift")
    graph_manifest = tmp_path / "graph-drift.json"
    save_v3_protocol_manifest(
        build_v3_protocol_manifest(
            graph_set["graph_dir"],
            graph_set["case_paths"],
            public_task_paths=graph_set["public_paths"],
        ),
        graph_manifest,
    )
    nodes_path = graph_set["graph_dir"] / "nodes.jsonl"
    nodes_path.write_bytes(nodes_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="non-canonical|drift"):
        verify_v3_protocol_manifest(
            graph_manifest,
            graph_set["graph_dir"],
            graph_set["case_paths"],
            public_task_paths=graph_set["public_paths"],
        )

    registry_set = _make_artifact_set(tmp_path / "registry-drift")
    registry_manifest = tmp_path / "registry-drift.json"
    save_v3_protocol_manifest(
        build_v3_protocol_manifest(
            registry_set["graph_dir"],
            registry_set["case_paths"],
            public_task_paths=registry_set["public_paths"],
        ),
        registry_manifest,
    )
    registry_path = registry_set["graph_dir"] / "corpus_registry.json"
    registry_path.write_bytes(registry_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="non-canonical|drift"):
        verify_v3_protocol_manifest(
            registry_manifest,
            registry_set["graph_dir"],
            registry_set["case_paths"],
            public_task_paths=registry_set["public_paths"],
        )


def test_self_hash_and_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    artifacts = _make_artifact_set(tmp_path)
    target = tmp_path / "protocol.json"
    argv = ["--graph-dir", str(artifacts["graph_dir"]), "--out", str(target)]
    for case_path in artifacts["case_paths"]:
        argv.extend(("--case", str(case_path)))
    for public_path in artifacts["public_paths"]:
        argv.extend(("--public-task", str(public_path)))
    assert manifest_cli(argv) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    verify_argv = [
        "--graph-dir",
        str(artifacts["graph_dir"]),
        "--verify",
        str(target),
    ]
    for case_path in artifacts["case_paths"]:
        verify_argv.extend(("--case", str(case_path)))
    for public_path in artifacts["public_paths"]:
        verify_argv.extend(("--public-task", str(public_path)))
    assert manifest_cli(verify_argv) == 0

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build_v3_protocol_manifest.py"
    )
    outside_cwd = subprocess.run(
        [sys.executable, str(script), *verify_argv],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert outside_cwd.returncode == 0, outside_cwd.stderr

    manifest = json.loads(target.read_text(encoding="utf-8"))
    manifest["case_hashes"][manifest["task_ids"][0]] = "0" * 64
    # Keep the stale self-hash to prove that content edits cannot self-validate.
    target.write_text(json.dumps(manifest), encoding="utf-8")
    assert manifest_cli(verify_argv) == 1
    assert "manifest_sha256" in capsys.readouterr().err

    # Sanity check that the manifest commits exact case bytes, not model dumps.
    assert sha256_file(artifacts["case_paths"][0]) in load_v3_protocol_manifest(
        save_again(artifacts, tmp_path / "fresh.json")
    )["case_hashes"].values()


def test_formal_manifest_rejects_resigned_scorer_implementation_drift(
    tmp_path: Path,
) -> None:
    artifacts = _make_artifact_set(tmp_path)
    manifest = build_v3_protocol_manifest(
        artifacts["graph_dir"],
        artifacts["case_paths"],
        public_task_paths=artifacts["public_paths"],
    )
    manifest["scorer_implementation_sha256"] = "0" * 64
    manifest["manifest_sha256"] = sha256_bytes(
        canonical_json_bytes(
            {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
        )
    )
    with pytest.raises(
        ProtocolManifestV3Error,
        match="scorer implementation bytes have drifted",
    ):
        validate_v3_protocol_manifest(manifest)


def test_proof_manifest_requires_accepted_blind_review_task(tmp_path: Path) -> None:
    case = CaseSpecV3.from_dict(proof_step_case_dict())
    query = (
        "A traveler wears glasses and has a small bag. Compare form a with form b "
        "and choose the better form factor for the stated trip."
    )
    packet = build_blind_review_packet(case, attempt=1, query_text=query)
    review = {
        "schema": "blind_semantic_alignment_review_v1",
        "task_id": case.task_id,
        "attempt": 1,
        "max_generation_attempts": 3,
        "generator_view_sha256": packet["generator_view_sha256"],
        "query_sha256": packet["query_sha256"],
        "reviewer_id": "blind-reviewer-01",
        "faithful": True,
        "natural": True,
        "closed_environment_answerable": True,
        "requires_multi_branch_research": True,
        "passed": True,
    }
    accepted = render_task(
        case,
        blind_review_record=review,
        query_text=query,
    )
    accepted_path = tmp_path / "accepted-task.json"
    save_json(accepted_path, accepted)

    hashes = _load_public_tasks([accepted_path], {case.task_id: case})
    assert hashes == {case.task_id: sha256_file(accepted_path)}

    tampered = dict(accepted)
    tampered["intent"] = query + " Include a concise recommendation."
    tampered_path = tmp_path / "tampered-task.json"
    save_json(tampered_path, tampered)
    with pytest.raises(ProtocolManifestV3Error, match="bind.*public query"):
        _load_public_tasks([tampered_path], {case.task_id: case})

    pending_path = tmp_path / "pending-task.json"
    save_json(pending_path, render_task(case))
    with pytest.raises(ProtocolManifestV3Error, match="not accepted"):
        _load_public_tasks([pending_path], {case.task_id: case})


def save_again(artifacts: dict[str, object], path: Path) -> Path:
    manifest = build_v3_protocol_manifest(
        artifacts["graph_dir"],
        artifacts["case_paths"],
        public_task_paths=artifacts["public_paths"],
    )
    save_v3_protocol_manifest(manifest, path)
    return path
