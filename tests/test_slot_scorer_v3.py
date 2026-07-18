from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from src.eval.evidence_graph import (
    EVIDENCE_GRAPH_MANIFEST_VERSION,
    FrozenCorpusEntry,
    FrozenCorpusRegistry,
    canonical_json_bytes,
)
from src.eval.observation_ledger import (
    ObservationEvent,
    ObservationLedger,
    load_observation_ledger,
    sha256_text,
)
from src.eval.case_schema_v3 import (
    decidable_claims_sha256,
    proof_subgraph_fingerprint,
    validate_case,
)
from src.eval.slot_scorer import score_case
from src.eval.protocol_manifest_v3 import (
    PROTOCOL_MANIFEST_SCHEMA,
    scorer_implementation_sha256,
)
from src.eval.protocol_v3 import protocol_stamp, validate_protocol
from test_case_schema_v3 import valid_case_dict


U1 = "http://localhost:9999/products/alpha"
U2 = "http://localhost:8090/content/wikipedia_en_all_nopic/A/cabin-noise"
UNUSED = "http://localhost:3000/t/unused"
FABRICATED = "http://localhost:9999/not-in-frozen-corpus"
BODY1 = "The frozen Alpha page says battery life is 30 hours."
BODY2 = "The frozen concept page says cabin noise is low frequency."


def _event(i, kind, url, text, *, status=None, parent=None):
    return {
        "run_id": "run-v3",
        "event_id": i,
        "timestamp": float(i),
        "event_type": kind,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent,
        "content_sha256": sha256_text(text),
        "content_text_or_blob_ref": text,
        "http_status": status,
        "observable": True,
    }


