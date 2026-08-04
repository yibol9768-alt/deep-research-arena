"""Controlled, item-level comparison of two DRA semantic judges."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Callable, Hashable


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not Path(path).is_file():
        return rows
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cohen_kappa(labels_a: list[Hashable], labels_b: list[Hashable]) -> float | None:
    """Return unweighted Cohen's kappa, or None when it is undefined."""

    if len(labels_a) != len(labels_b):
        raise ValueError("label sequences must have equal length")
    if not labels_a:
        return None
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a)
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    labels = set(counts_a) | set(counts_b)
    expected = sum(
        (counts_a[label] / len(labels_a))
        * (counts_b[label] / len(labels_b))
        for label in labels
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else None
    return (observed - expected) / (1.0 - expected)


def _map_rows(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], Hashable],
) -> dict[Hashable, dict[str, Any]]:
    mapped: dict[Hashable, dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row)
        if key in mapped:
            raise ValueError(f"duplicate judgment item key: {key!r}")
        mapped[key] = row
    return mapped


def _axis_comparison(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    key_fn: Callable[[dict[str, Any]], Hashable],
    label_fn: Callable[[dict[str, Any]], Hashable],
    example_fields: tuple[str, ...],
) -> dict[str, Any]:
    map_a = _map_rows(rows_a, key_fn)
    map_b = _map_rows(rows_b, key_fn)
    keys_a = set(map_a)
    keys_b = set(map_b)
    shared = sorted(keys_a & keys_b, key=str)
    labels_a = [label_fn(map_a[key]) for key in shared]
    labels_b = [label_fn(map_b[key]) for key in shared]
    agreements = sum(a == b for a, b in zip(labels_a, labels_b))
    union = keys_a | keys_b
    examples: list[dict[str, Any]] = []
    for key, label_a, label_b in zip(shared, labels_a, labels_b):
        if label_a == label_b:
            continue
        source = map_a[key]
        example = {
            "item_key": key,
            "judge_a": label_a,
            "judge_b": label_b,
        }
        for field in example_fields:
            if source.get(field) is not None:
                example[field] = source.get(field)
        examples.append(example)
        if len(examples) >= 8:
            break
    return {
        "judge_a_item_count": len(keys_a),
        "judge_b_item_count": len(keys_b),
        "shared_item_count": len(shared),
        "same_item_set": keys_a == keys_b,
        "item_set_jaccard": (
            len(keys_a & keys_b) / len(union) if union else 1.0
        ),
        "raw_agreement": agreements / len(shared) if shared else None,
        "cohen_kappa": cohen_kappa(labels_a, labels_b),
        "disagreement_count": len(shared) - agreements,
        "judge_a_only": sorted(keys_a - keys_b, key=str)[:20],
        "judge_b_only": sorted(keys_b - keys_a, key=str)[:20],
        "disagreement_examples": examples,
    }


def _input_hashes(manifest: dict[str, Any]) -> dict[str, str | None]:
    inputs = manifest.get("inputs") or {}
    return {
        name: (inputs.get(name) or {}).get("sha256")
        for name in (
            "task",
            "report",
            "trace",
            "citation_map",
            "task_world_model",
            "research_test_suite",
            "graph_manifest",
            "url_registry",
        )
    }


def _instrument_hashes(
    score: dict[str, Any],
    input_manifest: dict[str, Any],
) -> dict[str, Any]:
    frozen = input_manifest.get("frozen_artifacts") or {}
    return {
        "scoring_protocol_sha256": (
            input_manifest.get("scoring_protocol") or {}
        ).get("protocol_sha256"),
        "task_contract_sha256": score.get("task_contract_sha256")
        or (frozen.get("task_contract") or {}).get("contract_sha256"),
        "claim_ledger_sha256": score.get("claim_ledger_sha256")
        or (frozen.get("claim_ledger") or {}).get("claim_ledger_sha256"),
        "fact_packet_bundle_sha256": score.get("fact_packet_bundle_sha256")
        or (frozen.get("fact_packets") or {}).get(
            "fact_packet_bundle_sha256"
        ),
        "input_hashes": _input_hashes(input_manifest),
    }


