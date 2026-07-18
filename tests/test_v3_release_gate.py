from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import src.eval.release_gate_v3_formal86 as release_gate_module
from scripts.check_v3_release_readiness import main as release_cli
from src.eval.evidence_graph import EVIDENCE_GRAPH_MANIFEST_VERSION
from src.eval.oracle_validation_v3 import (
    REQUIRED_ADVERSARIAL_CATEGORIES,
    VALIDATION_SCHEMA,
    VALIDATION_SEMANTICS,
)
from src.eval.protocol_manifest_v3 import (
    PROTOCOL_MANIFEST_SCHEMA,
    scorer_implementation_sha256,
)
from src.eval.protocol_v3 import proof_steps_protocol_stamp
from src.eval.release_gate_v3 import (
    RELEASE_READINESS_SCHEMA as LEGACY_RELEASE_READINESS_SCHEMA,
    check_release_readiness as check_legacy_release_readiness,
    new_release_readiness_template as new_legacy_release_readiness_template,
)
from src.eval.release_gate_v3_formal86 import (
    ACQUISITION_PATH_CONFORMANCE_SCHEMA,
    ACQUISITION_PATH_COVERAGE_SCHEMA,
    BYPASS_AUDIT_SCHEMA,
    DEVELOPMENT_TASK_COUNT,
    FORMAL_TASK_COUNT,
    ISOLATION_AUDIT_SCHEMA,
    MAINTAINED_HARNESSES,
    ORACLE_RELEASE_BUNDLE_SCHEMA,
    PUBLICATION_SURFACES,
    RELEASE_READINESS_SCHEMA,
    canonical_json_bytes,
    check_release_readiness,
    new_release_readiness_template,
)


MOTIFS = (
    "claim_verification",
    "evidence_reconciliation",
    "multi_branch_synthesis",
    "causal_or_evolution_explanation",
    "constraint_match_and_select",
)


def _write(path: Path, value: object) -> dict[str, str]:
    if isinstance(value, (dict, list)):
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
    else:
        payload = str(value).encode("utf-8")
    path.write_bytes(payload)
    return {"path": path.name, "sha256": hashlib.sha256(payload).hexdigest()}


@pytest.fixture(autouse=True)
def _stub_expensive_formal_suite_replay(monkeypatch):
    """Exercise exact suite/result wiring without rerunning 86 full scorers."""

    def replay(raw, *, source, suite_sha256, path, errors):
        del source, suite_sha256
        if not isinstance(raw, dict) or not isinstance(
            raw.get("expected_result"), dict
        ):
            errors.append(f"{path}: invalid test suite fixture")
            return None
        return raw["expected_result"]

    monkeypatch.setattr(release_gate_module, "_replay_oracle_suite", replay)