def ledger() -> ObservationLedger:
    return ObservationLedger.from_records(
        [
            _event(1, "search_result", U1, "Alpha catalog result"),
            _event(2, "fetch_body", U1, BODY1, status=200, parent=1),
            _event(3, "search_result", U2, "Cabin noise concept result"),
            _event(4, "fetch_body", U2, BODY2, status=200, parent=3),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )


def case() -> dict:
    return {
        "task_id": "dra_v3_test_0001",
        "task_version": 3,
        "case_schema": "evidence_graph_case_v1",
        "corpus_snapshot": "fixture-snapshot-v1",
        "cluster_id": "test_cluster",
        "corpus_registry_urls": [U1, U2, UNUSED],
        "corpus_registry_hash": sha256_text("fixture corpus registry v1"),
        "research_subgoals": [
            {
                "subgoal_id": "G1",
                "description": "synthesize endurance and cabin-noise evidence",
                "critical": True,
                "requires": ["E1", "E2", "B1"],
                "local_conclusion_slot_id": "B1",
            },
            {
                "subgoal_id": "G2",
                "description": "make the final priority-consistent decision",
                "critical": True,
                "requires": ["B1", "D1"],
                "local_conclusion_slot_id": "D1",
            },
        ],
        "slots": [
            {"slot_id": "E1", "type": "evidence", "critical": True, "claim_id": "ev1"},
            {"slot_id": "E2", "type": "evidence", "critical": True, "claim_id": "ev2"},
            {
                "slot_id": "B1",
                "type": "bridge",
                "critical": True,
                "requires": ["E1", "E2"],
                "rule": {"accepted_phrases": ["Together these facts make Alpha suitable for travel"]},
            },
            {
                "slot_id": "D1",
                "type": "decision",
                "critical": True,
                "requires": ["B1"],
                "rule": {
                    "accepted_phrases": ["Noise control is the first priority"],
                    "conclusion_matchers": {
                        "Alpha": {
                            "matcher": "normalized_text",
                            "accepted_phrases": ["recommend Alpha"],
                        }
                    },
                },
            },
        ],
        "acceptable_conclusions": ["Alpha"],
    }


def graph() -> dict:
    return {
        "schema_version": "evidence_graph_v1",
        "nodes": {
            "ev1": {
                "evidence_id": "ev1",
                "subject": "Alpha",
                "predicate": "battery_life",
                "object": "30 hours",
                "source_url": U1,
                "content_sha256": sha256_text(BODY1),
                "support_spans": [{"text": "battery life is 30 hours"}],
                "verifier": {
                    "kind": "typed_claim",
                    "accepted_phrases": ["Alpha lasts 30 hours"],
                },
            },
            "ev2": {
                "evidence_id": "ev2",
                "subject": "cabin noise",
                "predicate": "frequency",
                "object": "low",
                "source_url": U2,
                "content_sha256": sha256_text(BODY2),
                "support_spans": [{"text": "cabin noise is low frequency"}],
                "verifier": {
                    "kind": "typed_claim",
                    "accepted_phrases": ["Cabin noise is low frequency"],
                },
            },
        },
    }


def oracle_report(extra: str = "") -> str:
    return (
        f"Alpha lasts 30 hours [Alpha source]({U1}). "
        f"Cabin noise is low frequency [concept source]({U2}).\n\n"
        "Together these facts make Alpha suitable for travel. "
        "Noise control is the first priority. Therefore, I recommend Alpha."
        + extra
    )


def by_id(result: dict, slot_id: str) -> dict:
    return next(row for row in result["slot_results"] if row["slot_id"] == slot_id)


def _valid_formal_case() -> dict:
    draft = valid_case_dict()
    draft_spec = validate_case(draft)
    payload = deepcopy(draft)
    discovery_root_url = "http://localhost:8080/start"
    registry_digest = sha256_text("sealed typed registry bytes")
    graph_digest = sha256_text("sealed graph bytes")
    evidence_ids = sorted(
        slot.claim_id
        for slot in draft_spec.slots
        if slot.critical and slot.type == "evidence"
    )
    payload.update({
        "corpus_registry_urls": sorted(
            [
                discovery_root_url,
                *(source.source_url for source in draft_spec.evidence_sources),
            ]
        ),
        "corpus_registry_hash": registry_digest,
        "discovery_root_urls": [discovery_root_url],
        "formal_bindings": {
            "formal": True,
            "evidence_catalog_sha256": sha256_text("sealed evidence catalog"),
            "support_spans_sha256": sha256_text("sealed support spans"),
            "graph_edges_sha256": sha256_text("sealed graph edges"),
            "evidence_graph_sha256": graph_digest,
            "corpus_registry_sha256": registry_digest,
            "reachability_manifest_sha256": sha256_text("sealed reachability"),
            "decidable_claims_sha256": decidable_claims_sha256(draft_spec),
            "proof_subgraph_sha256": proof_subgraph_fingerprint(draft_spec),
            "root_node_ids": ["seed_root"],
            "critical_evidence_node_ids": evidence_ids,
            "reachable_node_ids": evidence_ids,
        },
    })
    validate_case(payload)
    return payload


def _sealed_manifest(formal_case: dict, case_digest: str) -> dict:
    spec = validate_case(formal_case)
    task_id = formal_case["task_id"]
    graph_digest = formal_case["formal_bindings"]["evidence_graph_sha256"]
    registry_digest = formal_case["formal_bindings"]["corpus_registry_sha256"]
    public_digest = sha256_text("sealed public task bytes")
    protocols = protocol_stamp(
        corpus_snapshot=formal_case["corpus_snapshot"],
        task_ids=[task_id],
        case_hashes={task_id: case_digest},
        public_task_hashes={task_id: public_digest},
        evidence_graph_hash=graph_digest,
        corpus_registry_hash=registry_digest,
    )
    payload = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": protocols,
        "task_ids": [task_id],
        "task_clusters": {task_id: formal_case["cluster_id"]},
        "task_contracts": {
            task_id: {
                "cluster_id": spec.cluster_id,
                "motif": spec.motif,
                "declared_proof_depth": spec.difficulty.proof_depth,
                "minimum_reasoning_depth": spec.minimum_reasoning_depth,
                "required_research_subgoals": len(spec.research_subgoals),
                "cross_source_bridges": spec.cross_source_bridge_count,
                "single_page_sufficient": spec.oracle.single_page_sufficient,
            }
        },
        "proof_subgraph_fingerprints": {
            task_id: spec.proof_subgraph_sha256
        },
        "case_hashes": {task_id: case_digest},
        "public_task_hashes": {task_id: public_digest},
        "scorer_implementation_sha256": scorer_implementation_sha256(),
        "evidence_graph_artifact": {
            "manifest_schema": EVIDENCE_GRAPH_MANIFEST_VERSION,
            "evidence_graph_hash": graph_digest,
            "corpus_registry_hash": registry_digest,
            "graph_corpus_hash": sha256_text("graph corpus"),
            "counts": {
                "registry_entries": 3,
                "nodes": 2,
                "edges": 2,
                "support_spans": 2,
            },
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def test_completed_oracle_passes_every_slot_and_metrics():
    result = score_case(case(), oracle_report(), ledger(), graph())
    assert result["status"] == "scored"
    assert result["task_pass"] == 1
    assert (result["tp"], result["fn"], result["fp"]) == (4, 0, 0)
    assert result["precision"] == result["recall"] == result["f1"] == 1.0
    assert result["verified_research_completion"] == 1.0
    assert result["evidence_completion"] == 1.0
    assert result["bridge_completion"] == 1.0
    assert result["decision_completion"] == 1.0
    assert all(row["passed"] for row in result["research_subgoal_results"])
    assert result["fabricated_citations"] == 0
    assert result["unused_citations"] == []
    assert result["run_id"] == "run-v3"
    assert result["report_sha256"] == sha256_text(oracle_report())
    assert len(result["observation_ledger_sha256"]) == 64
    assert result["case_artifact_sha256"] is None
    assert result["protocol_manifest_sha256"] is None
    assert len(result["scoring_input_sha256"]) == 64
    assert len(result["corpus_registry_hash"]) == 64
    assert "headline_metric" not in result["protocols"]
    assert "partial_metric" not in result["protocols"]
    assert validate_protocol(result) == result["protocols"]
    assert all(row["verified"] for row in result["slot_results"])
    assert all(by_id(result, "E1")[axis] for axis in "CBRLO")


def test_url_dump_and_fact_dump_do_not_solve_the_task():
    url_dump = f"Sources: [one]({U1}) [two]({U2})"
    dumped = score_case(case(), url_dump, ledger(), graph())
    assert dumped["task_pass"] == 0
    assert dumped["tp"] == 0
    assert set(dumped["unused_citations"]) == {U1, U2}

    fact_dump = (
        f"Alpha lasts 30 hours [one]({U1}). "
        f"Cabin noise is low frequency [two]({U2})."
    )
    facts = score_case(case(), fact_dump, ledger(), graph())
    assert by_id(facts, "E1")["verified"]
    assert by_id(facts, "E2")["verified"]
    assert not by_id(facts, "B1")["verified"]
    assert not by_id(facts, "D1")["verified"]
    assert facts["verified_research_completion"] == 0.0
    assert facts["evidence_completion"] == 1.0
    assert facts["bridge_completion"] == 0.0
    assert facts["decision_completion"] == 0.0
    assert facts["task_pass"] == 0


def test_snippet_support_is_distinct_from_body_support_and_link_discovery():
    one_case = case()
    one_case["slots"] = [one_case["slots"][0]]
    node = graph()["nodes"]["ev1"]
    node.pop("content_sha256")
    node["support_spans"] = [{"text": "battery life is 30 hours"}]
    snippet_ledger = ObservationLedger.from_records(
        [_event(1, "search_result", U1, "battery life is 30 hours")],
        expected_run_id="run-v3",
        capture_complete=True,
    )
    report = f"Alpha lasts 30 hours [source]({U1})."

    node["search_snippet_support"] = True
    supported = score_case(one_case, report, snippet_ledger, {"nodes": {"ev1": node}})
    assert by_id(supported, "E1")["O"] is True
    assert by_id(supported, "E1")["L"] is True

    node["search_snippet_support"] = False
    body_only = score_case(one_case, report, snippet_ledger, {"nodes": {"ev1": node}})
    assert by_id(body_only, "E1")["O"] is False

    # An L event is discovery only.  It cannot license the parent page's or
    # target page's body content without a real fetch/extract observation.
    parent = "http://localhost:9999/index"
    one_case["discovery_root_urls"] = [parent]
    parent_body = f'<a href="{U1}">Alpha</a>'
    link_ledger = ObservationLedger.from_records(
        [
            _event(1, "fetch_body", parent, parent_body, status=200),
            _event(2, "page_link", U1, U1, parent=1),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )
    linked = score_case(one_case, report, link_ledger, {"nodes": {"ev1": node}})
    assert by_id(linked, "E1")["L"] is True
    assert by_id(linked, "E1")["O"] is False


def test_missing_or_damaged_ledger_withholds_but_complete_empty_trace_scores_zero():
    missing = score_case(case(), oracle_report(), None, graph())
    assert missing["status"] == "withheld"
    assert missing["task_pass"] is None
    assert missing["f1"] is None

    bad_event = _event(1, "search_result", U1, "visible")
    bad_event["content_sha256"] = "0" * 64
    damaged = ObservationLedger.from_records(
        [bad_event], expected_run_id="run-v3", capture_complete=True
    )
    withheld = score_case(case(), oracle_report(), damaged, graph())
    assert withheld["status"] == "withheld"
    assert "observation_content_hash_mismatch" in {
        reason["code"] for reason in withheld["withhold_reasons"]
    }

    empty = ObservationLedger.from_records(
        [], expected_run_id="run-v3", capture_complete=True
    )
    silent = score_case(case(), "", empty, graph())
    assert silent["status"] == "scored"
    assert (silent["tp"], silent["fp"]) == (0, 0)
    assert silent["precision"] == silent["recall"] == silent["f1"] == 0.0
    assert silent["task_pass"] == 0

    loose_mapping = {"run_id": "run-v3", "capture_complete": True, "events": []}
    assert score_case(case(), "", loose_mapping, graph())["status"] == "withheld"
    assert score_case(case(), "", [], graph())["status"] == "withheld"


def test_missing_full_corpus_registry_withholds_instead_of_using_case_subgraph():
    incomplete = case()
    incomplete.pop("corpus_registry_urls")
    incomplete.pop("corpus_registry_hash")
    result = score_case(incomplete, oracle_report(), ledger(), graph())
    assert result["status"] == "withheld"
    assert result["task_pass"] is None
    assert result["fabricated_citations"] is None
    assert result["fabricated_citation_urls"] is None
    assert result["unused_citations"] is None
    assert "corpus_registry_unavailable" in {
        reason["code"] for reason in result["withhold_reasons"]
    }


def test_sealed_protocol_manifest_is_injected_not_self_manufactured():
    formal_case = _valid_formal_case()
    case_digest = sha256_text("exact sealed case file bytes")
    manifest = _sealed_manifest(formal_case, case_digest)
    public_digest = manifest["public_task_hashes"][formal_case["task_id"]]
    result = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        graph(),
        protocols=manifest,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert result["status"] == "scored"
    assert result["protocols"]["case_set_hash"] == manifest["protocols"]["case_set_hash"]
    assert result["protocols"]["evidence_graph_hash"] == manifest["protocols"]["evidence_graph_hash"]
    assert result["case_artifact_sha256"] == case_digest
    assert result["public_task_sha256"] == public_digest
    assert result["protocol_manifest_sha256"] == manifest["manifest_sha256"]
    assert result["agent"] == "agent-a"
    assert result["replicate"] == 1

    expected_identity = {
        "version": "dra_v3_scoring_input_v2",
        "run_id": result["run_id"],
        "agent": "agent-a",
        "task_id": formal_case["task_id"],
        "replicate": 1,
        "cluster_id": formal_case["cluster_id"],
        "report_sha256": result["report_sha256"],
        "observation_ledger_sha256": result["observation_ledger_sha256"],
        "case_artifact_sha256": case_digest,
        "public_task_sha256": public_digest,
        "protocol_manifest_sha256": manifest["manifest_sha256"],
        "corpus_registry_hash": formal_case["corpus_registry_hash"],
    }
    assert result["scoring_input_sha256"] == hashlib.sha256(
        json.dumps(
            expected_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    no_digest = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        graph(),
        protocols=manifest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert no_digest["status"] == "withheld"
    assert "protocol_manifest_invalid" in {
        reason["code"] for reason in no_digest["withhold_reasons"]
    }

    wrong_bytes = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        graph(),
        protocols=manifest,
        case_artifact_sha256=sha256_text("different case file bytes"),
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert wrong_bytes["status"] == "withheld"

    tampered = dict(manifest)
    tampered["task_clusters"] = dict(manifest["task_clusters"])
    tampered["task_clusters"][formal_case["task_id"]] = "wrong_cluster"
    invalid_self_hash = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        graph(),
        protocols=tampered,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert invalid_self_hash["status"] == "withheld"


def test_formal_seed_override_is_withheld_but_draft_seed_behavior_remains():
    guessed_ledger = ObservationLedger.from_records(
        [
            _event(1, "fetch_body", U1, BODY1, status=200),
            _event(2, "search_result", U2, "Cabin noise concept result"),
            _event(3, "fetch_body", U2, BODY2, status=200, parent=2),
        ],
        expected_run_id="run-v3",
        capture_complete=True,
    )

    # Draft diagnostics retain the explicit-seed compatibility path.
    draft = score_case(
        case(),
        oracle_report(),
        guessed_ledger,
        graph(),
        seed_urls=[U1],
    )
    assert draft["status"] == "scored"
    assert by_id(draft, "E1")["discovery_class"] == "task_seed"
    assert draft["task_pass"] == 1

    formal_case = _valid_formal_case()
    case_digest = sha256_text("exact sealed case file bytes")
    manifest = _sealed_manifest(formal_case, case_digest)
    public_digest = manifest["public_task_hashes"][formal_case["task_id"]]
    rejected = score_case(
        formal_case,
        oracle_report(),
        guessed_ledger,
        protocols=manifest,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
        seed_urls=[U1],
    )
    assert rejected["status"] == "withheld"
    assert rejected["slot_results"] == []
    assert rejected["task_pass"] is None
    assert "formal_seed_override_forbidden" in {
        reason["code"] for reason in rejected["withhold_reasons"]
    }


def test_formal_corpus_override_cannot_launder_a_fabricated_url():
    formal_case = _valid_formal_case()
    case_digest = sha256_text("exact sealed case file bytes")
    manifest = _sealed_manifest(formal_case, case_digest)
    public_digest = manifest["public_task_hashes"][formal_case["task_id"]]
    common = {
        "protocols": manifest,
        "case_artifact_sha256": case_digest,
        "public_task_sha256": public_digest,
        "agent": "agent-a",
        "replicate": 1,
    }

    exact_copy = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        corpus_urls=formal_case["corpus_registry_urls"],
        corpus_registry_hash=formal_case["corpus_registry_hash"],
        **common,
    )
    assert exact_copy["status"] == "scored"
    assert exact_copy["corpus_registry_source"] == "case_or_graph_registry"
    assert "formal_corpus_registry_override_invalid" not in {
        reason["code"] for reason in exact_copy["withhold_reasons"]
    }

    rejected = score_case(
        formal_case,
        oracle_report(f"\nExtra reference: {FABRICATED}"),
        ledger(),
        corpus_urls=[*formal_case["corpus_registry_urls"], FABRICATED],
        # Before this regression, pairing an extended URL set with the sealed
        # hash washed the fabricated citation out of the global TaskPass gate.
        corpus_registry_hash=formal_case["corpus_registry_hash"],
        **common,
    )
    assert rejected["status"] == "withheld"
    assert rejected["task_pass"] is None
    assert "formal_corpus_registry_override_invalid" in {
        reason["code"] for reason in rejected["withhold_reasons"]
    }


def test_formal_schema_contract_and_attribution_fail_closed_before_scoring():
    formal_case = _valid_formal_case()
    case_digest = sha256_text("exact sealed case file bytes")
    manifest = _sealed_manifest(formal_case, case_digest)
    public_digest = manifest["public_task_hashes"][formal_case["task_id"]]

    malformed = deepcopy(formal_case)
    malformed["research_subgoals"] = malformed["research_subgoals"][:1]
    rejected = score_case(
        malformed,
        oracle_report(),
        ledger(),
        protocols=manifest,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert rejected["status"] == "withheld"
    assert rejected["slot_results"] == []
    assert rejected["task_pass"] is None
    assert "formal_case_schema_invalid" in {
        reason["code"] for reason in rejected["withhold_reasons"]
    }

    missing_attribution = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        protocols=manifest,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
    )
    assert missing_attribution["status"] == "withheld"
    assert "formal_replay_identity_invalid" in {
        reason["code"] for reason in missing_attribution["withhold_reasons"]
    }

    contract_drift = deepcopy(manifest)
    contract_drift["task_contracts"] = deepcopy(manifest["task_contracts"])
    contract_drift["task_contracts"][formal_case["task_id"]][
        "declared_proof_depth"
    ] += 1
    contract_drift["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes({
            key: value
            for key, value in contract_drift.items()
            if key != "manifest_sha256"
        })
    ).hexdigest()
    rejected_contract = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        protocols=contract_drift,
        case_artifact_sha256=case_digest,
        public_task_sha256=public_digest,
        agent="agent-a",
        replicate=1,
    )
    assert rejected_contract["status"] == "withheld"
    assert "protocol_manifest_invalid" in {
        reason["code"] for reason in rejected_contract["withhold_reasons"]
    }

    wrong_public = score_case(
        formal_case,
        oracle_report(),
        ledger(),
        protocols=manifest,
        case_artifact_sha256=case_digest,
        public_task_sha256=sha256_text("another public task"),
        agent="agent-a",
        replicate=1,
    )
    assert wrong_public["status"] == "withheld"


def test_fabricated_global_gate_R_axis_and_real_unused_diagnostic():
    contaminated = score_case(
        case(), oracle_report(f"\n\nExtra [fabricated]({FABRICATED})."), ledger(), graph()
    )
    assert contaminated["f1"] == 1.0
    assert contaminated["fabricated_citations"] == 1
    assert contaminated["fabricated_citation_urls"] == [FABRICATED]
    assert contaminated["task_pass"] == 0

    wrong_binding = oracle_report().replace(U1, FABRICATED)
    bound = score_case(case(), wrong_binding, ledger(), graph())
    assert by_id(bound, "E1")["C"] is True
    assert by_id(bound, "E1")["B"] is False
    assert by_id(bound, "E1")["R"] is False
    assert by_id(bound, "E1")["reason_codes"]["R"] == "citation_not_in_frozen_corpus"

    unused = score_case(
        case(), oracle_report(f"\n\nBackground [real but irrelevant]({UNUSED})."), ledger(), graph()
    )
    assert unused["fabricated_citations"] == 0
    assert unused["unused_citations"] == [UNUSED]
    assert unused["task_pass"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        f"\n\nBare fabricated source: {FABRICATED}",
        f"\n\nAn unsupported aside [9].\n\n## References\n[9] {FABRICATED}",
    ],
)
def test_report_wide_fabricated_gate_covers_bare_and_numbered_styles(extra):
    result = score_case(case(), oracle_report(extra), ledger(), graph())
    assert result["fabricated_citations"] == 1
    assert result["fabricated_citation_urls"] == [FABRICATED]
    assert result["task_pass"] == 0


