from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import src.eval.oracle_validation_v3 as oracle_module
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
    OracleSuiteValidationError,
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
from src.eval.slot_scorer import score_proof_steps
from src.tasks.query_renderer_v3 import render_task
from test_case_schema_v3 import proof_step_case_dict
from test_v3_oracle_adversarial import _suite as legacy_suite
from test_v3_oracle_formal import (
    BODIES,
    _event as formal_event,
    _negative as formal_negative,
    _positive as formal_positive,
    _sha_file,
    _write_json,
)


def _proof_suite() -> dict:
    suite = copy.deepcopy(legacy_suite())
    case = suite["case"]["inline"]
    steps = []
    for slot in case["slots"]:
        step = copy.deepcopy(slot)
        step["step_id"] = step.pop("slot_id")
        step["vital"] = step.pop("critical")
        steps.append(step)
    case["evaluator_view"] = {"required_proof_steps": steps}
    suite["scoring_semantics"] = "proof_steps_v1"
    return suite


def _formal_proof_case() -> dict:
    draft = proof_step_case_dict()
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
    graph_digest = sha256_text("formal proof oracle graph")
    registry_digest = sha256_text("formal proof oracle registry")
    evidence_ids = sorted(
        slot.claim_id
        for slot in spec.slots
        if slot.type == "evidence" and slot.critical
    )
    case = copy.deepcopy(draft)
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


def _formal_proof_manifest(case: dict, case_sha: str, public_sha: str) -> dict:
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
        scoring_semantics="proof_steps_v1",
    )
    manifest = {
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
                "registry_entries": len(case["corpus_registry_urls"]),
                "nodes": len(case["evidence_sources"]),
                "edges": len(case["evidence_sources"]),
                "support_spans": sum(
                    len(source["support_spans"])
                    for source in case["evidence_sources"]
                ),
            },
        },
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()
    return manifest


def _formal_alternative_proof_case() -> tuple[dict, dict[str, str]]:
    draft = proof_step_case_dict()
    alternate = copy.deepcopy(draft["evidence_sources"][0])
    alternate.update(
        {
            "evidence_id": "ev_seal_alt",
            "subject": "ev_seal_alt",
            "source_url": "http://localhost:8080/seal-equivalent",
        }
    )
    alternate["verifier"]["accepted_phrases"] = [
        "ev_seal_alt supports the conclusion"
    ]
    alternate["verifier"]["accepted_aliases"] = ["ev_seal_alt"]
    alternate["support_spans"][0].update(
        {
            "support_span_id": "span_seal_alt",
            "evidence_id": "ev_seal_alt",
            "source_url": alternate["source_url"],
        }
    )
    draft["evidence_sources"].append(alternate)
    draft["evaluator_view"]["propositions"] = ["P_SEAL", "ev_noise"]
    e1 = draft["evaluator_view"]["required_proof_steps"][0]
    e1["claim"] = "P_SEAL"
    e1["acceptable_support"]["source_ids"] = ["ev_seal", "ev_seal_alt"]
    e1["acceptable_support"]["support_relation"] = "SUPPORTED_BY"
    bodies = {**BODIES, "ev_seal_alt": "altsealb"}
    for source in draft["evidence_sources"]:
        body = bodies[source["evidence_id"]]
        digest = sha256_text(body)
        source["content_sha256"] = digest
        source["support_spans"][0].update(
            {
                "start": 0,
                "end": len(body.encode("utf-8")),
                "sha256": digest,
            }
        )
    spec = validate_case(draft)
    graph_digest = sha256_text("formal alternative proof oracle graph")
    registry_digest = sha256_text("formal alternative proof oracle registry")
    case = copy.deepcopy(draft)
    case.update(
        {
            "corpus_registry_urls": sorted(
                [
                    "http://localhost:8080/start",
                    *(source.source_url for source in spec.evidence_sources),
                ]
            ),
            "corpus_registry_hash": registry_digest,
            "discovery_root_urls": ["http://localhost:8080/start"],
            "formal_bindings": {
                "formal": True,
                "evidence_catalog_sha256": sha256_text(
                    "formal alternative evidence catalog"
                ),
                "support_spans_sha256": sha256_text(
                    "formal alternative support spans"
                ),
                "graph_edges_sha256": sha256_text(
                    "formal alternative graph edges"
                ),
                "evidence_graph_sha256": graph_digest,
                "corpus_registry_sha256": registry_digest,
                "reachability_manifest_sha256": sha256_text(
                    "formal alternative reachability"
                ),
                "decidable_claims_sha256": decidable_claims_sha256(spec),
                "proof_subgraph_sha256": proof_subgraph_fingerprint(spec),
                "root_node_ids": ["seed_root"],
                "critical_evidence_node_ids": spec.critical_support_source_ids,
                "reachable_node_ids": spec.critical_support_source_ids,
            },
        }
    )
    validate_case(case)
    return case, bodies


