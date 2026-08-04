#!/usr/bin/env python3
"""Profile audited Qwen judge calls without changing scorer semantics."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable


AUDITED_CALL_SCHEMA = "dra_audited_judge_call_v1"


@dataclass(frozen=True)
class CallRecord:
    harness: str
    stage_group: str
    stage: str
    cache_hit: bool
    error: str | None
    timestamp: datetime | None
    input_chars: int
    output_chars: int


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _identity(metadata_path: Path, root: Path, stage: str) -> tuple[str, str]:
    relative = metadata_path.relative_to(root)
    harness = relative.parts[0] if len(relative.parts) > 1 else "run"
    try:
        judge_calls_index = relative.parts.index("judge_calls")
    except ValueError:
        judge_calls_index = -1
    if judge_calls_index >= 0 and judge_calls_index + 1 < len(relative.parts):
        stage_group = relative.parts[judge_calls_index + 1]
    else:
        stage_group = stage.split("-", 1)[0] if stage else "unknown"
    return harness, stage_group


def read_call_records(root: Path) -> tuple[list[CallRecord], list[str]]:
    records: list[CallRecord] = []
    warnings: list[str] = []
    for metadata_path in sorted(root.rglob("metadata.json")):
        metadata = _read_json(metadata_path)
        if metadata is None or metadata.get("schema") != AUDITED_CALL_SCHEMA:
            continue
        call_dir = metadata_path.parent
        request = _read_json(call_dir / "request.json") or {}
        try:
            raw_response = (call_dir / "raw-response.txt").read_text(
                encoding="utf-8"
            )
        except OSError:
            raw_response = ""
            warnings.append(f"missing raw response: {call_dir}")
        stage = str(metadata.get("stage") or "")
        harness, stage_group = _identity(metadata_path, root, stage)
        system = str(request.get("system") or "")
        user = str(request.get("user") or "")
        records.append(
            CallRecord(
                harness=harness,
                stage_group=stage_group,
                stage=stage,
                cache_hit=bool(metadata.get("cache_hit")),
                error=str(metadata["error"]) if metadata.get("error") else None,
                timestamp=_parse_timestamp(metadata.get("timestamp_utc")),
                input_chars=len(system) + len(user),
                output_chars=len(raw_response),
            )
        )
    return records, warnings


def _empty_bucket() -> dict[str, int]:
    return {
        "logical_calls": 0,
        "fresh_calls": 0,
        "cache_hits": 0,
        "errors": 0,
        "logical_input_chars": 0,
        "fresh_input_chars": 0,
        "logical_output_chars": 0,
        "fresh_output_chars": 0,
    }


def _add_record(bucket: dict[str, int], record: CallRecord) -> None:
    bucket["logical_calls"] += 1
    bucket["logical_input_chars"] += record.input_chars
    bucket["logical_output_chars"] += record.output_chars
    if record.cache_hit:
        bucket["cache_hits"] += 1
    else:
        bucket["fresh_calls"] += 1
        bucket["fresh_input_chars"] += record.input_chars
        bucket["fresh_output_chars"] += record.output_chars
    if record.error:
        bucket["errors"] += 1


def _directory_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def build_profile(
    root: Path, records: Iterable[CallRecord], warnings: Iterable[str]
) -> dict[str, Any]:
    rows = list(records)
    overall = _empty_bucket()
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    harnesses: set[str] = set()
    for record in rows:
        harnesses.add(record.harness)
        _add_record(overall, record)
        bucket = grouped.setdefault(
            (record.harness, record.stage_group), _empty_bucket()
        )
        _add_record(bucket, record)

    fresh_times = sorted(
        record.timestamp
        for record in rows
        if not record.cache_hit and record.timestamp is not None
    )
    elapsed_seconds = (
        (fresh_times[-1] - fresh_times[0]).total_seconds()
        if len(fresh_times) >= 2
        else 0.0
    )
    mean_spacing = (
        elapsed_seconds / (len(fresh_times) - 1)
        if len(fresh_times) >= 2
        else None
    )
    harness_count = len(harnesses)
    logical_calls = overall["logical_calls"]
    fresh_calls = overall["fresh_calls"]
    profile_rows = [
        {
            "harness": harness,
            "stage_group": stage_group,
            **values,
        }
        for (harness, stage_group), values in sorted(grouped.items())
    ]
    return {
        "schema": "dra_qwen_judge_run_profile_v1",
        "measurement_kind": "historical_replay_profile_not_cold_run",
        "run_root": str(root.resolve()),
        "audited_call_schema": AUDITED_CALL_SCHEMA,
        "harness_count": harness_count,
        "directory_bytes": _directory_bytes(root),
        "overall": {
            **overall,
            "cache_hit_rate": (
                overall["cache_hits"] / logical_calls if logical_calls else 0.0
            ),
            "logical_calls_per_harness": (
                logical_calls / harness_count if harness_count else None
            ),
            "fresh_calls_per_harness": (
                fresh_calls / harness_count if harness_count else None
            ),
            "fresh_timestamp_min": (
                fresh_times[0].isoformat() if fresh_times else None
            ),
            "fresh_timestamp_max": (
                fresh_times[-1].isoformat() if fresh_times else None
            ),
            "fresh_window_seconds": elapsed_seconds,
            "fresh_mean_spacing_seconds": mean_spacing,
        },
        "by_harness_and_stage": profile_rows,
        "limitations": [
            "This profile includes historical cache reuse and is not a cold run.",
            "Request transcripts do not currently retain provider token usage; "
            "character counts are reported as a proxy.",
            "Fresh timestamp span is elapsed replay time, not isolated GPU "
            "service time.",
        ],
        "warnings": sorted(set(warnings)),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "harness",
        "stage_group",
        "logical_calls",
        "fresh_calls",
        "cache_hits",
        "errors",
        "logical_input_chars",
        "fresh_input_chars",
        "logical_output_chars",
        "fresh_output_chars",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Profile immutable audited-judge artifacts."
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()

    root = args.run_root.resolve()
    if not root.is_dir():
        parser.error(f"run root is not a directory: {root}")
    records, warnings = read_call_records(root)
    if not records:
        parser.error(f"no {AUDITED_CALL_SCHEMA} metadata found below {root}")
    profile = build_profile(root, records, warnings)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(args.out_csv, profile["by_harness_and_stage"])
    print(
        json.dumps(
            {
                "logical_calls": profile["overall"]["logical_calls"],
                "fresh_calls": profile["overall"]["fresh_calls"],
                "cache_hits": profile["overall"]["cache_hits"],
                "harness_count": profile["harness_count"],
                "out_json": str(args.out_json.resolve()),
                "out_csv": str(args.out_csv.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
