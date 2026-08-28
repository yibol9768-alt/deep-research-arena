#!/usr/bin/env python3
"""Offline, evidence-preserving summary for the Biodiversity Q1 cross-5 pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRICING = ROOT / "config/pricing.cross5.20260825.json"
# The old Pilot is a diagnostic asset with old task/cell identities.  Pin its
# summarizer to a dedicated immutable snapshot so the Q1-v2 formal matrix can
# evolve without mixing Pilot inputs into real results.
DEFAULT_MANIFEST = ROOT / "config/matrix.pilot-v1.snapshot.json"
PILOT_CELL_IDS = (
    "biodiversity-q1--deerflow--gpt-5-6-sol",
    "biodiversity-q1--deerflow--gemini-3-1-pro-preview",
    "biodiversity-q1--deerflow--claude-opus-5",
    "biodiversity-q1--opencode--gpt-5-6-sol",
    "biodiversity-q1--claude-code--gpt-5-6-sol",
)
TOKEN_KEYS = ("input", "output", "cached_input", "cache_write", "cache_write_5m", "cache_write_1h", "reasoning", "total")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    return {"status": "present", "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: JSONL row is not an object")
        rows.append(value)
    return rows


def zero_tokens() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


def normalized_tokens(value: dict[str, Any] | None) -> dict[str, int]:
    value = value or {}
    prompt_details = value.get("prompt_tokens_details") if isinstance(value.get("prompt_tokens_details"), dict) else {}
    completion_details = value.get("completion_tokens_details") if isinstance(value.get("completion_tokens_details"), dict) else {}
    aliases = {
        "input": ("input", "prompt_tokens", "input_tokens"),
        "output": ("output", "completion_tokens", "output_tokens"),
        "cached_input": ("cached_input", "cached_tokens", "cache_read_tokens"),
        "cache_write": ("cache_write", "cache_creation_input_tokens"),
        "cache_write_5m": ("cache_write_5m", "cache_creation_5m_input_tokens"),
        "cache_write_1h": ("cache_write_1h", "cache_creation_1h_input_tokens"),
        "reasoning": ("reasoning", "reasoning_tokens"),
        "total": ("total", "total_tokens"),
    }
    out = {}
    for target, choices in aliases.items():
        raw = next((value[key] for key in choices if value.get(key) is not None), 0)
        out[target] = int(raw or 0)
        if out[target] < 0:
            raise ValueError(f"negative token count for {target}")
    if out["total"] == 0:
        out["total"] = out["input"] + out["output"]
    if out["cached_input"] == 0:
        out["cached_input"] = int(prompt_details.get("cached_tokens", 0) or 0)
    if out["reasoning"] == 0:
        out["reasoning"] = int(completion_details.get("reasoning_tokens", 0) or 0)
    return out


def add_tokens(rows: list[dict[str, int]]) -> dict[str, int]:
    return {key: sum(row.get(key, 0) for row in rows) for key in TOKEN_KEYS}


class Pricing:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.doc = read_json(self.path)
        if not isinstance(self.doc, dict):
            raise ValueError("pricing source is not an object")
        self.by_requested = {row["requested_model_name"]: row for row in self.doc.get("models", [])}

    def price(self, requested_model: str | None, tokens: dict[str, int], service_tier: str | None) -> dict[str, Any]:
        model = self.by_requested.get(requested_model)
        base = {
            "currency": "USD",
            "cny": None,
            "cny_status": "N/A_FX" if self.doc.get("fx_snapshot", {}).get("cny_per_usd") is None else "available",
            "pricing_model": requested_model,
            "service_tier_observed": service_tier,
        }
        if not model or model.get("status") != "official_verified":
            return {**base, "status": "N/A_UNPRICED_EXACT_MODEL", "usd": None, "rate_card_id": None}
        prompt = tokens["input"]
        cards = [
            card for card in model.get("rate_cards", [])
            if prompt >= int(card.get("prompt_tokens_min", 0))
            and (card.get("prompt_tokens_max") is None or prompt <= int(card["prompt_tokens_max"]))
        ]
        if len(cards) != 1:
            return {**base, "status": "N/A_NO_UNIQUE_RATE_CARD", "usd": None, "rate_card_id": None}
        card = cards[0]
        rates = card.get("per_million_tokens", {})
        if rates.get("input") is None or rates.get("output") is None:
            return {**base, "status": "N/A_INCOMPLETE_RATE_CARD", "usd": None, "rate_card_id": card.get("rate_card_id")}
        # The frozen price-axis policy intentionally includes input/output only.
        # Cached/cache-write/reasoning buckets remain observable but are not
        # separately added to this official-equivalent axis.
        usd = (
            Decimal(tokens["input"]) * Decimal(str(rates["input"]))
            + Decimal(tokens["output"]) * Decimal(str(rates["output"]))
        ) / Decimal(1_000_000)
        fx = self.doc.get("fx_snapshot", {}).get("cny_per_usd")
        return {
            **base,
            "status": "priced_official_input_output_axis",
            "usd": float(usd),
            "cny": float(usd * Decimal(str(fx))) if fx is not None else None,
            "rate_card_id": card.get("rate_card_id"),
            "input_usd_per_million": rates["input"],
            "output_usd_per_million": rates["output"],
        }


def combine_costs(costs: list[dict[str, Any]], *, missing_status: str = "not_available") -> dict[str, Any]:
    if not costs:
        return {"status": missing_status, "currency": "USD", "usd": None, "cny": None, "cny_status": "not_available"}
    unknown = [row for row in costs if row.get("usd") is None]
    known_usd = sum(Decimal(str(row["usd"])) for row in costs if row.get("usd") is not None)
    known_cny = sum(Decimal(str(row["cny"])) for row in costs if row.get("cny") is not None)
    all_known_cny = all(row.get("cny") is not None for row in costs if row.get("usd") is not None)
    status = "priced_official_input_output_axis" if not unknown else "PARTIAL_NA_UNPRICED"
    return {
        "status": status,
        "currency": "USD",
        "usd": float(known_usd) if not unknown else None,
        "known_usd_subtotal": float(known_usd),
        "unpriced_item_count": len(unknown),
        "cny": float(known_cny) if not unknown and all_known_cny else None,
        "known_cny_subtotal": float(known_cny),
        "cny_status": "available" if not unknown and all_known_cny else ("PARTIAL_NA_UNPRICED" if unknown else "N/A_FX"),
    }


def request_record(row: dict[str, Any], *, run_id: str, cell_id: str, attempt_index: int, pricing: Pricing) -> dict[str, Any]:
    if row.get("cell_id") not in {None, cell_id}:
        raise ValueError(f"usage attribution mismatch in {run_id}/{cell_id}/attempt-{attempt_index}")
    matrix_cell = (row.get("matrix_attribution") or {}).get("cell_id")
    if matrix_cell not in {None, cell_id}:
        raise ValueError(f"matrix attribution mismatch in {run_id}/{cell_id}/attempt-{attempt_index}")
    tokens = normalized_tokens(row.get("tokens") or row.get("usage_raw"))
    requested = row.get("requested_model") or (row.get("matrix_attribution") or {}).get("requested_model")
    return {
        "run_id": run_id,
        "cell_id": cell_id,
        "cell_attempt_index": attempt_index,
        "cell_retry_index": attempt_index - 1,
        "gateway_request_index": row.get("request_index"),
        "event_id": row.get("event_id"),
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
        "response_body_sha256": row.get("response_body_sha256"),
        "cost": pricing.price(requested, tokens, row.get("service_tier")),
    }


def metric_view(score: dict[str, Any]) -> dict[str, Any]:
    metrics = score.get("metrics")
    if not isinstance(metrics, dict):
        metrics = (score.get("score") or {}).get("metrics") if isinstance(score.get("score"), dict) else {}
    def one(name: str) -> dict[str, Any]:
        row = metrics.get(name) if isinstance(metrics.get(name), dict) else {}
        source_status = row.get("status")
        status = (
            "scored"
            if str(source_status or "").startswith("scored")
            else source_status
        )
        return {"score": row.get("score"), "status": status, "source_status": source_status, "numerator": row.get("passed_required_claim_count", row.get("grounded_claim_count", row.get("grounded_unit_count"))), "denominator": row.get("required_claim_count", row.get("eligible_claim_count", row.get("necessary_unit_count")))}
    return {"citation_binding": one("citation_binding"), "gcp": one("gcp"), "grr": one("grr")}


def infer_score_key(score_dir: Path, explicit_key: str | None = None) -> tuple[str, str, int]:
    if explicit_key:
        parts = explicit_key.split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            raise ValueError("--score-map key must be RUN_ID:CELL_ID:ATTEMPT")
        return parts[0], parts[1], int(parts[2])
    candidates = []
    for name in ("run-manifest.json", "projection-receipt.json", "protocol-manifest.json", "run-receipt.json"):
        doc = read_json(score_dir / name, {})
        if not isinstance(doc, dict):
            continue
        flattened = [doc]
        for key in ("source", "matrix", "input", "matrix_attempt"):
            if isinstance(doc.get(key), dict):
                flattened.append(doc[key])
        for row in flattened:
            run_id = row.get("matrix_run_id") or row.get("source_run_id") or row.get("run_id")
            cell_id = row.get("cell_id") or row.get("matrix_cell_id")
            attempt = row.get("attempt") or row.get("attempt_index") or row.get("matrix_attempt")
            if isinstance(run_id, str) and isinstance(cell_id, str) and attempt is not None:
                candidates.append((run_id, cell_id, int(attempt)))
    if len(set(candidates)) != 1:
        raise ValueError(f"cannot uniquely infer score association for {score_dir}; use --score-map")
    return candidates[0]


def load_score(score_dir: Path, key: tuple[str, str, int], pricing: Pricing) -> dict[str, Any]:
    shadow_path = score_dir / "shadow-score.json"
    shadow = read_json(shadow_path)
    if not isinstance(shadow, dict):
        raise ValueError(f"missing shadow-score.json in {score_dir}")
    judge_calls = []
    for metadata_path in sorted(score_dir.glob("judge-calls/*/metadata.json")):
        row = read_json(metadata_path, {})
        tokens = normalized_tokens(row.get("usage"))
        request_model = row.get("request_model")
        judge_calls.append({
            "stage": row.get("stage"), "retry_index": row.get("retry_index"),
            "request_model": request_model, "expected_response_model": row.get("expected_response_model"),
            "actual_response_model": row.get("actual_response_model"), "identity_match": row.get("identity_match"),
            "http_status": row.get("http_status"), "transport_error": row.get("transport_error"),
            "latency_ms": row.get("latency_ms"), "tokens": tokens,
            "cost": pricing.price(request_model, tokens, None),
            "metadata": artifact(metadata_path),
        })
    return {
        "association": {"run_id": key[0], "cell_id": key[1], "attempt_index": key[2]},
        "score_dir": str(score_dir.resolve()), "shadow_score": artifact(shadow_path),
        "metrics": metric_view(shadow), "failure_status": shadow.get("failure_status") or (shadow.get("score") or {}).get("failure_status"),
        "judge_calls": judge_calls, "judge_tokens": add_tokens([row["tokens"] for row in judge_calls]),
        "judge_cost": combine_costs([row["cost"] for row in judge_calls]),
    }


def score_map(score_specs: list[str], score_dirs: list[Path], pricing: Pricing) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    result: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    items: list[tuple[str | None, Path]] = [(None, path) for path in score_dirs]
    for spec in score_specs:
        if "=" not in spec:
            raise ValueError("--score-map requires RUN_ID:CELL_ID:ATTEMPT=DIR")
        key, value = spec.split("=", 1)
        items.append((key, Path(value)))
    for explicit, path in items:
        path = path.resolve()
        key = infer_score_key(path, explicit)
        result.setdefault(key, []).append(load_score(path, key, pricing))
    return result


def diagnostic_records(paths: list[Path], pricing: Pricing) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        doc = read_json(path)
        if not isinstance(doc, dict):
            raise ValueError(f"diagnostic receipt is not an object: {path}")
        if doc.get("schema_version") == "gpt_route_payload_probe_v1":
            requested = doc.get("requested_model")
            rows = doc.get("rows") if isinstance(doc.get("rows"), list) else []
            for index, row in enumerate(rows, 1):
                tokens = normalized_tokens(row.get("usage"))
                records.append({
                    "receipt": artifact(path), "diagnostic_type": "gpt_route_payload_probe",
                    "request_index": index, "variant": row.get("variant"), "requested_model": requested,
                    "actual_model_identity": row.get("actual_model_identity"), "identity_match": row.get("identity_match"),
                    "http_status": row.get("http_status"), "latency_ms": row.get("latency_ms"),
                    "tokens": tokens, "cost": pricing.price(requested, tokens, None),
                })
        elif doc.get("schema") == "biodiv_q1_judge_control_probe_v1":
            tokens = normalized_tokens(doc.get("usage"))
            requested = doc.get("request_model") or doc.get("expected_model")
            records.append({
                "receipt": artifact(path), "diagnostic_type": "judge_control_probe",
                "request_index": 1, "variant": doc.get("variant"), "requested_model": requested,
                "actual_model_identity": doc.get("actual_model"), "identity_match": doc.get("identity_match"),
                "http_status": doc.get("http_status"), "latency_ms": doc.get("latency_ms"),
                "tokens": tokens, "cost": pricing.price(requested, tokens, None),
            })
        else:
            raise ValueError(f"unsupported diagnostic receipt schema: {path}")
    return records


def attempt_record(run_id: str, cell_id: str, attempt_dir: Path, pricing: Pricing, scores: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_index = int(attempt_dir.name.split("-")[-1])
    exit_doc = read_json(attempt_dir / "exit_status.json", {})
    requests = [request_record(row, run_id=run_id, cell_id=cell_id, attempt_index=attempt_index, pricing=pricing) for row in jsonl(attempt_dir / "gateway_usage.jsonl")]
    report = artifact(attempt_dir / "report.md")
    if report["status"] == "present":
        report["report_status"] = "present" if report["bytes"] else "empty"
    else:
        report["report_status"] = "missing"
    report["attempt_relation"] = (
        "present_on_successful_attempt" if report["report_status"] == "present" and exit_doc.get("status") == "success"
        else "present_on_non_success_attempt" if report["report_status"] == "present"
        else "no_nonempty_report"
    )
    evidence = []
    for name in ("failure_receipt.json", "exit_status.json", "identity.json", "observability.json", "seal.json", "stderr.log", "stdout.log"):
        path = attempt_dir / name
        if path.is_file():
            item = artifact(path)
            if name.endswith(".json"):
                item["content"] = read_json(path)
            evidence.append(item)
    return {
        "run_id": run_id, "cell_id": cell_id, "attempt_index": attempt_index,
        "retry_index": attempt_index - 1, "path": str(attempt_dir.resolve()),
        "status": exit_doc.get("status", "unknown"), "reason": exit_doc.get("reason"),
        "exit_code": exit_doc.get("exit_code"), "report": report,
        "requests": requests, "request_count": len(requests),
        "agent_tokens": add_tokens([row["tokens"] for row in requests]),
        "agent_cost": combine_costs([row["cost"] for row in requests]),
        "scores": scores, "failure_evidence": evidence,
    }


def classify_evaluation_outcome(
    attempts: list[dict[str, Any]], score_runs: list[dict[str, Any]]
) -> tuple[str, str]:
    """Return a terminal pilot label without converting missing evidence to zero."""
    if score_runs:
        latest = score_runs[-1]
        metrics = latest["metrics"]
        if all(
            metrics[name].get("status") == "scored"
            and metrics[name].get("score") is not None
            for name in ("citation_binding", "gcp", "grr")
        ):
            return "scored", "latest_score_run_has_all_three_metrics"
        failure = latest.get("failure_status")
        if isinstance(failure, dict):
            reason = failure.get("status_code") or failure.get("reason")
        else:
            reason = failure
        statuses = sorted(
            {
                str(metrics[name].get("status"))
                for name in ("citation_binding", "gcp", "grr")
                if metrics[name].get("status")
            }
        )
        return "withheld_scoring", str(reason or ",".join(statuses) or "score_not_available")

    report_attempts = [
        row for row in attempts if row["report"].get("report_status") == "present"
    ]
    observability_failures = [
        row
        for row in report_attempts
        if row.get("reason") == "evidence_observability_incomplete"
    ]
    if observability_failures:
        return "withheld_observability", "evidence_observability_incomplete"
    successful = [row for row in attempts if row.get("status") == "success"]
    if successful:
        return "withheld_unscored", "successful_report_has_no_score_run"
    if attempts:
        last = attempts[-1]
        return "harness_failure", str(last.get("reason") or "failed_without_score")
    return "blocked_not_run", "no_attempt_record"


def build_summary(run_dirs: list[Path], pricing: Pricing, scores: dict[tuple[str, str, int], list[dict[str, Any]]], manifest_path: Path = DEFAULT_MANIFEST, diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    diagnostics = diagnostics or []
    manifest = read_json(manifest_path)
    by_id = {row["cell_id"]: row for row in manifest.get("cells", [])}
    if set(PILOT_CELL_IDS) - set(by_id):
        raise ValueError("matrix manifest lacks one or more frozen pilot cells")
    run_records = []
    attempts_by_cell = {cell_id: [] for cell_id in PILOT_CELL_IDS}
    states_by_cell = {cell_id: [] for cell_id in PILOT_CELL_IDS}
    seen_runs = set()
    for run_dir in run_dirs:
        run_dir = run_dir.resolve()
        header = read_json(run_dir / "run.json")
        if not isinstance(header, dict) or not isinstance(header.get("run_id"), str):
            raise ValueError(f"invalid run directory: {run_dir}")
        run_id = header["run_id"]
        if run_id in seen_runs:
            raise ValueError(f"duplicate run_id input: {run_id}")
        seen_runs.add(run_id)
        states = []
        for cell_id in PILOT_CELL_IDS:
            cell_dir = run_dir / "cells" / cell_id
            state = read_json(cell_dir / "state.json", {"cell_id": cell_id, "status": "missing", "status_reason": "missing_state"})
            state_view = {"run_id": run_id, "cell_id": cell_id, "status": state.get("status"), "reason": state.get("status_reason"), "attempt_count": state.get("attempt_count", 0), "usage_event_count": state.get("usage_event_count", 0)}
            states.append(state_view)
            states_by_cell[cell_id].append(state_view)
            for attempt_dir in sorted(cell_dir.glob("attempt-[0-9]*"), key=lambda p: int(p.name.split("-")[-1])):
                idx = int(attempt_dir.name.split("-")[-1])
                attempts_by_cell[cell_id].append(attempt_record(run_id, cell_id, attempt_dir, pricing, scores.get((run_id, cell_id, idx), [])))
        run_records.append({"run_id": run_id, "path": str(run_dir), "header": header, "pilot_states": states})
    unused_scores = sorted(set(scores) - {(a["run_id"], a["cell_id"], a["attempt_index"]) for values in attempts_by_cell.values() for a in values})
    if unused_scores:
        raise ValueError(f"scores reference absent attempts: {unused_scores}")
    cells = []
    for cell_id in PILOT_CELL_IDS:
        cell_manifest = by_id[cell_id]
        attempts = attempts_by_cell[cell_id]
        requests = [request for attempt in attempts for request in attempt["requests"]]
        score_runs = [score for attempt in attempts for score in attempt["scores"]]
        evaluation_status, evaluation_reason = classify_evaluation_outcome(
            attempts, score_runs
        )
        actual = sorted({row["actual_model_identity"] for row in requests if row.get("actual_model_identity")})
        observed_identity_rows = [row for row in requests if row.get("actual_model_identity") is not None]
        cell = {
            "cell_id": cell_id, "harness_id": cell_manifest["harness_id"], "model_id": cell_manifest["model_id"],
            "requested_model": cell_manifest["model_request_name"], "run_states": states_by_cell[cell_id],
            "attempts": attempts, "attempt_count": len(attempts), "request_count": len(requests),
            "http_status_counts": dict(sorted(Counter(str(row.get("http_status") if row.get("http_status") is not None else "transport_error") for row in requests).items())),
            "actual_model_identities": actual,
            "identity_all_observed_match": all(row.get("identity_match") is True for row in observed_identity_rows) if observed_identity_rows else None,
            "report_count": sum(a["report"]["report_status"] == "present" for a in attempts),
            "agent_tokens": add_tokens([row["tokens"] for row in requests]),
            "agent_cost": combine_costs([row["cost"] for row in requests]),
            "score_runs": score_runs,
            "score_status": "available" if score_runs else "not_available",
            "evaluation_status": evaluation_status,
            "evaluation_reason": evaluation_reason,
            "latest_metrics": score_runs[-1]["metrics"] if score_runs else {name: {"score": None, "status": "not_available", "numerator": None, "denominator": None} for name in ("citation_binding", "gcp", "grr")},
            "judge_tokens": add_tokens([score["judge_tokens"] for score in score_runs]),
            "judge_cost": combine_costs([call["cost"] for score in score_runs for call in score["judge_calls"]]),
        }
        cells.append(cell)
    all_requests = [request for cell in cells for attempt in cell["attempts"] for request in attempt["requests"]]
    all_judge_calls = [call for cell in cells for score in cell["score_runs"] for call in score["judge_calls"]]
    return {
        "schema_version": "biodiversity_q1_cross5_pilot_summary_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "SHADOW_EXPERIMENTAL_ONLY",
        "design": {"unique_cell_count": 5, "cell_ids": list(PILOT_CELL_IDS), "not_a_3x3_product": True},
        "pricing": {"source": artifact(pricing.path), "manifest_id": pricing.doc.get("pricing_manifest_id"), "verified_on": pricing.doc.get("verified_on"), "axis_policy": pricing.doc.get("price_axis_policy"), "fx_snapshot": pricing.doc.get("fx_snapshot")},
        "runs": run_records, "cells": cells, "diagnostics": diagnostics,
        "totals": {
            "run_count": len(run_records), "unique_cell_count": 5,
            "attempt_count": sum(cell["attempt_count"] for cell in cells),
            "request_count": len(all_requests), "report_count": sum(cell["report_count"] for cell in cells),
            "scored_cell_count": sum(cell["score_status"] == "available" for cell in cells),
            "agent_tokens": add_tokens([row["tokens"] for row in all_requests]),
            "agent_cost": combine_costs([row["cost"] for row in all_requests]),
            "judge_tokens": add_tokens([row["tokens"] for row in all_judge_calls]),
            "judge_cost": combine_costs([row["cost"] for row in all_judge_calls]),
            "diagnostic_tokens": add_tokens([row["tokens"] for row in diagnostics]),
            "diagnostic_cost": combine_costs([row["cost"] for row in diagnostics]),
            "cny_status": "N/A_FX" if pricing.doc.get("fx_snapshot", {}).get("cny_per_usd") is None else "available",
        },
    }


def write_csvs(summary: dict[str, Any], output_dir: Path) -> None:
    def write(name: str, fields: list[str], rows: list[dict[str, Any]]):
        with (output_dir / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
    cell_rows = []
    for cell in summary["cells"]:
        metrics = cell["latest_metrics"]
        cell_rows.append({
            "cell_id": cell["cell_id"], "harness_id": cell["harness_id"], "model_id": cell["model_id"], "requested_model": cell["requested_model"],
            "attempt_count": cell["attempt_count"], "request_count": cell["request_count"], "report_count": cell["report_count"], "score_status": cell["score_status"],
            "evaluation_status": cell["evaluation_status"], "evaluation_reason": cell["evaluation_reason"],
            "citation_binding": metrics["citation_binding"]["score"], "gcp": metrics["gcp"]["score"], "grr": metrics["grr"]["score"],
            **{f"agent_{key}_tokens": value for key, value in cell["agent_tokens"].items()},
            "agent_cost_usd": cell["agent_cost"]["usd"], "agent_cost_status": cell["agent_cost"]["status"], "agent_cost_cny": cell["agent_cost"]["cny"], "cny_status": cell["agent_cost"]["cny_status"],
            **{f"judge_{key}_tokens": value for key, value in cell["judge_tokens"].items()},
            "judge_cost_usd": cell["judge_cost"]["usd"], "judge_cost_cny": cell["judge_cost"].get("cny"),
            "judge_known_cost_usd": cell["judge_cost"].get("known_usd_subtotal"),
            "judge_known_cost_cny": cell["judge_cost"].get("known_cny_subtotal"),
            "judge_unpriced_item_count": cell["judge_cost"].get("unpriced_item_count", 0),
            "judge_cost_status": cell["judge_cost"]["status"], "judge_cny_status": cell["judge_cost"].get("cny_status"),
        })
    cell_fields = list(cell_rows[0])
    write("pilot_cells.csv", cell_fields, cell_rows)
    request_rows = []
    for cell in summary["cells"]:
        for attempt in cell["attempts"]:
            for request in attempt["requests"]:
                request_rows.append({**{k: v for k, v in request.items() if k not in {"tokens", "cost"}}, **{f"{k}_tokens": v for k, v in request["tokens"].items()}, "cost_usd": request["cost"]["usd"], "cost_status": request["cost"]["status"], "rate_card_id": request["cost"].get("rate_card_id"), "cost_cny": request["cost"]["cny"], "cny_status": request["cost"]["cny_status"]})
    request_fields = ["run_id", "cell_id", "cell_attempt_index", "cell_retry_index", "gateway_request_index", "event_id", "bracket_run_id", "requested_model", "caller_requested_model", "expected_actual_identity", "actual_model_identity", "identity_match", "http_status", "transport_error_type", "latency_ms", "service_tier", "usage_observed", *[f"{k}_tokens" for k in TOKEN_KEYS], "cost_usd", "cost_status", "rate_card_id", "cost_cny", "cny_status", "response_body_sha256"]
    write("pilot_requests.csv", request_fields, request_rows)
    attempt_rows = []
    for cell in summary["cells"]:
        for attempt in cell["attempts"]:
            report = attempt["report"]
            attempt_rows.append({
                "run_id": attempt["run_id"], "cell_id": attempt["cell_id"],
                "attempt_index": attempt["attempt_index"], "retry_index": attempt["retry_index"],
                "status": attempt["status"], "reason": attempt["reason"], "exit_code": attempt["exit_code"],
                "attempt_path": attempt["path"], "request_count": attempt["request_count"],
                "score_run_count": len(attempt["scores"]), "report_status": report["report_status"],
                "report_relation": report["attempt_relation"], "report_bytes": report.get("bytes"),
                "report_sha256": report.get("sha256"),
                **{f"agent_{key}_tokens": value for key, value in attempt["agent_tokens"].items()},
                "agent_cost_usd": attempt["agent_cost"].get("usd"),
                "agent_cost_cny": attempt["agent_cost"].get("cny"),
                "agent_cost_status": attempt["agent_cost"].get("status"),
            })
    attempt_fields = list(attempt_rows[0])
    write("pilot_attempts.csv", attempt_fields, attempt_rows)
    score_rows = []
    for cell in summary["cells"]:
        for score in cell["score_runs"]:
            metrics = score["metrics"]
            failure = score.get("failure_status")
            row = {
                **score["association"], "score_dir": score["score_dir"],
                "failure_status": json.dumps(failure, sort_keys=True) if failure else None,
                "citation_binding": metrics["citation_binding"]["score"],
                "citation_binding_numerator": metrics["citation_binding"]["numerator"],
                "citation_binding_denominator": metrics["citation_binding"]["denominator"],
                "gcp": metrics["gcp"]["score"], "gcp_numerator": metrics["gcp"]["numerator"],
                "gcp_denominator": metrics["gcp"]["denominator"],
                "grr": metrics["grr"]["score"], "grr_numerator": metrics["grr"]["numerator"],
                "grr_denominator": metrics["grr"]["denominator"],
                "judge_request_count": len(score["judge_calls"]),
                **{f"judge_{key}_tokens": value for key, value in score["judge_tokens"].items()},
                "judge_cost_usd": score["judge_cost"].get("usd"),
                "judge_cost_cny": score["judge_cost"].get("cny"),
                "judge_known_cost_usd": score["judge_cost"].get("known_usd_subtotal"),
                "judge_known_cost_cny": score["judge_cost"].get("known_cny_subtotal"),
                "judge_unpriced_item_count": score["judge_cost"].get("unpriced_item_count", 0),
                "judge_cost_status": score["judge_cost"]["status"],
                "judge_cny_status": score["judge_cost"].get("cny_status"),
            }
            score_rows.append(row)
    score_fields = list(score_rows[0]) if score_rows else ["run_id", "cell_id", "attempt_index", "score_dir"]
    write("pilot_scores.csv", score_fields, score_rows)
    diagnostic_rows = []
    for row in summary["diagnostics"]:
        diagnostic_rows.append({
            **{k: row.get(k) for k in ("diagnostic_type", "request_index", "variant", "requested_model", "actual_model_identity", "identity_match", "http_status", "latency_ms")},
            **{f"{key}_tokens": value for key, value in row["tokens"].items()},
            "cost_usd": row["cost"]["usd"], "cost_cny": row["cost"]["cny"], "cost_status": row["cost"]["status"],
            "receipt_path": row["receipt"].get("path"), "receipt_sha256": row["receipt"].get("sha256"),
        })
    diagnostic_fields = ["diagnostic_type", "request_index", "variant", "requested_model", "actual_model_identity", "identity_match", "http_status", "latency_ms", *[f"{key}_tokens" for key in TOKEN_KEYS], "cost_usd", "cost_cny", "cost_status", "receipt_path", "receipt_sha256"]
    write("pilot_diagnostics.csv", diagnostic_fields, diagnostic_rows)


def write_outputs(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "pilot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_csvs(summary, output_dir)
    files = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file():
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    (output_dir / "SHA256SUMS.json").write_text(json.dumps({"schema_version": "pilot_output_seal_v1", "files": files}, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, action="append", required=True, help="Repeat for each local/synced matrix run directory")
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--score-dir", type=Path, action="append", default=[], help="Scorer output whose association is embedded in its receipts")
    parser.add_argument("--score-map", action="append", default=[], help="RUN_ID:CELL_ID:ATTEMPT=/path/to/scorer-output")
    parser.add_argument("--diagnostic-probe", type=Path, action="append", default=[], help="Auditable GPT-route or Judge-control probe receipt")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    pricing = Pricing(args.pricing)
    scores = score_map(args.score_map, args.score_dir, pricing)
    diagnostics = diagnostic_records(args.diagnostic_probe, pricing)
    summary = build_summary(args.run_dir, pricing, scores, args.manifest, diagnostics)
    write_outputs(summary, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "runs": summary["totals"]["run_count"], "cells": 5, "requests": summary["totals"]["request_count"], "reports": summary["totals"]["report_count"], "scored_cells": summary["totals"]["scored_cell_count"], "agent_cost_usd": summary["totals"]["agent_cost"]["usd"], "cny_status": summary["totals"]["cny_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