def test_default_suite_keeps_verified_slots_and_proof_steps_is_explicit():
    legacy = validate_oracle_suite(legacy_suite())
    proof = validate_oracle_suite(_proof_suite())

    legacy_score = legacy["oracle_results"][0]["score"]
    assert legacy_score["protocols"]["scoring_semantics"] == "verified_slots_v1"
    assert legacy_score["task_pass"] == 1
    assert legacy_score["verified_recall"] == 1.0
    assert "step_results" not in legacy_score

    assert verify_validation_result(proof)
    proof_score = proof["oracle_results"][0]["score"]
    assert proof_score["scoring_semantics"] == "proof_steps_v1"
    assert proof_score["protocols"]["scoring_semantics"] == "proof_steps_v1"
    assert proof_score["partial_completion"] == 1.0
    assert proof_score["full_pass"] == 1
    assert proof_score["final_answer_pass"] is True
    assert proof_score["scoring_input_sha256"] != legacy_score["scoring_input_sha256"]
    assert all(
        row["passed"]
        == all(row[axis] for axis in ("D", "O", "S", "B", "R"))
        for row in proof_score["step_results"]
    )


def test_proof_suite_replays_all_adversarial_categories_in_new_semantics():
    result = validate_oracle_suite(_proof_suite())
    negatives = {
        row["category"]: row["score"] for row in result["adversarial_results"]
    }

    assert all(score["scoring_semantics"] == "proof_steps_v1" for score in negatives.values())
    assert all(score["full_pass"] == 0 for score in negatives.values())
    assert negatives["url_dump"]["partial_completion"] == 0.0
    assert negatives["correct_plus_fabricated"]["partial_completion"] == 1.0
    assert negatives["correct_plus_fabricated"]["fabricated_citations"] == 1
    assert negatives["fact_dump"]["partial_completion"] == 0.5
    assert negatives["contradictory_decision"]["final_answer_pass"] is False
    guessed = negatives["guessed_then_fetched"]["step_results"]
    assert any(
        row["D"] is False
        and row["reason_codes"]["D"] == "guessed_then_fetched"
        for row in guessed
    )


def test_formal_proof_suite_binds_v3_replay_identity_without_legacy_fields(tmp_path):
    case = _formal_proof_case()
    case_path = tmp_path / "case.json"
    public_path = tmp_path / "public-task.json"
    protocol_path = tmp_path / "protocol.json"
    _write_json(case_path, case)
    _write_json(public_path, render_task(case))
    manifest = _formal_proof_manifest(
        case,
        _sha_file(case_path),
        _sha_file(public_path),
    )
    _write_json(protocol_path, manifest)
    suite = {
        "schema": SUITE_SCHEMA,
        "suite_id": "formal-proof-oracle-v1",
        "validation_scope": "formal",
        "scoring_semantics": "proof_steps_v1",
        "case": {"path": case_path.name, "sha256": _sha_file(case_path)},
        "public_task": {
            "path": public_path.name,
            "sha256": _sha_file(public_path),
        },
        "evidence_graph": {
            "inline": {
                "nodes": {
                    source["evidence_id"]: source
                    for source in case["evidence_sources"]
                }
            }
        },
        "protocols": {
            "path": protocol_path.name,
            "sha256": _sha_file(protocol_path),
        },
        "oracles": [
            formal_positive("formal-machine", "machine", case),
            formal_positive("formal-human", "human", case),
            formal_positive("formal-minimal", "minimal", case),
        ],
        "adversarial": [
            formal_negative(category, case)
            for category in REQUIRED_ADVERSARIAL_CATEGORIES
        ],
    }

    result = validate_oracle_suite(suite, base_dir=tmp_path)
    all_scores = [
        *(row["score"] for row in result["oracle_results"]),
        *(row["score"] for row in result["adversarial_results"]),
    ]
    assert result["formal_human_validation_passed"] is True
    assert all(score["scoring_semantics"] == "proof_steps_v1" for score in all_scores)
    assert all(score["protocol_manifest_sha256"] == manifest["manifest_sha256"] for score in all_scores)
    assert all(score["scoring_input_sha256"] for score in all_scores)
    assert all(not (set(score) & oracle_module._LEGACY_SCORE_FIELDS) for score in all_scores)


