"""Replayable oracle and adversarial validation for DRA v3.

This module validates reports by calling :func:`src.eval.slot_scorer.score_case`.
It never accepts a pre-computed score from a suite file.  The suite therefore
tests the same deterministic path used for an agent run: compiled case, frozen
evidence graph, report, and complete observation ledger.

Human work is deliberately not automated.  A human oracle must carry a manual
record (reviewer, elapsed solve time, access path, and attestation), and its
report and ledger are replayed just like every other oracle.  Synthetic suites
remain permanently labelled as mechanism tests and can never be promoted into
evidence that a production pilot or a formal human audit passed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.eval.observation_ledger import ObservationLedger, load_observation_ledger
from src.eval.slot_scorer import (
    SCORING_SEMANTICS,
    VERIFIED_SLOTS_SEMANTICS,
    score_proof_steps,
    score_verified_slots,
)
from src.verifiers.citation_format import canonicalize_url


SUITE_SCHEMA = "dra_v3_oracle_suite_v1"
VALIDATION_SCHEMA = "dra_v3_oracle_suite_validation_v1"
VALIDATION_SEMANTICS = "oracle_adversarial_replay_v1"
VALIDATION_SCOPES = frozenset({"synthetic_test", "formal"})
CORE_ORACLE_KINDS = frozenset({"machine", "human", "minimal"})
ADMISSIBLE_ORACLE_KIND = "admissible_alternative"
REQUIRED_ADVERSARIAL_CATEGORIES = (
    "url_dump",
    "correct_plus_fabricated",
    "fetch_all_no_answer",
    "unsupported_answer",
    "fact_dump",
    "single_source",
    "guessed_then_fetched",
    "wrong_binding",
    "contradictory_decision",
    "silence",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_FIELDS = {
    "schema",
    "suite_id",
    "validation_scope",
    "case",
    "public_task",
    "evidence_graph",
    "protocols",
    "oracles",
    "adversarial",
    "scoring_semantics",
}

_LEGACY_SCORE_FIELDS = frozenset({
    "slot_results",
    "required_slot_ids",
    "tp",
    "fn",
    "fp",
    "precision",
    "recall",
    "f1",
    "verified_precision",
    "verified_recall",
    "verified_f1",
    "verified_research_completion",
    "research_subgoal_results",
    "research_completion_diagnostics",
    "evidence_completion",
    "bridge_completion",
    "decision_completion",
    "task_pass",
    "legacy_compatibility_aliases",
})
_ORACLE_FIELDS = {
    "run_id",
    "kind",
    "answer",
    "report",
    "ledger",
    "expected",
    "minimal_evidence_ids",
    "manual_record",
}
_ADVERSARIAL_FIELDS = {
    "run_id",
    "category",
    "answer",
    "report",
    "ledger",
    "expected",
}
_ARTIFACT_FIELDS = {"inline", "path", "sha256"}
_MANUAL_FIELDS = {
    "origin",
    "reviewer",
    "solve_minutes",
    "access_path",
    "attested",
    "synthetic",
}
_CONTENT_EVENT_TYPES = frozenset({"search_result", "fetch_body", "extracted_body"})


class OracleSuiteValidationError(ValueError):
    """Raised when a suite is incomplete, non-replayable, or behaves wrongly."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one JSON representation used by suite and result hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _canon_url(value: Any) -> str:
    raw = str(value or "").strip()
    return canonicalize_url(raw) if raw else ""


def _normal_identifier_text(value: Any) -> str:
    return " ".join(
        re.sub(r"[_-]+", " ", str(value or "")).casefold().split()
    )


def _strict_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OracleSuiteValidationError(f"{label} must be a JSON object")
    return dict(value)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], *, label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise OracleSuiteValidationError(f"{label} has unknown fields: {unknown}")


@dataclass(frozen=True)
class _LoadedArtifact:
    value: Any
    audit: dict[str, Any]
    resolved_path: Path | None = None


def _safe_artifact_path(raw_path: Any, base_dir: Path | None, *, label: str) -> Path:
    if base_dir is None:
        raise OracleSuiteValidationError(
            f"{label} uses a path but no suite base directory was supplied"
        )
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise OracleSuiteValidationError(f"{label} path must be a non-empty string")
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise OracleSuiteValidationError(
            f"{label} path must be relative and cannot traverse the suite directory"
        )
    root = base_dir.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise OracleSuiteValidationError(
            f"{label} path resolves outside the suite directory"
        ) from exc
    if not resolved.is_file():
        raise OracleSuiteValidationError(f"{label} artifact is not a file: {raw_path}")
    return resolved


def _read_stable(path: Path, *, label: str) -> bytes:
    try:
        first = path.read_bytes()
        second = path.read_bytes()
    except OSError as exc:
        raise OracleSuiteValidationError(f"cannot read {label}: {exc}") from exc
    if sha256_bytes(first) != sha256_bytes(second):
        raise OracleSuiteValidationError(f"{label} changed while being loaded")
    return first


