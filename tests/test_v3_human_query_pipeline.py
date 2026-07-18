from __future__ import annotations

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from scripts.capture_v3_candidate_sources import validate_capture_plan
from scripts.compile_case_v3 import main as compile_main
from src.eval.case_schema_v3 import CaseSpecV3
from src.tasks.human_query_pipeline_v3 import (
    BLIND_REVIEW_ATTESTATION,
    HUMAN_ATTESTATION,
    HumanActorV1,
    HumanBlindQueryReviewV1,
    HumanFewShotExampleV1,
    HumanGraphAnnotationV1,
    HumanQueryPipelineError,
    HumanSourceSelectionV1,
    QueryRendererModelConfigV1,
    artifact_sha256,
    build_few_shot_dataset,
    build_graph_annotation_template,
    build_human_blind_review_template,
    build_human_query_release,
    build_query_attempt_closure,
    build_query_generation_record,
    build_registered_query_messages,
    build_registered_query_prompt,
    capture_plan_from_human_selection,
    validate_few_shot_example_for_case,
    validate_graph_annotation_for_case,
    validate_human_query_release,
    validate_query_generation_record,
)
from test_case_schema_v3 import (
    catalog_records,
    corpus_registry,
    graph_edges,
    proof_step_case_dict,
    reachability_manifest,
    support_spans,
)


NOW = "2026-07-16T12:00:00Z"


def _actor(actor_id: str, role: str) -> dict:
    return {
        "actor_type": "human",
        "actor_id": actor_id,
        "role": role,
        "attestation": HUMAN_ATTESTATION,
    }


def _case_variant(index: int, motif: str) -> CaseSpecV3:
    payload = deepcopy(proof_step_case_dict())
    payload["task_id"] = f"dra_v3_dev_variant_{index:04d}"
    payload["cluster_id"] = f"dev_variant_{index}"
    payload["motif"] = motif
    payload["generator_view"] = {
        "scenario": f"Scenario {index} needs a documented choice.",
        "constraints": ["wears_glasses", "small_bag"],
        "candidate_actions": ["form_a", "form_b"],
        "target": f"Compare both options for scenario {index}.",
    }
    return CaseSpecV3.from_dict(payload)


def _evidence_review_gate(
    case: CaseSpecV3,
    graph_hash: str,
    *,
    candidate_id: str,
    reviewer_id: str,
) -> dict:
    item_results = [
        {
            "review_item_id": source.evidence_id,
            "evidence_id": source.evidence_id,
            "review_kind": "semantic",
            "decision": "approve",
            "checks": {
                "support_span_correct": True,
                "proposition_supported": True,
                "source_scope_correct": True,
                "context_sufficient": True,
            },
            "review_complete": True,
            "first_pass_approved": True,
            "formal_promotion_candidate": True,
            "disposition": "human_approved_pending_materialization",
            "reason_codes": [],
        }
        for source in case.evidence_sources
    ]
    report = {
        "schema_version": "dra_v3_review_gate_report_v1",
        "status": "eligible_for_case_generation",
        "candidate_id": candidate_id,
        "corpus_snapshot": case.corpus_snapshot,
        "evidence_graph_hash": graph_hash,
        "review_authority": "human",
        "review_identity": {
            "reviewer_id": reviewer_id,
            "reviewed_at_utc": NOW,
            "independent_review": True,
            "candidate_verdict": "eligible",
        },
        "input_hashes": {
            "review_packet_manifest_sha256": "1" * 64,
            "review_queue_canonical_sha256": "2" * 64,
            "review_decisions_canonical_sha256": "3" * 64,
        },
        "item_results": item_results,
        "formal_promotion_candidate_ids": [
            source.evidence_id for source in case.evidence_sources
        ],
        "candidate_gate": {
            "eligible_for_case_generation": True,
            "blocker_codes": [],
        },
    }
    report["report_sha256"] = artifact_sha256(report)
    return report