def test_formal_proof_score_accepts_compiler_bound_equivalent_source() -> None:
    case, bodies = _formal_alternative_proof_case()
    case_sha = hashlib.sha256(canonical_json_bytes(case)).hexdigest()
    public_task = render_task(case)
    public_sha = hashlib.sha256(canonical_json_bytes(public_task)).hexdigest()
    manifest = _formal_proof_manifest(case, case_sha, public_sha)
    run_id = "formal-equivalent-source"
    urls = {
        source["evidence_id"]: source["source_url"]
        for source in case["evidence_sources"]
    }
    ledger = {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": [
            formal_event(
                run_id,
                1,
                "search_result",
                urls["ev_seal_alt"],
                "equivalent seal result",
            ),
            formal_event(
                run_id,
                2,
                "fetch_body",
                urls["ev_seal_alt"],
                bodies["ev_seal_alt"],
                parent=1,
            ),
            formal_event(
                run_id,
                3,
                "search_result",
                urls["ev_noise"],
                "noise result",
            ),
            formal_event(
                run_id,
                4,
                "fetch_body",
                urls["ev_noise"],
                bodies["ev_noise"],
                parent=3,
            ),
        ],
    }
    report = (
        f"ev_seal_alt supports the conclusion [seal]({urls['ev_seal_alt']}). "
        f"ev_noise supports the conclusion [noise]({urls['ev_noise']}).\n\n"
        "The seal evidence changes the expected noise-control result. "
        "The concept evidence and experience evidence require reconciliation. "
        "The reconciled evidence supports a candidate-level comparison. "
        "Form A is the final conclusion under the stated priorities. Form A."
    )

    score = score_proof_steps(
        case,
        report,
        ledger,
        protocols=manifest,
        expected_run_id=run_id,
        case_artifact_sha256=case_sha,
        public_task_sha256=public_sha,
        agent="oracle:equivalent-source",
        replicate=1,
    )
    e1 = next(row for row in score["step_results"] if row["step_id"] == "E1")

    assert score["withheld"] is False
    assert score["full_pass"] == 1
    assert e1["matched_support_source_id"] == "ev_seal_alt"
    assert e1["admissible_support_source_ids"] == ["ev_seal", "ev_seal_alt"]


def test_proof_step_validator_rejects_axis_conjunction_drift(monkeypatch):
    real_scorer = oracle_module.score_proof_steps

    def drifted(*args, **kwargs):
        score = real_scorer(*args, **kwargs)
        if score.get("step_results"):
            score["step_results"][0]["passed"] = False
        return score

    monkeypatch.setattr(oracle_module, "score_proof_steps", drifted)
    with pytest.raises(OracleSuiteValidationError, match="D AND O AND S AND B AND R"):
        validate_oracle_suite(_proof_suite())


def test_formal_proof_score_rejects_nonformal_legacy_aliases():
    result = validate_oracle_suite(_proof_suite())
    score = result["oracle_results"][0]["score"]

    with pytest.raises(OracleSuiteValidationError, match="leaks legacy score fields"):
        oracle_module._validate_proof_score_shape(
            score,
            run_id="oracle-machine",
            expected_agent="oracle:machine",
            formal=True,
        )


def test_unknown_semantics_and_cli_semantics_mismatch_fail_closed(tmp_path):
    unknown = _proof_suite()
    unknown["scoring_semantics"] = "proof_steps_v2"
    with pytest.raises(OracleSuiteValidationError, match="scoring_semantics must be"):
        validate_oracle_suite(unknown)

    suite_path = tmp_path / "legacy-suite.json"
    suite_path.write_text(json.dumps(legacy_suite()), encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validate_oracle_suite_v3.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--suite",
            str(suite_path),
            "--scoring-semantics",
            "proof_steps_v1",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "does not match --scoring-semantics" in completed.stderr
