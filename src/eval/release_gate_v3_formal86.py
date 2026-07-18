"""Fail-closed Formal-86/Dev-14 release gate added beside the legacy pilot gate.

This module deliberately does not perform human review.  It verifies exact
artifact bytes and the completeness of signed human-review records, then
classifies the handoff as code-pending, manual-pending, or formally eligible.
A checked boolean is never accepted as a substitute for review evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any


RELEASE_READINESS_SCHEMA = "dra_v3_release_readiness_v2"
ORACLE_RELEASE_BUNDLE_SCHEMA = "dra_v3_oracle_release_bundle_v2"
ACQUISITION_PATH_COVERAGE_SCHEMA = (
    "dra_v3_acquisition_path_coverage_matrix_v2"
)
ACQUISITION_PATH_CONFORMANCE_SCHEMA = (
    "dra_v3_acquisition_path_conformance_result_v1"
)
ISOLATION_AUDIT_SCHEMA = "dra_v3_acquisition_path_isolation_audit_v1"
BYPASS_AUDIT_SCHEMA = "dra_v3_acquisition_path_bypass_audit_v1"
DEVELOPMENT_TASK_COUNT = 14
FEW_SHOT_TASK_COUNT = 3
CALIBRATION_TASK_COUNT = 11
FORMAL_TASK_COUNT = 86
MACHINE_EVIDENCE_KEYS = (
    "protocol_manifest",
    "oracle_validation",
    "acquisition_path_coverage",
)
MANUAL_REVIEW_KEYS = (
    "development_14_partition_and_exclusion",
    "formal_86_case_and_oracle_authoring",
    "query_naturalness_and_leakage",
    "human_oracle_runs",
    "double_step_annotation_and_adjudication",
    "acquisition_path_coverage_audit",
    "formal_86_statistics_and_fairness",
    "publication_method_consistency",
)
MAINTAINED_HARNESSES = (
    "camel-ai",
    "claude-code",
    "deerflow",
    "flowsearcher-ds",
    "gpt-researcher",
    "ii-researcher",
    "langchain-odr",
    "ldr",
    "opencode",
    "qx-agents",
    "smolagents",
    "storm",
)
PUBLICATION_SURFACES = ("paper", "website", "datasheet", "scorer", "board_json")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVIEWED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T[^\s]+)?$")
_TOP_LEVEL_KEYS = {"schema", "machine_evidence", "manual_reviews"}
_MACHINE_RECORD_KEYS = {"status", "artifact"}
_MACHINE_ARTIFACT_KEYS = {"path", "sha256"}
_MANUAL_ARTIFACT_KEYS = {"path", "sha256"}
_REVIEWER_KEYS = {"name", "reviewed_at", "signature"}
_ORACLE_BUNDLE_KEYS = {
    "schema",
    "status",
    "protocol_manifest_sha256",
    "task_ids",
    "validation_results",
    "bundle_sha256",
}
_ORACLE_VALIDATION_RESULT_KEYS = {
    "schema",
    "validation_semantics",
    "suite_id",
    "suite_sha256",
    "task_id",
    "validation_scope",
    "validation_tier",
    "status",
    "artifacts",
    "oracle_results",
    "adversarial_results",
    "manual_human_record",
    "manual_human_status",
    "formal_human_validation_passed",
    "formal_pilot_passed",
    "synthetic_only",
    "requires_real_human_followup",
    "required_adversarial_categories",
    "validation_sha256",
}
_ORACLE_VALIDATION_ENTRY_KEYS = {"suite", "result"}
_ACQUISITION_MATRIX_KEYS = {
    "schema",
    "status",
    "protocol_manifest_sha256",
    "development_task_ids",
    "harnesses",
    "matrix_sha256",
}
_ACQUISITION_HARNESS_KEYS = {
    "harness_id",
    "acquisition_paths",
}
_ACQUISITION_PATH_KEYS = {
    "acquisition_path_id",
    "capability_class",
    "leaderboard_protocol",
    "development_task_id",
    "run_id",
    "ledger",
    "conformance_result",
    "isolation_audit",
    "bypass_audit",
}
_CONFORMANCE_RESULT_KEYS = {
    "schema",
    "status",
    "harness_id",
    "acquisition_path_id",
    "development_task_id",
    "run_id",
    "search_produces_s",
    "fetch_produces_f_with_body_sha256",
    "fetched_body_produces_l",
    "l_only_denies_body_support",
    "f_only_marks_guessed_then_fetched",
    "citation_backreferences_observation",
}
_PATH_AUDIT_KEYS = {
    "schema",
    "status",
    "harness_id",
    "acquisition_path_id",
    "run_id",
}
_CONFORMANCE_BOOLEAN_FIELDS = (
    "search_produces_s",
    "fetch_produces_f_with_body_sha256",
    "fetched_body_produces_l",
    "l_only_denies_body_support",
    "f_only_marks_guessed_then_fetched",
    "citation_backreferences_observation",
)
_PROOF_MOTIFS = {
    "claim_verification",
    "evidence_reconciliation",
    "multi_branch_synthesis",
    "causal_or_evolution_explanation",
    "constraint_match_and_select",
}
_FORMAL_PROOF_FORBIDDEN_ALIASES = {
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
}


class ReleaseReadinessV3Error(ValueError):
    """Raised when a readiness document is structurally invalid."""


def _machine_record(*, protocol: bool = False) -> dict[str, Any]:
    # ``protocol`` documents why the protocol manifest uses null status fields
    # once supplied; a fresh template intentionally supplies no artifact at all.
    _ = protocol
    return {"status": "pending", "artifact": None}


def _review_stub(**fields: Any) -> dict[str, Any]:
    return {
        "status": "pending",
        **fields,
        "evidence": [],
        "reviewers": [],
        "notes": "",
    }


def new_release_readiness_template() -> dict[str, Any]:
    """Return a fresh deterministic TODO document; it is never a pass result."""

    return {
        "schema": RELEASE_READINESS_SCHEMA,
        "machine_evidence": {
            "protocol_manifest": _machine_record(protocol=True),
            "oracle_validation": _machine_record(),
            "acquisition_path_coverage": _machine_record(),
        },
        "manual_reviews": {
            "development_14_partition_and_exclusion": _review_stub(
                development_tasks=[],
                few_shot_examples=[],
                calibration_task_ids=[],
                headline_exclusion_evidence=None,
            ),
            "formal_86_case_and_oracle_authoring": _review_stub(
                task_ids=[],
                dataset_role=None,
                case_specs_authored=False,
                support_spans_authored=False,
                decision_rules_authored=False,
                oracle_materials_authored=False,
            ),
            "query_naturalness_and_leakage": _review_stub(
                task_ids=[],
                naturalness_reviewed=False,
                no_gold_or_scorer_leakage_reviewed=False,
                decision_priority_reviewed=False,
                constraint_diff_empty=False,
            ),
            "human_oracle_runs": _review_stub(task_ids=[], runs=[]),
            "double_step_annotation_and_adjudication": {
                "status": "pending",
                "annotation_unit": "step_pass_fail",
                "task_ids": [],
                "annotator_names": [],
                "adjudicator_name": None,
                "preregistered_threshold": None,
                "observed_agreement": None,
                "disagreement_count": None,
                "adjudicated_disagreement_count": None,
                "all_steps_double_annotated": False,
                "preregistration_evidence": None,
                "measurement_evidence": None,
                "adjudication_evidence": None,
                "reviewers": [],
                "notes": "",
            },
            "acquisition_path_coverage_audit": {
                "status": "pending",
                "development_task_ids": [],
                "harnesses": [],
                "reviewers": [],
                "notes": "",
            },
            "formal_86_statistics_and_fairness": {
                "status": "pending",
                "formal_task_count": None,
                "development_tasks_excluded": False,
                "cluster_bootstrap_ci_passed": False,
                "replicate_stability_passed": False,
                "harness_fairness_passed": False,
                "validation_panel_evidence": None,
                "cluster_bootstrap_ci_evidence": None,
                "replicate_stability_evidence": None,
                "harness_fairness_evidence": None,
                "reviewers": [],
                "notes": "",
            },
            "publication_method_consistency": {
                "status": "pending",
                "surfaces": {},
                "reviewers": [],
                "notes": "",
            },
        },
    }


def canonical_json_bytes(value: object) -> bytes:
    """Return stable JSON bytes used by the CLI and determinism tests."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _object(value: object, path: str, errors: list[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append(f"{path}: expected an object")
        return None
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], path: str, errors: list[str]
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        errors.append(f"{path}: missing fields {missing}")
    if unknown:
        errors.append(f"{path}: unknown fields {unknown}")


