from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.import_v3_review_decisions import main as import_review_main
from src.eval.evidence_graph import canonical_json_bytes
from src.eval.review_decisions_v3 import (
    ReviewDecisionError,
    evaluate_review_decisions,
)


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/pilot_v3/review_packets/cand_audio_glasses_flight"
QUEUE = PACKET / "review_queue.json"
SIMULATED = (
    ROOT
    / "data/pilot_v3/review_decisions"
    / "cand_audio_glasses_flight.llm_simulated.json"
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _inputs() -> tuple[dict, dict]:
    return _json(QUEUE), _json(SIMULATED)


def test_llm_simulation_approves_items_but_cannot_promote_candidate() -> None:
    queue, decisions = _inputs()
    report = evaluate_review_decisions(
        queue,
        decisions,
        review_authority="llm_simulation",
    )

    assert report["status"] == "rejected"
    assert report["counts"] == {
        "review_items": 28,
        "semantic_items": 18,
        "structured_items": 10,
        "support_items": 0,
        "complete_item_reviews": 28,
        "first_pass_approved_items": 28,
        "formal_promotion_candidates": 0,
        "known_evidence_gaps": 3,
    }
    assert len(report["first_pass_approved_evidence_ids"]) == 28
    assert report["formal_promotion_candidate_ids"] == []
    gate = report["candidate_gate"]
    assert gate["eligible_for_case_generation"] is False
    assert gate["blocked_by_evidence_gap_ids"] == [
        "gap_001",
        "gap_002",
        "gap_003",
    ]
    assert gate["blocker_codes"] == [
        "non_human_review_authority",
        "review_not_independent",
        "current_snapshot_has_known_evidence_gaps",
        "snapshot_marked_ineligible",
        "candidate_rejected",
        "new_snapshot_required",
        "candidate_rejected_by_gap_review",
    ]
    assert all(
        item["disposition"] == "llm_first_pass_approved_non_gold"
        for item in report["item_results"]
    )

    digest = report["report_sha256"]
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    assert digest == hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def test_browser_string_tokens_are_normalized_for_human_review() -> None:
    queue, decisions = _inputs()
    decisions["reviewer_id"] = "human-reviewer-01"
    decisions["independent_review"] = True
    decisions["candidate_verdict"] = "eligible"
    for gap in decisions["evidence_gaps"]:
        gap["resolution"] = "unresolved"
    for index, item in enumerate(decisions["items"]):
        item["support_span_correct"] = "yes"
        item["context_sufficient"] = "yes"
        item["source_scope_correct"] = "yes"
        item["proposition_supported"] = (
            "yes" if queue["items"][index]["review_kind"] == "semantic" else "not_applicable"
        )

    report = evaluate_review_decisions(
        queue,
        decisions,
        review_authority="human",
    )

    assert report["counts"]["formal_promotion_candidates"] == 28
    assert len(report["formal_promotion_candidate_ids"]) == 28
    assert report["candidate_gate"]["eligible_for_case_generation"] is False
    assert report["candidate_gate"]["blocker_codes"] == [
        "current_snapshot_has_known_evidence_gaps",
        "snapshot_marked_ineligible",
    ]


def test_old_snapshot_gap_cannot_be_closed_by_review_text() -> None:
    queue, decisions = _inputs()
    decisions["reviewer_id"] = "human-reviewer-01"
    decisions["independent_review"] = True
    decisions["candidate_verdict"] = "eligible"
    for gap in decisions["evidence_gaps"]:
        gap["resolution"] = "resolved_by_new_evidence"

    report = evaluate_review_decisions(
        queue,
        decisions,
        review_authority="human",
    )

    assert report["candidate_gate"]["eligible_for_case_generation"] is False
    assert "new_snapshot_required" in report["candidate_gate"]["blocker_codes"]
    assert all(
        result["resolved_in_current_snapshot"] is False
        for result in report["evidence_gap_results"]
    )


def test_semantic_approval_without_proposition_confirmation_is_incomplete() -> None:
    queue, decisions = _inputs()
    target = next(
        item
        for item in decisions["items"]
        if item["review_item_id"] == "assert_over_ear_seal"
    )
    target["proposition_supported"] = False

    report = evaluate_review_decisions(
        queue,
        decisions,
        review_authority="llm_simulation",
    )
    result = next(
        item
        for item in report["item_results"]
        if item["review_item_id"] == "assert_over_ear_seal"
    )
    assert result["review_complete"] is False
    assert result["first_pass_approved"] is False
    assert result["reason_codes"] == ["proposition_not_confirmed"]
    assert report["counts"]["first_pass_approved_items"] == 27
    assert "item_reviews_incomplete" in report["candidate_gate"]["blocker_codes"]


def test_identity_and_item_coverage_are_fail_closed() -> None:
    queue, decisions = _inputs()
    bad_hash = copy.deepcopy(decisions)
    bad_hash["evidence_graph_hash"] = "0" * 64
    with pytest.raises(ReviewDecisionError, match="does not match"):
        evaluate_review_decisions(
            queue,
            bad_hash,
            review_authority="llm_simulation",
        )

    missing_item = copy.deepcopy(decisions)
    missing_item["items"].pop()
    with pytest.raises(ReviewDecisionError, match="exactly cover"):
        evaluate_review_decisions(
            queue,
            missing_item,
            review_authority="llm_simulation",
        )


def test_clean_human_review_can_pass_only_on_gap_free_eligible_snapshot() -> None:
    queue, decisions = _inputs()
    queue["eligible_for_case_generation"] = True
    queue["evidence_gaps"] = []
    decisions["evidence_gaps"] = []
    decisions["reviewer_id"] = "human-reviewer-01"
    decisions["independent_review"] = True
    decisions["candidate_verdict"] = "eligible"

    report = evaluate_review_decisions(
        queue,
        decisions,
        review_authority="human",
    )
    assert report["status"] == "eligible_for_case_generation"
    assert report["candidate_gate"]["eligible_for_case_generation"] is True
    assert report["candidate_gate"]["blocker_codes"] == []


def test_cli_verifies_packet_and_writes_blocked_report(tmp_path: Path) -> None:
    output = tmp_path / "review-gate.json"
    assert import_review_main(
        [
            "--review-packet",
            str(PACKET),
            "--decisions",
            str(SIMULATED),
            "--authority",
            "llm_simulation",
            "--out",
            str(output),
        ]
    ) == 0
    report = _json(output)
    assert report["status"] == "rejected"
    assert report["input_hashes"]["review_packet_manifest_sha256"] == (
        hashlib.sha256((PACKET / "manifest.json").read_bytes()).hexdigest()
    )
    assert report["candidate_gate"]["blocked_by_evidence_gap_ids"] == [
        "gap_001",
        "gap_002",
        "gap_003",
    ]
