"""Build a blinded human-calibration queue from two controlled judge runs."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Callable, Hashable

from src.scoring.judge_comparison import compare_judge_runs
from src.scoring.task_evaluation_contract import (
    canonical_json_sha256,
    file_sha256,
)


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )


def _row_map(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], Hashable],
) -> dict[Hashable, dict[str, Any]]:
    mapped: dict[Hashable, dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row)
        if key in mapped:
            raise ValueError(f"duplicate calibration item: {key!r}")
        mapped[key] = row
    return mapped


def _select_agreements(
    agreement_keys_by_label: dict[Hashable, list[Hashable]],
    *,
    limit: int,
    rng: random.Random,
) -> list[Hashable]:
    groups = {
        label: list(keys)
        for label, keys in sorted(
            agreement_keys_by_label.items(),
            key=lambda pair: str(pair[0]),
        )
    }
    for keys in groups.values():
        rng.shuffle(keys)
    selected: list[Hashable] = []
    labels = list(groups)
    while len(selected) < limit and labels:
        next_labels: list[Hashable] = []
        for label in labels:
            if groups[label] and len(selected) < limit:
                selected.append(groups[label].pop())
            if groups[label]:
                next_labels.append(label)
        labels = next_labels
    return selected


def _blind_payload(
    axis: str,
    row: dict[str, Any],
    *,
    run_dir: Path,
) -> dict[str, Any]:
    if axis == "fact":
        claim_id = str(row["claim_id"])
        packet_path = run_dir / "fact_packets" / f"{claim_id}.json"
        packet = _read_json(packet_path) if packet_path.is_file() else None
        return {
            "claim_id": claim_id,
            "normalized_claim": row.get("normalized_claim"),
            "fact_packet": packet,
        }
    if axis == "evidence":
        return {
            key: row.get(key)
            for key in (
                "claim_id",
                "occurrence_index",
                "citation_id",
                "claim",
                "claim_kind",
                "claim_raw_text",
                "local_report_context",
                "url",
                "canonical_url",
                "source_title",
                "source_role",
                "observed",
                "observation_tier",
                "observed_text",
                "complete_scope_observed",
                "valid",
            )
        }
    if axis == "completeness":
        return {
            key: row.get(key)
            for key in (
                "unit_id",
                "statement",
                "facet_id",
                "unit_type",
                "importance",
                "applicable",
                "evidence_required",
            )
        }
    if axis == "rubric":
        return {
            key: row.get(key)
            for key in (
                "rubric_id",
                "query_span",
                "requirement",
                "requirement_type",
                "importance",
                "applicable",
            )
        }
    raise ValueError(f"unknown calibration axis: {axis}")


def _annotation_choices(axis: str) -> list[str]:
    return {
        "fact": [
            "true",
            "false",
            "conflicted",
            "unresolved",
            "out_of_world",
            "instrument_ambiguous",
        ],
        "evidence": ["passed", "failed"],
        "completeness": ["covered", "not_covered"],
        "rubric": [
            "fulfilled",
            "partially_fulfilled",
            "not_fulfilled",
            "ambiguous",
        ],
    }[axis]


def build_calibration_queue(
    run_a: Path,
    run_b: Path,
    output_dir: Path,
    *,
    agreement_sample_per_axis: int = 20,
    seed: int = 20260728,
) -> dict[str, Any]:
    """Export all disagreements plus a stratified matched agreement sample."""

    run_a = Path(run_a)
    run_b = Path(run_b)
    output_dir = Path(output_dir)
    comparison = compare_judge_runs(run_a, run_b)
    if not comparison["controlled_comparison"]:
        raise ValueError(
            "calibration queue requires a controlled comparison: "
            + json.dumps(
                comparison["control_failures"],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    input_a = _read_json(run_a / "input-manifest.json")
    input_b = _read_json(run_b / "input-manifest.json")
    report_path_a = Path(input_a["inputs"]["report"]["path"])
    report_path_b = Path(input_b["inputs"]["report"]["path"])
    report_a = report_path_a.read_text(encoding="utf-8")
    report_b = report_path_b.read_text(encoding="utf-8")
    if report_a != report_b:
        raise ValueError("controlled runs reference different report bytes")
    task_path = Path(input_a["inputs"]["task"]["path"])
    task = _read_json(task_path)
    (output_dir / "report.md").parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.md").write_text(report_a, encoding="utf-8")
    _write_json(output_dir / "task.json", task)

    specs = {
        "fact": (
            "fact_verdicts.jsonl",
            lambda row: str(row.get("claim_id")),
            lambda row: str(row.get("verdict")),
        ),
        "evidence": (
            "citation_bindings.jsonl",
            lambda row: (
                str(row.get("claim_id")),
                int(row.get("occurrence_index", 0)),
                str(row.get("citation_id")),
            ),
            lambda row: "passed" if bool(row.get("passed")) else "failed",
        ),
        "completeness": (
            "completeness_units.jsonl",
            lambda row: str(row.get("unit_id")),
            lambda row: (
                "covered"
                if bool(row.get("content_covered"))
                else "not_covered"
            ),
        ),
        "rubric": (
            "rubric_verdicts.jsonl",
            lambda row: str(row.get("rubric_id")),
            lambda row: str(row.get("verdict")),
        ),
    }
    rng = random.Random(seed)
    blind_items: list[dict[str, Any]] = []
    private_labels: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for axis, (filename, key_fn, label_fn) in specs.items():
        map_a = _row_map(_read_jsonl(run_a / filename), key_fn)
        map_b = _row_map(_read_jsonl(run_b / filename), key_fn)
        if set(map_a) != set(map_b):
            raise ValueError(f"{axis} item sets differ despite controlled flag")
        disagreements: list[Hashable] = []
        agreement_groups: dict[Hashable, list[Hashable]] = defaultdict(list)
        for key in sorted(map_a, key=str):
            label_a = label_fn(map_a[key])
            label_b = label_fn(map_b[key])
            if label_a != label_b:
                disagreements.append(key)
            else:
                agreement_groups[label_a].append(key)
        sampled_agreements = _select_agreements(
            agreement_groups,
            limit=agreement_sample_per_axis,
            rng=rng,
        )
        chosen = [
            ("judge_disagreement", key) for key in disagreements
        ] + [
            ("matched_agreement_sample", key) for key in sampled_agreements
        ]
        for selection_reason, key in chosen:
            item_id = (
                f"cal_{axis}_"
                + hashlib.sha256(
                    json.dumps(
                        key,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8")
                ).hexdigest()[:12]
            )
            blind_items.append(
                {
                    "schema": "dra_human_calibration_item_v1",
                    "item_id": item_id,
                    "axis": axis,
                    "selection_reason": selection_reason,
                    "task_id": task.get("task_id"),
                    "report_file": "report.md",
                    "task_file": "task.json",
                    "payload": _blind_payload(
                        axis,
                        map_a[key],
                        run_dir=run_a,
                    ),
                    "allowed_labels": _annotation_choices(axis),
                    "human_annotation": {
                        "annotator_id": None,
                        "label": None,
                        "confidence": None,
                        "exact_quotes_or_span_ids": [],
                        "reason": None,
                    },
                }
            )
            private_labels.append(
                {
                    "item_id": item_id,
                    "axis": axis,
                    "selection_reason": selection_reason,
                    "item_key": key,
                    "judge_a_label": label_fn(map_a[key]),
                    "judge_b_label": label_fn(map_b[key]),
                }
            )
        counts[axis] = {
            "all_items": len(map_a),
            "judge_disagreements": len(disagreements),
            "sampled_agreements": len(sampled_agreements),
            "annotation_items": len(chosen),
        }

    blind_items.sort(key=lambda row: (row["axis"], row["item_id"]))
    private_labels.sort(key=lambda row: (row["axis"], row["item_id"]))
    _write_jsonl(output_dir / "annotation-items.blind.jsonl", blind_items)
    _write_jsonl(output_dir / "judge-labels.private.jsonl", private_labels)
    manifest_identity = {
        "schema": "dra_human_calibration_queue_v1",
        "comparison_instruments": comparison["instrument_a"],
        "run_a": str(run_a.resolve()),
        "run_b": str(run_b.resolve()),
        "seed": seed,
        "agreement_sample_per_axis": agreement_sample_per_axis,
        "counts": counts,
        "annotation_items_sha256": file_sha256(
            output_dir / "annotation-items.blind.jsonl"
        ),
        "private_labels_sha256": file_sha256(
            output_dir / "judge-labels.private.jsonl"
        ),
        "report_sha256": file_sha256(output_dir / "report.md"),
        "task_sha256": file_sha256(output_dir / "task.json"),
    }
    manifest = {
        **manifest_identity,
        "queue_sha256": canonical_json_sha256(manifest_identity),
        "blinding_contract": (
            "annotators receive annotation-items.blind.jsonl, report.md, and "
            "task.json; judge-labels.private.jsonl remains hidden until both "
            "independent annotations are frozen"
        ),
    }
    _write_json(output_dir / "queue-manifest.json", manifest)
    return manifest


__all__ = ["build_calibration_queue"]