def _nonempty_strings(value: object, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{path}: expected a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{path}: values must be unique")
    return list(value)


def _resolve_artifact(path_text: str, base_dir: Path) -> Path:
    source = Path(path_text)
    return source if source.is_absolute() else base_dir / source


def _artifact_ref_identity(value: object) -> tuple[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    path = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        return None
    return path, digest


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_artifact_ref(
    value: object,
    *,
    path: str,
    base_dir: Path,
    errors: list[str],
    machine: bool,
) -> tuple[Path, Mapping[str, Any], bytes] | None:
    ref = _object(value, path, errors)
    if ref is None:
        return None
    _exact_keys(
        ref,
        _MACHINE_ARTIFACT_KEYS if machine else _MANUAL_ARTIFACT_KEYS,
        path,
        errors,
    )
    path_text = ref.get("path")
    declared_hash = ref.get("sha256")
    if not isinstance(path_text, str) or not path_text.strip():
        errors.append(f"{path}.path: expected a non-empty path")
        return None
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        errors.append(f"{path}.sha256: expected lowercase SHA-256")
        return None
    source = _resolve_artifact(path_text, base_dir)
    if not source.is_file():
        errors.append(f"{path}.path: artifact is not a file: {source}")
        return None
    try:
        first = source.read_bytes()
        second = source.read_bytes()
    except OSError as exc:
        errors.append(f"{path}.path: cannot read artifact: {exc}")
        return None
    if first != second:
        errors.append(f"{path}.path: artifact changed while being read")
        return None
    actual_hash = hashlib.sha256(first).hexdigest()
    if actual_hash != declared_hash:
        errors.append(
            f"{path}.sha256: artifact hash mismatch ({actual_hash} != {declared_hash})"
        )
        return None
    return source, ref, first


def _json_field(document: object, dotted: str) -> object:
    cursor = document
    for part in dotted.split("."):
        if not part or not isinstance(cursor, Mapping) or part not in cursor:
            raise KeyError(dotted)
        cursor = cursor[part]
    return cursor


def _self_hash(document: Mapping[str, Any], field: str) -> str:
    payload = {key: value for key, value in document.items() if key != field}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _read_json_artifact(payload: bytes, path: str, errors: list[str]) -> Any | None:
    try:
        return json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{path}: expected valid UTF-8 JSON: {exc}")
        return None


def _validate_score_hash(
    row: Mapping[str, Any], *, path: str, errors: list[str]
) -> Mapping[str, Any] | None:
    score = _object(row.get("score"), f"{path}.score", errors)
    score_hash = row.get("score_sha256")
    if not isinstance(score_hash, str) or not _SHA256_RE.fullmatch(score_hash):
        errors.append(f"{path}.score_sha256: expected lowercase SHA-256")
        return score
    if score is not None:
        actual = hashlib.sha256(canonical_json_bytes(score)).hexdigest()
        if score_hash != actual:
            errors.append(f"{path}.score_sha256: score self-hash mismatch")
    return score


def _exact_scalar(actual: object, expected: object) -> bool:
    """Compare JSON scalars without Python's bool/int equality aliasing."""

    return type(actual) is type(expected) and actual == expected


def _validate_score_replay_identity(
    score: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    path: str,
    expected_agent: str,
    task_id: str,
    case_sha256: str,
    public_task_sha256: str,
    protocol_manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    task_clusters = protocol_manifest.get("task_clusters")
    if (
        not isinstance(task_id, str)
        or not task_id
        or not isinstance(task_clusters, Mapping)
        or task_id not in task_clusters
    ):
        errors.append(f"{path}.score.task_id: task is absent from protocol manifest")
        return
    report_audit = row.get("report_artifact")
    report_sha256 = (
        report_audit.get("sha256") if isinstance(report_audit, Mapping) else None
    )
    protocols = protocol_manifest["protocols"]
    identity = {
        "run_id": row.get("run_id"),
        "agent": expected_agent,
        "task_id": task_id,
        "replicate": 1,
        "cluster_id": task_clusters[task_id],
        "report_sha256": report_sha256,
        "observation_ledger_sha256": score.get("observation_ledger_sha256"),
        "case_artifact_sha256": case_sha256,
        "public_task_sha256": public_task_sha256,
        "protocol_manifest_sha256": protocol_manifest["manifest_sha256"],
        "corpus_registry_hash": protocols["corpus_registry_hash"],
    }
    for field, expected in identity.items():
        if not _exact_scalar(score.get(field), expected):
            errors.append(f"{path}.score.{field}: replay identity mismatch")
    for field in (
        "report_sha256",
        "observation_ledger_sha256",
        "case_artifact_sha256",
        "public_task_sha256",
        "protocol_manifest_sha256",
        "corpus_registry_hash",
        "scoring_input_sha256",
    ):
        if not isinstance(score.get(field), str) or not _SHA256_RE.fullmatch(
            str(score.get(field) or "")
        ):
            errors.append(f"{path}.score.{field}: expected lowercase SHA-256")
    expected_input_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "version": "dra_v3_scoring_input_v2",
                **identity,
            }
        )
    ).hexdigest()
    if score.get("scoring_input_sha256") != expected_input_hash:
        errors.append(
            f"{path}.score.scoring_input_sha256: replay hash mismatch"
        )
    score_protocols = score.get("protocols")
    expected_protocol_keys = set(protocols) | {"corpus_url_set_hash"}
    if (
        not isinstance(score_protocols, Mapping)
        or set(score_protocols) != expected_protocol_keys
        or any(
            score_protocols.get(field) != value
            for field, value in protocols.items()
        )
        or not isinstance(score_protocols.get("corpus_url_set_hash"), str)
        or not _SHA256_RE.fullmatch(
            str(score_protocols.get("corpus_url_set_hash") or "")
        )
    ):
        errors.append(f"{path}.score.protocols: protocol stamp mismatch")


def _validate_proof_score_contract(
    score: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    path: str,
    expected_agent: str,
    task_id: str,
    protocol_manifest: Mapping[str, Any],
    require_full_pass: bool,
    errors: list[str],
) -> None:
    """Replay the independent proof-step score contract used by Formal-86."""

    forbidden = sorted(_FORMAL_PROOF_FORBIDDEN_ALIASES & set(score))
    if forbidden:
        errors.append(
            f"{path}.score: formal proof-step score contains legacy aliases {forbidden}"
        )
    if "quality" in score or "truth" in score:
        errors.append(f"{path}.score: legacy quality/truth fields are forbidden")
    expected_scalars = {
        "agent": expected_agent,
        "task_id": task_id,
        "replicate": 1,
        "cluster_id": protocol_manifest.get("task_clusters", {}).get(task_id),
        "scoring_semantics": "proof_steps_v1",
        "status": "scored",
        "withheld": False,
        "scorer_observability_complete": True,
    }
    for field, expected in expected_scalars.items():
        if not _exact_scalar(score.get(field), expected):
            errors.append(
                f"{path}.score.{field}: expected {expected!r} for Formal-86 replay"
            )

    report = row.get("report_artifact")
    ledger = row.get("ledger_artifact")
    report_sha256 = report.get("sha256") if isinstance(report, Mapping) else None
    ledger_sha256 = ledger.get("sha256") if isinstance(ledger, Mapping) else None
    if score.get("report_sha256") != report_sha256:
        errors.append(f"{path}.score.report_sha256: report artifact binding mismatch")
    # Inline ledgers use canonical-JSON hashing in both places.  A path audit
    # intentionally binds raw file bytes, while the scorer identity binds the
    # materialized ledger's canonical hash; pretty-printing can make those two
    # valid hashes differ.  Exact suite replay verifies path-ledger linkage.
    if (
        isinstance(ledger, Mapping)
        and ledger.get("source") == "inline"
        and score.get("observation_ledger_sha256") != ledger_sha256
    ):
        errors.append(
            f"{path}.score.observation_ledger_sha256: ledger artifact binding mismatch"
        )

    try:
        from src.eval.board_v3 import (
            V3BoardError,
            _proof_steps_from_record,
            _validate_proof_replay_identity,
        )
        from src.eval.protocol_v3 import (
            assert_comparable,
            validate_proof_steps_protocol,
        )

        base_protocol = validate_proof_steps_protocol(
            protocol_manifest["protocols"], formal=True
        )
        assert_comparable(base_protocol, score, formal=True)
        score_protocol = validate_proof_steps_protocol(score, formal=True)
        mismatches = sorted(
            field
            for field, value in base_protocol.items()
            if score_protocol.get(field) != value
        )
        if mismatches:
            raise V3BoardError(
                "proof-step score protocol differs from manifest: "
                + ", ".join(mismatches)
            )
        key = (expected_agent, task_id, 1)
        _validate_proof_replay_identity(
            score, base_protocol, protocol_manifest, key
        )
        metrics = _proof_steps_from_record(score, key=key, formal=True)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"{path}.score: invalid proof_steps_v1 replay: {exc}")
        return

    if require_full_pass:
        required = {
            "partial_completion": 1.0,
            "full_pass": 1,
            "final_answer_pass": True,
            "critical_contradictions": 0,
            "fabricated_citations": 0,
        }
        for field, expected in required.items():
            if not _exact_scalar(score.get(field), expected):
                errors.append(
                    f"{path}.score.{field}: positive oracle requires {expected!r}"
                )
        if metrics.get("full_pass") != 1.0:
            errors.append(f"{path}.score.full_pass: positive oracle did not replay")
    elif not _exact_scalar(score.get("full_pass"), 0):
        errors.append(f"{path}.score.full_pass: adversarial run must fail")


def _validate_embedded_artifact_audit(
    value: object, *, path: str, errors: list[str]
) -> None:
    audit = _object(value, path, errors)
    if audit is None:
        return
    source = audit.get("source")
    expected = (
        {"source", "relative_path", "sha256", "hash_basis"}
        if source == "path"
        else {"source", "sha256", "hash_basis"}
    )
    _exact_keys(audit, expected, path, errors)
    if not isinstance(source, str) or source not in {"path", "inline"}:
        errors.append(f"{path}.source: expected 'path' or 'inline'")
    if source == "path" and (
        not isinstance(audit.get("relative_path"), str)
        or not audit.get("relative_path", "").strip()
    ):
        errors.append(f"{path}.relative_path: required for path artifacts")
    digest = audit.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        errors.append(f"{path}.sha256: expected lowercase SHA-256")
    hash_basis = audit.get("hash_basis")
    if not isinstance(hash_basis, str) or hash_basis not in {
        "raw_bytes",
        "canonical_json",
        "utf8_text",
    }:
        errors.append(f"{path}.hash_basis: unknown hash basis")


