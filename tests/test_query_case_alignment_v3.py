from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.eval.case_schema_v3 import CaseSpec, QUERY_MAX_GENERATION_ATTEMPTS
from src.tasks.query_renderer_v3 import (
    BlindSemanticReviewRecordV3,
    QueryAlignmentError,
    QueryCaseDiscardedError,
    QueryLeakError,
    QueryRetryRequiredError,
    SanitizedFewShotExampleV3,
    assert_no_query_leaks,
    assert_query_accepted,
    assert_query_case_alignment,
    build_blind_review_packet,
    build_hard_rule_pass_record,
    build_query_acceptance_record,
    build_query_generation_prompt,
    canonical_query_contract,
    detect_query_leaks,
    query_constraint_diff,
    render_query,
    render_task,
    validate_query_candidate,
    validate_sanitized_few_shot_examples,
)
from test_case_schema_v3 import proof_step_case_dict


def _case() -> CaseSpec:
    return CaseSpec.from_dict(proof_step_case_dict())


def _blind_record(
    case: CaseSpec,
    *,
    attempt: int = 1,
    passed: bool = True,
    query_text: str | None = None,
) -> dict:
    packet = build_blind_review_packet(
        case, attempt=attempt, query_text=query_text
    )
    return {
        "schema": "blind_semantic_alignment_review_v1",
        "task_id": case.task_id,
        "attempt": attempt,
        "max_generation_attempts": QUERY_MAX_GENERATION_ATTEMPTS,
        "generator_view_sha256": packet["generator_view_sha256"],
        "query_sha256": packet["query_sha256"],
        "reviewer_id": "human-reviewer-01",
        "faithful": passed,
        "natural": passed,
        "closed_environment_answerable": passed,
        "requires_multi_branch_research": passed,
        "passed": passed,
    }


def _natural_query(case: CaseSpec) -> str:
    return (
        "I am working with a traveler who wears glasses and has a small bag. "
        "Please compare form a with form b, then choose the better form factor "
        "for the stated trip."
    )


def test_renderer_reads_only_generator_view() -> None:
    case = _case()
    query = render_query(case)
    task = render_task(case)

    assert "A traveler wears glasses" in query
    assert "wears glasses" in query
    assert "small bag" in query
    assert "form a" in query
    assert "form b" in query
    assert case.generator_view.target in query
    assert task["intent"] == query
    assert task["scoring_semantics"] == "proof_steps_v1"
    assert task["query_validation"]["status"] == "pending_blind_review"
    assert task["headline_metrics"] == [
        "partial_completion_rate_v1",
        "full_pass_rate_v1",
    ]
    assert task["diagnostic_metrics"] == [
        "route_coverage_v1",
        "acquisition_diagnostics_v1",
    ]
    assert "diagnostic_metric" not in task

    for private in (
        "http://",
        "ev_seal",
        "E1",
        "D1",
        "Q1",
        "acceptable_conclusions",
        "typed_claim",
        "Required research subgoals",
        "Required deliverables",
    ):
        assert private not in query
    for private_key in (
        "evaluator_view",
        "required_proof_steps",
        "evidence_sources",
        "acceptable_conclusions",
        "oracle",
        "formal_bindings",
    ):
        assert private_key not in task
    assert assert_no_query_leaks(case, query) is None


def test_public_contract_is_exact_generator_view_projection() -> None:
    case = _case()
    contract = canonical_query_contract(case)
    assert contract == {
        "schema": "generator_view_query_contract_v1",
        "generator_view": case.generator_view.model_dump(mode="json"),
    }
    blob = repr(contract)
    assert "Q1" not in blob
    assert "E1" not in blob
    assert "ev_seal" not in blob
    assert "final_answer_contract" not in blob


def test_private_field_mutations_cannot_change_formal_query() -> None:
    original = proof_step_case_dict()
    baseline = render_query(original)

    for mutation in ("requirements", "subgoals", "oracle", "evaluator"):
        payload = deepcopy(original)
        if mutation == "requirements":
            payload["query_requirements"][0]["text"] = (
                "Use http://private.invalid and complete E1."
            )
        elif mutation == "subgoals":
            payload["research_subgoals"][0]["description"] = "Secret gold route"
        elif mutation == "oracle":
            payload["oracle"]["human_solve_minutes"] = 999
        else:
            payload["evaluator_view"]["final_answer_contract"][
                "must_explain_tradeoffs"
            ] = True
        assert render_query(payload) == baseline


