#!/usr/bin/env python3
"""Project one matrix attempt into the strict inputs used by the Q1 scorer.

The projection never searches again and never infers evidence from the report.
It expands only response blobs already captured by the per-cell search door.
When a search result contains raw page content, that content is admitted as a
structured lookup only if its canonical Kiwix URL is in the frozen registry and
it contains at least one exact frozen evidence quote for that page.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from auto_score_biodiv_q1 import (
    PackageAssets,
    canonicalize_citation_urls,
    extract_citations,
    reconstruct_observations,
    sha256_file,
)


CONTENT_PREFIX = "http://localhost:8090/content/"
CANONICAL_PREFIX = "http://localhost:8090/"


class ProjectionError(RuntimeError):
    pass


def canonical_url(url: str) -> str:
    if url.startswith(CONTENT_PREFIX):
        return CANONICAL_PREFIX + url[len(CONTENT_PREFIX):]
    return url


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _snapshot_prefixes(assets: PackageAssets) -> list[str]:
    prefixes = set()
    for url in assets.registry_by_url:
        if "/" in url:
            prefixes.add(url.rsplit("/", 1)[0] + "/")
    return sorted(prefixes)


def build_citation_diagnostics(
    *,
    report_path: Path,
    assets: PackageAssets,
    ledger_rows: list[dict[str, Any]],
    ledger_path: Path,
) -> dict[str, Any]:
    """Classify report citations before any semantic judge call.

    The important distinction is registry scope: a citation can be inside the
    frozen Kiwix snapshot but outside the package's 30-page scoring registry.
    That is an asset-coverage diagnostic, not proof of fabrication.
    """
    report = report_path.read_text(encoding="utf-8")
    citations = canonicalize_citation_urls(extract_citations(report), assets)
    observations = reconstruct_observations(ledger_rows, ledger_path, assets)
    prefixes = _snapshot_prefixes(assets)
    grounding_tiers = {
        "full_page",
        "full_fetch",
        "fetched_content",
        "browser_observation",
        "structured_lookup",
    }
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for citation in citations:
        reported = str(citation.get("reported_url") or citation.get("url") or "")
        candidate = (
            CANONICAL_PREFIX + reported[len(CONTENT_PREFIX):]
            if reported.startswith(CONTENT_PREFIX)
            else reported
        )
        resolution = str(citation.get("resolution_status") or "")
        registry = assets.registry_by_url.get(candidate)
        observation = observations.get(candidate)
        matched_evidence_ids = list(observation.get("observed_evidence_ids") or []) if observation else []
        failure_gate = None
        if resolution in {
            "missing_definition",
            "missing_definition_url",
            "label_target_mismatch",
            "conflicting_definition",
        }:
            status = "missing_reference_definition"
            failure_gate = resolution
        elif registry:
            if observation and observation.get("observation_tier") in grounding_tiers:
                status = "in_registry_and_fetched" if matched_evidence_ids else "quote_not_found"
                failure_gate = None if matched_evidence_ids else "exact_quote_miss"
            else:
                status = "in_registry_but_snippet_only"
                failure_gate = "full_page_not_observed"
        elif any(candidate.startswith(prefix) for prefix in prefixes):
            status = "in_snapshot_but_out_of_package_registry"
            failure_gate = "registry_miss"
        else:
            status = "out_of_snapshot_or_fabricated"
            failure_gate = "registry_miss"
        rows.append(
            {
                "citation_ref": citation.get("citation_ref"),
                "raw_url": reported,
                "reported_url": reported,
                "canonical_url": candidate,
                "status": status,
                "failure_gate": failure_gate,
                "resolution_status": resolution,
                "registry_hit": bool(registry),
                "alias_rewritten": bool(registry) and candidate != reported,
                "observed": bool(observation),
                "observation_tier": observation.get("observation_tier") if observation else None,
                "page_content_sha256": registry.get("page_content_sha256") if registry else None,
                "matched_evidence_ids": matched_evidence_ids,
            }
        )
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": "1.0.0",
        "citation_count": len(rows),
        "status_counts": counts,
        "registry_url_count": len(assets.registry_by_url),
        "snapshot_prefixes": prefixes,
        "citations": rows,
    }


def write_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)


def safe_blob_path(evidence_dir: Path, reference: str) -> Path:
    path = (evidence_dir / reference).resolve()
    base = evidence_dir.resolve()
    if path != base and not str(path).startswith(str(base) + os.sep):
        raise ProjectionError("response blob escapes evidence directory")
    if not path.is_file():
        raise ProjectionError(f"response blob is missing: {reference}")
    return path


def read_jsonl_files(evidence_dir: Path) -> list[tuple[Path, int, dict[str, Any]]]:
    rows = []
    for path in sorted(evidence_dir.glob("*.jsonl")):
        if path.name == "source_health_receipts.jsonl":
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ProjectionError(f"non-object evidence row: {path}:{line_number}")
            rows.append((path, line_number, value))
    return rows


def project(
    *,
    attempt_dir: Path,
    package_dir: Path,
    output_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ProjectionError("output directory already exists")
    output_dir.mkdir(parents=True, mode=0o700)
    report_path = attempt_dir / "report.md"
    meta_path = attempt_dir / "meta.json"
    exit_path = attempt_dir / "exit_status.json"
    observability_path = attempt_dir / "observability.json"
    provenance_path = attempt_dir / "report_provenance.json"
    evidence_dir = attempt_dir / "search_evidence"
    if not report_path.is_file():
        raise ProjectionError("attempt has no report artifact")
    if not meta_path.is_file() or not exit_path.is_file():
        raise ProjectionError("attempt lacks meta or exit status")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    exit_status = json.loads(exit_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict) or not isinstance(exit_status, dict):
        raise ProjectionError("attempt meta or exit status is not an object")
    observability = (
        json.loads(observability_path.read_text(encoding="utf-8"))
        if observability_path.is_file()
        else None
    )
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance_path.is_file()
        else None
    )

    assets = PackageAssets.load(package_dir)
    quotes_by_url: dict[str, list[str]] = {}
    for row in assets.evidence_rows:
        quotes_by_url.setdefault(str(row["canonical_url"]), []).append(str(row["quote"]))

    ledger: list[dict[str, Any]] = []
    seen_body_keys: set[tuple[str, str]] = set()
    search_count = 0
    projected_content_count = 0
    frozen_quote_verified_count = 0
    for source_path, line_number, row in read_jsonl_files(evidence_dir):
        if row.get("kind") != "search":
            continue
        search_count += 1
        reference = str(row.get("response_blob_ref") or "")
        if not reference:
            raise ProjectionError("search row lacks response_blob_ref")
        blob_path = safe_blob_path(evidence_dir, reference)
        blob_sha = sha256_file(blob_path)
        if blob_sha != row.get("response_sha256"):
            raise ProjectionError("captured search response SHA mismatch")
        try:
            response = json.loads(blob_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProjectionError("captured search response is not JSON") from exc
        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(results, list):
            results = []
        result_rows = [value for value in results if isinstance(value, dict)]
        urls = [canonical_url(str(value.get("url") or "")) for value in result_rows]
        urls = [url for url in urls if url]
        ledger.append({
            "schema_version": "1.0.0",
            "event_id": f"SEARCH{search_count:04d}",
            "kind": "search",
            "status": row.get("status"),
            "urls_returned": urls,
            "captured_response_sha256": blob_sha,
            "source_ledger": source_path.name,
            "source_line": line_number,
        })
        for result_index, result in enumerate(result_rows, 1):
            reported_url = str(result.get("url") or "")
            url = canonical_url(reported_url)
            content = str(result.get("raw_content") or result.get("content") or "")
            if not url or not content:
                continue
            content_sha = hashlib.sha256(content.encode()).hexdigest()
            body_key = (url, content_sha)
            if body_key in seen_body_keys:
                continue
            seen_body_keys.add(body_key)
            frozen_quotes = quotes_by_url.get(url, [])
            matched_quotes = [quote for quote in frozen_quotes if quote in content]
            registry = assets.registry_by_url.get(url)
            verified = bool(registry) and bool(matched_quotes)
            if verified:
                frozen_quote_verified_count += len(matched_quotes)
            body_doc = {
                "canonical_url": url,
                "reported_url": reported_url,
                "content": content,
                "content_sha256": content_sha,
                "page_content_sha256": registry.get("page_content_sha256") if verified else None,
                "evidence_level": "structured_lookup",
                "truncated": True,
                "source_search_response_sha256": blob_sha,
                "frozen_exact_quote_ids": [
                    row["evidence_id"]
                    for row in assets.evidence_rows
                    if row.get("canonical_url") == url and row.get("quote") in matched_quotes
                ],
            }
            body_path = output_dir / "bodies" / f"{content_sha}.json"
            write_exclusive(body_path, body_doc)
            projected_content_count += 1
            ledger.append({
                "schema_version": "1.0.0",
                "event_id": f"LOOKUP{projected_content_count:04d}",
                "kind": "fetch",
                "operation": "search_response_raw_content_projection",
                "status": row.get("status"),
                "canonical_url": url,
                "reported_url": reported_url,
                "body_path": str(body_path.relative_to(output_dir)),
                "body_sha256": sha256_file(body_path),
                "page_content_sha256": body_doc["page_content_sha256"],
                "observation_tier": "structured_lookup",
                "source_search_response_sha256": blob_sha,
                "source_result_index": result_index,
                "frozen_identity_verified_by_exact_quote": verified,
            })

    source_rows = read_jsonl_files(evidence_dir)
    enhanced_health = (
        isinstance(observability, dict)
        and observability.get("schema_version") == "2.0.0"
    )
    if enhanced_health:
        fetch_count = sum(row.get("kind") == "fetch" for _, _, row in source_rows)
        if not (
            observability.get("recorder_initialized") is True
            and observability.get("capture_bracket_valid") is True
            and observability.get("capture_healthy") is True
            and observability.get("search_call_count") == search_count
            and observability.get("fetch_call_count") == fetch_count
        ):
            raise ProjectionError("attempt evidence recorder health proof is invalid")
    elif search_count == 0:
        raise ProjectionError("legacy matrix attempt contains no captured search")
    if search_count == 0:
        ledger.append(
            {
                "schema_version": "1.0.0",
                "event_id": "RECORDER0001",
                "kind": "recorder_health",
                "capture_healthy": True,
                "zero_tool_calls_attested": True,
            }
        )
    ledger_path = output_dir / "strict-evidence.jsonl"
    ledger_bytes = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode() + b"\n"
        for row in ledger
    )
    fd = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(ledger_bytes)

    citation_diagnostics = build_citation_diagnostics(
        report_path=report_path,
        assets=assets,
        ledger_rows=ledger,
        ledger_path=ledger_path,
    )
    citation_diagnostics_path = output_dir / "citation-diagnostics.json"
    write_exclusive(citation_diagnostics_path, citation_diagnostics)

    matrix_status = str(exit_status.get("status") or "").strip().lower()
    matrix_reason = str(exit_status.get("reason") or "").strip()
    projection_recovers_observability_only = (
        matrix_status == "failed" and matrix_reason == "evidence_observability_incomplete"
    )
    normal_agent_return = (
        exit_status.get("exit_code") == 0
        and meta.get("status") == "pass"
        and (
            matrix_status in {"success", "pass", "completed"}
            or projection_recovers_observability_only
        )
        and (
            not isinstance(provenance, dict)
            or provenance.get("model_output_attested") is True
        )
    )
    manifest = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "cell_id": exit_status.get("cell_id"),
        "completed": bool(normal_agent_return),
        "status": "completed" if normal_agent_return else "failed",
        "execution": {"outcome": "success" if normal_agent_return else "failed"},
        "failure": None if normal_agent_return else {
            "matrix_reason": exit_status.get("reason"),
            "runner_meta_status": meta.get("status"),
        },
        "report_sha256": sha256_file(report_path),
        "report_bytes": report_path.stat().st_size,
        "matrix_exit_status_sha256": sha256_file(exit_path),
        "matrix_meta_sha256": sha256_file(meta_path),
        "projection_kind": "captured_search_raw_content_only",
        "evidence_recorder_health_sha256": (
            sha256_file(observability_path) if observability_path.is_file() else None
        ),
        "report_provenance_sha256": (
            sha256_file(provenance_path) if provenance_path.is_file() else None
        ),
        "projection_recovers_observability_only": projection_recovers_observability_only,
    }
    write_exclusive(output_dir / "run-manifest.json", manifest)
    receipt = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "report_sha256": manifest["report_sha256"],
        "strict_evidence_sha256": sha256_file(ledger_path),
        "search_event_count": search_count,
        "zero_tool_calls_attested": search_count == 0,
        "projected_content_count": projected_content_count,
        "frozen_exact_quote_verified_count": frozen_quote_verified_count,
        "citation_diagnostics_sha256": sha256_file(citation_diagnostics_path),
        "citation_status_counts": citation_diagnostics["status_counts"],
        "normal_agent_return": normal_agent_return,
        "projection_recovers_observability_only": projection_recovers_observability_only,
        "formal_eligible": False,
        "scoring_mode": "SHADOW_EXPERIMENTAL_ONLY",
    }
    write_exclusive(output_dir / "projection-receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-dir", required=True, type=Path)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = project(
        attempt_dir=args.attempt_dir.resolve(),
        package_dir=args.package_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        run_id=args.run_id,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
