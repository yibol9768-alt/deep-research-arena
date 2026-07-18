"""Dual-view, leak-resistant query rendering for DRA v3 cases.

The renderer has one case-specific input boundary: ``GeneratorView``.  It may
also consume exactly three separately sanitized development examples, each of
which contains only ``GeneratorView`` and ``HumanWrittenQuery``.  Evaluator
propositions, proof steps, evidence, URLs, answer conditions, and scorer-shaped
counts never enter the generation prompt or the public task.

Query publication is deliberately two-stage.  Deterministic RulePass is
computed here.  Blind semantic alignment is a human/reviewer record whose
schema contains only hashes and four judgments; this module never fabricates a
passing blind review.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.eval.case_schema_v3 import (
    QUERY_MAX_GENERATION_ATTEMPTS,
    SCORING_SEMANTICS,
    CaseSpecV3,
    ConditionalConclusionV3,
    GeneratorViewV3,
    validate_case,
)


QUERY_CONTRACT_SCHEMA = "generator_view_query_contract_v1"
RENDERED_TASK_SCHEMA = "rendered_task_v3"
FEW_SHOT_SCHEMA = "sanitized_generator_query_example_v1"
GENERATION_PROMPT_SCHEMA = "generator_view_query_prompt_v1"
HARD_RULE_RECORD_SCHEMA = "query_hard_rule_pass_v1"
BLIND_REVIEW_SCHEMA = "blind_semantic_alignment_review_v1"
BLIND_REVIEW_PACKET_SCHEMA = "blind_semantic_alignment_packet_v1"
QUERY_ACCEPTANCE_SCHEMA = "query_acceptance_record_v1"

# Kept as an import compatibility constant.  It is no longer injected into a
# formal query because it is not part of GeneratorView.
EVIDENCE_CITATION_CONTRACT = (
    "For every factual evidence claim used to support the conclusion, place a "
    "citation to its specific supporting source in the same paragraph."
)

_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>()]+")
_SCORER_WORD_RE = re.compile(
    r"(?i)\b(?:step[_ -]?id|required[_ -]?proof[_ -]?steps?|"
    r"required[_ -]?step[_ -]?count|source[_ -]?url|gold[_ -]?answer|"
    r"slot[_ -]?id|scorer|proof[_ -]?of[_ -]?fetch|"
    r"verified[_ -]?(?:f1|recall|precision)|task[_ -]?solve[_ -]?rate)\b"
)
_QUOTA_PATTERNS = (
    re.compile(
        r"(?i)(?:at\s+least|minimum(?:\s+of)?|no\s+fewer\s+than|>=)\s*\d+\s*"
        r"(?:required\s+)?(?:steps?|sources?|citations?|urls?|pages?|"
        r"search(?:es)?|fetch(?:es)?|references?|words?)\b"
    ),
    re.compile(
        r"(?i)\b(?:cite|visit|browse|open|fetch|search|complete)\s+"
        r"(?:at\s+least\s+|>=\s*)?\d+\s*"
        r"(?:distinct\s+)?(?:steps?|sources?|citations?|urls?|pages?|"
        r"times?|results?)\b"
    ),
)
_EXPLICIT_ANSWER_RE = re.compile(
    r"(?i)\b(?:gold|correct|secret)\s+answer\b|\bthe\s+answer\s+is\b"
)
_COVERAGE_SEPARATOR_RE = re.compile(r"[^A-Za-z0-9]+")


class QueryRenderError(ValueError):
    """Base error for an unsafe or unrenderable v3 query."""


class QueryLeakError(QueryRenderError):
    """Raised when query text discloses private evaluator/scorer material."""


class QueryAlignmentError(QueryRenderError):
    """Raised when rendered constraints differ from GeneratorView."""


class QueryRetryRequiredError(QueryRenderError):
    """Raised after a failed attempt below the frozen retry ceiling."""


class QueryCaseDiscardedError(QueryRenderError):
    """Raised when a failed final attempt permanently discards the case."""


class _StrictRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class LeakFinding(_StrictRecord):
    kind: Literal[
        "step_id",
        "source_url",
        "gold_answer",
        "required_step_count",
        "scorer_term",
    ]
    value: str

    def to_dict(self) -> dict[str, str]:
        return self.model_dump(mode="json")


class HardRuleChecksV3(_StrictRecord):
    constraint_coverage: bool
    option_coverage: bool
    no_url: bool
    no_scorer_terms: bool
    no_answer_leak: bool

    @property
    def passed(self) -> bool:
        return all(self.model_dump().values())


class HardRulePassRecordV3(_StrictRecord):
    record_schema: Literal["query_hard_rule_pass_v1"] = Field(
        default=HARD_RULE_RECORD_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    task_id: str
    attempt: int = Field(ge=1, le=QUERY_MAX_GENERATION_ATTEMPTS)
    max_generation_attempts: Literal[3] = QUERY_MAX_GENERATION_ATTEMPTS
    generator_view_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: HardRuleChecksV3
    missing_constraints: list[str]
    missing_options: list[str]
    findings: list[LeakFinding]
    passed: bool

    @model_validator(mode="after")
    def validate_pass_flag(self) -> "HardRulePassRecordV3":
        expected = (
            self.checks.passed
            and not self.missing_constraints
            and not self.missing_options
            and not self.findings
        )
        if self.passed != expected:
            raise ValueError("hard-rule passed flag disagrees with checks/findings")
        return self


class BlindSemanticReviewRecordV3(_StrictRecord):
    """A manually supplied blind judgment; no private-gold fields are legal."""

    record_schema: Literal["blind_semantic_alignment_review_v1"] = Field(
        default=BLIND_REVIEW_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    task_id: str
    attempt: int = Field(ge=1, le=QUERY_MAX_GENERATION_ATTEMPTS)
    max_generation_attempts: Literal[3] = QUERY_MAX_GENERATION_ATTEMPTS
    generator_view_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str = Field(min_length=1)
    faithful: bool
    natural: bool
    closed_environment_answerable: bool
    requires_multi_branch_research: bool
    passed: bool

    @field_validator("reviewer_id")
    @classmethod
    def validate_reviewer_id(cls, value: str) -> str:
        if value.strip() != value or not value.strip():
            raise ValueError("reviewer_id must be non-empty and trimmed")
        return value

    @model_validator(mode="after")
    def validate_pass_flag(self) -> "BlindSemanticReviewRecordV3":
        expected = all(
            (
                self.faithful,
                self.natural,
                self.closed_environment_answerable,
                self.requires_multi_branch_research,
            )
        )
        if self.passed != expected:
            raise ValueError("blind-review passed flag disagrees with judgments")
        return self


class QueryAcceptanceRecordV3(_StrictRecord):
    record_schema: Literal["query_acceptance_record_v1"] = Field(
        default=QUERY_ACCEPTANCE_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    task_id: str
    attempt: int = Field(ge=1, le=QUERY_MAX_GENERATION_ATTEMPTS)
    max_generation_attempts: Literal[3] = QUERY_MAX_GENERATION_ATTEMPTS
    hard_rules: HardRulePassRecordV3
    blind_semantic_alignment: BlindSemanticReviewRecordV3
    disposition: Literal["accepted", "retry", "discarded"]

    @model_validator(mode="after")
    def validate_disposition(self) -> "QueryAcceptanceRecordV3":
        if self.hard_rules.task_id != self.task_id or (
            self.blind_semantic_alignment.task_id != self.task_id
        ):
            raise ValueError("query acceptance records disagree on task_id")
        if self.hard_rules.attempt != self.attempt or (
            self.blind_semantic_alignment.attempt != self.attempt
        ):
            raise ValueError("query acceptance records disagree on attempt")
        if (
            self.hard_rules.generator_view_sha256
            != self.blind_semantic_alignment.generator_view_sha256
            or self.hard_rules.query_sha256
            != self.blind_semantic_alignment.query_sha256
        ):
            raise ValueError("hard and blind review records bind different inputs")
        passed = self.hard_rules.passed and self.blind_semantic_alignment.passed
        expected = (
            "accepted"
            if passed
            else (
                "discarded"
                if self.attempt == QUERY_MAX_GENERATION_ATTEMPTS
                else "retry"
            )
        )
        if self.disposition != expected:
            raise ValueError(
                f"query disposition must be {expected!r} for this attempt"
            )
        return self


class SanitizedFewShotExampleV3(_StrictRecord):
    """The only legal few-shot row: no IDs or private annotation alongside it."""

    generator_view: GeneratorViewV3
    human_written_query: str = Field(min_length=1)

    @field_validator("human_written_query")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        if value.strip() != value or not value.strip():
            raise ValueError("HumanWrittenQuery must be non-empty and trimmed")
        if _URL_RE.search(value):
            raise ValueError("sanitized few-shot query must not contain a URL")
        if _SCORER_WORD_RE.search(value) or any(
            pattern.search(value) for pattern in _QUOTA_PATTERNS
        ):
            raise ValueError("sanitized few-shot query contains scorer terms")
        if _EXPLICIT_ANSWER_RE.search(value):
            raise ValueError("sanitized few-shot query contains an answer leak")
        return value

    @model_validator(mode="after")
    def validate_coverage(self) -> "SanitizedFewShotExampleV3":
        missing_constraints = _missing_public_items(
            self.generator_view.constraints, self.human_written_query
        )
        missing_options = _missing_public_items(
            self.generator_view.candidate_actions, self.human_written_query
        )
        if missing_constraints or missing_options:
            raise ValueError(
                "sanitized few-shot query does not cover its GeneratorView; "
                f"constraints={missing_constraints}, options={missing_options}"
            )
        return self


def _case(value: CaseSpecV3 | Mapping[str, Any]) -> CaseSpecV3:
    return validate_case(value)


def _canonical_sha256(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def query_sha256(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def generator_view_sha256(
    value: GeneratorViewV3 | Mapping[str, Any],
) -> str:
    view = (
        value
        if isinstance(value, GeneratorViewV3)
        else GeneratorViewV3.model_validate(dict(value))
    )
    return _canonical_sha256(view.model_dump(mode="json"))


def _display(identifier: str) -> str:
    if "\n" in identifier or "\r" in identifier:
        raise QueryRenderError("GeneratorView identifiers must be single-line")
    return " ".join(identifier.replace("_", " ").split())


def _coverage_normalize(value: str) -> str:
    """Normalize public identifiers and prose without changing their tokens.

    GeneratorView identifiers use underscores where a natural query may use
    punctuation.  In particular, a constraint token such as ``51_61`` should
    be covered by the natural monetary spelling ``$51.61``; requiring the
    author to write ``51 61`` merely to satisfy RulePass damages naturalness.
    """

    return " ".join(_COVERAGE_SEPARATOR_RE.sub(" ", value).casefold().split())


def _public_item_present(item: str, text: str) -> bool:
    variants = {item, _display(item)}
    for variant in variants:
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(variant)}(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        ):
            return True
    normalized_item = _coverage_normalize(_display(item))
    normalized_text = _coverage_normalize(text)
    if not normalized_item:
        return False
    return re.search(
        rf"(?<![a-z0-9]){re.escape(normalized_item)}(?![a-z0-9])",
        normalized_text,
    ) is not None


def _missing_public_items(items: Sequence[str], text: str) -> list[str]:
    return [item for item in items if not _public_item_present(item, text)]


def canonical_query_contract(
    case: CaseSpecV3 | Mapping[str, Any],
) -> dict[str, Any]:
    """Project the exact public contract from GeneratorView only."""

    spec = _case(case)
    if spec.scoring_semantics == SCORING_SEMANTICS:
        # Replay adapter for frozen verified_slots_v1 artifacts.  New formal
        # proof-step cases never enter this branch.
        return {
            "schema": "query_constraint_contract_v1",
            "context": spec.generator_view.scenario,
            "objective": spec.generator_view.target,
            "constraints": [
                {"id": item, "text": _display(item)}
                for item in spec.generator_view.constraints
            ],
            "priority_order": [
                {"rank": rank, "id": item, "text": _display(item)}
                for rank, item in enumerate(spec.generator_view.constraints, 1)
            ],
            "candidate_actions": [
                {"id": item, "text": _display(item)}
                for item in spec.generator_view.candidate_actions
            ],
            "research_subgoals": [
                " ".join(item.description.split())
                for item in spec.research_subgoals
            ],
            "requirements": [
                " ".join(item.text.split()) for item in spec.query_requirements
            ],
            "evidence_citation_contract": EVIDENCE_CITATION_CONTRACT,
        }
    return {
        "schema": QUERY_CONTRACT_SCHEMA,
        "generator_view": spec.generator_view.model_dump(mode="json"),
    }


def query_contract_sha256(contract: Mapping[str, Any]) -> str:
    return _canonical_sha256(dict(contract))


def _contains_token(text: str, token: str) -> bool:
    if not token:
        return False
    return re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _collect_matcher_phrases(value: Any, output: set[str]) -> None:
    if isinstance(value, BaseModel):
        _collect_matcher_phrases(
            value.model_dump(mode="json", exclude_none=True), output
        )
    elif isinstance(value, Mapping):
        for key, nested in value.items():
            if key in {
                "accepted_phrases",
                "accepted_regexes",
                "accepted_aliases",
                "when",
                "required_tradeoffs",
            }:
                if isinstance(nested, str):
                    output.add(nested)
                elif isinstance(nested, Sequence):
                    output.update(str(item) for item in nested)
            else:
                _collect_matcher_phrases(nested, output)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _collect_matcher_phrases(nested, output)


def detect_query_leaks(
    case: CaseSpecV3 | Mapping[str, Any], text: str
) -> list[LeakFinding]:
    """Return deterministic evaluator, URL, answer, and scorer leaks."""

    spec = _case(case)
    findings: list[LeakFinding] = []
    for match in _URL_RE.finditer(text):
        findings.append(
            LeakFinding(
                kind="source_url", value=match.group(0).rstrip(".,;")
            )
        )

    internal_ids = [step.slot_id for step in spec.slots]
    internal_ids.extend(spec.evaluator_view.propositions)
    internal_ids.extend(source.evidence_id for source in spec.evidence_sources)
    internal_ids.extend(
        requirement.requirement_id for requirement in spec.query_requirements
    )
    internal_ids.extend(subgoal.subgoal_id for subgoal in spec.research_subgoals)
    internal_ids.extend(claim.claim_id for claim in spec.decidable_claims)
    internal_ids.extend(
        step.rule for step in spec.slots if step.rule is not None
    )
    public_ids = set(
        spec.generator_view.constraints + spec.generator_view.candidate_actions
    )
    for identifier in sorted(set(internal_ids) - public_ids, key=lambda x: (-len(x), x)):
        if _contains_token(text, identifier):
            findings.append(LeakFinding(kind="step_id", value=identifier))

    private_phrases: set[str] = set()
    _collect_matcher_phrases(spec.rule_definitions, private_phrases)
    _collect_matcher_phrases(spec.decidable_claims, private_phrases)
    for conclusion in spec.acceptable_conclusions:
        if isinstance(conclusion, ConditionalConclusionV3):
            private_phrases.add(conclusion.when)
            private_phrases.update(conclusion.required_tradeoffs)
    public_variants = {
        value.casefold()
        for item in public_ids
        for value in (item, _display(item))
    }
    folded = text.casefold()
    for phrase in sorted(private_phrases, key=lambda x: (-len(x), x)):
        normalized = phrase.casefold().strip()
        if not normalized or normalized in public_variants:
            continue
        # Regex matchers are private too.  Treat them as literal only here; a
        # renderer must never evaluate a gold regex against public prose.
        if normalized in folded:
            findings.append(LeakFinding(kind="gold_answer", value=phrase))

    scorer_match = _SCORER_WORD_RE.search(text)
    if scorer_match:
        findings.append(
            LeakFinding(kind="scorer_term", value=scorer_match.group(0))
        )
    for pattern in _QUOTA_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                LeakFinding(
                    kind="required_step_count", value=match.group(0)
                )
            )
    if _EXPLICIT_ANSWER_RE.search(text):
        match = _EXPLICIT_ANSWER_RE.search(text)
        assert match is not None
        findings.append(LeakFinding(kind="gold_answer", value=match.group(0)))

    for source in spec.evidence_sources:
        if source.source_url in text and not any(
            item.kind == "source_url" and item.value == source.source_url
            for item in findings
        ):
            findings.append(
                LeakFinding(kind="source_url", value=source.source_url)
            )

    unique: list[LeakFinding] = []
    seen: set[tuple[str, str]] = set()
    for finding in findings:
        key = (finding.kind, finding.value.casefold())
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def assert_no_query_leaks(
    case: CaseSpecV3 | Mapping[str, Any], text: str
) -> None:
    findings = detect_query_leaks(case, text)
    if findings:
        details = ", ".join(
            f"{item.kind}={item.value!r}" for item in findings
        )
        raise QueryLeakError(
            f"rendered query contains forbidden private material: {details}"
        )


def render_query(case: CaseSpecV3 | Mapping[str, Any]) -> str:
    """Render the deterministic query using GeneratorView and no private data."""

    spec = _case(case)
    view = spec.generator_view
    if spec.scoring_semantics == SCORING_SEMANTICS:
        contract = canonical_query_contract(spec)
        lines = [contract["context"], "", "Objective:", contract["objective"], ""]
        lines.append("Constraints:")
        lines.extend(f"- {item['text']}" for item in contract["constraints"])
        lines.extend(("", "Decision priorities (highest first):"))
        lines.extend(
            f"{item['rank']}. {item['text']}"
            for item in contract["priority_order"]
        )
        lines.extend(("", "Candidate actions to compare:"))
        lines.extend(f"- {item['text']}" for item in contract["candidate_actions"])
        lines.extend(("", "Required research subgoals:"))
        lines.extend(f"- {item}" for item in contract["research_subgoals"])
        lines.extend(("", "Required deliverables:"))
        lines.extend(f"- {item}" for item in contract["requirements"])
        lines.extend(("", "Evidence citation requirement:"))
        lines.append(f"- {contract['evidence_citation_contract']}")
        query = "\n".join(str(item) for item in lines).strip()
        assert_no_query_leaks(spec, query)
        return query
    lines = [
        "Scenario:",
        view.scenario,
        "",
        "Constraints:",
        *(f"- {_display(item)}" for item in view.constraints),
        "",
        "Candidate actions to compare:",
        *(f"- {_display(item)}" for item in view.candidate_actions),
        "",
        "Research target:",
        view.target,
    ]
    query = "\n".join(lines).strip()
    assert_no_query_leaks(spec, query)
    hard = build_hard_rule_pass_record(spec, query, attempt=1)
    if not hard.passed:
        raise QueryAlignmentError("canonical query failed deterministic RulePass")
    return query


def validate_query_candidate(
    case: CaseSpecV3 | Mapping[str, Any],
    query: str,
    *,
    attempt: int,
) -> str:
    """Validate one externally rendered GeneratorView-only query candidate.

    The deterministic renderer remains the fallback, but formal publication may
    bind a natural-language candidate produced from the sanitized generation
    prompt.  The candidate must be byte-stable, cover every public constraint
    and option, and pass the same leak checks before it can enter blind review.
    """

    spec = _case(case)
    if not isinstance(query, str) or not query:
        raise QueryRenderError("query candidate must be a non-empty string")
    if query.strip() != query:
        raise QueryRenderError(
            "query candidate must be trimmed before hashing and review"
        )
    hard = build_hard_rule_pass_record(spec, query, attempt=attempt)
    if not hard.passed:
        raise QueryAlignmentError(
            "query candidate failed deterministic RulePass: "
            + json.dumps(
                hard.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return query


def _selected_query(
    case: CaseSpecV3,
    *,
    query_text: str | None,
    attempt: int,
) -> str:
    if query_text is None:
        return render_query(case)
    return validate_query_candidate(case, query_text, attempt=attempt)


def build_hard_rule_pass_record(
    case: CaseSpecV3 | Mapping[str, Any],
    query: str,
    *,
    attempt: int,
) -> HardRulePassRecordV3:
    """Compute the frozen RulePass contract for one candidate query."""

    spec = _case(case)
    missing_constraints = _missing_public_items(
        spec.generator_view.constraints, query
    )
    missing_options = _missing_public_items(
        spec.generator_view.candidate_actions, query
    )
    findings = detect_query_leaks(spec, query)
    checks = HardRuleChecksV3(
        constraint_coverage=not missing_constraints,
        option_coverage=not missing_options,
        no_url=not any(item.kind == "source_url" for item in findings),
        no_scorer_terms=not any(
            item.kind in {"scorer_term", "required_step_count"}
            for item in findings
        ),
        no_answer_leak=not any(
            item.kind in {"gold_answer", "step_id"} for item in findings
        ),
    )
    return HardRulePassRecordV3(
        task_id=spec.task_id,
        attempt=attempt,
        generator_view_sha256=generator_view_sha256(spec.generator_view),
        query_sha256=query_sha256(query),
        checks=checks,
        missing_constraints=missing_constraints,
        missing_options=missing_options,
        findings=findings,
        passed=checks.passed and not findings,
    )


def validate_blind_semantic_review(
    case: CaseSpecV3 | Mapping[str, Any],
    query: str,
    record: BlindSemanticReviewRecordV3 | Mapping[str, Any],
) -> BlindSemanticReviewRecordV3:
    """Validate that a manual blind record binds exactly this public input."""

    spec = _case(case)
    review = (
        record
        if isinstance(record, BlindSemanticReviewRecordV3)
        else BlindSemanticReviewRecordV3.model_validate(dict(record))
    )
    if review.task_id != spec.task_id:
        raise QueryAlignmentError("blind review is for a different task_id")
    if review.generator_view_sha256 != generator_view_sha256(spec.generator_view):
        raise QueryAlignmentError("blind review binds a different GeneratorView")
    if review.query_sha256 != query_sha256(query):
        raise QueryAlignmentError("blind review binds a different query")
    return review


def build_query_acceptance_record(
    case: CaseSpecV3 | Mapping[str, Any],
    query: str,
    blind_review: BlindSemanticReviewRecordV3 | Mapping[str, Any],
) -> QueryAcceptanceRecordV3:
    """Combine RulePass with a real blind review and freeze retry/discard state."""

    review = validate_blind_semantic_review(case, query, blind_review)
    hard = build_hard_rule_pass_record(case, query, attempt=review.attempt)
    passed = hard.passed and review.passed
    disposition: Literal["accepted", "retry", "discarded"] = (
        "accepted"
        if passed
        else (
            "discarded"
            if review.attempt == QUERY_MAX_GENERATION_ATTEMPTS
            else "retry"
        )
    )
    return QueryAcceptanceRecordV3(
        task_id=hard.task_id,
        attempt=review.attempt,
        hard_rules=hard,
        blind_semantic_alignment=review,
        disposition=disposition,
    )


def assert_query_accepted(record: QueryAcceptanceRecordV3) -> None:
    if record.disposition == "accepted":
        return
    if record.disposition == "discarded":
        raise QueryCaseDiscardedError(
            "query failed the frozen final attempt; discard the CaseSpec"
        )
    raise QueryRetryRequiredError(
        "query failed validation; regenerate without silently editing the case"
    )


def build_blind_review_packet(
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    attempt: int,
    query_text: str | None = None,
) -> dict[str, Any]:
    """Produce the safe packet a human blind reviewer is allowed to see."""

    spec = _case(case)
    query = _selected_query(spec, query_text=query_text, attempt=attempt)
    hard = build_hard_rule_pass_record(spec, query, attempt=attempt)
    return {
        "schema": BLIND_REVIEW_PACKET_SCHEMA,
        "task_id": spec.task_id,
        "attempt": attempt,
        "max_generation_attempts": QUERY_MAX_GENERATION_ATTEMPTS,
        "generator_view": spec.generator_view.model_dump(mode="json"),
        "query": query,
        "generator_view_sha256": hard.generator_view_sha256,
        "query_sha256": hard.query_sha256,
        "hard_rules": hard.model_dump(mode="json"),
    }


def validate_sanitized_few_shot_examples(
    examples: Sequence[SanitizedFewShotExampleV3 | Mapping[str, Any]],
) -> list[SanitizedFewShotExampleV3]:
    """Validate the frozen three-example dev-14 subset shape."""

    if len(examples) != 3:
        raise QueryRenderError("formal query rendering requires exactly 3 few-shot examples")
    validated = [
        item
        if isinstance(item, SanitizedFewShotExampleV3)
        else SanitizedFewShotExampleV3.model_validate(dict(item))
        for item in examples
    ]
    view_hashes = [generator_view_sha256(item.generator_view) for item in validated]
    query_hashes = [query_sha256(item.human_written_query) for item in validated]
    if len(set(view_hashes)) != 3 or len(set(query_hashes)) != 3:
        raise QueryRenderError("few-shot examples must be three distinct structures")
    return validated


def build_query_generation_prompt(
    case: CaseSpecV3 | Mapping[str, Any],
    examples: Sequence[SanitizedFewShotExampleV3 | Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the complete renderer input, proving that no evaluator data enters."""

    spec = _case(case)
    rows = validate_sanitized_few_shot_examples(examples)
    return {
        "schema": GENERATION_PROMPT_SCHEMA,
        "few_shot_subset": spec.query_rendering.few_shot_subset,
        "instruction": (
            "Write a natural research query faithful to every scenario constraint, "
            "candidate action, and target. Add no facts, answers, URLs, proof-step "
            "language, or numeric research quotas."
        ),
        "examples": [
            {
                "generator_view": row.generator_view.model_dump(mode="json"),
                "human_written_query": row.human_written_query,
            }
            for row in rows
        ],
        "generator_view": spec.generator_view.model_dump(mode="json"),
    }