def _validate_formal_oracle_result(
    raw: object,
    *,
    path: str,
    protocol_manifest: Mapping[str, Any],
    protocol_file_hashes: set[str],
    errors: list[str],
    score_semantics: str = "proof_steps_v1",
) -> str | None:
    if score_semantics not in {"proof_steps_v1", "verified_slots_v1"}:
        errors.append(f"{path}: unsupported score semantics {score_semantics!r}")
        return None
    result = _object(raw, path, errors)
    if result is None:
        return None
    _exact_keys(result, _ORACLE_VALIDATION_RESULT_KEYS, path, errors)
    try:
        from src.eval.oracle_validation_v3 import (
            CORE_ORACLE_KINDS,
            REQUIRED_ADVERSARIAL_CATEGORIES,
            VALIDATION_SCHEMA,
            VALIDATION_SEMANTICS,
            verify_validation_result,
        )
    except ImportError as exc:  # pragma: no cover - packaging/configuration failure
        errors.append(f"{path}: oracle validator is unavailable: {exc}")
        return None
    if not verify_validation_result(result):
        errors.append(f"{path}: validation result schema/self-hash is invalid")
    expected_scalars = {
        "schema": VALIDATION_SCHEMA,
        "validation_semantics": VALIDATION_SEMANTICS,
        "validation_scope": "formal",
        "validation_tier": "formal_human_attested",
        "status": "validated",
        "manual_human_status": "attested_and_replayed",
        "formal_human_validation_passed": True,
        "formal_pilot_passed": True,
        "synthetic_only": False,
        "requires_real_human_followup": False,
    }
    for field, expected in expected_scalars.items():
        if not _exact_scalar(result.get(field), expected):
            errors.append(f"{path}.{field}: expected {expected!r}")
    for field in ("suite_id", "task_id"):
        if not isinstance(result.get(field), str) or not result.get(field, "").strip():
            errors.append(f"{path}.{field}: expected a non-empty string")
    if not isinstance(result.get("suite_sha256"), str) or not _SHA256_RE.fullmatch(
        str(result.get("suite_sha256") or "")
    ):
        errors.append(f"{path}.suite_sha256: expected lowercase SHA-256")

    task_id_value = result.get("task_id")
    task_id = task_id_value if isinstance(task_id_value, str) else ""
    manifest_task_ids = protocol_manifest.get("task_ids")
    if not isinstance(manifest_task_ids, list) or task_id not in manifest_task_ids:
        errors.append(f"{path}.task_id: task is absent from protocol manifest")
    artifacts = _object(result.get("artifacts"), f"{path}.artifacts", errors)
    case_sha256 = ""
    public_task_sha256 = ""
    if artifacts is not None:
        if set(artifacts) != {
            "case", "public_task", "evidence_graph", "protocols"
        }:
            errors.append(
                f"{path}.artifacts: formal validation requires exactly case, "
                "public_task, evidence_graph, and protocols"
            )
        protocol_audit = _object(
            artifacts.get("protocols"), f"{path}.artifacts.protocols", errors
        )
        if protocol_audit is not None:
            audit_hash = protocol_audit.get("sha256")
            if (
                not isinstance(audit_hash, str)
                or audit_hash not in protocol_file_hashes
            ):
                errors.append(
                    f"{path}.artifacts.protocols.sha256: result was replayed "
                    "against a different protocol manifest"
                )
        case_audit = _object(
            artifacts.get("case"), f"{path}.artifacts.case", errors
        )
        public_audit = _object(
            artifacts.get("public_task"),
            f"{path}.artifacts.public_task",
            errors,
        )
        if case_audit is not None:
            case_sha256 = str(case_audit.get("sha256") or "")
            if (
                case_audit.get("source") != "path"
                or case_audit.get("hash_basis") != "raw_bytes"
            ):
                errors.append(
                    f"{path}.artifacts.case: formal case must bind raw path bytes"
                )
        if public_audit is not None:
            public_task_sha256 = str(public_audit.get("sha256") or "")
            if (
                public_audit.get("source") != "path"
                or public_audit.get("hash_basis") != "raw_bytes"
            ):
                errors.append(
                    f"{path}.artifacts.public_task: formal public task must bind raw path bytes"
                )
        if task_id in protocol_manifest.get("case_hashes", {}):
            if case_sha256 != protocol_manifest["case_hashes"][task_id]:
                errors.append(
                    f"{path}.artifacts.case.sha256: does not match protocol case bytes"
                )
            if public_task_sha256 != protocol_manifest["public_task_hashes"][task_id]:
                errors.append(
                    f"{path}.artifacts.public_task.sha256: does not match protocol public task bytes"
                )
        for name in ("case", "public_task", "evidence_graph", "protocols"):
            _validate_embedded_artifact_audit(
                artifacts.get(name), path=f"{path}.artifacts.{name}", errors=errors
            )

    manual = _object(
        result.get("manual_human_record"), f"{path}.manual_human_record", errors
    )
    if manual is not None:
        _exact_keys(
            manual,
            {"origin", "reviewer", "solve_minutes", "access_path", "attested", "synthetic"},
            f"{path}.manual_human_record",
            errors,
        )
        if manual.get("origin") != "manual" or manual.get("attested") is not True:
            errors.append(f"{path}.manual_human_record: real manual attestation required")
        if manual.get("synthetic") is not False:
            errors.append(f"{path}.manual_human_record.synthetic must be false")
        if not isinstance(manual.get("reviewer"), str) or not manual.get("reviewer", "").strip():
            errors.append(f"{path}.manual_human_record.reviewer is required")
        minutes = manual.get("solve_minutes")
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not math.isfinite(float(minutes))
            or minutes <= 0
        ):
            errors.append(f"{path}.manual_human_record.solve_minutes must be positive")
        access = manual.get("access_path")
        if not isinstance(access, list) or not access or any(
            not isinstance(url, str) or not url.strip() for url in access
        ):
            errors.append(f"{path}.manual_human_record.access_path must be non-empty")

    raw_oracles = result.get("oracle_results")
    kinds: list[str] = []
    run_ids: list[str] = []
    if not isinstance(raw_oracles, list):
        errors.append(f"{path}.oracle_results: expected an array")
    else:
        for index, raw_row in enumerate(raw_oracles):
            row_path = f"{path}.oracle_results[{index}]"
            row = _object(raw_row, row_path, errors)
            if row is None:
                continue
            allowed = {
                "run_id", "kind", "report_artifact", "ledger_artifact",
                "score_sha256", "score", "answer",
            }
            unknown = set(row) - allowed
            required = allowed - {"answer"}
            if unknown or not required <= set(row):
                errors.append(
                    f"{row_path}: oracle result fields are incomplete or unknown"
                )
            kind = row.get("kind")
            if isinstance(kind, str):
                kinds.append(kind)
            else:
                errors.append(f"{row_path}.kind: expected a string")
            run_id = row.get("run_id")
            if isinstance(run_id, str) and run_id.strip():
                run_ids.append(run_id)
            else:
                errors.append(f"{row_path}.run_id: expected a non-empty string")
            _validate_embedded_artifact_audit(
                row.get("report_artifact"),
                path=f"{row_path}.report_artifact",
                errors=errors,
            )
            _validate_embedded_artifact_audit(
                row.get("ledger_artifact"),
                path=f"{row_path}.ledger_artifact",
                errors=errors,
            )
            score = _validate_score_hash(row, path=row_path, errors=errors)
            if score is not None:
                if score_semantics == "proof_steps_v1":
                    _validate_proof_score_contract(
                        score,
                        row,
                        path=row_path,
                        expected_agent=f"oracle:{kind}",
                        task_id=task_id,
                        protocol_manifest=protocol_manifest,
                        require_full_pass=True,
                        errors=errors,
                    )
                else:
                    required_score = {
                        "status": "scored",
                        "withheld": False,
                        "scorer_observability_complete": True,
                        "task_pass": 1,
                        "verified_recall": 1.0,
                        "verified_research_completion": 1.0,
                        "critical_contradictions": 0,
                        "fabricated_citations": 0,
                    }
                    for field, expected in required_score.items():
                        if not _exact_scalar(score.get(field), expected):
                            errors.append(
                                f"{row_path}.score.{field}: expected {expected!r}"
                            )
                    _validate_score_replay_identity(
                        score,
                        row,
                        path=row_path,
                        expected_agent=f"oracle:{kind}",
                        task_id=task_id,
                        case_sha256=case_sha256,
                        public_task_sha256=public_task_sha256,
                        protocol_manifest=protocol_manifest,
                        errors=errors,
                    )
        for kind in sorted(CORE_ORACLE_KINDS):
            if kinds.count(kind) != 1:
                errors.append(f"{path}.oracle_results: requires exactly one {kind} oracle")
        unknown_kinds = set(kinds) - set(CORE_ORACLE_KINDS) - {"admissible_alternative"}
        if unknown_kinds:
            errors.append(f"{path}.oracle_results: unknown kinds {sorted(unknown_kinds)}")

    required_categories = list(REQUIRED_ADVERSARIAL_CATEGORIES)
    if result.get("required_adversarial_categories") != required_categories:
        errors.append(
            f"{path}.required_adversarial_categories: exact ten-category contract required"
        )
    raw_adversarial = result.get("adversarial_results")
    categories: list[str] = []
    if not isinstance(raw_adversarial, list):
        errors.append(f"{path}.adversarial_results: expected an array")
    else:
        for index, raw_row in enumerate(raw_adversarial):
            row_path = f"{path}.adversarial_results[{index}]"
            row = _object(raw_row, row_path, errors)
            if row is None:
                continue
            expected_fields = {
                "run_id", "category", "report_artifact", "ledger_artifact",
                "score_sha256", "score",
            }
            if set(row) != expected_fields:
                errors.append(f"{row_path}: adversarial result fields must be exact")
            category = row.get("category")
            if isinstance(category, str):
                categories.append(category)
            else:
                errors.append(f"{row_path}.category: expected a string")
            run_id = row.get("run_id")
            if isinstance(run_id, str) and run_id.strip():
                run_ids.append(run_id)
            else:
                errors.append(f"{row_path}.run_id: expected a non-empty string")
            _validate_embedded_artifact_audit(
                row.get("report_artifact"),
                path=f"{row_path}.report_artifact",
                errors=errors,
            )
            _validate_embedded_artifact_audit(
                row.get("ledger_artifact"),
                path=f"{row_path}.ledger_artifact",
                errors=errors,
            )
            score = _validate_score_hash(row, path=row_path, errors=errors)
            if score is not None:
                if score_semantics == "proof_steps_v1":
                    _validate_proof_score_contract(
                        score,
                        row,
                        path=row_path,
                        expected_agent=f"adversarial:{category}",
                        task_id=task_id,
                        protocol_manifest=protocol_manifest,
                        require_full_pass=False,
                        errors=errors,
                    )
                else:
                    required_score = {
                        "status": "scored",
                        "withheld": False,
                        "scorer_observability_complete": True,
                        "task_pass": 0,
                    }
                    for field, expected in required_score.items():
                        if not _exact_scalar(score.get(field), expected):
                            errors.append(
                                f"{row_path}.score.{field}: expected {expected!r}"
                            )
                    _validate_score_replay_identity(
                        score,
                        row,
                        path=row_path,
                        expected_agent=f"adversarial:{category}",
                        task_id=task_id,
                        case_sha256=case_sha256,
                        public_task_sha256=public_task_sha256,
                        protocol_manifest=protocol_manifest,
                        errors=errors,
                    )
        if (
            len(categories) != len(required_categories)
            or len(categories) != len(set(categories))
            or set(categories) != set(required_categories)
        ):
            errors.append(
                f"{path}.adversarial_results: must contain each of the ten categories once"
            )
    if len(run_ids) != len(set(run_ids)):
        errors.append(f"{path}: oracle/adversarial run_id values must be globally unique")
    return task_id or None


