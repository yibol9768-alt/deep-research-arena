"""Proof-step scorer for DRA v3.

The only score-bearing atom in v3 is a pre-frozen required proof step.  An
evidence step passes only when discovery, observation, support, local binding,
and the step relation all pass::

    StepPass_i = D_i and O_i and S_i and B_i and R_i

Bridge and final-answer steps depend on already passed premises and explicit
report expressions.  By default expressions use frozen deterministic
matchers; callers may instead supply a separately sealed LLM semantic-match
artifact containing exact report spans.  This module never fetches a URL and
never lets semantic matching replace provenance checks.  If the observation
ledger is missing or invalid it returns a
``withheld`` result with no numeric metrics, rather than accusing the agent of
an observed failure.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.eval.case_schema_v3 import CaseSpecV3, validate_case
from src.eval.observation_ledger import (
    OBSERVATION_SEMANTICS,
    ObservationEvent,
    ObservationLedger,
    LedgerIssue,
    adapt_run_evidence,
    load_observation_ledger,
    sha256_bytes,
)
from src.eval.protocol_manifest_v3 import (
    ProtocolManifestV3Error,
    validate_v3_protocol_manifest,
)
from src.eval.protocol_v3 import (
    DIAGNOSTIC_METRICS,
    FULL_PASS_RATE_METRIC,
    HEADLINE_METRICS,
    PARTIAL_COMPLETION_RATE_METRIC,
    LEGACY_SCORING_SEMANTICS,
    SCORING_SEMANTICS as PROTOCOL_SCORING_SEMANTICS,
    protocol_stamp,
)
from src.verifiers.citation_format import (
    Citation,
    canonicalize_url,
    extract_citations,
    strip_url_trail,
)


SCORING_SEMANTICS = PROTOCOL_SCORING_SEMANTICS
VERIFIED_SLOTS_SEMANTICS = LEGACY_SCORING_SEMANTICS
PARTIAL_COMPLETION_METRIC = PARTIAL_COMPLETION_RATE_METRIC
FULL_PASS_METRIC = FULL_PASS_RATE_METRIC
_URL_RE = re.compile(r"https?://[^\s<>\"'`\]]+")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?![A-Za-z0-9])")
_DECISION_CUE_RE = re.compile(
    r"\b(?:recommend|recommended|choose|chosen|select|selected|pick|best\s+(?:choice|option)|"
    r"conclusion|therefore|thus)\b|推荐|选择|结论|因此",
    re.IGNORECASE,
)


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        raw = value.to_dict()
        return dict(raw) if isinstance(raw, Mapping) else {}
    if hasattr(value, "model_dump"):
        raw = value.model_dump()
        return dict(raw) if isinstance(raw, Mapping) else {}
    try:
        return dict(vars(value))
    except (TypeError, ValueError):
        return {}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _proof_step_source(case: Mapping[str, Any]) -> tuple[list[Any], str]:
    """Return the score-bearing proof-step list and its compatibility tier."""

    evaluator = _mapping(case.get("evaluator_view"))
    if evaluator.get("required_proof_steps") is not None:
        return _list(evaluator["required_proof_steps"]), "evaluator_view"
    if case.get("required_proof_steps") is not None:
        return _list(case["required_proof_steps"]), "top_level_draft"
    # Old slot-shaped cases remain useful for local migration diagnostics.  A
    # formal case is never allowed to reach scoring through this fallback.
    return _list(case.get("slots")), "legacy_slots_draft"


def _normalize_proof_steps(
    case: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    raw_steps, source = _proof_step_source(case)
    steps: list[dict[str, Any]] = []
    for raw in raw_steps:
        step = _mapping(raw)
        step_id = step.get("step_id") or step.get("slot_id")
        step_type = str(step.get("type") or "").lower()
        if step_type == "final_answer":
            step_type = "decision"
        normalized = dict(step)
        normalized["step_id"] = str(step_id or "")
        normalized["slot_id"] = str(step_id or "")
        normalized["type"] = step_type
        normalized["vital"] = bool(
            step.get("vital", step.get("critical", step.get("required", True)))
        )
        normalized["_vital_declared"] = "vital" in step
        normalized["critical"] = normalized["vital"]
        normalized["required"] = step.get("required", True) is not False
        normalized["requires"] = [
            str(value) for value in _list(step.get("requires")) if str(value)
        ]
        claim = step.get("claim_id") or step.get("claim") or step.get("evidence_id")
        if claim is not None:
            normalized["claim_id"] = str(claim)
        relation = step.get("relation")
        if normalized.get("rule") is None and relation is not None:
            normalized["rule"] = relation
        support = _mapping(
            step.get("acceptable_support") or step.get("admissible_support")
        )
        for key in (
            "source_id",
            "source_ids",
            "source_url",
            "source_urls",
            "support_spans",
            "search_snippet_support",
            "body_support",
            "verifier",
            "accepted_phrases",
            "accepted_regex",
            "support_mode",
            "condition_match",
        ):
            if normalized.get(key) is None and support.get(key) is not None:
                normalized[key] = support[key]
        branch_values: list[str] = []
        for key in ("branch_id", "route_id", "source_branch"):
            if step.get(key):
                branch_values.append(str(step[key]))
        branch_values.extend(
            str(value)
            for value in _list(step.get("branches") or step.get("route_branches"))
            if str(value)
        )
        branch_values.extend(
            f"source_role:{value}"
            for value in _list(support.get("source_roles"))
            if str(value)
        )
        normalized["route_branches"] = sorted(set(branch_values))
        steps.append(normalized)
    return steps, source


def _proof_step_shape_issues(
    steps: Sequence[Mapping[str, Any]], *, source: str, formal: bool
) -> list[str]:
    issues: list[str] = []
    if formal and source != "evaluator_view":
        issues.append(
            "formal scoring requires evaluator_view.required_proof_steps; "
            "slot/top-level fallbacks are diagnostic-only"
        )
    if not steps:
        issues.append("required proof steps are missing")
        return issues
    step_ids = [str(step.get("step_id") or "") for step in steps]
    if any(not step_id for step_id in step_ids):
        issues.append("every proof step requires a non-empty step_id")
    if len(step_ids) != len(set(step_ids)):
        issues.append("proof step_id values must be unique")
    decisions = 0
    known_ids = set(step_ids)
    for step in steps:
        step_id = str(step.get("step_id") or "<missing>")
        step_type = str(step.get("type") or "")
        if step_type not in {"evidence", "bridge", "decision"}:
            issues.append(f"{step_id}: unsupported proof step type {step_type!r}")
            continue
        if step_type == "decision":
            decisions += 1
        if type(step.get("vital")) is not bool:
            issues.append(f"{step_id}: vital must be a JSON boolean")
        elif formal and step.get("_vital_declared") is not True:
            issues.append(f"{step_id}: formal proof step must explicitly declare vital")
        if formal and step.get("required") is False:
            issues.append(f"{step_id}: formal required_proof_steps cannot be optional")
        dependencies = list(step.get("requires") or [])
        unknown = sorted(set(map(str, dependencies)) - known_ids)
        if unknown:
            issues.append(f"{step_id}: unknown proof dependencies {unknown}")
        if step_type == "evidence":
            if not step.get("claim_id"):
                issues.append(f"{step_id}: evidence step requires a claim")
            support = _mapping(
                step.get("acceptable_support") or step.get("admissible_support")
            )
            if formal and not support:
                issues.append(
                    f"{step_id}: formal evidence step requires acceptable_support"
                )
            if formal and not str(step.get("provenance_contract") or "").strip():
                issues.append(
                    f"{step_id}: formal evidence step requires provenance_contract"
                )
        elif not dependencies or not (step.get("rule") or step.get("relation")):
            issues.append(
                f"{step_id}: derived proof step requires dependencies and a relation"
            )
    if decisions < 1:
        issues.append("required proof steps require a final-answer/decision step")
    return issues


def _canon(url: Any) -> str:
    raw = str(url or "").strip()
    return canonicalize_url(raw) if raw else ""


def _stable_hash_strings(values: Iterable[str]) -> str:
    body = json.dumps(sorted(set(values)), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _canonical_json_digest(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _replay_identity(
    *,
    task_id: Any,
    cluster_id: Any,
    agent: Any,
    replicate: Any,
    ledger: ObservationLedger,
    observation_ledger_sha256: str,
    report_sha256: str,
    case_artifact_sha256: Optional[str],
    public_task_sha256: Optional[str],
    protocol_manifest_sha256: Optional[str],
    corpus_registry_hash: Optional[str],
    scoring_semantics: str,
) -> dict[str, Any]:
    identity = {
        "run_id": ledger.run_id,
        "agent": agent,
        "task_id": task_id,
        "replicate": replicate,
        "cluster_id": cluster_id,
        "report_sha256": report_sha256,
        "observation_ledger_sha256": observation_ledger_sha256,
        "case_artifact_sha256": case_artifact_sha256,
        "public_task_sha256": public_task_sha256,
        "protocol_manifest_sha256": protocol_manifest_sha256,
        "corpus_registry_hash": corpus_registry_hash,
    }
    return {
        **identity,
        "scoring_input_sha256": _canonical_json_digest({
            "version": (
                "dra_v3_scoring_input_v3"
                if scoring_semantics == SCORING_SEMANTICS
                else "dra_v3_scoring_input_v2"
            ),
            **identity,
        }),
    }


def _protocols_for_score(
    case: Mapping[str, Any],
    corpus_registry_hash: Optional[str],
    corpus_url_set_hash: str,
    injected: Optional[Mapping[str, Any]] = None,
    scoring_semantics: str = VERIFIED_SLOTS_SEMANTICS,
) -> dict[str, Any]:
    if injected is not None:
        protocols = dict(injected)
        protocols["corpus_url_set_hash"] = corpus_url_set_hash
        return protocols
    task_id = str(case.get("task_id") or "unknown_task")
    corpus_snapshot = str(case.get("corpus_snapshot") or "pilot-unspecified")
    # A single-case scorer cannot manufacture panel identity from the case it
    # is currently scoring.  Formal case-set/evidence-graph hashes come only
    # from a separately sealed protocol manifest.
    protocols = protocol_stamp(
        corpus_snapshot=corpus_snapshot,
        task_ids=[task_id],
        corpus_registry_hash=corpus_registry_hash,
        scoring_semantics=scoring_semantics,
    )
    protocols["corpus_url_set_hash"] = corpus_url_set_hash
    return protocols


def _validate_protocol_manifest_for_case(
    manifest: Mapping[str, Any],
    case: CaseSpecV3,
    corpus_registry_hash: Optional[str],
    case_artifact_sha256: Optional[str],
    public_task_sha256: Optional[str],
    scoring_semantics: str,
) -> tuple[
    Optional[dict[str, Any]],
    Optional[dict[str, Any]],
    Optional[str],
]:
    if not case_artifact_sha256:
        return None, None, "formal protocol injection requires exact case artifact sha256"
    if not re.fullmatch(r"[0-9a-f]{64}", str(case_artifact_sha256)):
        return None, None, "case artifact sha256 must be 64 lowercase hex characters"
    if not re.fullmatch(r"[0-9a-f]{64}", str(public_task_sha256 or "")):
        return None, None, (
            "formal protocol injection requires exact public task artifact sha256"
        )
    try:
        validated_manifest = validate_v3_protocol_manifest(manifest)
    except (ProtocolManifestV3Error, TypeError, ValueError) as exc:
        return None, None, str(exc)
    validated = dict(validated_manifest["protocols"])
    if validated.get("scoring_semantics") != scoring_semantics:
        return None, None, (
            "protocol manifest scoring_semantics does not match the selected scorer"
        )
    expected_snapshot = case.corpus_snapshot
    if expected_snapshot and validated.get("corpus_snapshot") != expected_snapshot:
        return None, None, "protocol manifest corpus_snapshot does not match the case"
    if corpus_registry_hash and validated.get("corpus_registry_hash") != corpus_registry_hash:
        return None, None, (
            "protocol manifest corpus_registry_hash does not match scorer input"
        )
    case_data = case.to_dict()
    for case_key, protocol_key in (
        ("task_version", "task_version"),
        ("case_schema", "case_schema"),
        ("evidence_graph", "evidence_graph"),
        ("observation_semantics", "observation_semantics"),
        ("scoring_semantics", "scoring_semantics"),
    ):
        expected = case_data.get(case_key)
        if expected is not None and validated.get(protocol_key) != expected:
            return None, None, (
                f"protocol manifest {protocol_key} does not match the case"
            )
    task_id = case.task_id
    task_ids = validated_manifest["task_ids"]
    task_clusters = validated_manifest["task_clusters"]
    if task_id not in task_ids:
        return None, None, f"task_id {task_id!r} is absent from the protocol manifest"
    if task_clusters[task_id] != case.cluster_id:
        return None, None, "protocol manifest task cluster does not match the case"
    if validated_manifest["case_hashes"][task_id] != case_artifact_sha256:
        return None, None, (
            "protocol manifest case hash does not match exact case artifact bytes"
        )
    if validated_manifest["public_task_hashes"][task_id] != public_task_sha256:
        return None, None, (
            "protocol manifest public task hash does not match exact public task bytes"
        )
    bindings = case.formal_bindings
    if bindings is None or bindings.formal is not True:
        return None, None, "formal protocol injection requires case formal_bindings"
    formal_graph = bindings.evidence_graph_sha256
    formal_registry = bindings.corpus_registry_sha256
    if formal_graph != validated.get("evidence_graph_hash"):
        return None, None, (
            "protocol manifest graph hash does not match case formal bindings"
        )
    if formal_registry != validated.get("corpus_registry_hash"):
        return None, None, (
            "protocol manifest registry hash does not match case formal bindings"
        )

    actual_contract = {
        "cluster_id": case.cluster_id,
        "motif": case.motif,
        "declared_proof_depth": case.difficulty.proof_depth,
        "minimum_reasoning_depth": case.minimum_reasoning_depth,
        "required_research_subgoals": len(case.research_subgoals),
        "cross_source_bridges": case.cross_source_bridge_count,
        "single_page_sufficient": case.oracle.single_page_sufficient,
    }
    declared_contract = dict(validated_manifest["task_contracts"][task_id])
    if declared_contract != actual_contract:
        mismatches = sorted(
            field_name
            for field_name, actual_value in actual_contract.items()
            if declared_contract.get(field_name) != actual_value
        )
        return None, None, (
            "protocol manifest task_contract disagrees with validated CaseSpecV3 "
            f"fields: {mismatches}"
        )
    if (
        validated_manifest["proof_subgraph_fingerprints"][task_id]
        != case.proof_subgraph_sha256
    ):
        return None, None, (
            "protocol manifest proof fingerprint does not match validated CaseSpecV3"
        )
    return dict(validated), dict(validated_manifest), None


def _mask_urls(text: str) -> str:
    """Mask URL destinations without moving report character offsets."""

    chars = list(text or "")
    for match in _URL_RE.finditer(text or ""):
        raw = match.group(0)
        clean = strip_url_trail(raw)
        for index in range(match.start(), match.start() + len(clean)):
            chars[index] = " "
    return "".join(chars)


def _normal(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").split())


@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int
    text: str
    kind: str


def _values(objects: Iterable[Any], keys: Sequence[str]) -> list[Any]:
    out: list[Any] = []
    for obj in objects:
        data = _mapping(obj)
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            out.extend(_list(value))
        verifier = data.get("verifier")
        if isinstance(verifier, Mapping):
            for key in keys:
                value = verifier.get(key)
                if value is not None:
                    out.extend(_list(value))
    return out


def _first(objects: Iterable[Any], keys: Sequence[str], default: Any = None) -> Any:
    for obj in objects:
        data = _mapping(obj)
        for key in keys:
            if data.get(key) is not None:
                return data[key]
        verifier = data.get("verifier")
        if isinstance(verifier, Mapping):
            for key in keys:
                if verifier.get(key) is not None:
                    return verifier[key]
    return default


def _phrase_matches(
    text: str,
    phrase: str,
    *,
    case_sensitive: bool = False,
    normalizers: Sequence[str] = (),
) -> list[TextMatch]:
    if not phrase:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    # Whitespace in an accepted phrase is semantic whitespace, not a demand for
    # the exact number of spaces/newlines used by one oracle.
    phrase_text = str(phrase)
    if "hyphen" in normalizers:
        phrase_text = re.sub(r"[-‐‑‒–—]+", " ", phrase_text)
    pieces = [re.escape(piece) for piece in phrase_text.split()]
    if not pieces:
        return []
    separator = r"[\s\W_]+" if "punctuation" in normalizers else (
        r"(?:\s+|[-‐‑‒–—]+)" if "hyphen" in normalizers else r"\s+"
    )
    pattern = separator.join(pieces)
    return [TextMatch(m.start(), m.end(), m.group(0), "accepted_phrase") for m in re.finditer(pattern, text, flags)]


def _regex_matches(text: str, pattern: str, *, case_sensitive: bool = False) -> list[TextMatch]:
    if not pattern:
        return []
    flags = re.MULTILINE | (0 if case_sensitive else re.IGNORECASE)
    try:
        return [
            TextMatch(m.start(), m.end(), m.group(0), "regex")
            for m in re.finditer(pattern, text, flags)
        ]
    except re.error:
        return []


def _regex_fullmatches(text: str, pattern: str, *, case_sensitive: bool = False) -> list[TextMatch]:
    flags = re.MULTILINE | (0 if case_sensitive else re.IGNORECASE)
    try:
        compiled = re.compile(pattern, flags)
    except re.error:
        return []
    out: list[TextMatch] = []
    for segment in re.finditer(r"[^\n.!?。！？]+(?:[.!?。！？]+|$)", text):
        raw = segment.group(0).strip()
        # URL bytes have already been masked.  Remove the remaining Markdown
        # citation shell before applying a full-claim regex.
        with_punctuation = re.sub(r"\[[^\]]*\]\(\s*\)", "", raw).strip()
        with_punctuation = re.sub(
            r"\s+([.!?。！？]+)$", r"\1", with_punctuation
        )
        without_punctuation = with_punctuation.rstrip(".!?。！？").strip()
        # A typed rule may anchor either the complete sentence bytes or its
        # punctuation-neutral claim text.  Trying both keeps full-match
        # semantics without silently rewriting the case-authored regex.
        for candidate in dict.fromkeys((with_punctuation, without_punctuation)):
            if candidate and compiled.fullmatch(candidate):
                out.append(TextMatch(
                    segment.start(), segment.end(), candidate, "regex_fullmatch"
                ))
                break
    return out


def _negated_context(text: str, match: TextMatch) -> bool:
    left, right = _sentence_bounds(text, match.start, match.end)
    prefix = text[max(left, match.start - 80):match.start]
    suffix = text[match.end:min(right, match.end + 50)]
    prefix_negative = re.search(
        r"(?:\bnot\b|\bnever\b|\bfalse\s+that\b|\bincorrect\s+that\b|"
        r"\b(?:deny|denies|denied|reject|rejects|rejected)\s+(?:that\s+)?|"
        r"\bno\s+evidence\s+that\b|并非|不是|不应认为|错误地认为)"
        r"[^.!?。！？\n]{0,40}$",
        prefix,
        re.IGNORECASE,
    )
    suffix_negative = re.match(
        r"\s+(?:is|was|seems?)\s+(?:false|incorrect|wrong)\b|"
        r"\s*(?:并不成立|是错误的|不正确)",
        suffix,
        re.IGNORECASE,
    )
    return bool(prefix_negative or suffix_negative)


def _numeric_matches(text: str, objects: Iterable[Any], node: Mapping[str, Any]) -> list[TextMatch]:
    numeric_pattern = _first(objects, ("numeric_regex", "value_regex", "context_regex"))
    tolerance = _first(objects, ("tolerance", "absolute_tolerance"), 0.0)
    relative = _first(objects, ("relative_tolerance",), 0.0)
    expected = _first(objects, ("expected", "expected_value", "value"), node.get("object"))
    try:
        expected_number = float(str(expected).replace(",", ""))
        absolute_tolerance = float(tolerance)
        relative_tolerance = float(relative or 0.0)
    except (TypeError, ValueError):
        return []
    allowed = max(absolute_tolerance, abs(expected_number) * relative_tolerance)
    out: list[TextMatch] = []
    if numeric_pattern:
        try:
            contexts = list(re.finditer(str(numeric_pattern), text, re.IGNORECASE | re.MULTILINE))
        except re.error:
            return []
    else:
        subject = _normal(node.get("subject"))
        predicate = _normal(node.get("predicate"))
        contexts = []
        # Use line-local contexts so decimal points are not mistaken for
        # sentence terminators (``30.5 hours`` must remain one numeric claim).
        for context in re.finditer(r"[^\n]+", text):
            normalized = _normal(context.group(0))
            predicate_tokens = [token for token in predicate.split() if len(token) > 1]
            if subject and subject not in normalized:
                continue
            if predicate_tokens and not any(token in normalized for token in predicate_tokens):
                continue
            if re.search(r"\b(?:not|no|never|isn't|aren't|doesn't|didn't|without)\b|不|并非|不是|没有", context.group(0), re.I):
                continue
            contexts.append(context)
    unit = str(_first(objects, ("unit",), "") or "").strip()
    for context_match in contexts:
        if "value" in context_match.groupdict() and context_match.group("value") is not None:
            value_matches = [re.search(_NUMBER_RE, context_match.group("value"))]
            value_base = context_match.start("value")
        else:
            value_matches = list(_NUMBER_RE.finditer(context_match.group(0)))
            value_base = context_match.start()
        for match in value_matches:
            if match is None:
                continue
            raw_value = match.group(0)
            absolute_start = value_base + match.start()
            absolute_end = value_base + match.end()
            try:
                actual = float(raw_value.replace(",", ""))
            except ValueError:
                continue
            if not math.isclose(actual, expected_number, rel_tol=0.0, abs_tol=allowed):
                continue
            if unit and _normal(unit) not in _normal(context_match.group(0)):
                continue
            out.append(TextMatch(absolute_start, absolute_end, raw_value, "numeric_tolerance"))
    return out


def _typed_fallback(text: str, node: Mapping[str, Any]) -> list[TextMatch]:
    direct = node.get("text") or node.get("claim") or node.get("statement")
    if direct:
        return _phrase_matches(text, str(direct))
    subject = str(node.get("subject") or "").strip()
    predicate = str(node.get("predicate") or "").replace("_", " ").strip()
    obj = str(node.get("object") or "").strip()
    if not subject or not obj:
        return []
    # Keep the fallback conservative: subject and object must occur in one
    # paragraph, and a meaningful predicate token must occur there as well.
    out: list[TextMatch] = []
    cursor = 0
    for paragraph in re.split(r"\n\s*\n", text):
        start = text.find(paragraph, cursor)
        cursor = start + len(paragraph)
        norm = _normal(paragraph)
        if _normal(subject) not in norm or _normal(obj) not in norm:
            continue
        pred_words = [word for word in _normal(predicate).split() if len(word) > 2]
        if pred_words and not any(word in norm for word in pred_words):
            continue
        out.append(TextMatch(start, start + len(paragraph), paragraph, "typed_claim"))
    return out


def _find_matches(text: str, objects: Iterable[Any], node: Optional[Mapping[str, Any]] = None) -> list[TextMatch]:
    objects = list(objects)
    matcher = str(_first(objects, ("matcher",), "") or "")
    normalizers = [str(value) for value in _values(objects, ("normalizers",))]
    case_sensitive = bool(_first(objects, ("case_sensitive",), False)) or matcher in {"exact", "typed_exact"}
    matches: list[TextMatch] = []
    for phrase in _values(objects, ("accepted_phrases", "accepted_phrase", "accepted_aliases", "phrases", "phrase")):
        if isinstance(phrase, Mapping):
            phrase = phrase.get("text") or phrase.get("phrase")
        if phrase is not None:
            matches.extend(_phrase_matches(
                text,
                str(phrase),
                case_sensitive=case_sensitive,
                normalizers=normalizers,
            ))
    for pattern in _values(objects, ("accepted_regex", "accepted_regexes", "regex", "regexes", "patterns")):
        if isinstance(pattern, Mapping):
            pattern = pattern.get("pattern") or pattern.get("regex")
        if pattern is not None:
            if matcher == "regex_fullmatch":
                matches.extend(_regex_fullmatches(text, str(pattern), case_sensitive=case_sensitive))
            else:
                matches.extend(_regex_matches(text, str(pattern), case_sensitive=case_sensitive))
    if node is not None:
        if matcher in {"numeric", "numeric_tolerance"}:
            matches.extend(_numeric_matches(text, objects, node))
    # No subject/predicate/object fallback: co-occurrence cannot distinguish a
    # positive assertion from negation, a question, or a counterfactual.  A
    # formal typed claim must carry an explicit positive phrase/regex/numeric
    # context matcher.
    if not bool(_first(objects, ("allow_negated",), False)):
        matches = [match for match in matches if not _negated_context(text, match)]
    unique = {(match.start, match.end, match.kind): match for match in matches}
    return sorted(unique.values(), key=lambda item: (item.start, item.end, item.kind))


def _semantic_text_match(
    report: str,
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]],
    target_id: str,
) -> Optional[TextMatch]:
    """Return an exact, revalidated report span for one entailed target."""

    if semantic_matches is None:
        return None
    row = _mapping(semantic_matches.get(target_id))
    if row.get("verdict") != "entailed":
        return None
    quote = row.get("matched_quote")
    start, end = row.get("start"), row.get("end")
    if (
        not isinstance(quote, str)
        or not quote
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or report[start:end] != quote
    ):
        return None
    return TextMatch(start, end, quote, "llm_semantic_exact_span")


def _graph_nodes(graph: Any) -> dict[str, dict[str, Any]]:
    raw = _get(graph, "nodes", graph)
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, Mapping):
        rows = raw.items()
    else:
        rows = [(None, row) for row in _list(raw)]
    for key, value in rows:
        node = _mapping(value)
        if not node:
            continue
        node_id = key or node.get("evidence_id") or node.get("claim_id") or node.get("node_id") or node.get("id")
        if node_id:
            out[str(node_id)] = node
    return out


def _source_catalog(case: Mapping[str, Any], graph: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for owner in (graph, case):
        raw = _get(owner, "evidence_sources", None) or _get(owner, "sources", None)
        if isinstance(raw, Mapping):
            rows = raw.items()
        else:
            rows = [(None, row) for row in _list(raw)]
        for key, value in rows:
            source = _mapping(value)
            sid = key or source.get("source_id") or source.get("evidence_id") or source.get("id")
            if sid:
                out[str(sid)] = source
    return out


def _corpus_registry(
    case: Mapping[str, Any],
    graph: Any,
    nodes: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    explicit: Optional[Iterable[str]],
    explicit_hash: Optional[str],
) -> tuple[set[str], str, Optional[str], str, Optional[str]]:
    """Return full registry URLs, provenance, typed hash, URL hash and issue.

    Evidence used by this case is intentionally *not* promoted into a corpus
    registry.  Doing so would classify every unrelated real corpus citation as
    fabricated and make report-wide provenance depend on the case subgraph.
    """

    urls: set[str] = set()
    source = "missing"
    declared_hash = str(explicit_hash or "").strip().lower()
    if explicit is not None:
        urls.update(_canon(url) for url in explicit if _canon(url))
        source = "argument"
    else:
        for owner in (graph, case):
            registry_obj = _get(owner, "corpus_registry", None)
            if isinstance(registry_obj, Mapping):
                raw_urls = registry_obj.get("urls") or registry_obj.get("corpus_registry_urls")
                if raw_urls is not None and not urls:
                    urls.update(_canon(url) for url in _list(raw_urls) if _canon(url))
                    source = "case_or_graph_registry"
                if not declared_hash:
                    declared_hash = str(registry_obj.get("sha256") or registry_obj.get("hash") or "").strip().lower()
            for key in ("corpus_registry_urls", "frozen_corpus_urls"):
                raw = _get(owner, key, None)
                if raw is None:
                    continue
                if isinstance(raw, Mapping):
                    raw = raw.keys()
                urls.update(_canon(url) for url in _list(raw) if _canon(url))
                source = "case_or_graph_registry"
            if not declared_hash:
                declared_hash = str(_get(owner, "corpus_registry_hash", "") or "").strip().lower()
    if declared_hash.startswith("sha256:"):
        declared_hash = declared_hash.split(":", 1)[1]
    issue: Optional[str] = None
    if not urls:
        issue = "full frozen corpus registry URL set is missing"
    elif not re.fullmatch(r"[0-9a-f]{64}", declared_hash):
        issue = "full frozen corpus registry sha256 is missing or invalid"

    graph_urls: set[str] = set()
    for row in list(nodes.values()) + list(sources.values()):
        if row.get("frozen") is False:
            continue
        for url in _list(row.get("source_urls") or row.get("source_url") or row.get("url")):
            if _canon(url):
                graph_urls.add(_canon(url))
    outside = sorted(graph_urls - urls)
    if not issue and outside:
        issue = "evidence source URL is absent from the declared full corpus registry"
    return urls, source, (declared_hash or None), _stable_hash_strings(urls), issue


def _resolve_node(
    slot: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    cid = slot.get("claim_id") or slot.get("evidence_id") or slot.get("node_id")
    node = dict(nodes.get(str(cid), {})) if cid is not None else {}
    source_id = slot.get("source_id") or cid
    source = sources.get(str(source_id), {}) if source_id is not None else {}
    for key, value in source.items():
        node.setdefault(key, value)
    # Inline fields are useful for tiny pilot fixtures and override only when
    # the graph did not provide the field.
    for key in (
        "subject", "predicate", "object", "text", "source_url", "source_urls",
        "support_spans", "search_snippet_support", "body_support", "verifier",
        "accepted_phrases", "accepted_regex", "tolerance", "content_sha256",
    ):
        if key not in node and slot.get(key) is not None:
            node[key] = slot[key]
    return node


def _resolve_support_node(
    slot: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    source_id: str,
) -> dict[str, Any]:
    """Resolve one proof-only alternative without changing legacy precedence."""

    cid = slot.get("claim_id") or slot.get("evidence_id") or slot.get("node_id")
    node = dict(nodes.get(str(cid), {})) if cid is not None else {}
    source: dict[str, Any] = {}
    source.update(_mapping(nodes.get(source_id)))
    source.update(_mapping(sources.get(source_id)))
    # The proposition/claim node supplies the semantic atom.  Page-bound
    # fields must come from the selected support source so an alternative URL
    # is checked against its own bytes, spans, visibility and verifier rather
    # than accidentally reusing the first source's gold snapshot.
    source_bound_fields = {
        "source_id",
        "source_url",
        "source_urls",
        "url",
        "content_sha256",
        "allowed_content_sha256",
        "body_sha256",
        "source_content_sha256",
        "support_spans",
        "search_snippet_support",
        "body_support",
        "source_role",
        "source_type",
        "verifier",
    }
    for key, value in source.items():
        if key in source_bound_fields:
            node[key] = value
        else:
            node.setdefault(key, value)
    node["source_id"] = source_id
    # Inline fields are useful for tiny pilot fixtures and override only when
    # the graph did not provide the field.
    for key in (
        "subject", "predicate", "object", "text", "source_url", "source_urls",
        "support_spans", "search_snippet_support", "body_support", "verifier",
        "accepted_phrases", "accepted_regex", "tolerance", "content_sha256",
        "support_mode", "condition_match",
    ):
        if key not in node and slot.get(key) is not None:
            node[key] = slot[key]
    return node


def _resolve_support_nodes(
    slot: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve every explicitly proposition-bound support alternative.

    ``source_roles`` constrain admissibility but do not identify semantic
    support.  Expanding to every same-role page would allow an unrelated page
    to pass.  The compiler-bound source IDs establish the proposition link;
    each candidate is then evaluated with its own frozen support material.
    """

    support = _mapping(
        slot.get("acceptable_support") or slot.get("admissible_support")
    )
    source_ids = [
        str(value)
        for value in _list(
            support.get("source_ids")
            or slot.get("source_ids")
            or support.get("source_id")
            or slot.get("source_id")
        )
        if str(value)
    ]
    if not source_ids:
        fallback = (
            slot.get("claim_id")
            or slot.get("evidence_id")
            or slot.get("node_id")
        )
        if fallback is not None:
            source_ids = [str(fallback)]
    return [
        (
            source_id,
            _resolve_support_node(slot, nodes, sources, source_id),
        )
        for source_id in dict.fromkeys(source_ids)
    ]