def render_task(
    case: CaseSpecV3 | Mapping[str, Any],
    *,
    blind_review_record: BlindSemanticReviewRecordV3 | Mapping[str, Any] | None = None,
    attempt: int = 1,
    query_text: str | None = None,
) -> dict[str, Any]:
    """Return a public task and its accepted or pending query-validation state."""

    spec = _case(case)
    contract = canonical_query_contract(spec)
    query = _selected_query(spec, query_text=query_text, attempt=attempt)
    hard = build_hard_rule_pass_record(spec, query, attempt=attempt)
    if blind_review_record is None:
        validation: dict[str, Any] = {
            "schema": "query_acceptance_pending_v1",
            "status": "pending_blind_review",
            "attempt": attempt,
            "max_generation_attempts": QUERY_MAX_GENERATION_ATTEMPTS,
            "hard_rules": hard.model_dump(mode="json"),
        }
    else:
        acceptance = build_query_acceptance_record(
            spec, query, blind_review_record
        )
        assert_query_accepted(acceptance)
        validation = acceptance.model_dump(mode="json")

    task = {
        "rendered_task_schema": RENDERED_TASK_SCHEMA,
        "task_id": spec.task_id,
        "task_version": spec.task_version,
        "case_schema": spec.case_schema,
        "evidence_graph": spec.evidence_graph,
        "observation_semantics": spec.observation_semantics,
        "scoring_semantics": spec.scoring_semantics,
        "corpus_snapshot": spec.corpus_snapshot,
        "cluster_id": spec.cluster_id,
        "motif": spec.motif,
        "headline_metrics": spec.headline_metrics,
        "intent": query,
        "query_contract": contract,
        "query_contract_sha256": query_contract_sha256(contract),
        "query_validation": validation,
    }
    if spec.diagnostic_metrics is not None:
        task["diagnostic_metrics"] = spec.diagnostic_metrics
    else:
        task["diagnostic_metric"] = spec.diagnostic_metric
    assert_no_query_leaks(spec, task["intent"])
    return task


