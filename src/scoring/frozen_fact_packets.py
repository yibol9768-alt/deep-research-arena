"""Hash-verified Fact candidate packets for controlled judge comparisons.

Retrieval is part of the evaluation instrument, not part of the semantic
verdict.  A cross-judge experiment therefore freezes the same candidate spans
for every judge and changes only the model that labels those packets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.scoring.task_evaluation_contract import (
    canonical_json_sha256,
    file_sha256,
)


FACT_PACKET_BUNDLE_SCHEMA = "dra_frozen_fact_packet_bundle_v1"
MATERIAL_FACT_KINDS = {
    "external_atomic",
    "derived_arithmetic",
    "bounded_absence",
}


class FactPacketValidationError(ValueError):
    """Raised when candidate evidence packets are incomplete or have drifted."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FactPacketValidationError(f"{path} must contain a JSON object")
    return value


def _material_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in claims
        if row.get("claim_kind") in MATERIAL_FACT_KINDS
    ]


def _claim_identity(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": row.get("claim_id"),
            "normalized_claim": row.get("normalized_claim"),
            "claim_kind": row.get("claim_kind"),
            "attribution": row.get("attribution"),
            "qualifiers": row.get("qualifiers", {}),
        }
        for row in sorted(
            _material_claims(claims),
            key=lambda item: str(item.get("claim_id") or ""),
        )
    ]


