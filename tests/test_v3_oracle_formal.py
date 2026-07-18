from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from src.eval.case_schema_v3 import (
    decidable_claims_sha256,
    proof_subgraph_fingerprint,
    validate_case,
)
from src.eval.evidence_graph import (
    EVIDENCE_GRAPH_MANIFEST_VERSION,
    canonical_json_bytes,
)
from src.eval.observation_ledger import sha256_text
from src.eval.oracle_validation_v3 import (
    REQUIRED_ADVERSARIAL_CATEGORIES,
    SUITE_SCHEMA,
    validate_oracle_suite,
    verify_validation_result,
)
from src.eval.protocol_manifest_v3 import (
    PROTOCOL_MANIFEST_SCHEMA,
    scorer_implementation_sha256,
)
from src.eval.protocol_v3 import protocol_stamp
from src.eval.release_gate_v3 import _replay_oracle_suite
from src.tasks.query_renderer_v3 import render_task
from test_case_schema_v3 import valid_case_dict


BODIES = {
    "ev_seal": "sealbody",
    "ev_noise": "noisebod",
}
FABRICATED = "http://localhost:8080/not-in-the-frozen-registry"


def _sha_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _formal_case() -> dict:
    draft = valid_case_dict()
    for source in draft["evidence_sources"]:
        body = BODIES[source["evidence_id"]]
        digest = sha256_text(body)
        source["content_sha256"] = digest
        source["support_spans"][0].update({
            "start": 0,
            "end": len(body.encode("utf-8")),
            "sha256": digest,
        })
    spec = validate_case(draft)
    graph_digest = sha256_text("formal oracle graph")
    registry_digest = sha256_text("formal oracle registry")
    evidence_ids = sorted(
        slot.claim_id
        for slot in spec.slots
        if slot.type == "evidence" and slot.critical
    )
    case = deepcopy(draft)
    case.update({
        "corpus_registry_urls": sorted([
            "http://localhost:8080/start",
            *(source.source_url for source in spec.evidence_sources),
        ]),
        "corpus_registry_hash": registry_digest,
        "discovery_root_urls": ["http://localhost:8080/start"],
        "formal_bindings": {
            "formal": True,
            "evidence_catalog_sha256": sha256_text("formal evidence catalog"),
            "support_spans_sha256": sha256_text("formal support spans"),
            "graph_edges_sha256": sha256_text("formal graph edges"),
            "evidence_graph_sha256": graph_digest,
            "corpus_registry_sha256": registry_digest,
            "reachability_manifest_sha256": sha256_text("formal reachability"),
            "decidable_claims_sha256": decidable_claims_sha256(spec),
            "proof_subgraph_sha256": proof_subgraph_fingerprint(spec),
            "root_node_ids": ["seed_root"],
            "critical_evidence_node_ids": evidence_ids,
            "reachable_node_ids": evidence_ids,
        },
    })
    validate_case(case)
    return case