def _resolve_rule(rule: Any, case: Mapping[str, Any], graph: Any, slot: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(rule, Mapping):
        resolved = dict(rule)
    else:
        resolved = {}
        rule_id = str(rule or "")
        for owner in (case, _mapping(graph)):
            for key in ("rules", "rule_definitions", "decision_rules", "bridge_rules"):
                catalog = owner.get(key)
                if isinstance(catalog, Mapping) and rule_id in catalog:
                    resolved = _mapping(catalog[rule_id])
                    break
            if resolved:
                break
        if rule_id:
            resolved.setdefault("rule_id", rule_id)
    # Slot-level deterministic expressions are convenient and remain visible in
    # the case spec; they are not inferred from the natural language query.
    for key in (
        "accepted_phrases", "accepted_phrase", "accepted_regex", "accepted_regexes",
        "regex", "tolerance", "conclusion_phrases", "decision_phrases",
    ):
        if slot.get(key) is not None and key not in resolved:
            resolved[key] = slot[key]
    decision_matcher = resolved.get("decision_matcher")
    if isinstance(decision_matcher, Mapping):
        for key, value in decision_matcher.items():
            resolved.setdefault(str(key), value)
    return resolved


def _source_urls(
    slot: Mapping[str, Any],
    node: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    *,
    expand_accepted_roles: bool = True,
) -> list[str]:
    values: list[Any] = []
    values.extend(_list(node.get("source_urls") or node.get("source_url")))
    values.extend(_list(slot.get("source_urls") or slot.get("source_url")))
    source_ids = _list(
        slot.get("source_ids")
        or slot.get("source_id")
        or node.get("source_ids")
        or node.get("source_id")
    )
    for source_id in source_ids:
        source = sources.get(str(source_id), {})
        values.extend(_list(source.get("source_urls") or source.get("source_url") or source.get("url")))
    support = _mapping(
        slot.get("acceptable_support") or slot.get("admissible_support")
    )
    accepted_roles = {
        str(value).casefold() for value in _list(support.get("source_roles"))
        if str(value)
    }
    role_families = {
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
    if expand_accepted_roles and accepted_roles:
        for source in sources.values():
            source_type = str(
                source.get("source_role") or source.get("source_type") or ""
            ).casefold()
            family = role_families.get(source_type, source_type)
            role_aliases = {source_type, family}
            if source_type == "concept":
                role_aliases.add("concept")
            if accepted_roles & role_aliases:
                values.extend(
                    _list(
                        source.get("source_urls")
                        or source.get("source_url")
                        or source.get("url")
                    )
                )
    return sorted({_canon(url) for url in values if _canon(url)})


def _paragraph_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left_matches = list(re.finditer(r"\n\s*\n", text[:start]))
    left = left_matches[-1].end() if left_matches else 0
    right_match = re.search(r"\n\s*\n", text[end:])
    right = end + right_match.start() if right_match else len(text)
    return left, right


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    def boundary(index: int) -> bool:
        char = text[index]
        if char not in ".!?。！？\n":
            return False
        if char == "." and 0 < index < len(text) - 1:
            if text[index - 1].isdigit() and text[index + 1].isdigit():
                return False
        return True

    left = 0
    for index in range(start - 1, -1, -1):
        if boundary(index):
            left = index + 1
            break
    right = len(text)
    for index in range(end, len(text)):
        if boundary(index):
            right = index + 1
            break
    return left, right


def _bound_citations(
    report: str,
    claim: TextMatch,
    citations: Sequence[Citation],
    slot: Mapping[str, Any],
) -> list[Citation]:
    scope = str(slot.get("citation_scope") or "sentence").lower()
    try:
        window = int(slot.get("citation_window", 240))
    except (TypeError, ValueError):
        window = 240
    if scope in {"line", "same_line"}:
        left = report.rfind("\n", 0, claim.start) + 1
        right_pos = report.find("\n", claim.end)
        right = len(report) if right_pos < 0 else right_pos
    elif scope in {"paragraph", "same_paragraph"}:
        left, right = _paragraph_bounds(report, claim.start, claim.end)
    else:
        left, right = _sentence_bounds(report, claim.start, claim.end)
    return sorted(
        [
            cite for cite in citations
            if left <= cite.char_offset <= right
            and min(abs(cite.char_offset - claim.start), abs(cite.char_offset - claim.end)) <= max(window, 0)
        ],
        key=lambda cite: min(abs(cite.char_offset - claim.start), abs(cite.char_offset - claim.end)),
    )


def _span_observed(text: str, spans: Sequence[Any], *, allow_offsets: bool) -> bool:
    encoded = text.encode("utf-8")
    for raw in spans:
        span = _mapping(raw)
        phrases = _list(span.get("accepted_phrases") or span.get("text") or span.get("quote"))
        if any(_phrase_matches(text, str(phrase)) for phrase in phrases if phrase is not None):
            return True
        regex = span.get("regex") or span.get("accepted_regex")
        if regex and _regex_matches(text, str(regex)):
            return True
        start, end, digest = span.get("start"), span.get("end"), str(span.get("sha256") or "")
        if not allow_offsets:
            # Page and snippet offsets are different coordinate spaces.  The
            # span digest still permits proof without gold plaintext: scan the
            # short snippet for a byte window of the gold span's known length.
            # We never apply the page's absolute offset to snippet bytes.
            if (
                type(start) is int and type(end) is int and digest
                and 0 <= start <= end and end - start <= len(encoded)
            ):
                width = end - start
                if any(
                    sha256_bytes(encoded[index:index + width]) == digest.lower()
                    for index in range(0, len(encoded) - width + 1)
                ):
                    return True
            continue
        if type(start) is not int or type(end) is not int or not digest or start < 0 or end < start:
            continue
        candidates: list[bytes] = []
        if end <= len(encoded):
            candidates.append(encoded[start:end])
        if end <= len(text):
            candidates.append(text[start:end].encode("utf-8"))
        if any(sha256_bytes(candidate) == digest.lower() for candidate in candidates):
            return True
    return False


def _content_supports(event: ObservationEvent, node: Mapping[str, Any], ledger: ObservationLedger) -> bool:
    if not event.observable or event.http_status not in (None, 200):
        return False
    text = event.visible_text(ledger.blob_loader)
    if text is None:
        return False
    if event.event_type in {"fetch_body", "extracted_body"}:
        expected_hashes = {
            str(value).lower()
            for value in _list(
                node.get("allowed_content_sha256")
                or node.get("content_sha256")
                or node.get("body_sha256")
                or node.get("source_content_sha256")
            )
            if value
        }
        if expected_hashes and event.content_sha256 not in expected_hashes:
            return False
    spans = _list(node.get("support_spans"))
    if event.event_type == "search_result":
        spans = [
            span for span in spans
            if str(_get(span, "support_type", "search_snippet")) == "search_snippet"
        ]
    elif event.event_type in {"fetch_body", "extracted_body"}:
        spans = [
            span for span in spans
            if str(_get(span, "support_type", "body")) == "body"
        ]
    if spans:
        return _span_observed(
            text,
            spans,
            allow_offsets=event.event_type in {"fetch_body", "extracted_body"},
        )
    support_objects = [
        {
            "accepted_phrases": node.get("support_phrases") or node.get("accepted_phrases"),
            "accepted_regex": node.get("support_regex") or node.get("accepted_regex"),
            "tolerance": _get(node.get("verifier"), "tolerance", node.get("tolerance")),
            "expected": _get(node.get("verifier"), "expected", node.get("object")),
        }
    ]
    return bool(_find_matches(text, support_objects, node))


def _seed_urls(case: Mapping[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in (
        "seed_urls", "start_urls", "task_seed_urls", "allowed_start_urls",
        "discovery_root_urls",
    ):
        values.extend(_list(case.get(key)))
    scenario = _mapping(case.get("scenario"))
    for key in ("seed_urls", "start_urls"):
        values.extend(_list(scenario.get(key)))
    return {_canon(url) for url in values if _canon(url)}


def _observation_for_source(
    source_url: str,
    node: Mapping[str, Any],
    ledger: ObservationLedger,
    seeds: set[str],
) -> dict[str, Any]:
    events = [event for event in ledger.events if event.canonical_url == source_url]
    by_event_id = ledger.by_id()
    license_cache: dict[int, bool] = {}

    def content_visible(event: ObservationEvent) -> bool:
        return bool(
            event.observable
            and event.event_type
            in {"search_result", "fetch_body", "extracted_body"}
            and event.visible_text(ledger.blob_loader) is not None
        )

    def body_event_licensed(body_event: ObservationEvent) -> bool:
        cached = license_cache.get(body_event.event_id)
        if cached is not None:
            return cached
        if body_event.canonical_url in seeds:
            license_cache[body_event.event_id] = True
            return True
        prior = [
            event for event in ledger.events
            if event.event_id < body_event.event_id
            and event.canonical_url == body_event.canonical_url
            and event.event_type in {"search_result", "page_link"}
        ]
        licensed = False
        for discovery in prior:
            if discovery.event_type == "search_result":
                licensed = True
                break
            parent = by_event_id.get(discovery.parent_event_id)
            if parent is not None and body_event_licensed(parent):
                licensed = True
                break
        license_cache[body_event.event_id] = licensed
        return licensed

    def valid_discovery(event: ObservationEvent) -> bool:
        if event.event_type == "search_result":
            return True
        parent = by_event_id.get(event.parent_event_id)
        return parent is not None and body_event_licensed(parent)

    discoveries = [
        event for event in events
        if event.event_type in {"search_result", "page_link"} and valid_discovery(event)
    ]
    candidates: list[dict[str, Any]] = []
    snippet_allowed = node.get("search_snippet_support") is True or any(
        str(_get(span, "support_type", _get(span, "visibility", ""))).lower()
        in {"snippet", "search_snippet", "both"}
        for span in _list(node.get("support_spans"))
    )
    body_allowed = node.get("body_support") is not False
    support_mode = str(node.get("support_mode") or "").lower()
    if support_mode == "body":
        snippet_allowed = False
    elif support_mode == "exact_snippet":
        body_allowed = False
    for event in events:
        supports = False
        if event.event_type == "search_result" and snippet_allowed:
            supports = _content_supports(event, node, ledger)
        elif event.event_type in {"fetch_body", "extracted_body"} and body_allowed:
            supports = _content_supports(event, node, ledger)
        if not supports:
            continue
        if event.event_type == "search_result":
            licensed = True
            discovery_class = "searched"
            discovery_id = event.event_id
        else:
            prior = [item for item in discoveries if item.event_id < event.event_id]
            if source_url in seeds:
                licensed = True
                discovery_class = "task_seed"
                discovery_id = None
            elif prior:
                chosen = prior[-1]
                licensed = True
                discovery_class = "searched" if chosen.event_type == "search_result" else "linked"
                discovery_id = chosen.event_id
            else:
                licensed = False
                discovery_class = "guessed_then_fetched"
                discovery_id = None
        candidates.append({
            "observed": True,
            "content_observed": True,
            "supported": True,
            "licensed": licensed,
            "observation_event_id": event.event_id,
            "observation_type": event.event_type,
            "discovery_event_id": discovery_id,
            "discovery_class": discovery_class,
        })
    if candidates:
        # Prefer a legitimately licensed support event, then chronology.
        return sorted(candidates, key=lambda row: (not row["licensed"], row["observation_event_id"]))[0]
    fetched = [event for event in events if event.event_type in {"fetch_body", "extracted_body"}]
    if fetched:
        first = fetched[0]
        prior = [item for item in discoveries if item.event_id < first.event_id]
        licensed = source_url in seeds or bool(prior)
        return {
            "observed": False,
            "content_observed": content_visible(first),
            "supported": False,
            "licensed": licensed,
            "observation_event_id": None,
            "observation_type": None,
            "discovery_event_id": (prior[-1].event_id if prior else None),
            "discovery_class": (
                "task_seed" if source_url in seeds else
                ("searched" if prior and prior[-1].event_type == "search_result" else "linked") if prior
                else "guessed_then_fetched"
            ),
        }
    if discoveries:
        last = discoveries[-1]
        return {
            "observed": False,
            "content_observed": any(content_visible(event) for event in discoveries),
            "supported": False,
            "licensed": True,
            "observation_event_id": None,
            "observation_type": None,
            "discovery_event_id": last.event_id,
            "discovery_class": "searched" if last.event_type == "search_result" else "linked",
        }
    return {
        "observed": False,
        "content_observed": False,
        "supported": False,
        "licensed": source_url in seeds,
        "observation_event_id": None,
        "observation_type": None,
        "discovery_event_id": None,
        "discovery_class": "task_seed" if source_url in seeds else "not_discovered",
    }


def _check_code(axis: str, passed: bool, success: str, failure: str) -> dict[str, Any]:
    return {"passed": bool(passed), "reason_code": success if passed else failure, "axis": axis}


def _evidence_result(
    slot: Mapping[str, Any],
    node: Mapping[str, Any],
    report: str,
    masked: str,
    citations: Sequence[Citation],
    ledger: ObservationLedger,
    sources: Mapping[str, Mapping[str, Any]],
    corpus_urls: set[str],
    seeds: set[str],
    *,
    expand_accepted_roles: bool = True,
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> tuple[dict[str, Any], set[str]]:
    slot_id = str(slot.get("slot_id") or "")
    if semantic_matches is None:
        matches = _find_matches(masked, [slot, node], node)
    else:
        semantic_match = _semantic_text_match(report, semantic_matches, slot_id)
        matches = [semantic_match] if semantic_match else []
    expected_urls = _source_urls(
        slot,
        node,
        sources,
        expand_accepted_roles=expand_accepted_roles,
    )
    best: Optional[dict[str, Any]] = None
    used: set[str] = set()
    for match in matches or [None]:
        local = _bound_citations(report, match, citations, slot) if match else []
        expected_cites = [cite for cite in local if cite.canonical_url in expected_urls]
        chosen = expected_cites[0] if expected_cites else (local[0] if local else None)
        c_ok = match is not None
        b_ok = bool(chosen and chosen.canonical_url in expected_urls)
        r_ok = bool(chosen and chosen.canonical_url in corpus_urls)
        # L/O audit the source the report actually bound locally.  Looking up
        # the expected URL after a wrong-page citation would misleadingly show
        # good provenance/observation for evidence the report did not cite.
        source_url = chosen.canonical_url if chosen else (expected_urls[0] if not local and expected_urls else "")
        observation = _observation_for_source(source_url, node, ledger, seeds) if source_url else {
            "observed": False, "content_observed": False, "supported": False,
            "licensed": False, "observation_event_id": None,
            "observation_type": None, "discovery_event_id": None, "discovery_class": "no_source_url",
        }
        row = {
            "match": match,
            "chosen": chosen,
            "C": c_ok,
            "B": b_ok,
            "R": r_ok,
            "L": bool(observation["licensed"]),
            "O": bool(observation["observed"]),
            "observation": observation,
            "source_url": source_url,
        }
        rank = sum(int(row[key]) for key in ("C", "B", "R", "L", "O"))
        if best is None or rank > best["rank"]:
            best = {**row, "rank": rank}
    assert best is not None
    verified = all(best[key] for key in ("C", "B", "R", "L", "O"))
    if best["B"] and best["chosen"]:
        used.add(best["chosen"].canonical_url)
    checks = {
        "C": _check_code("C", best["C"], "claim_correct", "claim_missing_or_incorrect"),
        "B": _check_code("B", best["B"], "citation_locally_bound", "citation_missing_wrong_or_detached"),
        "R": _check_code("R", best["R"], "citation_in_frozen_corpus", "citation_not_in_frozen_corpus"),
        "L": _check_code(
            "L", best["L"], "source_discovery_licensed",
            "guessed_then_fetched" if best["observation"]["discovery_class"] == "guessed_then_fetched" else "source_not_discovered",
        ),
        "O": _check_code("O", best["O"], "support_observed", "support_not_observed"),
    }
    result = {
        "slot_id": slot_id,
        "type": "evidence",
        "critical": bool(slot.get("critical", False)),
        "required": slot.get("required", True) is not False and slot.get("optional") is not True,
        "claim_id": slot.get("claim_id") or slot.get("evidence_id"),
        "requires": list(slot.get("requires") or []),
        "verified": verified,
        "C": best["C"], "B": best["B"], "R": best["R"], "L": best["L"], "O": best["O"],
        "content_observed": bool(best["observation"].get("content_observed")),
        "supported": bool(best["observation"].get("supported")),
        "checks": checks,
        "reason_codes": {key: value["reason_code"] for key, value in checks.items()},
        "matched_text": best["match"].text if best["match"] else None,
        "citation_url": best["chosen"].canonical_url if best["chosen"] else None,
        "expected_source_urls": expected_urls,
        **best["observation"],
    }
    return result, used


def _proof_evidence_result(
    slot: Mapping[str, Any],
    support_nodes: Sequence[tuple[str, Mapping[str, Any]]],
    report: str,
    masked: str,
    citations: Sequence[Citation],
    ledger: ObservationLedger,
    sources: Mapping[str, Mapping[str, Any]],
    corpus_urls: set[str],
    seeds: set[str],
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> tuple[dict[str, Any], set[str]]:
    """Choose the best fully audited route among proposition-bound sources."""

    candidates: list[tuple[tuple[int, ...], str, dict[str, Any], set[str]]] = []
    all_expected_urls: set[str] = set()
    all_source_ids: list[str] = []
    for source_id, node in support_nodes:
        candidate_slot = dict(slot)
        candidate_slot["source_ids"] = [source_id]
        candidate_slot["source_id"] = source_id
        result, used = _evidence_result(
            candidate_slot,
            node,
            report,
            masked,
            citations,
            ledger,
            sources,
            corpus_urls,
            seeds,
            expand_accepted_roles=False,
            semantic_matches=semantic_matches,
        )
        all_expected_urls.update(result.get("expected_source_urls") or [])
        all_source_ids.append(source_id)
        axis_values = tuple(
            int(bool(result.get(axis)))
            for axis in ("C", "B", "R", "L", "O")
        )
        rank = (
            int(bool(result.get("verified"))),
            sum(axis_values),
            *axis_values,
        )
        candidates.append((rank, source_id, result, used))
    if not candidates:
        # Shape validation normally prevents this.  Retaining a deterministic
        # failing candidate keeps draft diagnostics useful without widening
        # admissibility to same-role sources.
        result, used = _evidence_result(
            slot,
            {},
            report,
            masked,
            citations,
            ledger,
            sources,
            corpus_urls,
            seeds,
            expand_accepted_roles=False,
            semantic_matches=semantic_matches,
        )
        result["admissible_support_source_ids"] = []
        result["matched_support_source_id"] = None
        return result, used
    candidates.sort(key=lambda row: row[1])
    _, selected_source_id, selected, used = max(
        candidates,
        key=lambda row: row[0],
    )
    selected["expected_source_urls"] = sorted(all_expected_urls)
    selected["admissible_support_source_ids"] = sorted(set(all_source_ids))
    selected["matched_support_source_id"] = (
        selected_source_id if selected.get("B") else None
    )
    return selected, used


def _dependency_result(
    slot: Mapping[str, Any],
    slot_type: str,
    report_text: str,
    results: Mapping[str, Mapping[str, Any]],
    case: Mapping[str, Any],
    graph: Any,
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    dependencies = [str(dep) for dep in slot.get("requires") or []]
    failed = [dep for dep in dependencies if not bool(_get(results.get(dep), "verified", False))]
    rule = _resolve_rule(slot.get("rule"), case, graph, slot)
    slot_id = str(slot.get("slot_id") or "")
    if semantic_matches is None:
        rule_matches = _find_matches(report_text, [rule]) if rule else []
    else:
        semantic_match = _semantic_text_match(
            report_text, semantic_matches, slot_id
        )
        rule_matches = [semantic_match] if semantic_match else []
    rule_ok = bool(rule_matches)
    checks: dict[str, dict[str, Any]] = {
        "DEPENDENCIES": _check_code(
            "DEPENDENCIES", not failed, "dependencies_verified", "dependency_unverified"
        ),
        "RULE_OK": _check_code(
            "RULE_OK", rule_ok, f"{slot_type}_rule_explicit", f"{slot_type}_rule_missing"
        ),
    }
    conclusion: Optional[str] = None
    conclusion_ok = True
    admissibility: Optional[dict[str, Any]] = None
    if slot_type == "decision":
        conclusion_ok, conclusion, admissibility = _decision_conclusion(
            report_text, slot, rule, case, graph, semantic_matches
        )
        checks["CONCLUSION"] = _check_code(
            "CONCLUSION", conclusion_ok, "admissible_conclusion_explicit", "admissible_conclusion_missing"
        )
    verified = not failed and rule_ok and conclusion_ok
    result = {
        "slot_id": str(slot.get("slot_id") or ""),
        "type": slot_type,
        "critical": bool(slot.get("critical", False)),
        "required": slot.get("required", True) is not False and slot.get("optional") is not True,
        "requires": dependencies,
        "verified": verified,
        "failed_dependencies": failed,
        "rule_id": rule.get("rule_id") or (slot.get("rule") if isinstance(slot.get("rule"), str) else None),
        "rule_match": rule_matches[0].text if rule_matches else None,
        "checks": checks,
        "reason_codes": {key: value["reason_code"] for key, value in checks.items()},
    }
    if slot_type == "decision":
        result["conclusion"] = conclusion
        result["admissibility"] = admissibility
    return result


def _explicit_conclusion(text: str, answer: str, phrases: Sequence[Any]) -> Optional[TextMatch]:
    for phrase in phrases:
        matches = _phrase_matches(text, str(phrase))
        positive = [match for match in matches if not _negated_context(text, match)]
        if positive:
            return positive[0]
    if phrases:
        # Formal rules provide positive conclusion matchers.  Falling through
        # to a generic cue would turn "I do not recommend Alpha" into a pass.
        return None
    answer_pattern = re.escape(str(answer)).replace("_", r"[ _-]")
    patterns = [
        rf"(?:{_DECISION_CUE_RE.pattern})[^\n.!?。！？]{{0,100}}\b{answer_pattern}\b",
        rf"\b{answer_pattern}\b[^\n.!?。！？]{{0,100}}(?:{_DECISION_CUE_RE.pattern})",
    ]
    for pattern in patterns:
        matches = [
            match for match in _regex_matches(text, pattern)
            if not _negated_context(text, match)
        ]
        if matches:
            return matches[0]
    return None


def _condition_explicit(text: str, value: Any, case: Mapping[str, Any], graph: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(_find_matches(text, [value]))
    key = str(value or "")
    for owner in (case, _mapping(graph)):
        for catalog_key in ("conditions", "tradeoffs", "expressions"):
            catalog = owner.get(catalog_key)
            if isinstance(catalog, Mapping) and key in catalog:
                return bool(_find_matches(text, [_mapping(catalog[key])]))
    return bool(_phrase_matches(text, key.replace("_", " ")))


def _decision_conclusion(
    text: str,
    slot: Mapping[str, Any],
    rule: Mapping[str, Any],
    case: Mapping[str, Any],
    graph: Any,
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    alternatives = slot.get("acceptable_conclusions")
    if alternatives is None:
        alternatives = case.get("acceptable_conclusions")
    formal_case = _mapping(case.get("formal_bindings")).get("formal") is True
    conclusion_matchers = rule.get("conclusion_matchers")
    conditional_by_answer: dict[str, dict[str, Any]] = {}
    closest_answer: Optional[str] = None
    closest_detail: Optional[dict[str, Any]] = None
    for raw_condition in _list(rule.get("admissible_conditions")):
        condition = _mapping(raw_condition)
        answer_key = condition.get("answer") or condition.get("conclusion")
        if answer_key:
            conditional_by_answer[str(answer_key)] = condition
    for raw in _list(alternatives):
        alternative = _mapping(raw) if isinstance(raw, Mapping) or not isinstance(raw, str) else {"answer": raw}
        answer = alternative.get("answer") or alternative.get("conclusion") or alternative.get("value")
        if not answer:
            continue
        conditional = conditional_by_answer.get(str(answer), {})
        merged = dict(conditional)
        merged.update(alternative)
        alternative = merged
        typed_matcher = (
            _mapping(conclusion_matchers.get(str(answer)))
            if isinstance(conclusion_matchers, Mapping)
            else {}
        )
        if semantic_matches is None:
            typed_matches = _find_matches(text, [typed_matcher]) if typed_matcher else []
        else:
            semantic_match = _semantic_text_match(
                text,
                semantic_matches,
                f"{slot.get('slot_id')}::conclusion::{answer}",
            )
            typed_matches = [semantic_match] if semantic_match else []
        match = typed_matches[0] if typed_matches else None
        if not match and not formal_case and not typed_matcher:
            # Draft fixtures retain a narrow compatibility path.  Formal cases
            # are sealed against the typed conclusion_matchers map and may not
            # fall through to answer-name or generic decision-cue matching.
            phrases = _list(
                alternative.get("accepted_phrases")
                or alternative.get("conclusion_phrases")
            )
            if not phrases:
                catalog = rule.get("conclusion_phrases") or rule.get("decision_phrases")
                if isinstance(catalog, Mapping):
                    phrases = _list(catalog.get(str(answer)))
            conclusion_regexes = rule.get("conclusion_regexes")
            match = _explicit_conclusion(text, str(answer), phrases)
            if not match and isinstance(conclusion_regexes, Mapping):
                regex_matches = _find_matches(
                    text, [{"accepted_regexes": conclusion_regexes.get(str(answer))}]
                )
                match = regex_matches[0] if regex_matches else None
        if not match:
            continue
        when = alternative.get("when")
        condition_matcher = alternative.get("condition_matcher")
        if condition_matcher:
            when_ok = bool(_find_matches(text, [_mapping(condition_matcher)]))
        else:
            when_ok = True if not when else _condition_explicit(text, when, case, graph)
        tradeoffs = _list(alternative.get("required_tradeoffs"))
        tradeoff_matchers = alternative.get("tradeoff_matchers")
        missing_tradeoffs = []
        for tradeoff in tradeoffs:
            matcher = (
                tradeoff_matchers.get(str(tradeoff))
                if isinstance(tradeoff_matchers, Mapping) else None
            )
            present = (
                bool(_find_matches(text, [_mapping(matcher)])) if matcher
                else _condition_explicit(text, tradeoff, case, graph)
            )
            if not present:
                missing_tradeoffs.append(tradeoff)
        detail = {
            "answer": str(answer),
            "when_satisfied": when_ok,
            "missing_tradeoffs": missing_tradeoffs,
            "matched_text": match.text,
        }
        if when_ok and not missing_tradeoffs:
            return True, str(answer), detail
        closest_answer, closest_detail = str(answer), detail
    return False, closest_answer, closest_detail


def _score_research_subgoals(
    case: Mapping[str, Any],
    report_text: str,
    slot_results: Sequence[Mapping[str, Any]],
    graph: Any,
) -> tuple[Optional[float], list[dict[str, Any]], dict[str, Any]]:
    """Aggregate verified slots into complete local research questions.

    Evidence leaves are diagnostic prerequisites only; a subgoal must identify
    one required bridge/decision as ``local_conclusion_slot_id``.  That slot's
    already-verified rule is the conclusion atom, preventing both fact-dump
    credit and a second score-bearing matcher outside the proof DAG.
    """

    def type_completion(slot_type: str) -> dict[str, Any]:
        required_rows = [
            row for row in slot_results
            if row.get("type") == slot_type and row.get("required", True)
        ]
        verified = sum(1 for row in required_rows if row.get("verified"))
        return {
            "required": len(required_rows),
            "verified": verified,
            "completion": verified / len(required_rows) if required_rows else 0.0,
        }

    slot_type_completion = {
        slot_type: type_completion(slot_type)
        for slot_type in ("evidence", "bridge", "decision")
    }
    raw_subgoals = _get(case, "research_subgoals", None)
    if raw_subgoals is None:
        return None, [], {
            "available": False,
            "reason_code": "research_subgoals_missing",
            "required": 0,
            "passed": 0,
            "evidence_slots_verified": sum(
                1 for row in slot_results
                if row.get("type") == "evidence" and row.get("verified")
            ),
            "bridge_slots_verified": sum(
                1 for row in slot_results
                if row.get("type") == "bridge" and row.get("verified")
            ),
            "decision_slots_verified": sum(
                1 for row in slot_results
                if row.get("type") == "decision" and row.get("verified")
            ),
            "slot_type_completion": slot_type_completion,
        }
    by_id = {str(row.get("slot_id")): row for row in slot_results}
    results: list[dict[str, Any]] = []
    required_results: list[dict[str, Any]] = []
    for raw in _list(raw_subgoals):
        subgoal = _mapping(raw)
        subgoal_id = str(subgoal.get("subgoal_id") or subgoal.get("id") or "")
        requires = [str(value) for value in subgoal.get("requires") or []]
        missing = [slot_id for slot_id in requires if slot_id not in by_id]
        failed = [
            slot_id for slot_id in requires
            if slot_id in by_id and not bool(by_id[slot_id].get("verified"))
        ]
        reasoning_slots = [
            slot_id for slot_id in requires
            if slot_id in by_id and by_id[slot_id].get("type") in {"bridge", "decision"}
        ]
        conclusion_slot_id = str(subgoal.get("local_conclusion_slot_id") or "")
        conclusion_slot = by_id.get(conclusion_slot_id)
        structural_ok = bool(
            conclusion_slot_id
            and conclusion_slot_id in requires
            and conclusion_slot is not None
            and conclusion_slot.get("type") in {"bridge", "decision"}
        )
        # The local conclusion's deterministic expression has already been
        # verified by its bridge/decision slot.  Re-running a second matcher
        # here would create a score-bearing atom outside the proof DAG.
        conclusion_ok = bool(structural_ok and conclusion_slot.get("verified"))
        passed = not missing and not failed and structural_ok and conclusion_ok
        required = subgoal.get("required", subgoal.get("critical", True)) is not False
        checks = {
            "SLOTS": _check_code(
                "SLOTS", not missing and not failed,
                "subgoal_slots_verified", "subgoal_slot_unverified",
            ),
            "RESEARCH_SYNTHESIS": _check_code(
                "RESEARCH_SYNTHESIS", structural_ok,
                "subgoal_has_reasoning_slot", "evidence_leaf_only_not_completion",
            ),
            "LOCAL_CONCLUSION": _check_code(
                "LOCAL_CONCLUSION", conclusion_ok,
                "local_conclusion_correct", "local_conclusion_missing_or_incorrect",
            ),
        }
        result = {
            "subgoal_id": subgoal_id,
            "description": subgoal.get("description"),
            "required": required,
            "critical": bool(subgoal.get("critical", required)),
            "requires": requires,
            "missing_slots": missing,
            "failed_slots": failed,
            "reasoning_slots": reasoning_slots,
            "local_conclusion_slot_id": conclusion_slot_id or None,
            "local_conclusion_match": (
                conclusion_slot.get("rule_match") if conclusion_slot else None
            ),
            "passed": passed,
            "checks": checks,
            "reason_codes": {key: value["reason_code"] for key, value in checks.items()},
        }
        results.append(result)
        if required:
            required_results.append(result)
    passed_count = sum(1 for result in required_results if result["passed"])
    completion = passed_count / len(required_results) if required_results else 0.0
    diagnostics = {
        "available": True,
        "required": len(required_results),
        "passed": passed_count,
        "failed": len(required_results) - passed_count,
        "evidence_slots_verified": sum(
            1 for row in slot_results
            if row.get("type") == "evidence" and row.get("verified")
        ),
        "bridge_slots_verified": sum(
            1 for row in slot_results
            if row.get("type") == "bridge" and row.get("verified")
        ),
        "decision_slots_verified": sum(
            1 for row in slot_results
            if row.get("type") == "decision" and row.get("verified")
        ),
        "isolated_evidence_leaves_credit": 0,
        "slot_type_completion": slot_type_completion,
    }
    return completion, results, diagnostics


def _proof_step_results(
    steps: Sequence[Mapping[str, Any]],
    slot_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project verifier internals onto the frozen D/O/S/B/R step contract."""

    slots_by_id = {str(row.get("slot_id") or ""): row for row in slot_results}
    proof_by_id: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for step in steps:
        step_id = str(step.get("step_id") or step.get("slot_id") or "")
        row = slots_by_id.get(step_id, {})
        step_type = str(step.get("type") or row.get("type") or "unknown")
        dependencies = [str(value) for value in step.get("requires") or []]
        if step_type == "evidence":
            old_checks = _mapping(row.get("checks"))
            claim_ok = bool(row.get("C"))
            local_binding_ok = bool(row.get("B"))
            registry_ok = bool(row.get("R"))
            axes = {
                "D": bool(row.get("L")),
                "O": bool(row.get("content_observed", row.get("O"))),
                "S": bool(row.get("supported", row.get("O"))),
                "B": claim_ok and local_binding_ok and registry_ok,
                # A pure evidence leaf has the identity relation by definition.
                "R": True,
            }
            checks = {
                "D": _check_code(
                    "D",
                    axes["D"],
                    "source_discovery_licensed",
                    _get(old_checks.get("L"), "reason_code", "source_not_discovered"),
                ),
                "O": _check_code(
                    "O", axes["O"], "support_content_observed", "support_content_not_observed"
                ),
                "S": _check_code(
                    "S", axes["S"], "visible_content_supports_claim", "visible_content_does_not_support_claim"
                ),
                "B": _check_code(
                    "B",
                    axes["B"],
                    "claim_and_citation_locally_bound",
                    (
                        "claim_missing_or_incorrect"
                        if not claim_ok
                        else "citation_missing_wrong_or_detached"
                        if not local_binding_ok
                        else "citation_not_in_frozen_corpus"
                    ),
                ),
                "R": _check_code(
                    "R", True, "evidence_leaf_relation_identity", ""
                ),
            }
            extra = {
                "claim": step.get("claim") or step.get("claim_id"),
                "matched_text": row.get("matched_text"),
                "citation_urls": (
                    [row["citation_url"]] if row.get("citation_url") else []
                ),
                "expected_source_urls": list(row.get("expected_source_urls") or []),
                "admissible_support_source_ids": list(
                    row.get("admissible_support_source_ids") or []
                ),
                "matched_support_source_id": row.get(
                    "matched_support_source_id"
                ),
                "observation_event_id": row.get("observation_event_id"),
                "observation_type": row.get("observation_type"),
                "discovery_event_id": row.get("discovery_event_id"),
                "discovery_class": row.get("discovery_class"),
                "support_spans": _list(
                    step.get("support_spans")
                    or _get(step.get("acceptable_support"), "support_spans", [])
                ),
            }
        else:
            dependency_rows = [proof_by_id.get(dep, {}) for dep in dependencies]
            dependencies_present = bool(dependencies) and all(dependency_rows)
            dependencies_passed = bool(
                dependencies_present
                and all(bool(dep.get("passed")) for dep in dependency_rows)
            )
            old_checks = _mapping(row.get("checks"))
            rule_ok = bool(_get(old_checks.get("RULE_OK"), "passed", False))
            conclusion_ok = (
                bool(_get(old_checks.get("CONCLUSION"), "passed", False))
                if step_type == "decision"
                else True
            )
            axes = {
                "D": bool(
                    dependencies_present
                    and all(bool(dep.get("D")) for dep in dependency_rows)
                ),
                "O": bool(
                    dependencies_present
                    and all(bool(dep.get("O")) for dep in dependency_rows)
                ),
                "S": dependencies_passed,
                "B": bool(
                    dependencies_present
                    and all(bool(dep.get("B")) for dep in dependency_rows)
                ),
                "R": rule_ok and conclusion_ok,
            }
            checks = {
                "D": _check_code(
                    "D", axes["D"], "dependency_discovery_complete", "dependency_discovery_incomplete"
                ),
                "O": _check_code(
                    "O", axes["O"], "dependency_observation_complete", "dependency_observation_incomplete"
                ),
                "S": _check_code(
                    "S", axes["S"], "premises_passed", "premise_step_failed"
                ),
                "B": _check_code(
                    "B", axes["B"], "dependency_bindings_complete", "dependency_binding_incomplete"
                ),
                "R": _check_code(
                    "R",
                    axes["R"],
                    f"{step_type}_relation_explicit",
                    (
                        "final_answer_contract_failed"
                        if step_type == "decision" and rule_ok and not conclusion_ok
                        else f"{step_type}_relation_missing"
                    ),
                ),
            }
            extra = {
                "relation": step.get("relation") or step.get("rule"),
                "matched_text": row.get("rule_match"),
                "failed_dependencies": list(row.get("failed_dependencies") or []),
            }
            if step_type == "decision":
                extra.update({
                    "conclusion": row.get("conclusion"),
                    "admissibility": row.get("admissibility"),
                    "final_answer_pass": bool(row.get("verified")),
                })
        passed = all(axes.values())
        result = {
            "step_id": step_id,
            "type": step_type,
            "vital": bool(step.get("vital", step.get("critical", True))),
            "required": step.get("required", True) is not False,
            "requires": dependencies,
            "passed": passed,
            **axes,
            "checks": checks,
            "reason_codes": {
                axis: check["reason_code"] for axis, check in checks.items()
            },
            "route_branches": list(step.get("route_branches") or []),
            **extra,
        }
        proof_by_id[step_id] = result
        ordered.append(result)
    return ordered


def _coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required = len(rows)
    passed = sum(1 for row in rows if row.get("passed") is True)
    return {
        "required_steps": required,
        "passed_steps": passed,
        "coverage": passed / required if required else 0.0,
    }


def _route_coverage(step_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for step_type in ("evidence", "bridge", "decision"):
        label = "final_answer" if step_type == "decision" else step_type
        by_type[label] = _coverage(
            [row for row in step_results if row.get("type") == step_type]
        )
    branch_rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in step_results:
        for branch in row.get("route_branches") or []:
            branch_rows.setdefault(str(branch), []).append(row)
    return {
        "metric": "route_coverage_v1",
        "overall": _coverage(step_results),
        "by_type": by_type,
        "by_branch": {
            branch: _coverage(rows) for branch, rows in sorted(branch_rows.items())
        },
        "score_bearing": False,
    }


def _acquisition_diagnostics(
    step_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evidence = [row for row in step_results if row.get("type") == "evidence"]
    return {
        "metric": "acquisition_diagnostics_v1",
        "required_evidence_steps": len(evidence),
        "discovery_licensed": sum(1 for row in evidence if row.get("D") is True),
        "content_observed": sum(1 for row in evidence if row.get("O") is True),
        "content_supported": sum(1 for row in evidence if row.get("S") is True),
        "guessed_then_fetched": sum(
            1
            for row in evidence
            if row.get("discovery_class") == "guessed_then_fetched"
        ),
        "score_bearing": False,
    }


def _false_positives(
    case: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
    report_text: str,
    slots: Sequence[Mapping[str, Any]],
    semantic_matches: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> tuple[list[dict[str, Any]], int]:
    slot_critical: dict[str, bool] = {}
    for slot in slots:
        if slot.get("type") != "evidence":
            continue
        critical = bool(slot.get("critical", False))
        slot_critical[str(slot.get("slot_id") or "")] = critical
        slot_critical[str(slot.get("claim_id") or slot.get("evidence_id") or "")] = critical
    candidates: list[tuple[str, dict[str, Any]]] = []
    for index, raw in enumerate(_list(case.get("decidable_claims"))):
        claim = _mapping(raw)
        candidates.append((str(claim.get("claim_id") or claim.get("id") or f"decidable_{index}"), claim))
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim_id, claim in candidates:
        matcher = _mapping(claim.get("rejected_matcher"))
        if not matcher:
            continue
        objects = [matcher]
        if semantic_matches is None:
            matches = _find_matches(report_text, objects)
        else:
            semantic_match = _semantic_text_match(
                report_text, semantic_matches, f"rejected::{claim_id}"
            )
            matches = [semantic_match] if semantic_match else []
        if not matches or claim_id in seen:
            continue
        seen.add(claim_id)
        contradicts_slot_id = claim.get("contradicts_slot_id")
        critical = bool(
            claim.get(
                "critical",
                slot_critical.get(str(contradicts_slot_id or claim_id), False),
            )
        )
        found.append({
            "claim_id": claim_id,
            "contradicts_slot_id": contradicts_slot_id,
            "reason_code": "decidable_claim_contradicted",
            "matched_text": matches[0].text,
            "critical": critical,
        })
    return found, sum(1 for row in found if row["critical"])


def _unscored_sentences(
    masked_report: str,
    slot_results: Sequence[Mapping[str, Any]],
    false_positives: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Disclose substantive report sentences not mapped to a decidable atom.

    This is intentionally a coverage diagnostic, not an FP generator.  Open
    prose cannot be called wrong merely because the deterministic scorer lacks
    a verifier for it.
    """

    mapped_fragments: list[str] = []
    for row in slot_results:
        for value in (
            row.get("matched_text"),
            row.get("rule_match"),
            _get(row.get("admissibility"), "matched_text", None),
        ):
            if value:
                mapped_fragments.append(_normal(value))
    mapped_fragments.extend(
        _normal(row.get("matched_text"))
        for row in false_positives if row.get("matched_text")
    )
    unscored: list[dict[str, Any]] = []
    total = 0
    mapped = 0
    for match in re.finditer(r"[^\n.!?。！？]+(?:[.!?。！？]+|$)", masked_report):
        text = " ".join(match.group(0).split()).strip(" #*-\t")
        if not text:
            continue
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text)
        cjk = re.findall(r"[\u3400-\u9fff]", text)
        if len(words) < 4 and len(cjk) < 8:
            continue
        total += 1
        normalized = _normal(text)
        is_mapped = any(
            fragment and (fragment in normalized or normalized in fragment)
            for fragment in mapped_fragments
        )
        if is_mapped:
            mapped += 1
        else:
            unscored.append({
                "text": text,
                "char_start": match.start(),
                "char_end": match.end(),
                "reason_code": "no_deterministic_slot_mapping",
            })
    return unscored, mapped, total


def _coerce_ledger(value: Any, expected_run_id: Optional[str]) -> ObservationLedger:
    if isinstance(value, ObservationLedger):
        # Revalidate if a caller constructed the dataclass directly.
        value._validate(expected_run_id=expected_run_id)
        return value
    if value is None:
        return ObservationLedger.unavailable(
            "no_observation_ledger", "no observation ledger was provided", run_id=expected_run_id
        )
    if isinstance(value, (str, Path)):
        return load_observation_ledger(value, expected_run_id=expected_run_id)
    if isinstance(value, Mapping):
        if "events" in value:
            if value.get("observation_semantics") != OBSERVATION_SEMANTICS:
                return ObservationLedger.unavailable(
                    "observation_semantics_mismatch",
                    "in-memory ledger envelope has missing/wrong observation_semantics",
                    run_id=expected_run_id,
                )
            declared_run_id = value.get("run_id")
            if not isinstance(declared_run_id, str) or not declared_run_id.strip():
                return ObservationLedger.unavailable(
                    "observation_missing_run_id",
                    "in-memory ledger envelope requires a non-empty run_id",
                    run_id=expected_run_id,
                )
            if (
                expected_run_id is not None
                and declared_run_id != str(expected_run_id)
            ):
                return ObservationLedger.unavailable(
                    "observation_run_id_mismatch",
                    f"ledger run_id {declared_run_id!r} does not match expected "
                    f"{expected_run_id!r}",
                    run_id=declared_run_id,
                )
            if not isinstance(value.get("events"), list):
                return ObservationLedger.unavailable(
                    "observation_events_missing",
                    "in-memory ledger envelope requires an events array",
                    run_id=expected_run_id or declared_run_id,
                )
            if type(value.get("capture_complete")) is not bool:
                return ObservationLedger.unavailable(
                    "observation_capture_marker_missing",
                    "in-memory ledger envelope requires boolean capture_complete",
                    run_id=expected_run_id or declared_run_id,
                )
            return ObservationLedger.from_records(
                value.get("events") or [],
                expected_run_id=expected_run_id or declared_run_id,
                capture_complete=value.get("capture_complete") is True,
            )
        if "fetched" in value or "searches" in value:
            return adapt_run_evidence(value, expected_run_id=expected_run_id)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        # A bare list has no run-level completion attestation.  Keep it useful
        # for diagnostic normalization, but never promote it to a scoreable
        # formal trace.
        return ObservationLedger.from_records(
            value, expected_run_id=expected_run_id, capture_complete=False
        )
    return adapt_run_evidence(value, expected_run_id=expected_run_id)


def _attach_nonformal_legacy_aliases(
    result: dict[str, Any],
    *,
    slot_results: Sequence[Mapping[str, Any]],
    required_slot_ids: Sequence[str],
    tp: Optional[int],
    fn: Optional[int],
    fp: Optional[int],
    precision: Optional[float],
    recall: Optional[float],
    f1: Optional[float],
    research_completion: Optional[float],
    subgoal_results: Sequence[Mapping[str, Any]],
    completion_diagnostics: Optional[Mapping[str, Any]],
    evidence_completion: Optional[float],
    bridge_completion: Optional[float],
    decision_completion: Optional[float],
) -> None:
    """Expose old field names only on explicitly non-formal draft scores."""

    aliases = {
        "slot_results": list(slot_results),
        "required_slot_ids": list(required_slot_ids),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "verified_precision": precision,
        "verified_recall": recall,
        "verified_f1": f1,
        "verified_research_completion": research_completion,
        "research_subgoal_results": list(subgoal_results),
        "research_completion_diagnostics": (
            dict(completion_diagnostics)
            if isinstance(completion_diagnostics, Mapping)
            else completion_diagnostics
        ),
        "evidence_completion": evidence_completion,
        "bridge_completion": bridge_completion,
        "decision_completion": decision_completion,
        "task_pass": result.get("full_pass"),
    }
    result.update(aliases)
    result["legacy_compatibility_aliases"] = {
        "formal": False,
        "source_semantics": "verified_slots_v1",
        "canonical_semantics": SCORING_SEMANTICS,
        "fields": sorted(aliases),
    }


def _withheld_result(
    case: Mapping[str, Any],
    graph: Any,
    ledger: ObservationLedger,
    corpus_urls: set[str],
    corpus_registry_hash: Optional[str],
    corpus_url_set_hash: str,
    corpus_registry_source: str,
    citations: Sequence[Citation],
    protocol_manifest: Optional[Mapping[str, Any]] = None,
    corpus_registry_complete: bool = True,
    replay_identity: Optional[Mapping[str, Any]] = None,
    scoring_semantics: str = VERIFIED_SLOTS_SEMANTICS,
) -> dict[str, Any]:
    cited = sorted({citation.canonical_url for citation in citations})
    fabricated = sorted(set(cited) - corpus_urls) if corpus_registry_complete else []
    protocols = _protocols_for_score(
        case,
        corpus_registry_hash,
        corpus_url_set_hash,
        protocol_manifest,
        scoring_semantics,
    )
    if scoring_semantics == VERIFIED_SLOTS_SEMANTICS:
        return {
            **dict(replay_identity or {}),
            "task_id": case.get("task_id"),
            "cluster_id": case.get("cluster_id"),
            "status": "withheld",
            "withheld": True,
            "scorer_observability_complete": False,
            "withhold_reasons": [
                issue.to_dict() for issue in ledger.issues if issue.fatal
            ],
            "slot_results": [],
            "tp": None,
            "fn": None,
            "fp": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "task_pass": None,
            "verified_precision": None,
            "verified_recall": None,
            "verified_f1": None,
            "verified_research_completion": None,
            "research_subgoal_results": [],
            "research_completion_diagnostics": None,
            "evidence_completion": None,
            "bridge_completion": None,
            "decision_completion": None,
            "critical_contradictions": None,
            "fabricated_citations": (
                len(fabricated) if corpus_registry_complete else None
            ),
            "fabricated_citation_urls": (
                fabricated if corpus_registry_complete else None
            ),
            "unused_citations": (
                sorted(set(cited) & corpus_urls)
                if corpus_registry_complete
                else None
            ),
            "n_unused_citations": (
                len(set(cited) & corpus_urls)
                if corpus_registry_complete
                else None
            ),
            "unscored_claims": [],
            "scorer_coverage": None,
            "corpus_registry_hash": corpus_registry_hash,
            "corpus_url_set_hash": corpus_url_set_hash,
            "corpus_registry_source": corpus_registry_source,
            "corpus_registry_complete": corpus_registry_complete,
            "protocols": protocols,
        }
    formal_case = _mapping(case.get("formal_bindings")).get("formal") is True
    result = {
        **dict(replay_identity or {}),
        "task_id": case.get("task_id"),
        "cluster_id": case.get("cluster_id"),
        "scoring_semantics": SCORING_SEMANTICS,
        "status": "withheld",
        "withheld": True,
        "scorer_observability_complete": False,
        "withhold_reasons": [issue.to_dict() for issue in ledger.issues if issue.fatal],
        "step_results": [],
        "required_step_ids": [],
        "passed_steps": None,
        "required_steps": None,
        "partial_completion": None,
        "full_pass": None,
        "final_answer_pass": None,
        "full_pass_failure_reasons": [],
        "route_coverage": None,
        "acquisition_diagnostics": None,
        "critical_contradictions": None,
        "fabricated_citations": len(fabricated) if corpus_registry_complete else None,
        "fabricated_citation_urls": fabricated if corpus_registry_complete else None,
        "unused_citations": sorted(set(cited) & corpus_urls) if corpus_registry_complete else None,
        "n_unused_citations": len(set(cited) & corpus_urls) if corpus_registry_complete else None,
        "unscored_claims": [],
        "scorer_coverage": None,
        "corpus_registry_hash": corpus_registry_hash,
        "corpus_url_set_hash": corpus_url_set_hash,
        "corpus_registry_source": corpus_registry_source,
        "corpus_registry_complete": corpus_registry_complete,
        "protocols": protocols,
    }
    if not formal_case:
        _attach_nonformal_legacy_aliases(
            result,
            slot_results=[],
            required_slot_ids=[],
            tp=None,
            fn=None,
            fp=None,
            precision=None,
            recall=None,
            f1=None,
            research_completion=None,
            subgoal_results=[],
            completion_diagnostics=None,
            evidence_completion=None,
            bridge_completion=None,
            decision_completion=None,
        )
    return result


def score_case(
    case: Any,
    report: str,
    observation_ledger: Any,
    evidence_graph: Any = None,
    *,
    corpus_urls: Optional[Iterable[str]] = None,
    corpus_registry_hash: Optional[str] = None,
    seed_urls: Optional[Iterable[str]] = None,
    protocols: Optional[Mapping[str, Any]] = None,
    expected_run_id: Optional[str] = None,
    case_artifact_sha256: Optional[str] = None,
    public_task_sha256: Optional[str] = None,
    agent: Optional[str] = None,
    replicate: Optional[int] = None,
    scoring_semantics: str = VERIFIED_SLOTS_SEMANTICS,
    semantic_match_artifact: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Score one report against one v3 case.

    Parameters are dict-first but may be dataclass/Pydantic-like objects.
    ``corpus_urls`` should be the complete frozen registry; if omitted, the
    scorer reads ``corpus_registry_urls`` plus ``corpus_registry_hash`` from the
    graph/case.  A case subgraph is never silently treated as the full corpus.
    """

    if scoring_semantics not in {SCORING_SEMANTICS, VERIFIED_SLOTS_SEMANTICS}:
        raise ValueError(
            "scoring_semantics must be proof_steps_v1 or verified_slots_v1"
        )
    proof_step_mode = scoring_semantics == SCORING_SEMANTICS
    case_data = _mapping(case)
    report = str(report or "")
    masked = _mask_urls(report)
    # Materialize caller-provided iterables once.  Formal cases may compare
    # these values with compiler-bound inputs below; draft scoring keeps the
    # existing ability to supply ad-hoc registries and seed URLs.
    explicit_corpus_urls = None if corpus_urls is None else list(corpus_urls)
    explicit_seed_urls = None if seed_urls is None else list(seed_urls)
    formal_case = _mapping(case_data.get("formal_bindings")).get("formal") is True
    validated_case: Optional[CaseSpecV3] = None
    case_schema_issue: Optional[str] = None
    if formal_case:
        # This is deliberately the first formal gate.  Scoring permissive
        # dictionaries before validating the complete CaseSpecV3 would let a
        # malformed private gold artifact acquire numeric results merely by
        # carrying ``formal=true``.
        try:
            validated_case = validate_case(case_data)
        except (TypeError, ValueError) as exc:
            case_schema_issue = str(exc)
        else:
            case_data = validated_case.to_dict()
    proof_steps, proof_step_source = _normalize_proof_steps(case_data)
    proof_step_issues = _proof_step_shape_issues(
        proof_steps, source=proof_step_source, formal=formal_case
    )

    # Formal cases consume their compiler-bound evidence_sources.  Unverified
    # caller graph dictionaries must not override those sealed claim atoms.
    nodes = (
        {}
        if formal_case
        else _graph_nodes(evidence_graph or case_data.get("evidence_graph") or {})
    )
    scoring_graph = None if formal_case else evidence_graph
    sources = _source_catalog(case_data, scoring_graph)
    formal_input_issues: list[tuple[str, str]] = []
    effective_corpus_urls = explicit_corpus_urls
    effective_corpus_registry_hash = corpus_registry_hash
    if formal_case:
        # The compiler-bound registry is part of the exact case artifact and
        # protocol manifest.  An external registry may be supplied only as an
        # exact verification copy; it must never replace or extend the sealed
        # URL set (which could otherwise launder fabricated citations).
        compiled_urls = {
            _canon(url)
            for url in _list(case_data.get("corpus_registry_urls"))
            if _canon(url)
        }
        if explicit_corpus_urls is not None:
            supplied_urls = {
                _canon(url) for url in explicit_corpus_urls if _canon(url)
            }
            if supplied_urls != compiled_urls:
                formal_input_issues.append((
                    "formal_corpus_registry_override_invalid",
                    "explicit corpus URL set does not exactly match the "
                    "compiler-bound formal registry",
                ))
        if corpus_registry_hash is not None:
            supplied_hash = str(corpus_registry_hash).strip().lower()
            if supplied_hash.startswith("sha256:"):
                supplied_hash = supplied_hash.split(":", 1)[1]
            compiled_hash = str(case_data.get("corpus_registry_hash") or "").lower()
            if supplied_hash != compiled_hash:
                formal_input_issues.append((
                    "formal_corpus_registry_override_invalid",
                    "explicit corpus registry hash does not match the "
                    "compiler-bound formal registry",
                ))
        # Always score from the sealed case values after the equality audit.
        effective_corpus_urls = None
        effective_corpus_registry_hash = None
        if explicit_seed_urls:
            formal_input_issues.append((
                "formal_seed_override_forbidden",
                "formal scoring forbids caller-supplied seed URLs; discovery "
                "roots come only from the compiled case",
            ))
    registry, registry_source, registry_hash, url_set_hash, registry_issue = _corpus_registry(
        case_data,
        scoring_graph,
        nodes,
        sources,
        effective_corpus_urls,
        effective_corpus_registry_hash,
    )
    citations = extract_citations(report, sandbox_only=False)
    ledger = _coerce_ledger(observation_ledger, expected_run_id)
    report_sha256 = sha256_bytes(report.encode("utf-8"))
    semantic_matches: Optional[dict[str, dict[str, Any]]] = None
    if semantic_match_artifact is not None:
        from src.eval.semantic_matcher import semantic_index

        semantic_matches = semantic_index(
            semantic_match_artifact,
            report,
            case_sha256=case_artifact_sha256,
        )
    observation_ledger_sha256 = _canonical_json_digest(ledger.to_dict())
    validated_protocols: Optional[dict[str, Any]] = None
    validated_manifest: Optional[dict[str, Any]] = None
    if formal_case:
        for code, message in formal_input_issues:
            ledger.issues.append(LedgerIssue(code, message))
        if proof_step_mode:
            for message in proof_step_issues:
                ledger.issues.append(LedgerIssue(
                    "formal_proof_steps_invalid", message
                ))
        if case_schema_issue is not None:
            ledger.issues.append(LedgerIssue(
                "formal_case_schema_invalid",
                f"formal CaseSpecV3 validation failed: {case_schema_issue}",
            ))
        attribution_errors: list[str] = []
        if not isinstance(agent, str) or not agent.strip():
            attribution_errors.append("agent must be a non-empty string")
        if type(replicate) is not int or replicate < 1:
            attribution_errors.append("replicate must be a positive integer")
        if not re.fullmatch(r"[0-9a-f]{64}", str(public_task_sha256 or "")):
            attribution_errors.append(
                "public_task_sha256 must bind exact public task bytes"
            )
        if attribution_errors:
            ledger.issues.append(LedgerIssue(
                "formal_replay_identity_invalid",
                "; ".join(attribution_errors),
            ))
        if protocols is None:
            ledger.issues.append(LedgerIssue(
                "protocol_manifest_missing",
                "formal case scoring requires a sealed v3 protocol manifest",
            ))
        elif validated_case is not None:
            (
                validated_protocols,
                validated_manifest,
                protocol_issue,
            ) = _validate_protocol_manifest_for_case(
                protocols,
                validated_case,
                registry_hash,
                case_artifact_sha256,
                public_task_sha256,
                scoring_semantics,
            )
            if protocol_issue:
                ledger.issues.append(LedgerIssue(
                    "protocol_manifest_invalid", protocol_issue
                ))
    elif protocols is not None:
        # A sealed protocol is meaningful only for a compiler-validated formal
        # case.  A draft cannot become formal by injecting a manifest at score
        # time.
        ledger.issues.append(LedgerIssue(
            "draft_protocol_manifest_forbidden",
            "a draft case cannot consume a formal protocol manifest",
        ))
    if registry_issue:
        ledger.issues.append(LedgerIssue("corpus_registry_unavailable", registry_issue))
    protocol_manifest_sha256 = (
        str(validated_manifest.get("manifest_sha256"))
        if validated_manifest is not None
        else None
    )
    replay_identity = _replay_identity(
        task_id=(
            case_data.get("task_id")
            if isinstance(case_data.get("task_id"), str) else None
        ),
        cluster_id=(
            case_data.get("cluster_id")
            if isinstance(case_data.get("cluster_id"), str) else None
        ),
        agent=agent if isinstance(agent, str) else None,
        replicate=replicate if type(replicate) is int else None,
        ledger=ledger,
        observation_ledger_sha256=observation_ledger_sha256,
        report_sha256=report_sha256,
        case_artifact_sha256=case_artifact_sha256,
        public_task_sha256=(
            public_task_sha256 if isinstance(public_task_sha256, str) else None
        ),
        protocol_manifest_sha256=protocol_manifest_sha256,
        corpus_registry_hash=registry_hash,
        scoring_semantics=scoring_semantics,
    )
    if not ledger.complete:
        return _withheld_result(
            case_data,
            evidence_graph,
            ledger,
            registry,
            registry_hash,
            url_set_hash,
            registry_source,
            citations,
            validated_protocols,
            registry_issue is None,
            replay_identity,
            scoring_semantics,
        )

    slots = (
        proof_steps
        if proof_step_mode
        else [_mapping(slot) for slot in _list(case_data.get("slots"))]
    )
    seeds = _seed_urls(case_data)
    if explicit_seed_urls is not None:
        seeds.update(_canon(url) for url in explicit_seed_urls if _canon(url))
    results: dict[str, dict[str, Any]] = {}
    used_citation_urls: set[str] = set()
    for slot in slots:
        if str(slot.get("type") or "").lower() != "evidence":
            continue
        if proof_step_mode:
            result, used = _proof_evidence_result(
                slot,
                _resolve_support_nodes(slot, nodes, sources),
                report,
                masked,
                citations,
                ledger,
                sources,
                registry,
                seeds,
                semantic_matches,
            )
        else:
            node = _resolve_node(slot, nodes, sources)
            result, used = _evidence_result(
                slot,
                node,
                report,
                masked,
                citations,
                ledger,
                sources,
                registry,
                seeds,
                semantic_matches=semantic_matches,
            )
        results[result["slot_id"]] = result
        used_citation_urls.update(used)

    # Evaluate dependency slots in topological waves.  A malformed cycle stays
    # an observed failure with an explicit dependency code; case compilation is
    # responsible for rejecting it before a formal panel is frozen.
    pending = [slot for slot in slots if str(slot.get("type") or "").lower() in {"bridge", "decision"}]
    while pending:
        progressed = False
        for slot in list(pending):
            deps = [str(dep) for dep in slot.get("requires") or []]
            if any(dep not in results for dep in deps):
                continue
            slot_type = str(slot.get("type")).lower()
            result = _dependency_result(
                slot, slot_type, report if semantic_matches is not None else masked,
                results, case_data, scoring_graph, semantic_matches
            )
            results[result["slot_id"]] = result
            pending.remove(slot)
            progressed = True
        if not progressed:
            for slot in pending:
                slot_type = str(slot.get("type")).lower()
                result = _dependency_result(
                    slot, slot_type, report if semantic_matches is not None else masked,
                    results, case_data, scoring_graph, semantic_matches
                )
                result["reason_codes"]["DEPENDENCIES"] = "dependency_missing_or_cyclic"
                result["checks"]["DEPENDENCIES"]["passed"] = False
                result["checks"]["DEPENDENCIES"]["reason_code"] = "dependency_missing_or_cyclic"
                result["verified"] = False
                results[result["slot_id"]] = result
            break

    for slot in slots:
        slot_id = str(slot.get("slot_id") or "")
        if slot_id in results:
            continue
        results[slot_id] = {
            "slot_id": slot_id,
            "type": str(slot.get("type") or "unknown"),
            "critical": bool(slot.get("critical", False)),
            "required": slot.get("required", True) is not False and slot.get("optional") is not True,
            "requires": list(slot.get("requires") or []),
            "verified": False,
            "checks": {"TYPE": _check_code("TYPE", False, "", "unsupported_slot_type")},
            "reason_codes": {"TYPE": "unsupported_slot_type"},
        }

    ordered = [results[str(slot.get("slot_id") or "")] for slot in slots]
    required = [row for row in ordered if row.get("required")]
    tp = sum(1 for row in required if row.get("verified"))
    fn = len(required) - tp
    false_positive_claims, critical_contradictions = _false_positives(
        case_data, nodes, report if semantic_matches is not None else masked,
        slots, semantic_matches
    )
    fp = len(false_positive_claims)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * tp) / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0

    cited_urls = {citation.canonical_url for citation in citations}
    fabricated_urls = sorted(cited_urls - registry)
    real_urls = cited_urls & registry
    unused_urls = sorted(real_urls - used_citation_urls)
    legacy_critical_ok = all(
        row.get("verified") for row in ordered if row.get("critical")
    )
    legacy_decisions = [
        row
        for row in ordered
        if row.get("type") == "decision" and row.get("required")
    ]
    legacy_decision_ok = bool(legacy_decisions) and all(
        row.get("verified") for row in legacy_decisions
    )
    legacy_task_pass = int(
        legacy_critical_ok
        and legacy_decision_ok
        and critical_contradictions == 0
        and not fabricated_urls
    )
    step_results = _proof_step_results(proof_steps, ordered)
    required_step_results = [
        row for row in step_results if row.get("required") is True
    ]
    required_steps = len(required_step_results)
    passed_steps = sum(
        1 for row in required_step_results if row.get("passed") is True
    )
    partial_completion = (
        passed_steps / required_steps if required_steps else 0.0
    )
    vital_failures = [
        str(row.get("step_id"))
        for row in required_step_results
        if row.get("vital") is True and row.get("passed") is not True
    ]
    final_steps = [
        row for row in required_step_results if row.get("type") == "decision"
    ]
    final_answer_pass = bool(final_steps) and all(
        row.get("passed") is True for row in final_steps
    )
    full_pass = int(
        not vital_failures
        and final_answer_pass
        and critical_contradictions == 0
        and not fabricated_urls
    )
    full_pass_failure_reasons: list[dict[str, Any]] = []
    if vital_failures:
        full_pass_failure_reasons.append({
            "reason_code": "vital_proof_steps_failed",
            "step_ids": vital_failures,
        })
    if not final_answer_pass:
        full_pass_failure_reasons.append({
            "reason_code": "final_answer_contract_failed",
            "step_ids": [str(row.get("step_id")) for row in final_steps],
        })
    if critical_contradictions:
        full_pass_failure_reasons.append({
            "reason_code": "critical_contradictions_present",
            "count": critical_contradictions,
        })
    if fabricated_urls:
        full_pass_failure_reasons.append({
            "reason_code": "fabricated_citations_present",
            "count": len(fabricated_urls),
        })
    route_coverage = _route_coverage(required_step_results)
    acquisition_diagnostics = _acquisition_diagnostics(required_step_results)
    research_completion, subgoal_results, completion_diagnostics = _score_research_subgoals(
        case_data, masked, ordered, scoring_graph
    )
    type_completion = completion_diagnostics["slot_type_completion"]
    unscored_claims, mapped_sentences, substantive_sentences = _unscored_sentences(
        masked, ordered, false_positive_claims
    )
    n_decidable = len(required) + len(false_positive_claims)
    protocols = _protocols_for_score(
        case_data,
        registry_hash,
        url_set_hash,
        validated_protocols,
        scoring_semantics,
    )
    if not proof_step_mode:
        legacy_ordered = [
            {
                key: value
                for key, value in row.items()
                if key not in {"content_observed", "supported"}
            }
            for row in ordered
        ]
        return {
            **replay_identity,
            "task_id": case_data.get("task_id"),
            "cluster_id": case_data.get("cluster_id"),
            "status": "scored",
            "withheld": False,
            "scorer_observability_complete": True,
            "withhold_reasons": [],
            "slot_results": legacy_ordered,
            "required_slot_ids": [row["slot_id"] for row in required],
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "verified_precision": precision,
            "verified_recall": recall,
            "verified_f1": f1,
            "verified_research_completion": research_completion,
            "research_subgoal_results": subgoal_results,
            "research_completion_diagnostics": completion_diagnostics,
            "evidence_completion": type_completion["evidence"]["completion"],
            "bridge_completion": type_completion["bridge"]["completion"],
            "decision_completion": type_completion["decision"]["completion"],
            "task_pass": legacy_task_pass,
            "critical_contradictions": critical_contradictions,
            "false_positive_claims": false_positive_claims,
            "fabricated_citations": len(fabricated_urls),
            "fabricated_citation_urls": fabricated_urls,
            "unused_citations": unused_urls,
            "n_unused_citations": len(unused_urls),
            "used_citations": sorted(used_citation_urls),
            "unscored_claims": unscored_claims,
            "scorer_coverage": {
                "required_slots": len(required),
                "decidable_claims_checked": n_decidable,
                "substantive_report_sentences": substantive_sentences,
                "mapped_report_sentences": mapped_sentences,
                "report_claims_unscored": len(unscored_claims),
                "sentence_mapping_rate": (
                    mapped_sentences / substantive_sentences
                    if substantive_sentences
                    else 0.0
                ),
            },
            "corpus_registry_hash": registry_hash,
            "corpus_url_set_hash": url_set_hash,
            "corpus_registry_source": registry_source,
            "corpus_registry_complete": True,
            "protocols": protocols,
        }
    score = {
        **replay_identity,
        "task_id": case_data.get("task_id"),
        "cluster_id": case_data.get("cluster_id"),
        "scoring_semantics": SCORING_SEMANTICS,
        "report_match_semantics": (
            str(semantic_match_artifact.get("matching_semantics"))
            if semantic_match_artifact is not None
            else "frozen_phrase_match_v1"
        ),
        "semantic_match_artifact_sha256": (
            _canonical_json_digest(semantic_match_artifact)
            if semantic_match_artifact is not None else None
        ),
        "status": "scored",
        "withheld": False,
        "scorer_observability_complete": True,
        "withhold_reasons": [],
        "step_results": step_results,
        "required_step_ids": [
            str(row["step_id"]) for row in required_step_results
        ],
        "passed_steps": passed_steps,
        "required_steps": required_steps,
        "partial_completion": partial_completion,
        "full_pass": full_pass,
        "final_answer_pass": final_answer_pass,
        "full_pass_failure_reasons": full_pass_failure_reasons,
        "route_coverage": route_coverage,
        "acquisition_diagnostics": acquisition_diagnostics,
        "critical_contradictions": critical_contradictions,
        "false_positive_claims": false_positive_claims,
        "fabricated_citations": len(fabricated_urls),
        "fabricated_citation_urls": fabricated_urls,
        "unused_citations": unused_urls,
        "n_unused_citations": len(unused_urls),
        "used_citations": sorted(used_citation_urls),
        "unscored_claims": unscored_claims,
        "scorer_coverage": {
            "required_steps": required_steps,
            "decidable_claims_checked": n_decidable,
            "substantive_report_sentences": substantive_sentences,
            "mapped_report_sentences": mapped_sentences,
            "report_claims_unscored": len(unscored_claims),
            "sentence_mapping_rate": (
                mapped_sentences / substantive_sentences if substantive_sentences else 0.0
            ),
        },
        "corpus_registry_hash": registry_hash,
        "corpus_url_set_hash": url_set_hash,
        "corpus_registry_source": registry_source,
        "corpus_registry_complete": True,
        "protocols": protocols,
    }
    if not formal_case:
        _attach_nonformal_legacy_aliases(
            score,
            slot_results=ordered,
            required_slot_ids=[str(row["slot_id"]) for row in required],
            tp=tp,
            fn=fn,
            fp=fp,
            precision=precision,
            recall=recall,
            f1=f1,
            research_completion=research_completion,
            subgoal_results=subgoal_results,
            completion_diagnostics=completion_diagnostics,
            evidence_completion=type_completion["evidence"]["completion"],
            bridge_completion=type_completion["bridge"]["completion"],
            decision_completion=type_completion["decision"]["completion"],
        )
    return score


class VerifiedSlotScorer:
    """Reusable scorer bound to a case and frozen evidence graph."""

    def __init__(
        self,
        case: Any,
        evidence_graph: Any = None,
        *,
        corpus_urls: Optional[Iterable[str]] = None,
        corpus_registry_hash: Optional[str] = None,
        seed_urls: Optional[Iterable[str]] = None,
        protocols: Optional[Mapping[str, Any]] = None,
        case_artifact_sha256: Optional[str] = None,
        public_task_sha256: Optional[str] = None,
        agent: Optional[str] = None,
        replicate: Optional[int] = None,
    ) -> None:
        self.case = case
        self.evidence_graph = evidence_graph
        self.corpus_urls = None if corpus_urls is None else list(corpus_urls)
        self.corpus_registry_hash = corpus_registry_hash
        self.seed_urls = None if seed_urls is None else list(seed_urls)
        self.protocols = None if protocols is None else dict(protocols)
        self.case_artifact_sha256 = case_artifact_sha256
        self.public_task_sha256 = public_task_sha256
        self.agent = agent
        self.replicate = replicate

    def score(
        self,
        report: str,
        observation_ledger: Any,
        *,
        expected_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return score_case(
            self.case,
            report,
            observation_ledger,
            self.evidence_graph,
            corpus_urls=self.corpus_urls,
            corpus_registry_hash=self.corpus_registry_hash,
            seed_urls=self.seed_urls,
            protocols=self.protocols,
            expected_run_id=expected_run_id,
            case_artifact_sha256=self.case_artifact_sha256,
            public_task_sha256=self.public_task_sha256,
            agent=self.agent,
            replicate=self.replicate,
            scoring_semantics=VERIFIED_SLOTS_SEMANTICS,
        )


class ProofStepScorer(VerifiedSlotScorer):
    """Reusable scorer for the independent ``proof_steps_v1`` protocol."""

    def score(
        self,
        report: str,
        observation_ledger: Any,
        *,
        expected_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return score_case(
            self.case,
            report,
            observation_ledger,
            self.evidence_graph,
            corpus_urls=self.corpus_urls,
            corpus_registry_hash=self.corpus_registry_hash,
            seed_urls=self.seed_urls,
            protocols=self.protocols,
            expected_run_id=expected_run_id,
            case_artifact_sha256=self.case_artifact_sha256,
            public_task_sha256=self.public_task_sha256,
            agent=self.agent,
            replicate=self.replicate,
            scoring_semantics=SCORING_SEMANTICS,
        )


def score_verified_slots(
    case: Any,
    report: str,
    observation_ledger: Any,
    evidence_graph: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Replay the preserved ``verified_slots_v1`` scorer."""

    kwargs.pop("scoring_semantics", None)
    return score_case(
        case,
        report,
        observation_ledger,
        evidence_graph,
        scoring_semantics=VERIFIED_SLOTS_SEMANTICS,
        **kwargs,
    )


def score_proof_steps(
    case: Any,
    report: str,
    observation_ledger: Any,
    evidence_graph: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Score the new required-proof-step protocol without legacy fields."""

    kwargs.pop("scoring_semantics", None)
    return score_case(
        case,
        report,
        observation_ledger,
        evidence_graph,
        scoring_semantics=SCORING_SEMANTICS,
        **kwargs,
    )


__all__ = [
    "SCORING_SEMANTICS",
    "VERIFIED_SLOTS_SEMANTICS",
    "HEADLINE_METRICS",
    "DIAGNOSTIC_METRICS",
    "PARTIAL_COMPLETION_METRIC",
    "FULL_PASS_METRIC",
    "VerifiedSlotScorer",
    "ProofStepScorer",
    "score_case",
    "score_verified_slots",
    "score_proof_steps",
]