def _validate_packets(
    packets: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> None:
    claim_map = {
        str(row.get("claim_id") or ""): row for row in _material_claims(claims)
    }
    packet_ids: list[str] = []
    for packet in packets:
        claim_id = str(packet.get("claim_id") or "")
        if claim_id not in claim_map:
            raise FactPacketValidationError(
                f"Fact packet references unknown material claim: {claim_id!r}"
            )
        packet_ids.append(claim_id)
        claim = claim_map[claim_id]
        if packet.get("claim") != claim.get("normalized_claim"):
            raise FactPacketValidationError(
                f"Fact packet claim text mismatch: {claim_id}"
            )
        if packet.get("claim_kind") != claim.get("claim_kind"):
            raise FactPacketValidationError(
                f"Fact packet claim kind mismatch: {claim_id}"
            )
        spans = packet.get("evidence_spans")
        if not isinstance(spans, list):
            raise FactPacketValidationError(
                f"Fact packet evidence_spans must be a list: {claim_id}"
            )
        span_ids: list[str] = []
        for span in spans:
            span_id = str(span.get("span_id") or "")
            if not span_id or not str(span.get("url") or ""):
                raise FactPacketValidationError(
                    f"Fact packet has an invalid evidence span: {claim_id}"
                )
            if not isinstance(span.get("text"), str):
                raise FactPacketValidationError(
                    f"Fact packet span has no text: {claim_id}/{span_id}"
                )
            span_ids.append(span_id)
        if len(span_ids) != len(set(span_ids)):
            raise FactPacketValidationError(
                f"Fact packet repeats span identifiers: {claim_id}"
            )
    expected_ids = set(claim_map)
    actual_ids = set(packet_ids)
    if len(packet_ids) != len(actual_ids):
        raise FactPacketValidationError("duplicate Fact packet claim identifiers")
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise FactPacketValidationError(
            f"Fact packet coverage mismatch; missing={missing}, extra={extra}"
        )


def _bundle_identity(
    *,
    claim_ledger_sha256: str,
    material_claims_sha256: str,
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": FACT_PACKET_BUNDLE_SCHEMA,
        "claim_ledger_sha256": claim_ledger_sha256,
        "material_claims_sha256": material_claims_sha256,
        "artifacts": artifacts,
    }


def seal_fact_packet_bundle(
    packet_dir: Path,
    claims: list[dict[str, Any]],
    *,
    claim_ledger_sha256: str,
) -> dict[str, Any]:
    """Seal one complete set of per-claim candidate evidence packets."""

    if not claim_ledger_sha256:
        raise FactPacketValidationError(
            "claim_ledger_sha256 is required to seal Fact packets"
        )
    packet_dir = Path(packet_dir)
    paths = sorted(
        path
        for path in packet_dir.glob("*.json")
        if path.name != "fact-packet-bundle-manifest.json"
    )
    packets = [_read_json(path) for path in paths]
    _validate_packets(packets, claims)
    artifacts = {
        path.name: {
            "file": path.name,
            "format": "json",
            "sha256": file_sha256(path),
            "row_count": 1,
            "claim_id": packet["claim_id"],
        }
        for path, packet in zip(paths, packets)
    }
    material_claims_sha256 = canonical_json_sha256(_claim_identity(claims))
    identity = _bundle_identity(
        claim_ledger_sha256=claim_ledger_sha256,
        material_claims_sha256=material_claims_sha256,
        artifacts=artifacts,
    )
    manifest = {
        **identity,
        "fact_packet_bundle_sha256": canonical_json_sha256(identity),
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": len(packets),
        "candidate_retrieval_is_score": False,
        "scoring_contract": (
            "candidate retrieval supplies evidence only; semantic verdicts "
            "and deterministic gates determine Fact credit"
        ),
    }
    (packet_dir / "fact-packet-bundle-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_frozen_fact_packets(
    packet_dir: Path,
    claims: list[dict[str, Any]],
    *,
    expected_claim_ledger_sha256: str,
) -> dict[str, Any]:
    """Load candidate packets only after verifying every file and claim."""

    packet_dir = Path(packet_dir)
    manifest_path = packet_dir / "fact-packet-bundle-manifest.json"
    if not manifest_path.is_file():
        raise FactPacketValidationError(
            "fact-packet-bundle-manifest.json is required for frozen reuse"
        )
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != FACT_PACKET_BUNDLE_SCHEMA:
        raise FactPacketValidationError(
            f"unsupported Fact packet schema: {manifest.get('schema')!r}"
        )
    if manifest.get("claim_ledger_sha256") != expected_claim_ledger_sha256:
        raise FactPacketValidationError(
            "Fact packets belong to a different Claim Ledger"
        )
    expected_claims_sha = canonical_json_sha256(_claim_identity(claims))
    if manifest.get("material_claims_sha256") != expected_claims_sha:
        raise FactPacketValidationError(
            "Fact packet material-claim identity mismatch"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise FactPacketValidationError("Fact packet bundle has no artifacts")
    packets: list[dict[str, Any]] = []
    for filename, entry in sorted(artifacts.items()):
        if filename != Path(filename).name or entry.get("file") != filename:
            raise FactPacketValidationError(
                f"invalid Fact packet artifact path: {filename!r}"
            )
        path = packet_dir / filename
        if not path.is_file():
            raise FactPacketValidationError(
                f"missing frozen Fact packet: {filename}"
            )
        if file_sha256(path) != entry.get("sha256"):
            raise FactPacketValidationError(
                f"Fact packet hash mismatch: {filename}"
            )
        packet = _read_json(path)
        if packet.get("claim_id") != entry.get("claim_id"):
            raise FactPacketValidationError(
                f"Fact packet manifest claim mismatch: {filename}"
            )
        packets.append(packet)
    identity = _bundle_identity(
        claim_ledger_sha256=expected_claim_ledger_sha256,
        material_claims_sha256=expected_claims_sha,
        artifacts=artifacts,
    )
    if canonical_json_sha256(identity) != manifest.get(
        "fact_packet_bundle_sha256"
    ):
        raise FactPacketValidationError("Fact packet bundle identity mismatch")
    if len(packets) != manifest.get("packet_count"):
        raise FactPacketValidationError("Fact packet bundle count mismatch")
    _validate_packets(packets, claims)
    return {
        "packets": sorted(packets, key=lambda row: str(row["claim_id"])),
        "manifest": manifest,
        "packet_dir": packet_dir,
        "manifest_path": manifest_path,
    }


__all__ = [
    "FACT_PACKET_BUNDLE_SCHEMA",
    "FactPacketValidationError",
    "load_frozen_fact_packets",
    "seal_fact_packet_bundle",
]