def _manifest(case: dict, case_sha: str, public_sha: str) -> dict:
    spec = validate_case(case)
    task_id = spec.task_id
    graph_sha = spec.formal_bindings.evidence_graph_sha256
    registry_sha = spec.formal_bindings.corpus_registry_sha256
    protocols = protocol_stamp(
        corpus_snapshot=spec.corpus_snapshot,
        task_ids=[task_id],
        case_hashes={task_id: case_sha},
        public_task_hashes={task_id: public_sha},
        evidence_graph_hash=graph_sha,
        corpus_registry_hash=registry_sha,
    )
    payload = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": protocols,
        "task_ids": [task_id],
        "task_clusters": {task_id: spec.cluster_id},
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
            task_id: spec.proof_subgraph_sha256,
        },
        "case_hashes": {task_id: case_sha},
        "public_task_hashes": {task_id: public_sha},
        "scorer_implementation_sha256": scorer_implementation_sha256(),
        "evidence_graph_artifact": {
            "manifest_schema": EVIDENCE_GRAPH_MANIFEST_VERSION,
            "evidence_graph_hash": graph_sha,
            "corpus_registry_hash": registry_sha,
            "graph_corpus_hash": sha256_text("formal graph corpus"),
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


def _event(run_id, event_id, kind, url, text, parent=None):
    return {
        "run_id": run_id,
        "event_id": event_id,
        "timestamp": float(event_id),
        "event_type": kind,
        "request_url": url,
        "canonical_url": url,
        "parent_event_id": parent,
        "content_sha256": sha256_text(text),
        "content_text_or_blob_ref": text,
        "http_status": 200 if kind == "fetch_body" else None,
        "observable": True,
    }


def _ledger(run_id: str, case: dict, mode: str = "full") -> dict:
    urls = {
        source["evidence_id"]: source["source_url"]
        for source in case["evidence_sources"]
    }
    if mode == "empty":
        events = []
    elif mode == "guessed":
        events = [
            _event(run_id, 1, "fetch_body", urls["ev_seal"], BODIES["ev_seal"]),
            _event(run_id, 2, "search_result", urls["ev_noise"], "noise result"),
            _event(
                run_id,
                3,
                "fetch_body",
                urls["ev_noise"],
                BODIES["ev_noise"],
                parent=2,
            ),
        ]
    else:
        events = [
            _event(run_id, 1, "search_result", urls["ev_seal"], "seal result"),
            _event(
                run_id,
                2,
                "fetch_body",
                urls["ev_seal"],
                BODIES["ev_seal"],
                parent=1,
            ),
            _event(run_id, 3, "search_result", urls["ev_noise"], "noise result"),
            _event(
                run_id,
                4,
                "fetch_body",
                urls["ev_noise"],
                BODIES["ev_noise"],
                parent=3,
            ),
        ]
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": events,
    }


def _parts(case: dict) -> tuple[str, str, str, str, str]:
    urls = {
        source["evidence_id"]: source["source_url"]
        for source in case["evidence_sources"]
    }
    evidence = (
        f"ev_seal supports the conclusion [seal]({urls['ev_seal']}). "
        f"ev_noise supports the conclusion [noise]({urls['ev_noise']})."
    )
    bridges = (
        "The seal evidence changes the expected noise-control result. "
        "The concept evidence and experience evidence require reconciliation. "
        "The reconciled evidence supports a candidate-level comparison."
    )
    decision = (
        "Form A is the final conclusion under the stated priorities. Form A."
    )
    one_source = (
        f"ev_seal supports the conclusion [seal]({urls['ev_seal']})."
    )
    wrong_binding = (
        f"ev_seal supports the conclusion [wrong]({urls['ev_noise']}). "
        f"ev_noise supports the conclusion [wrong]({urls['ev_seal']})."
    )
    return evidence, bridges, decision, one_source, wrong_binding


def _positive(run_id: str, kind: str, case: dict) -> dict:
    evidence, bridges, decision, _, _ = _parts(case)
    entry = {
        "run_id": run_id,
        "kind": kind,
        "answer": "form_a",
        "report": {"inline": f"{evidence}\n\n{bridges} {decision}"},
        "ledger": {"inline": _ledger(run_id, case)},
    }
    if kind == "minimal":
        entry["minimal_evidence_ids"] = ["ev_seal", "ev_noise"]
    if kind == "human":
        entry["manual_record"] = {
            "origin": "manual",
            "reviewer": "formal-human-reviewer",
            "solve_minutes": 3.5,
            "access_path": [
                source["source_url"] for source in case["evidence_sources"]
            ],
            "attested": True,
            "synthetic": False,
        }
    return entry


