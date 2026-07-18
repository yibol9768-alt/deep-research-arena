#!/usr/bin/env python3
"""Fail closed on cross-task proof-source reuse and rejected-corpus replay."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


AUDIT_SCHEMA = "dra_v3_source_reuse_audit_v1"
TASK_ORDINAL_RE = re.compile(r"_(\d{4})$")
FORMAL_CANDIDATE_RE = re.compile(r"^cand_formal_(\d{4})(?:_|$)")
FORMAL_FIRST_ORDINAL = 15
EXACT_INSTANCE_SOURCE_TYPES = frozenset({"magento", "postmill"})
POSTMILL_SUBMISSION_RE = re.compile(r"^/f/[^/]+/(\d+)(?:/.*)?$")


class SourceReuseAuditError(ValueError):
    """Raised when audit inputs cannot define an unambiguous comparison."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceReuseAuditError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise SourceReuseAuditError(f"{label}: {path} must contain an object")
    return dict(value)


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceReuseAuditError(f"{label}: expected a non-empty string")
    return value.strip()


def _ordinal(task_id: str) -> int:
    match = TASK_ORDINAL_RE.search(task_id)
    if match is None:
        raise SourceReuseAuditError(
            f"task_id {task_id!r} does not end in a four-digit ordinal"
        )
    return int(match.group(1))


def _case_paths(case_dirs: Sequence[Path]) -> list[Path]:
    return sorted({path for root in case_dirs for path in root.rglob("*.json")})


def _critical_source_usage(case_dirs: Sequence[Path]) -> dict[str, list[dict[str, Any]]]:
    usage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_tasks: set[str] = set()
    for path in _case_paths(case_dirs):
        value = _load_object(path, "case")
        if value.get("task_version") != 3:
            continue
        task_id = _non_empty(value.get("task_id"), f"{path}.task_id")
        if task_id in seen_tasks:
            raise SourceReuseAuditError(f"duplicate v3 case task_id {task_id!r}")
        seen_tasks.add(task_id)
        cluster_id = _non_empty(value.get("cluster_id"), f"{path}.cluster_id")
        sources = value.get("evidence_sources")
        if not isinstance(sources, list) or not sources:
            raise SourceReuseAuditError(f"{path}.evidence_sources must be non-empty")
        for index, raw in enumerate(sources):
            if not isinstance(raw, Mapping):
                raise SourceReuseAuditError(
                    f"{path}.evidence_sources[{index}] must be an object"
                )
            source_url = _non_empty(
                raw.get("source_url"), f"{path}.evidence_sources[{index}].source_url"
            )
            usage[source_url].append(
                {
                    "task_id": task_id,
                    "ordinal": _ordinal(task_id),
                    "cluster_id": cluster_id,
                    "evidence_id": _non_empty(
                        raw.get("evidence_id"),
                        f"{path}.evidence_sources[{index}].evidence_id",
                    ),
                    "source_type": _non_empty(
                        raw.get("source_type"),
                        f"{path}.evidence_sources[{index}].source_type",
                    ),
                    "case_path": path.as_posix(),
                }
            )
    return usage


def _capture_plans(capture_plan_dir: Path) -> dict[str, dict[str, Any]]:
    plans: dict[str, dict[str, Any]] = {}
    for path in sorted(capture_plan_dir.glob("*.json")):
        value = _load_object(path, "capture plan")
        candidate_id = _non_empty(value.get("candidate_id"), f"{path}.candidate_id")
        metadata = value.get("metadata")
        if not isinstance(metadata, Mapping):
            raise SourceReuseAuditError(f"{path}.metadata must be an object")
        source_task_id = _non_empty(
            metadata.get("candidate_source_task_id"),
            f"{path}.metadata.candidate_source_task_id",
        )
        extracts = value.get("extracts")
        if not isinstance(extracts, list) or not extracts:
            raise SourceReuseAuditError(f"{path}.extracts must be non-empty")
        sources: dict[str, str] = {}
        for index, raw in enumerate(extracts):
            if not isinstance(raw, Mapping):
                raise SourceReuseAuditError(f"{path}.extracts[{index}] must be an object")
            url = _non_empty(raw.get("url"), f"{path}.extracts[{index}].url")
            source_type = _non_empty(
                raw.get("source_type"), f"{path}.extracts[{index}].source_type"
            )
            if url in sources:
                raise SourceReuseAuditError(f"{path}: duplicate extract URL {url!r}")
            sources[url] = source_type
        record = plans.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "source_task_id": source_task_id,
                "paths": [],
                "urls": set(),
                "source_types_by_url": {},
            },
        )
        if record["source_task_id"] != source_task_id:
            raise SourceReuseAuditError(
                f"candidate {candidate_id!r} maps to multiple source tasks"
            )
        record["paths"].append(path.as_posix())
        record["urls"].update(sources)
        for url, source_type in sources.items():
            previous_type = record["source_types_by_url"].get(url)
            if previous_type is not None and previous_type != source_type:
                raise SourceReuseAuditError(
                    f"candidate {candidate_id!r} assigns multiple source types "
                    f"to {url!r}: {previous_type!r}, {source_type!r}"
                )
            record["source_types_by_url"][url] = source_type
    for record in plans.values():
        record["paths"] = sorted(record["paths"])
        record["urls"] = sorted(record["urls"])
        record["source_types_by_url"] = dict(
            sorted(record["source_types_by_url"].items())
        )
    return plans