@pytest.mark.parametrize(
    ("leak_text", "kind"),
    [
        ("Use http://localhost:8080/seal as your source.", "source_url"),
        ("Make sure you complete E1.", "step_id"),
        ("The answer is Private Winner ZX.", "gold_answer"),
        ("Complete at least 3 required steps.", "required_step_count"),
        ("Optimize the scorer and required_proof_steps.", "scorer_term"),
    ],
)
def test_url_step_answer_and_scorer_leaks_are_rejected(
    leak_text: str, kind: str
) -> None:
    case = _case()
    findings = detect_query_leaks(case, leak_text)
    assert kind in {finding.kind for finding in findings}
    with pytest.raises(QueryLeakError):
        assert_no_query_leaks(case, leak_text)


def test_new_leak_and_validation_protocol_is_exact() -> None:
    payload = proof_step_case_dict()
    payload["query_rendering"]["forbidden_leaks"].remove("required_step_count")
    with pytest.raises(ValidationError, match="required_step_count"):
        CaseSpec.from_dict(payload)

    payload = proof_step_case_dict()
    payload["query_rendering"]["validation"].reverse()
    with pytest.raises(ValidationError, match="hard_rules"):
        CaseSpec.from_dict(payload)

    payload = proof_step_case_dict()
    payload["query_rendering"]["max_generation_attempts"] = 4
    with pytest.raises(ValidationError):
        CaseSpec.from_dict(payload)


def test_constraint_diff_is_empty_only_for_exact_generator_projection() -> None:
    case = _case()
    task = render_task(case)
    assert query_constraint_diff(case, task) == {}
    assert_query_case_alignment(case, task)

    changed = deepcopy(task)
    changed["query_contract"]["generator_view"]["constraints"][0] = (
        "does_not_wear_glasses"
    )
    assert "query_contract" in query_constraint_diff(case, changed)
    with pytest.raises(QueryAlignmentError):
        assert_query_case_alignment(case, changed)

    missing = deepcopy(task)
    missing["intent"] = missing["intent"].replace("- small bag\n", "")
    assert "query_text" in query_constraint_diff(case, missing)


def test_natural_generator_view_query_can_be_hash_bound_and_published() -> None:
    case = _case()
    query = _natural_query(case)

    assert validate_query_candidate(case, query, attempt=1) == query
    packet = build_blind_review_packet(case, attempt=1, query_text=query)
    review = _blind_record(case, query_text=query)
    task = render_task(
        case,
        query_text=query,
        blind_review_record=review,
    )

    assert packet["query"] == query
    assert packet["query_sha256"] == task["query_validation"][
        "blind_semantic_alignment"
    ]["query_sha256"]
    assert task["intent"] == query
    assert query_constraint_diff(case, task) == {}


def test_renderer_cannot_drop_constraint_option_or_target() -> None:
    case = _case()
    canonical = render_query(case)
    without_constraint = canonical.replace("- small bag\n", "")
    without_option = canonical.replace("- form b\n", "")
    without_target = canonical.replace(case.generator_view.target, "")
    assert query_constraint_diff(case, without_constraint)
    assert query_constraint_diff(case, without_option)
    assert query_constraint_diff(case, without_target)

    hard = build_hard_rule_pass_record(case, without_constraint, attempt=1)
    assert hard.checks.constraint_coverage is False
    assert hard.missing_constraints == ["small_bag"]
    assert hard.passed is False


def test_hard_rule_coverage_accepts_natural_punctuation_for_identifier_tokens() -> None:
    case = _case()
    case.generator_view.constraints = [
        "the_panasonic_51_61_display_is_not_a_verified_checkout_deal"
    ]
    case.generator_view.candidate_actions = ["keep_current_phone"]
    query = (
        "The Panasonic $51.61 display is not a verified checkout deal, so "
        "compare it with the option to keep current phone."
    )

    hard = build_hard_rule_pass_record(case, query, attempt=1)

    assert hard.missing_constraints == []
    assert hard.missing_options == []
    assert hard.passed is True