def _replay_oracle_suite(
    raw: object,
    *,
    source: Path,
    suite_sha256: str,
    path: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    """Replay one exact suite and return the result produced by the scorer."""

    if not isinstance(raw, Mapping):
        errors.append(f"{path}: oracle suite must be a JSON object")
        return None
    try:
        from src.eval.oracle_validation_v3 import (
            OracleSuiteValidationError,
            validate_oracle_suite,
        )

        return validate_oracle_suite(
            raw,
            base_dir=source.parent,
            suite_sha256=suite_sha256,
        )
    except (OracleSuiteValidationError, OSError, TypeError, ValueError) as exc:
        errors.append(f"{path}: formal suite replay failed: {exc}")
        return None


def _validate_oracle_release_bundle(
    raw: object,
    *,
    source: Path,
    protocol_manifest: Mapping[str, Any],
    protocol_task_ids: list[str],
    protocol_manifest_sha256: str,
    protocol_file_hashes: set[str],
    errors: list[str],
) -> bool:
    path = "machine_evidence.oracle_validation.artifact"
    bundle = _object(raw, path, errors)
    if bundle is None:
        return False
    _exact_keys(bundle, _ORACLE_BUNDLE_KEYS, path, errors)
    if bundle.get("schema") != ORACLE_RELEASE_BUNDLE_SCHEMA:
        errors.append(f"{path}.schema: expected {ORACLE_RELEASE_BUNDLE_SCHEMA!r}")
    if bundle.get("status") != "passed":
        errors.append(f"{path}.status: expected 'passed'")
    if bundle.get("protocol_manifest_sha256") != protocol_manifest_sha256:
        errors.append(f"{path}: protocol manifest self-hash mismatch")
    task_ids = _nonempty_strings(bundle.get("task_ids"), f"{path}.task_ids", errors)
    if task_ids != sorted(task_ids):
        errors.append(f"{path}.task_ids: must be sorted")
    if task_ids != protocol_task_ids or len(task_ids) != FORMAL_TASK_COUNT:
        errors.append(
            f"{path}.task_ids: must exactly equal the formal protocol Formal-86"
        )
    declared_hash = bundle.get("bundle_sha256")
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        errors.append(f"{path}.bundle_sha256: expected lowercase SHA-256")
    elif declared_hash != _self_hash(bundle, "bundle_sha256"):
        errors.append(f"{path}.bundle_sha256: bundle self-hash mismatch")
    refs = bundle.get("validation_results")
    result_task_ids: list[str] = []
    suite_paths: list[str] = []
    result_paths: list[str] = []
    if not isinstance(refs, list):
        errors.append(f"{path}.validation_results: expected an array")
    else:
        for index, raw_entry in enumerate(refs):
            entry_path = f"{path}.validation_results[{index}]"
            entry = _object(raw_entry, entry_path, errors)
            if entry is None:
                continue
            _exact_keys(entry, _ORACLE_VALIDATION_ENTRY_KEYS, entry_path, errors)
            suite_checked = _validate_artifact_ref(
                entry.get("suite"),
                path=f"{entry_path}.suite",
                base_dir=source.parent,
                errors=errors,
                machine=False,
            )
            result_checked = _validate_artifact_ref(
                entry.get("result"),
                path=f"{entry_path}.result",
                base_dir=source.parent,
                errors=errors,
                machine=False,
            )
            for field, paths in (("suite", suite_paths), ("result", result_paths)):
                value = entry.get(field)
                if isinstance(value, Mapping) and isinstance(value.get("path"), str):
                    paths.append(str(value["path"]))
            if suite_checked is None or result_checked is None:
                continue
            suite_source, suite_ref, suite_bytes = suite_checked
            _, _, result_bytes = result_checked
            suite_raw = _read_json_artifact(
                suite_bytes,
                f"{entry_path}.suite",
                errors,
            )
            validation_raw = _read_json_artifact(
                result_bytes,
                f"{entry_path}.result",
                errors,
            )
            replayed = _replay_oracle_suite(
                suite_raw,
                source=suite_source,
                suite_sha256=str(suite_ref["sha256"]),
                path=f"{entry_path}.suite",
                errors=errors,
            )
            if (
                replayed is not None
                and validation_raw is not None
                and canonical_json_bytes(replayed)
                != canonical_json_bytes(validation_raw)
            ):
                errors.append(
                    f"{entry_path}.result: bytes do not match deterministic suite replay"
                )
            task_id = _validate_formal_oracle_result(
                validation_raw,
                path=f"{entry_path}.result",
                protocol_manifest=protocol_manifest,
                protocol_file_hashes=protocol_file_hashes,
                errors=errors,
            )
            if task_id:
                result_task_ids.append(task_id)
    if len(suite_paths) != len(set(suite_paths)):
        errors.append(f"{path}.validation_results: suite artifact paths must be unique")
    if len(result_paths) != len(set(result_paths)):
        errors.append(f"{path}.validation_results: result artifact paths must be unique")
    if result_task_ids != task_ids:
        errors.append(
            f"{path}.validation_results: must replay every Formal-86 task once "
            "in protocol order"
        )
    return not any(error.startswith(path) for error in errors)


def _validate_path_audit(
    raw: object,
    *,
    path: str,
    expected_schema: str,
    harness_id: str,
    acquisition_path_id: str,
    run_id: str,
    errors: list[str],
) -> None:
    audit = _object(raw, path, errors)
    if audit is None:
        return
    _exact_keys(audit, _PATH_AUDIT_KEYS, path, errors)
    expected = {
        "schema": expected_schema,
        "status": "passed",
        "harness_id": harness_id,
        "acquisition_path_id": acquisition_path_id,
        "run_id": run_id,
    }
    for field, value in expected.items():
        if not _exact_scalar(audit.get(field), value):
            errors.append(f"{path}.{field}: expected {value!r}")


def _validate_acquisition_path_coverage(
    raw: object,
    *,
    source: Path,
    protocol_manifest_sha256: str,
    errors: list[str],
) -> tuple[bool, list[str], dict[str, dict[str, str]]]:
    path = "machine_evidence.acquisition_path_coverage.artifact"
    matrix = _object(raw, path, errors)
    if matrix is None:
        return False, [], {}
    _exact_keys(matrix, _ACQUISITION_MATRIX_KEYS, path, errors)
    if matrix.get("schema") != ACQUISITION_PATH_COVERAGE_SCHEMA:
        errors.append(
            f"{path}.schema: expected {ACQUISITION_PATH_COVERAGE_SCHEMA!r}"
        )
    if matrix.get("status") != "passed":
        errors.append(f"{path}.status: expected 'passed'")
    if matrix.get("protocol_manifest_sha256") != protocol_manifest_sha256:
        errors.append(f"{path}: protocol manifest self-hash mismatch")
    development_task_ids = _nonempty_strings(
        matrix.get("development_task_ids"),
        f"{path}.development_task_ids",
        errors,
    )
    if development_task_ids != sorted(development_task_ids):
        errors.append(f"{path}.development_task_ids: must be sorted")
    if len(development_task_ids) != DEVELOPMENT_TASK_COUNT:
        errors.append(
            f"{path}.development_task_ids: must contain exactly Dev-14"
        )
    declared_hash = matrix.get("matrix_sha256")
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        errors.append(f"{path}.matrix_sha256: expected lowercase SHA-256")
    elif declared_hash != _self_hash(matrix, "matrix_sha256"):
        errors.append(f"{path}.matrix_sha256: matrix self-hash mismatch")

    raw_harnesses = matrix.get("harnesses")
    harness_ids: list[str] = []
    run_ids: list[str] = []
    evidence_refs: list[tuple[str, str]] = []
    coverage: dict[str, dict[str, str]] = {}
    if not isinstance(raw_harnesses, list):
        errors.append(f"{path}.harnesses: expected an array")
    else:
        for harness_index, raw_harness in enumerate(raw_harnesses):
            harness_path = f"{path}.harnesses[{harness_index}]"
            harness = _object(raw_harness, harness_path, errors)
            if harness is None:
                continue
            _exact_keys(
                harness, _ACQUISITION_HARNESS_KEYS, harness_path, errors
            )
            harness_id = harness.get("harness_id")
            if isinstance(harness_id, str) and harness_id:
                harness_ids.append(harness_id)
            else:
                errors.append(f"{harness_path}.harness_id: required")
                harness_id = ""
            raw_paths = harness.get("acquisition_paths")
            if not isinstance(raw_paths, list) or not raw_paths:
                errors.append(
                    f"{harness_path}.acquisition_paths: every harness must declare "
                    "at least one supported acquisition path"
                )
                continue
            path_bindings: dict[str, str] = {}
            for path_index, raw_path_entry in enumerate(raw_paths):
                entry_path = (
                    f"{harness_path}.acquisition_paths[{path_index}]"
                )
                entry = _object(raw_path_entry, entry_path, errors)
                if entry is None:
                    continue
                _exact_keys(entry, _ACQUISITION_PATH_KEYS, entry_path, errors)
                acquisition_path_id = entry.get("acquisition_path_id")
                if (
                    not isinstance(acquisition_path_id, str)
                    or not acquisition_path_id.strip()
                ):
                    errors.append(
                        f"{entry_path}.acquisition_path_id: required"
                    )
                    acquisition_path_id = ""
                elif acquisition_path_id in path_bindings:
                    errors.append(
                        f"{harness_path}.acquisition_paths: duplicate "
                        f"acquisition_path_id {acquisition_path_id!r}"
                    )
                capability = entry.get("capability_class")
                if capability not in {
                    "fetch_capable",
                    "snippet_only_separate_protocol",
                }:
                    errors.append(
                        f"{entry_path}.capability_class: expected fetch_capable "
                        "or snippet_only_separate_protocol"
                    )
                leaderboard_protocol = entry.get("leaderboard_protocol")
                if (
                    not isinstance(leaderboard_protocol, str)
                    or not leaderboard_protocol.strip()
                ):
                    errors.append(
                        f"{entry_path}.leaderboard_protocol: explicit protocol "
                        "assignment is required"
                    )
                development_task_id = entry.get("development_task_id")
                if (
                    not isinstance(development_task_id, str)
                    or development_task_id not in set(development_task_ids)
                ):
                    errors.append(
                        f"{entry_path}.development_task_id: must belong to Dev-14"
                    )
                    development_task_id = ""
                run_id = entry.get("run_id")
                if not isinstance(run_id, str) or not run_id.strip():
                    errors.append(f"{entry_path}.run_id: required")
                    run_id = ""
                else:
                    run_ids.append(run_id)
                if acquisition_path_id:
                    path_bindings[acquisition_path_id] = str(development_task_id)

                for field in (
                    "ledger",
                    "conformance_result",
                    "isolation_audit",
                    "bypass_audit",
                ):
                    checked = _validate_artifact_ref(
                        entry.get(field),
                        path=f"{entry_path}.{field}",
                        base_dir=source.parent,
                        errors=errors,
                        machine=False,
                    )
                    if checked is None:
                        continue
                    artifact_path, ref, artifact_bytes = checked
                    evidence_refs.append(
                        (str(ref["path"]), str(ref["sha256"]))
                    )
                    if field == "ledger" and run_id:
                        try:
                            from src.eval.observation_ledger import load_observation_ledger

                            ledger = load_observation_ledger(
                                artifact_path,
                                expected_run_id=run_id,
                                allow_legacy=False,
                            )
                        except (OSError, TypeError, ValueError) as exc:
                            errors.append(
                                f"{entry_path}.ledger: cannot validate ledger: {exc}"
                            )
                        else:
                            if not ledger.complete:
                                reasons = [issue.code for issue in ledger.issues]
                                errors.append(
                                    f"{entry_path}.ledger: complete native ledger required; "
                                    f"issues={reasons}"
                                )
                            elif not ledger.events:
                                errors.append(
                                    f"{entry_path}.ledger: acquisition-path conformance "
                                    "requires "
                                    "at least one captured observation event"
                                )
                            if _hash_file(artifact_path) != ref["sha256"]:
                                errors.append(
                                    f"{entry_path}.ledger: artifact changed during validation"
                                )
                    elif field == "conformance_result":
                        audit = _read_json_artifact(
                            artifact_bytes, f"{entry_path}.{field}", errors
                        )
                        audit_obj = _object(
                            audit, f"{entry_path}.{field}", errors
                        )
                        if audit_obj is not None:
                            _exact_keys(
                                audit_obj,
                                _CONFORMANCE_RESULT_KEYS,
                                f"{entry_path}.{field}",
                                errors,
                            )
                            expected_scalars = {
                                "schema": ACQUISITION_PATH_CONFORMANCE_SCHEMA,
                                "status": "passed",
                                "harness_id": harness_id,
                                "acquisition_path_id": acquisition_path_id,
                                "development_task_id": development_task_id,
                                "run_id": run_id,
                            }
                            for name, expected in expected_scalars.items():
                                if not _exact_scalar(
                                    audit_obj.get(name), expected
                                ):
                                    errors.append(
                                        f"{entry_path}.{field}.{name}: "
                                        f"expected {expected!r}"
                                    )
                            for name in _CONFORMANCE_BOOLEAN_FIELDS:
                                if audit_obj.get(name) is not True:
                                    errors.append(
                                        f"{entry_path}.{field}.{name}: must pass"
                                    )
                    elif field in {"isolation_audit", "bypass_audit"}:
                        audit = _read_json_artifact(
                            artifact_bytes, f"{entry_path}.{field}", errors
                        )
                        _validate_path_audit(
                            audit,
                            path=f"{entry_path}.{field}",
                            expected_schema=(
                                ISOLATION_AUDIT_SCHEMA
                                if field == "isolation_audit"
                                else BYPASS_AUDIT_SCHEMA
                            ),
                            harness_id=harness_id,
                            acquisition_path_id=acquisition_path_id,
                            run_id=run_id,
                            errors=errors,
                        )
            if harness_id:
                coverage[harness_id] = path_bindings

    if harness_ids != list(MAINTAINED_HARNESSES):
        errors.append(
            f"{path}.harnesses: must cover the 12 maintained harnesses in "
            "canonical order"
        )
    if len(run_ids) != len(set(run_ids)):
        errors.append(f"{path}.harnesses: path run_id values must be globally unique")
    if len(evidence_refs) != len(set(evidence_refs)):
        errors.append(
            f"{path}.harnesses: every path ledger/conformance/isolation/bypass "
            "artifact must be a distinct hashed file"
        )
    return (
        not any(error.startswith(path) for error in errors),
        development_task_ids,
        coverage,
    )


def _validate_machine_evidence(
    value: object, base_dir: Path, errors: list[str]
) -> tuple[
    list[str],
    list[str],
    list[str],
    str | None,
    list[str],
    dict[str, dict[str, str]],
]:
    machine = _object(value, "machine_evidence", errors)
    if machine is None:
        return list(MACHINE_EVIDENCE_KEYS), [], [], None, [], {}
    _exact_keys(machine, set(MACHINE_EVIDENCE_KEYS), "machine_evidence", errors)
    not_passed: list[str] = []
    verified: list[str] = []
    passed_artifacts: dict[str, tuple[Path, Mapping[str, Any], Any]] = {}
    for key in MACHINE_EVIDENCE_KEYS:
        record_path = f"machine_evidence.{key}"
        record = _object(machine.get(key), record_path, errors)
        if record is None:
            not_passed.append(key)
            continue
        _exact_keys(record, _MACHINE_RECORD_KEYS, record_path, errors)
        status = record.get("status")
        if not isinstance(status, str) or status not in {
            "pending",
            "passed",
            "failed",
        }:
            errors.append(f"{record_path}.status: expected pending, passed, or failed")
            not_passed.append(key)
            continue
        artifact = record.get("artifact")
        if status != "passed":
            not_passed.append(key)
            if artifact is not None:
                _validate_artifact_ref(
                    artifact,
                    path=f"{record_path}.artifact",
                    base_dir=base_dir,
                    errors=errors,
                    machine=True,
                )
            continue
        if artifact is None:
            errors.append(f"{record_path}: passed requires a hashed artifact")
            not_passed.append(key)
            continue
        checked = _validate_artifact_ref(
            artifact,
            path=f"{record_path}.artifact",
            base_dir=base_dir,
            errors=errors,
            machine=True,
        )
        if checked is None:
            not_passed.append(key)
            continue
        source, ref, artifact_bytes = checked
        raw = _read_json_artifact(
            artifact_bytes,
            f"{record_path}.artifact",
            errors,
        )
        if raw is None:
            not_passed.append(key)
            continue
        passed_artifacts[key] = (source, ref, raw)

    protocol_task_ids: list[str] = []
    protocol_manifest_sha256: str | None = None
    protocol_file_hashes: set[str] = set()
    protocol_item = passed_artifacts.get("protocol_manifest")
    if protocol_item is not None:
        source, ref, raw = protocol_item
        path = "machine_evidence.protocol_manifest.artifact"
        try:
            from src.eval.protocol_manifest_v3 import validate_v3_protocol_manifest
            from src.eval.protocol_v3 import validate_proof_steps_protocol

            protocol = validate_v3_protocol_manifest(raw)
            validate_proof_steps_protocol(protocol["protocols"], formal=True)
        except (TypeError, ValueError) as exc:
            errors.append(
                f"{path}: Formal-86 requires a proof_steps_v1 protocol manifest: {exc}"
            )
            not_passed.append("protocol_manifest")
        else:
            protocol_task_ids = list(protocol["task_ids"])
            protocol_manifest_sha256 = str(protocol["manifest_sha256"])
            if len(protocol_task_ids) != FORMAL_TASK_COUNT:
                errors.append(
                    f"{path}.task_ids: formal release requires exactly Formal-86"
                )
                not_passed.append("protocol_manifest")
            else:
                motifs = {
                    protocol["task_contracts"][task_id]["motif"]
                    for task_id in protocol_task_ids
                }
                if motifs != _PROOF_MOTIFS:
                    errors.append(
                        f"{path}.task_contracts: Formal-86 must cover every "
                        "proof motif"
                    )
                    not_passed.append("protocol_manifest")
            protocol_file_hashes = {
                str(ref["sha256"]),
                hashlib.sha256(canonical_json_bytes(protocol)).hexdigest(),
            }
            if "protocol_manifest" not in not_passed:
                verified.append("protocol_manifest")

    development_task_ids: list[str] = []
    acquisition_coverage: dict[str, dict[str, str]] = {}
    for key, validator in (
        ("oracle_validation", _validate_oracle_release_bundle),
        ("acquisition_path_coverage", _validate_acquisition_path_coverage),
    ):
        item = passed_artifacts.get(key)
        if item is None:
            continue
        if protocol_manifest_sha256 is None or not protocol_task_ids:
            errors.append(
                f"machine_evidence.{key}: cannot verify without a valid Formal-86 "
                "protocol manifest"
            )
            not_passed.append(key)
            continue
        source, _, raw = item
        if key == "oracle_validation":
            valid = validator(
                raw,
                source=source,
                protocol_manifest=protocol,
                protocol_task_ids=protocol_task_ids,
                protocol_manifest_sha256=protocol_manifest_sha256,
                protocol_file_hashes=protocol_file_hashes,
                errors=errors,
            )
        else:
            (
                valid,
                development_task_ids,
                acquisition_coverage,
            ) = validator(
                raw,
                source=source,
                protocol_manifest_sha256=protocol_manifest_sha256,
                errors=errors,
            )
        if valid:
            verified.append(key)
        else:
            not_passed.append(key)
    return (
        sorted(set(not_passed)),
        sorted(set(verified)),
        protocol_task_ids,
        protocol_manifest_sha256,
        development_task_ids,
        acquisition_coverage,
    )


def _validate_reviewers(
    value: object,
    *,
    path: str,
    errors: list[str],
    required_count: int,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path}: expected a reviewer list")
        return []
    names: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        reviewer = _object(item, item_path, errors)
        if reviewer is None:
            continue
        _exact_keys(reviewer, _REVIEWER_KEYS, item_path, errors)
        name = reviewer.get("name")
        reviewed_at = reviewer.get("reviewed_at")
        signature = reviewer.get("signature")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{item_path}.name: reviewer identity is required")
        else:
            names.append(name.strip())
        if not isinstance(reviewed_at, str) or not _REVIEWED_AT_RE.fullmatch(reviewed_at):
            errors.append(f"{item_path}.reviewed_at: use YYYY-MM-DD or ISO datetime")
        if not isinstance(signature, str) or not signature.strip():
            errors.append(f"{item_path}.signature: explicit human signature is required")
    if len(names) != len(set(names)):
        errors.append(f"{path}: reviewer identities must be distinct")
    if len(names) < required_count:
        errors.append(f"{path}: at least {required_count} signed reviewer(s) required")
    return names


def _validate_manual_evidence_list(
    value: object, *, path: str, base_dir: Path, errors: list[str], required: bool
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected an artifact list")
        return
    if required and not value:
        errors.append(f"{path}: at least one hashed review artifact is required")
    for index, ref in enumerate(value):
        _validate_artifact_ref(
            ref,
            path=f"{path}[{index}]",
            base_dir=base_dir,
            errors=errors,
            machine=False,
        )


def _validate_common_review(
    review: Mapping[str, Any],
    *,
    path: str,
    base_dir: Path,
    errors: list[str],
    complete: bool,
    reviewer_count: int = 1,
) -> None:
    if review.get("notes") is not None and not isinstance(review.get("notes"), str):
        errors.append(f"{path}.notes: expected a string")
    _validate_manual_evidence_list(
        review.get("evidence"),
        path=f"{path}.evidence",
        base_dir=base_dir,
        errors=errors,
        required=complete,
    )
    reviewers = review.get("reviewers")
    if complete or reviewers:
        _validate_reviewers(
            reviewers,
            path=f"{path}.reviewers",
            errors=errors,
            required_count=reviewer_count if complete else 0,
        )
    elif not isinstance(reviewers, list):
        errors.append(f"{path}.reviewers: expected a reviewer list")


def _manual_status(review: Mapping[str, Any], path: str, errors: list[str]) -> bool:
    status = review.get("status")
    if not isinstance(status, str) or status not in {"pending", "complete"}:
        errors.append(f"{path}.status: expected pending or complete")
    return status == "complete"


def _validate_development_review(
    value: object, base_dir: Path, errors: list[str]
) -> tuple[bool, list[str], list[str]]:
    path = "manual_reviews.development_14_partition_and_exclusion"
    review = _object(value, path, errors)
    expected = {
        "status",
        "development_tasks",
        "few_shot_examples",
        "calibration_task_ids",
        "headline_exclusion_evidence",
        "evidence",
        "reviewers",
        "notes",
    }
    if review is None:
        return False, [], []
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)

    development_ids: list[str] = []
    raw_tasks = review.get("development_tasks")
    if not isinstance(raw_tasks, list):
        errors.append(f"{path}.development_tasks: expected a list")
    else:
        for index, raw_task in enumerate(raw_tasks):
            item_path = f"{path}.development_tasks[{index}]"
            task = _object(raw_task, item_path, errors)
            if task is None:
                continue
            _exact_keys(
                task,
                {"task_id", "dataset_role", "excluded_from_headline"},
                item_path,
                errors,
            )
            task_id = task.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                errors.append(f"{item_path}.task_id: required")
            else:
                development_ids.append(task_id)
            if task.get("dataset_role") != "development":
                errors.append(
                    f"{item_path}.dataset_role: must be 'development'"
                )
            if task.get("excluded_from_headline") is not True:
                errors.append(
                    f"{item_path}.excluded_from_headline: must be true"
                )
    if len(development_ids) != len(set(development_ids)):
        errors.append(f"{path}.development_tasks: task_id values must be unique")

    few_shot_ids: list[str] = []
    few_shot_motifs: list[str] = []
    few_shot_refs: list[tuple[str, str]] = []
    raw_examples = review.get("few_shot_examples")
    if not isinstance(raw_examples, list):
        errors.append(f"{path}.few_shot_examples: expected a list")
    else:
        example_keys = {
            "task_id",
            "graph_motif",
            "generator_view",
            "human_written_query",
            "leakage_audit",
        }
        for index, raw_example in enumerate(raw_examples):
            item_path = f"{path}.few_shot_examples[{index}]"
            example = _object(raw_example, item_path, errors)
            if example is None:
                continue
            _exact_keys(example, example_keys, item_path, errors)
            task_id = example.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                errors.append(f"{item_path}.task_id: required")
            else:
                few_shot_ids.append(task_id)
            motif = example.get("graph_motif")
            if motif not in _PROOF_MOTIFS:
                errors.append(f"{item_path}.graph_motif: unknown proof motif")
            else:
                few_shot_motifs.append(str(motif))
            for field in (
                "generator_view",
                "human_written_query",
                "leakage_audit",
            ):
                ref = example.get(field)
                _validate_artifact_ref(
                    ref,
                    path=f"{item_path}.{field}",
                    base_dir=base_dir,
                    errors=errors,
                    machine=False,
                )
                identity = _artifact_ref_identity(ref)
                if identity is not None:
                    few_shot_refs.append(identity)
    calibration_ids = _nonempty_strings(
        review.get("calibration_task_ids"),
        f"{path}.calibration_task_ids",
        errors,
    )
    exclusion_ref = review.get("headline_exclusion_evidence")
    if exclusion_ref is not None:
        _validate_artifact_ref(
            exclusion_ref,
            path=f"{path}.headline_exclusion_evidence",
            base_dir=base_dir,
            errors=errors,
            machine=False,
        )

    if complete:
        if len(development_ids) != DEVELOPMENT_TASK_COUNT:
            errors.append(f"{path}: exactly Dev-14 tasks are required")
        if (
            len(few_shot_ids) != FEW_SHOT_TASK_COUNT
            or len(set(few_shot_ids)) != FEW_SHOT_TASK_COUNT
        ):
            errors.append(f"{path}: exactly three distinct few-shot tasks required")
        if len(set(few_shot_motifs)) != FEW_SHOT_TASK_COUNT:
            errors.append(
                f"{path}: the three few-shot examples must use distinct graph motifs"
            )
        if len(calibration_ids) != CALIBRATION_TASK_COUNT:
            errors.append(f"{path}: exactly 11 calibration tasks are required")
        if set(few_shot_ids) & set(calibration_ids):
            errors.append(f"{path}: few-shot and calibration task sets must be disjoint")
        if set(few_shot_ids) | set(calibration_ids) != set(development_ids):
            errors.append(
                f"{path}: three few-shot plus eleven calibration tasks must "
                "partition Dev-14"
            )
        if len(few_shot_refs) != 3 * FEW_SHOT_TASK_COUNT or len(
            set(few_shot_refs)
        ) != len(few_shot_refs):
            errors.append(
                f"{path}: each few-shot needs distinct GeneratorView, "
                "HumanWrittenQuery, and leakage-audit artifacts"
            )
        if exclusion_ref is None:
            errors.append(
                f"{path}: hashed evidence excluding Dev-14 from headline "
                "denominators is required"
            )
    _validate_common_review(
        review, path=path, base_dir=base_dir, errors=errors, complete=complete
    )
    return complete, development_ids, calibration_ids


def _validate_formal_case_review(
    value: object,
    base_dir: Path,
    errors: list[str],
    protocol_task_ids: list[str],
) -> tuple[bool, list[str]]:
    path = "manual_reviews.formal_86_case_and_oracle_authoring"
    review = _object(value, path, errors)
    expected = {
        "status", "task_ids", "dataset_role", "case_specs_authored", "support_spans_authored",
        "decision_rules_authored", "oracle_materials_authored", "evidence",
        "reviewers", "notes",
    }
    if review is None:
        return False, []
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    task_ids = _nonempty_strings(review.get("task_ids"), f"{path}.task_ids", errors)
    if review.get("dataset_role") not in {None, "formal"}:
        errors.append(f"{path}.dataset_role: expected 'formal' or null while pending")
    bool_fields = (
        "case_specs_authored", "support_spans_authored",
        "decision_rules_authored", "oracle_materials_authored",
    )
    for field in bool_fields:
        if type(review.get(field)) is not bool:
            errors.append(f"{path}.{field}: expected a boolean")
    if complete:
        if review.get("dataset_role") != "formal":
            errors.append(f"{path}.dataset_role: complete review requires 'formal'")
        if len(task_ids) != FORMAL_TASK_COUNT:
            errors.append(f"{path}: exactly Formal-86 task IDs are required")
        if protocol_task_ids and task_ids != protocol_task_ids:
            errors.append(
                f"{path}: task_ids must exactly match the protocol Formal-86 in order"
            )
        if any(review.get(field) is not True for field in bool_fields):
            errors.append(f"{path}: case, spans, decision rules, and oracles must all be hand-authored")
    _validate_common_review(review, path=path, base_dir=base_dir, errors=errors, complete=complete)
    return complete, task_ids


def _validate_query_review(
    value: object, base_dir: Path, errors: list[str], task_ids: list[str]
) -> bool:
    path = "manual_reviews.query_naturalness_and_leakage"
    review = _object(value, path, errors)
    expected = {
        "status", "task_ids", "naturalness_reviewed",
        "no_gold_or_scorer_leakage_reviewed", "decision_priority_reviewed",
        "constraint_diff_empty", "evidence", "reviewers", "notes",
    }
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    reviewed_ids = _nonempty_strings(review.get("task_ids"), f"{path}.task_ids", errors)
    bool_fields = (
        "naturalness_reviewed", "no_gold_or_scorer_leakage_reviewed",
        "decision_priority_reviewed", "constraint_diff_empty",
    )
    for field in bool_fields:
        if type(review.get(field)) is not bool:
            errors.append(f"{path}.{field}: expected a boolean")
    if complete:
        if reviewed_ids != task_ids or len(reviewed_ids) != FORMAL_TASK_COUNT:
            errors.append(
                f"{path}: task_ids must exactly match the authored Formal-86 in order"
            )
        if any(review.get(field) is not True for field in bool_fields):
            errors.append(f"{path}: every naturalness, priority, alignment, and leakage check must pass")
    _validate_common_review(review, path=path, base_dir=base_dir, errors=errors, complete=complete)
    return complete


def _validate_human_oracle_review(
    value: object, base_dir: Path, errors: list[str], task_ids: list[str]
) -> bool:
    path = "manual_reviews.human_oracle_runs"
    review = _object(value, path, errors)
    expected = {"status", "task_ids", "runs", "evidence", "reviewers", "notes"}
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    declared_ids = _nonempty_strings(review.get("task_ids"), f"{path}.task_ids", errors)
    runs = review.get("runs")
    run_ids: list[str] = []
    if not isinstance(runs, list):
        errors.append(f"{path}.runs: expected a list")
    else:
        run_keys = {"task_id", "elapsed_minutes", "access_path", "completed_at", "reviewer_note"}
        for index, item in enumerate(runs):
            item_path = f"{path}.runs[{index}]"
            run = _object(item, item_path, errors)
            if run is None:
                continue
            _exact_keys(run, run_keys, item_path, errors)
            task_id = run.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                errors.append(f"{item_path}.task_id: required")
            else:
                run_ids.append(task_id)
            minutes = run.get("elapsed_minutes")
            if (
                isinstance(minutes, bool)
                or not isinstance(minutes, (int, float))
                or not math.isfinite(float(minutes))
                or minutes <= 0
            ):
                errors.append(f"{item_path}.elapsed_minutes: expected a positive number")
            access_path = run.get("access_path")
            if not isinstance(access_path, list) or not access_path or any(
                not isinstance(step, str) or not step.strip() for step in access_path
            ):
                errors.append(f"{item_path}.access_path: record a non-empty access path")
            completed_at = run.get("completed_at")
            if not isinstance(completed_at, str) or not _REVIEWED_AT_RE.fullmatch(completed_at):
                errors.append(f"{item_path}.completed_at: use YYYY-MM-DD or ISO datetime")
            if not isinstance(run.get("reviewer_note"), str) or not run.get("reviewer_note", "").strip():
                errors.append(f"{item_path}.reviewer_note: required")
    if len(run_ids) != len(set(run_ids)):
        errors.append(f"{path}.runs: one human run per unique task is required")
    if complete:
        expected_ids = set(task_ids)
        if (
            len(declared_ids) != FORMAL_TASK_COUNT
            or declared_ids != task_ids
        ):
            errors.append(f"{path}: task_ids must exactly match Formal-86 in order")
        if len(run_ids) != FORMAL_TASK_COUNT or set(run_ids) != expected_ids:
            errors.append(f"{path}: every Formal-86 task needs a real human run")
    _validate_common_review(review, path=path, base_dir=base_dir, errors=errors, complete=complete)
    return complete


def _validate_annotation_review(
    value: object,
    base_dir: Path,
    errors: list[str],
    calibration_task_ids: list[str],
) -> bool:
    path = "manual_reviews.double_step_annotation_and_adjudication"
    review = _object(value, path, errors)
    expected = {
        "status",
        "annotation_unit",
        "task_ids",
        "annotator_names",
        "adjudicator_name",
        "preregistered_threshold",
        "observed_agreement",
        "disagreement_count",
        "adjudicated_disagreement_count",
        "all_steps_double_annotated",
        "preregistration_evidence",
        "measurement_evidence",
        "adjudication_evidence",
        "reviewers",
        "notes",
    }
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    if review.get("annotation_unit") != "step_pass_fail":
        errors.append(f"{path}.annotation_unit must be 'step_pass_fail'")
    task_ids = _nonempty_strings(
        review.get("task_ids"), f"{path}.task_ids", errors
    )
    annotators = _nonempty_strings(
        review.get("annotator_names"), f"{path}.annotator_names", errors
    )
    adjudicator = review.get("adjudicator_name")
    if adjudicator is not None and (
        not isinstance(adjudicator, str) or not adjudicator.strip()
    ):
        errors.append(f"{path}.adjudicator_name: expected a non-empty name or null")
    threshold = review.get("preregistered_threshold")
    observed = review.get("observed_agreement")
    valid_numbers: dict[str, bool] = {}
    for name, number in (("preregistered_threshold", threshold), ("observed_agreement", observed)):
        valid = number is None or (
            not isinstance(number, bool)
            and isinstance(number, (int, float))
            and math.isfinite(float(number))
            and 0 <= number <= 1
        )
        valid_numbers[name] = valid
        if not valid:
            errors.append(f"{path}.{name}: expected a number in [0, 1] or null")
    disagreement_count = review.get("disagreement_count")
    adjudicated_count = review.get("adjudicated_disagreement_count")
    for field, value in (
        ("disagreement_count", disagreement_count),
        ("adjudicated_disagreement_count", adjudicated_count),
    ):
        if value is not None and (type(value) is not int or value < 0):
            errors.append(f"{path}.{field}: expected a non-negative integer or null")
    if type(review.get("all_steps_double_annotated")) is not bool:
        errors.append(f"{path}.all_steps_double_annotated: expected a boolean")

    evidence_refs: list[tuple[str, str]] = []
    for field in (
        "preregistration_evidence",
        "measurement_evidence",
        "adjudication_evidence",
    ):
        ref = review.get(field)
        if ref is not None:
            _validate_artifact_ref(ref, path=f"{path}.{field}", base_dir=base_dir, errors=errors, machine=False)
            identity = _artifact_ref_identity(ref)
            if identity is not None:
                evidence_refs.append(identity)
    reviewers = review.get("reviewers")
    if complete:
        if task_ids != calibration_task_ids or len(task_ids) != CALIBRATION_TASK_COUNT:
            errors.append(
                f"{path}: double annotation must cover exactly the 11 calibration tasks"
            )
        if len(annotators) != 2:
            errors.append(f"{path}: exactly two independent annotators are required")
        if (
            not isinstance(adjudicator, str)
            or not adjudicator.strip()
            or adjudicator.strip() in set(annotators)
        ):
            errors.append(
                f"{path}: an independent adjudicator distinct from both annotators is required"
            )
        if threshold is None or observed is None:
            errors.append(f"{path}: a human must fill both preregistered threshold and observed agreement")
        elif (
            valid_numbers["preregistered_threshold"]
            and valid_numbers["observed_agreement"]
            and observed < threshold
        ):
            errors.append(f"{path}: observed agreement is below the preregistered threshold")
        if disagreement_count is None or adjudicated_count is None:
            errors.append(f"{path}: disagreement and adjudication counts are required")
        elif disagreement_count != adjudicated_count:
            errors.append(f"{path}: every step disagreement must be adjudicated")
        if review.get("all_steps_double_annotated") is not True:
            errors.append(f"{path}: all calibration proof steps must be double annotated")
        if len(evidence_refs) != 3 or len(set(evidence_refs)) != 3:
            errors.append(
                f"{path}: preregistration, measurement, and adjudication need "
                "three distinct hashed artifacts"
            )
        reviewer_names = _validate_reviewers(
            reviewers,
            path=f"{path}.reviewers",
            errors=errors,
            required_count=3,
        )
        expected_reviewers = set(annotators)
        if isinstance(adjudicator, str):
            expected_reviewers.add(adjudicator.strip())
        if set(reviewer_names) != expected_reviewers:
            errors.append(f"{path}: both annotators and the adjudicator must sign")
    elif reviewers:
        _validate_reviewers(reviewers, path=f"{path}.reviewers", errors=errors, required_count=0)
    elif not isinstance(reviewers, list):
        errors.append(f"{path}.reviewers: expected a reviewer list")
    if review.get("notes") is not None and not isinstance(review.get("notes"), str):
        errors.append(f"{path}.notes: expected a string")
    return complete


def _validate_acquisition_path_review(
    value: object,
    base_dir: Path,
    errors: list[str],
    development_task_ids: list[str],
    machine_development_task_ids: list[str],
    machine_coverage: Mapping[str, Mapping[str, str]],
) -> bool:
    path = "manual_reviews.acquisition_path_coverage_audit"
    review = _object(value, path, errors)
    expected = {
        "status",
        "development_task_ids",
        "harnesses",
        "reviewers",
        "notes",
    }
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    declared_development_ids = _nonempty_strings(
        review.get("development_task_ids"),
        f"{path}.development_task_ids",
        errors,
    )
    harnesses = review.get("harnesses")
    seen: list[str] = []
    audit_refs: list[tuple[str, str]] = []
    if not isinstance(harnesses, list):
        errors.append(f"{path}.harnesses: expected a list")
    else:
        entry_keys = {
            "harness_id",
            "acquisition_path_ids",
            "development_case_ids",
            "all_declared_paths_covered",
            "uncovered_paths_disabled_or_separate_protocol",
            "evidence",
        }
        for index, item in enumerate(harnesses):
            item_path = f"{path}.harnesses[{index}]"
            entry = _object(item, item_path, errors)
            if entry is None:
                continue
            _exact_keys(entry, entry_keys, item_path, errors)
            harness_id = entry.get("harness_id")
            if not isinstance(harness_id, str) or not harness_id:
                errors.append(f"{item_path}.harness_id: required")
            else:
                seen.append(harness_id)
            path_ids = _nonempty_strings(
                entry.get("acquisition_path_ids"),
                f"{item_path}.acquisition_path_ids",
                errors,
            )
            case_ids = _nonempty_strings(
                entry.get("development_case_ids"),
                f"{item_path}.development_case_ids",
                errors,
            )
            for field in (
                "all_declared_paths_covered",
                "uncovered_paths_disabled_or_separate_protocol",
            ):
                if type(entry.get(field)) is not bool:
                    errors.append(f"{item_path}.{field}: expected a boolean")
                elif complete and entry.get(field) is not True:
                    errors.append(f"{item_path}.{field}: must pass")
            evidence = entry.get("evidence")
            _validate_manual_evidence_list(
                evidence,
                path=f"{item_path}.evidence",
                base_dir=base_dir,
                errors=errors,
                required=complete,
            )
            if isinstance(evidence, list):
                for ref in evidence:
                    identity = _artifact_ref_identity(ref)
                    if identity is not None:
                        audit_refs.append(identity)
            if complete:
                machine_paths = dict(machine_coverage.get(str(harness_id), {}))
                if set(path_ids) != set(machine_paths):
                    errors.append(
                        f"{item_path}.acquisition_path_ids: must exactly match "
                        "the machine coverage matrix"
                    )
                if set(case_ids) != set(machine_paths.values()):
                    errors.append(
                        f"{item_path}.development_case_ids: must exactly match "
                        "the machine conformance cases"
                    )
                if not set(case_ids) <= set(development_task_ids):
                    errors.append(
                        f"{item_path}.development_case_ids: must belong to Dev-14"
                    )
    if len(seen) != len(set(seen)):
        errors.append(f"{path}.harnesses: duplicate harness_id")
    if complete and seen != list(MAINTAINED_HARNESSES):
        errors.append(
            f"{path}: exactly the 12 maintained harnesses are required in "
            "canonical order"
        )
    if complete and declared_development_ids != development_task_ids:
        errors.append(f"{path}.development_task_ids: must exactly equal Dev-14")
    if (
        complete
        and machine_development_task_ids
        and declared_development_ids != machine_development_task_ids
    ):
        errors.append(
            f"{path}.development_task_ids: manual and machine Dev-14 sets differ"
        )
    if complete and (
        len(audit_refs) < len(MAINTAINED_HARNESSES)
        or len(set(audit_refs)) != len(audit_refs)
    ):
        errors.append(
            f"{path}: every harness needs distinct hashed path-review evidence"
        )
    reviewers = review.get("reviewers")
    if complete or reviewers:
        _validate_reviewers(reviewers, path=f"{path}.reviewers", errors=errors, required_count=1 if complete else 0)
    elif not isinstance(reviewers, list):
        errors.append(f"{path}.reviewers: expected a reviewer list")
    if review.get("notes") is not None and not isinstance(review.get("notes"), str):
        errors.append(f"{path}.notes: expected a string")
    return complete


def _validate_validation_review(
    value: object, base_dir: Path, errors: list[str]
) -> bool:
    path = "manual_reviews.formal_86_statistics_and_fairness"
    review = _object(value, path, errors)
    evidence_fields = (
        "validation_panel_evidence", "cluster_bootstrap_ci_evidence",
        "replicate_stability_evidence", "harness_fairness_evidence",
    )
    expected = {
        "status", "formal_task_count", "development_tasks_excluded",
        "cluster_bootstrap_ci_passed",
        "replicate_stability_passed", "harness_fairness_passed", *evidence_fields,
        "reviewers", "notes",
    }
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    count = review.get("formal_task_count")
    if count is not None and (type(count) is not int or count < 0):
        errors.append(f"{path}.formal_task_count: expected a non-negative integer or null")
    bool_fields = (
        "development_tasks_excluded",
        "cluster_bootstrap_ci_passed",
        "replicate_stability_passed",
        "harness_fairness_passed",
    )
    for field in bool_fields:
        if type(review.get(field)) is not bool:
            errors.append(f"{path}.{field}: expected a boolean")
    evidence_refs: list[tuple[str, str]] = []
    for field in evidence_fields:
        ref = review.get(field)
        if ref is not None:
            _validate_artifact_ref(ref, path=f"{path}.{field}", base_dir=base_dir, errors=errors, machine=False)
            identity = _artifact_ref_identity(ref)
            if identity is not None:
                evidence_refs.append(identity)
        elif complete:
            errors.append(f"{path}.{field}: hashed validation evidence is required")
    if complete:
        if count != FORMAL_TASK_COUNT:
            errors.append(f"{path}: statistics must cover exactly Formal-86")
        if any(review.get(field) is not True for field in bool_fields):
            errors.append(
                f"{path}: Dev-14 exclusion, CI, replicate stability, and "
                "harness fairness must all pass"
            )
        if len(evidence_refs) != len(evidence_fields) or len(set(evidence_refs)) != len(evidence_refs):
            errors.append(f"{path}: four distinct validation artifacts are required")
    reviewers = review.get("reviewers")
    if complete or reviewers:
        _validate_reviewers(reviewers, path=f"{path}.reviewers", errors=errors, required_count=1 if complete else 0)
    elif not isinstance(reviewers, list):
        errors.append(f"{path}.reviewers: expected a reviewer list")
    if review.get("notes") is not None and not isinstance(review.get("notes"), str):
        errors.append(f"{path}.notes: expected a string")
    return complete


def _validate_publication_review(
    value: object, base_dir: Path, errors: list[str]
) -> bool:
    path = "manual_reviews.publication_method_consistency"
    review = _object(value, path, errors)
    expected = {"status", "surfaces", "reviewers", "notes"}
    if review is None:
        return False
    _exact_keys(review, expected, path, errors)
    complete = _manual_status(review, path, errors)
    surfaces = _object(review.get("surfaces"), f"{path}.surfaces", errors)
    method_hashes: list[str] = []
    surface_artifacts: list[tuple[str, str]] = []
    if surfaces is not None:
        if complete:
            _exact_keys(surfaces, set(PUBLICATION_SURFACES), f"{path}.surfaces", errors)
        elif set(surfaces) - set(PUBLICATION_SURFACES):
            errors.append(f"{path}.surfaces: unknown fields {sorted(set(surfaces) - set(PUBLICATION_SURFACES))}")
        surface_keys = {"artifact", "method_text_sha256"}
        for name, value in surfaces.items():
            item_path = f"{path}.surfaces.{name}"
            item = _object(value, item_path, errors)
            if item is None:
                continue
            _exact_keys(item, surface_keys, item_path, errors)
            _validate_artifact_ref(item.get("artifact"), path=f"{item_path}.artifact", base_dir=base_dir, errors=errors, machine=False)
            identity = _artifact_ref_identity(item.get("artifact"))
            if identity is not None:
                surface_artifacts.append(identity)
            method_hash = item.get("method_text_sha256")
            if not isinstance(method_hash, str) or not _SHA256_RE.fullmatch(method_hash):
                errors.append(f"{item_path}.method_text_sha256: expected lowercase SHA-256")
            else:
                method_hashes.append(method_hash)
    if complete and (len(method_hashes) != len(PUBLICATION_SURFACES) or len(set(method_hashes)) != 1):
        errors.append(f"{path}: paper, website, datasheet, scorer, and board JSON must share one method-text hash")
    if complete and (
        len(surface_artifacts) != len(PUBLICATION_SURFACES)
        or len(set(surface_artifacts)) != len(surface_artifacts)
    ):
        errors.append(f"{path}: every publication surface needs a distinct artifact")
    reviewers = review.get("reviewers")
    if complete or reviewers:
        _validate_reviewers(reviewers, path=f"{path}.reviewers", errors=errors, required_count=1 if complete else 0)
    elif not isinstance(reviewers, list):
        errors.append(f"{path}.reviewers: expected a reviewer list")
    if review.get("notes") is not None and not isinstance(review.get("notes"), str):
        errors.append(f"{path}.notes: expected a string")
    return complete


def _validate_manual_reviews(
    value: object,
    base_dir: Path,
    errors: list[str],
    *,
    protocol_task_ids: list[str],
    machine_development_task_ids: list[str],
    machine_coverage: Mapping[str, Mapping[str, str]],
) -> tuple[list[str], list[str], list[str]]:
    manual = _object(value, "manual_reviews", errors)
    if manual is None:
        return list(MANUAL_REVIEW_KEYS), [], []
    _exact_keys(manual, set(MANUAL_REVIEW_KEYS), "manual_reviews", errors)
    complete: dict[str, bool] = {}
    (
        complete[MANUAL_REVIEW_KEYS[0]],
        development_ids,
        calibration_ids,
    ) = _validate_development_review(
        manual.get(MANUAL_REVIEW_KEYS[0]), base_dir, errors
    )
    complete[MANUAL_REVIEW_KEYS[1]], task_ids = _validate_formal_case_review(
        manual.get(MANUAL_REVIEW_KEYS[1]),
        base_dir,
        errors,
        protocol_task_ids,
    )
    complete[MANUAL_REVIEW_KEYS[2]] = _validate_query_review(manual.get(MANUAL_REVIEW_KEYS[2]), base_dir, errors, task_ids)
    complete[MANUAL_REVIEW_KEYS[3]] = _validate_human_oracle_review(manual.get(MANUAL_REVIEW_KEYS[3]), base_dir, errors, task_ids)
    complete[MANUAL_REVIEW_KEYS[4]] = _validate_annotation_review(
        manual.get(MANUAL_REVIEW_KEYS[4]),
        base_dir,
        errors,
        calibration_ids,
    )
    complete[MANUAL_REVIEW_KEYS[5]] = _validate_acquisition_path_review(
        manual.get(MANUAL_REVIEW_KEYS[5]),
        base_dir,
        errors,
        development_ids,
        machine_development_task_ids,
        machine_coverage,
    )
    complete[MANUAL_REVIEW_KEYS[6]] = _validate_validation_review(manual.get(MANUAL_REVIEW_KEYS[6]), base_dir, errors)
    complete[MANUAL_REVIEW_KEYS[7]] = _validate_publication_review(manual.get(MANUAL_REVIEW_KEYS[7]), base_dir, errors)
    return (
        sorted(key for key in MANUAL_REVIEW_KEYS if not complete.get(key, False)),
        development_ids,
        task_ids,
    )


def _check_release_readiness_impl(
    document: Mapping[str, Any], *, base_dir: str | Path = "."
) -> dict[str, Any]:
    """Validate and classify a readiness document without auto-attesting work.

    ``base_dir`` is used only to resolve relative artifact paths.  The returned
    object contains no timestamps or absolute paths and is deterministic for a
    fixed document and artifact set.
    """

    errors: list[str] = []
    root = _object(document, "readiness", errors)
    if root is None:
        root = {}
    _exact_keys(root, _TOP_LEVEL_KEYS, "readiness", errors)
    if root.get("schema") != RELEASE_READINESS_SCHEMA:
        errors.append(
            f"readiness.schema: expected {RELEASE_READINESS_SCHEMA!r}"
        )
    artifact_root = Path(base_dir)
    (
        machine_pending,
        verified,
        protocol_task_ids,
        _,
        machine_development_task_ids,
        machine_coverage,
    ) = _validate_machine_evidence(
        root.get("machine_evidence"), artifact_root, errors
    )
    manual_pending, development_task_ids, authored_task_ids = _validate_manual_reviews(
        root.get("manual_reviews"),
        artifact_root,
        errors,
        protocol_task_ids=protocol_task_ids,
        machine_development_task_ids=machine_development_task_ids,
        machine_coverage=machine_coverage,
    )
    if (
        development_task_ids
        and protocol_task_ids
        and set(development_task_ids) & set(protocol_task_ids)
    ):
        errors.append(
            "manual_reviews.development_14_partition_and_exclusion: Dev-14 "
            "must be disjoint from protocol Formal-86"
        )
    if authored_task_ids and protocol_task_ids and authored_task_ids != protocol_task_ids:
        errors.append(
            "manual_reviews.formal_86_case_and_oracle_authoring.task_ids: must "
            "exactly match protocol Formal-86 in order"
        )
    errors = sorted(set(errors))
    code_ready = not machine_pending and not errors
    manual_complete = not manual_pending and not errors
    eligible = code_ready and manual_complete
    if errors:
        status = "invalid"
    elif eligible:
        status = "formal_release_eligible"
    elif code_ready:
        status = "manual_pending"
    else:
        status = "code_pending"
    return {
        "schema": RELEASE_READINESS_SCHEMA,
        "status": status,
        "code_ready": code_ready,
        "manual_review_complete": manual_complete,
        "formal_release_eligible": eligible,
        "verified_machine_artifacts": verified,
        "machine_pending": machine_pending,
        "manual_pending": manual_pending,
        "errors": errors,
    }


def check_release_readiness(
    document: Mapping[str, Any], *, base_dir: str | Path = "."
) -> dict[str, Any]:
    """Fail closed for every JSON-representable malformed readiness record."""

    try:
        return _check_release_readiness_impl(document, base_dir=base_dir)
    except (AttributeError, ImportError, KeyError, TypeError, ValueError) as exc:
        return {
            "schema": RELEASE_READINESS_SCHEMA,
            "status": "invalid",
            "code_ready": False,
            "manual_review_complete": False,
            "formal_release_eligible": False,
            "verified_machine_artifacts": [],
            "machine_pending": list(MACHINE_EVIDENCE_KEYS),
            "manual_pending": list(MANUAL_REVIEW_KEYS),
            "errors": [
                "readiness: validation failed closed for malformed input: "
                f"{type(exc).__name__}: {exc}"
            ],
        }


def template_copy() -> dict[str, Any]:
    """Compatibility helper returning a detached template."""

    return deepcopy(new_release_readiness_template())


# Explicit additive names prevent callers from confusing this schema with the
# frozen Pilot-12 v1 gate in ``release_gate_v3``.
RELEASE_READINESS_V2_SCHEMA = RELEASE_READINESS_SCHEMA
ORACLE_RELEASE_BUNDLE_V2_SCHEMA = ORACLE_RELEASE_BUNDLE_SCHEMA
ACQUISITION_PATH_COVERAGE_V2_SCHEMA = ACQUISITION_PATH_COVERAGE_SCHEMA
MACHINE_EVIDENCE_V2_KEYS = MACHINE_EVIDENCE_KEYS
MANUAL_REVIEW_V2_KEYS = MANUAL_REVIEW_KEYS
check_release_readiness_v2 = check_release_readiness
new_release_readiness_v2_template = new_release_readiness_template
template_v2_copy = template_copy


__all__ = [
    "ACQUISITION_PATH_CONFORMANCE_SCHEMA",
    "ACQUISITION_PATH_COVERAGE_SCHEMA",
    "BYPASS_AUDIT_SCHEMA",
    "CALIBRATION_TASK_COUNT",
    "DEVELOPMENT_TASK_COUNT",
    "FEW_SHOT_TASK_COUNT",
    "FORMAL_TASK_COUNT",
    "ISOLATION_AUDIT_SCHEMA",
    "MAINTAINED_HARNESSES",
    "MACHINE_EVIDENCE_KEYS",
    "MANUAL_REVIEW_KEYS",
    "ORACLE_RELEASE_BUNDLE_SCHEMA",
    "ORACLE_RELEASE_BUNDLE_V2_SCHEMA",
    "PUBLICATION_SURFACES",
    "RELEASE_READINESS_SCHEMA",
    "RELEASE_READINESS_V2_SCHEMA",
    "ReleaseReadinessV3Error",
    "canonical_json_bytes",
    "check_release_readiness",
    "check_release_readiness_v2",
    "new_release_readiness_template",
    "new_release_readiness_v2_template",
    "template_copy",
    "template_v2_copy",
    "ACQUISITION_PATH_COVERAGE_V2_SCHEMA",
    "MACHINE_EVIDENCE_V2_KEYS",
    "MANUAL_REVIEW_V2_KEYS",
]