def _formal_candidate_ordinal(candidate_id: str) -> int | None:
    match = FORMAL_CANDIDATE_RE.match(candidate_id)
    return int(match.group(1)) if match is not None else None


def _exact_instance_identity(source_url: str, source_type: str) -> str:
    """Collapse harmless URL variants that still address the same product or post."""
    parsed = urlsplit(source_url)
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    if source_type == "postmill":
        match = POSTMILL_SUBMISSION_RE.fullmatch(path)
        if match is not None:
            return f"postmill://{netloc}/submission/{match.group(1)}"
    return f"{source_type}://{netloc}{path}"


def _rejected_candidates(corpus_audit_path: Path) -> list[dict[str, str]]:
    value = _load_object(corpus_audit_path, "corpus audit")
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        raise SourceReuseAuditError("corpus audit candidates must be an array")
    result: list[dict[str, str]] = []
    for index, raw in enumerate(candidates):
        if not isinstance(raw, Mapping):
            raise SourceReuseAuditError(
                f"corpus audit candidate[{index}] must be an object"
            )
        if raw.get("verdict") != "rejected":
            continue
        result.append(
            {
                "candidate_id": _non_empty(
                    raw.get("candidate_id"),
                    f"corpus audit candidate[{index}].candidate_id",
                ),
                "source_task_id": _non_empty(
                    raw.get("source_task_id"),
                    f"corpus audit candidate[{index}].source_task_id",
                ),
            }
        )
    return result


