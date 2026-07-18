"""Fail-closed ingestion of DRA v3 frozen-evidence review decisions.

Review decisions can approve individual extracted evidence, but they cannot
change the bytes or completeness claims of the frozen corpus snapshot.  A
candidate with a known evidence gap must therefore be rebuilt against a new
snapshot or rejected.  LLM review is recorded as a non-gold first pass and is
never accepted as formal human authority.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from src.eval.evidence_graph import canonical_json_bytes


REVIEW_QUEUE_SCHEMA = "dra_v3_human_review_queue_v1"
REVIEW_DECISIONS_SCHEMA = "dra_v3_human_review_decisions_v1"
REVIEW_GATE_REPORT_SCHEMA = "dra_v3_review_gate_report_v1"
REVIEW_AUTHORITIES = {"human", "llm_simulation"}

_CANDIDATE_VERDICTS = {"pending", "eligible", "reject", "revise_scope"}
_ITEM_DECISIONS = {"pending", "approve", "reject", "needs_more_context"}
_GAP_RESOLUTIONS = {
    "unresolved",
    "resolved_by_new_evidence",
    "resolved_by_scope_change",
    "reject_candidate",
}
_REVIEW_KINDS = {"semantic", "structured", "support"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_QUEUE_BASE_KEYS = {
    "schema_version",
    "corpus_snapshot",
    "evidence_graph_hash",
    "corpus_registry_hash",
    "inventory_sha256",
    "candidate_id",
    "status",
    "eligible_for_case_generation",
    "review_policy",
    "evidence_gaps",
    "items",
    "sources",
}
_QUEUE_ITEM_BASE_KEYS = {
    "review_item_id",
    "review_kind",
    "evidence_id",
    "node_type",
    "subject",
    "predicate",
    "object",
    "source_url",
    "source_type",
    "content_sha256",
    "body_support",
    "search_snippet_support",
    "verifier",
    "metadata",
    "proposed_propositions",
    "support_spans",
}
_DECISION_KEYS = {
    "schema_version",
    "corpus_snapshot",
    "evidence_graph_hash",
    "candidate_id",
    "reviewer_id",
    "reviewed_at_utc",
    "independent_review",
    "candidate_verdict",
    "items",
    "evidence_gaps",
}
_DECISION_ITEM_KEYS = {
    "review_item_id",
    "decision",
    "support_span_correct",
    "proposition_supported",
    "source_scope_correct",
    "context_sufficient",
    "reviewer_note",
}
_GAP_KEYS = {"gap_id", "description", "resolution", "reviewer_note"}
_REQUIRED_REVIEW_POLICY = {
    "frozen_bytes_are_authoritative": True,
    "live_page_may_override_snapshot": False,
    "review_does_not_auto_promote": True,
    "semantic_claims_require_scope_review": True,
    "structured_claims_require_span_review": True,
}


class ReviewDecisionError(ValueError):
    """A review queue or decision file violates the v3 review contract."""


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewDecisionError(f"{path}: expected an object")
    return dict(value)


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], path: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ReviewDecisionError(f"{path}: missing fields {missing}")
    if unknown:
        raise ReviewDecisionError(f"{path}: unknown fields {unknown}")


def _non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewDecisionError(f"{path}: expected a non-empty string")
    return value


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_utc_timestamp(value: object) -> str:
    text = _non_empty_string(value, "decisions.reviewed_at_utc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewDecisionError(
            "decisions.reviewed_at_utc: expected an ISO-8601 UTC timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReviewDecisionError(
            "decisions.reviewed_at_utc: timestamp must include the UTC offset"
        )
    return text


def _tri_state(value: object, path: str) -> bool | None:
    if type(value) is bool:
        return value
    if value is None:
        return None
    if isinstance(value, str):
        mapping: dict[str, bool | None] = {
            "yes": True,
            "no": False,
            "unknown": None,
            "not_applicable": None,
        }
        if value in mapping:
            return mapping[value]
    raise ReviewDecisionError(
        f"{path}: expected true/false/null or yes/no/unknown/not_applicable"
    )


def _validated_queue(queue: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    value = _object(queue, "queue")
    allowed_keys = _QUEUE_BASE_KEYS | {"translation"}
    if set(value) not in (_QUEUE_BASE_KEYS, allowed_keys):
        missing = sorted(_QUEUE_BASE_KEYS - set(value))
        unknown = sorted(set(value) - allowed_keys)
        if missing:
            raise ReviewDecisionError(f"queue: missing fields {missing}")
        raise ReviewDecisionError(f"queue: unknown fields {unknown}")
    if value["schema_version"] != REVIEW_QUEUE_SCHEMA:
        raise ReviewDecisionError(
            f"queue.schema_version: expected {REVIEW_QUEUE_SCHEMA!r}"
        )
    _non_empty_string(value["candidate_id"], "queue.candidate_id")
    _non_empty_string(value["corpus_snapshot"], "queue.corpus_snapshot")
    graph_hash = _non_empty_string(
        value["evidence_graph_hash"], "queue.evidence_graph_hash"
    )
    if not _SHA256_RE.fullmatch(graph_hash):
        raise ReviewDecisionError(
            "queue.evidence_graph_hash: expected lowercase SHA-256"
        )
    for field in ("corpus_registry_hash", "inventory_sha256"):
        digest = _non_empty_string(value[field], f"queue.{field}")
        if not _SHA256_RE.fullmatch(digest):
            raise ReviewDecisionError(f"queue.{field}: expected lowercase SHA-256")
    if type(value["eligible_for_case_generation"]) is not bool:
        raise ReviewDecisionError(
            "queue.eligible_for_case_generation: expected a boolean"
        )
    if value["review_policy"] != _REQUIRED_REVIEW_POLICY:
        raise ReviewDecisionError(
            "queue.review_policy: frozen review safeguards do not match v1"
        )

    raw_items = value["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise ReviewDecisionError("queue.items: expected a non-empty array")
    items: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        item = _object(raw_item, f"queue.items[{index}]")
        allowed_item_keys = _QUEUE_ITEM_BASE_KEYS | {"translation_zh"}
        if set(item) not in (_QUEUE_ITEM_BASE_KEYS, allowed_item_keys):
            missing = sorted(_QUEUE_ITEM_BASE_KEYS - set(item))
            unknown = sorted(set(item) - allowed_item_keys)
            if missing:
                raise ReviewDecisionError(
                    f"queue.items[{index}]: missing fields {missing}"
                )
            raise ReviewDecisionError(
                f"queue.items[{index}]: unknown fields {unknown}"
            )
        review_item_id = _non_empty_string(
            item["review_item_id"], f"queue.items[{index}].review_item_id"
        )
        if review_item_id in seen_item_ids:
            raise ReviewDecisionError(
                f"queue.items[{index}].review_item_id: duplicate {review_item_id!r}"
            )
        seen_item_ids.add(review_item_id)
        if item["evidence_id"] != review_item_id:
            raise ReviewDecisionError(
                f"queue.items[{index}]: review_item_id must equal evidence_id"
            )
        if item["review_kind"] not in _REVIEW_KINDS:
            raise ReviewDecisionError(
                f"queue.items[{index}].review_kind: unsupported value"
            )
        spans = item["support_spans"]
        propositions = item["proposed_propositions"]
        if not isinstance(spans, list) or not spans:
            raise ReviewDecisionError(
                f"queue.items[{index}].support_spans: expected a non-empty array"
            )
        if not isinstance(propositions, list):
            raise ReviewDecisionError(
                f"queue.items[{index}].proposed_propositions: expected an array"
            )
        items.append(item)

    gaps = value["evidence_gaps"]
    if not isinstance(gaps, list) or any(
        not isinstance(gap, str) or not gap.strip() for gap in gaps
    ):
        raise ReviewDecisionError(
            "queue.evidence_gaps: expected a list of non-empty strings"
        )
    if len(gaps) != len(set(gaps)):
        raise ReviewDecisionError("queue.evidence_gaps: descriptions must be unique")
    return items, list(gaps)


def _validated_decisions(
    decisions: Mapping[str, Any],
    *,
    queue: Mapping[str, Any],
    queue_items: list[dict[str, Any]],
    queue_gaps: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    value = _object(decisions, "decisions")
    _exact_keys(value, _DECISION_KEYS, "decisions")
    if value["schema_version"] != REVIEW_DECISIONS_SCHEMA:
        raise ReviewDecisionError(
            f"decisions.schema_version: expected {REVIEW_DECISIONS_SCHEMA!r}"
        )
    for field in ("candidate_id", "corpus_snapshot", "evidence_graph_hash"):
        if value[field] != queue[field]:
            raise ReviewDecisionError(
                f"decisions.{field}: does not match the frozen review queue"
            )
    reviewer_id = _non_empty_string(value["reviewer_id"], "decisions.reviewer_id")
    reviewed_at_utc = _validate_utc_timestamp(value["reviewed_at_utc"])
    if type(value["independent_review"]) is not bool:
        raise ReviewDecisionError("decisions.independent_review: expected a boolean")
    verdict = value["candidate_verdict"]
    if verdict not in _CANDIDATE_VERDICTS:
        raise ReviewDecisionError(
            f"decisions.candidate_verdict: unsupported value {verdict!r}"
        )

    raw_items = value["items"]
    if not isinstance(raw_items, list):
        raise ReviewDecisionError("decisions.items: expected an array")
    decisions_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(raw_items):
        item = _object(raw_item, f"decisions.items[{index}]")
        _exact_keys(item, _DECISION_ITEM_KEYS, f"decisions.items[{index}]")
        review_item_id = _non_empty_string(
            item["review_item_id"], f"decisions.items[{index}].review_item_id"
        )
        if review_item_id in decisions_by_id:
            raise ReviewDecisionError(
                f"decisions.items[{index}].review_item_id: duplicate {review_item_id!r}"
            )
        decision = item["decision"]
        if decision not in _ITEM_DECISIONS:
            raise ReviewDecisionError(
                f"decisions.items[{index}].decision: unsupported value {decision!r}"
            )
        if not isinstance(item["reviewer_note"], str):
            raise ReviewDecisionError(
                f"decisions.items[{index}].reviewer_note: expected a string"
            )
        normalized = dict(item)
        for field in (
            "support_span_correct",
            "proposition_supported",
            "source_scope_correct",
            "context_sufficient",
        ):
            normalized[field] = _tri_state(
                item[field], f"decisions.items[{index}].{field}"
            )
        decisions_by_id[review_item_id] = normalized

    expected_item_ids = {str(item["review_item_id"]) for item in queue_items}
    actual_item_ids = set(decisions_by_id)
    if actual_item_ids != expected_item_ids:
        raise ReviewDecisionError(
            "decisions.items: IDs must exactly cover the review queue; "
            f"missing={sorted(expected_item_ids - actual_item_ids)}, "
            f"unknown={sorted(actual_item_ids - expected_item_ids)}"
        )

    raw_gaps = value["evidence_gaps"]
    if not isinstance(raw_gaps, list):
        raise ReviewDecisionError("decisions.evidence_gaps: expected an array")
    gaps_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_gap in enumerate(raw_gaps):
        gap = _object(raw_gap, f"decisions.evidence_gaps[{index}]")
        _exact_keys(gap, _GAP_KEYS, f"decisions.evidence_gaps[{index}]")
        gap_id = _non_empty_string(
            gap["gap_id"], f"decisions.evidence_gaps[{index}].gap_id"
        )
        if gap_id in gaps_by_id:
            raise ReviewDecisionError(
                f"decisions.evidence_gaps[{index}].gap_id: duplicate {gap_id!r}"
            )
        resolution = gap["resolution"]
        if resolution not in _GAP_RESOLUTIONS:
            raise ReviewDecisionError(
                f"decisions.evidence_gaps[{index}].resolution: unsupported value"
            )
        if not isinstance(gap["reviewer_note"], str):
            raise ReviewDecisionError(
                f"decisions.evidence_gaps[{index}].reviewer_note: expected a string"
            )
        gaps_by_id[gap_id] = gap

    expected_gap_ids = [f"gap_{index:03d}" for index in range(1, len(queue_gaps) + 1)]
    if set(gaps_by_id) != set(expected_gap_ids):
        raise ReviewDecisionError(
            "decisions.evidence_gaps: IDs must exactly cover the queue; "
            f"missing={sorted(set(expected_gap_ids) - set(gaps_by_id))}, "
            f"unknown={sorted(set(gaps_by_id) - set(expected_gap_ids))}"
        )
    for gap_id, description in zip(expected_gap_ids, queue_gaps):
        if gaps_by_id[gap_id]["description"] != description:
            raise ReviewDecisionError(
                f"decisions.evidence_gaps[{gap_id}].description: "
                "does not match the frozen review queue"
            )

    ordered_items = [
        decisions_by_id[str(item["review_item_id"])] for item in queue_items
    ]
    ordered_gaps = [gaps_by_id[gap_id] for gap_id in expected_gap_ids]
    identity = {
        "reviewer_id": reviewer_id,
        "reviewed_at_utc": reviewed_at_utc,
        "independent_review": value["independent_review"],
        "candidate_verdict": verdict,
    }
    return ordered_items, ordered_gaps, identity


def _item_result(
    queue_item: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    review_authority: str,
    independent_review: bool,
) -> dict[str, Any]:
    kind = str(queue_item["review_kind"])
    selected = str(decision["decision"])
    note = str(decision["reviewer_note"])
    checks = {
        "support_span_correct": decision["support_span_correct"],
        "proposition_supported": decision["proposition_supported"],
        "source_scope_correct": decision["source_scope_correct"],
        "context_sufficient": decision["context_sufficient"],
    }
    reason_codes: list[str] = []

    if selected == "pending":
        reason_codes.append("item_decision_pending")
    elif selected == "needs_more_context":
        if checks["context_sufficient"] is not False:
            reason_codes.append("needs_more_context_without_negative_context_check")
        if not note.strip():
            reason_codes.append("reviewer_note_required")
    elif selected == "reject":
        if not any(value is False for value in checks.values()):
            reason_codes.append("rejection_without_negative_check")
        if not note.strip():
            reason_codes.append("reviewer_note_required")
    elif selected == "approve":
        if checks["support_span_correct"] is not True:
            reason_codes.append("support_span_not_confirmed")
        if checks["context_sufficient"] is not True:
            reason_codes.append("context_not_confirmed")
        if kind == "semantic":
            if checks["proposition_supported"] is not True:
                reason_codes.append("proposition_not_confirmed")
            if checks["source_scope_correct"] is not True:
                reason_codes.append("source_scope_not_confirmed")
        elif kind == "structured":
            if checks["proposition_supported"] is not None:
                reason_codes.append("structured_proposition_must_be_not_applicable")
            if checks["source_scope_correct"] not in (True, None):
                reason_codes.append("structured_source_scope_rejected")
        else:
            if checks["proposition_supported"] is False:
                reason_codes.append("support_item_proposition_rejected")
            if checks["source_scope_correct"] is False:
                reason_codes.append("support_item_scope_rejected")

    review_complete = not reason_codes
    first_pass_approved = selected == "approve" and review_complete
    formal_promotion_candidate = (
        first_pass_approved
        and review_authority == "human"
        and independent_review
    )
    if formal_promotion_candidate:
        disposition = "human_approved_pending_materialization"
    elif first_pass_approved and review_authority == "llm_simulation":
        disposition = "llm_first_pass_approved_non_gold"
    elif first_pass_approved:
        disposition = "approved_but_not_independent"
    elif selected == "reject" and review_complete:
        disposition = "rejected"
    elif selected == "needs_more_context" and review_complete:
        disposition = "needs_more_context"
    else:
        disposition = "incomplete"

    return {
        "review_item_id": queue_item["review_item_id"],
        "evidence_id": queue_item["evidence_id"],
        "review_kind": kind,
        "decision": selected,
        "checks": checks,
        "review_complete": review_complete,
        "first_pass_approved": first_pass_approved,
        "formal_promotion_candidate": formal_promotion_candidate,
        "disposition": disposition,
        "reason_codes": reason_codes,
    }


def evaluate_review_decisions(
    queue: Mapping[str, Any],
    decisions: Mapping[str, Any],
    *,
    review_authority: str,
    review_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate one decision document and return a non-mutating gate report."""

    if review_authority not in REVIEW_AUTHORITIES:
        raise ReviewDecisionError(
            f"review_authority: expected one of {sorted(REVIEW_AUTHORITIES)}"
        )
    if review_packet_manifest_sha256 is not None and not _SHA256_RE.fullmatch(
        review_packet_manifest_sha256
    ):
        raise ReviewDecisionError(
            "review_packet_manifest_sha256: expected lowercase SHA-256"
        )

    queue_items, queue_gaps = _validated_queue(queue)
    normalized_items, normalized_gaps, identity = _validated_decisions(
        decisions,
        queue=queue,
        queue_items=queue_items,
        queue_gaps=queue_gaps,
    )
    independent = bool(identity["independent_review"])
    item_results = [
        _item_result(
            queue_item,
            decision,
            review_authority=review_authority,
            independent_review=independent,
        )
        for queue_item, decision in zip(queue_items, normalized_items)
    ]

    gap_results = []
    for index, (description, decision) in enumerate(
        zip(queue_gaps, normalized_gaps), 1
    ):
        resolution = str(decision["resolution"])
        if resolution == "unresolved":
            required_action = "capture_new_evidence_or_reject_candidate"
        elif resolution == "resolved_by_new_evidence":
            required_action = "rebuild_and_review_a_new_frozen_snapshot"
        elif resolution == "resolved_by_scope_change":
            required_action = "compile_and_review_a_new_scoped_candidate"
        else:
            required_action = "reject_candidate"
        gap_results.append(
            {
                "gap_id": f"gap_{index:03d}",
                "description": description,
                "review_resolution": resolution,
                "resolved_in_current_snapshot": False,
                "required_action": required_action,
            }
        )

    approved_ids = [
        str(result["evidence_id"])
        for result in item_results
        if result["first_pass_approved"]
    ]
    formal_ids = [
        str(result["evidence_id"])
        for result in item_results
        if result["formal_promotion_candidate"]
    ]
    all_items_complete = all(result["review_complete"] for result in item_results)
    all_items_approved = all(result["first_pass_approved"] for result in item_results)

    blocker_codes: list[str] = []
    if review_authority != "human":
        blocker_codes.append("non_human_review_authority")
    if not independent:
        blocker_codes.append("review_not_independent")
    if not all_items_complete:
        blocker_codes.append("item_reviews_incomplete")
    if not all_items_approved:
        blocker_codes.append("not_all_review_items_approved")
    if queue_gaps:
        blocker_codes.append("current_snapshot_has_known_evidence_gaps")
    if queue.get("eligible_for_case_generation") is not True:
        blocker_codes.append("snapshot_marked_ineligible")

    verdict = str(identity["candidate_verdict"])
    if verdict == "pending":
        blocker_codes.append("candidate_verdict_pending")
    elif verdict == "reject":
        blocker_codes.append("candidate_rejected")
    elif verdict == "revise_scope":
        blocker_codes.append("candidate_scope_revision_required")
    if any(
        gap["review_resolution"] == "resolved_by_new_evidence"
        for gap in gap_results
    ):
        blocker_codes.append("new_snapshot_required")
    if any(
        gap["review_resolution"] == "resolved_by_scope_change"
        for gap in gap_results
    ):
        blocker_codes.append("new_scoped_candidate_required")
    if any(
        gap["review_resolution"] == "reject_candidate" for gap in gap_results
    ):
        blocker_codes.append("candidate_rejected_by_gap_review")

    blocker_codes = list(dict.fromkeys(blocker_codes))
    eligible = verdict == "eligible" and not blocker_codes
    if eligible:
        status = "eligible_for_case_generation"
    elif "candidate_rejected" in blocker_codes or (
        "candidate_rejected_by_gap_review" in blocker_codes
    ):
        status = "rejected"
    elif "candidate_scope_revision_required" in blocker_codes:
        status = "scope_revision_required"
    else:
        status = "blocked"

    required_actions: list[str] = []
    if queue_gaps:
        required_actions.append("capture_and_freeze_missing_evidence_or_reject_candidate")
    if review_authority != "human" or not independent:
        required_actions.append("obtain_independent_human_review_before_formal_gold")
    if not all_items_complete or not all_items_approved:
        required_actions.append("resolve_non_approved_review_items")
    if verdict == "pending":
        required_actions.append("set_candidate_verdict_after_snapshot_review")
    if verdict == "revise_scope":
        required_actions.append("create_a_new_scoped_candidate_id")

    counts = {
        "review_items": len(item_results),
        "semantic_items": sum(
            result["review_kind"] == "semantic" for result in item_results
        ),
        "structured_items": sum(
            result["review_kind"] == "structured" for result in item_results
        ),
        "support_items": sum(
            result["review_kind"] == "support" for result in item_results
        ),
        "complete_item_reviews": sum(
            result["review_complete"] for result in item_results
        ),
        "first_pass_approved_items": len(approved_ids),
        "formal_promotion_candidates": len(formal_ids),
        "known_evidence_gaps": len(gap_results),
    }
    report: dict[str, Any] = {
        "schema_version": REVIEW_GATE_REPORT_SCHEMA,
        "status": status,
        "candidate_id": queue["candidate_id"],
        "corpus_snapshot": queue["corpus_snapshot"],
        "evidence_graph_hash": queue["evidence_graph_hash"],
        "review_authority": review_authority,
        "review_identity": identity,
        "input_hashes": {
            "review_packet_manifest_sha256": review_packet_manifest_sha256,
            "review_queue_canonical_sha256": _sha256(queue),
            "review_decisions_canonical_sha256": _sha256(decisions),
        },
        "counts": counts,
        "item_results": item_results,
        "first_pass_approved_evidence_ids": approved_ids,
        "formal_promotion_candidate_ids": formal_ids,
        "evidence_gap_results": gap_results,
        "candidate_gate": {
            "requested_verdict": verdict,
            "queue_declared_eligible": queue["eligible_for_case_generation"],
            "all_item_reviews_complete": all_items_complete,
            "all_review_items_approved": all_items_approved,
            "current_snapshot_has_no_known_gaps": not queue_gaps,
            "formal_human_authority": review_authority == "human",
            "independent_review": independent,
            "eligible_for_case_generation": eligible,
            "blocked_by_evidence_gap_ids": [
                str(result["gap_id"]) for result in gap_results
            ],
            "blocker_codes": blocker_codes,
            "required_actions": required_actions,
        },
    }
    report["report_sha256"] = _sha256(report)
    return report


__all__ = [
    "REVIEW_AUTHORITIES",
    "REVIEW_DECISIONS_SCHEMA",
    "REVIEW_GATE_REPORT_SCHEMA",
    "REVIEW_QUEUE_SCHEMA",
    "ReviewDecisionError",
    "evaluate_review_decisions",
]