def _protocol_manifest(
    tmp_path: Path, task_ids: list[str]
) -> tuple[dict[str, str], dict]:
    graph_hash = "2" * 64
    registry_hash = "3" * 64
    case_hashes = {task_id: "4" * 64 for task_id in task_ids}
    public_hashes = {task_id: "5" * 64 for task_id in task_ids}
    payload = {
        "schema": PROTOCOL_MANIFEST_SCHEMA,
        "protocols": proof_steps_protocol_stamp(
            corpus_snapshot="corpus-v3-test",
            task_ids=task_ids,
            case_hashes=case_hashes,
            public_task_hashes=public_hashes,
            evidence_graph_hash=graph_hash,
            corpus_registry_hash=registry_hash,
        ),
        "task_ids": task_ids,
        "task_clusters": {task_id: "cluster-1" for task_id in task_ids},
        "task_contracts": {
            task_id: {
                "cluster_id": "cluster-1",
                "motif": MOTIFS[index % len(MOTIFS)],
                "declared_proof_depth": 2,
                "minimum_reasoning_depth": 2,
                "required_research_subgoals": 4,
                "cross_source_bridges": 2,
                "single_page_sufficient": False,
            }
            for index, task_id in enumerate(task_ids)
        },
        "proof_subgraph_fingerprints": {
            task_id: "1" * 64 for task_id in task_ids
        },
        "case_hashes": case_hashes,
        "public_task_hashes": public_hashes,
        "scorer_implementation_sha256": scorer_implementation_sha256(),
        "evidence_graph_artifact": {
            "manifest_schema": EVIDENCE_GRAPH_MANIFEST_VERSION,
            "evidence_graph_hash": graph_hash,
            "corpus_registry_hash": registry_hash,
            "graph_corpus_hash": "6" * 64,
            "counts": {
                "registry_entries": 1,
                "nodes": 1,
                "edges": 0,
                "support_spans": 1,
            },
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return _write(tmp_path / "protocol.json", payload), payload


def _score_row(
    *,
    run_id: str,
    discriminator: str,
    value: str,
    task_pass: int,
    task_id: str,
    protocol: dict,
) -> dict:
    passed = bool(task_pass)
    steps = [
        _proof_step("E1", "evidence", passed, ("source:evidence",)),
        _proof_step("B1", "bridge", passed, ("synthesis",)),
        _proof_step("D1", "decision", passed, ("final_answer",)),
    ]
    passed_steps = sum(1 for step in steps if step["passed"])
    final_answer_pass = passed
    failure_reasons = [] if passed else [
        {
            "reason_code": "vital_proof_steps_failed",
            "step_ids": ["E1", "B1", "D1"],
        },
        {
            "reason_code": "final_answer_contract_failed",
            "step_ids": ["D1"],
        },
    ]
    agent = (
        f"oracle:{value}"
        if discriminator == "kind"
        else f"adversarial:{value}"
    )
    identity = {
        "run_id": run_id,
        "agent": agent,
        "task_id": task_id,
        "replicate": 1,
        "cluster_id": protocol["task_clusters"][task_id],
        "report_sha256": "7" * 64,
        "observation_ledger_sha256": "8" * 64,
        "case_artifact_sha256": protocol["case_hashes"][task_id],
        "public_task_sha256": protocol["public_task_hashes"][task_id],
        "protocol_manifest_sha256": protocol["manifest_sha256"],
        "corpus_registry_hash": protocol["protocols"]["corpus_registry_hash"],
    }
    score = {
        **identity,
        "scoring_semantics": "proof_steps_v1",
        "status": "scored",
        "withheld": False,
        "scorer_observability_complete": True,
        "step_results": steps,
        "required_step_ids": ["E1", "B1", "D1"],
        "passed_steps": passed_steps,
        "required_steps": len(steps),
        "partial_completion": passed_steps / len(steps),
        "full_pass": int(passed),
        "final_answer_pass": final_answer_pass,
        "full_pass_failure_reasons": failure_reasons,
        "route_coverage": _proof_route(steps),
        "acquisition_diagnostics": {
            "metric": "acquisition_diagnostics_v1",
            "required_evidence_steps": 1,
            "discovery_licensed": int(passed),
            "content_observed": int(passed),
            "content_supported": int(passed),
            "guessed_then_fetched": 0,
            "score_bearing": False,
        },
        "critical_contradictions": 0,
        "fabricated_citations": 0,
        "protocols": dict(protocol["protocols"]),
    }
    score["scoring_input_sha256"] = hashlib.sha256(
        canonical_json_bytes({"version": "dra_v3_scoring_input_v3", **identity})
    ).hexdigest()
    return {
        "run_id": run_id,
        discriminator: value,
        "report_artifact": {
            "source": "path",
            "relative_path": f"{run_id}.md",
            "sha256": "7" * 64,
            "hash_basis": "raw_bytes",
        },
        "ledger_artifact": {
            "source": "path",
            "relative_path": f"{run_id}.ledger.json",
            "sha256": "8" * 64,
            "hash_basis": "raw_bytes",
        },
        "score_sha256": hashlib.sha256(canonical_json_bytes(score)).hexdigest(),
        "score": score,
    }


def _proof_step(
    step_id: str, step_type: str, passed: bool, branches: tuple[str, ...]
) -> dict:
    axes = {
        "D": passed,
        "O": passed,
        "S": passed,
        "B": passed,
        "R": True if step_type == "evidence" else passed,
    }
    row = {
        "step_id": step_id,
        "type": step_type,
        "vital": True,
        "required": True,
        "route_branches": list(branches),
        **axes,
        "passed": all(axes.values()),
    }
    if step_type == "evidence":
        row["discovery_class"] = "searched" if passed else "not_discovered"
    return row


def _proof_coverage(steps: list[dict]) -> dict:
    passed = sum(1 for step in steps if step["passed"])
    return {
        "required_steps": len(steps),
        "passed_steps": passed,
        "coverage": passed / len(steps) if steps else 0.0,
    }


def _proof_route(steps: list[dict]) -> dict:
    branches: dict[str, list[dict]] = {}
    for step in steps:
        for branch in step["route_branches"]:
            branches.setdefault(branch, []).append(step)
    return {
        "metric": "route_coverage_v1",
        "overall": _proof_coverage(steps),
        "by_type": {
            "evidence": _proof_coverage(
                [step for step in steps if step["type"] == "evidence"]
            ),
            "bridge": _proof_coverage(
                [step for step in steps if step["type"] == "bridge"]
            ),
            "final_answer": _proof_coverage(
                [step for step in steps if step["type"] == "decision"]
            ),
        },
        "by_branch": {
            branch: _proof_coverage(rows)
            for branch, rows in sorted(branches.items())
        },
        "score_bearing": False,
    }


def _validation_result(
    task_id: str, protocol_file_sha256: str, protocol: dict
) -> dict:
    result = {
        "schema": VALIDATION_SCHEMA,
        "validation_semantics": VALIDATION_SEMANTICS,
        "suite_id": f"suite-{task_id}",
        "suite_sha256": "9" * 64,
        "task_id": task_id,
        "validation_scope": "formal",
        "validation_tier": "formal_human_attested",
        "status": "validated",
        "artifacts": {
            "case": {
                "source": "path",
                "relative_path": f"{task_id}.case.json",
                "sha256": protocol["case_hashes"][task_id],
                "hash_basis": "raw_bytes",
            },
            "public_task": {
                "source": "path",
                "relative_path": f"{task_id}.public-task.json",
                "sha256": protocol["public_task_hashes"][task_id],
                "hash_basis": "raw_bytes",
            },
            "evidence_graph": {
                "source": "path",
                "relative_path": "nodes.jsonl",
                "sha256": "b" * 64,
                "hash_basis": "raw_bytes",
            },
            "protocols": {
                "source": "path",
                "relative_path": "protocol.json",
                "sha256": protocol_file_sha256,
                "hash_basis": "raw_bytes",
            },
        },
        "oracle_results": [
            _score_row(
                run_id=f"{task_id}-{kind}",
                discriminator="kind",
                value=kind,
                task_pass=1,
                task_id=task_id,
                protocol=protocol,
            )
            for kind in ("human", "machine", "minimal")
        ],
        "adversarial_results": [
            _score_row(
                run_id=f"{task_id}-{category}",
                discriminator="category",
                value=category,
                task_pass=0,
                task_id=task_id,
                protocol=protocol,
            )
            for category in REQUIRED_ADVERSARIAL_CATEGORIES
        ],
        "manual_human_record": {
            "origin": "manual",
            "reviewer": "human-oracle-reviewer",
            "solve_minutes": 12.0,
            "access_path": ["http://localhost/evidence"],
            "attested": True,
            "synthetic": False,
        },
        "manual_human_status": "attested_and_replayed",
        "formal_human_validation_passed": True,
        "formal_pilot_passed": True,
        "synthetic_only": False,
        "requires_real_human_followup": False,
        "required_adversarial_categories": list(REQUIRED_ADVERSARIAL_CATEGORIES),
    }
    result["validation_sha256"] = hashlib.sha256(
        canonical_json_bytes(result)
    ).hexdigest()
    return result


def _signed(name: str) -> dict[str, str]:
    return {
        "name": name,
        "reviewed_at": "2026-07-15",
        "signature": f"signed-by-{name}",
    }


def _ledger(run_id: str) -> dict:
    text = "captured harness observation"
    return {
        "observation_semantics": "observation_ledger_v1",
        "run_id": run_id,
        "capture_complete": True,
        "events": [
            {
                "run_id": run_id,
                "event_id": 1,
                "timestamp": 1.0,
                "event_type": "search_result",
                "request_url": "http://localhost:8090/start",
                "canonical_url": "http://localhost:8090/start",
                "parent_event_id": None,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "content_text_or_blob_ref": text,
                "http_status": None,
                "observable": True,
            }
        ],
    }


def _path_artifacts(
    tmp_path: Path,
    *,
    harness_id: str,
    path_id: str,
    task_id: str,
    run_id: str,
) -> dict:
    stem = f"{harness_id}-{path_id}"
    conformance = {
        "schema": ACQUISITION_PATH_CONFORMANCE_SCHEMA,
        "status": "passed",
        "harness_id": harness_id,
        "acquisition_path_id": path_id,
        "development_task_id": task_id,
        "run_id": run_id,
        "search_produces_s": True,
        "fetch_produces_f_with_body_sha256": True,
        "fetched_body_produces_l": True,
        "l_only_denies_body_support": True,
        "f_only_marks_guessed_then_fetched": True,
        "citation_backreferences_observation": True,
    }
    common = {
        "status": "passed",
        "harness_id": harness_id,
        "acquisition_path_id": path_id,
        "run_id": run_id,
    }
    return {
        "ledger": _write(tmp_path / f"{stem}-ledger.json", _ledger(run_id)),
        "conformance_result": _write(
            tmp_path / f"{stem}-conformance.json", conformance
        ),
        "isolation_audit": _write(
            tmp_path / f"{stem}-isolation.json",
            {"schema": ISOLATION_AUDIT_SCHEMA, **common},
        ),
        "bypass_audit": _write(
            tmp_path / f"{stem}-bypass.json",
            {"schema": BYPASS_AUDIT_SCHEMA, **common},
        ),
    }


def _complete_document(tmp_path: Path, *, formal_count: int = 86) -> dict:
    doc = new_release_readiness_template()
    formal_ids = [
        f"formal-{number:04d}" for number in range(1, formal_count + 1)
    ]
    development_ids = [
        f"dev-{number:02d}" for number in range(1, DEVELOPMENT_TASK_COUNT + 1)
    ]
    protocol_ref, protocol = _protocol_manifest(tmp_path, formal_ids)

    validation_refs = []
    for task_id in formal_ids:
        validation = _validation_result(task_id, protocol_ref["sha256"], protocol)
        validation_refs.append(
            {
                "suite": _write(
                    tmp_path / f"oracle-suite-{task_id}.json",
                    {"expected_result": validation},
                ),
                "result": _write(
                    tmp_path / f"oracle-result-{task_id}.json", validation
                ),
            }
        )
    bundle = {
        "schema": ORACLE_RELEASE_BUNDLE_SCHEMA,
        "status": "passed",
        "protocol_manifest_sha256": protocol["manifest_sha256"],
        "task_ids": formal_ids,
        "validation_results": validation_refs,
    }
    bundle["bundle_sha256"] = hashlib.sha256(
        canonical_json_bytes(bundle)
    ).hexdigest()
    oracle_ref = _write(tmp_path / "oracle-bundle.json", bundle)

    machine_harnesses = []
    manual_harnesses = []
    for harness_index, harness_id in enumerate(MAINTAINED_HARNESSES):
        paths = []
        path_ids = []
        path_task_ids = []
        for path_index, path_id in enumerate(("native", "browser")):
            task_id = development_ids[
                (harness_index + path_index) % len(development_ids)
            ]
            run_id = f"dev-{harness_id}-{path_id}"
            path_ids.append(path_id)
            path_task_ids.append(task_id)
            paths.append(
                {
                    "acquisition_path_id": path_id,
                    "capability_class": (
                        "fetch_capable"
                        if path_id == "native"
                        else "snippet_only_separate_protocol"
                    ),
                    "leaderboard_protocol": (
                        "formal-fetch-v1"
                        if path_id == "native"
                        else "snippet-only-v1"
                    ),
                    "development_task_id": task_id,
                    "run_id": run_id,
                    **_path_artifacts(
                        tmp_path,
                        harness_id=harness_id,
                        path_id=path_id,
                        task_id=task_id,
                        run_id=run_id,
                    ),
                }
            )
        machine_harnesses.append(
            {"harness_id": harness_id, "acquisition_paths": paths}
        )
        manual_harnesses.append(
            {
                "harness_id": harness_id,
                "acquisition_path_ids": path_ids,
                "development_case_ids": sorted(set(path_task_ids)),
                "all_declared_paths_covered": True,
                "uncovered_paths_disabled_or_separate_protocol": True,
                "evidence": [
                    _write(
                        tmp_path / f"manual-{harness_id}-paths.txt",
                        f"reviewed all declared paths for {harness_id}",
                    )
                ],
            }
        )
    matrix = {
        "schema": ACQUISITION_PATH_COVERAGE_SCHEMA,
        "status": "passed",
        "protocol_manifest_sha256": protocol["manifest_sha256"],
        "development_task_ids": development_ids,
        "harnesses": machine_harnesses,
    }
    matrix["matrix_sha256"] = hashlib.sha256(
        canonical_json_bytes(matrix)
    ).hexdigest()
    coverage_ref = _write(tmp_path / "acquisition-path-matrix.json", matrix)
    for key, ref in (
        ("protocol_manifest", protocol_ref),
        ("oracle_validation", oracle_ref),
        ("acquisition_path_coverage", coverage_ref),
    ):
        doc["machine_evidence"][key] = {"status": "passed", "artifact": ref}

    common_evidence = _write(
        tmp_path / "manual-review.txt", "human reviewed evidence"
    )
    development = doc["manual_reviews"][
        "development_14_partition_and_exclusion"
    ]
    development.update(
        status="complete",
        development_tasks=[
            {
                "task_id": task_id,
                "dataset_role": "development",
                "excluded_from_headline": True,
            }
            for task_id in development_ids
        ],
        few_shot_examples=[
            {
                "task_id": task_id,
                "graph_motif": MOTIFS[index],
                "generator_view": _write(
                    tmp_path / f"{task_id}-generator-view.json",
                    {"task_id": task_id, "scenario": "sanitized"},
                ),
                "human_written_query": _write(
                    tmp_path / f"{task_id}-human-query.txt",
                    f"Human-written query for {task_id}",
                ),
                "leakage_audit": _write(
                    tmp_path / f"{task_id}-leakage-audit.json",
                    {"task_id": task_id, "status": "passed"},
                ),
            }
            for index, task_id in enumerate(development_ids[:3])
        ],
        calibration_task_ids=development_ids[3:],
        headline_exclusion_evidence=_write(
            tmp_path / "dev14-headline-exclusion.json",
            {"task_ids": development_ids, "excluded": True},
        ),
        evidence=[common_evidence],
        reviewers=[_signed("development-reviewer")],
    )

    authored = doc["manual_reviews"]["formal_86_case_and_oracle_authoring"]
    authored.update(
        status="complete",
        task_ids=formal_ids,
        dataset_role="formal",
        case_specs_authored=True,
        support_spans_authored=True,
        decision_rules_authored=True,
        oracle_materials_authored=True,
        evidence=[common_evidence],
        reviewers=[_signed("case-author")],
    )
    query = doc["manual_reviews"]["query_naturalness_and_leakage"]
    query.update(
        status="complete",
        task_ids=formal_ids,
        naturalness_reviewed=True,
        no_gold_or_scorer_leakage_reviewed=True,
        decision_priority_reviewed=True,
        constraint_diff_empty=True,
        evidence=[common_evidence],
        reviewers=[_signed("query-reviewer")],
    )
    human = doc["manual_reviews"]["human_oracle_runs"]
    human.update(
        status="complete",
        task_ids=formal_ids,
        runs=[
            {
                "task_id": task_id,
                "elapsed_minutes": 12,
                "access_path": [
                    "search:noise",
                    "fetch:http://localhost/evidence",
                ],
                "completed_at": "2026-07-15T12:00:00Z",
                "reviewer_note": "Solved inside the frozen environment.",
            }
            for task_id in formal_ids
        ],
        evidence=[common_evidence],
        reviewers=[_signed("human-oracle-reviewer")],
    )
    annotation = doc["manual_reviews"][
        "double_step_annotation_and_adjudication"
    ]
    annotation.update(
        status="complete",
        task_ids=development_ids[3:],
        annotator_names=["annotator-a", "annotator-b"],
        adjudicator_name="adjudicator-c",
        preregistered_threshold=0.80,
        observed_agreement=0.85,
        disagreement_count=7,
        adjudicated_disagreement_count=7,
        all_steps_double_annotated=True,
        preregistration_evidence=_write(
            tmp_path / "step-preregistration.txt", "registered before annotation"
        ),
        measurement_evidence=_write(
            tmp_path / "step-measurement.txt", "double step annotation results"
        ),
        adjudication_evidence=_write(
            tmp_path / "step-adjudication.txt", "all disagreements adjudicated"
        ),
        reviewers=[
            _signed("annotator-a"),
            _signed("annotator-b"),
            _signed("adjudicator-c"),
        ],
    )
    acquisition = doc["manual_reviews"]["acquisition_path_coverage_audit"]
    acquisition.update(
        status="complete",
        development_task_ids=development_ids,
        harnesses=manual_harnesses,
        reviewers=[_signed("acquisition-path-auditor")],
    )
    statistics = doc["manual_reviews"]["formal_86_statistics_and_fairness"]
    statistics.update(
        status="complete",
        formal_task_count=FORMAL_TASK_COUNT,
        development_tasks_excluded=True,
        cluster_bootstrap_ci_passed=True,
        replicate_stability_passed=True,
        harness_fairness_passed=True,
        validation_panel_evidence=_write(
            tmp_path / "formal86-panel.txt", "Formal-86 panel review"
        ),
        cluster_bootstrap_ci_evidence=_write(
            tmp_path / "cluster-bootstrap.txt", "cluster bootstrap review"
        ),
        replicate_stability_evidence=_write(
            tmp_path / "replicate-stability.txt", "replicate stability review"
        ),
        harness_fairness_evidence=_write(
            tmp_path / "harness-fairness.txt", "harness fairness review"
        ),
        reviewers=[_signed("statistics-reviewer")],
    )
    method_hash = hashlib.sha256(b"same method text").hexdigest()
    publication = doc["manual_reviews"]["publication_method_consistency"]
    publication.update(
        status="complete",
        surfaces={
            name: {
                "artifact": _write(
                    tmp_path / f"publication-{name}.txt",
                    f"{name} method surface",
                ),
                "method_text_sha256": method_hash,
            }
            for name in PUBLICATION_SURFACES
        },
        reviewers=[_signed("publication-reviewer")],
    )
    return doc


def _rewrite_matrix(doc: dict, tmp_path: Path, mutate) -> None:
    outer = doc["machine_evidence"]["acquisition_path_coverage"]["artifact"]
    matrix_path = tmp_path / outer["path"]
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    mutate(matrix)
    matrix["matrix_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in matrix.items() if key != "matrix_sha256"}
        )
    ).hexdigest()
    doc["machine_evidence"]["acquisition_path_coverage"]["artifact"] = _write(
        matrix_path, matrix
    )


def _resign_first_oracle_result(doc: dict, tmp_path: Path, mutate) -> None:
    bundle_ref = doc["machine_evidence"]["oracle_validation"]["artifact"]
    bundle_path = tmp_path / bundle_ref["path"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    result_ref = bundle["validation_results"][0]["result"]
    result_path = tmp_path / result_ref["path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    mutate(result)
    result["validation_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in result.items() if key != "validation_sha256"}
        )
    ).hexdigest()
    result_ref.update(_write(result_path, result))
    bundle["bundle_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in bundle.items() if key != "bundle_sha256"}
        )
    ).hexdigest()
    doc["machine_evidence"]["oracle_validation"]["artifact"] = _write(
        bundle_path, bundle
    )


def test_template_is_v2_pending_and_cli_returns_two(tmp_path: Path) -> None:
    template = new_release_readiness_template()
    assert template["schema"] == RELEASE_READINESS_SCHEMA
    assert set(template["machine_evidence"]) == {
        "protocol_manifest",
        "oracle_validation",
        "acquisition_path_coverage",
    }
    result = check_release_readiness(template, base_dir=tmp_path)
    assert result["status"] == "code_pending"
    source = tmp_path / "todo.json"
    source.write_text(json.dumps(template), encoding="utf-8")
    assert release_cli(["--check-v2", str(source)]) == 2


def test_complete_dev14_formal86_handoff_is_eligible(tmp_path: Path) -> None:
    result = check_release_readiness(_complete_document(tmp_path), base_dir=tmp_path)
    assert result == {
        "schema": RELEASE_READINESS_SCHEMA,
        "status": "formal_release_eligible",
        "code_ready": True,
        "manual_review_complete": True,
        "formal_release_eligible": True,
        "verified_machine_artifacts": [
            "acquisition_path_coverage",
            "oracle_validation",
            "protocol_manifest",
        ],
        "machine_pending": [],
        "manual_pending": [],
        "errors": [],
    }


def test_old_scale_protocol_cannot_claim_formal_release(tmp_path: Path) -> None:
    result = check_release_readiness(
        _complete_document(tmp_path, formal_count=85), base_dir=tmp_path
    )
    assert result["status"] == "invalid"
    assert any("exactly Formal-86" in error for error in result["errors"])


def test_dev14_must_be_development_excluded_and_disjoint(tmp_path: Path) -> None:
    doc = _complete_document(tmp_path)
    review = doc["manual_reviews"]["development_14_partition_and_exclusion"]
    review["development_tasks"][0]["dataset_role"] = "formal"
    review["development_tasks"][0]["excluded_from_headline"] = False
    formal_id = doc["manual_reviews"]["formal_86_case_and_oracle_authoring"][
        "task_ids"
    ][0]
    review["development_tasks"][1]["task_id"] = formal_id
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("dataset_role" in error for error in result["errors"])
    assert any("excluded_from_headline" in error for error in result["errors"])
    assert any("disjoint" in error for error in result["errors"])


def test_three_few_shots_and_eleven_calibration_tasks_are_a_partition(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    review = doc["manual_reviews"]["development_14_partition_and_exclusion"]
    review["few_shot_examples"][1]["graph_motif"] = review[
        "few_shot_examples"
    ][0]["graph_motif"]
    review["calibration_task_ids"][0] = review["few_shot_examples"][0]["task_id"]
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("distinct graph motifs" in error for error in result["errors"])
    assert any("must be disjoint" in error for error in result["errors"])


def test_step_annotation_requires_two_annotators_and_full_adjudication(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    review = doc["manual_reviews"][
        "double_step_annotation_and_adjudication"
    ]
    review["adjudicated_disagreement_count"] = 6
    review["adjudicator_name"] = "annotator-a"
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("every step disagreement" in error for error in result["errors"])
    assert any("independent adjudicator" in error for error in result["errors"])


def test_every_declared_acquisition_path_must_pass_all_sfl_checks(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    outer = doc["machine_evidence"]["acquisition_path_coverage"]["artifact"]
    matrix_path = tmp_path / outer["path"]
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    path_entry = matrix["harnesses"][0]["acquisition_paths"][1]
    result_path = tmp_path / path_entry["conformance_result"]["path"]
    conformance = json.loads(result_path.read_text(encoding="utf-8"))
    conformance["l_only_denies_body_support"] = False
    path_entry["conformance_result"] = _write(result_path, conformance)
    matrix["matrix_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in matrix.items() if key != "matrix_sha256"}
        )
    ).hexdigest()
    doc["machine_evidence"]["acquisition_path_coverage"]["artifact"] = _write(
        matrix_path, matrix
    )
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("l_only_denies_body_support: must pass" in error for error in result["errors"])


def test_manual_path_inventory_must_equal_machine_matrix(tmp_path: Path) -> None:
    doc = _complete_document(tmp_path)
    manual = doc["manual_reviews"]["acquisition_path_coverage_audit"]
    manual["harnesses"][0]["acquisition_path_ids"] = ["native"]
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("machine coverage matrix" in error for error in result["errors"])


def test_empty_path_ledger_cannot_prove_conformance(tmp_path: Path) -> None:
    doc = _complete_document(tmp_path)
    outer = doc["machine_evidence"]["acquisition_path_coverage"]["artifact"]
    matrix_path = tmp_path / outer["path"]
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    path_entry = matrix["harnesses"][0]["acquisition_paths"][0]
    ledger_path = tmp_path / path_entry["ledger"]["path"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["events"] = []
    path_entry["ledger"] = _write(ledger_path, ledger)
    matrix["matrix_sha256"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in matrix.items() if key != "matrix_sha256"}
        )
    ).hexdigest()
    doc["machine_evidence"]["acquisition_path_coverage"]["artifact"] = _write(
        matrix_path, matrix
    )
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("at least one captured observation event" in error for error in result["errors"])


def test_oracle_bundle_is_freshly_replayed_for_all_formal_tasks(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    _resign_first_oracle_result(
        doc,
        tmp_path,
        lambda result: result["manual_human_record"].update(
            reviewer="different-reviewer"
        ),
    )
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("deterministic suite replay" in error for error in result["errors"])


def test_formal86_oracle_rejects_legacy_aliases_and_v2_replay_identity(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)

    def downgrade(result: dict) -> None:
        row = result["oracle_results"][0]
        score = row["score"]
        score["task_pass"] = 1
        identity = {
            key: score[key]
            for key in (
                "run_id",
                "agent",
                "task_id",
                "replicate",
                "cluster_id",
                "report_sha256",
                "observation_ledger_sha256",
                "case_artifact_sha256",
                "public_task_sha256",
                "protocol_manifest_sha256",
                "corpus_registry_hash",
            )
        }
        score["scoring_input_sha256"] = hashlib.sha256(
            canonical_json_bytes(
                {"version": "dra_v3_scoring_input_v2", **identity}
            )
        ).hexdigest()
        row["score_sha256"] = hashlib.sha256(
            canonical_json_bytes(score)
        ).hexdigest()

    _resign_first_oracle_result(doc, tmp_path, downgrade)
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("legacy aliases" in error for error in result["errors"])
    assert any("scoring_input_sha256" in error for error in result["errors"])


def test_status_only_artifact_and_unsigned_manual_review_fail_closed(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    fake = _write(tmp_path / "fake-coverage.json", {"status": "passed"})
    doc["machine_evidence"]["acquisition_path_coverage"] = {
        "status": "passed",
        "artifact": fake,
    }
    review = doc["manual_reviews"]["formal_86_case_and_oracle_authoring"]
    review["evidence"] = []
    review["reviewers"] = []
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert "acquisition_path_coverage" in result["machine_pending"]
    assert any("hashed review artifact" in error for error in result["errors"])
    assert any("signed reviewer" in error for error in result["errors"])


def test_statistics_bind_formal86_and_dev14_exclusion(tmp_path: Path) -> None:
    doc = _complete_document(tmp_path)
    review = doc["manual_reviews"]["formal_86_statistics_and_fairness"]
    review["formal_task_count"] = 85
    review["development_tasks_excluded"] = False
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any("exactly Formal-86" in error for error in result["errors"])
    assert any("Dev-14 exclusion" in error for error in result["errors"])


def test_old_v1_readiness_schema_is_rejected(tmp_path: Path) -> None:
    doc = _complete_document(tmp_path)
    doc["schema"] = "dra_v3_release_readiness_v1"
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"
    assert any(RELEASE_READINESS_SCHEMA in error for error in result["errors"])


def test_v1_and_v2_gates_and_cli_modes_coexist(tmp_path: Path, capsys) -> None:
    legacy = new_legacy_release_readiness_template()
    current = new_release_readiness_template()
    assert legacy["schema"] == LEGACY_RELEASE_READINESS_SCHEMA
    assert current["schema"] == RELEASE_READINESS_SCHEMA
    assert LEGACY_RELEASE_READINESS_SCHEMA != RELEASE_READINESS_SCHEMA
    assert set(legacy["machine_evidence"]) == {
        "protocol_manifest",
        "oracle_validation",
        "harness_ledger_matrix",
    }
    assert "candidate_corpus_and_pilot_selection" in legacy["manual_reviews"]
    assert "validation_30_and_fairness" in legacy["manual_reviews"]
    assert "development_14_partition_and_exclusion" not in legacy["manual_reviews"]
    assert check_legacy_release_readiness(legacy, base_dir=tmp_path)["status"] == "code_pending"
    assert check_release_readiness(current, base_dir=tmp_path)["status"] == "code_pending"
    assert check_legacy_release_readiness(current, base_dir=tmp_path)["status"] == "invalid"
    assert check_release_readiness(legacy, base_dir=tmp_path)["status"] == "invalid"

    assert release_cli(["--init-template"]) == 0
    legacy_cli = json.loads(capsys.readouterr().out)
    assert legacy_cli["schema"] == LEGACY_RELEASE_READINESS_SCHEMA
    assert release_cli(["--init-v2-template"]) == 0
    current_cli = json.loads(capsys.readouterr().out)
    assert current_cli["schema"] == RELEASE_READINESS_SCHEMA

    legacy_path = tmp_path / "legacy-todo.json"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert release_cli(["--check", str(legacy_path)]) == 2
    legacy_result = json.loads(capsys.readouterr().out)
    assert legacy_result["schema"] == LEGACY_RELEASE_READINESS_SCHEMA
    current_path = tmp_path / "current-todo.json"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    assert release_cli(["--check-v2", str(current_path)]) == 2
    current_result = json.loads(capsys.readouterr().out)
    assert current_result["schema"] == RELEASE_READINESS_SCHEMA


def test_json_type_confusion_and_nonfinite_numbers_fail_closed(
    tmp_path: Path,
) -> None:
    doc = _complete_document(tmp_path)
    doc["machine_evidence"]["protocol_manifest"]["status"] = []
    result = check_release_readiness(doc, base_dir=tmp_path)
    assert result["status"] == "invalid"

    source = tmp_path / "nan.json"
    source.write_text('{"elapsed": NaN}', encoding="utf-8")
    assert release_cli(["--check-v2", str(source)]) == 1


def test_template_and_result_are_deterministic(tmp_path: Path) -> None:
    assert canonical_json_bytes(new_release_readiness_template()) == canonical_json_bytes(
        new_release_readiness_template()
    )
    doc = _complete_document(tmp_path)
    assert check_release_readiness(doc, base_dir=tmp_path) == check_release_readiness(
        doc, base_dir=tmp_path
    )