def test_citation_must_be_local_not_a_detached_bibliography():
    report = (
        "Alpha lasts 30 hours. Cabin noise is low frequency.\n\n"
        "Together these facts make Alpha suitable for travel. "
        "Noise control is the first priority. Therefore, I recommend Alpha.\n\n"
        f"## Sources\n\n[Alpha]({U1}) [concept]({U2})"
    )
    result = score_case(case(), report, ledger(), graph())
    assert by_id(result, "E1")["C"] is True
    assert by_id(result, "E1")["B"] is False
    assert result["task_pass"] == 0

    swapped = (
        f"Alpha lasts 30 hours [wrong]({U2}). "
        f"Cabin noise is low frequency [wrong]({U1})."
    )
    crossed = score_case(case(), swapped, ledger(), graph())
    assert by_id(crossed, "E1")["B"] is False
    assert by_id(crossed, "E2")["B"] is False


def test_regex_fullmatch_and_numeric_tolerance_are_explicit_positive_matchers():
    one_case = case()
    one_case["slots"] = [one_case["slots"][0]]
    one_node = graph()["nodes"]["ev1"]
    one_node["verifier"] = {
        "kind": "typed_claim",
        "matcher": "regex_fullmatch",
        "accepted_regexes": [r"Alpha lasts exactly 30 hours"],
    }
    full = score_case(
        one_case,
        f"Alpha lasts exactly 30 hours [source]({U1}).",
        ledger(),
        {"nodes": {"ev1": one_node}},
    )
    assert by_id(full, "E1")["C"] is True
    one_node["verifier"]["accepted_regexes"] = [
        r"Alpha lasts exactly 30 hours\."
    ]
    punctuated = score_case(
        one_case,
        f"Alpha lasts exactly 30 hours [source]({U1}).",
        ledger(),
        {"nodes": {"ev1": one_node}},
    )
    assert by_id(punctuated, "E1")["C"] is True
    one_node["verifier"]["accepted_regexes"] = [
        r"Alpha lasts exactly 30 hours"
    ]
    prefixed = score_case(
        one_case,
        f"For context, Alpha lasts exactly 30 hours [source]({U1}).",
        ledger(),
        {"nodes": {"ev1": one_node}},
    )
    assert by_id(prefixed, "E1")["C"] is False

    one_node["verifier"] = {
        "kind": "typed_claim",
        "matcher": "numeric_tolerance",
        "expected": 30,
        "tolerance": 1,
        "unit": "hours",
    }
    numeric = score_case(
        one_case,
        f"Alpha battery life is 30.5 hours [source]({U1}).",
        ledger(),
        {"nodes": {"ev1": one_node}},
    )
    assert by_id(numeric, "E1")["C"] is True
    negated = score_case(
        one_case,
        f"Alpha battery life is not 30.5 hours [source]({U1}).",
        ledger(),
        {"nodes": {"ev1": one_node}},
    )
    assert by_id(negated, "E1")["C"] is False