def _load_artifact(
    raw: Any,
    *,
    label: str,
    value_type: str,
    base_dir: Path | None,
) -> _LoadedArtifact:
    """Load one inline/path artifact and bind paths to an exact raw hash."""

    wrapper = _strict_mapping(raw, label=label)
    _reject_unknown(wrapper, _ARTIFACT_FIELDS, label=label)
    has_inline = "inline" in wrapper
    has_path = "path" in wrapper
    if has_inline == has_path:
        raise OracleSuiteValidationError(
            f"{label} must declare exactly one of inline or path"
        )
    declared_hash = wrapper.get("sha256")
    if declared_hash is not None and not _SHA256_RE.fullmatch(str(declared_hash)):
        raise OracleSuiteValidationError(f"{label} sha256 must be 64 lowercase hex")

    if has_path:
        if declared_hash is None:
            raise OracleSuiteValidationError(
                f"{label} path artifacts require an exact sha256 to prevent path drift"
            )
        path = _safe_artifact_path(wrapper["path"], base_dir, label=label)
        payload = _read_stable(path, label=label)
        actual_hash = sha256_bytes(payload)
        if actual_hash != declared_hash:
            raise OracleSuiteValidationError(
                f"{label} sha256 mismatch: expected {declared_hash}, got {actual_hash}"
            )
        audit = {
            "source": "path",
            "relative_path": str(Path(str(wrapper["path"]))),
            "sha256": actual_hash,
            "hash_basis": "raw_bytes",
        }
        if value_type == "text":
            try:
                value = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise OracleSuiteValidationError(f"{label} is not UTF-8 text") from exc
        elif value_type == "ledger":
            # Let observation_ledger load JSON, JSONL, legacy brackets, and
            # content-addressed sibling blobs.  The exact ledger bytes were
            # already pinned above; the caller verifies them once more after
            # loading to close the read/replay race.
            value = path
        else:
            try:
                value = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OracleSuiteValidationError(f"{label} is not valid UTF-8 JSON") from exc
        return _LoadedArtifact(
            value=value,
            audit=audit,
            resolved_path=path if value_type == "ledger" else None,
        )

    value = wrapper["inline"]
    if value_type == "text":
        if not isinstance(value, str):
            raise OracleSuiteValidationError(f"{label} inline value must be text")
        payload = value.encode("utf-8")
        hash_basis = "utf8_text"
    else:
        payload = canonical_json_bytes(value)
        hash_basis = "canonical_json"
    actual_hash = sha256_bytes(payload)
    if declared_hash is not None and actual_hash != declared_hash:
        raise OracleSuiteValidationError(
            f"{label} inline sha256 mismatch: expected {declared_hash}, got {actual_hash}"
        )
    return _LoadedArtifact(
        value=value,
        audit={
            "source": "inline",
            "sha256": actual_hash,
            "hash_basis": hash_basis,
        },
    )


def _ledger_events(ledger: Any) -> list[dict[str, Any]]:
    if isinstance(ledger, ObservationLedger):
        return [event.to_dict() for event in ledger.events]
    if not isinstance(ledger, Mapping):
        return []
    events = ledger.get("events")
    if not isinstance(events, list):
        return []
    return [dict(event) for event in events if isinstance(event, Mapping)]


def _materialize_ledger(artifact: _LoadedArtifact, *, run_id: str) -> Any:
    if artifact.resolved_path is None:
        return artifact.value
    ledger = load_observation_ledger(
        artifact.resolved_path,
        expected_run_id=run_id,
    )
    after = sha256_bytes(_read_stable(artifact.resolved_path, label=f"ledger {run_id}"))
    if after != artifact.audit["sha256"]:
        raise OracleSuiteValidationError(
            f"ledger {run_id} changed between hash verification and replay"
        )
    return ledger


def _access_path(ledger: Any) -> list[str]:
    """Chronological content path, with immediately repeated URLs collapsed."""

    path: list[str] = []
    for event in _ledger_events(ledger):
        if event.get("event_type") not in _CONTENT_EVENT_TYPES:
            continue
        url = _canon_url(
            event.get("canonical_url") or event.get("url") or event.get("request_url")
        )
        if url and (not path or path[-1] != url):
            path.append(url)
    return path


def _slot_rows(score: Mapping[str, Any], slot_type: str) -> list[dict[str, Any]]:
    rows = score.get("slot_results")
    if not isinstance(rows, list):
        return []
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("type") == slot_type
    ]


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise OracleSuiteValidationError(message)


def _require_scored(score: Mapping[str, Any], *, run_id: str) -> None:
    _require(
        score.get("status") == "scored" and score.get("withheld") is False,
        f"run {run_id} was withheld instead of deterministically scored",
    )
    _require(
        score.get("scorer_observability_complete") is True,
        f"run {run_id} lacks complete scorer observability",
    )


def _check_declared_expected(
    score: Mapping[str, Any], expected: Any, *, run_id: str
) -> None:
    if expected is None:
        return
    expected_map = _strict_mapping(expected, label=f"run {run_id} expected")
    for key, value in sorted(expected_map.items()):
        if key not in score:
            raise OracleSuiteValidationError(
                f"run {run_id} expected unknown score field {key!r}"
            )
        if score[key] != value:
            raise OracleSuiteValidationError(
                f"run {run_id} expected {key}={value!r}, got {score[key]!r}"
            )