def _approved_annotation(
    case: CaseSpecV3,
    graph_hash: str,
    *,
    candidate_id: str,
    annotator_id: str = "graph_annotator_a",
    adjudicator_id: str = "graph_adjudicator_b",
) -> HumanGraphAnnotationV1:
    gate = _evidence_review_gate(
        case,
        graph_hash,
        candidate_id=candidate_id,
        reviewer_id=annotator_id,
    )
    template = build_graph_annotation_template(
        case,
        candidate_id=candidate_id,
        evidence_graph_sha256=graph_hash,
        evidence_review_gate=gate,
    ).model_dump(mode="json", exclude_none=True)
    template.update(
        {
            "status": "approved",
            "annotator": _actor(annotator_id, "graph_annotator"),
            "adjudicator": _actor(adjudicator_id, "graph_adjudicator"),
            "annotated_at_utc": NOW,
            "adjudicated_at_utc": NOW,
            "annotation_note": "Every source span and proposition was checked.",
            "adjudication_note": "All disagreements were resolved from frozen bytes.",
        }
    )
    for item in template["evidence_items"]:
        item.update(
            {
                "support_span_correct": True,
                "proposition_supported": True,
                "source_scope_correct": True,
                "context_sufficient": True,
                "decision": "keep",
                "reviewer_note": "Frozen span supports the scoped proposition.",
            }
        )
    for item in template["proof_steps"]:
        item.update(
            {
                "necessary": True,
                "dependencies_correct": True,
                "verifier_contract_clear": True,
                "deletion_test": (
                    "becomes_unresolved"
                    if item["step_type"] == "evidence"
                    else "not_applicable"
                ),
                "decision": "keep",
                "necessity_rationale": "Removing this obligation breaks the declared route.",
            }
        )
    template["generator_view_review"] = {
        "scenario_faithful": True,
        "constraints_complete": True,
        "candidate_actions_complete": True,
        "target_requires_research": True,
        "contains_no_gold_or_urls": True,
        "decision": "approve",
        "reviewer_note": "The public projection is complete and contains no gold.",
    }
    record = HumanGraphAnnotationV1.model_validate(template)
    return validate_graph_annotation_for_case(
        record,
        case,
        expected_graph_sha256=graph_hash,
    )


def _few_shot_example(
    case: CaseSpecV3,
    annotation: HumanGraphAnnotationV1,
    index: int,
) -> HumanFewShotExampleV1:
    query = (
        f"For scenario {index}, account for wears_glasses and small_bag, compare "
        "form_a with form_b, and explain the resulting choice."
    )
    payload = {
        "example_id": f"dev_example_{index}",
        "task_id": case.task_id,
        "case_sha256": case.sha256(),
        "graph_annotation_sha256": artifact_sha256(annotation),
        "motif": case.motif,
        "generator_view": case.generator_view.model_dump(mode="json"),
        "human_written_query": query,
        "author": _actor(f"query_author_{index}", "few_shot_query_author"),
        "adjudicator": _actor(f"query_judge_{index}", "few_shot_adjudicator"),
        "authored_at_utc": NOW,
        "adjudicated_at_utc": NOW,
        "adjudication_note": "The query faithfully covers the public view.",
        "status": "approved",
    }
    return validate_few_shot_example_for_case(payload, case, annotation)


def _few_shot_dataset():
    motifs = [
        "constraint_match_and_select",
        "claim_verification",
        "evidence_reconciliation",
    ]
    examples = []
    for index, motif in enumerate(motifs, 1):
        case = _case_variant(index, motif)
        graph_hash = str(index) * 64
        annotation = _approved_annotation(
            case,
            graph_hash,
            candidate_id=f"dev_candidate_{index}",
            annotator_id=f"dev_graph_a_{index}",
            adjudicator_id=f"dev_graph_b_{index}",
        )
        examples.append(_few_shot_example(case, annotation, index))
    return build_few_shot_dataset(
        dataset_id="manual_dev_three_motifs_v1",
        examples=examples,
        approved_by=HumanActorV1.model_validate(
            _actor("dataset_adjudicator", "few_shot_adjudicator")
        ),
        approved_at_utc=NOW,
    )