def test_hard_rule_and_manual_blind_review_are_both_required() -> None:
    case = _case()
    query = render_query(case)
    hard = build_hard_rule_pass_record(case, query, attempt=1)
    assert hard.passed is True
    assert hard.checks.model_dump() == {
        "constraint_coverage": True,
        "option_coverage": True,
        "no_url": True,
        "no_scorer_terms": True,
        "no_answer_leak": True,
    }

    accepted = build_query_acceptance_record(case, query, _blind_record(case))
    assert accepted.disposition == "accepted"
    assert_query_accepted(accepted)
    task = render_task(case, blind_review_record=_blind_record(case))
    assert task["query_validation"]["disposition"] == "accepted"


def test_blind_review_record_is_hash_bound_and_cannot_carry_gold() -> None:
    case = _case()
    record = _blind_record(case)
    record["query_sha256"] = "f" * 64
    with pytest.raises(QueryAlignmentError, match="different query"):
        build_query_acceptance_record(case, render_query(case), record)

    record = _blind_record(case)
    record["gold_answer"] = "form_a"
    with pytest.raises(ValidationError):
        BlindSemanticReviewRecordV3.model_validate(record)

    record = _blind_record(case)
    record["passed"] = False
    with pytest.raises(ValidationError, match="disagrees"):
        BlindSemanticReviewRecordV3.model_validate(record)


def test_failed_review_retries_then_discards_at_frozen_limit() -> None:
    case = _case()
    query = render_query(case)

    retry = build_query_acceptance_record(
        case, query, _blind_record(case, attempt=2, passed=False)
    )
    assert retry.disposition == "retry"
    with pytest.raises(QueryRetryRequiredError):
        assert_query_accepted(retry)

    discarded = build_query_acceptance_record(
        case,
        query,
        _blind_record(
            case, attempt=QUERY_MAX_GENERATION_ATTEMPTS, passed=False
        ),
    )
    assert discarded.disposition == "discarded"
    with pytest.raises(QueryCaseDiscardedError):
        assert_query_accepted(discarded)


def test_blind_review_packet_contains_only_allowed_public_inputs() -> None:
    packet = build_blind_review_packet(_case(), attempt=1)
    assert set(packet) == {
        "schema",
        "task_id",
        "attempt",
        "max_generation_attempts",
        "generator_view",
        "query",
        "generator_view_sha256",
        "query_sha256",
        "hard_rules",
    }
    blob = repr(packet)
    for private in (
        "evaluator_view",
        "required_proof_steps",
        "ev_seal",
        "http://localhost:8080",
        "acceptable_conclusions",
        "oracle",
    ):
        assert private not in blob


def _few_shots() -> list[dict]:
    return [
        {
            "generator_view": {
                "scenario": f"Scenario {index}",
                "constraints": [f"constraint_{index}"],
                "candidate_actions": [f"option_{index}_a", f"option_{index}_b"],
                "target": f"Compare the options for scenario {index}.",
            },
            "human_written_query": (
                f"Under constraint {index}, compare option {index} a and "
                f"option {index} b for scenario {index}."
            ),
        }
        for index in range(1, 4)
    ]


def test_three_few_shots_have_only_generator_view_and_human_query() -> None:
    rows = validate_sanitized_few_shot_examples(_few_shots())
    assert all(isinstance(row, SanitizedFewShotExampleV3) for row in rows)
    prompt = build_query_generation_prompt(_case(), rows)
    assert len(prompt["examples"]) == 3
    assert set(prompt["examples"][0]) == {
        "generator_view",
        "human_written_query",
    }
    blob = repr(prompt)
    assert "evaluator_view" not in blob
    assert "required_proof_steps" not in blob

    leaked = _few_shots()
    leaked[0]["evaluator_view"] = {"gold_answer": "x"}
    with pytest.raises(ValidationError):
        validate_sanitized_few_shot_examples(leaked)

    quota = _few_shots()
    quota[0]["human_written_query"] += " Cite at least 3 sources."
    with pytest.raises(ValidationError, match="scorer"):
        validate_sanitized_few_shot_examples(quota)

    missing_constraint = render_query(_case()).replace("- small bag\n", "")
    with pytest.raises(QueryAlignmentError):
        assert_query_case_alignment(_case(), missing_constraint)
