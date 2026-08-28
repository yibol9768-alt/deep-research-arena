#!/usr/bin/env python3
"""Build the sealed five-cell Q1-v2 Cross-5 score and cost delivery."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from summarize_cross5_pilot import (
    Pricing,
    add_tokens,
    combine_costs,
    normalized_tokens,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CROSS5_CELL_IDS = (
    "biodiversity-q1-v2--deerflow--gpt-5-6-sol",
    "biodiversity-q1-v2--deerflow--gemini-3-1-pro-preview",
    "biodiversity-q1-v2--deerflow--claude-opus-5",
    "biodiversity-q1-v2--opencode--gpt-5-6-sol",
    "biodiversity-q1-v2--claude-code--gpt-5-6-sol",
)
METRICS = ("citation_binding", "gcp", "grr")
TOKEN_KEYS = (
    "input", "output", "cached_input", "cache_write", "cache_write_5m",
    "cache_write_1h", "reasoning", "total",
)
SCORE_VERSION_RE = re.compile(r"score-v[1-9][0-9]*\Z")


def validated_score_version(value: str) -> str:
    if not SCORE_VERSION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "score version must match score-v[1-9][0-9]*"
        )
    return value


def cell_evaluation_path(
    scores_root: Path,
    run_id: str,
    cell_id: str,
    attempt_index: int,
    score_version: str,
) -> Path:
    validated_score_version(score_version)
    return (
        scores_root / run_id / cell_id / f"attempt-{attempt_index}"
        / score_version / "cell-evaluation.json"
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL row: {path}:{line_number}")
        rows.append(value)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_view(
    row: dict[str, Any],
    *,
    run_id: str,
    cell_id: str,
    attempt_index: int,
    pricing: Pricing,
) -> dict[str, Any]:
    if row.get("cell_id") != cell_id:
        raise ValueError(f"untagged or wrong cell_id in {cell_id}/attempt-{attempt_index}")
    attribution = row.get("matrix_attribution")
    if not isinstance(attribution, dict) or attribution.get("cell_id") != cell_id:
        raise ValueError(f"untagged or wrong matrix attribution in {cell_id}/attempt-{attempt_index}")
    event_id = row.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError(f"missing event_id in {cell_id}/attempt-{attempt_index}")
    tokens = normalized_tokens(row.get("tokens") or row.get("usage_raw"))
    requested = row.get("requested_model") or attribution.get("requested_model")
    return {
        "run_id": run_id,
        "cell_id": cell_id,
        "attempt_index": attempt_index,
        "event_id": event_id,
        "request_index": row.get("request_index"),
        "bracket_run_id": row.get("bracket_run_id"),
        "requested_model": requested,
        "caller_requested_model": row.get("caller_requested_model"),
        "expected_actual_identity": row.get("expected_actual_identity"),
        "actual_model_identity": row.get("actual_model_identity"),
        "identity_match": row.get("identity_match"),
        "http_status": row.get("http_status"),
        "transport_error_type": row.get("transport_error_type"),
        "latency_ms": row.get("latency_ms"),
        "service_tier": row.get("service_tier"),
        "usage_observed": bool(row.get("usage_observed")),
        "tokens": tokens,
        "cost": pricing.price(requested, tokens, row.get("service_tier")),
        "response_body_sha256": row.get("response_body_sha256"),
    }


def load_evaluation(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    document = read_json(path)
    if document.get("status") != "SCORED":
        raise ValueError(f"non-SCORED cell evaluation: {path}")
    metrics = document.get("metrics") if isinstance(document.get("metrics"), dict) else {}
    for name in METRICS:
        row = metrics.get(name)
        value = row.get("score") if isinstance(row, dict) else None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError(f"non-numeric {name} in {path}")
    if metrics["grr"].get("denominator") != 34:
        raise ValueError(f"GRR denominator is not 34 in {path}")
    seal = path.with_name("cell-evaluation-seal.json")
    if not seal.is_file():
        raise ValueError(f"cell evaluation seal is missing: {path}")
    return document


def reconcile_gateway_events(
    run_rows: list[dict[str, Any]], attempt_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    run_ids = [row.get("event_id") for row in run_rows]
    attempt_ids = [row.get("event_id") for row in attempt_rows]
    if any(not isinstance(value, str) or not value for value in run_ids + attempt_ids):
        raise ValueError("gateway ledger contains an untagged event")
    if len(run_ids) != len(set(run_ids)) or len(attempt_ids) != len(set(attempt_ids)):
        raise ValueError("gateway ledger contains duplicate event IDs")
    if Counter(run_ids) != Counter(attempt_ids):
        raise ValueError("run-level gateway ledger does not equal per-attempt ledgers")
    return {
        "status": "PASS_EXACT_EVENT_ID_RECONCILIATION",
        "run_event_count": len(run_ids),
        "attempt_event_count": len(attempt_ids),
        "untagged_event_count": 0,
        "duplicate_event_count": 0,
    }


def group_summary(cells: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values = sorted({str(row[key]) for row in cells})
    result = []
    for value in values:
        selected = [row for row in cells if str(row[key]) == value]
        scored = [row for row in selected if row["evaluation_status"] == "scored"]
        request_costs = [cost for row in selected for cost in row["agent_request_costs"]]
        result.append(
            {
                key: value,
                "cell_count": len(selected),
                "scored_cell_count": len(scored),
                "agent_request_count": sum(row["agent_request_count"] for row in selected),
                "agent_tokens": add_tokens([row["agent_tokens"] for row in selected]),
                "agent_cost": combine_costs(request_costs),
                **{
                    f"mean_{metric}": (
                        sum(row["metrics"][metric]["score"] for row in scored) / len(scored)
                        if scored else None
                    )
                    for metric in METRICS
                },
            }
        )
    return result


def build_summary(
    *,
    run_dir: Path,
    scores_root: Path,
    manifest_path: Path,
    pricing: Pricing,
    route_probe: Path | None,
    score_version: str = "score-v1",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    score_version = validated_score_version(score_version)
    manifest = read_json(manifest_path)
    if tuple(row.get("cell_id") for row in manifest.get("cells", [])) != EXPECTED_CROSS5_CELL_IDS:
        raise ValueError("manifest is not the frozen Q1-v2 Cross-5 matrix")
    run_header = read_json(run_dir / "run.json")
    if (
        run_header.get("matrix_id") != manifest.get("matrix_id")
        or run_header.get("task_id") != manifest.get("task_id")
        or run_header.get("formal_eligible") is not False
    ):
        raise ValueError("matrix run header does not match the Q1-v2 manifest")
    run_id = str(run_header["run_id"])
    all_requests = []
    raw_attempt_rows = []
    cells = []
    for cell in manifest["cells"]:
        cell_id = cell["cell_id"]
        cell_dir = run_dir / "cells" / cell_id
        state = read_json(cell_dir / "state.json")
        attempts = []
        for attempt_dir in sorted(
            cell_dir.glob("attempt-[0-9]*"),
            key=lambda path: int(path.name.split("-")[-1]),
        ):
            attempt_index = int(attempt_dir.name.split("-")[-1])
            raw_rows = jsonl(attempt_dir / "gateway_usage.jsonl")
            raw_attempt_rows.extend(raw_rows)
            rows = [
                request_view(
                    row,
                    run_id=run_id,
                    cell_id=cell_id,
                    attempt_index=attempt_index,
                    pricing=pricing,
                )
                for row in raw_rows
            ]
            all_requests.extend(rows)
            exit_status = read_json(attempt_dir / "exit_status.json")
            attempts.append(
                {
                    "attempt_index": attempt_index,
                    "status": exit_status.get("status"),
                    "reason": exit_status.get("reason"),
                    "exit_code": exit_status.get("exit_code"),
                    "request_count": len(rows),
                    "tokens": add_tokens([row["tokens"] for row in rows]),
                    "cost": combine_costs([row["cost"] for row in rows]),
                    "report_sha256": (
                        sha256_file(attempt_dir / "report.md")
                        if (attempt_dir / "report.md").is_file() else None
                    ),
                    "seal_sha256": (
                        sha256_file(attempt_dir / "seal.json")
                        if (attempt_dir / "seal.json").is_file() else None
                    ),
                }
            )
        attempt_index = int(state.get("attempt_count") or 0)
        evaluation_path = cell_evaluation_path(
            scores_root,
            run_id,
            cell_id,
            attempt_index,
            score_version,
        )
        evaluation = load_evaluation(evaluation_path) if attempt_index else None
        cell_requests = [row for row in all_requests if row["cell_id"] == cell_id]
        cell_costs = [row["cost"] for row in cell_requests]
        cell_record = {
            "cell_id": cell_id,
            "harness_id": cell["harness_id"],
            "model_id": cell["model_id"],
            "requested_model": cell["model_request_name"],
            "matrix_status": state.get("status"),
            "matrix_reason": state.get("status_reason"),
            "attempt_count": len(attempts),
            "attempts": attempts,
            "agent_request_count": len(cell_requests),
            "agent_tokens": add_tokens([row["tokens"] for row in cell_requests]),
            "agent_cost": combine_costs(cell_costs),
            "agent_request_costs": cell_costs,
            "evaluation_status": "scored" if evaluation else "not_scored",
            "metrics": (
                evaluation["metrics"] if evaluation else {
                    name: {"score": None, "status": "not_scored", "numerator": None, "denominator": None}
                    for name in METRICS
                }
            ),
            "judge": evaluation.get("judge") if evaluation else None,
            "evaluation_path": str(evaluation_path) if evaluation else None,
            "evaluation_sha256": sha256_file(evaluation_path) if evaluation else None,
        }
        cells.append(cell_record)
    reconciliation = reconcile_gateway_events(
        jsonl(run_dir / "usage/gateway_events.jsonl"), raw_attempt_rows
    )
    diagnostic_rows = []
    if route_probe is not None:
        probe = read_json(route_probe)
        if probe.get("schema_version") != "q1_v2_model_route_probe_v1":
            raise ValueError("route probe receipt has the wrong schema")
        for row in probe.get("rows", []):
            tokens = normalized_tokens(row.get("usage"))
            diagnostic_rows.append(
                {
                    "model_id": row.get("model_id"),
                    "requested_model": row.get("upstream_request_model"),
                    "actual_model_identity": row.get("actual_model_identity"),
                    "identity_match": row.get("identity_match"),
                    "http_status": row.get("http_status"),
                    "tokens": tokens,
                    "cost": pricing.price(row.get("upstream_request_model"), tokens, None),
                }
            )
    model_groups = group_summary(cells, "model_id")
    harness_groups = group_summary(cells, "harness_id")
    all_agent_costs = [row["cost"] for row in all_requests]
    judge_rows = [row["judge"] for row in cells if row["judge"] is not None]
    summary = {
        "schema_version": "biodiversity_q1_v2_cross5_summary_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "matrix_id": manifest["matrix_id"],
        "task_id": manifest["task_id"],
        "score_version": score_version,
        "scope": "SHADOW_EXPERIMENTAL_ONLY",
        "formal_eligible": False,
        "cell_count": 5,
        "scored_cell_count": sum(row["evaluation_status"] == "scored" for row in cells),
        "matrix_status_counts": dict(sorted(Counter(str(row["matrix_status"]) for row in cells).items())),
        "gateway_reconciliation": reconciliation,
        "pricing": {
            "manifest_id": pricing.doc.get("pricing_manifest_id"),
            "verified_on": pricing.doc.get("verified_on"),
            "manifest_sha256": sha256_file(pricing.path),
            "fx_snapshot": pricing.doc.get("fx_snapshot"),
            "axis_policy": pricing.doc.get("price_axis_policy"),
        },
        "cells": [{key: value for key, value in row.items() if key != "agent_request_costs"} for row in cells],
        "by_model": model_groups,
        "by_harness": harness_groups,
        "totals": {
            "agent_request_count": len(all_requests),
            "agent_tokens": add_tokens([row["tokens"] for row in all_requests]),
            "agent_cost": combine_costs(all_agent_costs),
            "judge_request_count": sum(int(row.get("request_count") or 0) for row in judge_rows),
            "judge_tokens": add_tokens([row["tokens"] for row in judge_rows]),
            "judge_cost": combine_costs([row["cost"] for row in judge_rows]),
            "diagnostic_request_count": len(diagnostic_rows),
            "diagnostic_tokens": add_tokens([row["tokens"] for row in diagnostic_rows]),
            "diagnostic_cost": combine_costs([row["cost"] for row in diagnostic_rows]),
        },
    }
    return summary, all_requests


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def flattened_group(rows: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        result.append(
            {
                group_key: row[group_key],
                "cell_count": row["cell_count"],
                "scored_cell_count": row["scored_cell_count"],
                "agent_request_count": row["agent_request_count"],
                **{f"agent_{key}_tokens": row["agent_tokens"][key] for key in TOKEN_KEYS},
                "agent_cost_usd": row["agent_cost"].get("usd"),
                "agent_known_cost_usd": row["agent_cost"].get("known_usd_subtotal"),
                "agent_cost_cny": row["agent_cost"].get("cny"),
                "agent_known_cost_cny": row["agent_cost"].get("known_cny_subtotal"),
                "agent_cost_status": row["agent_cost"].get("status"),
                "mean_citation_binding": row["mean_citation_binding"],
                "mean_gcp": row["mean_gcp"],
                "mean_grr": row["mean_grr"],
            }
        )
    return result


def write_outputs(summary: dict[str, Any], requests: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "matrix_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cell_rows = []
    for row in summary["cells"]:
        cell_rows.append(
            {
                "cell_id": row["cell_id"],
                "harness_id": row["harness_id"],
                "model_id": row["model_id"],
                "requested_model": row["requested_model"],
                "matrix_status": row["matrix_status"],
                "matrix_reason": row["matrix_reason"],
                "attempt_count": row["attempt_count"],
                "agent_request_count": row["agent_request_count"],
                **{f"agent_{key}_tokens": row["agent_tokens"][key] for key in TOKEN_KEYS},
                "agent_cost_usd": row["agent_cost"].get("usd"),
                "agent_known_cost_usd": row["agent_cost"].get("known_usd_subtotal"),
                "agent_cost_cny": row["agent_cost"].get("cny"),
                "agent_known_cost_cny": row["agent_cost"].get("known_cny_subtotal"),
                "agent_cost_status": row["agent_cost"].get("status"),
                "evaluation_status": row["evaluation_status"],
                "citation_binding": row["metrics"]["citation_binding"]["score"],
                "gcp": row["metrics"]["gcp"]["score"],
                "grr": row["metrics"]["grr"]["score"],
                "grr_denominator": row["metrics"]["grr"]["denominator"],
                "judge_request_count": (row["judge"] or {}).get("request_count"),
                "judge_cost_usd": ((row["judge"] or {}).get("cost") or {}).get("usd"),
                "judge_cost_status": ((row["judge"] or {}).get("cost") or {}).get("status"),
                "evaluation_sha256": row["evaluation_sha256"],
            }
        )
    write_csv(output_dir / "matrix_cells.csv", cell_rows)
    request_rows = []
    for row in requests:
        request_rows.append(
            {
                **{key: value for key, value in row.items() if key not in {"tokens", "cost"}},
                **{f"{key}_tokens": row["tokens"][key] for key in TOKEN_KEYS},
                "cost_usd": row["cost"].get("usd"),
                "known_cost_usd": row["cost"].get("known_usd_subtotal"),
                "cost_cny": row["cost"].get("cny"),
                "known_cost_cny": row["cost"].get("known_cny_subtotal"),
                "cost_status": row["cost"].get("status"),
                "rate_card_id": row["cost"].get("rate_card_id"),
            }
        )
    write_csv(output_dir / "agent_requests.csv", request_rows)
    write_csv(output_dir / "model_summary.csv", flattened_group(summary["by_model"], "model_id"))
    write_csv(output_dir / "harness_summary.csv", flattened_group(summary["by_harness"], "harness_id"))
    files = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.json":
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    (output_dir / "SHA256SUMS.json").write_text(
        json.dumps({"schema_version": "q1_v2_delivery_seal_v1", "files": files}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--scores-root", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "generated/matrix.cross5.manifest.json",
    )
    parser.add_argument("--pricing", type=Path, default=ROOT / "config/pricing.cross5.20260825.json")
    parser.add_argument("--route-probe-receipt", type=Path)
    parser.add_argument(
        "--score-version",
        default="score-v1",
        type=validated_score_version,
        help="Read evaluations only from this immutable score version.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary, requests = build_summary(
        run_dir=args.run_dir.resolve(),
        scores_root=args.scores_root.resolve(),
        manifest_path=args.manifest.resolve(),
        pricing=Pricing(args.pricing),
        route_probe=args.route_probe_receipt.resolve() if args.route_probe_receipt else None,
        score_version=args.score_version,
    )
    write_outputs(summary, requests, args.output_dir.resolve())
    print(json.dumps({
        "output_dir": str(args.output_dir.resolve()),
        "cell_count": summary["cell_count"],
        "scored_cell_count": summary["scored_cell_count"],
        "agent_request_count": summary["totals"]["agent_request_count"],
        "gateway_reconciliation": summary["gateway_reconciliation"]["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
