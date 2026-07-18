"""Version identity and compatibility guards for DRA v3.

The v2 scorer remains replayable and intentionally lives in its existing
modules.  This module is the narrow choke point for artifacts that claim v3
semantics: a case, score, or board must carry every stamp below, and artifacts
with different stamps must never be merged or compared as if they measured the
same thing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping


TASK_VERSION = 3
CASE_SCHEMA = "evidence_graph_case_v1"
EVIDENCE_GRAPH = "evidence_graph_v1"
OBSERVATION_SEMANTICS = "observation_ledger_v1"
SCORING_SEMANTICS = "proof_steps_v1"
LEGACY_SCORING_SEMANTICS = "verified_slots_v1"
PARTIAL_COMPLETION_RATE_METRIC = "partial_completion_rate_v1"
FULL_PASS_RATE_METRIC = "full_pass_rate_v1"
HEADLINE_METRICS = (
    PARTIAL_COMPLETION_RATE_METRIC,
    FULL_PASS_RATE_METRIC,
)
ROUTE_COVERAGE_METRIC = "route_coverage_v1"
ACQUISITION_DIAGNOSTICS_METRIC = "acquisition_diagnostics_v1"
DIAGNOSTIC_METRICS = (
    ROUTE_COVERAGE_METRIC,
    ACQUISITION_DIAGNOSTICS_METRIC,
)
# The verified-slot protocol remains replayable as a parallel historical v3
# method.  These names keep their original values; they are never aliases for
# the proof-step headlines.
VERIFIED_RESEARCH_COMPLETION_METRIC = "verified_research_completion_v1"
TASK_SOLVE_RATE_METRIC = "task_solve_rate_v1"
LEGACY_HEADLINE_METRICS = (
    VERIFIED_RESEARCH_COMPLETION_METRIC,
    TASK_SOLVE_RATE_METRIC,
)
LEGACY_DIAGNOSTIC_METRIC = "verified_f1_v1"
DIAGNOSTIC_METRIC = ROUTE_COVERAGE_METRIC
HEADLINE_METRIC = FULL_PASS_RATE_METRIC
PARTIAL_METRIC = PARTIAL_COMPLETION_RATE_METRIC
PROTOCOL_VERSION = "dra_v3_evidence_graph_proof_steps_v1"
LEGACY_PROTOCOL_VERSION = "dra_v3_evidence_graph_verified_slots_v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

IDENTITY_FIELDS = (
    "protocol_version",
    "task_version",
    "case_schema",
    "evidence_graph",
    "observation_semantics",
    "scoring_semantics",
    "headline_metrics",
    "corpus_snapshot",
    "task_set_hash",
    "n_tasks",
)


class ProtocolV3Error(ValueError):
    """Raised when an artifact falsely or incompletely claims v3 semantics."""


class IncomparableProtocolError(ProtocolV3Error):
    """Raised when callers try to combine artifacts from different protocols."""


def stable_hash(values: Iterable[str]) -> str:
    """Order-independent SHA-256 over a set-like collection of identifiers."""

    payload = "\n".join(sorted({str(v) for v in values})).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_json_hash(value: object) -> str:
    """Stable SHA-256 for a JSON-compatible value."""

    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def protocol_stamp(
    *,
    corpus_snapshot: str,
    task_ids: Iterable[str],
    case_hashes: Mapping[str, str] | None = None,
    public_task_hashes: Mapping[str, str] | None = None,
    evidence_graph_hash: str | None = None,
    corpus_registry_hash: str | None = None,
    scoring_semantics: str = LEGACY_SCORING_SEMANTICS,
) -> dict:
    """Return a complete non-weighted v3 protocol stamp.

    The default preserves the established ``verified_slots_v1`` caller
    contract.  New formal panels must call :func:`proof_steps_protocol_stamp`
    or explicitly request ``proof_steps_v1``.  Content hashes are optional
    while authoring either protocol and mandatory for formal aggregation.
    """

    task_ids = sorted({str(t) for t in task_ids})
    if not corpus_snapshot:
        raise ProtocolV3Error("corpus_snapshot is required")
    if not task_ids or any(not task_id for task_id in task_ids):
        raise ProtocolV3Error("at least one non-empty task_id is required")
    if scoring_semantics == SCORING_SEMANTICS:
        protocol_version = PROTOCOL_VERSION
        headline_metrics = list(HEADLINE_METRICS)
        diagnostic_fields = {"diagnostic_metrics": list(DIAGNOSTIC_METRICS)}
    elif scoring_semantics == LEGACY_SCORING_SEMANTICS:
        protocol_version = LEGACY_PROTOCOL_VERSION
        headline_metrics = list(LEGACY_HEADLINE_METRICS)
        diagnostic_fields = {"diagnostic_metric": LEGACY_DIAGNOSTIC_METRIC}
    else:
        raise ProtocolV3Error(
            "scoring_semantics must be proof_steps_v1 or verified_slots_v1"
        )
    stamp = {
        "protocol_version": protocol_version,
        "task_version": TASK_VERSION,
        "case_schema": CASE_SCHEMA,
        "evidence_graph": EVIDENCE_GRAPH,
        "observation_semantics": OBSERVATION_SEMANTICS,
        "scoring_semantics": scoring_semantics,
        "headline_metrics": headline_metrics,
        **diagnostic_fields,
        "corpus_snapshot": str(corpus_snapshot),
        "task_set_hash": stable_hash(task_ids),
        "n_tasks": len(task_ids),
        "legacy_quality_used": False,
    }
    if case_hashes is not None:
        normalized = {str(k): str(v) for k, v in sorted(case_hashes.items())}
        if set(normalized) != set(task_ids):
            raise ProtocolV3Error(
                "case_hashes keys must exactly match the stamped task_ids"
            )
        bad_hashes = sorted(
            task_id
            for task_id, digest in normalized.items()
            if not _SHA256_RE.fullmatch(digest)
        )
        if bad_hashes:
            raise ProtocolV3Error(
                "case_hashes must contain lowercase SHA-256 digests; invalid tasks: "
                + ", ".join(bad_hashes)
            )
        stamp["case_set_hash"] = canonical_json_hash(normalized)
    if public_task_hashes is not None:
        normalized_public = {
            str(k): str(v) for k, v in sorted(public_task_hashes.items())
        }
        if set(normalized_public) != set(task_ids):
            raise ProtocolV3Error(
                "public_task_hashes keys must exactly match the stamped task_ids"
            )
        bad_public_hashes = sorted(
            task_id
            for task_id, digest in normalized_public.items()
            if not _SHA256_RE.fullmatch(digest)
        )
        if bad_public_hashes:
            raise ProtocolV3Error(
                "public_task_hashes must contain lowercase SHA-256 digests; "
                "invalid tasks: " + ", ".join(bad_public_hashes)
            )
        stamp["public_task_set_hash"] = canonical_json_hash(normalized_public)
    if evidence_graph_hash is not None:
        evidence_graph_hash = str(evidence_graph_hash)
        if not _SHA256_RE.fullmatch(evidence_graph_hash):
            raise ProtocolV3Error(
                "evidence_graph_hash must be a lowercase SHA-256 digest"
            )
        stamp["evidence_graph_hash"] = evidence_graph_hash
    if corpus_registry_hash is not None:
        corpus_registry_hash = str(corpus_registry_hash)
        if not _SHA256_RE.fullmatch(corpus_registry_hash):
            raise ProtocolV3Error(
                "corpus_registry_hash must be a lowercase SHA-256 digest"
            )
        stamp["corpus_registry_hash"] = corpus_registry_hash
    return stamp


def proof_steps_protocol_stamp(**kwargs) -> dict:
    """Build the independent ``proof_steps_v1`` protocol stamp."""

    return protocol_stamp(**kwargs, scoring_semantics=SCORING_SEMANTICS)


def verified_slots_protocol_stamp(**kwargs) -> dict:
    """Build the preserved ``verified_slots_v1`` protocol stamp."""

    return protocol_stamp(**kwargs, scoring_semantics=LEGACY_SCORING_SEMANTICS)


def _protocol_block(artifact: Mapping) -> Mapping:
    block = artifact.get("protocols") if isinstance(artifact, Mapping) else None
    return block if isinstance(block, Mapping) else artifact


def validate_protocol(
    artifact: Mapping,
    *,
    formal: bool = False,
    required_semantics: str | None = None,
) -> dict:
    """Validate and return an artifact's v3 protocol block.

    ``formal=True`` additionally requires content hashes that a draft/pilot
    artifact may not yet have.  v2 artifacts fail explicitly instead of being
    silently interpreted through best-effort field aliases.
    """

    p = dict(_protocol_block(artifact))
    semantics = p.get("scoring_semantics")
    if required_semantics is not None and semantics != required_semantics:
        raise ProtocolV3Error(
            "invalid DRA v3 protocol: scoring_semantics="
            f"{semantics!r}, expected {required_semantics!r}"
        )
    if semantics == SCORING_SEMANTICS:
        expected_version = PROTOCOL_VERSION
        expected_headlines = list(HEADLINE_METRICS)
        expected_diagnostics = list(DIAGNOSTIC_METRICS)
    elif semantics == LEGACY_SCORING_SEMANTICS:
        expected_version = LEGACY_PROTOCOL_VERSION
        expected_headlines = list(LEGACY_HEADLINE_METRICS)
        expected_diagnostics = LEGACY_DIAGNOSTIC_METRIC
    else:
        raise ProtocolV3Error(
            "invalid DRA v3 protocol: unsupported scoring_semantics="
            f"{semantics!r}"
        )
    expected = {
        "protocol_version": expected_version,
        "task_version": TASK_VERSION,
        "case_schema": CASE_SCHEMA,
        "evidence_graph": EVIDENCE_GRAPH,
        "observation_semantics": OBSERVATION_SEMANTICS,
        "scoring_semantics": semantics,
        "headline_metrics": expected_headlines,
    }
    errors = []
    for key, value in expected.items():
        if p.get(key) != value:
            errors.append(f"{key}={p.get(key)!r}, expected {value!r}")
    for obsolete in ("headline_metric", "partial_metric"):
        if obsolete in p:
            errors.append(
                f"obsolete singular protocol field {obsolete!r} is forbidden"
            )
    if semantics == SCORING_SEMANTICS:
        if p.get("diagnostic_metrics") != expected_diagnostics:
            errors.append(
                f"diagnostic_metrics={p.get('diagnostic_metrics')!r}, "
                f"expected {expected_diagnostics!r}"
            )
        if "diagnostic_metric" in p:
            errors.append(
                "proof_steps_v1 forbids the verified-slot diagnostic_metric field"
            )
    else:
        if p.get("diagnostic_metric") != expected_diagnostics:
            errors.append(
                f"diagnostic_metric={p.get('diagnostic_metric')!r}, "
                f"expected {expected_diagnostics!r}"
            )
        if "diagnostic_metrics" in p:
            errors.append(
                "verified_slots_v1 forbids proof-step diagnostic_metrics"
            )
    for key in ("corpus_snapshot", "task_set_hash"):
        if not p.get(key):
            errors.append(f"missing {key}")
    if not _SHA256_RE.fullmatch(str(p.get("task_set_hash") or "")):
        errors.append("task_set_hash must be a lowercase SHA-256 digest")
    n_tasks = p.get("n_tasks")
    if isinstance(n_tasks, bool) or not isinstance(n_tasks, int) or n_tasks <= 0:
        errors.append("n_tasks must be a positive integer")
    if p.get("legacy_quality_used") is not False:
        errors.append("legacy_quality_used must be false")
    if "weights" in p or "quality" in p:
        errors.append("v3 protocol must not contain legacy quality/weights")
    if formal:
        for key in (
            "case_set_hash",
            "public_task_set_hash",
            "evidence_graph_hash",
            "corpus_registry_hash",
        ):
            if not p.get(key):
                errors.append(f"formal artifact missing {key}")
            elif not _SHA256_RE.fullmatch(str(p[key])):
                errors.append(f"{key} must be a lowercase SHA-256 digest")
    if errors:
        raise ProtocolV3Error("invalid DRA v3 protocol: " + "; ".join(errors))
    return p


def validate_proof_steps_protocol(
    artifact: Mapping, *, formal: bool = False
) -> dict:
    """Validate only the new proof-step protocol."""

    return validate_protocol(
        artifact, formal=formal, required_semantics=SCORING_SEMANTICS
    )


def validate_verified_slots_protocol(
    artifact: Mapping, *, formal: bool = False
) -> dict:
    """Validate only the preserved verified-slot protocol."""

    return validate_protocol(
        artifact, formal=formal, required_semantics=LEGACY_SCORING_SEMANTICS
    )


def assert_comparable(left: Mapping, right: Mapping, *, formal: bool = False) -> None:
    """Refuse cross-version or cross-snapshot comparisons."""

    a = validate_protocol(left, formal=formal)
    b = validate_protocol(right, formal=formal)
    fields = list(IDENTITY_FIELDS)
    fields.append(
        "diagnostic_metrics"
        if a.get("scoring_semantics") == SCORING_SEMANTICS
        else "diagnostic_metric"
    )
    if formal:
        fields += [
            "case_set_hash",
            "public_task_set_hash",
            "evidence_graph_hash",
            "corpus_registry_hash",
        ]
    mismatches = [f for f in fields if a.get(f) != b.get(f)]
    if mismatches:
        detail = ", ".join(
            f"{f}: {a.get(f)!r} != {b.get(f)!r}" for f in mismatches
        )
        raise IncomparableProtocolError(
            "DRA artifacts are not comparable across protocol/task/corpus versions: "
            + detail
        )


__all__ = [
    "TASK_VERSION",
    "CASE_SCHEMA",
    "EVIDENCE_GRAPH",
    "OBSERVATION_SEMANTICS",
    "SCORING_SEMANTICS",
    "LEGACY_SCORING_SEMANTICS",
    "PARTIAL_COMPLETION_RATE_METRIC",
    "FULL_PASS_RATE_METRIC",
    "ROUTE_COVERAGE_METRIC",
    "ACQUISITION_DIAGNOSTICS_METRIC",
    "VERIFIED_RESEARCH_COMPLETION_METRIC",
    "TASK_SOLVE_RATE_METRIC",
    "HEADLINE_METRICS",
    "LEGACY_HEADLINE_METRICS",
    "DIAGNOSTIC_METRICS",
    "LEGACY_DIAGNOSTIC_METRIC",
    "DIAGNOSTIC_METRIC",
    "HEADLINE_METRIC",
    "PARTIAL_METRIC",
    "PROTOCOL_VERSION",
    "LEGACY_PROTOCOL_VERSION",
    "ProtocolV3Error",
    "IncomparableProtocolError",
    "stable_hash",
    "canonical_json_hash",
    "protocol_stamp",
    "proof_steps_protocol_stamp",
    "verified_slots_protocol_stamp",
    "validate_protocol",
    "validate_proof_steps_protocol",
    "validate_verified_slots_protocol",
    "assert_comparable",
]
