"""Legacy Pilot-12 DRA v3 release-readiness gate.

This is the frozen v1 gate.  The Dev-14/Formal-86 gate is intentionally kept
in :mod:`src.eval.release_gate_v3_formal86`; the two schemas are non-comparable
and neither silently accepts the other's readiness document.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any


RELEASE_READINESS_SCHEMA = "dra_v3_release_readiness_v1"
ORACLE_RELEASE_BUNDLE_SCHEMA = "dra_v3_oracle_release_bundle_v1"
HARNESS_LEDGER_MATRIX_SCHEMA = "dra_v3_harness_ledger_matrix_v1"
MACHINE_EVIDENCE_KEYS = (
    "protocol_manifest",
    "oracle_validation",
    "harness_ledger_matrix",
)
MANUAL_REVIEW_KEYS = (
    "candidate_corpus_and_pilot_selection",
    "case_and_oracle_authoring",
    "query_naturalness_and_leakage",
    "human_oracle_runs",
    "double_slot_annotation",
    "maintained_harness_audit",
    "validation_30_and_fairness",
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
_PROOF_MOTIFS = {
    "constraint_filter",
    "mechanism_application",
    "claim_reconciliation",
    "comparative_tradeoff",
    "counterexample_revision",
}
_TOP_LEVEL_KEYS = {"schema", "machine_evidence", "manual_reviews"}
_MACHINE_RECORD_KEYS = {"status", "artifact"}
_ARTIFACT_KEYS = {"path", "sha256"}
_REVIEWER_KEYS = {"name", "reviewed_at", "signature"}
_ORACLE_BUNDLE_KEYS = {
    "schema",
    "status",
    "protocol_manifest_sha256",
    "task_ids",
    "validation_results",
    "bundle_sha256",
}
_ORACLE_ENTRY_KEYS = {"suite", "result"}
_MATRIX_KEYS = {
    "schema",
    "status",
    "protocol_manifest_sha256",
    "task_ids",
    "runs",
    "matrix_sha256",
}
_MATRIX_RUN_KEYS = {
    "harness_id",
    "task_id",
    "run_id",
    "ledger",
    "ledger_status",
    "isolation_audit",
    "isolation_status",
    "bypass_audit",
    "bypass_status",
}


class ReleaseReadinessV3Error(ValueError):
    """Raised when a legacy readiness document is structurally invalid."""


def canonical_json_bytes(value: object) -> bytes:
    """Return the canonical JSON bytes used by all v1 self-hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _machine_record() -> dict[str, Any]:
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
    """Return the unchanged v1 Pilot-12 TODO template."""

    return {
        "schema": RELEASE_READINESS_SCHEMA,
        "machine_evidence": {
            "protocol_manifest": _machine_record(),
            "oracle_validation": _machine_record(),
            "harness_ledger_matrix": _machine_record(),
        },
        "manual_reviews": {
            "candidate_corpus_and_pilot_selection": _review_stub(
                candidate_count_reviewed=None,
                eligible_candidate_ids=[],
                rejected_or_deferred_candidate_ids=[],
                pilot_cases=[],
            ),
            "case_and_oracle_authoring": _review_stub(
                task_ids=[],
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
            "double_slot_annotation": {
                "status": "pending",
                "annotator_names": [],
                "preregistered_threshold": None,
                "observed_agreement": None,
                "preregistration_evidence": None,
                "measurement_evidence": None,
                "reviewers": [],
                "notes": "",
            },
            "maintained_harness_audit": {
                "status": "pending",
                "harnesses": [],
                "reviewers": [],
                "notes": "",
            },
            "validation_30_and_fairness": {
                "status": "pending",
                "validation_task_count": None,
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


def _strings(value: object, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{path}: expected a list of non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{path}: values must be unique")
    return list(value)


def _resolve(path_text: str, base_dir: Path) -> Path:
    source = Path(path_text)
    return source if source.is_absolute() else base_dir / source


def _artifact(
    value: object,
    *,
    path: str,
    base_dir: Path,
    errors: list[str],
) -> tuple[Path, Mapping[str, Any], bytes] | None:
    ref = _object(value, path, errors)
    if ref is None:
        return None
    _exact_keys(ref, _ARTIFACT_KEYS, path, errors)
    path_text = ref.get("path")
    digest = ref.get("sha256")
    if not isinstance(path_text, str) or not path_text.strip():
        errors.append(f"{path}.path: expected a non-empty path")
        return None
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        errors.append(f"{path}.sha256: expected lowercase SHA-256")
        return None
    source = _resolve(path_text, base_dir)
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
    actual = hashlib.sha256(first).hexdigest()
    if actual != digest:
        errors.append(f"{path}.sha256: artifact hash mismatch ({actual} != {digest})")
        return None
    return source, ref, first


def _json(payload: bytes, path: str, errors: list[str]) -> Any | None:
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


def _self_hash(value: Mapping[str, Any], field: str) -> str:
    return hashlib.sha256(
        canonical_json_bytes({key: item for key, item in value.items() if key != field})
    ).hexdigest()


def _validate_protocol(
    raw: object,
    *,
    artifact_ref: Mapping[str, Any],
    errors: list[str],
) -> tuple[Mapping[str, Any] | None, list[str], set[str]]:
    path = "machine_evidence.protocol_manifest.artifact"
    manifest = _object(raw, path, errors)
    if manifest is None:
        return None, [], set()
    try:
        from src.eval.protocol_manifest_v3 import validate_v3_protocol_manifest
        from src.eval.protocol_v3 import validate_verified_slots_protocol

        validated = validate_v3_protocol_manifest(manifest)
        validate_verified_slots_protocol(validated["protocols"], formal=True)
    except (ImportError, TypeError, ValueError) as exc:
        errors.append(f"{path}: invalid protocol manifest: {exc}")
        return None, [], {str(artifact_ref.get("sha256") or "")}
    task_ids = _strings(validated.get("task_ids"), f"{path}.task_ids", errors)
    if len(task_ids) != 12:
        errors.append(f"{path}.task_ids: Pilot-12 requires exactly 12 tasks")
    contracts = validated.get("task_contracts")
    motifs = Counter(
        contract.get("motif")
        for contract in contracts.values()
        if isinstance(contracts, Mapping) and isinstance(contract, Mapping)
    ) if isinstance(contracts, Mapping) else Counter()
    if set(motifs) != _PROOF_MOTIFS or any(
        motifs[motif] < 2 or motifs[motif] > 3 for motif in _PROOF_MOTIFS
    ):
        errors.append(
            f"{path}.task_contracts: every proof motif must occur 2-3 times in Pilot-12"
        )
    file_hashes = {
        str(artifact_ref.get("sha256") or ""),
        str(validated.get("manifest_sha256") or ""),
    }
    return validated, task_ids, file_hashes


def _replay_oracle_suite(
    raw: object,
    *,
    source: Path,
    suite_sha256: str,
    path: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    if not isinstance(raw, Mapping):
        errors.append(f"{path}: oracle suite must be a JSON object")
        return None
    try:
        from src.eval.oracle_validation_v3 import (
            validate_oracle_suite,
        )

        return validate_oracle_suite(
            raw,
            base_dir=source.parent,
            suite_sha256=suite_sha256,
        )
    except (ImportError, OSError, TypeError, ValueError) as exc:
        errors.append(f"{path}: formal suite replay failed: {exc}")
        return None


def _validate_oracle_bundle(
    raw: object,
    *,
    source: Path,
    protocol: Mapping[str, Any] | None,
    protocol_task_ids: list[str],
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
    expected_manifest_hash = protocol.get("manifest_sha256") if protocol else None
    if bundle.get("protocol_manifest_sha256") != expected_manifest_hash:
        errors.append(f"{path}: protocol manifest self-hash mismatch")
    task_ids = _strings(bundle.get("task_ids"), f"{path}.task_ids", errors)
    if task_ids != protocol_task_ids or len(task_ids) != 12:
        errors.append(f"{path}.task_ids: must exactly equal protocol Pilot-12")
    digest = bundle.get("bundle_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        errors.append(f"{path}.bundle_sha256: expected lowercase SHA-256")
    elif digest != _self_hash(bundle, "bundle_sha256"):
        errors.append(f"{path}.bundle_sha256: bundle self-hash mismatch")
    entries = bundle.get("validation_results")
    result_task_ids: list[str] = []
    suite_paths: list[str] = []
    result_paths: list[str] = []
    if not isinstance(entries, list):
        errors.append(f"{path}.validation_results: expected an array")
    elif protocol is not None:
        from src.eval.release_gate_v3_formal86 import _validate_formal_oracle_result

        for index, value in enumerate(entries):
            entry_path = f"{path}.validation_results[{index}]"
            entry = _object(value, entry_path, errors)
            if entry is None:
                continue
            _exact_keys(entry, _ORACLE_ENTRY_KEYS, entry_path, errors)
            for field, seen in (("suite", suite_paths), ("result", result_paths)):
                ref = entry.get(field)
                if isinstance(ref, Mapping) and isinstance(ref.get("path"), str):
                    seen.append(str(ref["path"]))
            suite_checked = _artifact(
                entry.get("suite"), path=f"{entry_path}.suite", base_dir=source.parent,
                errors=errors,
            )
            result_checked = _artifact(
                entry.get("result"), path=f"{entry_path}.result", base_dir=source.parent,
                errors=errors,
            )
            if suite_checked is None or result_checked is None:
                continue
            suite_source, suite_ref, suite_bytes = suite_checked
            _, _, result_bytes = result_checked
            suite_raw = _json(suite_bytes, f"{entry_path}.suite", errors)
            result_raw = _json(result_bytes, f"{entry_path}.result", errors)
            replayed = _replay_oracle_suite(
                suite_raw,
                source=suite_source,
                suite_sha256=str(suite_ref.get("sha256") or ""),
                path=f"{entry_path}.suite",
                errors=errors,
            )
            if replayed is not None and result_raw is not None:
                try:
                    matches = canonical_json_bytes(replayed) == canonical_json_bytes(result_raw)
                except (TypeError, ValueError):
                    matches = False
                if not matches:
                    errors.append(
                        f"{entry_path}.result: bytes do not match deterministic suite replay"
                    )
            task_id = _validate_formal_oracle_result(
                result_raw,
                path=f"{entry_path}.result",
                protocol_manifest=protocol,
                protocol_file_hashes=protocol_file_hashes,
                errors=errors,
                score_semantics="verified_slots_v1",
            )
            if task_id:
                result_task_ids.append(task_id)
    if len(suite_paths) != len(set(suite_paths)):
        errors.append(f"{path}.validation_results: suite artifact paths must be unique")
    if len(result_paths) != len(set(result_paths)):
        errors.append(f"{path}.validation_results: result artifact paths must be unique")
    if result_task_ids != task_ids:
        errors.append(
            f"{path}.validation_results: must replay every Pilot-12 task once in protocol order"
        )
    return not any(error.startswith(path) for error in errors)


def _validate_run_audit(
    value: object,
    *,
    path: str,
    base_dir: Path,
    run_id: str,
    errors: list[str],
) -> bool:
    checked = _artifact(value, path=path, base_dir=base_dir, errors=errors)
    if checked is None:
        return False
    _, _, payload = checked
    audit = _object(_json(payload, path, errors), path, errors)
    if audit is None:
        return False
    _exact_keys(audit, {"run_id", "status"}, path, errors)
    if audit.get("run_id") != run_id:
        errors.append(f"{path}.run_id: must match matrix run_id")
    if audit.get("status") != "passed":
        errors.append(f"{path}.status: expected 'passed'")
    return not any(error.startswith(path) for error in errors)


def _validate_matrix(
    raw: object,
    *,
    source: Path,
    protocol: Mapping[str, Any] | None,
    protocol_task_ids: list[str],
    errors: list[str],
) -> bool:
    path = "machine_evidence.harness_ledger_matrix.artifact"
    matrix = _object(raw, path, errors)
    if matrix is None:
        return False
    _exact_keys(matrix, _MATRIX_KEYS, path, errors)
    if matrix.get("schema") != HARNESS_LEDGER_MATRIX_SCHEMA:
        errors.append(f"{path}.schema: expected {HARNESS_LEDGER_MATRIX_SCHEMA!r}")
    if matrix.get("status") != "passed":
        errors.append(f"{path}.status: expected 'passed'")
    expected_manifest_hash = protocol.get("manifest_sha256") if protocol else None
    if matrix.get("protocol_manifest_sha256") != expected_manifest_hash:
        errors.append(f"{path}: protocol manifest self-hash mismatch")
    task_ids = _strings(matrix.get("task_ids"), f"{path}.task_ids", errors)
    if task_ids != protocol_task_ids or len(task_ids) != 12:
        errors.append(f"{path}.task_ids: must exactly equal protocol Pilot-12")
    digest = matrix.get("matrix_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        errors.append(f"{path}.matrix_sha256: expected lowercase SHA-256")
    elif digest != _self_hash(matrix, "matrix_sha256"):
        errors.append(f"{path}.matrix_sha256: matrix self-hash mismatch")
    runs = matrix.get("runs")
    harness_ids: list[str] = []
    run_ids: list[str] = []
    run_task_ids: list[str] = []
    if not isinstance(runs, list):
        errors.append(f"{path}.runs: expected an array")
    else:
        from src.eval.observation_ledger import load_observation_ledger

        for index, value in enumerate(runs):
            run_path = f"{path}.runs[{index}]"
            run = _object(value, run_path, errors)
            if run is None:
                continue
            _exact_keys(run, _MATRIX_RUN_KEYS, run_path, errors)
            harness_id = run.get("harness_id")
            task_id = run.get("task_id")
            run_id = run.get("run_id")
            if isinstance(harness_id, str) and harness_id:
                harness_ids.append(harness_id)
            else:
                errors.append(f"{run_path}.harness_id: expected a non-empty string")
            if isinstance(task_id, str) and task_id:
                run_task_ids.append(task_id)
            else:
                errors.append(f"{run_path}.task_id: expected a non-empty string")
            if isinstance(run_id, str) and run_id:
                run_ids.append(run_id)
            else:
                errors.append(f"{run_path}.run_id: expected a non-empty string")
                run_id = ""
            if run.get("ledger_status") != "complete":
                errors.append(f"{run_path}.ledger_status: expected 'complete'")
            ledger_checked = _artifact(
                run.get("ledger"), path=f"{run_path}.ledger", base_dir=source.parent,
                errors=errors,
            )
            if ledger_checked is not None:
                ledger_source, _, _ = ledger_checked
                ledger = load_observation_ledger(
                    ledger_source, expected_run_id=run_id, allow_legacy=False
                )
                if not ledger.complete:
                    errors.append(f"{run_path}.ledger: capture must be complete")
                if not ledger.events:
                    errors.append(
                        f"{run_path}.ledger: requires at least one captured observation event"
                    )
            for field in ("isolation", "bypass"):
                status_field = f"{field}_status"
                artifact_field = f"{field}_audit"
                if run.get(status_field) != "passed":
                    errors.append(f"{run_path}.{status_field}: expected 'passed'")
                _validate_run_audit(
                    run.get(artifact_field),
                    path=f"{run_path}.{artifact_field}",
                    base_dir=source.parent,
                    run_id=run_id,
                    errors=errors,
                )
    if harness_ids != list(MAINTAINED_HARNESSES):
        errors.append(f"{path}.runs: must cover maintained harnesses in canonical order")
    if len(run_ids) != len(set(run_ids)):
        errors.append(f"{path}.runs: run_id values must be unique")
    if run_task_ids != task_ids:
        errors.append(f"{path}.runs: task_ids must replay protocol Pilot-12 in order")
    return not any(error.startswith(path) for error in errors)


def _validate_machine(
    raw: object, base_dir: Path, errors: list[str]
) -> tuple[list[str], list[str], list[str]]:
    machine = _object(raw, "machine_evidence", errors)
    if machine is None:
        return list(MACHINE_EVIDENCE_KEYS), [], []
    _exact_keys(machine, set(MACHINE_EVIDENCE_KEYS), "machine_evidence", errors)
    checked: dict[str, tuple[Path, Mapping[str, Any], bytes] | None] = {}
    pending: list[str] = []
    for key in MACHINE_EVIDENCE_KEYS:
        path = f"machine_evidence.{key}"
        record = _object(machine.get(key), path, errors)
        if record is None:
            pending.append(key)
            continue
        _exact_keys(record, _MACHINE_RECORD_KEYS, path, errors)
        status = record.get("status")
        if status in {"pending", "failed"}:
            pending.append(key)
            if record.get("artifact") is not None:
                _artifact(
                    record.get("artifact"),
                    path=f"{path}.artifact",
                    base_dir=base_dir,
                    errors=errors,
                )
            continue
        if status != "passed":
            errors.append(f"{path}.status: expected 'pending', 'passed', or 'failed'")
            pending.append(key)
            continue
        checked[key] = _artifact(
            record.get("artifact"), path=f"{path}.artifact", base_dir=base_dir,
            errors=errors,
        )
        if checked[key] is None:
            pending.append(key)
    protocol: Mapping[str, Any] | None = None
    task_ids: list[str] = []
    protocol_hashes: set[str] = set()
    protocol_checked = checked.get("protocol_manifest")
    if protocol_checked is not None:
        _, ref, payload = protocol_checked
        before = len(errors)
        protocol, task_ids, protocol_hashes = _validate_protocol(
            _json(payload, "machine_evidence.protocol_manifest.artifact", errors),
            artifact_ref=ref,
            errors=errors,
        )
        if protocol is None or len(errors) != before:
            pending.append("protocol_manifest")
    elif any(key in checked for key in ("oracle_validation", "harness_ledger_matrix")):
        errors.append("machine_evidence: dependent bundles require a valid protocol manifest")
    oracle_checked = checked.get("oracle_validation")
    if oracle_checked is not None:
        source, _, payload = oracle_checked
        valid = _validate_oracle_bundle(
            _json(payload, "machine_evidence.oracle_validation.artifact", errors),
            source=source,
            protocol=protocol,
            protocol_task_ids=task_ids,
            protocol_file_hashes=protocol_hashes,
            errors=errors,
        )
        if not valid:
            pending.append("oracle_validation")
    matrix_checked = checked.get("harness_ledger_matrix")
    if matrix_checked is not None:
        source, _, payload = matrix_checked
        valid = _validate_matrix(
            _json(payload, "machine_evidence.harness_ledger_matrix.artifact", errors),
            source=source,
            protocol=protocol,
            protocol_task_ids=task_ids,
            errors=errors,
        )
        if not valid:
            pending.append("harness_ledger_matrix")
    verified = sorted(
        key
        for key in MACHINE_EVIDENCE_KEYS
        if key in checked and key not in set(pending)
    )
    return sorted(set(pending)), verified, task_ids


def _reviewers(
    value: object, path: str, errors: list[str]
) -> tuple[bool, list[str]]:
    if not isinstance(value, list) or not value:
        errors.append(f"{path}: complete review requires at least one signed reviewer")
        return False, []
    names: list[str] = []
    valid = True
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        reviewer = _object(raw, item_path, errors)
        if reviewer is None:
            valid = False
            continue
        _exact_keys(reviewer, _REVIEWER_KEYS, item_path, errors)
        name = reviewer.get("name")
        reviewed_at = reviewer.get("reviewed_at")
        signature = reviewer.get("signature")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{item_path}.name: required")
            valid = False
        else:
            names.append(name)
        if not isinstance(reviewed_at, str) or not _REVIEWED_AT_RE.fullmatch(reviewed_at):
            errors.append(f"{item_path}.reviewed_at: expected an ISO date or timestamp")
            valid = False
        if not isinstance(signature, str) or not signature.strip():
            errors.append(f"{item_path}.signature: required")
            valid = False
    if len(names) != len(set(names)):
        errors.append(f"{path}: reviewer names must be unique")
        valid = False
    return valid, names


def _artifact_list(
    value: object, path: str, base_dir: Path, errors: list[str]
) -> tuple[bool, list[tuple[str, str]]]:
    if not isinstance(value, list) or not value:
        errors.append(f"{path}: complete review requires a hashed review artifact")
        return False, []
    identities: list[tuple[str, str]] = []
    valid = True
    for index, ref in enumerate(value):
        checked = _artifact(ref, path=f"{path}[{index}]", base_dir=base_dir, errors=errors)
        if checked is None:
            valid = False
        elif isinstance(ref, Mapping):
            identities.append((str(ref.get("path")), str(ref.get("sha256"))))
    return valid, identities


def _manual_header(
    value: object,
    *,
    path: str,
    expected: set[str],
    base_dir: Path,
    errors: list[str],
    evidence_field: str | None = "evidence",
) -> tuple[Mapping[str, Any] | None, bool, list[str]]:
    review = _object(value, path, errors)
    if review is None:
        return None, False, []
    _exact_keys(review, expected, path, errors)
    status = review.get("status")
    if status == "pending":
        return review, False, []
    if status != "complete":
        errors.append(f"{path}.status: expected 'pending' or 'complete'")
        return review, False, []
    reviewers_ok, reviewer_names = _reviewers(
        review.get("reviewers"), f"{path}.reviewers", errors
    )
    evidence_ok = True
    if evidence_field is not None:
        evidence_ok, _ = _artifact_list(
            review.get(evidence_field), f"{path}.{evidence_field}", base_dir, errors
        )
    return review, reviewers_ok and evidence_ok, reviewer_names


def _validate_manual(
    raw: object,
    *,
    base_dir: Path,
    protocol_task_ids: list[str],
    errors: list[str],
) -> list[str]:
    manual = _object(raw, "manual_reviews", errors)
    if manual is None:
        return list(MANUAL_REVIEW_KEYS)
    _exact_keys(manual, set(MANUAL_REVIEW_KEYS), "manual_reviews", errors)
    complete: dict[str, bool] = {}

    key = MANUAL_REVIEW_KEYS[0]
    path = f"manual_reviews.{key}"
    expected = {
        "status", "candidate_count_reviewed", "eligible_candidate_ids",
        "rejected_or_deferred_candidate_ids", "pilot_cases", "evidence",
        "reviewers", "notes",
    }
    review, shell_ok, _ = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir, errors=errors
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        if type(review.get("candidate_count_reviewed")) is not int or review.get("candidate_count_reviewed") != 20:
            errors.append(f"{path}.candidate_count_reviewed: expected exactly 20")
            valid = False
        eligible = _strings(review.get("eligible_candidate_ids"), f"{path}.eligible_candidate_ids", errors)
        rejected = _strings(review.get("rejected_or_deferred_candidate_ids"), f"{path}.rejected_or_deferred_candidate_ids", errors)
        if not 10 <= len(eligible) <= 15:
            errors.append(f"{path}.eligible_candidate_ids: expected 10-15 candidates")
            valid = False
        if set(eligible) & set(rejected) or len(eligible) + len(rejected) != 20:
            errors.append(f"{path}: candidate partition must be disjoint and cover all 20")
            valid = False
        pilot_cases = review.get("pilot_cases")
        case_candidate_ids: list[str] = []
        case_task_ids: list[str] = []
        if not isinstance(pilot_cases, list) or len(pilot_cases) != 12:
            errors.append(f"{path}.pilot_cases: expected exactly Pilot-12")
            valid = False
        else:
            for index, value in enumerate(pilot_cases):
                item_path = f"{path}.pilot_cases[{index}]"
                item = _object(value, item_path, errors)
                if item is None:
                    valid = False
                    continue
                _exact_keys(item, {"candidate_id", "task_id"}, item_path, errors)
                candidate_id = item.get("candidate_id")
                task_id = item.get("task_id")
                if isinstance(candidate_id, str) and candidate_id:
                    case_candidate_ids.append(candidate_id)
                else:
                    errors.append(f"{item_path}.candidate_id: required")
                    valid = False
                if isinstance(task_id, str) and task_id:
                    case_task_ids.append(task_id)
                else:
                    errors.append(f"{item_path}.task_id: required")
                    valid = False
        if case_candidate_ids != eligible or case_task_ids != protocol_task_ids:
            errors.append(f"{path}.pilot_cases: must exactly match protocol manifest task_ids")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"

    boolean_reviews = (
        (
            MANUAL_REVIEW_KEYS[1],
            ("case_specs_authored", "support_spans_authored", "decision_rules_authored", "oracle_materials_authored"),
        ),
        (
            MANUAL_REVIEW_KEYS[2],
            ("naturalness_reviewed", "no_gold_or_scorer_leakage_reviewed", "decision_priority_reviewed", "constraint_diff_empty"),
        ),
    )
    for key, boolean_fields in boolean_reviews:
        path = f"manual_reviews.{key}"
        expected = {"status", "task_ids", *boolean_fields, "evidence", "reviewers", "notes"}
        review, shell_ok, _ = _manual_header(
            manual.get(key), path=path, expected=expected, base_dir=base_dir, errors=errors
        )
        valid = shell_ok
        if review is not None and review.get("status") == "complete":
            task_ids = _strings(review.get("task_ids"), f"{path}.task_ids", errors)
            if task_ids != protocol_task_ids:
                errors.append(f"{path}.task_ids: must exactly match protocol Pilot-12")
                valid = False
            for field in boolean_fields:
                if review.get(field) is not True:
                    errors.append(f"{path}.{field}: complete review requires true")
                    valid = False
        complete[key] = valid and review is not None and review.get("status") == "complete"

    key = MANUAL_REVIEW_KEYS[3]
    path = f"manual_reviews.{key}"
    expected = {"status", "task_ids", "runs", "evidence", "reviewers", "notes"}
    review, shell_ok, _ = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir, errors=errors
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        task_ids = _strings(review.get("task_ids"), f"{path}.task_ids", errors)
        if task_ids != protocol_task_ids:
            errors.append(f"{path}.task_ids: must exactly match protocol Pilot-12")
            valid = False
        runs = review.get("runs")
        seen: list[str] = []
        if not isinstance(runs, list) or len(runs) != 12:
            errors.append(f"{path}.runs: one human run per Pilot-12 task is required")
            valid = False
        else:
            for index, value in enumerate(runs):
                item_path = f"{path}.runs[{index}]"
                item = _object(value, item_path, errors)
                if item is None:
                    valid = False
                    continue
                _exact_keys(
                    item,
                    {"task_id", "elapsed_minutes", "access_path", "completed_at", "reviewer_note"},
                    item_path,
                    errors,
                )
                task_id = item.get("task_id")
                if isinstance(task_id, str):
                    seen.append(task_id)
                minutes = item.get("elapsed_minutes")
                if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(float(minutes)) or minutes <= 0:
                    errors.append(f"{item_path}.elapsed_minutes: expected a positive finite number")
                    valid = False
                access = item.get("access_path")
                if not isinstance(access, list) or not access or any(not isinstance(part, str) or not part.strip() for part in access):
                    errors.append(f"{item_path}.access_path: expected a non-empty string list")
                    valid = False
                for field in ("completed_at", "reviewer_note"):
                    if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                        errors.append(f"{item_path}.{field}: required")
                        valid = False
        if seen != task_ids:
            errors.append(f"{path}.runs: must cover Pilot-12 exactly once in order")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"

    key = MANUAL_REVIEW_KEYS[4]
    path = f"manual_reviews.{key}"
    expected = {
        "status", "annotator_names", "preregistered_threshold",
        "observed_agreement", "preregistration_evidence", "measurement_evidence",
        "reviewers", "notes",
    }
    review, shell_ok, reviewer_names = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir,
        errors=errors, evidence_field=None,
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        annotators = _strings(review.get("annotator_names"), f"{path}.annotator_names", errors)
        if len(annotators) != 2 or reviewer_names != annotators:
            errors.append(f"{path}: exactly two signed annotators are required")
            valid = False
        numbers: dict[str, float] = {}
        for field in ("preregistered_threshold", "observed_agreement"):
            value = review.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
                errors.append(f"{path}.{field}: expected a finite number in [0, 1]")
                valid = False
            else:
                numbers[field] = float(value)
        if len(numbers) == 2 and numbers["observed_agreement"] < numbers["preregistered_threshold"]:
            errors.append(f"{path}.observed_agreement: must meet preregistered threshold")
            valid = False
        identities: list[tuple[str, str]] = []
        for field in ("preregistration_evidence", "measurement_evidence"):
            checked = _artifact(review.get(field), path=f"{path}.{field}", base_dir=base_dir, errors=errors)
            if checked is None:
                valid = False
            elif isinstance(review.get(field), Mapping):
                ref = review[field]
                identities.append((str(ref.get("path")), str(ref.get("sha256"))))
        if len(identities) == 2 and identities[0] == identities[1]:
            errors.append(f"{path}: preregistration and measurement artifacts must be distinct")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"

    key = MANUAL_REVIEW_KEYS[5]
    path = f"manual_reviews.{key}"
    expected = {"status", "harnesses", "reviewers", "notes"}
    review, shell_ok, _ = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir,
        errors=errors, evidence_field=None,
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        rows = review.get("harnesses")
        harness_ids: list[str] = []
        case_ids: list[str] = []
        if not isinstance(rows, list):
            errors.append(f"{path}.harnesses: expected an array")
            valid = False
        else:
            for index, value in enumerate(rows):
                item_path = f"{path}.harnesses[{index}]"
                item = _object(value, item_path, errors)
                if item is None:
                    valid = False
                    continue
                _exact_keys(
                    item,
                    {"harness_id", "formal_case_id", "observation_complete", "isolation_passed", "no_undisclosed_bypass", "ledger_evidence", "isolation_evidence", "bypass_evidence"},
                    item_path,
                    errors,
                )
                if isinstance(item.get("harness_id"), str):
                    harness_ids.append(str(item["harness_id"]))
                if isinstance(item.get("formal_case_id"), str):
                    case_ids.append(str(item["formal_case_id"]))
                for field in ("observation_complete", "isolation_passed", "no_undisclosed_bypass"):
                    if item.get(field) is not True:
                        errors.append(f"{item_path}.{field}: complete review requires true")
                        valid = False
                identities: list[tuple[str, str]] = []
                for field in ("ledger_evidence", "isolation_evidence", "bypass_evidence"):
                    checked = _artifact(item.get(field), path=f"{item_path}.{field}", base_dir=base_dir, errors=errors)
                    if checked is None:
                        valid = False
                    elif isinstance(item.get(field), Mapping):
                        ref = item[field]
                        identities.append((str(ref.get("path")), str(ref.get("sha256"))))
                if len(identities) != len(set(identities)):
                    errors.append(f"{item_path}: three audit artifacts must be distinct")
                    valid = False
        if harness_ids != list(MAINTAINED_HARNESSES) or case_ids != protocol_task_ids:
            errors.append(f"{path}.harnesses: must map every maintained harness to Pilot-12 in order")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"

    key = MANUAL_REVIEW_KEYS[6]
    path = f"manual_reviews.{key}"
    evidence_fields = (
        "validation_panel_evidence", "cluster_bootstrap_ci_evidence",
        "replicate_stability_evidence", "harness_fairness_evidence",
    )
    expected = {
        "status", "validation_task_count", "cluster_bootstrap_ci_passed",
        "replicate_stability_passed", "harness_fairness_passed", *evidence_fields,
        "reviewers", "notes",
    }
    review, shell_ok, _ = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir,
        errors=errors, evidence_field=None,
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        if type(review.get("validation_task_count")) is not int or review.get("validation_task_count") != 30:
            errors.append(f"{path}.validation_task_count: expected validation-30")
            valid = False
        for field in ("cluster_bootstrap_ci_passed", "replicate_stability_passed", "harness_fairness_passed"):
            if review.get(field) is not True:
                errors.append(f"{path}.{field}: complete review requires true")
                valid = False
        identities: list[tuple[str, str]] = []
        for field in evidence_fields:
            checked = _artifact(review.get(field), path=f"{path}.{field}", base_dir=base_dir, errors=errors)
            if checked is None:
                valid = False
            elif isinstance(review.get(field), Mapping):
                ref = review[field]
                identities.append((str(ref.get("path")), str(ref.get("sha256"))))
        if len(identities) != len(set(identities)):
            errors.append(f"{path}: statistics evidence artifacts must be distinct")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"

    key = MANUAL_REVIEW_KEYS[7]
    path = f"manual_reviews.{key}"
    expected = {"status", "surfaces", "reviewers", "notes"}
    review, shell_ok, _ = _manual_header(
        manual.get(key), path=path, expected=expected, base_dir=base_dir,
        errors=errors, evidence_field=None,
    )
    valid = shell_ok
    if review is not None and review.get("status") == "complete":
        surfaces = _object(review.get("surfaces"), f"{path}.surfaces", errors)
        hashes: list[str] = []
        identities: list[tuple[str, str]] = []
        if surfaces is None:
            valid = False
        else:
            _exact_keys(surfaces, set(PUBLICATION_SURFACES), f"{path}.surfaces", errors)
            for name in PUBLICATION_SURFACES:
                item_path = f"{path}.surfaces.{name}"
                item = _object(surfaces.get(name), item_path, errors)
                if item is None:
                    valid = False
                    continue
                _exact_keys(item, {"artifact", "method_text_sha256"}, item_path, errors)
                checked = _artifact(item.get("artifact"), path=f"{item_path}.artifact", base_dir=base_dir, errors=errors)
                if checked is None:
                    valid = False
                elif isinstance(item.get("artifact"), Mapping):
                    ref = item["artifact"]
                    identities.append((str(ref.get("path")), str(ref.get("sha256"))))
                digest = item.get("method_text_sha256")
                if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                    errors.append(f"{item_path}.method_text_sha256: expected lowercase SHA-256")
                    valid = False
                else:
                    hashes.append(digest)
        if len(set(hashes)) != 1 or len(hashes) != len(PUBLICATION_SURFACES):
            errors.append(f"{path}.surfaces: method text hashes must be identical")
            valid = False
        if len(identities) != len(set(identities)):
            errors.append(f"{path}.surfaces: publication artifacts must be distinct")
            valid = False
    complete[key] = valid and review is not None and review.get("status") == "complete"
    return sorted(key for key in MANUAL_REVIEW_KEYS if not complete.get(key, False))


def _check_release_readiness_impl(
    document: Mapping[str, Any], *, base_dir: str | Path = "."
) -> dict[str, Any]:
    errors: list[str] = []
    root = _object(document, "readiness", errors) or {}
    _exact_keys(root, _TOP_LEVEL_KEYS, "readiness", errors)
    if root.get("schema") != RELEASE_READINESS_SCHEMA:
        errors.append(f"readiness.schema: expected {RELEASE_READINESS_SCHEMA!r}")
    artifact_root = Path(base_dir)
    machine_pending, verified, protocol_task_ids = _validate_machine(
        root.get("machine_evidence"), artifact_root, errors
    )
    manual_pending = _validate_manual(
        root.get("manual_reviews"),
        base_dir=artifact_root,
        protocol_task_ids=protocol_task_ids,
        errors=errors,
    )
    errors = sorted(set(errors))
    code_ready = not machine_pending and not errors
    manual_complete = not manual_pending and not errors
    eligible = code_ready and manual_complete
    status = (
        "invalid" if errors else
        "formal_release_eligible" if eligible else
        "manual_pending" if code_ready else
        "code_pending"
    )
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
    """Validate only the frozen v1 schema and fail closed on malformed input."""

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
    return deepcopy(new_release_readiness_template())


# Additive v2 API.  Literal schema names plus lazy calls keep importing/running
# the frozen v1 gate independent from the new implementation.
RELEASE_READINESS_V2_SCHEMA = "dra_v3_release_readiness_v2"
ORACLE_RELEASE_BUNDLE_V2_SCHEMA = "dra_v3_oracle_release_bundle_v2"
ACQUISITION_PATH_COVERAGE_V2_SCHEMA = (
    "dra_v3_acquisition_path_coverage_matrix_v2"
)
ACQUISITION_PATH_COVERAGE_SCHEMA = ACQUISITION_PATH_COVERAGE_V2_SCHEMA
ACQUISITION_PATH_CONFORMANCE_SCHEMA = (
    "dra_v3_acquisition_path_conformance_result_v1"
)
ISOLATION_AUDIT_SCHEMA = "dra_v3_acquisition_path_isolation_audit_v1"
BYPASS_AUDIT_SCHEMA = "dra_v3_acquisition_path_bypass_audit_v1"
DEVELOPMENT_TASK_COUNT = 14
FEW_SHOT_TASK_COUNT = 3
CALIBRATION_TASK_COUNT = 11
FORMAL_TASK_COUNT = 86
MACHINE_EVIDENCE_V2_KEYS = (
    "protocol_manifest",
    "oracle_validation",
    "acquisition_path_coverage",
)
MANUAL_REVIEW_V2_KEYS = (
    "development_14_partition_and_exclusion",
    "formal_86_case_and_oracle_authoring",
    "query_naturalness_and_leakage",
    "human_oracle_runs",
    "double_step_annotation_and_adjudication",
    "acquisition_path_coverage_audit",
    "formal_86_statistics_and_fairness",
    "publication_method_consistency",
)


def check_release_readiness_v2(
    document: Mapping[str, Any], *, base_dir: str | Path = "."
) -> dict[str, Any]:
    from src.eval.release_gate_v3_formal86 import check_release_readiness_v2 as check

    return check(document, base_dir=base_dir)


def new_release_readiness_v2_template() -> dict[str, Any]:
    from src.eval.release_gate_v3_formal86 import (
        new_release_readiness_v2_template as build,
    )

    return build()


def template_v2_copy() -> dict[str, Any]:
    return deepcopy(new_release_readiness_v2_template())


__all__ = [
    "HARNESS_LEDGER_MATRIX_SCHEMA",
    "MAINTAINED_HARNESSES",
    "MACHINE_EVIDENCE_KEYS",
    "MANUAL_REVIEW_KEYS",
    "ORACLE_RELEASE_BUNDLE_SCHEMA",
    "PUBLICATION_SURFACES",
    "RELEASE_READINESS_SCHEMA",
    "ReleaseReadinessV3Error",
    "canonical_json_bytes",
    "check_release_readiness",
    "new_release_readiness_template",
    "template_copy",
    "ACQUISITION_PATH_CONFORMANCE_SCHEMA",
    "ACQUISITION_PATH_COVERAGE_V2_SCHEMA",
    "ACQUISITION_PATH_COVERAGE_SCHEMA",
    "BYPASS_AUDIT_SCHEMA",
    "CALIBRATION_TASK_COUNT",
    "DEVELOPMENT_TASK_COUNT",
    "FEW_SHOT_TASK_COUNT",
    "FORMAL_TASK_COUNT",
    "ISOLATION_AUDIT_SCHEMA",
    "MANUAL_REVIEW_V2_KEYS",
    "MACHINE_EVIDENCE_V2_KEYS",
    "ORACLE_RELEASE_BUNDLE_V2_SCHEMA",
    "RELEASE_READINESS_V2_SCHEMA",
    "check_release_readiness_v2",
    "new_release_readiness_v2_template",
    "template_v2_copy",
]