def _critical_evidence(case: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    evaluator = case.get("evaluator_view")
    proof_steps = (
        evaluator.get("required_proof_steps")
        if isinstance(evaluator, Mapping)
        else None
    )
    if not isinstance(proof_steps, list):
        proof_steps = case.get("required_proof_steps")
    score_atoms = proof_steps if isinstance(proof_steps, list) else case.get("slots", [])
    claim_ids = {
        str(slot.get("claim_id") or slot.get("claim") or slot.get("evidence_id"))
        for slot in score_atoms
        if isinstance(slot, Mapping)
        and slot.get("type") == "evidence"
        and (
            slot.get("vital") is True
            or (
                "vital" not in slot
                and slot.get("critical") is True
            )
        )
        and (slot.get("claim_id") or slot.get("claim") or slot.get("evidence_id"))
    }
    sources: dict[str, str] = {}
    for owner_key in ("evidence_sources", "sources"):
        raw = case.get(owner_key)
        if isinstance(raw, Mapping):
            rows = raw.items()
        elif isinstance(raw, list):
            rows = [(None, row) for row in raw]
        else:
            rows = []
        for key, row in rows:
            if not isinstance(row, Mapping):
                continue
            evidence_id = key or row.get("evidence_id") or row.get("id")
            if evidence_id and row.get("source_url"):
                sources[str(evidence_id)] = _canon_url(row.get("source_url"))
    urls = {sources[item] for item in claim_ids if sources.get(item)}
    return claim_ids, urls


def _critical_evidence_with_graph(
    case: Mapping[str, Any], graph: Mapping[str, Any]
) -> tuple[set[str], set[str]]:
    ids, urls = _critical_evidence(case)
    raw_nodes = graph.get("nodes", {})
    if isinstance(raw_nodes, Mapping):
        rows = raw_nodes.items()
    elif isinstance(raw_nodes, list):
        rows = [(None, row) for row in raw_nodes]
    else:
        rows = []
    for key, row in rows:
        if not isinstance(row, Mapping):
            continue
        evidence_id = str(key or row.get("evidence_id") or row.get("id") or "")
        if evidence_id in ids and row.get("source_url"):
            urls.add(_canon_url(row.get("source_url")))
    return ids, {url for url in urls if url}


def _validate_manual_record(
    raw: Any,
    *,
    ledger: Any,
    run_id: str,
    validation_scope: str,
) -> dict[str, Any]:
    manual = _strict_mapping(raw, label=f"human oracle {run_id} manual_record")
    _reject_unknown(manual, _MANUAL_FIELDS, label=f"human oracle {run_id} manual_record")
    missing = sorted(_MANUAL_FIELDS - set(manual))
    if missing:
        raise OracleSuiteValidationError(
            f"human oracle {run_id} manual_record is missing {missing}"
        )
    _require(
        manual.get("origin") == "manual",
        f"human oracle {run_id} must explicitly declare origin=manual",
    )
    reviewer = manual.get("reviewer")
    _require(
        isinstance(reviewer, str) and reviewer.strip(),
        f"human oracle {run_id} requires a non-empty reviewer",
    )
    minutes = manual.get("solve_minutes")
    _require(
        type(minutes) in {int, float}
        and math.isfinite(float(minutes))
        and float(minutes) > 0,
        f"human oracle {run_id} solve_minutes must be a positive finite number",
    )
    _require(
        manual.get("attested") is True,
        f"human oracle {run_id} requires attested=true from the reviewer",
    )
    _require(
        type(manual.get("synthetic")) is bool,
        f"human oracle {run_id} synthetic must be a JSON boolean",
    )
    if validation_scope == "formal":
        _require(
            manual.get("synthetic") is False,
            "a synthetic human fixture cannot satisfy formal human validation",
        )
    raw_path = manual.get("access_path")
    _require(
        isinstance(raw_path, list) and raw_path,
        f"human oracle {run_id} access_path must be a non-empty URL array",
    )
    declared_path = [_canon_url(url) for url in raw_path]
    _require(
        all(declared_path),
        f"human oracle {run_id} access_path contains an invalid URL",
    )
    observed_path = _access_path(ledger)
    _require(
        declared_path == observed_path,
        f"human oracle {run_id} access_path does not match its replay ledger: "
        f"declared={declared_path!r}, observed={observed_path!r}",
    )
    return {
        "origin": "manual",
        "reviewer": reviewer.strip(),
        "solve_minutes": float(minutes),
        "access_path": declared_path,
        "attested": True,
        "synthetic": manual["synthetic"],
    }


def _validate_positive_legacy_score(
    score: Mapping[str, Any], *, run_id: str, kind: str
) -> None:
    _require_scored(score, run_id=run_id)
    required = {
        "task_pass": 1,
        "verified_recall": 1.0,
        "verified_research_completion": 1.0,
        "critical_contradictions": 0,
        "fabricated_citations": 0,
    }
    for key, expected in required.items():
        _require(
            score.get(key) == expected,
            f"{kind} oracle {run_id} requires {key}={expected!r}, "
            f"got {score.get(key)!r}",
        )


def _proof_step_rows(score: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = score.get("step_results")
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _validate_proof_replay_identity(
    score: Mapping[str, Any],
    *,
    run_id: str,
    expected_agent: str,
    formal: bool,
) -> None:
    _require(
        score.get("run_id") == run_id,
        f"run {run_id} proof-step replay identity has the wrong run_id",
    )
    _require(
        score.get("agent") == expected_agent,
        f"run {run_id} proof-step replay identity has the wrong agent",
    )
    _require(
        type(score.get("replicate")) is int and score.get("replicate") == 1,
        f"run {run_id} proof-step replay identity requires replicate=1",
    )
    identity_fields = (
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
    expected_hash = _canonical_hash({
        "version": "dra_v3_scoring_input_v3",
        **{field: score.get(field) for field in identity_fields},
    })
    _require(
        score.get("scoring_input_sha256") == expected_hash,
        f"run {run_id} proof-step scoring_input_sha256 is not replayable",
    )
    if formal:
        for field in (
            "report_sha256",
            "observation_ledger_sha256",
            "case_artifact_sha256",
            "public_task_sha256",
            "protocol_manifest_sha256",
            "corpus_registry_hash",
            "scoring_input_sha256",
        ):
            _require(
                isinstance(score.get(field), str)
                and _SHA256_RE.fullmatch(str(score.get(field))),
                f"formal run {run_id} requires a sealed {field}",
            )


def _validate_proof_score_shape(
    score: Mapping[str, Any],
    *,
    run_id: str,
    expected_agent: str,
    formal: bool,
) -> list[dict[str, Any]]:
    _require_scored(score, run_id=run_id)
    _require(
        score.get("scoring_semantics") == SCORING_SEMANTICS,
        f"run {run_id} was not scored with {SCORING_SEMANTICS}",
    )
    protocols = score.get("protocols")
    _require(
        isinstance(protocols, Mapping)
        and protocols.get("scoring_semantics") == SCORING_SEMANTICS,
        f"run {run_id} protocol stamp is not {SCORING_SEMANTICS}",
    )
    _require(
        protocols.get("headline_metrics")
        == ["partial_completion_rate_v1", "full_pass_rate_v1"],
        f"run {run_id} proof-step headline metrics are not frozen",
    )
    _require(
        protocols.get("diagnostic_metrics")
        == ["route_coverage_v1", "acquisition_diagnostics_v1"],
        f"run {run_id} proof-step diagnostic metrics are not frozen",
    )
    rows = _proof_step_rows(score)
    _require(rows, f"run {run_id} proof-step score has no step_results")
    required_ids = score.get("required_step_ids")
    _require(
        isinstance(required_ids, list)
        and required_ids
        and len(required_ids) == len(set(map(str, required_ids))),
        f"run {run_id} required_step_ids must be a non-empty unique array",
    )
    row_ids = [str(row.get("step_id") or "") for row in rows]
    _require(
        all(row_ids) and len(row_ids) == len(set(row_ids)),
        f"run {run_id} step_results require unique non-empty step_id values",
    )
    required_rows = [row for row in rows if row.get("required") is True]
    _require(
        [row["step_id"] for row in required_rows] == required_ids,
        f"run {run_id} required_step_ids do not match step_results",
    )
    for row in rows:
        step_id = str(row.get("step_id") or "<missing>")
        for axis in ("D", "O", "S", "B", "R"):
            _require(
                type(row.get(axis)) is bool,
                f"run {run_id} step {step_id} requires boolean {axis}",
            )
        expected_pass = all(row.get(axis) is True for axis in ("D", "O", "S", "B", "R"))
        _require(
            type(row.get("passed")) is bool and row.get("passed") is expected_pass,
            f"run {run_id} step {step_id} passed must equal D AND O AND S AND B AND R",
        )
        checks = row.get("checks")
        reasons = row.get("reason_codes")
        _require(
            isinstance(checks, Mapping)
            and set(checks) == {"D", "O", "S", "B", "R"},
            f"run {run_id} step {step_id} requires D/O/S/B/R checks",
        )
        _require(
            isinstance(reasons, Mapping)
            and set(reasons) == {"D", "O", "S", "B", "R"},
            f"run {run_id} step {step_id} requires D/O/S/B/R reason codes",
        )
    passed = sum(row.get("passed") is True for row in required_rows)
    _require(
        type(score.get("passed_steps")) is int and score.get("passed_steps") == passed,
        f"run {run_id} passed_steps does not match step_results",
    )
    _require(
        type(score.get("required_steps")) is int
        and score.get("required_steps") == len(required_rows),
        f"run {run_id} required_steps does not match step_results",
    )
    _require(
        type(score.get("partial_completion")) in {int, float}
        and score.get("partial_completion") == passed / len(required_rows),
        f"run {run_id} partial_completion is not passed_steps / required_steps",
    )
    _require(
        type(score.get("full_pass")) is int
        and score.get("full_pass") in {0, 1},
        f"run {run_id} full_pass must be integer 0 or 1",
    )
    _require(
        type(score.get("final_answer_pass")) is bool,
        f"run {run_id} final_answer_pass must be boolean",
    )
    _require(
        isinstance(score.get("route_coverage"), Mapping)
        and isinstance(score.get("acquisition_diagnostics"), Mapping),
        f"run {run_id} proof-step diagnostics are missing",
    )
    if formal:
        leaked = sorted(_LEGACY_SCORE_FIELDS & set(score))
        _require(
            not leaked,
            f"formal proof-step run {run_id} leaks legacy score fields: {leaked}",
        )
    _validate_proof_replay_identity(
        score,
        run_id=run_id,
        expected_agent=expected_agent,
        formal=formal,
    )
    return rows


def _validate_positive_proof_score(
    score: Mapping[str, Any],
    *,
    run_id: str,
    kind: str,
    formal: bool,
) -> None:
    rows = _validate_proof_score_shape(
        score,
        run_id=run_id,
        expected_agent=f"oracle:{kind}",
        formal=formal,
    )
    required = {
        "full_pass": 1,
        "partial_completion": 1.0,
        "final_answer_pass": True,
        "critical_contradictions": 0,
        "fabricated_citations": 0,
    }
    for key, expected in required.items():
        _require(
            type(score.get(key)) is type(expected) and score.get(key) == expected,
            f"{kind} oracle {run_id} requires {key}={expected!r}, "
            f"got {score.get(key)!r}",
        )
    _require(
        all(row.get("passed") is True for row in rows if row.get("required") is True),
        f"{kind} oracle {run_id} has an incomplete required proof step",
    )


def _validate_minimal_oracle(
    entry: Mapping[str, Any],
    score: Mapping[str, Any],
    case: Mapping[str, Any],
    graph: Mapping[str, Any],
    ledger: Any,
) -> None:
    run_id = str(entry["run_id"])
    declared = entry.get("minimal_evidence_ids")
    _require(
        isinstance(declared, list) and declared,
        f"minimal oracle {run_id} requires minimal_evidence_ids",
    )
    _require(
        len(declared) == len(set(map(str, declared))),
        f"minimal oracle {run_id} minimal_evidence_ids must be unique",
    )
    critical_ids, critical_urls = _critical_evidence_with_graph(case, graph)
    _require(
        set(map(str, declared)) == critical_ids,
        f"minimal oracle {run_id} evidence IDs must exactly equal the critical "
        f"proof leaves: expected {sorted(critical_ids)}, got {sorted(map(str, declared))}",
    )
    _require(
        critical_urls,
        f"minimal oracle {run_id} cannot resolve critical evidence URLs",
    )
    _require(
        set(score.get("used_citations") or []) == critical_urls,
        f"minimal oracle {run_id} must cite exactly the minimum critical source set",
    )
    _require(
        not score.get("unused_citations"),
        f"minimal oracle {run_id} contains non-minimal unused citations",
    )
    roots = {
        _canon_url(url) for url in case.get("discovery_root_urls", []) if _canon_url(url)
    }
    observed_urls = {
        _canon_url(
            event.get("canonical_url") or event.get("url") or event.get("request_url")
        )
        for event in _ledger_events(ledger)
        if event.get("event_type") in _CONTENT_EVENT_TYPES
    }
    observed_urls.discard("")
    _require(
        observed_urls <= critical_urls | roots,
        f"minimal oracle {run_id} observed non-minimal evidence URLs: "
        f"{sorted(observed_urls - critical_urls - roots)}",
    )


def _answer_from_decision(score: Mapping[str, Any]) -> str | None:
    for row in _proof_step_rows(score):
        if row.get("type") == "decision" and row.get("conclusion"):
            return str(row["conclusion"])
    for row in _slot_rows(score, "decision"):
        if row.get("required", True) and row.get("conclusion"):
            return str(row["conclusion"])
    return None


def _validate_expected_answer(
    entry: Mapping[str, Any], score: Mapping[str, Any], *, run_id: str
) -> None:
    if entry.get("answer") is None:
        return
    expected = str(entry["answer"])
    actual = _answer_from_decision(score)
    _require(
        actual == expected,
        f"oracle {run_id} expected admissible answer {expected!r}, got {actual!r}",
    )


def _validate_adversarial_legacy_score(
    category: str,
    score: Mapping[str, Any],
    *,
    run_id: str,
    report: str,
    entry: Mapping[str, Any],
) -> None:
    _require_scored(score, run_id=run_id)
    _require(
        score.get("task_pass") == 0,
        f"adversarial {category} run {run_id} unexpectedly passed the task",
    )
    evidence = _slot_rows(score, "evidence")
    bridges = _slot_rows(score, "bridge")
    decisions = _slot_rows(score, "decision")

    if category == "url_dump":
        _require(score.get("tp") == 0, f"url_dump {run_id} must have TP=0")
        _require(
            score.get("fabricated_citations") == 0,
            f"url_dump {run_id} must use real frozen URLs",
        )
        _require(
            int(score.get("n_unused_citations") or 0) > 0,
            f"url_dump {run_id} must expose unused real citations",
        )
    elif category == "correct_plus_fabricated":
        _require(
            score.get("verified_recall") == 1.0,
            f"correct_plus_fabricated {run_id} must otherwise complete the answer",
        )
        _require(
            int(score.get("fabricated_citations") or 0) > 0,
            f"correct_plus_fabricated {run_id} did not trigger the fabricated gate",
        )
    elif category == "fetch_all_no_answer":
        _require(score.get("tp") == 0, f"fetch_all_no_answer {run_id} must have TP=0")
        _require(
            evidence and all(row.get("O") is True for row in evidence),
            f"fetch_all_no_answer {run_id} did not actually observe every evidence page",
        )
        _require(
            score.get("decision_completion") == 0.0,
            f"fetch_all_no_answer {run_id} unexpectedly completed a decision",
        )
    elif category == "unsupported_answer":
        answer = entry.get("answer")
        _require(
            isinstance(answer, str) and answer.strip(),
            f"unsupported_answer {run_id} requires an answer field",
        )
        _require(
            _normal_identifier_text(answer) in _normal_identifier_text(report),
            f"unsupported_answer {run_id} report does not contain its declared answer",
        )
        _require(
            evidence and all(row.get("O") is False for row in evidence),
            f"unsupported_answer {run_id} must have no observed supporting evidence",
        )
        _require(
            not decisions or all(row.get("verified") is False for row in decisions),
            f"unsupported_answer {run_id} incorrectly verified the decision",
        )
    elif category == "fact_dump":
        _require(
            score.get("evidence_completion") == 1.0,
            f"fact_dump {run_id} must establish that evidence leaves alone receive no solve",
        )
        _require(
            score.get("bridge_completion") == 0.0
            and score.get("decision_completion") == 0.0,
            f"fact_dump {run_id} must leave bridge and decision at zero",
        )
        _require(
            score.get("verified_research_completion") == 0.0,
            f"fact_dump {run_id} must not complete a research subgoal",
        )
    elif category == "single_source":
        used = set(score.get("used_citations") or [])
        _require(
            len(used) == 1,
            f"single_source {run_id} must use exactly one bound source, got {sorted(used)}",
        )
        completion = score.get("evidence_completion")
        _require(
            isinstance(completion, (int, float)) and 0 < completion < 1,
            f"single_source {run_id} must verify some but not all critical evidence",
        )
    elif category == "guessed_then_fetched":
        guessed = [
            row
            for row in evidence
            if (row.get("reason_codes") or {}).get("L") == "guessed_then_fetched"
            and row.get("L") is False
        ]
        _require(
            guessed,
            f"guessed_then_fetched {run_id} did not fail the L axis with its reason code",
        )
    elif category == "wrong_binding":
        bad = [
            row
            for row in evidence
            if row.get("C") is True
            and row.get("B") is False
            and (row.get("reason_codes") or {}).get("B")
            == "citation_missing_wrong_or_detached"
        ]
        _require(
            bad,
            f"wrong_binding {run_id} did not preserve C while failing local B",
        )
        _require(
            score.get("fabricated_citations") == 0,
            f"wrong_binding {run_id} must use a real but incorrect frozen page",
        )
    elif category == "contradictory_decision":
        _require(
            score.get("evidence_completion") == 1.0
            and score.get("bridge_completion") == 1.0,
            f"contradictory_decision {run_id} must first reproduce evidence and bridges",
        )
        _require(
            score.get("decision_completion") == 0.0,
            f"contradictory_decision {run_id} unexpectedly verified its decision",
        )
        conclusion_failed = any(
            (row.get("reason_codes") or {}).get("CONCLUSION")
            == "admissible_conclusion_missing"
            for row in decisions
        )
        _require(
            conclusion_failed or int(score.get("critical_contradictions") or 0) > 0,
            f"contradictory_decision {run_id} lacks a decision failure/contradiction reason",
        )
    elif category == "silence":
        _require(
            len(report.strip()) <= 32 and "http" not in report.casefold(),
            f"silence {run_id} is not silent or a short shell",
        )
        _require(score.get("tp") == 0, f"silence {run_id} must have TP=0")
        _require(score.get("verified_f1") == 0.0, f"silence {run_id} must have F1=0")
        _require(
            score.get("verified_research_completion") == 0.0,
            f"silence {run_id} must have Research Completion=0",
        )
    else:  # Defensive even though category coverage is checked earlier.
        raise OracleSuiteValidationError(f"unsupported adversarial category: {category}")


def _validate_adversarial_proof_score(
    category: str,
    score: Mapping[str, Any],
    *,
    run_id: str,
    report: str,
    entry: Mapping[str, Any],
    formal: bool,
) -> None:
    rows = _validate_proof_score_shape(
        score,
        run_id=run_id,
        expected_agent=f"adversarial:{category}",
        formal=formal,
    )
    _require(
        score.get("full_pass") == 0,
        f"adversarial {category} run {run_id} unexpectedly passed the task",
    )
    evidence = [row for row in rows if row.get("type") == "evidence"]
    bridges = [row for row in rows if row.get("type") == "bridge"]
    decisions = [row for row in rows if row.get("type") == "decision"]

    if category == "url_dump":
        _require(
            score.get("partial_completion") == 0.0,
            f"url_dump {run_id} must have zero proof-step completion",
        )
        _require(
            score.get("fabricated_citations") == 0,
            f"url_dump {run_id} must use real frozen URLs",
        )
        _require(
            int(score.get("n_unused_citations") or 0) > 0,
            f"url_dump {run_id} must expose unused real citations",
        )
    elif category == "correct_plus_fabricated":
        _require(
            score.get("partial_completion") == 1.0,
            f"correct_plus_fabricated {run_id} must otherwise complete every proof step",
        )
        _require(
            int(score.get("fabricated_citations") or 0) > 0,
            f"correct_plus_fabricated {run_id} did not trigger the fabricated gate",
        )
    elif category == "fetch_all_no_answer":
        _require(
            evidence and all(row.get("O") is True for row in evidence),
            f"fetch_all_no_answer {run_id} did not observe every evidence page",
        )
        _require(
            decisions and all(row.get("passed") is False for row in decisions),
            f"fetch_all_no_answer {run_id} unexpectedly completed the final answer",
        )
    elif category == "unsupported_answer":
        answer = entry.get("answer")
        _require(
            isinstance(answer, str) and answer.strip(),
            f"unsupported_answer {run_id} requires an answer field",
        )
        _require(
            _normal_identifier_text(answer) in _normal_identifier_text(report),
            f"unsupported_answer {run_id} report does not contain its declared answer",
        )
        _require(
            evidence and all(row.get("O") is False for row in evidence),
            f"unsupported_answer {run_id} must have no observed supporting evidence",
        )
        _require(
            not decisions or all(row.get("passed") is False for row in decisions),
            f"unsupported_answer {run_id} incorrectly verified the final answer",
        )
    elif category == "fact_dump":
        _require(
            evidence and all(row.get("passed") is True for row in evidence),
            f"fact_dump {run_id} must first reproduce every evidence leaf",
        )
        _require(
            bridges and all(row.get("passed") is False for row in bridges),
            f"fact_dump {run_id} must leave bridge steps incomplete",
        )
        _require(
            decisions and all(row.get("passed") is False for row in decisions),
            f"fact_dump {run_id} must leave final-answer steps incomplete",
        )
    elif category == "single_source":
        used = set(score.get("used_citations") or [])
        _require(
            len(used) == 1,
            f"single_source {run_id} must use exactly one bound source, got {sorted(used)}",
        )
        passed_evidence = sum(row.get("passed") is True for row in evidence)
        _require(
            evidence and 0 < passed_evidence < len(evidence),
            f"single_source {run_id} must verify some but not all evidence steps",
        )
    elif category == "guessed_then_fetched":
        guessed = [
            row
            for row in evidence
            if row.get("D") is False
            and (row.get("reason_codes") or {}).get("D") == "guessed_then_fetched"
        ]
        _require(
            guessed,
            f"guessed_then_fetched {run_id} did not fail D with its reason code",
        )
    elif category == "wrong_binding":
        bad = [
            row
            for row in evidence
            if row.get("O") is True
            and row.get("B") is False
            and (row.get("reason_codes") or {}).get("B")
            == "citation_missing_wrong_or_detached"
        ]
        _require(
            bad,
            f"wrong_binding {run_id} did not observe content while failing binding",
        )
        _require(
            score.get("fabricated_citations") == 0,
            f"wrong_binding {run_id} must use real frozen pages",
        )
    elif category == "contradictory_decision":
        _require(
            evidence and all(row.get("passed") is True for row in evidence),
            f"contradictory_decision {run_id} must reproduce evidence steps",
        )
        _require(
            bridges and all(row.get("passed") is True for row in bridges),
            f"contradictory_decision {run_id} must reproduce bridge steps",
        )
        _require(
            decisions and all(row.get("passed") is False for row in decisions),
            f"contradictory_decision {run_id} unexpectedly passed its final answer",
        )
        _require(
            any(row.get("R") is False for row in decisions)
            or int(score.get("critical_contradictions") or 0) > 0,
            f"contradictory_decision {run_id} lacks a relation/contradiction failure",
        )
    elif category == "silence":
        _require(
            len(report.strip()) <= 32 and "http" not in report.casefold(),
            f"silence {run_id} is not silent or a short shell",
        )
        _require(
            score.get("partial_completion") == 0.0,
            f"silence {run_id} must have zero Partial Completion",
        )
    else:  # Defensive even though category coverage is checked earlier.
        raise OracleSuiteValidationError(f"unsupported adversarial category: {category}")


def _score_audit(score: Mapping[str, Any]) -> dict[str, Any]:
    """Retain replay diagnostics while making the result independently hashable."""

    score_copy = json.loads(canonical_json_bytes(score).decode("utf-8"))
    return {
        "score_sha256": _canonical_hash(score_copy),
        "score": score_copy,
    }


def _conditional_answers(case: Mapping[str, Any]) -> list[str]:
    conclusions = case.get("acceptable_conclusions")
    if not isinstance(conclusions, list):
        return []
    conditional: list[str] = []
    for value in conclusions:
        if isinstance(value, Mapping) and value.get("answer"):
            conditional.append(str(value["answer"]))
    if conditional and len(conditional) != len(conclusions):
        raise OracleSuiteValidationError(
            "acceptable_conclusions cannot mix simple and conditional forms"
        )
    return conditional if len(conditional) > 1 else []


def _validate_run_shape(
    raw: Any, *, label: str, allowed: set[str], discriminator: str
) -> dict[str, Any]:
    entry = _strict_mapping(raw, label=label)
    _reject_unknown(entry, allowed, label=label)
    for required in ("run_id", discriminator, "report", "ledger"):
        if required not in entry:
            raise OracleSuiteValidationError(f"{label} is missing {required}")
    run_id = entry.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise OracleSuiteValidationError(f"{label} run_id must be a non-empty string")
    if "expected" in entry and not isinstance(entry["expected"], Mapping):
        raise OracleSuiteValidationError(f"{label} expected must be a JSON object")
    return entry


def validate_oracle_suite(
    suite: Mapping[str, Any],
    *,
    base_dir: str | Path | None = None,
    suite_sha256: str | None = None,
) -> dict[str, Any]:
    """Replay and validate one complete v3 oracle/adversarial suite.

    ``base_dir`` is required only when an artifact uses ``path``.  Every path
    must remain beneath that directory and carry an exact raw SHA-256.  Formal
    validation additionally requires a compiled case, a sealed protocol
    manifest, and non-synthetic manually attested human data.
    """

    root = _strict_mapping(suite, label="oracle suite")
    _reject_unknown(root, _ROOT_FIELDS, label="oracle suite")
    required_root = {
        "schema",
        "suite_id",
        "validation_scope",
        "case",
        "evidence_graph",
        "oracles",
        "adversarial",
    }
    missing_root = sorted(required_root - set(root))
    if missing_root:
        raise OracleSuiteValidationError(f"oracle suite is missing {missing_root}")
    if root.get("schema") != SUITE_SCHEMA:
        raise OracleSuiteValidationError(
            f"oracle suite schema must be {SUITE_SCHEMA!r}"
        )
    suite_id = root.get("suite_id")
    if not isinstance(suite_id, str) or not suite_id.strip():
        raise OracleSuiteValidationError("suite_id must be a non-empty string")
    validation_scope = root.get("validation_scope")
    if validation_scope not in VALIDATION_SCOPES:
        raise OracleSuiteValidationError(
            f"validation_scope must be one of {sorted(VALIDATION_SCOPES)}"
        )
    scoring_semantics = root.get(
        "scoring_semantics", VERIFIED_SLOTS_SEMANTICS
    )
    if scoring_semantics not in {VERIFIED_SLOTS_SEMANTICS, SCORING_SEMANTICS}:
        raise OracleSuiteValidationError(
            "scoring_semantics must be proof_steps_v1 or verified_slots_v1"
        )
    proof_step_mode = scoring_semantics == SCORING_SEMANTICS
    scorer = score_proof_steps if proof_step_mode else score_verified_slots
    if suite_sha256 is not None and not _SHA256_RE.fullmatch(suite_sha256):
        raise OracleSuiteValidationError("suite_sha256 must be 64 lowercase hex")
    artifact_root = Path(base_dir) if base_dir is not None else None

    case_artifact = _load_artifact(
        root["case"], label="case", value_type="json", base_dir=artifact_root
    )
    graph_artifact = _load_artifact(
        root["evidence_graph"],
        label="evidence_graph",
        value_type="json",
        base_dir=artifact_root,
    )
    public_task_artifact: _LoadedArtifact | None = None
    if root.get("public_task") is not None:
        public_task_artifact = _load_artifact(
            root["public_task"],
            label="public_task",
            value_type="json",
            base_dir=artifact_root,
        )
    case = _strict_mapping(case_artifact.value, label="case artifact")
    graph = _strict_mapping(graph_artifact.value, label="evidence_graph artifact")
    task_id = case.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise OracleSuiteValidationError("case artifact requires task_id")

    protocols: dict[str, Any] | None = None
    protocol_audit: dict[str, Any] | None = None
    if root.get("protocols") is not None:
        protocol_artifact = _load_artifact(
            root["protocols"],
            label="protocols",
            value_type="json",
            base_dir=artifact_root,
        )
        protocols = _strict_mapping(protocol_artifact.value, label="protocols artifact")
        protocol_audit = protocol_artifact.audit
    if validation_scope == "formal":
        _require(
            isinstance(case.get("formal_bindings"), Mapping)
            and case["formal_bindings"].get("formal") is True,
            "formal oracle validation requires a formally compiled case",
        )
        _require(protocols is not None, "formal oracle validation requires sealed protocols")
        _require(
            public_task_artifact is not None,
            "formal oracle validation requires the exact rendered public task artifact",
        )
        _require(
            case_artifact.audit.get("hash_basis") == "raw_bytes",
            "formal oracle validation requires a path-backed exact case artifact",
        )
        _require(
            public_task_artifact.audit.get("hash_basis") == "raw_bytes",
            "formal oracle validation requires a path-backed exact public task artifact",
        )

    raw_oracles = root.get("oracles")
    raw_adversarial = root.get("adversarial")
    if not isinstance(raw_oracles, list):
        raise OracleSuiteValidationError("oracles must be an array")
    if not isinstance(raw_adversarial, list):
        raise OracleSuiteValidationError("adversarial must be an array")
    oracles = [
        _validate_run_shape(
            raw,
            label=f"oracle[{index}]",
            allowed=_ORACLE_FIELDS,
            discriminator="kind",
        )
        for index, raw in enumerate(raw_oracles)
    ]
    adversarial = [
        _validate_run_shape(
            raw,
            label=f"adversarial[{index}]",
            allowed=_ADVERSARIAL_FIELDS,
            discriminator="category",
        )
        for index, raw in enumerate(raw_adversarial)
    ]
    all_run_ids = [str(entry["run_id"]) for entry in [*oracles, *adversarial]]
    if len(all_run_ids) != len(set(all_run_ids)):
        raise OracleSuiteValidationError("oracle/adversarial run_id values must be unique")

    kinds = [str(entry.get("kind")) for entry in oracles]
    unknown_kinds = sorted(set(kinds) - CORE_ORACLE_KINDS - {ADMISSIBLE_ORACLE_KIND})
    if unknown_kinds:
        raise OracleSuiteValidationError(f"unknown oracle kinds: {unknown_kinds}")
    for kind in sorted(CORE_ORACLE_KINDS):
        count = kinds.count(kind)
        if count != 1:
            raise OracleSuiteValidationError(
                f"suite requires exactly one {kind} oracle; found {count}"
            )

    conditional_answers = _conditional_answers(case)
    alternative_entries = [
        entry for entry in oracles if entry.get("kind") == ADMISSIBLE_ORACLE_KIND
    ]
    alternative_answers = [str(entry.get("answer") or "") for entry in alternative_entries]
    if conditional_answers:
        if sorted(alternative_answers) != sorted(conditional_answers):
            raise OracleSuiteValidationError(
                "conditional conclusions require exactly one admissible_alternative "
                f"oracle per answer: expected {sorted(conditional_answers)}, "
                f"got {sorted(alternative_answers)}"
            )
    elif alternative_entries:
        raise OracleSuiteValidationError(
            "admissible_alternative oracles are only valid for conditional conclusions"
        )

    categories = [str(entry.get("category")) for entry in adversarial]
    unknown_categories = sorted(set(categories) - set(REQUIRED_ADVERSARIAL_CATEGORIES))
    missing_categories = sorted(set(REQUIRED_ADVERSARIAL_CATEGORIES) - set(categories))
    duplicate_categories = sorted(
        category for category in set(categories) if categories.count(category) != 1
    )
    if unknown_categories:
        raise OracleSuiteValidationError(
            f"unknown adversarial categories: {unknown_categories}"
        )
    if missing_categories:
        raise OracleSuiteValidationError(
            f"missing adversarial categories: {missing_categories}"
        )
    if duplicate_categories:
        raise OracleSuiteValidationError(
            f"each adversarial category must occur exactly once: {duplicate_categories}"
        )

    artifacts: dict[str, Any] = {
        "case": case_artifact.audit,
        "evidence_graph": graph_artifact.audit,
    }
    if public_task_artifact is not None:
        artifacts["public_task"] = public_task_artifact.audit
    if protocol_audit is not None:
        artifacts["protocols"] = protocol_audit
    oracle_results: list[dict[str, Any]] = []
    human_record: dict[str, Any] | None = None
    for entry in oracles:
        run_id = str(entry["run_id"])
        kind = str(entry["kind"])
        report_artifact = _load_artifact(
            entry["report"],
            label=f"oracle {run_id} report",
            value_type="text",
            base_dir=artifact_root,
        )
        ledger_artifact = _load_artifact(
            entry["ledger"],
            label=f"oracle {run_id} ledger",
            value_type="ledger",
            base_dir=artifact_root,
        )
        ledger = _materialize_ledger(ledger_artifact, run_id=run_id)
        score = scorer(
            case,
            report_artifact.value,
            ledger,
            graph,
            protocols=protocols,
            expected_run_id=run_id,
            case_artifact_sha256=case_artifact.audit["sha256"],
            public_task_sha256=(
                public_task_artifact.audit["sha256"]
                if public_task_artifact is not None else None
            ),
            agent=f"oracle:{kind}",
            replicate=1,
        )
        if proof_step_mode:
            _validate_positive_proof_score(
                score,
                run_id=run_id,
                kind=kind,
                formal=validation_scope == "formal",
            )
        else:
            _validate_positive_legacy_score(score, run_id=run_id, kind=kind)
        _validate_expected_answer(entry, score, run_id=run_id)
        if kind == "minimal":
            _validate_minimal_oracle(entry, score, case, graph, ledger)
        elif entry.get("minimal_evidence_ids") is not None:
            raise OracleSuiteValidationError(
                f"only the minimal oracle may declare minimal_evidence_ids ({run_id})"
            )
        if kind == "human":
            human_record = _validate_manual_record(
                entry.get("manual_record"),
                ledger=ledger,
                run_id=run_id,
                validation_scope=str(validation_scope),
            )
        elif entry.get("manual_record") is not None:
            raise OracleSuiteValidationError(
                f"only the human oracle may carry manual_record ({run_id})"
            )
        _check_declared_expected(score, entry.get("expected"), run_id=run_id)
        run_audit = {
            "run_id": run_id,
            "kind": kind,
            "report_artifact": report_artifact.audit,
            "ledger_artifact": ledger_artifact.audit,
            **_score_audit(score),
        }
        if entry.get("answer") is not None:
            run_audit["answer"] = str(entry["answer"])
        oracle_results.append(run_audit)

    adversarial_results: list[dict[str, Any]] = []
    for entry in adversarial:
        run_id = str(entry["run_id"])
        category = str(entry["category"])
        report_artifact = _load_artifact(
            entry["report"],
            label=f"adversarial {run_id} report",
            value_type="text",
            base_dir=artifact_root,
        )
        ledger_artifact = _load_artifact(
            entry["ledger"],
            label=f"adversarial {run_id} ledger",
            value_type="ledger",
            base_dir=artifact_root,
        )
        ledger = _materialize_ledger(ledger_artifact, run_id=run_id)
        score = scorer(
            case,
            report_artifact.value,
            ledger,
            graph,
            protocols=protocols,
            expected_run_id=run_id,
            case_artifact_sha256=case_artifact.audit["sha256"],
            public_task_sha256=(
                public_task_artifact.audit["sha256"]
                if public_task_artifact is not None else None
            ),
            agent=f"adversarial:{category}",
            replicate=1,
        )
        if proof_step_mode:
            _validate_adversarial_proof_score(
                category,
                score,
                run_id=run_id,
                report=report_artifact.value,
                entry=entry,
                formal=validation_scope == "formal",
            )
        else:
            _validate_adversarial_legacy_score(
                category,
                score,
                run_id=run_id,
                report=report_artifact.value,
                entry=entry,
            )
        _check_declared_expected(score, entry.get("expected"), run_id=run_id)
        adversarial_results.append(
            {
                "run_id": run_id,
                "category": category,
                "report_artifact": report_artifact.audit,
                "ledger_artifact": ledger_artifact.audit,
                **_score_audit(score),
            }
        )

    assert human_record is not None  # exactly one human oracle was enforced above
    formal = validation_scope == "formal"
    result: dict[str, Any] = {
        "schema": VALIDATION_SCHEMA,
        "validation_semantics": VALIDATION_SEMANTICS,
        "suite_id": suite_id.strip(),
        "suite_sha256": suite_sha256 or _canonical_hash(root),
        "task_id": task_id,
        "validation_scope": validation_scope,
        "validation_tier": (
            "formal_human_attested" if formal else "synthetic_mechanism_only"
        ),
        "status": "validated",
        "artifacts": artifacts,
        "oracle_results": oracle_results,
        "adversarial_results": adversarial_results,
        "manual_human_record": human_record,
        "manual_human_status": (
            "attested_and_replayed" if formal else "synthetic_fixture_replayed"
        ),
        "formal_human_validation_passed": formal,
        "formal_pilot_passed": formal,
        "synthetic_only": not formal,
        "requires_real_human_followup": not formal,
        "required_adversarial_categories": list(REQUIRED_ADVERSARIAL_CATEGORIES),
    }
    result["validation_sha256"] = _canonical_hash(result)
    return result


def verify_validation_result(result: Mapping[str, Any]) -> bool:
    """Verify schema and self-hash of a previously emitted validation result."""

    if not isinstance(result, Mapping) or result.get("schema") != VALIDATION_SCHEMA:
        return False
    declared = result.get("validation_sha256")
    if not isinstance(declared, str) or not _SHA256_RE.fullmatch(declared):
        return False
    payload = {key: value for key, value in result.items() if key != "validation_sha256"}
    return _canonical_hash(payload) == declared


def manual_human_requirements() -> dict[str, Any]:
    """Return the fields a person must supply; this is a checklist, not data."""

    return {
        "origin": "manual (literal value required)",
        "reviewer": "human reviewer identifier (required)",
        "solve_minutes": "positive measured elapsed minutes (required)",
        "access_path": "chronological URL path matching the captured ledger (required)",
        "attested": "true only after the reviewer checks the report and trace",
        "synthetic": "false for formal validation; true for test fixtures",
        "note": "Codex does not populate or attest these human-observation fields.",
    }


__all__ = [
    "ADMISSIBLE_ORACLE_KIND",
    "CORE_ORACLE_KINDS",
    "OracleSuiteValidationError",
    "REQUIRED_ADVERSARIAL_CATEGORIES",
    "SUITE_SCHEMA",
    "VALIDATION_SCHEMA",
    "VALIDATION_SEMANTICS",
    "canonical_json_bytes",
    "manual_human_requirements",
    "sha256_bytes",
    "validate_oracle_suite",
    "verify_validation_result",
]