def audit_source_reuse(
    *,
    case_dirs: Sequence[Path],
    capture_plan_dir: Path,
    corpus_audit_path: Path,
    formal_first_ordinal: int = FORMAL_FIRST_ORDINAL,
) -> dict[str, Any]:
    if not case_dirs:
        raise SourceReuseAuditError("at least one case directory is required")
    if formal_first_ordinal < 1:
        raise SourceReuseAuditError("formal_first_ordinal must be positive")

    usage = _critical_source_usage(case_dirs)
    same_cluster_shared_sources: list[dict[str, Any]] = []
    cross_cluster_warnings: list[dict[str, Any]] = []
    cross_cluster_conflicts: list[dict[str, Any]] = []
    for source_url, raw_rows in sorted(usage.items()):
        rows = sorted(raw_rows, key=lambda row: (row["ordinal"], row["evidence_id"]))
        if len({row["task_id"] for row in rows}) < 2:
            continue
        clusters = sorted({row["cluster_id"] for row in rows})
        record = {
            "source_url": source_url,
            "source_types": sorted({row["source_type"] for row in rows}),
            "cluster_ids": clusters,
            "uses": rows,
        }
        if len(clusters) == 1:
            same_cluster_shared_sources.append(record)
            continue
        includes_formal = any(
            row["ordinal"] >= formal_first_ordinal for row in rows
        )
        exact_instance_source = any(
            row["source_type"] in EXACT_INSTANCE_SOURCE_TYPES for row in rows
        )
        if includes_formal and exact_instance_source:
            cross_cluster_conflicts.append(record)
        else:
            cross_cluster_warnings.append(record)

    plans = _capture_plans(capture_plan_dir)
    capture_instance_usage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    formal_candidate_ids = {
        candidate_id
        for candidate_id in plans
        if (_formal_candidate_ordinal(candidate_id) or 0) >= formal_first_ordinal
    }
    for candidate_id, plan in sorted(plans.items()):
        for source_url, source_type in plan["source_types_by_url"].items():
            if source_type not in EXACT_INSTANCE_SOURCE_TYPES:
                continue
            source_identity = _exact_instance_identity(source_url, source_type)
            capture_instance_usage[source_identity].append(
                {
                    "candidate_id": candidate_id,
                    "source_task_id": plan["source_task_id"],
                    "source_type": source_type,
                    "source_url": source_url,
                    "capture_plans": plan["paths"],
                    "formal_candidate": candidate_id in formal_candidate_ids,
                }
            )
    capture_plan_exact_instance_conflicts: list[dict[str, Any]] = []
    for source_identity, rows in sorted(capture_instance_usage.items()):
        if len({row["candidate_id"] for row in rows}) < 2:
            continue
        if not any(row["formal_candidate"] for row in rows):
            continue
        capture_plan_exact_instance_conflicts.append(
            {
                "source_identity": source_identity,
                "source_url": sorted({row["source_url"] for row in rows})[0],
                "source_urls": sorted({row["source_url"] for row in rows}),
                "uses": sorted(rows, key=lambda row: row["candidate_id"]),
            }
        )

    rejected_replay_conflicts: list[dict[str, Any]] = []
    rejected_replay_unverifiable: list[dict[str, Any]] = []
    rejected_capture_plan_unavailable: list[dict[str, Any]] = []
    rejected_candidates = _rejected_candidates(corpus_audit_path)
    for rejected in rejected_candidates:
        same_source_replacements = [
            plan
            for candidate_id, plan in sorted(plans.items())
            if candidate_id != rejected["candidate_id"]
            and plan["source_task_id"] == rejected["source_task_id"]
        ]
        old_plan = plans.get(rejected["candidate_id"])
        if old_plan is None:
            unavailable = {
                "source_task_id": rejected["source_task_id"],
                "rejected_candidate_id": rejected["candidate_id"],
            }
            rejected_capture_plan_unavailable.append(unavailable)
            for new_plan in same_source_replacements:
                rejected_replay_unverifiable.append(
                    {
                        **unavailable,
                        "new_candidate_id": new_plan["candidate_id"],
                        "new_capture_plans": new_plan["paths"],
                    }
                )
            continue
        new_plans = {
            plan["candidate_id"]: plan for plan in same_source_replacements
        }
        old_urls = set(old_plan["urls"])
        for candidate_id, new_plan in sorted(new_plans.items()):
            overlap = sorted(old_urls & set(new_plan["urls"]))
            if overlap:
                rejected_replay_conflicts.append(
                    {
                        "source_task_id": rejected["source_task_id"],
                        "rejected_candidate_id": rejected["candidate_id"],
                        "new_candidate_id": candidate_id,
                        "rejected_capture_plans": old_plan["paths"],
                        "new_capture_plans": new_plan["paths"],
                        "overlapping_urls": overlap,
                    }
                )

    conflict_count = (
        len(cross_cluster_conflicts)
        + len(capture_plan_exact_instance_conflicts)
        + len(rejected_replay_conflicts)
        + len(rejected_replay_unverifiable)
    )
    return {
        "schema": AUDIT_SCHEMA,
        "status": "passed" if conflict_count == 0 else "failed",
        "formal_first_ordinal": formal_first_ordinal,
        "critical_source_url_count": len(usage),
        "same_cluster_shared_sources": same_cluster_shared_sources,
        "cross_cluster_warnings": cross_cluster_warnings,
        "cross_cluster_conflicts": cross_cluster_conflicts,
        "formal_capture_plan_count": len(formal_candidate_ids),
        "capture_plan_exact_instance_conflicts": capture_plan_exact_instance_conflicts,
        "rejected_candidate_count": len(rejected_candidates),
        "rejected_capture_plan_unavailable": rejected_capture_plan_unavailable,
        "rejected_replay_conflicts": rejected_replay_conflicts,
        "rejected_replay_unverifiable": rejected_replay_unverifiable,
        "conflict_count": conflict_count,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, action="append", required=True)
    parser.add_argument("--capture-plan-dir", type=Path, required=True)
    parser.add_argument("--corpus-audit", type=Path, required=True)
    parser.add_argument("--formal-first-ordinal", type=int, default=FORMAL_FIRST_ORDINAL)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = audit_source_reuse(
            case_dirs=args.case_dir,
            capture_plan_dir=args.capture_plan_dir,
            corpus_audit_path=args.corpus_audit,
            formal_first_ordinal=args.formal_first_ordinal,
        )
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError, SourceReuseAuditError) as exc:
        print(f"source-reuse audit failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