def query_constraint_diff(
    case: CaseSpecV3 | Mapping[str, Any],
    rendered: str | Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return an exact, fail-closed diff against GeneratorView projection."""

    spec = _case(case)
    expected_contract = canonical_query_contract(spec)
    diff: dict[str, dict[str, Any]] = {}
    if isinstance(rendered, str):
        try:
            validate_query_candidate(spec, rendered, attempt=1)
        except QueryRenderError as exc:
            diff["query_text"] = {
                "expected": "a GeneratorView-faithful RulePass query",
                "actual": str(exc),
            }
        return diff
    if not isinstance(rendered, Mapping):
        return {
            "rendered": {
                "expected": "string or mapping",
                "actual": type(rendered).__name__,
            }
        }

    actual_contract: Any = (
        rendered.get("query_contract")
        if "query_contract" in rendered
        else rendered
    )
    if actual_contract != expected_contract:
        diff["query_contract"] = {
            "expected": expected_contract,
            "actual": actual_contract,
        }
    if "intent" in rendered:
        actual_query = rendered.get("intent")
        try:
            validate_query_candidate(spec, actual_query, attempt=1)
        except QueryRenderError as exc:
            diff["query_text"] = {
                "expected": "a GeneratorView-faithful RulePass query",
                "actual": str(exc),
            }
    expected_hash = query_contract_sha256(expected_contract)
    if (
        "query_contract_sha256" in rendered
        and rendered.get("query_contract_sha256") != expected_hash
    ):
        diff["query_contract_sha256"] = {
            "expected": expected_hash,
            "actual": rendered.get("query_contract_sha256"),
        }
    return diff


def validate_query_alignment(
    case: CaseSpecV3 | Mapping[str, Any],
    rendered: str | Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return query_constraint_diff(case, rendered)


def assert_query_case_alignment(
    case: CaseSpecV3 | Mapping[str, Any],
    rendered: str | Mapping[str, Any],
) -> None:
    diff = query_constraint_diff(case, rendered)
    if diff:
        raise QueryAlignmentError(
            "rendered query constraint diff is not empty: "
            + json.dumps(diff, ensure_ascii=False, sort_keys=True)
        )
    text = rendered if isinstance(rendered, str) else str(rendered.get("intent", ""))
    assert_no_query_leaks(case, text)


constraint_diff = query_constraint_diff
BlindSemanticReviewRecord = BlindSemanticReviewRecordV3
HardRulePassRecord = HardRulePassRecordV3
QueryAcceptanceRecord = QueryAcceptanceRecordV3


__all__ = [
    "BLIND_REVIEW_PACKET_SCHEMA",
    "BLIND_REVIEW_SCHEMA",
    "EVIDENCE_CITATION_CONTRACT",
    "GENERATION_PROMPT_SCHEMA",
    "HARD_RULE_RECORD_SCHEMA",
    "QUERY_ACCEPTANCE_SCHEMA",
    "QUERY_CONTRACT_SCHEMA",
    "RENDERED_TASK_SCHEMA",
    "BlindSemanticReviewRecord",
    "BlindSemanticReviewRecordV3",
    "HardRuleChecksV3",
    "HardRulePassRecord",
    "HardRulePassRecordV3",
    "LeakFinding",
    "QueryAcceptanceRecord",
    "QueryAcceptanceRecordV3",
    "QueryAlignmentError",
    "QueryCaseDiscardedError",
    "QueryLeakError",
    "QueryRenderError",
    "QueryRetryRequiredError",
    "SanitizedFewShotExampleV3",
    "assert_no_query_leaks",
    "assert_query_accepted",
    "assert_query_case_alignment",
    "build_blind_review_packet",
    "build_hard_rule_pass_record",
    "build_query_acceptance_record",
    "build_query_generation_prompt",
    "canonical_query_contract",
    "constraint_diff",
    "detect_query_leaks",
    "generator_view_sha256",
    "query_constraint_diff",
    "query_contract_sha256",
    "query_sha256",
    "render_query",
    "render_task",
    "validate_blind_semantic_review",
    "validate_query_alignment",
    "validate_query_candidate",
    "validate_sanitized_few_shot_examples",
]
