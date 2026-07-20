#!/usr/bin/env python3
"""Issue an explicit E1 resource projection and current-host feasibility gate."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def monotonic(values: list[float]) -> bool:
    return all(right >= left for left, right in zip(values, values[1:]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--baseline-build", type=Path)
    parser.add_argument("--available-disk-bytes", type=int, required=True)
    parser.add_argument("--total-memory-bytes", type=int, required=True)
    parser.add_argument("--max-runtime-hours", type=float, default=168.0)
    parser.add_argument("--disk-usable-fraction", type=float, default=0.80)
    parser.add_argument("--memory-usable-fraction", type=float, default=0.80)
    parser.add_argument("--disk-uncertainty-factor", type=float, default=1.25)
    parser.add_argument("--runtime-uncertainty-factor", type=float, default=1.50)
    parser.add_argument("--memory-uncertainty-factor", type=float, default=2.0)
    parser.add_argument("--min-ingest-checkpoints", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for name in (
        "disk_usable_fraction",
        "memory_usable_fraction",
    ):
        value = getattr(args, name)
        if not 0 < value <= 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be in (0,1]")
    for name in (
        "disk_uncertainty_factor",
        "runtime_uncertainty_factor",
        "memory_uncertainty_factor",
    ):
        if getattr(args, name) < 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be >= 1")

    source_dir = args.source_dir.resolve()
    candidate_build = args.candidate_build.resolve()
    source = load(source_dir / "source-manifest.json")
    build = load(candidate_build / "build-manifest.json")
    resource = load(candidate_build / "resource-report.json")
    quality = load(candidate_build / "quality-report.json")
    selection_rate = float(source["selection"]["selection_rate"])
    if not 0 < selection_rate <= 1:
        raise SystemExit("invalid source selection_rate")
    expansion_factor = 1.0 / selection_rate
    population = sum(int(pack["population"]) for pack in source["packs"])
    selected = sum(
        int(pack["selected"]) - int(pack.get("errors") or 0)
        for pack in source["packs"]
    )
    curve = resource.get("curve") or []
    ingest = [
        point for point in curve
        if "ingest" in str(point.get("stage") or "")
    ]
    attempted_curve = [
        float(point["records_attempted"]) for point in ingest
    ]
    elapsed_curve = [float(point["elapsed_seconds"]) for point in ingest]
    disk_curve = [
        float(point["sqlite_allocated_bytes"]) for point in ingest
    ]
    observed_sqlite = int(resource["sqlite_bytes"])
    observed_elapsed = float(resource["elapsed_seconds"])
    observed_rss = int(resource["peak_rss_kib"]) * 1024
    point_disk = observed_sqlite * expansion_factor
    upper_disk = point_disk * args.disk_uncertainty_factor
    point_runtime_seconds = observed_elapsed * expansion_factor
    upper_runtime_seconds = (
        point_runtime_seconds * args.runtime_uncertainty_factor
    )
    upper_rss = observed_rss * args.memory_uncertainty_factor
    disk_budget = args.available_disk_bytes * args.disk_usable_fraction
    memory_budget = args.total_memory_bytes * args.memory_usable_fraction

    checks = {
        "source_is_formal_task_blind": (
            source.get("formal_eligible") is True
            and source.get("task_conditioned") is False
            and source.get("task_or_witness_inputs") == []
        ),
        "source_and_candidate_identity_match": (
            build.get("source_manifest_id") == source.get("source_manifest_id")
        ),
        "candidate_compiled_entire_shard": (
            int(resource["records_attempted"]) == selected
            and int(resource["records_compiled"]) == selected
            and int(resource["records_failed"]) == 0
            and build.get("engineering_cap_per_pack") is None
        ),
        "candidate_build_quality_gates_pass": (
            build.get("source_and_build_gates_pass") is True
            and all(
                value is True or key == "bm25_top20_observed_rate"
                for key, value in quality.get("gates", {}).items()
            )
        ),
        "enough_ingest_checkpoints": (
            len(ingest) >= args.min_ingest_checkpoints
        ),
        "checkpoint_records_monotonic": monotonic(attempted_curve),
        "checkpoint_elapsed_monotonic": monotonic(elapsed_curve),
        "checkpoint_allocated_bytes_monotonic": monotonic(disk_curve),
        "post_finalize_checkpoint_present": any(
            "post_finalize" in str(point.get("stage") or "")
            for point in curve
        ),
        "full_projection_fits_disk_budget": upper_disk <= disk_budget,
        "full_projection_fits_memory_budget": upper_rss <= memory_budget,
        "full_projection_fits_runtime_budget": (
            upper_runtime_seconds <= args.max_runtime_hours * 3600
        ),
    }
    baseline: dict[str, Any] | None = None
    if args.baseline_build:
        baseline_dir = args.baseline_build.resolve()
        baseline_resource = load(baseline_dir / "resource-report.json")
        baseline_bytes = int(baseline_resource["sqlite_bytes"])
        baseline = {
            "build": str(baseline_dir),
            "observed_sqlite_bytes": baseline_bytes,
            "projected_full_sqlite_bytes": (
                baseline_bytes * expansion_factor
            ),
            "candidate_to_baseline_size_ratio": (
                observed_sqlite / baseline_bytes if baseline_bytes else None
            ),
        }

    formal_gate_passed = all(checks.values())
    report = {
        "schema": "dra_e1_resource_projection_report_v1",
        "auditor_sha256": file_sha256(Path(__file__).resolve()),
        "source_dir": str(source_dir),
        "candidate_build": str(candidate_build),
        "source_manifest_id": source["source_manifest_id"],
        "logical_build_id": build["logical_build_id"],
        "selection": {
            "population_documents": population,
            "selected_documents": selected,
            "selection_rate": selection_rate,
            "horvitz_thompson_expansion_factor": expansion_factor,
        },
        "observed": {
            "sqlite_bytes": observed_sqlite,
            "elapsed_seconds": observed_elapsed,
            "peak_rss_bytes": observed_rss,
            "ingest_checkpoints": len(ingest),
        },
        "projection": {
            "execution_contract": (
                "single direct-stream full build; raw ZIM/database snapshots "
                "remain canonical inputs; no full JSONL staging copy"
            ),
            "point_sqlite_bytes": point_disk,
            "upper_sqlite_bytes": upper_disk,
            "point_runtime_hours": point_runtime_seconds / 3600,
            "upper_runtime_hours": upper_runtime_seconds / 3600,
            "upper_peak_rss_bytes": upper_rss,
            "disk_uncertainty_factor": args.disk_uncertainty_factor,
            "runtime_uncertainty_factor": args.runtime_uncertainty_factor,
            "memory_uncertainty_factor": args.memory_uncertainty_factor,
            "note": (
                "The stable hash shard is a Bernoulli document sample. The "
                "point projection uses inverse inclusion probability; explicit "
                "multipliers are operational safety margins, not confidence "
                "intervals. Full-build measurements supersede this projection."
            ),
        },
        "host_budget": {
            "available_disk_bytes": args.available_disk_bytes,
            "disk_usable_fraction": args.disk_usable_fraction,
            "disk_budget_bytes": disk_budget,
            "total_memory_bytes": args.total_memory_bytes,
            "memory_usable_fraction": args.memory_usable_fraction,
            "memory_budget_bytes": memory_budget,
            "max_runtime_hours": args.max_runtime_hours,
        },
        "baseline": baseline,
        "checks": checks,
        "formal_gate_passed": formal_gate_passed,
        "rounded_summary": {
            "projected_upper_disk_gib": round(
                upper_disk / (1024 ** 3), 2
            ),
            "disk_budget_gib": round(disk_budget / (1024 ** 3), 2),
            "projected_upper_runtime_hours": round(
                upper_runtime_seconds / 3600, 2
            ),
            "projected_upper_peak_rss_gib": round(
                upper_rss / (1024 ** 3), 2
            ),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if formal_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
