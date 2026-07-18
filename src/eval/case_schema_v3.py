"""Strict schema and structural validation for DRA evidence-graph cases.

The v3 case is the private, canonical source for both the public query and the
deterministic gold.  This module deliberately does not fetch pages, infer
claims, or repair drafts.  A case either carries a complete proof DAG and
auditable frozen-evidence bindings, or validation fails closed.

Formal compilation has one additional requirement implemented by
``scripts/compile_case_v3.py``: every evidence binding must match an external
frozen evidence catalog.  The self-contained checks here are useful while a
human is drafting a case, but are not by themselves a publication stamp.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Any, Iterable, Literal, Mapping, Sequence
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


TASK_VERSION = 3
CASE_SCHEMA = "evidence_graph_case_v1"
EVIDENCE_GRAPH_VERSION = "evidence_graph_v1"
OBSERVATION_SEMANTICS = "observation_ledger_v1"
SCORING_SEMANTICS = "verified_slots_v1"
PROOF_STEP_SCORING_SEMANTICS = "proof_steps_v1"
VERIFIED_RESEARCH_COMPLETION_METRIC = "verified_research_completion_v1"
TASK_SOLVE_RATE_METRIC = "task_solve_rate_v1"
HEADLINE_METRICS = (
    VERIFIED_RESEARCH_COMPLETION_METRIC,
    TASK_SOLVE_RATE_METRIC,
)
DIAGNOSTIC_METRIC = "verified_f1_v1"
PARTIAL_COMPLETION_RATE_METRIC = "partial_completion_rate_v1"
FULL_PASS_RATE_METRIC = "full_pass_rate_v1"
PROOF_STEP_HEADLINE_METRICS = (
    PARTIAL_COMPLETION_RATE_METRIC,
    FULL_PASS_RATE_METRIC,
)
PROOF_STEP_DIAGNOSTIC_METRICS = (
    "route_coverage_v1",
    "acquisition_diagnostics_v1",
)

SUPPORTED_MOTIFS = {
    "constraint_match_and_select",
    "claim_verification",
    "evidence_reconciliation",
    "causal_or_evolution_explanation",
    "multi_branch_synthesis",
}
LEGACY_SUPPORTED_MOTIFS = {
    "constraint_filter",
    "mechanism_application",
    "claim_reconciliation",
    "comparative_tradeoff",
    "counterexample_revision",
}
SUPPORTED_SLOT_TYPES = {"evidence", "bridge", "decision"}
SOURCE_ROLE_FAMILIES = {
    "shopping": "product",
    "magento": "product",
    "structured_db": "product",
    "concept": "mechanism",
    "wikipedia": "mechanism",
    "curated": "mechanism",
    "forum": "community",
    "postmill": "community",
    "case_spec": "decision",
    "search_result": "discovery",
}
REQUIRED_FORBIDDEN_LEAK_CLASSES = {
    "step_id",
    "source_url",
    "gold_answer",
    "required_step_count",
}
REQUIRED_QUERY_VALIDATIONS = ("hard_rules", "blind_semantic_alignment")
QUERY_MAX_GENERATION_ATTEMPTS = 3

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TASK_ID_RE = re.compile(r"^dra_v3_[a-z0-9][a-z0-9_-]*_[0-9]{4,}$")


class CaseValidationError(ValueError):
    """Raised by helper APIs when a case or catalog binding is invalid."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _require_unique(values: Sequence[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{label} must be unique; duplicates: {duplicates}")


