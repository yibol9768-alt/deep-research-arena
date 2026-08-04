"""Seal and verify report-bound Claim Ledgers.

A judge comparison is meaningful only when both judges receive the same list
of claims.  The ledger therefore binds every accepted claim to the exact
report bytes and records hashes for all extraction-stage artifacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from src.scoring.task_evaluation_contract import (
    canonical_json_sha256,
    file_sha256,
)


CLAIM_LEDGER_SCHEMA = "dra_frozen_claim_ledger_v1"


class ClaimLedgerValidationError(ValueError):
    """Raised when a Claim Ledger does not match its report or seal."""


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ClaimLedgerValidationError(
                    f"{path}:{line_no} must contain a JSON object"
                )
            rows.append(value)
    return rows


def _validate_report_span(
    report: str,
    span: dict[str, Any],
    *,
    location: str,
) -> None:
    try:
        start = int(span["start"])
        end = int(span["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ClaimLedgerValidationError(
            f"{location} has invalid report offsets"
        ) from exc
    if start < 0 or end < start or end > len(report):
        raise ClaimLedgerValidationError(
            f"{location} report offsets are out of bounds"
        )
    raw_text = str(span.get("raw_text") or "")
    if report[start:end] != raw_text:
        raise ClaimLedgerValidationError(
            f"{location} raw_text does not match report bytes"
        )
    if span.get("sha256") != _text_sha256(raw_text):
        raise ClaimLedgerValidationError(
            f"{location} span hash does not match raw_text"
        )


def _validate_claims(report: str, claims: list[dict[str, Any]]) -> None:
    identifiers: list[str] = []
    for index, claim in enumerate(claims, 1):
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id:
            raise ClaimLedgerValidationError(
                f"claim row {index} has no claim_id"
            )
        identifiers.append(claim_id)
        if not str(claim.get("normalized_claim") or ""):
            raise ClaimLedgerValidationError(
                f"{claim_id} has no normalized_claim"
            )
        span = claim.get("report_span")
        if not isinstance(span, dict):
            raise ClaimLedgerValidationError(
                f"{claim_id} has no report_span"
            )
        _validate_report_span(
            report,
            span,
            location=f"{claim_id}.report_span",
        )
        occurrences = claim.get("occurrences") or []
        if not isinstance(occurrences, list):
            raise ClaimLedgerValidationError(
                f"{claim_id}.occurrences must be a list"
            )
        for occurrence_index, occurrence in enumerate(occurrences, 1):
            occurrence_span = occurrence.get("report_span")
            if not isinstance(occurrence_span, dict):
                raise ClaimLedgerValidationError(
                    f"{claim_id}.occurrences[{occurrence_index}] has no span"
                )
            _validate_report_span(
                report,
                occurrence_span,
                location=(
                    f"{claim_id}.occurrences[{occurrence_index}].report_span"
                ),
            )
    duplicates = sorted(
        claim_id
        for claim_id in set(identifiers)
        if identifiers.count(claim_id) > 1
    )
    if duplicates:
        raise ClaimLedgerValidationError(
            f"duplicate claim identifiers: {duplicates}"
        )


def _artifact_table(claims_dir: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(claims_dir.iterdir()):
        if (
            not path.is_file()
            or path.name == "claim-ledger-manifest.json"
            or path.suffix not in {".json", ".jsonl"}
        ):
            continue
        if path.suffix == ".jsonl":
            value = _read_jsonl(path)
            row_count = len(value)
            file_format = "jsonl"
        else:
            _read_json(path)
            row_count = 1
            file_format = "json"
        artifacts[path.name] = {
            "file": path.name,
            "format": file_format,
            "sha256": file_sha256(path),
            "row_count": row_count,
        }
    return artifacts


def _ledger_identity(
    *,
    report_sha256: str,
    frozen_claim_count: int,
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": CLAIM_LEDGER_SCHEMA,
        "report_sha256": report_sha256,
        "frozen_claim_count": frozen_claim_count,
        "artifacts": artifacts,
    }


def seal_claim_ledger(
    claims_dir: Path,
    report: str,
    *,
    intended_for_cross_judge_reuse: bool,
) -> dict[str, Any]:
    """Write a cryptographic seal over an existing extraction directory."""

    claims_dir = Path(claims_dir)
    summary_path = claims_dir / "claim_extraction_summary.json"
    claims_path = claims_dir / "report_claims.jsonl"
    if not summary_path.is_file() or not claims_path.is_file():
        raise ClaimLedgerValidationError(
            "claim ledger requires claim_extraction_summary.json and "
            "report_claims.jsonl"
        )
    summary = _read_json(summary_path)
    report_sha256 = _text_sha256(report)
    if summary.get("report_sha256") != report_sha256:
        raise ClaimLedgerValidationError(
            "claim extraction summary does not match report bytes"
        )
    claims = _read_jsonl(claims_path)
    _validate_claims(report, claims)
    if summary.get("frozen_claim_count") != len(claims):
        raise ClaimLedgerValidationError(
            "claim extraction count does not match report_claims.jsonl"
        )
    artifacts = _artifact_table(claims_dir)
    identity = _ledger_identity(
        report_sha256=report_sha256,
        frozen_claim_count=len(claims),
        artifacts=artifacts,
    )
    manifest = {
        **identity,
        "claim_ledger_sha256": canonical_json_sha256(identity),
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "intended_for_cross_judge_reuse": bool(
            intended_for_cross_judge_reuse
        ),
        "extractor_models": {
            "proposal": summary.get("proposal_model"),
            "nli": summary.get("nli_model"),
            "structural": summary.get("structural_model"),
            "dedup": summary.get("dedup_model"),
        },
        "manual_claim_decisions": summary.get("manual_claim_decisions", 0),
    }
    (claims_dir / "claim-ledger-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_frozen_claim_ledger(
    claims_dir: Path,
    report: str,
) -> dict[str, Any]:
    """Load a Claim Ledger after verifying its report binding and all hashes."""

    claims_dir = Path(claims_dir)
    manifest_path = claims_dir / "claim-ledger-manifest.json"
    if not manifest_path.is_file():
        raise ClaimLedgerValidationError(
            "claim-ledger-manifest.json is required for frozen reuse"
        )
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != CLAIM_LEDGER_SCHEMA:
        raise ClaimLedgerValidationError(
            f"unsupported claim ledger schema: {manifest.get('schema')!r}"
        )
    report_sha256 = _text_sha256(report)
    if report_sha256 != manifest.get("report_sha256"):
        raise ClaimLedgerValidationError(
            "frozen Claim Ledger belongs to a different report"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ClaimLedgerValidationError("Claim Ledger has no artifact table")
    for filename, entry in artifacts.items():
        if filename != Path(filename).name or entry.get("file") != filename:
            raise ClaimLedgerValidationError(
                f"invalid Claim Ledger artifact path: {filename!r}"
            )
        path = claims_dir / filename
        if not path.is_file():
            raise ClaimLedgerValidationError(
                f"missing Claim Ledger artifact: {filename}"
            )
        if file_sha256(path) != entry.get("sha256"):
            raise ClaimLedgerValidationError(
                f"Claim Ledger artifact hash mismatch: {filename}"
            )
        value = _read_jsonl(path) if entry.get("format") == "jsonl" else _read_json(path)
        count = len(value) if isinstance(value, list) else 1
        if count != entry.get("row_count"):
            raise ClaimLedgerValidationError(
                f"Claim Ledger artifact count mismatch: {filename}"
            )

    identity = _ledger_identity(
        report_sha256=report_sha256,
        frozen_claim_count=int(manifest.get("frozen_claim_count") or 0),
        artifacts=artifacts,
    )
    if canonical_json_sha256(identity) != manifest.get(
        "claim_ledger_sha256"
    ):
        raise ClaimLedgerValidationError("Claim Ledger identity hash mismatch")
    claims = _read_jsonl(claims_dir / "report_claims.jsonl")
    summary = _read_json(claims_dir / "claim_extraction_summary.json")
    if len(claims) != manifest.get("frozen_claim_count"):
        raise ClaimLedgerValidationError("Claim Ledger claim count mismatch")
    if summary.get("report_sha256") != report_sha256:
        raise ClaimLedgerValidationError(
            "claim extraction summary report hash mismatch"
        )
    _validate_claims(report, claims)
    return {
        "claims": claims,
        "summary": summary,
        "manifest": manifest,
        "claims_dir": claims_dir,
        "manifest_path": manifest_path,
    }


__all__ = [
    "CLAIM_LEDGER_SCHEMA",
    "ClaimLedgerValidationError",
    "load_frozen_claim_ledger",
    "seal_claim_ledger",
]