def test_human_source_selection_compiles_to_existing_capture_contract() -> None:
    selection = HumanSourceSelectionV1.model_validate(
        {
            "candidate_id": "cand_human_0001",
            "corpus_snapshot": "human-query-pipeline-0001",
            "run_id": "human-query-pipeline-0001-r1",
            "research_goal": "Compare a product claim with an independent mechanism boundary.",
            "proposal_origin": "human_search",
            "selected_by": _actor("source_selector_1", "source_selector"),
            "selected_at_utc": NOW,
            "source_requirements": [
                {
                    "source_role": "product",
                    "purpose": "Freeze the exact offer and seller claims.",
                    "minimum_sources": 1,
                    "critical": True,
                },
                {
                    "source_role": "mechanism",
                    "purpose": "Bound the general mechanism independently.",
                    "minimum_sources": 1,
                    "critical": True,
                },
            ],
            "searches": [
                {
                    "search_id": "product_offer",
                    "query": "exact product offer",
                    "max_results": 5,
                    "include_domains": ["localhost:7770"],
                    "required_urls": ["http://localhost:7770/product.html"],
                },
                {
                    "search_id": "mechanism_page",
                    "query": "independent mechanism",
                    "max_results": 5,
                    "include_domains": ["localhost:8090"],
                    "required_urls": ["http://localhost:8090/content/mechanism"],
                },
            ],
            "selected_sources": [
                {
                    "registry_id": "reg_product",
                    "source_type": "magento",
                    "url": "http://localhost:7770/product.html",
                    "extract_depth": "advanced",
                    "source_role": "product",
                    "selection_rationale": "The exact frozen offer is decision relevant.",
                    "critical_candidate": True,
                },
                {
                    "registry_id": "reg_mechanism",
                    "source_type": "wikipedia",
                    "url": "http://localhost:8090/content/mechanism",
                    "extract_depth": "advanced",
                    "source_role": "mechanism",
                    "selection_rationale": "The page provides an independent mechanism boundary.",
                    "critical_candidate": True,
                },
            ],
            "source_identity": {"search_service": "frozen-search-v1"},
            "status": "approved_for_capture",
        }
    )

    plan = validate_capture_plan(capture_plan_from_human_selection(selection))

    assert plan["candidate_id"] == "cand_human_0001"
    assert len(plan["searches"]) == 2
    assert len(plan["extracts"]) == 2
    assert plan["metadata"]["authoring_policy"] == "human_source_selection_v1"
    assert plan["metadata"]["selected_by"] == "source_selector_1"


def test_graph_approval_is_exact_and_requires_two_distinct_humans() -> None:
    case = CaseSpecV3.from_dict(proof_step_case_dict())
    graph_hash = "a" * 64
    approved = _approved_annotation(
        case, graph_hash, candidate_id="candidate_graph_0001"
    )

    assert approved.status == "approved"
    assert len(approved.evidence_items) == len(case.evidence_sources)
    assert len(approved.proof_steps) == len(case.slots)

    broken = approved.model_dump(mode="json")
    broken["adjudicator"]["actor_id"] = broken["annotator"]["actor_id"]
    with pytest.raises(ValidationError, match="distinct humans"):
        HumanGraphAnnotationV1.model_validate(broken)

    incomplete = approved.model_copy(deep=True)
    incomplete.evidence_items.pop()
    with pytest.raises(HumanQueryPipelineError, match="exactly cover"):
        validate_graph_annotation_for_case(
            incomplete,
            case,
            expected_graph_sha256=graph_hash,
        )


def test_few_shot_prompt_contains_only_public_human_examples() -> None:
    target = CaseSpecV3.from_dict(proof_step_case_dict())
    dataset = _few_shot_dataset()

    prompt = build_registered_query_prompt(target, dataset)
    messages = build_registered_query_messages(target, dataset)
    blob = json.dumps({"prompt": prompt, "messages": messages})

    assert len(prompt["examples"]) == 3
    assert all(
        set(item) == {"generator_view", "human_written_query"}
        for item in prompt["examples"]
    )
    for private in (
        "evaluator_view",
        "required_proof_steps",
        "evidence_sources",
        "acceptable_conclusions",
        "http://localhost:8080/seal",
        "ev_seal",
    ):
        assert private not in blob