def _negative(category: str, case: dict) -> dict:
    run_id = f"formal-negative-{category}"
    evidence, bridges, decision, one_source, wrong_binding = _parts(case)
    full = f"{evidence}\n\n{bridges} {decision}"
    ledger = _ledger(run_id, case)
    answer = None
    if category == "url_dump":
        report = " ".join(
            f"[source]({source['source_url']})"
            for source in case["evidence_sources"]
        )
    elif category == "correct_plus_fabricated":
        report = f"{full}\n\nFabricated extra source: {FABRICATED}"
    elif category == "fetch_all_no_answer":
        report = "I opened every relevant frozen page."
    elif category == "unsupported_answer":
        report = full
        ledger = _ledger(run_id, case, "empty")
        answer = "form_a"
    elif category == "fact_dump":
        report = evidence
    elif category == "single_source":
        report = f"{one_source}\n\n{bridges} {decision}"
    elif category == "guessed_then_fetched":
        report = full
        ledger = _ledger(run_id, case, "guessed")
    elif category == "wrong_binding":
        report = f"{wrong_binding}\n\n{bridges} {decision}"
    elif category == "contradictory_decision":
        report = (
            f"{evidence}\n\n{bridges} "
            "Form B is the final conclusion under the stated priorities. Form B."
        )
    elif category == "silence":
        report = ""
        ledger = _ledger(run_id, case, "empty")
    else:
        raise AssertionError(category)
    entry = {
        "run_id": run_id,
        "category": category,
        "report": {"inline": report},
        "ledger": {"inline": ledger},
    }
    if answer is not None:
        entry["answer"] = answer
    return entry


def test_real_formal_oracle_path_replays_case_and_public_task_bytes(tmp_path):
    case = _formal_case()
    case_path = tmp_path / "case.json"
    public_path = tmp_path / "public-task.json"
    protocol_path = tmp_path / "protocol.json"
    _write_json(case_path, case)
    _write_json(public_path, render_task(case))
    protocol = _manifest(case, _sha_file(case_path), _sha_file(public_path))
    _write_json(protocol_path, protocol)

    graph = {
        "nodes": {
            source["evidence_id"]: source
            for source in case["evidence_sources"]
        }
    }
    suite = {
        "schema": SUITE_SCHEMA,
        "suite_id": "formal-oracle-positive-path-v1",
        "validation_scope": "formal",
        "case": {
            "path": case_path.name,
            "sha256": _sha_file(case_path),
        },
        "public_task": {
            "path": public_path.name,
            "sha256": _sha_file(public_path),
        },
        "evidence_graph": {"inline": graph},
        "protocols": {
            "path": protocol_path.name,
            "sha256": _sha_file(protocol_path),
        },
        "oracles": [
            _positive("formal-machine", "machine", case),
            _positive("formal-human", "human", case),
            _positive("formal-minimal", "minimal", case),
        ],
        "adversarial": [
            _negative(category, case)
            for category in REQUIRED_ADVERSARIAL_CATEGORIES
        ],
    }
    suite_path = tmp_path / "oracle-suite.json"
    _write_json(suite_path, suite)
    suite_sha256 = _sha_file(suite_path)
    result = validate_oracle_suite(
        suite,
        base_dir=tmp_path,
        suite_sha256=suite_sha256,
    )
    replay_errors: list[str] = []
    replayed = _replay_oracle_suite(
        suite,
        source=suite_path,
        suite_sha256=suite_sha256,
        path="formal-suite",
        errors=replay_errors,
    )

    assert verify_validation_result(result)
    assert replay_errors == []
    assert replayed == result
    assert result["status"] == "validated"
    assert result["formal_pilot_passed"] is True
    assert result["formal_human_validation_passed"] is True
    assert result["synthetic_only"] is False
    assert result["requires_real_human_followup"] is False
    assert result["artifacts"]["case"]["hash_basis"] == "raw_bytes"
    assert result["artifacts"]["public_task"]["sha256"] == _sha_file(public_path)
    assert all(
        row["score"]["status"] == "scored"
        for row in [*result["oracle_results"], *result["adversarial_results"]]
    )
