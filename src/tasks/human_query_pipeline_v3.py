"""Human-governed DRA v3 query authoring and release artifacts.

This module keeps interactive coding agents outside the formal data path.
Humans select sources, approve graph semantics, and author the development
few-shot queries.  A registered API model receives only GeneratorView plus the
three sanitized examples.  Deterministic checks and a blind review then create
the query-release certificate consumed by formal compilation.

The module does not decide whether a proposition is true or whether a proof
step is necessary.  It validates and hash-binds the human decisions that make
those judgments authoritative.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.eval.case_schema_v3 import (
    QUERY_MAX_GENERATION_ATTEMPTS,
    CaseSpecV3,
    GeneratorViewV3,
    validate_case,
)
from src.tasks.query_renderer_v3 import (
    BlindSemanticReviewRecordV3,
    HardRulePassRecordV3,
    QueryAcceptanceRecordV3,
    SanitizedFewShotExampleV3,
    assert_query_accepted,
    build_blind_review_packet,
    build_hard_rule_pass_record,
    build_query_acceptance_record,
    build_query_generation_prompt,
    generator_view_sha256,
    query_sha256,
    validate_blind_semantic_review,
    validate_sanitized_few_shot_examples,
)


SOURCE_SELECTION_SCHEMA = "dra_v3_human_source_selection_v1"
GRAPH_ANNOTATION_SCHEMA = "dra_v3_human_graph_annotation_v1"
FEW_SHOT_EXAMPLE_SCHEMA = "dra_v3_human_few_shot_example_v1"
FEW_SHOT_DATASET_SCHEMA = "dra_v3_human_few_shot_dataset_v1"
RENDERER_CONFIG_SCHEMA = "dra_v3_query_renderer_config_v1"
GENERATION_RECORD_SCHEMA = "dra_v3_query_generation_record_v1"
ATTEMPT_CLOSURE_SCHEMA = "dra_v3_query_attempt_closure_v1"
HUMAN_BLIND_REVIEW_SCHEMA = "dra_v3_human_blind_query_review_v1"
QUERY_RELEASE_SCHEMA = "dra_v3_human_query_release_v1"

HUMAN_ATTESTATION = "human_completed_without_model_substitution"
BLIND_REVIEW_ATTESTATION = "reviewed_only_generator_view_and_query"
RENDERER_INVOCATION_MODE = "registered_api_renderer"

_SHA256_RE = r"^[0-9a-f]{64}$"
_SAFE_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
_SAFE_LOWER_ID_RE = r"^[a-z0-9][a-z0-9_-]{0,127}$"
_ISO_UTC_RE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
_ENV_RE = r"^[A-Z_][A-Z0-9_]*$"


class HumanQueryPipelineError(ValueError):
    """A formal human-query artifact is missing, inconsistent, or unsafe."""


class _StrictRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _absolute_http_url(value: str, field_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    return value.rstrip("/")


def _require_role(actor: "HumanActorV1 | None", expected: str, label: str) -> None:
    if actor is None or actor.role != expected:
        raise HumanQueryPipelineError(f"{label} must have role={expected!r}")


class HumanActorV1(_StrictRecord):
    actor_type: Literal["human"] = "human"
    actor_id: str = Field(pattern=_SAFE_ID_RE)
    role: Literal[
        "source_selector",
        "graph_annotator",
        "graph_adjudicator",
        "few_shot_query_author",
        "few_shot_adjudicator",
        "blind_query_reviewer",
    ]
    attestation: Literal["human_completed_without_model_substitution"] = (
        HUMAN_ATTESTATION
    )


class SourceRequirementV1(_StrictRecord):
    source_role: Literal["product", "mechanism", "community", "other"]
    purpose: str = Field(min_length=8)
    minimum_sources: int = Field(ge=1, le=100)
    critical: bool


class SourceSearchSelectionV1(_StrictRecord):
    search_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    query: str = Field(min_length=2)
    max_results: int = Field(ge=1, le=100)
    include_domains: list[str]
    required_urls: list[str] = Field(min_length=1)

    @field_validator("required_urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        normalized = [_absolute_http_url(value, "required_urls") for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("required_urls must be unique within one search")
        return normalized


class SelectedSourceV1(_StrictRecord):
    registry_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    source_type: Literal["magento", "postmill", "wikipedia"]
    url: str
    extract_depth: Literal["basic", "advanced"]
    source_role: Literal["product", "mechanism", "community", "other"]
    selection_rationale: str = Field(min_length=8)
    critical_candidate: bool

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _absolute_http_url(value, "url")


class HumanSourceSelectionV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_source_selection_v1"] = (
        SOURCE_SELECTION_SCHEMA
    )
    candidate_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    corpus_snapshot: str = Field(pattern=_SAFE_LOWER_ID_RE)
    run_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    research_goal: str = Field(min_length=20)
    proposal_origin: Literal["human_search", "deterministic_registry_search"]
    selected_by: HumanActorV1
    selected_at_utc: str = Field(pattern=_ISO_UTC_RE)
    source_requirements: list[SourceRequirementV1] = Field(min_length=2)
    searches: list[SourceSearchSelectionV1] = Field(min_length=1)
    selected_sources: list[SelectedSourceV1] = Field(min_length=2)
    source_identity: dict[str, str] = Field(min_length=1)
    status: Literal["approved_for_capture"] = "approved_for_capture"

    @model_validator(mode="after")
    def validate_human_selection(self) -> "HumanSourceSelectionV1":
        _require_role(self.selected_by, "source_selector", "selected_by")
        search_ids = [item.search_id for item in self.searches]
        registry_ids = [item.registry_id for item in self.selected_sources]
        urls = [item.url for item in self.selected_sources]
        if len(search_ids) != len(set(search_ids)):
            raise ValueError("search_id values must be unique")
        if len(registry_ids) != len(set(registry_ids)):
            raise ValueError("registry_id values must be unique")
        if len(urls) != len(set(urls)):
            raise ValueError("selected source URLs must be unique")
        required_urls = {
            value for search in self.searches for value in search.required_urls
        }
        missing = sorted(set(urls) - required_urls)
        if missing:
            raise ValueError(
                "every selected source must be witnessed by a recorded search; "
                f"missing={missing}"
            )
        counts = Counter(item.source_role for item in self.selected_sources)
        duplicate_requirements = [
            role
            for role, count in Counter(
                item.source_role for item in self.source_requirements
            ).items()
            if count > 1
        ]
        if duplicate_requirements:
            raise ValueError(
                f"source requirements repeat roles: {sorted(duplicate_requirements)}"
            )
        shortfalls = {
            item.source_role: {
                "required": item.minimum_sources,
                "selected": counts[item.source_role],
            }
            for item in self.source_requirements
            if counts[item.source_role] < item.minimum_sources
        }
        if shortfalls:
            raise ValueError(f"source-role requirements are not met: {shortfalls}")
        return self


def capture_plan_from_human_selection(
    value: HumanSourceSelectionV1 | Mapping[str, Any],
) -> dict[str, Any]:
    selection = (
        value
        if isinstance(value, HumanSourceSelectionV1)
        else HumanSourceSelectionV1.model_validate(dict(value))
    )
    return {
        "schema_version": "dra_v3_candidate_capture_plan_v1",
        "candidate_id": selection.candidate_id,
        "corpus_snapshot": selection.corpus_snapshot,
        "run_id": selection.run_id,
        "searches": [
            item.model_dump(mode="json") for item in selection.searches
        ],
        "extracts": [
            {
                "registry_id": item.registry_id,
                "source_type": item.source_type,
                "url": item.url,
                "extract_depth": item.extract_depth,
            }
            for item in selection.selected_sources
        ],
        "source_identity": dict(selection.source_identity),
        "metadata": {
            "authoring_policy": "human_source_selection_v1",
            "source_selection_sha256": artifact_sha256(selection),
            "selected_by": selection.selected_by.actor_id,
            "selected_at_utc": selection.selected_at_utc,
            "proposal_origin": selection.proposal_origin,
            "research_goal": selection.research_goal,
            "source_roles": {
                item.url: {
                    "role": item.source_role,
                    "critical_candidate": item.critical_candidate,
                    "selection_rationale": item.selection_rationale,
                }
                for item in selection.selected_sources
            },
        },
    }


class EvidenceAnnotationDecisionV1(_StrictRecord):
    evidence_id: str = Field(pattern=_SAFE_ID_RE)
    support_span_ids: list[str]
    review_kind: Literal["semantic", "structured", "support"] | None = None
    support_span_correct: bool | None = None
    proposition_supported: bool | None = None
    source_scope_correct: bool | None = None
    context_sufficient: bool | None = None
    decision: Literal["pending", "keep", "revise", "drop"] = "pending"
    reviewer_note: str = ""


class ProofStepAnnotationDecisionV1(_StrictRecord):
    step_id: str = Field(pattern=_SAFE_ID_RE)
    step_type: Literal["evidence", "bridge", "decision"]
    necessary: bool | None = None
    dependencies_correct: bool | None = None
    verifier_contract_clear: bool | None = None
    deletion_test: Literal[
        "pending",
        "decision_changes",
        "becomes_unresolved",
        "not_applicable",
        "no_change",
    ] = "pending"
    decision: Literal["pending", "keep", "revise", "drop"] = "pending"
    necessity_rationale: str = ""


class GeneratorViewAnnotationDecisionV1(_StrictRecord):
    scenario_faithful: bool | None = None
    constraints_complete: bool | None = None
    candidate_actions_complete: bool | None = None
    target_requires_research: bool | None = None
    contains_no_gold_or_urls: bool | None = None
    decision: Literal["pending", "approve", "revise", "reject"] = "pending"
    reviewer_note: str = ""


def _validate_human_evidence_review_gate(
    value: Mapping[str, Any],
    *,
    candidate_id: str,
    corpus_snapshot: str,
    evidence_graph_sha256: str,
    expected_evidence_ids: set[str] | None = None,
) -> tuple[str, str]:
    """Validate and return ``(reviewer_id, reviewed_at_utc)``.

    The gate report is produced by ``import_v3_review_decisions.py`` from the
    self-contained frozen-byte review packet.  Embedding it in the annotation
    keeps the human evidence judgment, its input hashes, and the graph hash in
    the formal provenance chain.
    """

    report = dict(value)
    if report.get("schema_version") != "dra_v3_review_gate_report_v1":
        raise HumanQueryPipelineError("evidence review gate has the wrong schema")
    if report.get("status") != "eligible_for_case_generation":
        raise HumanQueryPipelineError("evidence review gate is not eligible")
    expected_identity = {
        "candidate_id": candidate_id,
        "corpus_snapshot": corpus_snapshot,
        "evidence_graph_hash": evidence_graph_sha256,
        "review_authority": "human",
    }
    mismatches = {
        key: (expected, report.get(key))
        for key, expected in expected_identity.items()
        if report.get(key) != expected
    }
    if mismatches:
        raise HumanQueryPipelineError(
            f"evidence review gate identity mismatch: {mismatches}"
        )
    stored_hash = report.get("report_sha256")
    if not isinstance(stored_hash, str) or re.fullmatch(_SHA256_RE, stored_hash) is None:
        raise HumanQueryPipelineError("evidence review gate has no valid report hash")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if artifact_sha256(unsigned) != stored_hash:
        raise HumanQueryPipelineError("evidence review gate report hash cannot replay")

    identity = report.get("review_identity")
    gate = report.get("candidate_gate")
    input_hashes = report.get("input_hashes")
    if not isinstance(identity, Mapping) or not isinstance(gate, Mapping):
        raise HumanQueryPipelineError("evidence review gate lacks human/gate records")
    if not isinstance(input_hashes, Mapping):
        raise HumanQueryPipelineError("evidence review gate lacks input hashes")
    reviewer_id = identity.get("reviewer_id")
    reviewed_at_utc = identity.get("reviewed_at_utc")
    if not isinstance(reviewer_id, str) or re.fullmatch(_SAFE_ID_RE, reviewer_id) is None:
        raise HumanQueryPipelineError("evidence review gate reviewer_id is invalid")
    if not isinstance(reviewed_at_utc, str) or re.fullmatch(
        _ISO_UTC_RE, reviewed_at_utc
    ) is None:
        raise HumanQueryPipelineError("evidence review gate timestamp is invalid")
    if identity.get("independent_review") is not True or (
        identity.get("candidate_verdict") != "eligible"
    ):
        raise HumanQueryPipelineError("evidence review was not independent and eligible")
    if gate.get("eligible_for_case_generation") is not True or gate.get(
        "blocker_codes"
    ) != []:
        raise HumanQueryPipelineError("evidence review gate still has blockers")
    for name in (
        "review_packet_manifest_sha256",
        "review_queue_canonical_sha256",
        "review_decisions_canonical_sha256",
    ):
        digest = input_hashes.get(name)
        if not isinstance(digest, str) or re.fullmatch(_SHA256_RE, digest) is None:
            raise HumanQueryPipelineError(
                f"evidence review gate input hash is invalid: {name}"
            )

    item_results = report.get("item_results")
    if not isinstance(item_results, list):
        raise HumanQueryPipelineError("evidence review gate has no item results")
    approved_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_item in item_results:
        if not isinstance(raw_item, Mapping):
            raise HumanQueryPipelineError("evidence review item result is malformed")
        evidence_id = raw_item.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id in approved_by_id:
            raise HumanQueryPipelineError(
                "evidence review item IDs must be non-empty and unique"
            )
        approved_by_id[evidence_id] = raw_item
    if expected_evidence_ids is not None:
        missing = sorted(expected_evidence_ids - set(approved_by_id))
        if missing:
            raise HumanQueryPipelineError(
                f"human evidence review does not cover case evidence: {missing}"
            )
        unresolved = sorted(
            evidence_id
            for evidence_id in expected_evidence_ids
            if approved_by_id[evidence_id].get("formal_promotion_candidate") is not True
            or approved_by_id[evidence_id].get("first_pass_approved") is not True
            or approved_by_id[evidence_id].get("review_complete") is not True
        )
        if unresolved:
            raise HumanQueryPipelineError(
                f"case evidence lacks formal human approval: {unresolved}"
            )
    return reviewer_id, reviewed_at_utc


class HumanGraphAnnotationV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_graph_annotation_v1"] = (
        GRAPH_ANNOTATION_SCHEMA
    )
    candidate_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    task_id: str = Field(pattern=_SAFE_ID_RE)
    corpus_snapshot: str = Field(min_length=1)
    case_sha256: str = Field(pattern=_SHA256_RE)
    evidence_graph_sha256: str = Field(pattern=_SHA256_RE)
    generator_view_sha256: str = Field(pattern=_SHA256_RE)
    evidence_review_gate: dict[str, Any] | None = None
    annotation_mode: Literal["independent_human_plus_adjudication"] = (
        "independent_human_plus_adjudication"
    )
    status: Literal["pending", "approved", "rejected"] = "pending"
    annotator: HumanActorV1 | None = None
    adjudicator: HumanActorV1 | None = None
    annotated_at_utc: str | None = Field(default=None, pattern=_ISO_UTC_RE)
    adjudicated_at_utc: str | None = Field(default=None, pattern=_ISO_UTC_RE)
    evidence_items: list[EvidenceAnnotationDecisionV1]
    proof_steps: list[ProofStepAnnotationDecisionV1]
    generator_view_review: GeneratorViewAnnotationDecisionV1
    annotation_note: str = ""
    adjudication_note: str = ""

    @model_validator(mode="after")
    def validate_decisions(self) -> "HumanGraphAnnotationV1":
        evidence_ids = [item.evidence_id for item in self.evidence_items]
        step_ids = [item.step_id for item in self.proof_steps]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence annotation IDs must be unique")
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("proof-step annotation IDs must be unique")
        if self.status != "approved":
            return self
        if self.evidence_review_gate is None:
            raise ValueError("approved graph annotation requires a human evidence gate")
        evidence_reviewer_id, evidence_reviewed_at = _validate_human_evidence_review_gate(
            self.evidence_review_gate,
            candidate_id=self.candidate_id,
            corpus_snapshot=self.corpus_snapshot,
            evidence_graph_sha256=self.evidence_graph_sha256,
        )
        _require_role(self.annotator, "graph_annotator", "annotator")
        _require_role(self.adjudicator, "graph_adjudicator", "adjudicator")
        assert self.annotator is not None
        assert self.adjudicator is not None
        if self.annotator.actor_id == self.adjudicator.actor_id:
            raise ValueError("graph annotator and adjudicator must be distinct humans")
        if self.annotator.actor_id != evidence_reviewer_id:
            raise ValueError("graph annotator must be the frozen-evidence reviewer")
        if self.annotated_at_utc != evidence_reviewed_at:
            raise ValueError("graph annotation timestamp must bind the evidence review")
        if not self.annotated_at_utc or not self.adjudicated_at_utc:
            raise ValueError("approved graph annotation requires both timestamps")
        if len(self.annotation_note.strip()) < 8 or len(
            self.adjudication_note.strip()
        ) < 8:
            raise ValueError(
                "approved graph annotation requires human annotation and adjudication notes"
            )
        for item in self.evidence_items:
            common_pass = (
                item.decision == "keep"
                and item.review_kind is not None
                and item.support_span_correct is True
                and item.context_sufficient is True
            )
            if item.review_kind == "semantic":
                kind_pass = (
                    item.proposition_supported is True
                    and item.source_scope_correct is True
                )
            elif item.review_kind == "structured":
                kind_pass = (
                    item.proposition_supported is None
                    and item.source_scope_correct in (True, None)
                )
            else:
                kind_pass = (
                    item.proposition_supported is not False
                    and item.source_scope_correct is not False
                )
            if not common_pass or not kind_pass:
                raise ValueError(
                    f"approved graph contains unresolved evidence {item.evidence_id!r}"
                )
        for item in self.proof_steps:
            if (
                item.decision != "keep"
                or not item.necessary
                or not item.dependencies_correct
                or not item.verifier_contract_clear
            ):
                raise ValueError(
                    f"approved graph contains unresolved proof step {item.step_id!r}"
                )
            if len(item.necessity_rationale.strip()) < 8:
                raise ValueError(
                    f"proof step {item.step_id!r} needs a human necessity rationale"
                )
            if item.step_type == "evidence" and item.deletion_test not in {
                "decision_changes",
                "becomes_unresolved",
            }:
                raise ValueError(
                    f"critical evidence {item.step_id!r} failed the deletion test"
                )
            if item.step_type != "evidence" and item.deletion_test == "pending":
                raise ValueError(
                    f"proof step {item.step_id!r} has a pending deletion decision"
                )
        review = self.generator_view_review
        if review.decision != "approve" or not all(
            (
                review.scenario_faithful,
                review.constraints_complete,
                review.candidate_actions_complete,
                review.target_requires_research,
                review.contains_no_gold_or_urls,
            )
        ):
            raise ValueError("GeneratorView has not received complete human approval")
        return self


def _case(value: CaseSpecV3 | Mapping[str, Any]) -> CaseSpecV3:
    return value if isinstance(value, CaseSpecV3) else validate_case(value)


def build_graph_annotation_template(
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    candidate_id: str,
    evidence_graph_sha256: str,
    evidence_review_gate: Mapping[str, Any] | None = None,
) -> HumanGraphAnnotationV1:
    spec = _case(case)
    if re.fullmatch(_SHA256_RE, evidence_graph_sha256) is None:
        raise HumanQueryPipelineError("evidence graph hash must be lowercase SHA-256")
    payload = spec.protocol_dict()
    expected_evidence_ids = {
        source["evidence_id"] for source in payload["evidence_sources"]
    }
    reviewer_id: str | None = None
    reviewed_at_utc: str | None = None
    review_items: dict[str, Mapping[str, Any]] = {}
    if evidence_review_gate is not None:
        reviewer_id, reviewed_at_utc = _validate_human_evidence_review_gate(
            evidence_review_gate,
            candidate_id=candidate_id,
            corpus_snapshot=spec.corpus_snapshot,
            evidence_graph_sha256=evidence_graph_sha256,
            expected_evidence_ids=expected_evidence_ids,
        )
        review_items = {
            str(item["evidence_id"]): item
            for item in evidence_review_gate["item_results"]
            if isinstance(item, Mapping)
        }
    evidence_items = []
    for source in payload["evidence_sources"]:
        item: dict[str, Any] = {
            "evidence_id": source["evidence_id"],
            "support_span_ids": sorted(
                span["support_span_id"] for span in source["support_spans"]
            ),
        }
        imported = review_items.get(source["evidence_id"])
        if imported is not None:
            checks = imported.get("checks")
            if not isinstance(checks, Mapping):
                raise HumanQueryPipelineError("evidence review checks are malformed")
            item.update(
                {
                    "support_span_correct": checks.get("support_span_correct"),
                    "proposition_supported": checks.get("proposition_supported"),
                    "source_scope_correct": checks.get("source_scope_correct"),
                    "context_sufficient": checks.get("context_sufficient"),
                    "review_kind": imported.get("review_kind"),
                    "decision": "keep",
                    "reviewer_note": "Imported from frozen-byte human review gate.",
                }
            )
        evidence_items.append(item)
    proof_steps = []
    for step in payload["evaluator_view"]["required_proof_steps"]:
        proof_steps.append(
            {
                "step_id": step["step_id"],
                "step_type": step["type"],
            }
        )
    return HumanGraphAnnotationV1(
        candidate_id=candidate_id,
        task_id=spec.task_id,
        corpus_snapshot=spec.corpus_snapshot,
        case_sha256=spec.sha256(),
        evidence_graph_sha256=evidence_graph_sha256,
        generator_view_sha256=generator_view_sha256(spec.generator_view),
        evidence_review_gate=(dict(evidence_review_gate) if evidence_review_gate else None),
        annotator=(
            HumanActorV1(
                actor_id=reviewer_id,
                role="graph_annotator",
            )
            if reviewer_id is not None
            else None
        ),
        annotated_at_utc=reviewed_at_utc,
        evidence_items=evidence_items,
        proof_steps=proof_steps,
        generator_view_review=GeneratorViewAnnotationDecisionV1(),
    )


def validate_graph_annotation_for_case(
    annotation: HumanGraphAnnotationV1 | Mapping[str, Any],
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    expected_graph_sha256: str,
    require_approved: bool = True,
) -> HumanGraphAnnotationV1:
    record = (
        annotation
        if isinstance(annotation, HumanGraphAnnotationV1)
        else HumanGraphAnnotationV1.model_validate(dict(annotation))
    )
    spec = _case(case)
    if record.task_id != spec.task_id:
        raise HumanQueryPipelineError("graph annotation targets another task")
    if record.corpus_snapshot != spec.corpus_snapshot:
        raise HumanQueryPipelineError("graph annotation snapshot does not match case")
    if record.case_sha256 != spec.sha256():
        raise HumanQueryPipelineError("graph annotation binds a different case draft")
    if record.evidence_graph_sha256 != expected_graph_sha256:
        raise HumanQueryPipelineError("graph annotation binds a different evidence graph")
    if record.generator_view_sha256 != generator_view_sha256(spec.generator_view):
        raise HumanQueryPipelineError("graph annotation binds a different GeneratorView")
    if record.evidence_review_gate is None:
        raise HumanQueryPipelineError("graph annotation has no human evidence review gate")
    formal_bindings = spec.formal_bindings
    if formal_bindings is not None and (
        formal_bindings.evidence_graph_sha256 != expected_graph_sha256
    ):
        raise HumanQueryPipelineError("formal case and graph annotation hashes disagree")

    payload = spec.protocol_dict()
    expected_evidence = {
        source["evidence_id"]: sorted(
            item["support_span_id"] for item in source["support_spans"]
        )
        for source in payload["evidence_sources"]
    }
    _validate_human_evidence_review_gate(
        record.evidence_review_gate,
        candidate_id=record.candidate_id,
        corpus_snapshot=spec.corpus_snapshot,
        evidence_graph_sha256=expected_graph_sha256,
        expected_evidence_ids=set(expected_evidence),
    )
    actual_evidence = {
        item.evidence_id: sorted(item.support_span_ids)
        for item in record.evidence_items
    }
    if actual_evidence != expected_evidence:
        raise HumanQueryPipelineError(
            "human evidence decisions do not exactly cover case evidence"
        )
    expected_steps = {
        item["step_id"]: item["type"]
        for item in payload["evaluator_view"]["required_proof_steps"]
    }
    actual_steps = {item.step_id: item.step_type for item in record.proof_steps}
    if actual_steps != expected_steps:
        raise HumanQueryPipelineError(
            "human proof decisions do not exactly cover required proof steps"
        )
    if require_approved and record.status != "approved":
        raise HumanQueryPipelineError("graph annotation is not human-approved")
    return record


class HumanFewShotExampleV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_few_shot_example_v1"] = (
        FEW_SHOT_EXAMPLE_SCHEMA
    )
    example_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    task_id: str = Field(pattern=_SAFE_ID_RE)
    case_sha256: str = Field(pattern=_SHA256_RE)
    graph_annotation_sha256: str = Field(pattern=_SHA256_RE)
    motif: str = Field(min_length=1)
    generator_view: GeneratorViewV3
    human_written_query: str = Field(min_length=1)
    author: HumanActorV1
    adjudicator: HumanActorV1
    authored_at_utc: str = Field(pattern=_ISO_UTC_RE)
    adjudicated_at_utc: str = Field(pattern=_ISO_UTC_RE)
    adjudication_note: str = Field(min_length=8)
    status: Literal["approved"] = "approved"

    @model_validator(mode="after")
    def validate_human_example(self) -> "HumanFewShotExampleV1":
        _require_role(self.author, "few_shot_query_author", "author")
        _require_role(self.adjudicator, "few_shot_adjudicator", "adjudicator")
        if self.author.actor_id == self.adjudicator.actor_id:
            raise ValueError("few-shot author and adjudicator must be distinct humans")
        SanitizedFewShotExampleV3(
            generator_view=self.generator_view,
            human_written_query=self.human_written_query,
        )
        return self


def validate_few_shot_example_for_case(
    example: HumanFewShotExampleV1 | Mapping[str, Any],
    case: CaseSpecV3 | Mapping[str, Any],
    graph_annotation: HumanGraphAnnotationV1 | Mapping[str, Any],
) -> HumanFewShotExampleV1:
    record = (
        example
        if isinstance(example, HumanFewShotExampleV1)
        else HumanFewShotExampleV1.model_validate(dict(example))
    )
    spec = _case(case)
    annotation = (
        graph_annotation
        if isinstance(graph_annotation, HumanGraphAnnotationV1)
        else HumanGraphAnnotationV1.model_validate(dict(graph_annotation))
    )
    validate_graph_annotation_for_case(
        annotation,
        spec,
        expected_graph_sha256=annotation.evidence_graph_sha256,
    )
    if record.task_id != spec.task_id or record.case_sha256 != spec.sha256():
        raise HumanQueryPipelineError("few-shot example binds a different case")
    if record.graph_annotation_sha256 != artifact_sha256(annotation):
        raise HumanQueryPipelineError(
            "few-shot example binds a different human graph annotation"
        )
    if record.generator_view != spec.generator_view:
        raise HumanQueryPipelineError("few-shot GeneratorView differs from its case")
    if record.motif != spec.motif:
        raise HumanQueryPipelineError("few-shot motif differs from its case")
    return record


class HumanFewShotDatasetV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_few_shot_dataset_v1"] = (
        FEW_SHOT_DATASET_SCHEMA
    )
    dataset_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    examples: list[HumanFewShotExampleV1] = Field(min_length=3, max_length=3)
    approved_by: HumanActorV1
    approved_at_utc: str = Field(pattern=_ISO_UTC_RE)
    status: Literal["approved"] = "approved"

    @model_validator(mode="after")
    def validate_dataset(self) -> "HumanFewShotDatasetV1":
        _require_role(self.approved_by, "few_shot_adjudicator", "approved_by")
        example_ids = [item.example_id for item in self.examples]
        task_ids = [item.task_id for item in self.examples]
        motifs = [item.motif for item in self.examples]
        if len(set(example_ids)) != 3 or len(set(task_ids)) != 3:
            raise ValueError("few-shot set requires three distinct examples and tasks")
        if len(set(motifs)) != 3:
            raise ValueError("few-shot set requires three distinct graph motifs")
        if self.approved_by.actor_id in {
            item.author.actor_id for item in self.examples
        }:
            raise ValueError("few-shot dataset approver cannot be an example author")
        validate_sanitized_few_shot_examples(
            [
                {
                    "generator_view": item.generator_view.model_dump(mode="json"),
                    "human_written_query": item.human_written_query,
                }
                for item in self.examples
            ]
        )
        return self


def build_few_shot_dataset(
    *,
    dataset_id: str,
    examples: Sequence[HumanFewShotExampleV1 | Mapping[str, Any]],
    approved_by: HumanActorV1 | Mapping[str, Any],
    approved_at_utc: str,
) -> HumanFewShotDatasetV1:
    actor = (
        approved_by
        if isinstance(approved_by, HumanActorV1)
        else HumanActorV1.model_validate(dict(approved_by))
    )
    records = [
        item
        if isinstance(item, HumanFewShotExampleV1)
        else HumanFewShotExampleV1.model_validate(dict(item))
        for item in examples
    ]
    return HumanFewShotDatasetV1(
        dataset_id=dataset_id,
        examples=records,
        approved_by=actor,
        approved_at_utc=approved_at_utc,
    )


def sanitized_few_shot_examples(
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
) -> list[dict[str, Any]]:
    record = (
        dataset
        if isinstance(dataset, HumanFewShotDatasetV1)
        else HumanFewShotDatasetV1.model_validate(dict(dataset))
    )
    return [
        {
            "generator_view": item.generator_view.model_dump(mode="json"),
            "human_written_query": item.human_written_query,
        }
        for item in record.examples
    ]


class QueryRendererModelConfigV1(_StrictRecord):
    schema_version: Literal["dra_v3_query_renderer_config_v1"] = (
        RENDERER_CONFIG_SCHEMA
    )
    provider: Literal["openai_compatible"] = "openai_compatible"
    renderer_id: str = Field(pattern=_SAFE_LOWER_ID_RE)
    base_url: str
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1, max_length=200)
    api_key_env: str = Field(pattern=_ENV_RE)
    temperature: float = 0.0
    max_tokens: int = Field(ge=128, le=8192)
    seed: int = Field(ge=0)
    timeout_seconds: float = Field(gt=0, le=600)
    invocation_mode: Literal["registered_api_renderer"] = RENDERER_INVOCATION_MODE

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _absolute_http_url(value, "base_url")

    @field_validator("model")
    @classmethod
    def reject_interactive_codex(cls, value: str) -> str:
        if "codex" in value.casefold():
            raise ValueError("interactive Codex models are not formal query renderers")
        return value

    @field_validator("model_revision")
    @classmethod
    def require_pinned_model_revision(cls, value: str) -> str:
        if value != value.strip() or "\n" in value or "\r" in value:
            raise ValueError("model_revision must be trimmed and single-line")
        if value.casefold() in {"latest", "default", "unknown", "unversioned"}:
            raise ValueError("formal renderer requires a pinned model revision")
        return value

    @model_validator(mode="after")
    def validate_deterministic_settings(self) -> "QueryRendererModelConfigV1":
        if self.temperature != 0.0:
            raise ValueError("formal query renderer temperature must be 0.0")
        return self


QUERY_RENDERER_SYSTEM_PROMPT = (
    "You are the registered DRA query renderer. Use only the supplied "
    "GeneratorView and the three sanitized human examples. Write one natural "
    "research query that preserves every scenario constraint, candidate action, "
    "and target. Add no facts, answers, URLs, proof-step language, scoring terms, "
    "or numeric research quotas. Return only the query text, with no JSON, label, "
    "commentary, or markdown fence."
)


def build_registered_query_prompt(
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
) -> dict[str, Any]:
    spec = _case(case)
    return build_query_generation_prompt(
        spec,
        sanitized_few_shot_examples(dataset),
    )


def build_registered_query_messages(
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
) -> list[dict[str, str]]:
    prompt = build_registered_query_prompt(case, dataset)
    return [
        {"role": "system", "content": QUERY_RENDERER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": canonical_json_bytes(prompt).decode("utf-8"),
        },
    ]


class QueryGenerationRecordV1(_StrictRecord):
    schema_version: Literal["dra_v3_query_generation_record_v1"] = (
        GENERATION_RECORD_SCHEMA
    )
    task_id: str = Field(pattern=_SAFE_ID_RE)
    attempt: int = Field(ge=1, le=QUERY_MAX_GENERATION_ATTEMPTS)
    generated_at_utc: str = Field(pattern=_ISO_UTC_RE)
    generator_view_sha256: str = Field(pattern=_SHA256_RE)
    few_shot_dataset_sha256: str = Field(pattern=_SHA256_RE)
    prompt_sha256: str = Field(pattern=_SHA256_RE)
    messages_sha256: str = Field(pattern=_SHA256_RE)
    request_sha256: str = Field(pattern=_SHA256_RE)
    raw_response_sha256: str = Field(pattern=_SHA256_RE)
    raw_response_base64: str = Field(min_length=1)
    renderer: QueryRendererModelConfigV1
    query: str = Field(min_length=1)
    query_sha256: str = Field(pattern=_SHA256_RE)
    hard_rules: HardRulePassRecordV3
    status: Literal["hard_rules_passed", "retry_required", "discarded"]

    @model_validator(mode="after")
    def validate_generation_record(self) -> "QueryGenerationRecordV1":
        try:
            raw_response = base64.b64decode(
                self.raw_response_base64.encode("ascii"), validate=True
            )
        except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
            raise ValueError("raw_response_base64 is invalid") from exc
        if hashlib.sha256(raw_response).hexdigest() != self.raw_response_sha256:
            raise ValueError("raw response hash does not bind stored response bytes")
        try:
            response_payload = json.loads(raw_response)
            response_query = response_payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ValueError("stored raw response is not a chat completion") from exc
        if not isinstance(response_query, str) or _normalize_model_query(
            response_query
        ) != self.query:
            raise ValueError("stored raw response does not contain the released query")
        if self.query != self.query.strip():
            raise ValueError("generated query must be trimmed")
        if self.query_sha256 != query_sha256(self.query):
            raise ValueError("query_sha256 does not bind generated query")
        if self.hard_rules.task_id != self.task_id:
            raise ValueError("hard-rule task_id differs from generation record")
        if self.hard_rules.attempt != self.attempt:
            raise ValueError("hard-rule attempt differs from generation record")
        if self.hard_rules.generator_view_sha256 != self.generator_view_sha256:
            raise ValueError("hard rules bind another GeneratorView")
        if self.hard_rules.query_sha256 != self.query_sha256:
            raise ValueError("hard rules bind another query")
        expected = (
            "hard_rules_passed"
            if self.hard_rules.passed
            else (
                "discarded"
                if self.attempt == QUERY_MAX_GENERATION_ATTEMPTS
                else "retry_required"
            )
        )
        if self.status != expected:
            raise ValueError("generation status disagrees with hard-rule result")
        return self


def _request_body(
    config: QueryRendererModelConfigV1,
    messages: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    return {
        "model": config.model,
        "messages": [dict(message) for message in messages],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "seed": config.seed,
        "stream": False,
    }


def _normalize_model_query(value: str) -> str:
    query = value.strip()
    if not query:
        raise HumanQueryPipelineError("renderer returned an empty query")
    if "```" in query:
        raise HumanQueryPipelineError("renderer returned a markdown fence")
    return query


def build_query_generation_record(
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    config: QueryRendererModelConfigV1 | Mapping[str, Any],
    *,
    attempt: int,
    generated_at_utc: str,
    assistant_text: str,
    raw_response_bytes: bytes,
) -> QueryGenerationRecordV1:
    spec = _case(case)
    few_shots = (
        dataset
        if isinstance(dataset, HumanFewShotDatasetV1)
        else HumanFewShotDatasetV1.model_validate(dict(dataset))
    )
    renderer = (
        config
        if isinstance(config, QueryRendererModelConfigV1)
        else QueryRendererModelConfigV1.model_validate(dict(config))
    )
    prompt = build_registered_query_prompt(spec, few_shots)
    messages = build_registered_query_messages(spec, few_shots)
    request = _request_body(renderer, messages)
    query = _normalize_model_query(assistant_text)
    hard = build_hard_rule_pass_record(spec, query, attempt=attempt)
    status: Literal["hard_rules_passed", "retry_required", "discarded"] = (
        "hard_rules_passed"
        if hard.passed
        else (
            "discarded"
            if attempt == QUERY_MAX_GENERATION_ATTEMPTS
            else "retry_required"
        )
    )
    return QueryGenerationRecordV1(
        task_id=spec.task_id,
        attempt=attempt,
        generated_at_utc=generated_at_utc,
        generator_view_sha256=generator_view_sha256(spec.generator_view),
        few_shot_dataset_sha256=artifact_sha256(few_shots),
        prompt_sha256=artifact_sha256(prompt),
        messages_sha256=artifact_sha256(messages),
        request_sha256=artifact_sha256(request),
        raw_response_sha256=hashlib.sha256(raw_response_bytes).hexdigest(),
        raw_response_base64=base64.b64encode(raw_response_bytes).decode("ascii"),
        renderer=renderer,
        query=query,
        query_sha256=query_sha256(query),
        hard_rules=hard,
        status=status,
    )


def validate_query_generation_record(
    record: QueryGenerationRecordV1 | Mapping[str, Any],
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    *,
    require_hard_rule_pass: bool = True,
) -> QueryGenerationRecordV1:
    generation = (
        record
        if isinstance(record, QueryGenerationRecordV1)
        else QueryGenerationRecordV1.model_validate(dict(record))
    )
    spec = _case(case)
    few_shots = (
        dataset
        if isinstance(dataset, HumanFewShotDatasetV1)
        else HumanFewShotDatasetV1.model_validate(dict(dataset))
    )
    prompt = build_registered_query_prompt(spec, few_shots)
    messages = build_registered_query_messages(spec, few_shots)
    request = _request_body(generation.renderer, messages)
    expected = {
        "task_id": spec.task_id,
        "generator_view_sha256": generator_view_sha256(spec.generator_view),
        "few_shot_dataset_sha256": artifact_sha256(few_shots),
        "prompt_sha256": artifact_sha256(prompt),
        "messages_sha256": artifact_sha256(messages),
        "request_sha256": artifact_sha256(request),
    }
    actual = {key: getattr(generation, key) for key in expected}
    if actual != expected:
        raise HumanQueryPipelineError(
            f"query generation provenance mismatch: expected={expected}, actual={actual}"
        )
    rebuilt = build_hard_rule_pass_record(
        spec, generation.query, attempt=generation.attempt
    )
    if rebuilt.model_dump(mode="json") != generation.hard_rules.model_dump(mode="json"):
        raise HumanQueryPipelineError("stored hard-rule record cannot be replayed")
    if require_hard_rule_pass and generation.status != "hard_rules_passed":
        raise HumanQueryPipelineError(
            f"generated query is not publishable: status={generation.status}"
        )
    return generation


def call_registered_query_renderer(
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    config: QueryRendererModelConfigV1 | Mapping[str, Any],
) -> tuple[str, bytes]:
    renderer = (
        config
        if isinstance(config, QueryRendererModelConfigV1)
        else QueryRendererModelConfigV1.model_validate(dict(config))
    )
    api_key = os.environ.get(renderer.api_key_env)
    if api_key is None:
        raise HumanQueryPipelineError(
            f"required API-key environment variable is unset: {renderer.api_key_env}"
        )
    messages = build_registered_query_messages(case, dataset)
    body = canonical_json_bytes(_request_body(renderer, messages))
    request = urllib.request.Request(
        renderer.base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=renderer.timeout_seconds
        ) as response:
            raw = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise HumanQueryPipelineError(f"registered renderer request failed: {exc}") from exc
    try:
        payload = json.loads(raw)
        content = payload["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise HumanQueryPipelineError(
            "registered renderer returned an invalid chat-completion response"
        ) from exc
    if not isinstance(content, str):
        raise HumanQueryPipelineError("registered renderer content is not text")
    return _normalize_model_query(content), raw


class HumanBlindQueryReviewV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_blind_query_review_v1"] = (
        HUMAN_BLIND_REVIEW_SCHEMA
    )
    reviewer: HumanActorV1
    reviewed_at_utc: str = Field(pattern=_ISO_UTC_RE)
    packet_sha256: str = Field(pattern=_SHA256_RE)
    attestation: Literal["reviewed_only_generator_view_and_query"] = (
        BLIND_REVIEW_ATTESTATION
    )
    review: BlindSemanticReviewRecordV3

    @model_validator(mode="after")
    def validate_reviewer(self) -> "HumanBlindQueryReviewV1":
        _require_role(self.reviewer, "blind_query_reviewer", "reviewer")
        if self.review.reviewer_id != self.reviewer.actor_id:
            raise ValueError("blind review reviewer_id differs from human actor")
        return self


def build_human_blind_review_template(
    case: CaseSpecV3 | Mapping[str, Any],
    generation: QueryGenerationRecordV1 | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = _case(case)
    record = (
        generation
        if isinstance(generation, QueryGenerationRecordV1)
        else QueryGenerationRecordV1.model_validate(dict(generation))
    )
    packet = build_blind_review_packet(
        spec,
        attempt=record.attempt,
        query_text=record.query,
    )
    template = {
        "schema_version": HUMAN_BLIND_REVIEW_SCHEMA,
        "reviewer": {
            "actor_type": "human",
            "actor_id": "",
            "role": "blind_query_reviewer",
            "attestation": HUMAN_ATTESTATION,
        },
        "reviewed_at_utc": "",
        "packet_sha256": artifact_sha256(packet),
        "attestation": BLIND_REVIEW_ATTESTATION,
        "review": {
            "schema": "blind_semantic_alignment_review_v1",
            "task_id": spec.task_id,
            "attempt": record.attempt,
            "max_generation_attempts": QUERY_MAX_GENERATION_ATTEMPTS,
            "generator_view_sha256": packet["generator_view_sha256"],
            "query_sha256": packet["query_sha256"],
            "reviewer_id": "",
            "faithful": None,
            "natural": None,
            "closed_environment_answerable": None,
            "requires_multi_branch_research": None,
            "passed": None,
        },
    }
    return packet, template


def validate_human_blind_query_review(
    value: HumanBlindQueryReviewV1 | Mapping[str, Any],
    case: CaseSpecV3 | Mapping[str, Any],
    generation: QueryGenerationRecordV1 | Mapping[str, Any],
    *,
    require_pass: bool = True,
) -> HumanBlindQueryReviewV1:
    record = (
        value
        if isinstance(value, HumanBlindQueryReviewV1)
        else HumanBlindQueryReviewV1.model_validate(dict(value))
    )
    spec = _case(case)
    generated = (
        generation
        if isinstance(generation, QueryGenerationRecordV1)
        else QueryGenerationRecordV1.model_validate(dict(generation))
    )
    packet = build_blind_review_packet(
        spec,
        attempt=generated.attempt,
        query_text=generated.query,
    )
    if record.packet_sha256 != artifact_sha256(packet):
        raise HumanQueryPipelineError("human blind review binds another packet")
    validate_blind_semantic_review(spec, generated.query, record.review)
    acceptance = build_query_acceptance_record(
        spec, generated.query, record.review
    )
    if require_pass:
        assert_query_accepted(acceptance)
    return record


class QueryAttemptClosureV1(_StrictRecord):
    """One immutable attempt, closed by hard rules or a human blind review."""

    schema_version: Literal["dra_v3_query_attempt_closure_v1"] = (
        ATTEMPT_CLOSURE_SCHEMA
    )
    generation: QueryGenerationRecordV1
    blind_review: HumanBlindQueryReviewV1 | None = None
    disposition: Literal["accepted", "retry_required", "discarded"]

    @model_validator(mode="after")
    def validate_closure(self) -> "QueryAttemptClosureV1":
        generation = self.generation
        if generation.hard_rules.passed:
            if self.blind_review is None:
                raise ValueError("a hard-rule-passing attempt requires blind review")
            review = self.blind_review.review
            if (
                review.task_id != generation.task_id
                or review.attempt != generation.attempt
                or review.generator_view_sha256 != generation.generator_view_sha256
                or review.query_sha256 != generation.query_sha256
            ):
                raise ValueError("attempt blind review binds another generation")
            passed = review.passed
        else:
            if self.blind_review is not None:
                raise ValueError("a hard-rule-failing attempt must not enter blind review")
            passed = False
        expected: Literal["accepted", "retry_required", "discarded"] = (
            "accepted"
            if passed
            else (
                "discarded"
                if generation.attempt == QUERY_MAX_GENERATION_ATTEMPTS
                else "retry_required"
            )
        )
        if self.disposition != expected:
            raise ValueError("attempt disposition disagrees with its closed checks")
        return self


def build_query_attempt_closure(
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    generation: QueryGenerationRecordV1 | Mapping[str, Any],
    *,
    blind_review: HumanBlindQueryReviewV1 | Mapping[str, Any] | None = None,
) -> QueryAttemptClosureV1:
    spec = _case(case)
    generated = validate_query_generation_record(
        generation,
        spec,
        dataset,
        require_hard_rule_pass=False,
    )
    review: HumanBlindQueryReviewV1 | None = None
    if generated.hard_rules.passed:
        if blind_review is None:
            raise HumanQueryPipelineError(
                "hard-rule-passing generation needs a completed blind review"
            )
        review = validate_human_blind_query_review(
            blind_review,
            spec,
            generated,
            require_pass=False,
        )
        passed = review.review.passed
    else:
        if blind_review is not None:
            raise HumanQueryPipelineError(
                "hard-rule-failing generation cannot receive blind review"
            )
        passed = False
    disposition: Literal["accepted", "retry_required", "discarded"] = (
        "accepted"
        if passed
        else (
            "discarded"
            if generated.attempt == QUERY_MAX_GENERATION_ATTEMPTS
            else "retry_required"
        )
    )
    return QueryAttemptClosureV1(
        generation=generated,
        blind_review=review,
        disposition=disposition,
    )


def validate_query_attempt_history(
    values: Sequence[QueryAttemptClosureV1 | Mapping[str, Any]],
    case: CaseSpecV3 | Mapping[str, Any],
    dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    *,
    require_final_accepted: bool,
) -> list[QueryAttemptClosureV1]:
    if not 1 <= len(values) <= QUERY_MAX_GENERATION_ATTEMPTS:
        raise HumanQueryPipelineError("attempt history must contain one to three rows")
    spec = _case(case)
    records: list[QueryAttemptClosureV1] = []
    for value in values:
        record = (
            value
            if isinstance(value, QueryAttemptClosureV1)
            else QueryAttemptClosureV1.model_validate(dict(value))
        )
        replayed = build_query_attempt_closure(
            spec,
            dataset,
            record.generation,
            blind_review=record.blind_review,
        )
        if replayed.model_dump(mode="json") != record.model_dump(mode="json"):
            raise HumanQueryPipelineError("query attempt closure cannot be replayed")
        records.append(record)
    attempts = [item.generation.attempt for item in records]
    if attempts != list(range(1, len(records) + 1)):
        raise HumanQueryPipelineError(
            f"attempt history must be contiguous from 1; found={attempts}"
        )
    if any(item.disposition != "retry_required" for item in records[:-1]):
        raise HumanQueryPipelineError("only a failed retryable attempt may be followed")
    timestamps = [
        datetime.fromisoformat(
            item.generation.generated_at_utc.replace("Z", "+00:00")
        )
        for item in records
    ]
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise HumanQueryPipelineError(
            "attempt generation timestamps must be unique and chronological"
        )
    renderer_hashes = [artifact_sha256(item.generation.renderer) for item in records]
    if len(set(renderer_hashes)) != 1:
        raise HumanQueryPipelineError("renderer config cannot change across retries")
    if require_final_accepted and records[-1].disposition != "accepted":
        raise HumanQueryPipelineError("final query attempt is not human-accepted")
    return records


class HumanQueryReleaseV1(_StrictRecord):
    schema_version: Literal["dra_v3_human_query_release_v1"] = (
        QUERY_RELEASE_SCHEMA
    )
    task_id: str = Field(pattern=_SAFE_ID_RE)
    case_sha256: str = Field(pattern=_SHA256_RE)
    evidence_graph_sha256: str = Field(pattern=_SHA256_RE)
    graph_annotation_sha256: str = Field(pattern=_SHA256_RE)
    few_shot_dataset_sha256: str = Field(pattern=_SHA256_RE)
    attempt_history_sha256: str = Field(pattern=_SHA256_RE)
    query: str = Field(min_length=1)
    query_sha256: str = Field(pattern=_SHA256_RE)
    graph_annotation: HumanGraphAnnotationV1
    few_shot_dataset: HumanFewShotDatasetV1
    attempts: list[QueryAttemptClosureV1] = Field(
        min_length=1,
        max_length=QUERY_MAX_GENERATION_ATTEMPTS,
    )
    query_acceptance: QueryAcceptanceRecordV3
    status: Literal["approved_for_formal_compile"] = "approved_for_formal_compile"

    @model_validator(mode="after")
    def validate_internal_hashes(self) -> "HumanQueryReleaseV1":
        final = self.attempts[-1]
        if self.query != final.generation.query:
            raise ValueError("release query differs from generation record")
        if self.query_sha256 != query_sha256(self.query):
            raise ValueError("release query hash mismatch")
        if self.graph_annotation_sha256 != artifact_sha256(self.graph_annotation):
            raise ValueError("release graph-annotation hash mismatch")
        if self.few_shot_dataset_sha256 != artifact_sha256(self.few_shot_dataset):
            raise ValueError("release few-shot hash mismatch")
        if self.attempt_history_sha256 != artifact_sha256(self.attempts):
            raise ValueError("release attempt-history hash mismatch")
        if final.blind_review is None or final.disposition != "accepted":
            raise ValueError("release final attempt is not accepted")
        return self

    @property
    def generation(self) -> QueryGenerationRecordV1:
        return self.attempts[-1].generation

    @property
    def blind_review(self) -> HumanBlindQueryReviewV1:
        review = self.attempts[-1].blind_review
        if review is None:  # pragma: no cover - protected by validation
            raise HumanQueryPipelineError("release has no final blind review")
        return review


def build_human_query_release(
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    expected_graph_sha256: str,
    graph_annotation: HumanGraphAnnotationV1 | Mapping[str, Any],
    few_shot_dataset: HumanFewShotDatasetV1 | Mapping[str, Any],
    attempts: Sequence[QueryAttemptClosureV1 | Mapping[str, Any]],
) -> HumanQueryReleaseV1:
    spec = _case(case)
    annotation = validate_graph_annotation_for_case(
        graph_annotation,
        spec,
        expected_graph_sha256=expected_graph_sha256,
    )
    dataset = (
        few_shot_dataset
        if isinstance(few_shot_dataset, HumanFewShotDatasetV1)
        else HumanFewShotDatasetV1.model_validate(dict(few_shot_dataset))
    )
    history = validate_query_attempt_history(
        attempts,
        spec,
        dataset,
        require_final_accepted=True,
    )
    generated = history[-1].generation
    review = history[-1].blind_review
    assert review is not None
    assert annotation.annotator is not None
    assert annotation.adjudicator is not None
    if review.reviewer.actor_id in {
        annotation.annotator.actor_id,
        annotation.adjudicator.actor_id,
    }:
        raise HumanQueryPipelineError(
            "blind query reviewer must not have seen the target graph gold"
        )
    acceptance = build_query_acceptance_record(
        spec, generated.query, review.review
    )
    assert_query_accepted(acceptance)
    return HumanQueryReleaseV1(
        task_id=spec.task_id,
        case_sha256=spec.sha256(),
        evidence_graph_sha256=expected_graph_sha256,
        graph_annotation_sha256=artifact_sha256(annotation),
        few_shot_dataset_sha256=artifact_sha256(dataset),
        attempt_history_sha256=artifact_sha256(history),
        query=generated.query,
        query_sha256=generated.query_sha256,
        graph_annotation=annotation,
        few_shot_dataset=dataset,
        attempts=history,
        query_acceptance=acceptance,
    )


def validate_human_query_release(
    value: HumanQueryReleaseV1 | Mapping[str, Any],
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    expected_graph_sha256: str | None = None,
) -> HumanQueryReleaseV1:
    record = (
        value
        if isinstance(value, HumanQueryReleaseV1)
        else HumanQueryReleaseV1.model_validate(dict(value))
    )
    spec = _case(case)
    graph_hash = expected_graph_sha256 or record.evidence_graph_sha256
    if record.task_id != spec.task_id or record.case_sha256 != spec.sha256():
        raise HumanQueryPipelineError("query release binds a different case draft")
    if record.evidence_graph_sha256 != graph_hash:
        raise HumanQueryPipelineError("query release binds a different evidence graph")
    annotation = validate_graph_annotation_for_case(
        record.graph_annotation,
        spec,
        expected_graph_sha256=graph_hash,
    )
    history = validate_query_attempt_history(
        record.attempts,
        spec,
        record.few_shot_dataset,
        require_final_accepted=True,
    )
    generation = history[-1].generation
    review_from_history = history[-1].blind_review
    assert review_from_history is not None
    review = validate_human_blind_query_review(
        review_from_history,
        spec,
        generation,
    )
    assert annotation.annotator is not None
    assert annotation.adjudicator is not None
    if review.reviewer.actor_id in {
        annotation.annotator.actor_id,
        annotation.adjudicator.actor_id,
    }:
        raise HumanQueryPipelineError(
            "blind query reviewer must be independent of target graph annotation"
        )
    acceptance = build_query_acceptance_record(
        spec, generation.query, review.review
    )
    assert_query_accepted(acceptance)
    if acceptance.model_dump(mode="json") != record.query_acceptance.model_dump(
        mode="json"
    ):
        raise HumanQueryPipelineError("query acceptance record cannot be replayed")
    return record


__all__ = [
    "ATTEMPT_CLOSURE_SCHEMA",
    "BLIND_REVIEW_ATTESTATION",
    "FEW_SHOT_DATASET_SCHEMA",
    "FEW_SHOT_EXAMPLE_SCHEMA",
    "GENERATION_RECORD_SCHEMA",
    "GRAPH_ANNOTATION_SCHEMA",
    "HUMAN_ATTESTATION",
    "HUMAN_BLIND_REVIEW_SCHEMA",
    "QUERY_RELEASE_SCHEMA",
    "RENDERER_CONFIG_SCHEMA",
    "SOURCE_SELECTION_SCHEMA",
    "EvidenceAnnotationDecisionV1",
    "GeneratorViewAnnotationDecisionV1",
    "HumanActorV1",
    "HumanBlindQueryReviewV1",
    "HumanFewShotDatasetV1",
    "HumanFewShotExampleV1",
    "HumanGraphAnnotationV1",
    "HumanQueryPipelineError",
    "HumanQueryReleaseV1",
    "HumanSourceSelectionV1",
    "ProofStepAnnotationDecisionV1",
    "QueryAttemptClosureV1",
    "QueryGenerationRecordV1",
    "QueryRendererModelConfigV1",
    "SelectedSourceV1",
    "SourceRequirementV1",
    "SourceSearchSelectionV1",
    "artifact_sha256",
    "build_few_shot_dataset",
    "build_graph_annotation_template",
    "build_human_blind_review_template",
    "build_human_query_release",
    "build_query_attempt_closure",
    "build_query_generation_record",
    "build_registered_query_messages",
    "build_registered_query_prompt",
    "call_registered_query_renderer",
    "canonical_json_bytes",
    "capture_plan_from_human_selection",
    "sanitized_few_shot_examples",
    "validate_few_shot_example_for_case",
    "validate_graph_annotation_for_case",
    "validate_human_blind_query_review",
    "validate_human_query_release",
    "validate_query_generation_record",
    "validate_query_attempt_history",
]