def _canonical_sha256(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def source_role_family(source_type: str) -> str:
    """Return the canonical evidence role used by cross-source gates."""

    try:
        return SOURCE_ROLE_FAMILIES[source_type]
    except KeyError as exc:
        raise ValueError(f"unsupported evidence source_type: {source_type!r}") from exc


def _validate_absolute_http_url(value: str) -> str:
    if not value or value.strip() != value or any(ch.isspace() for ch in value):
        raise ValueError("source_url must be a non-empty URL without whitespace")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("source_url must not contain credentials")
    if parsed.fragment:
        raise ValueError("source_url must not contain a fragment")
    return value


class DifficultyV3(_StrictModel):
    proof_depth: int = Field(ge=2)
    branching_factor: int = Field(ge=1)
    distractor_density: float = Field(ge=0.0, le=1.0)
    contradiction_count: int = Field(ge=0)


class ScenarioV3(_StrictModel):
    """Only public information from this object may enter the rendered query."""

    constraints: list[str] = Field(min_length=1)
    priority_order: list[str] = Field(min_length=1)
    candidate_actions: list[str] = Field(min_length=2)
    context: str | None = None
    objective: str | None = None
    constraint_labels: dict[str, str] = Field(default_factory=dict)
    priority_labels: dict[str, str] = Field(default_factory=dict)
    candidate_labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("constraints", "priority_order", "candidate_actions")
    @classmethod
    def validate_public_ids(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("scenario identifiers must be non-empty strings")
        _require_unique(values, "scenario identifiers")
        return values

    @model_validator(mode="after")
    def validate_label_keys(self) -> "ScenarioV3":
        allowed = {
            "constraint_labels": set(self.constraints),
            "priority_labels": set(self.priority_order),
            "candidate_labels": set(self.candidate_actions),
        }
        for field_name, keys in allowed.items():
            labels = getattr(self, field_name)
            unknown = sorted(set(labels) - keys)
            if unknown:
                raise ValueError(f"{field_name} contains unknown identifiers: {unknown}")
            if any(not value.strip() for value in labels.values()):
                raise ValueError(f"{field_name} values must be non-empty")
        return self


class GeneratorViewV3(_StrictModel):
    """The complete and only case-specific input allowed into query generation.

    This projection deliberately has no labels, URLs, propositions, proof steps,
    answer conditions, or evaluator instructions.  Human-readable wording belongs
    in ``scenario`` and ``target``; constraints and options remain stable public
    identifiers so exact coverage can be checked after rendering.
    """

    scenario: str = Field(min_length=1)
    constraints: list[str] = Field(min_length=1)
    candidate_actions: list[str] = Field(min_length=2)
    target: str = Field(min_length=1)

    @field_validator("scenario", "target")
    @classmethod
    def validate_public_text(cls, value: str) -> str:
        if value.strip() != value or not value.strip():
            raise ValueError("GeneratorView text must be non-empty and trimmed")
        if re.search(r"(?i)\b(?:https?|ftp)://", value):
            raise ValueError("GeneratorView must not contain URLs")
        if re.search(
            r"(?i)\b(?:step[_ -]?id|required[_ -]?proof[_ -]?steps?|"
            r"source[_ -]?url|gold[_ -]?answer|required[_ -]?step[_ -]?count|"
            r"acceptable[_ -]?conclusions?|formal[_ -]?bindings|oracle)\b",
            value,
        ):
            raise ValueError("GeneratorView contains evaluator/scorer vocabulary")
        return value

    @field_validator("constraints", "candidate_actions")
    @classmethod
    def validate_public_identifiers(cls, values: list[str]) -> list[str]:
        if any(
            not isinstance(value, str)
            or not value.strip()
            or value.strip() != value
            or "\n" in value
            or "\r" in value
            for value in values
        ):
            raise ValueError("GeneratorView identifiers must be non-empty single lines")
        if any(re.search(r"(?i)\b(?:https?|ftp)://", value) for value in values):
            raise ValueError("GeneratorView must not contain URLs")
        _require_unique(values, "GeneratorView identifiers")
        return values


class FinalAnswerContractV3(_StrictModel):
    unique_product_required: bool
    must_address_constraints: Literal[True]
    must_explain_tradeoffs: Literal[True]
    must_depend_on_verified_steps: Literal[True]


class AcceptableSupportV3(_StrictModel):
    source_ids: list[str] = Field(min_length=1)
    source_roles: list[str] = Field(min_length=1)
    support_relation: Literal[
        "SELF",
        "ASSERTS",
        "SUPPORTED_BY",
        "REFUTES",
    ] = "SELF"
    support_mode: Literal["body", "exact_snippet", "body_or_exact_snippet"]
    condition_match: Literal[True]

    @field_validator("source_ids", "source_roles")
    @classmethod
    def validate_support_identifiers(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("acceptable-support identifiers must be non-empty")
        _require_unique(values, "acceptable-support identifiers")
        return values


class EvidenceVerifierV3(_StrictModel):
    kind: str = Field(min_length=1)
    # ``subject``/``predicate``/``object`` live on EvidenceSourceV3 and form the
    # default exact typed claim.  These optional fields make accepted natural
    # language and numeric variants explicit rather than hiding them in code.
    matcher: Literal[
        "typed_exact",
        "exact",
        "casefold_exact",
        "normalized_text",
        "regex_fullmatch",
        "numeric_tolerance",
        "numeric",
    ] | None = None
    accepted_aliases: list[str] | None = None
    accepted_phrases: list[str] | None = None
    accepted_regexes: list[str] | None = None
    accepted_regex: str | None = None
    regex: str | None = None
    patterns: list[str] | None = None
    normalizers: list[
        Literal["casefold", "whitespace", "punctuation", "hyphen"]
    ] | None = None
    tolerance: float | int | None = None
    absolute_tolerance: float | int | None = None
    relative_tolerance: float | int | None = None
    expected: str | int | float | bool | None = None
    value: str | int | float | bool | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def validate_matcher(self) -> "EvidenceVerifierV3":
        for field_name in (
            "accepted_aliases",
            "accepted_phrases",
            "accepted_regexes",
            "patterns",
            "normalizers",
        ):
            values = getattr(self, field_name)
            if values is not None:
                if not values:
                    raise ValueError(f"verifier {field_name} cannot be empty when declared")
                _require_unique(values, f"verifier {field_name}")
        regex_values = [
            *(self.patterns or []),
            *(self.accepted_regexes or []),
            *([self.accepted_regex] if self.accepted_regex else []),
            *([self.regex] if self.regex else []),
        ]
        for pattern in regex_values:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid deterministic verifier regex: {pattern!r}") from exc
        if self.matcher is None:
            raise ValueError("evidence verifier requires an explicit positive matcher")
        if self.matcher == "regex_fullmatch" and not any(
            (self.patterns, self.accepted_regexes, self.accepted_regex, self.regex)
        ):
            raise ValueError("regex_fullmatch verifier requires an explicit regex")
        if self.matcher in {"numeric_tolerance", "numeric"}:
            if "expected" not in self.model_fields_set and "value" not in self.model_fields_set:
                raise ValueError("numeric verifier requires expected or value")
            if not any(
                tolerance is not None
                for tolerance in (
                    self.tolerance,
                    self.absolute_tolerance,
                    self.relative_tolerance,
                )
            ):
                raise ValueError("numeric verifier requires an explicit tolerance")
        elif not any(
            (
                self.accepted_phrases,
                self.accepted_aliases,
                self.patterns,
                self.accepted_regexes,
                self.accepted_regex,
                self.regex,
            )
        ):
            raise ValueError(
                "non-numeric evidence verifier requires accepted positive phrases or regexes"
            )
        for tolerance in (
            self.tolerance,
            self.absolute_tolerance,
            self.relative_tolerance,
        ):
            if tolerance is not None and tolerance < 0:
                raise ValueError("verifier tolerances must be non-negative")
        return self


class SupportSpanV3(_StrictModel):
    """A byte-addressed support span copied from the frozen evidence graph."""

    support_span_id: str | None = None
    evidence_id: str
    source_url: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    sha256: str
    support_type: Literal["body", "search_snippet"]

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("evidence_id is not a valid stable identifier")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validate_absolute_http_url(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("span sha256 must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def validate_offsets(self) -> "SupportSpanV3":
        if self.end <= self.start:
            raise ValueError("support span end must be greater than start")
        return self


class EvidenceSourceV3(_StrictModel):
    """Resolved evidence-node binding retained in private case gold.

    ``frozen`` and ``reachable`` are required literals, not permissive defaults.
    Formal compilation additionally checks this entire record against an
    independently supplied catalog, so declaring an invented ID here is not
    enough to publish a case.
    """

    evidence_id: str
    node_type: Literal[
        "entity",
        "attribute",
        "mechanism",
        "assertion",
        "proposition",
        "experience_claim",
        "constraint",
        "contradiction",
        "bridge",
        "decision",
        "category",
        "claim",
        "inference",
        "document",
        "search_result",
        "snippet",
    ]
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: Any
    source_url: str
    source_type: Literal[
        "shopping",
        "forum",
        "concept",
        "structured_db",
        "case_spec",
        "curated",
        "search_result",
        "magento",
        "postmill",
        "wikipedia",
    ]
    content_sha256: str
    corpus_snapshot: str = Field(min_length=1)
    search_snippet_support: bool
    body_support: bool
    verifier: EvidenceVerifierV3
    support_spans: list[SupportSpanV3] = Field(min_length=1)
    frozen: Literal[True]
    reachable: Literal[True]

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("evidence_id is not a valid stable identifier")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validate_absolute_http_url(value)

    @field_validator("content_sha256")
    @classmethod
    def validate_content_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("content_sha256 must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def validate_spans_and_visibility(self) -> "EvidenceSourceV3":
        try:
            json.dumps(self.object, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence object must be strict JSON") from exc
        if not (self.search_snippet_support or self.body_support):
            raise ValueError("an evidence source must expose body or snippet support")
        span_ids = [span.support_span_id for span in self.support_spans if span.support_span_id]
        _require_unique(span_ids, "support_span_id values")
        for span in self.support_spans:
            if span.evidence_id != self.evidence_id:
                raise ValueError(
                    f"support span {span.support_span_id or '<unnamed>'} belongs to "
                    f"{span.evidence_id}, expected {self.evidence_id}"
                )
            if span.source_url != self.source_url:
                raise ValueError("support span source_url must match its evidence source")
            if span.support_type == "body" and not self.body_support:
                raise ValueError("body support span declared while body_support is false")
            if span.support_type == "search_snippet" and not self.search_snippet_support:
                raise ValueError(
                    "search-snippet support span declared while search_snippet_support is false"
                )
        return self


class SlotV3(_StrictModel):
    """One required proof step, with legacy attribute names kept internally.

    The protocol spelling is ``step_id`` / ``vital`` / ``claim``.  Existing
    scorer code may continue to read ``slot_id`` / ``critical`` / ``claim_id``
    as Python attributes while it is migrated; serialized EvaluatorView data
    always uses the proof-step vocabulary.
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    slot_id: str = Field(
        validation_alias=AliasChoices("step_id", "slot_id"),
        serialization_alias="step_id",
    )
    type: Literal["evidence", "bridge", "decision"]
    required: bool = True
    critical: bool = Field(
        validation_alias=AliasChoices("vital", "critical"),
        serialization_alias="vital",
    )
    claim_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("claim", "claim_id"),
        serialization_alias="claim",
    )
    verifier: str | None = None
    acceptable_support: AcceptableSupportV3 | None = None
    provenance_contract: Literal[
        "discovered_then_observed",
        "observed",
    ] | None = None
    requires: list[str] = Field(default_factory=list)
    rule: str | None = None
    requirement_id: str | None = None

    @field_validator("slot_id")
    @classmethod
    def validate_slot_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("slot_id is not a valid stable identifier")
        return value

    @field_validator("requires")
    @classmethod
    def validate_requires_unique(cls, values: list[str]) -> list[str]:
        _require_unique(values, "slot dependencies")
        return values

    @model_validator(mode="after")
    def validate_type_shape(self) -> "SlotV3":
        if self.critical and not self.required:
            raise ValueError(
                "a vital proof step cannot be excluded from required completion"
            )
        if not self.required and self.requirement_id is not None:
            raise ValueError("optional diagnostic slots cannot map to a query requirement")
        if self.type == "evidence":
            if not self.claim_id or not self.verifier:
                raise ValueError("evidence proof steps require claim and verifier")
            if self.acceptable_support is None or self.provenance_contract is None:
                raise ValueError(
                    "evidence proof steps require acceptable_support and "
                    "provenance_contract"
                )
            if self.requires or self.rule is not None:
                raise ValueError("evidence proof steps cannot declare requires or rule")
        else:
            if not self.requires or not self.rule:
                raise ValueError(
                    f"{self.type} proof steps require non-empty requires and rule"
                )
            if any(
                value is not None
                for value in (
                    self.claim_id,
                    self.verifier,
                    self.acceptable_support,
                    self.provenance_contract,
                )
            ):
                raise ValueError(
                    f"{self.type} proof steps cannot declare evidence support fields"
                )
        return self

    @property
    def step_id(self) -> str:
        return self.slot_id

    @property
    def vital(self) -> bool:
        return self.critical

    @property
    def claim(self) -> str | None:
        return self.claim_id

    @property
    def support_source_ids(self) -> tuple[str, ...]:
        if self.type != "evidence" or self.acceptable_support is None:
            return ()
        return tuple(self.acceptable_support.source_ids)

    def legacy_dict(self) -> dict[str, Any]:
        """Return the temporary slot-shaped adapter used by old internal code."""

        payload = self.model_dump(
            mode="json", by_alias=False, exclude_none=True
        )
        payload.pop("acceptable_support", None)
        payload.pop("provenance_contract", None)
        return payload


class EvaluatorViewV3(_StrictModel):
    """Private propositions, proof obligations, and final-answer contract."""

    propositions: list[str] = Field(min_length=1)
    required_proof_steps: list[SlotV3] = Field(min_length=4)
    final_answer_contract: FinalAnswerContractV3

    @field_validator("propositions")
    @classmethod
    def validate_propositions(cls, values: list[str]) -> list[str]:
        if any(not _ID_RE.fullmatch(value) for value in values):
            raise ValueError("EvaluatorView propositions must be stable identifiers")
        _require_unique(values, "EvaluatorView propositions")
        return values

    @model_validator(mode="after")
    def validate_proposition_bindings(self) -> "EvaluatorViewV3":
        evidence_claims = {
            step.claim_id
            for step in self.required_proof_steps
            if step.type == "evidence" and step.claim_id is not None
        }
        unknown = sorted(evidence_claims - set(self.propositions))
        unused = sorted(set(self.propositions) - evidence_claims)
        if unknown or unused:
            raise ValueError(
                "EvaluatorView propositions must exactly match evidence-step claims; "
                f"unknown={unknown}, unused={unused}"
            )
        return self


# Public protocol name; SlotV3 remains as a compatibility type alias.
RequiredProofStepV3 = SlotV3


class QueryRequirementV3(_StrictModel):
    requirement_id: str
    text: str = Field(min_length=1)
    slot_ids: list[str] = Field(min_length=1)
    subgoal_ids: list[str] = Field(min_length=1)
    required: Literal[True]

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("requirement_id is not a valid stable identifier")
        return value

    @field_validator("slot_ids", "subgoal_ids")
    @classmethod
    def validate_slot_ids_unique(cls, values: list[str]) -> list[str]:
        _require_unique(values, "query requirement mappings")
        return values


class ConditionalConclusionV3(_StrictModel):
    answer: str = Field(min_length=1)
    when: str = Field(min_length=1)
    required_tradeoffs: list[str] = Field(min_length=1)

    @field_validator("required_tradeoffs")
    @classmethod
    def validate_tradeoffs_unique(cls, values: list[str]) -> list[str]:
        _require_unique(values, "required_tradeoffs")
        return values


class QueryRenderingV3(_StrictModel):
    few_shot_subset: Literal["manual_dev14_examples3_v1"]
    forbidden_leaks: list[
        Literal["step_id", "source_url", "gold_answer", "required_step_count"]
    ]
    validation: list[Literal["hard_rules", "blind_semantic_alignment"]]
    max_generation_attempts: Literal[3] = QUERY_MAX_GENERATION_ATTEMPTS

    @model_validator(mode="after")
    def validate_leak_policy(self) -> "QueryRenderingV3":
        _require_unique(self.forbidden_leaks, "forbidden_leaks")
        missing = sorted(REQUIRED_FORBIDDEN_LEAK_CLASSES - set(self.forbidden_leaks))
        if missing:
            raise ValueError(f"query leak policy is missing required classes: {missing}")
        if set(self.forbidden_leaks) != REQUIRED_FORBIDDEN_LEAK_CLASSES:
            raise ValueError("query leak policy contains unsupported leak classes")
        if tuple(self.validation) != REQUIRED_QUERY_VALIDATIONS:
            raise ValueError(
                "query validation must exactly be [hard_rules, "
                "blind_semantic_alignment]"
            )
        return self


class TextMatcherV3(_StrictModel):
    matcher: Literal["normalized_text", "regex_fullmatch"]
    accepted_phrases: list[str] | None = None
    accepted_regexes: list[str] | None = None
    normalizers: list[
        Literal["casefold", "whitespace", "punctuation", "hyphen"]
    ] | None = None

    @model_validator(mode="after")
    def validate_positive_matcher(self) -> "TextMatcherV3":
        if self.matcher == "normalized_text":
            if not self.accepted_phrases or self.accepted_regexes is not None:
                raise ValueError(
                    "normalized_text matcher requires accepted_phrases and forbids regexes"
                )
        elif not self.accepted_regexes or self.accepted_phrases is not None:
            raise ValueError(
                "regex_fullmatch matcher requires accepted_regexes and forbids phrases"
            )
        for field_name in ("accepted_phrases", "accepted_regexes", "normalizers"):
            values = getattr(self, field_name)
            if values is not None:
                if not values:
                    raise ValueError(f"{field_name} cannot be empty")
                _require_unique(values, field_name)
        for pattern in self.accepted_regexes or []:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid rule regex: {pattern!r}") from exc
        return self


class DecidableClaimV3(_StrictModel):
    """Case-authored, human-audited negative claim used only for deterministic FP.

    Formal compilation freezes this matcher as private gold.  It must never be
    inferred from report keywords, graph metadata, or an evaluator model.
    """

    claim_id: str
    contradicts_slot_id: str | None = None
    critical: bool
    rejected_matcher: TextMatcherV3

    @field_validator("claim_id", "contradicts_slot_id")
    @classmethod
    def validate_ids(cls, value: str | None) -> str | None:
        if value is not None and not _ID_RE.fullmatch(value):
            raise ValueError("decidable claim identifiers must be stable identifiers")
        return value


class BridgeRuleDefinitionV3(TextMatcherV3):
    type: Literal["bridge"]


class ConditionalDecisionMatcherV3(_StrictModel):
    answer: str = Field(min_length=1)
    when: str = Field(min_length=1)
    condition_matcher: TextMatcherV3
    tradeoff_matchers: dict[str, TextMatcherV3] = Field(min_length=1)


class DecisionRuleDefinitionV3(_StrictModel):
    type: Literal["decision"]
    decision_matcher: TextMatcherV3
    conclusion_matchers: dict[str, TextMatcherV3] = Field(min_length=1)
    admissible_conditions: list[ConditionalDecisionMatcherV3] | None = None

    @model_validator(mode="after")
    def validate_conclusion_matchers(self) -> "DecisionRuleDefinitionV3":
        if any(not answer.strip() for answer in self.conclusion_matchers):
            raise ValueError("conclusion_matchers requires non-empty answer IDs")
        return self


RuleDefinitionV3 = Annotated[
    BridgeRuleDefinitionV3 | DecisionRuleDefinitionV3,
    Field(discriminator="type"),
]


class ResearchSubgoalV3(_StrictModel):
    """One complete, locally decidable research question above slot level."""

    subgoal_id: str
    description: str = Field(min_length=1)
    critical: Literal[True]
    requires: list[str] = Field(min_length=2)
    # The local conclusion remains a slot, never a second scoring atom.  Its
    # deterministic matcher lives in that bridge/decision slot's rule_definition.
    local_conclusion_slot_id: str

    @field_validator("subgoal_id")
    @classmethod
    def validate_subgoal_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("subgoal_id is not a valid stable identifier")
        return value

    @field_validator("local_conclusion_slot_id")
    @classmethod
    def validate_local_conclusion_slot_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("local_conclusion_slot_id is not a valid stable identifier")
        return value

    @field_validator("requires")
    @classmethod
    def validate_requires(cls, values: list[str]) -> list[str]:
        _require_unique(values, "research subgoal slot dependencies")
        return values


class OracleV3(_StrictModel):
    proof: list[str] = Field(min_length=1)
    single_page_sufficient: Literal[False]
    critical_node_ablation: dict[str, "CriticalNodeAblationV3"]
    human_solve_minutes: int | None = Field(default=None, gt=0)
    minimum_required_evidence_nodes: int | None = Field(default=None, ge=2)
    minimum_reasoning_depth: int | None = Field(default=None, ge=2)

    @field_validator("proof")
    @classmethod
    def validate_proof_unique(cls, values: list[str]) -> list[str]:
        _require_unique(values, "oracle proof slots")
        return values


class CriticalNodeAblationV3(_StrictModel):
    """Human-audited semantic effect of removing one critical evidence slot."""

    outcome: Literal["decision_unresolved", "admissible_set_changed"]
    admissible_set_before: list[str] | None = None
    admissible_set_after: list[str] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "CriticalNodeAblationV3":
        before = self.admissible_set_before
        after = self.admissible_set_after
        if self.outcome == "decision_unresolved":
            if before is not None or after is not None:
                raise ValueError(
                    "decision_unresolved ablation must not declare admissible sets"
                )
            return self
        if before is None or after is None:
            raise ValueError(
                "admissible_set_changed requires admissible_set_before and "
                "admissible_set_after"
            )
        _require_unique(before, "admissible_set_before")
        _require_unique(after, "admissible_set_after")
        if set(before) == set(after):
            raise ValueError("ablation must change the admissible conclusion set")
        return self


OracleV3.model_rebuild()


class FormalBindingsV3(_StrictModel):
    """Private, compiler-produced binding to external formal inputs."""

    formal: Literal[True]
    evidence_catalog_sha256: str
    support_spans_sha256: str
    graph_edges_sha256: str
    evidence_graph_sha256: str
    corpus_registry_sha256: str
    reachability_manifest_sha256: str
    decidable_claims_sha256: str
    proof_subgraph_sha256: str
    query_authoring_policy: Literal[
        "legacy_query_path_v1",
        "human_query_pipeline_v1",
    ] = "legacy_query_path_v1"
    query_release_sha256: str | None = None
    root_node_ids: list[str] = Field(min_length=1)
    critical_evidence_node_ids: list[str] = Field(min_length=2)
    reachable_node_ids: list[str] = Field(min_length=2)

    @field_validator(
        "evidence_catalog_sha256",
        "support_spans_sha256",
        "graph_edges_sha256",
        "evidence_graph_sha256",
        "corpus_registry_sha256",
        "reachability_manifest_sha256",
        "decidable_claims_sha256",
        "proof_subgraph_sha256",
    )
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("formal binding hashes must be 64 lowercase hex characters")
        return value

    @field_validator("query_release_sha256")
    @classmethod
    def validate_optional_query_release_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError(
                "query release binding must be 64 lowercase hex characters"
            )
        return value

    @field_validator("root_node_ids", "critical_evidence_node_ids", "reachable_node_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not _ID_RE.fullmatch(value) for value in values):
            raise ValueError("formal binding node IDs must be stable identifiers")
        _require_unique(values, "formal binding node IDs")
        return values

    @model_validator(mode="after")
    def validate_query_authoring_binding(self) -> "FormalBindingsV3":
        if self.query_authoring_policy == "human_query_pipeline_v1":
            if self.query_release_sha256 is None:
                raise ValueError(
                    "human query authoring requires a query release binding"
                )
        elif self.query_release_sha256 is not None:
            raise ValueError(
                "legacy query authoring cannot declare a human query release"
            )
        return self


class CaseSpecV3(_StrictModel):
    """Canonical v3 case with a fully validated proof dependency graph."""

    task_id: str
    task_version: Literal[3]
    case_schema: Literal["evidence_graph_case_v1"]
    evidence_graph: Literal["evidence_graph_v1"]
    observation_semantics: Literal["observation_ledger_v1"]
    scoring_semantics: Literal["verified_slots_v1", "proof_steps_v1"]
    headline_metrics: list[str] = Field(min_length=2, max_length=2)
    diagnostic_metric: str | None = None
    diagnostic_metrics: list[str] | None = None
    corpus_snapshot: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    motif: Literal[
        "constraint_match_and_select",
        "claim_verification",
        "evidence_reconciliation",
        "causal_or_evolution_explanation",
        "multi_branch_synthesis",
        "constraint_filter",
        "mechanism_application",
        "claim_reconciliation",
        "comparative_tradeoff",
        "counterexample_revision",
    ]
    difficulty: DifficultyV3
    generator_view: GeneratorViewV3
    evaluator_view: EvaluatorViewV3
    evidence_sources: list[EvidenceSourceV3] = Field(min_length=2)
    # Formal compiler fills these from the independent, complete corpus
    # registry and reachability manifest.  They are private gold metadata and
    # are never copied into a rendered query.
    corpus_registry_urls: list[str] | None = None
    corpus_registry_hash: str | None = None
    discovery_root_urls: list[str] | None = None
    rule_definitions: dict[str, RuleDefinitionV3] = Field(min_length=1)
    decidable_claims: list[DecidableClaimV3] = Field(min_length=1)
    research_subgoals: list[ResearchSubgoalV3] = Field(min_length=4)
    query_requirements: list[QueryRequirementV3] = Field(min_length=1)
    acceptable_conclusions: list[str | ConditionalConclusionV3] = Field(min_length=1)
    query_rendering: QueryRenderingV3
    oracle: OracleV3
    formal_bindings: FormalBindingsV3 | None = None

    @model_validator(mode="before")
    @classmethod
    def adapt_internal_legacy_shape(cls, value: Any) -> Any:
        """Accept the temporary internal ``scenario``/``slots`` aliases.

        The adapter exists solely so the pre-redesign scorer and authoring
        helpers can migrate incrementally.  It is intentionally one-way:
        protocol serialization and formal compilation emit only the two views.
        """

        if not isinstance(value, Mapping):
            return value
        payload = dict(value)
        semantics = payload.get("scoring_semantics")
        proof_step_case = semantics == PROOF_STEP_SCORING_SEMANTICS

        legacy_scenario = payload.pop("scenario", None)
        if proof_step_case and legacy_scenario is not None:
            raise ValueError(
                "proof_steps_v1 protocol forbids the legacy top-level scenario alias"
            )
        if "generator_view" not in payload:
            if proof_step_case:
                raise ValueError(
                    "proof_steps_v1 cases require an explicit generator_view"
                )
            if not isinstance(legacy_scenario, Mapping):
                raise ValueError("case requires an explicit generator_view")
            context = str(legacy_scenario.get("context") or "").strip()
            objective = str(legacy_scenario.get("objective") or "").strip()
            payload["generator_view"] = {
                "scenario": context or objective,
                "constraints": list(legacy_scenario.get("constraints") or []),
                "candidate_actions": list(
                    legacy_scenario.get("candidate_actions") or []
                ),
                "target": objective or context,
            }

        sources = payload.get("evidence_sources")
        source_rows = sources if isinstance(sources, list) else []
        source_by_id = {
            str(row.get("evidence_id")): row
            for row in source_rows
            if isinstance(row, Mapping) and row.get("evidence_id")
        }

        legacy_steps = payload.pop("slots", None)
        if proof_step_case and legacy_steps is not None:
            raise ValueError(
                "proof_steps_v1 protocol forbids the legacy top-level slots alias"
            )
        evaluator = payload.get("evaluator_view")
        if evaluator is None:
            if proof_step_case:
                raise ValueError(
                    "proof_steps_v1 cases require evaluator_view.required_proof_steps"
                )
            if not isinstance(legacy_steps, list):
                raise ValueError("case requires an explicit evaluator_view")
            raw_steps: list[Any] = legacy_steps
            evidence_claims = [
                str(step.get("claim_id"))
                for step in raw_steps
                if isinstance(step, Mapping)
                and step.get("type") == "evidence"
                and step.get("claim_id")
            ]
            conclusions = payload.get("acceptable_conclusions")
            unique_product = bool(
                isinstance(conclusions, list)
                and len(conclusions) == 1
                and isinstance(conclusions[0], str)
            )
            evaluator = {
                "propositions": evidence_claims,
                "required_proof_steps": raw_steps,
                "final_answer_contract": {
                    "unique_product_required": unique_product,
                    "must_address_constraints": True,
                    "must_explain_tradeoffs": True,
                    "must_depend_on_verified_steps": True,
                },
            }
        if not isinstance(evaluator, Mapping):
            raise ValueError("evaluator_view must be an object")
        evaluator_payload = dict(evaluator)
        steps = evaluator_payload.get("required_proof_steps")
        if not isinstance(steps, list):
            raise ValueError("evaluator_view requires required_proof_steps")
        normalized_steps: list[Any] = []
        for raw_step in steps:
            if not isinstance(raw_step, Mapping):
                normalized_steps.append(raw_step)
                continue
            step = dict(raw_step)
            if "step_id" not in step and "slot_id" in step:
                step["step_id"] = step.pop("slot_id")
            if "vital" not in step and "critical" in step:
                step["vital"] = step.pop("critical")
            if "claim" not in step and "claim_id" in step:
                step["claim"] = step.pop("claim_id")
            step.setdefault("required", bool(step.get("vital", True)))
            if step.get("type") == "evidence":
                source = source_by_id.get(str(step.get("claim") or ""))
                if isinstance(source, Mapping):
                    verifier = source.get("verifier")
                    if "verifier" not in step and isinstance(verifier, Mapping):
                        step["verifier"] = verifier.get("kind")
                    step.setdefault(
                        "acceptable_support",
                        {
                            "source_ids": [str(source.get("evidence_id"))],
                            "source_roles": [str(source.get("source_type"))],
                            "support_mode": "body_or_exact_snippet",
                            "condition_match": True,
                        },
                    )
                    step.setdefault(
                        "provenance_contract", "discovered_then_observed"
                    )
                elif not proof_step_case:
                    # Preserve the legacy validator's more useful fabricated-ID
                    # failure instead of failing early on adapter-only fields.
                    step.setdefault(
                        "acceptable_support",
                        {
                            "source_ids": [str(step.get("claim") or "unknown")],
                            "source_roles": ["unknown"],
                            "support_mode": "body_or_exact_snippet",
                            "condition_match": True,
                        },
                    )
                    step.setdefault(
                        "provenance_contract", "discovered_then_observed"
                    )
            normalized_steps.append(step)
        evaluator_payload["required_proof_steps"] = normalized_steps
        payload["evaluator_view"] = evaluator_payload

        rendering = payload.get("query_rendering")
        if isinstance(rendering, Mapping) and "canonical_template" in rendering:
            if proof_step_case:
                raise ValueError(
                    "proof_steps_v1 cases require the new query_rendering protocol"
                )
            old = dict(rendering)
            old.pop("canonical_template", None)
            old.pop("gold_terms", None)
            aliases = {
                "slot_id": "step_id",
                "source_url": "source_url",
                "gold_product": "gold_answer",
                "scorer_quota": "required_step_count",
            }
            old["forbidden_leaks"] = [
                aliases.get(str(item), str(item))
                for item in old.get("forbidden_leaks", [])
            ]
            old["few_shot_subset"] = "manual_dev14_examples3_v1"
            old["validation"] = list(REQUIRED_QUERY_VALIDATIONS)
            old["max_generation_attempts"] = QUERY_MAX_GENERATION_ATTEMPTS
            payload["query_rendering"] = old
        return payload

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        if not _TASK_ID_RE.fullmatch(value):
            raise ValueError("task_id must match dra_v3_<cluster>_<NNNN>")
        return value

    @field_validator("headline_metrics", "diagnostic_metrics")
    @classmethod
    def validate_metric_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError("metric names must be non-empty strings")
        _require_unique(values, "metric names")
        return values

    @field_validator("corpus_registry_urls", "discovery_root_urls")
    @classmethod
    def validate_private_urls(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        if not values:
            raise ValueError("private URL registries cannot be empty when declared")
        for value in values:
            _validate_absolute_http_url(value)
        _require_unique(values, "private URL registries")
        return values

    @field_validator("corpus_registry_hash")
    @classmethod
    def validate_corpus_registry_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError("corpus_registry_hash must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def validate_case_invariants(self) -> "CaseSpecV3":
        if self.scoring_semantics == PROOF_STEP_SCORING_SEMANTICS:
            if tuple(self.headline_metrics) != PROOF_STEP_HEADLINE_METRICS:
                raise ValueError(
                    "proof_steps_v1 headline_metrics must exactly be "
                    "[partial_completion_rate_v1, full_pass_rate_v1]"
                )
            if tuple(self.diagnostic_metrics or ()) != PROOF_STEP_DIAGNOSTIC_METRICS:
                raise ValueError(
                    "proof_steps_v1 diagnostic_metrics must exactly be "
                    "[route_coverage_v1, acquisition_diagnostics_v1]"
                )
            if self.diagnostic_metric is not None:
                raise ValueError(
                    "proof_steps_v1 forbids the legacy singular diagnostic_metric"
                )
        else:
            if tuple(self.headline_metrics) != HEADLINE_METRICS:
                raise ValueError(
                    "verified_slots_v1 headline_metrics must exactly be "
                    "[verified_research_completion_v1, task_solve_rate_v1]"
                )
            if self.diagnostic_metric != DIAGNOSTIC_METRIC:
                raise ValueError(
                    "verified_slots_v1 diagnostic_metric must be verified_f1_v1"
                )
            if self.diagnostic_metrics is not None:
                raise ValueError(
                    "verified_slots_v1 forbids proof-step diagnostic_metrics"
                )
            mismatched_legacy_steps = sorted(
                step.step_id
                for step in self.slots
                if step.required != step.vital
            )
            if mismatched_legacy_steps:
                raise ValueError(
                    "verified_slots_v1 requires required == critical; mismatched "
                    f"steps: {mismatched_legacy_steps}"
                )
        if (
            self.scoring_semantics == PROOF_STEP_SCORING_SEMANTICS
            and self.motif not in SUPPORTED_MOTIFS
        ):
            raise ValueError(
                "proof_steps_v1 cases require one of the five graph-native motifs"
            )
        if (
            self.scoring_semantics == SCORING_SEMANTICS
            and self.motif not in LEGACY_SUPPORTED_MOTIFS | SUPPORTED_MOTIFS
        ):
            raise ValueError("verified_slots_v1 case has an unsupported legacy motif")
        self._validate_generator_evaluator_separation()
        self._validate_evidence_bindings()
        slot_map = self.slot_map
        self._validate_dependency_graph(slot_map)
        decision = self.decision_slot
        closure = self.dependency_closure(decision.slot_id)
        critical_ids = {slot.slot_id for slot in self.slots if slot.critical}
        if closure != critical_ids:
            missing = sorted(closure - critical_ids)
            disconnected = sorted(critical_ids - closure)
            problems: list[str] = []
            if missing:
                problems.append(f"decision dependencies not marked critical: {missing}")
            if disconnected:
                problems.append(f"critical slots outside decision proof: {disconnected}")
            raise ValueError("; ".join(problems))

        critical_evidence = [
            slot for slot in self.slots if slot.critical and slot.type == "evidence"
        ]
        if len(critical_evidence) < 2:
            raise ValueError("a formal case requires at least two critical evidence slots")
        critical_url_sets = [
            {
                self.evidence_source_map[source_id].source_url
                for source_id in slot.support_source_ids
            }
            for slot in critical_evidence
        ]
        single_page_urls = set.intersection(*critical_url_sets)
        if single_page_urls:
            raise ValueError(
                "single-page case rejected: one frozen page can satisfy every "
                f"critical evidence step: {sorted(single_page_urls)}"
            )

        depth = self.minimum_reasoning_depth
        if depth < 2:
            raise ValueError(
                "proof is not multi-hop: evidence-to-decision reasoning depth must be at least 2"
            )
        for slot in critical_evidence:
            if self._decision_survives_ablation(slot.slot_id):
                raise ValueError(
                    f"critical ablation for {slot.slot_id} leaves the decision structurally resolvable"
                )

        self._validate_conclusions()
        self._validate_rule_definitions()
        self._validate_decidable_claims()
        self._validate_research_subgoals(critical_ids)
        self._validate_query_mapping(critical_ids)
        self._validate_oracle(critical_ids, depth)
        self._validate_formal_bindings()
        return self

    def _validate_generator_evaluator_separation(self) -> None:
        """Fail if any private proof/answer material entered GeneratorView."""

        public_payload = self.generator_view.model_dump(mode="json")
        public_text = json.dumps(public_payload, ensure_ascii=False).casefold()
        public_identifiers = {
            value.casefold()
            for value in (
                self.generator_view.constraints
                + self.generator_view.candidate_actions
            )
        }

        private_tokens: set[str] = {
            source.source_url for source in self.evidence_sources
        }
        private_tokens.update(source.evidence_id for source in self.evidence_sources)
        private_tokens.update(self.evaluator_view.propositions)
        for step in self.slots:
            private_tokens.add(step.slot_id)
            if step.claim_id:
                private_tokens.add(step.claim_id)
            if step.rule:
                private_tokens.add(step.rule)
        for conclusion in self.acceptable_conclusions:
            if isinstance(conclusion, ConditionalConclusionV3):
                private_tokens.add(conclusion.when)
                private_tokens.update(conclusion.required_tradeoffs)

        def collect_strings(value: Any) -> None:
            if isinstance(value, str):
                private_tokens.add(value)
            elif isinstance(value, BaseModel):
                collect_strings(value.model_dump(mode="json", exclude_none=True))
            elif isinstance(value, Mapping):
                for nested in value.values():
                    collect_strings(nested)
            elif isinstance(value, (list, tuple, set)):
                for nested in value:
                    collect_strings(nested)

        # Matcher phrases and decidable negatives are answer-side truths, even
        # when they do not carry an obvious gold-looking identifier.
        collect_strings(self.rule_definitions)
        collect_strings(self.decidable_claims)

        leaked: list[str] = []
        for token in sorted(private_tokens, key=lambda item: (-len(item), item)):
            folded = token.casefold().strip()
            if not folded or folded in public_identifiers:
                continue
            if re.search(r"^[A-Za-z0-9_.:-]+$", token):
                present = re.search(
                    rf"(?<![A-Za-z0-9_]){re.escape(folded)}(?![A-Za-z0-9_])",
                    public_text,
                )
            else:
                present = folded in public_text
            if present:
                leaked.append(token)
        if leaked:
            raise ValueError(
                "GeneratorView leaks EvaluatorView/evidence/answer material: "
                f"{leaked[:8]}"
            )

        if self.evaluator_view.final_answer_contract.unique_product_required:
            simple = [
                value
                for value in self.acceptable_conclusions
                if isinstance(value, str)
            ]
            if len(simple) != 1 or len(self.acceptable_conclusions) != 1:
                raise ValueError(
                    "unique_product_required needs exactly one unconditional "
                    "acceptable conclusion"
                )

    def _validate_evidence_bindings(self) -> None:
        evidence_ids = [source.evidence_id for source in self.evidence_sources]
        _require_unique(evidence_ids, "evidence source IDs")
        source_map = self.evidence_source_map
        evidence_slots = [slot for slot in self.slots if slot.type == "evidence"]
        claim_ids = [slot.claim_id for slot in evidence_slots if slot.claim_id]
        if self.scoring_semantics == SCORING_SEMANTICS:
            _require_unique(claim_ids, "evidence slot claim_ids")
            referenced_source_ids = set(claim_ids)
            for slot in evidence_slots:
                if set(slot.support_source_ids) != {slot.claim_id}:
                    raise ValueError(
                        "verified_slots_v1 evidence support must remain bound to "
                        f"its historical claim/source ID: {slot.step_id}"
                    )
                assert slot.acceptable_support is not None
                if slot.acceptable_support.support_relation != "SELF":
                    raise ValueError(
                        "verified_slots_v1 evidence support must retain SELF "
                        f"binding: {slot.step_id}"
                    )
        else:
            referenced_source_ids = {
                source_id
                for slot in evidence_slots
                for source_id in slot.support_source_ids
            }
            for slot in evidence_slots:
                assert slot.acceptable_support is not None
                relation = slot.acceptable_support.support_relation
                separates_proposition = any(
                    source_id != slot.claim_id
                    for source_id in slot.support_source_ids
                )
                if separates_proposition and relation == "SELF":
                    raise ValueError(
                        f"proof step {slot.step_id} binds separate support nodes "
                        "and must declare ASSERTS/SUPPORTED_BY/REFUTES"
                    )
                if relation != "SELF" and any(
                    source_id == slot.claim_id
                    for source_id in slot.support_source_ids
                ):
                    raise ValueError(
                        f"proof step {slot.step_id} cannot mix SELF and semantic-edge "
                        "support alternatives"
                    )
        unknown = sorted(referenced_source_ids - set(source_map))
        unused = sorted(set(source_map) - referenced_source_ids)
        if unknown:
            raise ValueError(
                f"evidence steps reference unknown/fabricated support IDs: {unknown}"
            )
        if unused:
            raise ValueError(f"evidence_sources contains unbound evidence IDs: {unused}")
        for source in self.evidence_sources:
            if source.corpus_snapshot != self.corpus_snapshot:
                raise ValueError(
                    f"evidence {source.evidence_id} snapshot {source.corpus_snapshot!r} "
                    f"does not match case snapshot {self.corpus_snapshot!r}"
                )
        for slot in evidence_slots:
            assert slot.acceptable_support is not None
            allowed_roles = set(slot.acceptable_support.source_roles)
            for source_id in slot.support_source_ids:
                source = source_map[source_id]
                if slot.verifier != source.verifier.kind:
                    raise ValueError(
                        f"step {slot.slot_id} verifier {slot.verifier!r} does not match "
                        f"support source {source_id} verifier {source.verifier.kind!r}"
                    )
                source_roles = {
                    source.source_type,
                    source_role_family(source.source_type),
                }
                if source.source_type in {"concept", "wikipedia", "curated"}:
                    # The redesign's public role vocabulary calls this family
                    # ``concept``; the historical cross-source gate called it
                    # ``mechanism``.  Accept both without changing legacy
                    # family-count semantics.
                    source_roles.add("concept")
                if allowed_roles.isdisjoint(source_roles):
                    raise ValueError(
                        f"proof step {slot.slot_id} acceptable_support excludes "
                        f"source {source_id} role {source.source_type!r}"
                    )
                support_mode = slot.acceptable_support.support_mode
                if support_mode == "body" and not source.body_support:
                    raise ValueError(
                        f"proof step {slot.slot_id} requires body support but "
                        f"source {source_id} has no frozen body support"
                    )
                if (
                    support_mode == "exact_snippet"
                    and not source.search_snippet_support
                ):
                    raise ValueError(
                        f"proof step {slot.slot_id} requires exact-snippet support "
                        f"but source {source_id} has no frozen snippet support"
                    )
                if slot.critical and (
                    source.source_type == "search_result"
                    or source.node_type == "search_result"
                ):
                    raise ValueError(
                        f"critical evidence {slot.slot_id} cannot use discovery-only "
                        "search_result support"
                    )
        if self.corpus_registry_urls is not None:
            missing_urls = sorted(
                {source.source_url for source in self.evidence_sources}
                - set(self.corpus_registry_urls)
            )
            if missing_urls:
                raise ValueError(
                    "evidence source URLs missing from complete corpus registry: "
                    f"{missing_urls}"
                )

    def _validate_dependency_graph(self, slot_map: Mapping[str, SlotV3]) -> None:
        slot_ids = [slot.slot_id for slot in self.slots]
        _require_unique(slot_ids, "slot IDs")
        for slot in self.slots:
            missing = sorted(set(slot.requires) - set(slot_map))
            if missing:
                raise ValueError(f"slot {slot.slot_id} has unknown dependencies: {missing}")
            if slot.slot_id in slot.requires:
                raise ValueError(f"slot {slot.slot_id} cannot depend on itself")
            if slot.type == "bridge":
                invalid = [dep for dep in slot.requires if slot_map[dep].type == "decision"]
                if invalid:
                    raise ValueError(
                        f"bridge {slot.slot_id} cannot depend on decision slots: {invalid}"
                    )
            if slot.type == "decision":
                invalid = [dep for dep in slot.requires if slot_map[dep].type == "decision"]
                if invalid:
                    raise ValueError(
                        f"decision {slot.slot_id} cannot depend on decision slots: {invalid}"
                    )

        decisions = [slot for slot in self.slots if slot.type == "decision"]
        if len(decisions) != 1:
            raise ValueError("the v3 foundation requires exactly one decision slot")
        if not decisions[0].critical:
            raise ValueError("the decision slot must be critical")
        if not decisions[0].required:
            raise ValueError("the decision slot must be required")

        state: dict[str, int] = {}

        def visit(slot_id: str, stack: list[str]) -> None:
            marker = state.get(slot_id, 0)
            if marker == 1:
                cycle_start = stack.index(slot_id) if slot_id in stack else 0
                cycle = stack[cycle_start:] + [slot_id]
                raise ValueError(f"slot dependencies must form a DAG; cycle: {' -> '.join(cycle)}")
            if marker == 2:
                return
            state[slot_id] = 1
            for dependency in slot_map[slot_id].requires:
                visit(dependency, stack + [slot_id])
            state[slot_id] = 2

        for slot_id in slot_map:
            visit(slot_id, [])

    def _validate_query_mapping(self, critical_ids: set[str]) -> None:
        requirement_ids = [item.requirement_id for item in self.query_requirements]
        _require_unique(requirement_ids, "query requirement IDs")
        slot_map = self.slot_map
        covered: set[str] = set()
        covered_subgoals: set[str] = set()
        requirement_map = {item.requirement_id: item for item in self.query_requirements}
        subgoal_map = {subgoal.subgoal_id: subgoal for subgoal in self.research_subgoals}
        required_ids = {slot.slot_id for slot in self.slots if slot.required}
        for requirement in self.query_requirements:
            unknown = sorted(set(requirement.slot_ids) - set(slot_map))
            if unknown:
                raise ValueError(
                    f"query requirement {requirement.requirement_id} maps unknown slots: {unknown}"
                )
            non_required = sorted(set(requirement.slot_ids) - required_ids)
            if non_required:
                raise ValueError(
                    f"query requirement {requirement.requirement_id} maps optional slots: "
                    f"{non_required}"
                )
            covered.update(requirement.slot_ids)
            unknown_subgoals = sorted(set(requirement.subgoal_ids) - set(subgoal_map))
            if unknown_subgoals:
                raise ValueError(
                    f"query requirement {requirement.requirement_id} maps unknown "
                    f"research subgoals: {unknown_subgoals}"
                )
            for subgoal_id in requirement.subgoal_ids:
                subgoal = subgoal_map[subgoal_id]
                missing_slots = sorted(set(subgoal.requires) - set(requirement.slot_ids))
                if missing_slots:
                    raise ValueError(
                        f"query requirement {requirement.requirement_id} maps subgoal "
                        f"{subgoal_id} without all of its slots: {missing_slots}"
                    )
            covered_subgoals.update(requirement.subgoal_ids)
        missing = sorted(required_ids - covered)
        if missing:
            raise ValueError(f"required slots have no query requirement mapping: {missing}")
        required_subgoals = {subgoal.subgoal_id for subgoal in self.research_subgoals}
        missing_subgoals = sorted(required_subgoals - covered_subgoals)
        if missing_subgoals:
            raise ValueError(
                "required research subgoals have no query requirement mapping: "
                f"{missing_subgoals}"
            )
        for slot in self.slots:
            if slot.requirement_id is None:
                continue
            requirement = requirement_map.get(slot.requirement_id)
            if requirement is None:
                raise ValueError(
                    f"slot {slot.slot_id} references unknown requirement {slot.requirement_id}"
                )
            if slot.slot_id not in requirement.slot_ids:
                raise ValueError(
                    f"slot {slot.slot_id} requirement_id is inconsistent with query mapping"
                )

    def _validate_research_subgoals(self, critical_ids: set[str]) -> None:
        subgoal_ids = [subgoal.subgoal_id for subgoal in self.research_subgoals]
        _require_unique(subgoal_ids, "research subgoal IDs")
        descriptions = [subgoal.description.casefold() for subgoal in self.research_subgoals]
        _require_unique(descriptions, "research subgoal descriptions")
        local_conclusion_slots = [
            subgoal.local_conclusion_slot_id for subgoal in self.research_subgoals
        ]
        _require_unique(
            local_conclusion_slots,
            "research subgoal local conclusion slots",
        )
        dependency_sets = [tuple(sorted(subgoal.requires)) for subgoal in self.research_subgoals]
        if len(set(dependency_sets)) != len(dependency_sets):
            raise ValueError(
                "research subgoals must have distinct required slot sets, not duplicate labels"
            )
        slot_map = self.slot_map
        covered: set[str] = set()
        for subgoal in self.research_subgoals:
            unknown = sorted(set(subgoal.requires) - set(slot_map))
            if unknown:
                raise ValueError(
                    f"research subgoal {subgoal.subgoal_id} has unknown slots: {unknown}"
                )
            noncritical = sorted(set(subgoal.requires) - critical_ids)
            if noncritical:
                raise ValueError(
                    f"research subgoal {subgoal.subgoal_id} uses non-critical slots: "
                    f"{noncritical}"
                )
            types = {slot_map[slot_id].type for slot_id in subgoal.requires}
            if "evidence" not in types or not ({"bridge", "decision"} & types):
                raise ValueError(
                    f"research subgoal {subgoal.subgoal_id} must combine evidence with "
                    "a bridge or decision; a fact leaf is not a research subgoal"
                )
            if subgoal.local_conclusion_slot_id not in subgoal.requires:
                raise ValueError(
                    f"research subgoal {subgoal.subgoal_id} local conclusion slot "
                    "must appear in requires"
                )
            conclusion_slot = slot_map[subgoal.local_conclusion_slot_id]
            if conclusion_slot.type not in {"bridge", "decision"}:
                raise ValueError(
                    f"research subgoal {subgoal.subgoal_id} local conclusion must be "
                    "a bridge or decision slot"
                )
            covered.update(subgoal.requires)
        missing = sorted(critical_ids - covered)
        if missing:
            raise ValueError(
                f"critical slots are outside all required research subgoals: {missing}"
            )

        if self.cross_source_bridge_count < 2:
            raise ValueError(
                "Deep Research pilot requires at least two critical cross-source bridges"
            )

    def _validate_conclusions(self) -> None:
        simple = [value for value in self.acceptable_conclusions if isinstance(value, str)]
        conditional = [
            value
            for value in self.acceptable_conclusions
            if isinstance(value, ConditionalConclusionV3)
        ]
        if simple and conditional:
            raise ValueError("acceptable_conclusions cannot mix simple and conditional forms")
        candidates = set(self.generator_view.candidate_actions)
        if simple:
            if len(simple) != 1:
                raise ValueError(
                    "multiple admissible answers require explicit conditional conclusion rules"
                )
            answers = simple
        else:
            answers = [item.answer for item in conditional]
            _require_unique(answers, "conditional conclusion answers")
            conditions = [item.when for item in conditional]
            _require_unique(conditions, "conditional conclusion conditions")
        unknown_answers = sorted(set(answers) - candidates)
        if unknown_answers:
            raise ValueError(
                f"acceptable conclusions are not declared candidate actions: {unknown_answers}"
            )

    def _validate_rule_definitions(self) -> None:
        for rule_id in self.rule_definitions:
            if not _ID_RE.fullmatch(rule_id):
                raise ValueError(f"invalid rule definition ID: {rule_id!r}")
        rule_slots = [slot for slot in self.slots if slot.type in {"bridge", "decision"}]
        referenced = {slot.rule for slot in rule_slots if slot.rule is not None}
        missing = sorted(referenced - set(self.rule_definitions))
        unused = sorted(set(self.rule_definitions) - referenced)
        if missing:
            raise ValueError(f"bridge/decision slots reference undefined rules: {missing}")
        if unused:
            raise ValueError(f"rule_definitions contains unused rules: {unused}")
        for slot in rule_slots:
            assert slot.rule is not None
            definition = self.rule_definitions[slot.rule]
            if definition.type != slot.type:
                raise ValueError(
                    f"slot {slot.slot_id} type {slot.type} references "
                    f"{definition.type} rule {slot.rule}"
                )

        decision_rule = self.rule_definitions[self.decision_slot.rule]
        assert isinstance(decision_rule, DecisionRuleDefinitionV3)
        conclusions = {
            value if isinstance(value, str) else value.answer
            for value in self.acceptable_conclusions
        }
        if set(decision_rule.conclusion_matchers) != conclusions:
            raise ValueError(
                "decision conclusion_matchers keys must exactly match acceptable conclusions"
            )
        conditional = [
            value
            for value in self.acceptable_conclusions
            if isinstance(value, ConditionalConclusionV3)
        ]
        conditions = decision_rule.admissible_conditions
        if not conditional:
            if conditions:
                raise ValueError(
                    "unique conclusion decision rule cannot declare admissible_conditions"
                )
            return
        if not conditions:
            raise ValueError(
                "conditional conclusions require decision-rule admissible_conditions"
            )
        by_answer = {condition.answer: condition for condition in conditions}
        if len(by_answer) != len(conditions) or set(by_answer) != conclusions:
            raise ValueError(
                "admissible_conditions must cover every conditional answer exactly once"
            )
        for conclusion in conditional:
            condition = by_answer[conclusion.answer]
            if condition.when != conclusion.when:
                raise ValueError(
                    f"condition matcher for {conclusion.answer} has the wrong when rule"
                )
            if set(condition.tradeoff_matchers) != set(conclusion.required_tradeoffs):
                raise ValueError(
                    f"tradeoff matchers for {conclusion.answer} must exactly cover "
                    "required_tradeoffs"
                )

    def _validate_decidable_claims(self) -> None:
        claim_ids = [claim.claim_id for claim in self.decidable_claims]
        _require_unique(claim_ids, "decidable claim IDs")
        matcher_hashes = [
            _canonical_sha256(
                claim.rejected_matcher.model_dump(mode="json", exclude_none=True)
            )
            for claim in self.decidable_claims
        ]
        _require_unique(matcher_hashes, "decidable rejected matchers")

        evidence_slot_by_claim_id = {
            slot.claim_id: slot
            for slot in self.slots
            if slot.type == "evidence" and slot.claim_id is not None
        }
        for claim in self.decidable_claims:
            target_id = claim.contradicts_slot_id or claim.claim_id
            target = self.slot_map.get(target_id) or evidence_slot_by_claim_id.get(target_id)
            if target is None:
                raise ValueError(
                    f"decidable claim {claim.claim_id} is not bound to a known slot; "
                    "declare contradicts_slot_id"
                )
            if claim.critical != target.critical:
                raise ValueError(
                    f"decidable claim {claim.claim_id} critical flag disagrees with "
                    f"slot {target.slot_id}"
                )
        if not any(claim.critical for claim in self.decidable_claims):
            raise ValueError(
                "a formal case requires at least one critical case-authored "
                "decidable negative claim"
            )

    def _validate_oracle(self, critical_ids: set[str], depth: int) -> None:
        proof = self.oracle.proof
        if set(proof) != critical_ids:
            missing = sorted(critical_ids - set(proof))
            extra = sorted(set(proof) - critical_ids)
            raise ValueError(f"oracle proof must equal critical proof closure; missing={missing}, extra={extra}")
        position = {slot_id: index for index, slot_id in enumerate(proof)}
        for slot_id in proof:
            for dependency in self.slot_map[slot_id].requires:
                if position[dependency] >= position[slot_id]:
                    raise ValueError(
                        f"oracle proof is not topological: {dependency} must precede {slot_id}"
                    )
        if proof[-1] != self.decision_slot.slot_id:
            raise ValueError("oracle proof must end with the decision slot")
        evidence_count = sum(
            1 for slot_id in critical_ids if self.slot_map[slot_id].type == "evidence"
        )
        critical_evidence_ids = {
            slot_id for slot_id in critical_ids if self.slot_map[slot_id].type == "evidence"
        }
        ablation_ids = set(self.oracle.critical_node_ablation)
        if ablation_ids != critical_evidence_ids:
            missing = sorted(critical_evidence_ids - ablation_ids)
            extra = sorted(ablation_ids - critical_evidence_ids)
            raise ValueError(
                "oracle critical_node_ablation must cover every and only critical "
                f"evidence slot; missing={missing}, extra={extra}"
            )
        conclusion_answers = {
            value if isinstance(value, str) else value.answer
            for value in self.acceptable_conclusions
        }
        candidates = set(self.generator_view.candidate_actions)
        for slot_id, ablation in self.oracle.critical_node_ablation.items():
            if self._decision_survives_ablation(slot_id):
                raise ValueError(
                    f"oracle ablation {slot_id} is not structurally connected to decision"
                )
            if ablation.outcome == "admissible_set_changed":
                assert ablation.admissible_set_before is not None
                assert ablation.admissible_set_after is not None
                if set(ablation.admissible_set_before) != conclusion_answers:
                    raise ValueError(
                        f"ablation {slot_id} admissible_set_before must equal case conclusions"
                    )
                unknown = sorted(set(ablation.admissible_set_after) - candidates)
                if unknown:
                    raise ValueError(
                        f"ablation {slot_id} has undeclared candidate conclusions: {unknown}"
                    )
        if (
            self.oracle.minimum_required_evidence_nodes is not None
            and self.oracle.minimum_required_evidence_nodes != evidence_count
        ):
            raise ValueError("oracle minimum_required_evidence_nodes disagrees with proof DAG")
        if (
            self.oracle.minimum_reasoning_depth is not None
            and self.oracle.minimum_reasoning_depth != depth
        ):
            raise ValueError("oracle minimum_reasoning_depth disagrees with proof DAG")

    def _validate_formal_bindings(self) -> None:
        if self.formal_bindings is None:
            if any(
                value is not None
                for value in (
                    self.corpus_registry_urls,
                    self.corpus_registry_hash,
                    self.discovery_root_urls,
                )
            ):
                raise ValueError(
                    "private corpus/root bindings require formal_bindings"
                )
            return
        if self.corpus_registry_urls is None or self.corpus_registry_hash is None:
            raise ValueError(
                "formal case requires corpus_registry_urls and corpus_registry_hash"
            )
        if self.discovery_root_urls is None:
            raise ValueError("formal case requires discovery_root_urls")
        if self.corpus_registry_hash != self.formal_bindings.corpus_registry_sha256:
            raise ValueError("top-level corpus_registry_hash disagrees with formal_bindings")
        if not set(self.discovery_root_urls).issubset(self.corpus_registry_urls):
            raise ValueError("discovery_root_urls must belong to complete corpus registry")
        expected = self.critical_support_source_ids
        if self.formal_bindings.critical_evidence_node_ids != expected:
            raise ValueError(
                "formal_bindings critical evidence IDs do not match the proof DAG"
            )
        if not set(expected).issubset(self.formal_bindings.reachable_node_ids):
            raise ValueError("formal_bindings do not make all critical evidence reachable")
        if self.formal_bindings.decidable_claims_sha256 != decidable_claims_sha256(self):
            raise ValueError(
                "formal_bindings decidable_claims_sha256 does not bind the "
                "case-authored negative claims"
            )
        if self.formal_bindings.proof_subgraph_sha256 != proof_subgraph_fingerprint(self):
            raise ValueError(
                "formal_bindings proof_subgraph_sha256 does not match the critical proof"
            )

    @property
    def slot_map(self) -> dict[str, SlotV3]:
        return {slot.slot_id: slot for slot in self.slots}

    @property
    def slots(self) -> list[SlotV3]:
        """Temporary Python alias for pre-redesign scorer code."""

        return self.evaluator_view.required_proof_steps

    @property
    def scenario(self) -> GeneratorViewV3:
        """Temporary Python alias; query code must read ``generator_view``."""

        return self.generator_view

    @property
    def evidence_source_map(self) -> dict[str, EvidenceSourceV3]:
        return {source.evidence_id: source for source in self.evidence_sources}

    @property
    def critical_support_source_ids(self) -> list[str]:
        """Frozen source nodes admissible for at least one vital evidence step."""

        return sorted(
            {
                source_id
                for slot in self.slots
                if slot.critical and slot.type == "evidence"
                for source_id in slot.support_source_ids
            }
        )

    @property
    def decision_slot(self) -> SlotV3:
        decisions = [slot for slot in self.slots if slot.type == "decision"]
        if len(decisions) != 1:
            raise CaseValidationError("case does not have exactly one decision slot")
        return decisions[0]

    def dependency_closure(self, slot_id: str) -> set[str]:
        if slot_id not in self.slot_map:
            raise KeyError(slot_id)
        closure: set[str] = set()

        def collect(current: str) -> None:
            if current in closure:
                return
            closure.add(current)
            for dependency in self.slot_map[current].requires:
                collect(dependency)

        collect(slot_id)
        return closure

    @property
    def minimum_reasoning_depth(self) -> int:
        """Longest number of dependency edges from evidence to the decision."""

        memo: dict[str, int] = {}

        def depth(slot_id: str) -> int:
            if slot_id in memo:
                return memo[slot_id]
            slot = self.slot_map[slot_id]
            if not slot.requires:
                value = 0
            else:
                value = 1 + max(depth(dependency) for dependency in slot.requires)
            memo[slot_id] = value
            return value

        return depth(self.decision_slot.slot_id)

    def _decision_survives_ablation(self, removed_slot_id: str) -> bool:
        available = set(self.slot_map) - {removed_slot_id}
        changed = True
        while changed:
            changed = False
            for slot_id in tuple(available):
                if any(dep not in available for dep in self.slot_map[slot_id].requires):
                    available.remove(slot_id)
                    changed = True
        return self.decision_slot.slot_id in available

    @property
    def cross_source_bridge_count(self) -> int:
        count = 0
        for slot in self.slots:
            if not slot.critical or slot.type != "bridge":
                continue
            evidence_steps = [
                self.slot_map[step_id]
                for step_id in self.dependency_closure(slot.slot_id)
                if self.slot_map[step_id].type == "evidence"
            ]
            role_sets = [
                {
                    source_role_family(
                        self.evidence_source_map[source_id].source_type
                    )
                    for source_id in step.support_source_ids
                    if source_role_family(
                        self.evidence_source_map[source_id].source_type
                    )
                    != "discovery"
                }
                for step in evidence_steps
            ]
            role_sets = [roles for roles in role_sets if roles]
            all_roles = set().union(*role_sets) if role_sets else set()
            one_role_can_cover_bridge = bool(role_sets) and bool(
                set.intersection(*role_sets)
            )
            if len(all_roles) >= 2 and not one_role_can_cover_bridge:
                count += 1
        return count

    def validation_report(self) -> dict[str, Any]:
        critical_evidence = [
            slot for slot in self.slots if slot.critical and slot.type == "evidence"
        ]
        return {
            "task_id": self.task_id,
            "valid": True,
            "formal_bindings_declared": self.formal_bindings is not None,
            "minimum_required_evidence_nodes": len(critical_evidence),
            "minimum_reasoning_depth": self.minimum_reasoning_depth,
            "required_research_subgoals": len(self.research_subgoals),
            "case_authored_decidable_negatives": len(self.decidable_claims),
            "decidable_claims_origin": "case_authored_decidable_negative",
            "proof_subgraph_sha256": proof_subgraph_fingerprint(self),
            "cross_source_bridges": self.cross_source_bridge_count,
            "single_page_sufficient": False,
            "critical_evidence_pages": sorted(
                {
                    self.evidence_source_map[source_id].source_url
                    for slot in critical_evidence
                    for source_id in slot.support_source_ids
                }
            ),
            "critical_ablation": {
                slot.slot_id: self.oracle.critical_node_ablation[
                    slot.slot_id
                ].model_dump(mode="json", exclude_none=True)
                for slot in critical_evidence
            },
            "decision_slot_id": self.decision_slot.slot_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaseSpecV3":
        if not isinstance(payload, Mapping):
            raise TypeError("case payload must be a mapping")
        return cls.model_validate(dict(payload))

    @classmethod
    def load(cls, path: str | Path) -> "CaseSpecV3":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def protocol_dict(self) -> dict[str, Any]:
        """Return the canonical dual-view protocol representation."""

        return self.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )

    def to_dict(
        self, *, include_internal_aliases: bool = True
    ) -> dict[str, Any]:
        """Return case data, optionally with temporary old-scorer aliases.

        Formal writers must call :meth:`protocol_dict`.  The default aliases
        keep current in-process scorers working during the schema migration and
        are never emitted by ``compile_case_v3.py``.
        """

        payload = self.protocol_dict()
        if (
            include_internal_aliases
            and self.scoring_semantics == SCORING_SEMANTICS
        ):
            payload["slots"] = [slot.legacy_dict() for slot in self.slots]
            payload["scenario"] = {
                "constraints": list(self.generator_view.constraints),
                "priority_order": list(self.generator_view.constraints),
                "candidate_actions": list(self.generator_view.candidate_actions),
                "context": self.generator_view.scenario,
                "objective": self.generator_view.target,
                "constraint_labels": {},
                "priority_labels": {},
                "candidate_labels": {},
            }
        return payload

    def canonical_json(self) -> str:
        return json.dumps(
            self.protocol_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def proof_subgraph_sha256(self) -> str:
        return proof_subgraph_fingerprint(self)


# Concise alias for callers and the dict-first scorer contract.
CaseSpec = CaseSpecV3


def validate_case(payload: Mapping[str, Any] | CaseSpecV3) -> CaseSpecV3:
    """Validate and return a canonical case without fabricating defaults."""

    if isinstance(payload, CaseSpecV3):
        return payload
    return CaseSpecV3.from_dict(payload)


def validate_legacy_case(
    payload: Mapping[str, Any] | CaseSpecV3,
) -> CaseSpecV3:
    """Validate a replay-only ``verified_slots_v1`` case explicitly."""

    case = validate_case(payload)
    if case.scoring_semantics != SCORING_SEMANTICS:
        raise CaseValidationError(
            "validate_legacy_case only accepts verified_slots_v1 artifacts"
        )
    return case


def validate_proof_step_case(
    payload: Mapping[str, Any] | CaseSpecV3,
) -> CaseSpecV3:
    """Validate the new formal dual-view proof-step protocol explicitly."""

    case = validate_case(payload)
    if case.scoring_semantics != PROOF_STEP_SCORING_SEMANTICS:
        raise CaseValidationError(
            "formal dual-view path requires scoring_semantics=proof_steps_v1"
        )
    return case


def decidable_claims_sha256(case: CaseSpecV3 | Mapping[str, Any]) -> str:
    """Hash the exact case-authored negative matcher set, independent of order."""

    spec = case if isinstance(case, CaseSpecV3) else validate_case(case)
    rows = [
        claim.model_dump(mode="json", exclude_none=True)
        for claim in spec.decidable_claims
    ]
    rows.sort(key=lambda row: str(row["claim_id"]))
    return _canonical_sha256(rows)


def proof_subgraph_fingerprint(case: CaseSpecV3 | Mapping[str, Any]) -> str:
    """Hash critical evidence identity and proof topology while ignoring slot IDs.

    Scenario wording, slot/rule identifiers, candidate labels, and query prose do
    not enter this fingerprint.  Exact typed evidence identity and the recursive
    evidence/bridge/decision topology do, so paraphrases over the same proof
    subgraph collide and must share a cluster.
    """

    spec = case if isinstance(case, CaseSpecV3) else validate_case(case)
    memo: dict[str, Any] = {}

    def signature(slot_id: str) -> Any:
        if slot_id in memo:
            return memo[slot_id]
        slot = spec.slot_map[slot_id]
        if slot.type == "evidence":
            assert slot.claim_id is not None
            source_identities: list[dict[str, Any]] = []
            for source_id in slot.support_source_ids:
                source = spec.evidence_source_map[source_id]
                spans = [
                    {
                        "source_url": span.source_url,
                        "start": span.start,
                        "end": span.end,
                        "sha256": span.sha256,
                        "support_type": span.support_type,
                    }
                    for span in source.support_spans
                ]
                spans.sort(
                    key=lambda row: json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                source_identities.append(
                    {
                        "node_type": source.node_type,
                        "subject": source.subject,
                        "predicate": source.predicate,
                        "object": source.object,
                        "source_url": source.source_url,
                        "source_type": source.source_type,
                        "content_sha256": source.content_sha256,
                        "corpus_snapshot": source.corpus_snapshot,
                        "support_spans": spans,
                    }
                )
            source_identities.sort(
                key=lambda row: json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            )
            value: Any = {
                "type": "evidence",
                "claim": slot.claim_id,
                "admissible_source_identities": source_identities,
            }
        else:
            dependencies = [signature(dependency) for dependency in slot.requires]
            dependencies.sort(
                key=lambda item: json.dumps(
                    item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            )
            value = {"type": slot.type, "requires": dependencies}
        memo[slot_id] = value
        return value

    return _canonical_sha256(signature(spec.decision_slot.slot_id))


def normalize_catalog_records(payload: Any) -> list[dict[str, Any]]:
    """Extract evidence-node records from common JSON/JSONL catalog shapes.

    This function only normalizes containers.  It does not invent missing node
    fields or assert corpus membership.
    """

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, Mapping):
        for key in ("nodes", "evidence_nodes", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        else:
            # A mapping keyed by evidence_id is also accepted.
            if payload and all(isinstance(value, Mapping) for value in payload.values()):
                records = []
                for key, value in payload.items():
                    row = dict(value)
                    row.setdefault("evidence_id", str(key))
                    records.append(row)
            else:
                raise CaseValidationError("catalog JSON has no evidence-node records")
    else:
        raise CaseValidationError("evidence catalog must contain JSON objects")
    if not all(isinstance(record, Mapping) for record in records):
        raise CaseValidationError("every evidence catalog record must be an object")
    return [dict(record) for record in records]


def load_catalog_records(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON file, JSONL file, or evidence-graph directory."""

    source = Path(path)
    if source.is_dir():
        node_path = source / "nodes.jsonl"
        if not node_path.is_file():
            raise CaseValidationError(f"catalog directory has no nodes.jsonl: {source}")
        return load_catalog_records(node_path)
    if not source.is_file():
        raise CaseValidationError(f"evidence catalog does not exist: {source}")
    if source.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise CaseValidationError(
                    f"catalog line {line_number} is not a JSON object"
                )
            records.append(dict(value))
        return records
    return normalize_catalog_records(json.loads(source.read_text(encoding="utf-8")))


def _catalog_record_value(record: Mapping[str, Any], key: str) -> Any:
    if key == "verifier":
        value = record.get(key)
        if isinstance(value, str):
            return {"kind": value}
        if isinstance(value, Mapping):
            return {name: item for name, item in value.items() if item is not None}
        return value
    return record.get(key)


def validate_catalog_bindings(
    case: CaseSpecV3,
    catalog_records: Iterable[Mapping[str, Any]],
    *,
    support_span_records: Iterable[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Fail closed unless every case evidence binding exactly matches catalog.

    The returned URL list is the full frozen catalog URL membership set and can
    be stored privately in compiled case gold for report-level fabricated URL
    detection.  Duplicate evidence IDs, unknown IDs, snapshot drift, and any
    binding mismatch are rejected.
    """

    records = [dict(record) for record in catalog_records]
    ids = [str(record.get("evidence_id") or "") for record in records]
    if any(not value for value in ids):
        raise CaseValidationError("catalog evidence records require evidence_id")
    _require_unique(ids, "catalog evidence IDs")
    by_id = {str(record["evidence_id"]): record for record in records}

    span_by_evidence: dict[str, list[dict[str, Any]]] = {}
    if support_span_records is not None:
        for raw_span in support_span_records:
            span = dict(raw_span)
            evidence_id = str(span.get("evidence_id") or "")
            if not evidence_id:
                raise CaseValidationError("catalog support spans require evidence_id")
            span_by_evidence.setdefault(evidence_id, []).append(span)

    compare_fields = (
        "node_type",
        "subject",
        "predicate",
        "object",
        "source_url",
        "source_type",
        "content_sha256",
        "corpus_snapshot",
        "search_snippet_support",
        "body_support",
        "verifier",
    )
    for binding in case.evidence_sources:
        record = by_id.get(binding.evidence_id)
        if record is None:
            raise CaseValidationError(
                f"case evidence ID is absent from frozen catalog: {binding.evidence_id}"
            )
        expected = binding.model_dump(mode="json", exclude_none=False)
        expected["verifier"] = {
            name: item for name, item in expected["verifier"].items() if item is not None
        }
        for field_name in compare_fields:
            actual_value = _catalog_record_value(record, field_name)
            if actual_value != expected[field_name]:
                raise CaseValidationError(
                    f"catalog mismatch for {binding.evidence_id}.{field_name}: "
                    f"case={expected[field_name]!r}, catalog={actual_value!r}"
                )
        catalog_spans = span_by_evidence.get(binding.evidence_id)
        if catalog_spans is None:
            raw_spans = record.get("support_spans")
            catalog_spans = [dict(span) for span in raw_spans] if isinstance(raw_spans, list) else []
        if not catalog_spans:
            raise CaseValidationError(
                f"catalog has no support spans for evidence {binding.evidence_id}"
            )
        expected_spans = binding.model_dump(mode="json")["support_spans"]

        def span_key(span: Mapping[str, Any]) -> tuple[Any, ...]:
            return (
                span.get("support_span_id"),
                span.get("evidence_id"),
                span.get("source_url"),
                span.get("start"),
                span.get("end"),
                span.get("sha256"),
                span.get("support_type"),
            )

        if sorted(map(span_key, catalog_spans)) != sorted(map(span_key, expected_spans)):
            raise CaseValidationError(
                f"catalog support spans do not exactly match case evidence {binding.evidence_id}"
            )

    urls: list[str] = []
    for record in records:
        source_url = record.get("source_url")
        corpus_snapshot = record.get("corpus_snapshot")
        content_sha256 = record.get("content_sha256")
        if not isinstance(source_url, str):
            raise CaseValidationError(f"catalog evidence {record['evidence_id']} lacks source_url")
        _validate_absolute_http_url(source_url)
        if corpus_snapshot != case.corpus_snapshot:
            # A catalog may not silently mix snapshots for formal compilation.
            raise CaseValidationError(
                f"catalog evidence {record['evidence_id']} belongs to snapshot "
                f"{corpus_snapshot!r}, expected {case.corpus_snapshot!r}"
            )
        if not isinstance(content_sha256, str) or not _SHA256_RE.fullmatch(content_sha256):
            raise CaseValidationError(
                f"catalog evidence {record['evidence_id']} lacks a valid content_sha256"
            )
        urls.append(source_url)
    return sorted(set(urls))


__all__ = [
    "CASE_SCHEMA",
    "DIAGNOSTIC_METRIC",
    "EVIDENCE_GRAPH_VERSION",
    "HEADLINE_METRICS",
    "OBSERVATION_SEMANTICS",
    "PARTIAL_COMPLETION_RATE_METRIC",
    "PROOF_STEP_SCORING_SEMANTICS",
    "PROOF_STEP_DIAGNOSTIC_METRICS",
    "PROOF_STEP_HEADLINE_METRICS",
    "SCORING_SEMANTICS",
    "SOURCE_ROLE_FAMILIES",
    "TASK_VERSION",
    "TASK_SOLVE_RATE_METRIC",
    "FULL_PASS_RATE_METRIC",
    "VERIFIED_RESEARCH_COMPLETION_METRIC",
    "QUERY_MAX_GENERATION_ATTEMPTS",
    "SUPPORTED_MOTIFS",
    "AcceptableSupportV3",
    "CaseSpec",
    "CaseSpecV3",
    "CaseValidationError",
    "BridgeRuleDefinitionV3",
    "ConditionalDecisionMatcherV3",
    "CriticalNodeAblationV3",
    "DecisionRuleDefinitionV3",
    "ConditionalConclusionV3",
    "DecidableClaimV3",
    "EvidenceSourceV3",
    "EvaluatorViewV3",
    "FinalAnswerContractV3",
    "FormalBindingsV3",
    "GeneratorViewV3",
    "QueryRequirementV3",
    "QueryRenderingV3",
    "RequiredProofStepV3",
    "ResearchSubgoalV3",
    "RuleDefinitionV3",
    "SlotV3",
    "TextMatcherV3",
    "decidable_claims_sha256",
    "load_catalog_records",
    "normalize_catalog_records",
    "proof_subgraph_fingerprint",
    "source_role_family",
    "validate_case",
    "validate_legacy_case",
    "validate_proof_step_case",
    "validate_catalog_bindings",
]