def test_ledger_envelope_roundtrip_and_fail_closed_loading(tmp_path):
    original = _event(1, "search_result", U1, "visible snippet")
    original["metadata"] = {"query": "alpha", "lane": "test"}
    event = ObservationEvent.from_dict(original)
    roundtrip = ObservationEvent.from_dict(event.to_dict())
    assert roundtrip.metadata == {"query": "alpha", "lane": "test"}

    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps([original]))
    assert load_observation_ledger(bare, expected_run_id="run-v3").complete is False

    complete_empty = tmp_path / "empty-envelope.json"
    complete_empty.write_text(json.dumps({
        "observation_semantics": "observation_ledger_v1",
        "run_id": "run-v3",
        "capture_complete": True,
        "events": [],
    }))
    loaded = load_observation_ledger(complete_empty)
    assert loaded.complete is True
    assert loaded.run_id == "run-v3"

    wrong_run = tmp_path / "empty-wrong-run.json"
    wrong_run.write_text(json.dumps({
        "observation_semantics": "observation_ledger_v1",
        "run_id": "some-other-run",
        "capture_complete": True,
        "events": [],
    }))
    mismatched = load_observation_ledger(wrong_run, expected_run_id="run-v3")
    assert mismatched.complete is False
    assert "observation_run_id_mismatch" in mismatched.withhold_reason_codes

    in_memory_mismatch = score_case(
        case(),
        "",
        {
            "observation_semantics": "observation_ledger_v1",
            "run_id": "some-other-run",
            "capture_complete": True,
            "events": [],
        },
        graph(),
        expected_run_id="run-v3",
    )
    assert in_memory_mismatch["status"] == "withheld"
    assert "observation_run_id_mismatch" in {
        reason["code"] for reason in in_memory_mismatch["withhold_reasons"]
    }

    unattributed = tmp_path / "empty-unattributed.json"
    unattributed.write_text(json.dumps({
        "observation_semantics": "observation_ledger_v1",
        "capture_complete": True,
        "events": [],
    }))
    blind = load_observation_ledger(unattributed)
    assert blind.complete is False
    assert "observation_missing_run_id" in blind.withhold_reason_codes

    missing_events = tmp_path / "missing-events.json"
    missing_events.write_text(json.dumps({
        "observation_semantics": "observation_ledger_v1",
        "run_id": "run-v3",
        "capture_complete": True,
    }))
    assert "observation_events_missing" in load_observation_ledger(
        missing_events
    ).withhold_reason_codes

    missing_semantics = tmp_path / "missing-semantics.json"
    missing_semantics.write_text(json.dumps({
        "run_id": "run-v3", "capture_complete": True, "events": []
    }))
    assert "observation_semantics_mismatch" in load_observation_ledger(
        missing_semantics
    ).withhold_reason_codes