def compare_judge_runs(run_a: Path, run_b: Path) -> dict[str, Any]:
    """Compare two completed runs and certify whether inputs were controlled."""

    run_a = Path(run_a)
    run_b = Path(run_b)
    score_a = _read_json(run_a / "score.json")
    score_b = _read_json(run_b / "score.json")
    inputs_a = _read_json(run_a / "input-manifest.json")
    inputs_b = _read_json(run_b / "input-manifest.json")
    instrument_a = _instrument_hashes(score_a, inputs_a)
    instrument_b = _instrument_hashes(score_b, inputs_b)
    required_frozen = (
        "scoring_protocol_sha256",
        "task_contract_sha256",
        "claim_ledger_sha256",
        "fact_packet_bundle_sha256",
    )
    missing = [
        name
        for name in required_frozen
        if not instrument_a.get(name) or not instrument_b.get(name)
    ]
    mismatched = [
        name
        for name in required_frozen
        if instrument_a.get(name) != instrument_b.get(name)
    ]
    input_mismatches = [
        name
        for name, digest in instrument_a["input_hashes"].items()
        if digest != instrument_b["input_hashes"].get(name)
    ]
    controlled = not missing and not mismatched and not input_mismatches

    axes = {
        "fact": _axis_comparison(
            _read_jsonl(run_a / "fact_verdicts.jsonl"),
            _read_jsonl(run_b / "fact_verdicts.jsonl"),
            key_fn=lambda row: str(row.get("claim_id")),
            label_fn=lambda row: str(row.get("verdict")),
            example_fields=("normalized_claim", "reason_code"),
        ),
        "evidence": _axis_comparison(
            _read_jsonl(run_a / "citation_bindings.jsonl"),
            _read_jsonl(run_b / "citation_bindings.jsonl"),
            key_fn=lambda row: (
                str(row.get("claim_id")),
                int(row.get("occurrence_index", 0)),
                str(row.get("citation_id")),
            ),
            label_fn=lambda row: bool(row.get("passed")),
            example_fields=("claim", "nearby_claim", "failure_reasons"),
        ),
        "completeness": _axis_comparison(
            _read_jsonl(run_a / "completeness_units.jsonl"),
            _read_jsonl(run_b / "completeness_units.jsonl"),
            key_fn=lambda row: str(row.get("unit_id")),
            label_fn=lambda row: bool(row.get("content_covered")),
            example_fields=("statement", "facet_id", "unit_type"),
        ),
        "rubric": _axis_comparison(
            _read_jsonl(run_a / "rubric_verdicts.jsonl"),
            _read_jsonl(run_b / "rubric_verdicts.jsonl"),
            key_fn=lambda row: str(row.get("rubric_id")),
            label_fn=lambda row: str(row.get("verdict")),
            example_fields=("requirement", "reason_code"),
        ),
    }
    return {
        "schema": "dra_controlled_judge_comparison_v1",
        "run_a": str(run_a.resolve()),
        "run_b": str(run_b.resolve()),
        "judge_a_models": score_a.get("models"),
        "judge_b_models": score_b.get("models"),
        "controlled_comparison": controlled,
        "control_failures": {
            "missing_frozen_hashes": missing,
            "mismatched_frozen_hashes": mismatched,
            "mismatched_input_hashes": input_mismatches,
        },
        "instrument_a": instrument_a,
        "instrument_b": instrument_b,
        "axis_scores": {
            axis: {
                "judge_a": score_a.get(axis, {}).get("score"),
                "judge_b": score_b.get(axis, {}).get("score"),
                "delta_b_minus_a": (
                    score_b.get(axis, {}).get("score")
                    - score_a.get(axis, {}).get("score")
                    if score_a.get(axis, {}).get("score") is not None
                    and score_b.get(axis, {}).get("score") is not None
                    else None
                ),
            }
            for axis in ("fact", "evidence", "completeness", "rubric")
        },
        "truth": {
            "judge_a": score_a.get("truth"),
            "judge_b": score_b.get("truth"),
            "delta_b_minus_a": (
                score_b.get("truth") - score_a.get("truth")
                if score_a.get("truth") is not None
                and score_b.get("truth") is not None
                else None
            ),
        },
        "axes": axes,
        "interpretation": (
            "A similar total score never establishes judge equivalence. "
            "Equivalence requires identical frozen inputs plus item-level "
            "agreement and human-gold calibration on each axis."
        ),
    }


__all__ = ["cohen_kappa", "compare_judge_runs"]