def test_registered_renderer_rejects_codex_and_release_replays() -> None:
    target = CaseSpecV3.from_dict(proof_step_case_dict())
    target_graph_hash = "f" * 64
    annotation = _approved_annotation(
        target,
        target_graph_hash,
        candidate_id="target_candidate_0001",
        annotator_id="target_graph_annotator",
        adjudicator_id="target_graph_adjudicator",
    )
    dataset = _few_shot_dataset()

    with pytest.raises(ValidationError, match="Codex"):
        QueryRendererModelConfigV1(
            renderer_id="registered_renderer_v1",
            base_url="http://127.0.0.1:8000/v1",
            model="codex-interactive",
            model_revision="2026-07-16",
            api_key_env="DRA_QUERY_RENDERER_API_KEY",
            temperature=0.0,
            max_tokens=1024,
            seed=7,
            timeout_seconds=60.0,
        )

    config = QueryRendererModelConfigV1(
        renderer_id="registered_renderer_v1",
        base_url="http://127.0.0.1:8000/v1",
        model="registered-query-renderer-v1",
        model_revision="2026-07-16",
        api_key_env="DRA_QUERY_RENDERER_API_KEY",
        temperature=0.0,
        max_tokens=1024,
        seed=7,
        timeout_seconds=60.0,
    )
    query = (
        "A traveler wears glasses and has a small bag. Compare form a with form b "
        "and choose the better form factor for the stated trip."
    )
    raw_response = json.dumps(
        {"choices": [{"message": {"content": query}}]},
        sort_keys=True,
    ).encode("utf-8")
    generation = build_query_generation_record(
        target,
        dataset,
        config,
        attempt=1,
        generated_at_utc=NOW,
        assistant_text=query,
        raw_response_bytes=raw_response,
    )
    assert generation.status == "hard_rules_passed"
    validate_query_generation_record(generation, target, dataset)

    packet, template = build_human_blind_review_template(target, generation)
    template["reviewer"] = _actor("blind_reviewer_c", "blind_query_reviewer")
    template["reviewed_at_utc"] = NOW
    template["review"]["reviewer_id"] = "blind_reviewer_c"
    for key in (
        "faithful",
        "natural",
        "closed_environment_answerable",
        "requires_multi_branch_research",
        "passed",
    ):
        template["review"][key] = True
    review = HumanBlindQueryReviewV1.model_validate(template)
    assert review.packet_sha256 == artifact_sha256(packet)
    closure = build_query_attempt_closure(
        target,
        dataset,
        generation,
        blind_review=review,
    )

    release = build_human_query_release(
        target,
        expected_graph_sha256=target_graph_hash,
        graph_annotation=annotation,
        few_shot_dataset=dataset,
        attempts=[closure],
    )
    replayed = validate_human_query_release(
        release,
        target,
        expected_graph_sha256=target_graph_hash,
    )

    assert replayed.status == "approved_for_formal_compile"
    assert replayed.query == query
    assert replayed.blind_review.attestation == BLIND_REVIEW_ATTESTATION


def test_blind_reviewer_cannot_be_target_graph_annotator() -> None:
    target = CaseSpecV3.from_dict(proof_step_case_dict())
    graph_hash = "e" * 64
    annotation = _approved_annotation(
        target,
        graph_hash,
        candidate_id="target_candidate_0002",
        annotator_id="same_person",
        adjudicator_id="other_person",
    )
    dataset = _few_shot_dataset()
    config = QueryRendererModelConfigV1(
        renderer_id="registered_renderer_v1",
        base_url="http://127.0.0.1:8000/v1",
        model="registered-query-renderer-v1",
        model_revision="2026-07-16",
        api_key_env="DRA_QUERY_RENDERER_API_KEY",
        temperature=0.0,
        max_tokens=1024,
        seed=7,
        timeout_seconds=60.0,
    )
    query = (
        "A traveler wears glasses and has a small bag. Compare form a with form b "
        "and choose the better form factor for the stated trip."
    )
    raw = json.dumps({"choices": [{"message": {"content": query}}]}).encode()
    generation = build_query_generation_record(
        target,
        dataset,
        config,
        attempt=1,
        generated_at_utc=NOW,
        assistant_text=query,
        raw_response_bytes=raw,
    )
    _packet, template = build_human_blind_review_template(target, generation)
    template["reviewer"] = _actor("same_person", "blind_query_reviewer")
    template["reviewed_at_utc"] = NOW
    template["review"]["reviewer_id"] = "same_person"
    for key in (
        "faithful",
        "natural",
        "closed_environment_answerable",
        "requires_multi_branch_research",
        "passed",
    ):
        template["review"][key] = True
    review = HumanBlindQueryReviewV1.model_validate(template)
    closure = build_query_attempt_closure(
        target,
        dataset,
        generation,
        blind_review=review,
    )

    with pytest.raises(HumanQueryPipelineError, match="must not have seen"):
        build_human_query_release(
            target,
            expected_graph_sha256=graph_hash,
            graph_annotation=annotation,
            few_shot_dataset=dataset,
            attempts=[closure],
        )