def test_ledger_rejects_missing_hash_forged_page_link_and_blob_traversal():
    missing_hash = _event(1, "search_result", U1, "visible")
    missing_hash["content_sha256"] = ""
    first = ObservationLedger.from_records(
        [missing_hash], expected_run_id="run-v3", capture_complete=True
    )
    assert not first.complete
    assert "observation_missing_content_hash" in first.withhold_reason_codes

    parent = _event(1, "fetch_body", U2, "no link here", status=200)
    forged = _event(2, "page_link", U1, U1, parent=1)
    second = ObservationLedger.from_records(
        [parent, forged], expected_run_id="run-v3", capture_complete=True
    )
    assert not second.complete
    assert "observation_link_not_in_parent" in second.withhold_reason_codes

    traversal = _event(1, "fetch_body", U1, "ignored", status=200)
    traversal.pop("content_text_or_blob_ref")
    traversal["blob_ref"] = "../secret"
    traversal["content_sha256"] = "a" * 64
    third = ObservationLedger.from_records(
        [traversal], expected_run_id="run-v3", capture_complete=True
    )
    assert not third.complete
    assert "observation_invalid_blob_ref" in third.withhold_reason_codes


def test_legacy_run_evidence_jsonl_adapts_without_inventing_snippet_text(tmp_path):
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    digest = sha256_text(BODY1)
    (blobs / digest).write_text(BODY1)
    legacy = tmp_path / "run-v3.jsonl"
    records = [
        {"run_id": "run-v3", "ts": 1.0, "kind": "mark", "phase": "start"},
        {
            "run_id": "run-v3", "ts": 2.0, "kind": "search",
            "endpoint": "/search", "query": "alpha", "urls_returned": [U1],
        },
        {
            "run_id": "run-v3", "ts": 3.0, "kind": "fetch",
            "endpoint": "/fetch", "url": U1, "status": 200,
            "body_sha256": digest, "links": [],
        },
        {"run_id": "run-v3", "ts": 4.0, "kind": "mark", "phase": "end"},
    ]
    legacy.write_text("".join(json.dumps(row) + "\n" for row in records))
    adapted = load_observation_ledger(legacy, expected_run_id="run-v3")
    assert adapted.complete
    assert [event.event_type for event in adapted.events] == [
        "search_result", "fetch_body"
    ]
    assert adapted.events[0].visible_text() is None
    assert adapted.events[0].metadata["legacy_snippet_unavailable"] is True


