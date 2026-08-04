#!/usr/bin/env python3
"""Verify hashes, exact spans, IDs, and score reproducibility for one run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.audited_judge import canonical_json_bytes
from src.scoring.four_axis_score import score_four_axis


def _jsonl(path: Path) -> list[dict]:
    # JSON strings may legally contain Unicode line/paragraph separators
    # (U+2028/U+2029). ``str.splitlines()`` treats those code points as record
    # delimiters and can therefore split one otherwise-valid JSONL record.
    # JSONL records are delimited by the literal LF byte only.
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    report = args.report.read_text(encoding="utf-8")
    errors: list[str] = []

    claims = _jsonl(run_dir / "claims" / "report_claims.jsonl")
    claim_ids: set[str] = set()
    for row in claims:
        claim_id = str(row.get("claim_id"))
        if claim_id in claim_ids:
            errors.append(f"duplicate claim_id {claim_id}")
        claim_ids.add(claim_id)
        span = row["report_span"]
        exact = report[span["start"] : span["end"]]
        if exact != span["raw_text"]:
            errors.append(f"non-exact report span {claim_id}")
        if _sha(span["raw_text"]) != span["sha256"]:
            errors.append(f"bad report span hash {claim_id}")
        for occurrence in row.get("occurrences", []):
            osp = occurrence["report_span"]
            if report[osp["start"] : osp["end"]] != osp["raw_text"]:
                errors.append(f"non-exact occurrence {claim_id}")

    fact_rows = _jsonl(run_dir / "fact_verdicts.jsonl")
    for row in fact_rows:
        if row["claim_id"] not in claim_ids:
            errors.append(f"Fact references unknown claim {row['claim_id']}")
        packet_path = run_dir / "fact_packets" / f"{row['claim_id']}.json"
        if not packet_path.exists():
            errors.append(f"missing Fact packet {row['claim_id']}")
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        allowed = {span["span_id"] for span in packet.get("evidence_spans", [])}
        used = set(row.get("support_span_ids", [])) | set(
            row.get("contradiction_span_ids", [])
        )
        if not used.issubset(allowed):
            errors.append(f"Fact references foreign span {row['claim_id']}")
        certificate = packet.get("absence_certificate")
        valid_certificate_ids = {
            str(certificate.get("certificate_id"))
        } if certificate else set()
        used_certificate_ids = set(row.get("absence_certificate_ids", []))
        if not used_certificate_ids.issubset(valid_certificate_ids):
            errors.append(
                f"Fact references foreign absence certificate {row['claim_id']}"
            )
        if row.get("verdict") == "true" and not (
            row.get("support_span_ids") or used_certificate_ids
        ):
            errors.append(
                f"true Fact lacks support span or absence certificate "
                f"{row['claim_id']}"
            )
        if row.get("verdict") == "false" and not row.get(
            "contradiction_span_ids"
        ):
            errors.append(f"false Fact lacks contradiction span {row['claim_id']}")
        if row.get("verdict") == "conflicted" and (
            not row.get("support_span_ids")
            or not row.get("contradiction_span_ids")
        ):
            errors.append(f"conflicted Fact lacks both span roles {row['claim_id']}")

    for filename in ("completeness_units.jsonl", "rubric_verdicts.jsonl"):
        for row in _jsonl(run_dir / filename):
            for quote in row.get("exact_quotes", []):
                if quote not in report:
                    errors.append(f"non-exact quote in {filename}: {quote[:40]}")
            if (
                filename == "rubric_verdicts.jsonl"
                and row.get("verdict") in {"fulfilled", "partially_fulfilled"}
                and not row.get("exact_quotes")
            ):
                errors.append(
                    f"positive Rubric verdict lacks exact quote: "
                    f"{row.get('rubric_id')}"
                )

    for row in _jsonl(run_dir / "citation_bindings.jsonl"):
        expected = all(
            [
                row.get("observed"),
                row.get("bound"),
                row.get("supports"),
                row.get("role_ok"),
                row.get("complete_scope_observed", True),
            ]
        )
        if bool(row.get("passed")) != expected:
            errors.append(f"binding gate mismatch {row.get('binding_id')}")

    for row in _jsonl(run_dir / "cited_urls.jsonl"):
        expected = all(
            [
                row.get("canonicalized"),
                row.get("in_registry"),
                row.get("snapshot_available"),
            ]
        )
        if bool(row.get("valid")) != expected:
            errors.append(f"URL gate mismatch {row.get('canonical_url')}")

    call_dirs = sorted(
        metadata_path.parent
        for metadata_path in (run_dir / "judge_calls").rglob("metadata.json")
    )
    for call_dir in call_dirs:
        request = json.loads((call_dir / "request.json").read_text(encoding="utf-8"))
        raw = (call_dir / "raw-response.txt").read_text(encoding="utf-8")
        metadata = json.loads(
            (call_dir / "metadata.json").read_text(encoding="utf-8")
        )
        request_hash = hashlib.sha256(canonical_json_bytes(request)).hexdigest()
        if metadata.get("request_sha256") != request_hash:
            errors.append(f"request hash mismatch {call_dir.name}")
        if metadata.get("raw_response_sha256") != _sha(raw):
            errors.append(f"response hash mismatch {call_dir.name}")
        if metadata.get("error"):
            errors.append(f"judge error {call_dir.name}: {metadata['error']}")

    packet = json.loads((run_dir / "score-packet.json").read_text(encoding="utf-8"))
    published = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
    recomputed = score_four_axis(packet)
    for key in ("quality", "truth", "legacy_weight_ablation"):
        if abs(float(recomputed[key]) - float(published[key])) > 1e-12:
            errors.append(f"score mismatch {key}")
    for axis in ("fact", "evidence", "completeness", "rubric", "provenance"):
        if abs(
            float(recomputed[axis]["score"]) - float(published[axis]["score"])
        ) > 1e-12:
            errors.append(f"axis mismatch {axis}")

    result = {
        "schema": "dra_four_axis_artifact_verification_v1",
        "run_dir": str(run_dir.resolve()),
        "claim_count": len(claims),
        "judge_call_count": len(call_dirs),
        "error_count": len(errors),
        "errors": errors,
        "passed": not errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