def test_formal_compiler_consumes_human_query_release(
    tmp_path, capsys
) -> None:
    payload = proof_step_case_dict()
    target = CaseSpecV3.from_dict(payload)
    graph_hash = reachability_manifest()["evidence_graph_sha256"]
    annotation = _approved_annotation(
        target,
        graph_hash,
        candidate_id="compiler_release_candidate",
        annotator_id="compiler_graph_annotator",
        adjudicator_id="compiler_graph_adjudicator",
    )
    dataset = _few_shot_dataset()
    config = QueryRendererModelConfigV1(
        renderer_id="registered_renderer_v1",
        base_url="http://127.0.0.1:8000/v1",
        model="registered-query-renderer-v1",
        model_revision="2026-07-16",
        api_key_env="DRA_QUERY_RENDERER_API_KEY",
        temperature=0.0,
        max_tokens=1024,
        seed=7,
        timeout_seconds=60.0,
    )
    query = (
        "A traveler wears glasses and has a small bag. Compare form a with form b "
        "and choose the better form factor for the stated trip."
    )
    raw = json.dumps({"choices": [{"message": {"content": query}}]}).encode()
    generation = build_query_generation_record(
        target,
        dataset,
        config,
        attempt=1,
        generated_at_utc=NOW,
        assistant_text=query,
        raw_response_bytes=raw,
    )
    _packet, review_payload = build_human_blind_review_template(target, generation)
    review_payload["reviewer"] = _actor(
        "compiler_blind_reviewer", "blind_query_reviewer"
    )
    review_payload["reviewed_at_utc"] = NOW
    review_payload["review"]["reviewer_id"] = "compiler_blind_reviewer"
    for key in (
        "faithful",
        "natural",
        "closed_environment_answerable",
        "requires_multi_branch_research",
        "passed",
    ):
        review_payload["review"][key] = True
    review = HumanBlindQueryReviewV1.model_validate(review_payload)
    closure = build_query_attempt_closure(
        target,
        dataset,
        generation,
        blind_review=review,
    )
    release = build_human_query_release(
        target,
        expected_graph_sha256=graph_hash,
        graph_annotation=annotation,
        few_shot_dataset=dataset,
        attempts=[closure],
    )

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    for name, rows in (
        ("nodes.jsonl", catalog_records()),
        ("edges.jsonl", graph_edges()),
        ("support_spans.jsonl", support_spans()),
    ):
        (graph_dir / name).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    (graph_dir / "corpus_registry.json").write_text(
        json.dumps(corpus_registry()), encoding="utf-8"
    )
    draft_path = tmp_path / "draft.json"
    reachability_path = tmp_path / "reachability.json"
    release_path = tmp_path / "query-release.json"
    case_out = tmp_path / "case.json"
    task_out = tmp_path / "task.json"
    draft_path.write_text(json.dumps(payload), encoding="utf-8")
    reachability_path.write_text(
        json.dumps(reachability_manifest()), encoding="utf-8"
    )
    release_path.write_text(
        json.dumps(release.model_dump(mode="json", exclude_none=True)),
        encoding="utf-8",
    )

    assert compile_main(
        [
            str(draft_path),
            "--evidence-catalog",
            str(graph_dir),
            "--reachability-manifest",
            str(reachability_path),
            "--query-release-certificate",
            str(release_path),
            "--case-out",
            str(case_out),
            "--task-out",
            str(task_out),
        ]
    ) == 0
    summary = json.loads(capsys.readouterr().out)
    compiled = json.loads(case_out.read_text(encoding="utf-8"))
    rendered = json.loads(task_out.read_text(encoding="utf-8"))
    assert summary["query_authoring_policy"] == "human_query_pipeline_v1"
    assert summary["query_release_sha256"] == artifact_sha256(release)
    assert compiled["formal_bindings"]["query_authoring_policy"] == (
        "human_query_pipeline_v1"
    )
    assert compiled["formal_bindings"]["query_release_sha256"] == artifact_sha256(
        release
    )
    assert rendered["intent"] == query
    assert rendered["query_validation"]["disposition"] == "accepted"