def test_decidable_wrong_claim_counts_fp_and_critical_contradiction():
    bad_case = case()
    bad_case["decidable_claims"] = [
        {
            "claim_id": "wrong_ev1_runtime",
            "contradicts_slot_id": "E1",
            "critical": True,
            "rejected_matcher": {
                "matcher": "normalized_text",
                "accepted_phrases": ["Alpha lasts only 3 hours"]
            },
        }
    ]
    report = oracle_report() + " Alpha lasts only 3 hours."
    result = score_case(bad_case, report, ledger(), graph())
    assert result["fp"] == 1
    assert result["critical_contradictions"] == 1
    assert result["task_pass"] == 0


def test_score_case_v3_cli_emits_replayable_json(tmp_path):
    case_path = tmp_path / "case.json"
    graph_path = tmp_path / "graph.json"
    ledger_path = tmp_path / "ledger.json"
    report_path = tmp_path / "report.md"
    registry_path = tmp_path / "corpus_registry.json"
    case_path.write_text(json.dumps(case()))
    graph_path.write_text(json.dumps(graph()))
    ledger_path.write_text(json.dumps(ledger().to_dict()))
    report_path.write_text(oracle_report())
    registry = FrozenCorpusRegistry(
        corpus_snapshot="fixture-snapshot-v1",
        entries=(
            FrozenCorpusEntry(
                registry_id="alpha_page",
                source_url=U1,
                source_type="shopping",
                content_sha256=sha256_text(BODY1),
                corpus_snapshot="fixture-snapshot-v1",
            ),
            FrozenCorpusEntry(
                registry_id="noise_page",
                source_url=U2,
                source_type="concept",
                content_sha256=sha256_text(BODY2),
                corpus_snapshot="fixture-snapshot-v1",
            ),
            FrozenCorpusEntry(
                registry_id="unused_page",
                source_url=UNUSED,
                source_type="curated",
                content_sha256=sha256_text("unused frozen body"),
                corpus_snapshot="fixture-snapshot-v1",
            ),
        ),
    )
    registry.save(registry_path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_case_v3.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--case", str(case_path),
            "--report", str(report_path),
            "--ledger", str(ledger_path),
            "--evidence-graph", str(graph_path),
            "--corpus-registry", str(registry_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["task_pass"] == 1
    assert result["verified_research_completion"] == 1.0
    assert result["corpus_registry_hash"] == registry.corpus_sha256
    assert result["corpus_registry_source"] == "argument"
    assert result["protocols"]["scoring_semantics"] == "verified_slots_v1"

    bare_registry = tmp_path / "bare-registry.json"
    bare_registry.write_text(json.dumps([U1, U2, UNUSED]))
    rejected = subprocess.run(
        [
            sys.executable,
            str(script),
            "--case", str(case_path),
            "--report", str(report_path),
            "--ledger", str(ledger_path),
            "--evidence-graph", str(graph_path),
            "--corpus-registry", str(bare_registry),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "corpus registry must be an object" in rejected.stderr


def test_score_case_v3_cli_requires_and_hashes_formal_run_identity(tmp_path):
    formal_case = _valid_formal_case()
    case_path = tmp_path / "formal-case.json"
    case_path.write_text(json.dumps(formal_case), encoding="utf-8")
    case_digest = hashlib.sha256(case_path.read_bytes()).hexdigest()
    public_path = tmp_path / "public-task.json"
    public_path.write_text("sealed public task bytes", encoding="utf-8")
    manifest = _sealed_manifest(formal_case, case_digest)
    manifest_path = tmp_path / "protocol.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report_path = tmp_path / "report.md"
    report_path.write_text(oracle_report(), encoding="utf-8")
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger().to_dict()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_case_v3.py"

    base = [
        sys.executable,
        str(script),
        "--case", str(case_path),
        "--report", str(report_path),
        "--ledger", str(ledger_path),
        "--protocol-manifest", str(manifest_path),
    ]
    missing = subprocess.run(
        base,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0
    assert "formal scoring requires" in missing.stderr

    completed = subprocess.run(
        [
            *base,
            "--public-task", str(public_path),
            "--agent", "agent-a",
            "--replicate", "2",
            "--expected-run-id", "run-v3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "scored"
    assert result["agent"] == "agent-a"
    assert result["replicate"] == 2
    assert result["case_artifact_sha256"] == case_digest
    assert result["public_task_sha256"] == hashlib.sha256(
        public_path.read_bytes()
    ).hexdigest()

    injected_seed = subprocess.run(
        [
            *base,
            "--public-task", str(public_path),
            "--agent", "agent-a",
            "--replicate", "2",
            "--expected-run-id", "run-v3",
            "--seed-url", U1,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert injected_seed.returncode != 0
    assert "formal scoring forbids --seed-url" in injected_seed.stderr
