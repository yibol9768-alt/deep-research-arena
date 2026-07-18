#!/usr/bin/env python3
"""Build the deterministic queue that expands the DRA v3 panel to 100 tasks.

The queue treats legacy task specs only as scenario seeds.  It never imports a
v2 answer key, checklist, URL pool, verdict, or score into v3 gold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


QUEUE_SCHEMA = "dra_v3_formal_candidate_queue_v1"
SUPPLEMENTAL_SEED_SCHEMA = "dra_v3_supplemental_scenario_seed_pool_v1"
DEVELOPMENT_PANEL_SIZE = 14
SOURCE_TASK_RE = re.compile(r"^dr_cross_deep_(\d{4})\.json$")
SUPPLEMENTAL_SOURCE_RE = re.compile(r"^dra_v3_supplemental_seed_(\d{4})$")
TASK_ORDINAL_RE = re.compile(r"_(\d{4})$")
SAFE_SLUG_RE = re.compile(r"[^a-z0-9]+")
SUPPLEMENTAL_SEED_FIELDS = frozenset(
    {"source_task_id", "domain", "cluster", "archetype", "angle", "intent"}
)


class QueueBuildError(ValueError):
    """The current artifacts cannot define an unambiguous 100-task queue."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QueueBuildError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise QueueBuildError(f"{label}: {path} must contain an object")
    return dict(value)


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueueBuildError(f"{label}: expected a non-empty string")
    return value.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    slug = SAFE_SLUG_RE.sub("_", value.casefold()).strip("_")
    if not slug:
        raise QueueBuildError(f"cannot derive a safe slug from {value!r}")
    return slug


def _source_specs(source_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in sorted(source_dir.glob("dr_cross_deep_*.json")):
        match = SOURCE_TASK_RE.fullmatch(path.name)
        if match is None:
            continue
        spec = _load_object(path, "source task")
        source_task_id = _non_empty(spec.get("task_id"), f"{path}.task_id")
        expected = f"dr_cross_deep_{match.group(1)}"
        if source_task_id != expected:
            raise QueueBuildError(
                f"{path}: task_id {source_task_id!r} does not match {expected!r}"
            )
        if source_task_id in seen_ids:
            raise QueueBuildError(f"duplicate source task_id {source_task_id!r}")
        if spec.get("task_version") != 2:
            raise QueueBuildError(f"{path}: expected task_version=2")
        tri_source = spec.get("tri_source")
        if not isinstance(tri_source, Mapping):
            raise QueueBuildError(f"{path}: tri_source must be an object")
        domain = _non_empty(spec.get("domain"), f"{path}.domain")
        rows.append(
            {
                "source_ordinal": int(match.group(1)),
                "source_kind": "legacy_v2_scenario_seed",
                "source_sort_key": [0, int(match.group(1))],
                "source_task_id": source_task_id,
                "source_task_path": path.as_posix(),
                "source_task_sha256": _sha256(path),
                "source_entry_sha256": _sha256(path),
                "source_container_sha256": _sha256(path),
                "source_hash_basis": "raw_file_bytes",
                "domain": domain,
                "cluster": _non_empty(
                    tri_source.get("cluster"), f"{path}.tri_source.cluster"
                ),
                "archetype": _non_empty(
                    tri_source.get("archetype"), f"{path}.tri_source.archetype"
                ),
                "angle": _non_empty(
                    tri_source.get("angle"), f"{path}.tri_source.angle"
                ),
                "intent_sha256": hashlib.sha256(
                    _non_empty(spec.get("intent"), f"{path}.intent").encode("utf-8")
                ).hexdigest(),
            }
        )
        seen_ids.add(source_task_id)
    rows.sort(key=lambda row: row["source_ordinal"])
    return rows


def _supplemental_specs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    pool = _load_object(path, "supplemental seed pool")
    if pool.get("schema") != SUPPLEMENTAL_SEED_SCHEMA:
        raise QueueBuildError(
            f"{path}: expected schema={SUPPLEMENTAL_SEED_SCHEMA!r}"
        )
    raw_seeds = pool.get("seeds")
    if not isinstance(raw_seeds, list):
        raise QueueBuildError(f"{path}: seeds must be an array")
    pool_sha256 = _sha256(path)
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_sequences: set[int] = set()
    for index, raw in enumerate(raw_seeds):
        if not isinstance(raw, Mapping):
            raise QueueBuildError(f"{path}: seeds[{index}] must be an object")
        seed = dict(raw)
        unknown_fields = sorted(set(seed) - SUPPLEMENTAL_SEED_FIELDS)
        if unknown_fields:
            raise QueueBuildError(
                f"{path}: seeds[{index}] has unknown fields {unknown_fields}"
            )
        source_task_id = _non_empty(
            seed.get("source_task_id"), f"{path}.seeds[{index}].source_task_id"
        )
        match = SUPPLEMENTAL_SOURCE_RE.fullmatch(source_task_id)
        if match is None:
            raise QueueBuildError(
                f"{path}: invalid supplemental source_task_id {source_task_id!r}"
            )
        sequence = int(match.group(1))
        if source_task_id in seen_ids or sequence in seen_sequences:
            raise QueueBuildError(
                f"{path}: duplicate supplemental seed identity {source_task_id!r}"
            )
        intent = _non_empty(seed.get("intent"), f"{path}.seeds[{index}].intent")
        domain = _non_empty(seed.get("domain"), f"{path}.seeds[{index}].domain")
        entry_sha256 = hashlib.sha256(
            json.dumps(
                seed,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "source_ordinal": sequence,
                "source_kind": "v3_supplemental_scenario_seed",
                "source_sort_key": [1, sequence],
                "source_task_id": source_task_id,
                "source_task_path": path.as_posix(),
                "source_task_sha256": entry_sha256,
                "source_entry_sha256": entry_sha256,
                "source_container_sha256": pool_sha256,
                "source_hash_basis": "canonical_seed_entry",
                "domain": domain,
                "cluster": _non_empty(
                    seed.get("cluster"), f"{path}.seeds[{index}].cluster"
                ),
                "archetype": _non_empty(
                    seed.get("archetype"), f"{path}.seeds[{index}].archetype"
                ),
                "angle": _non_empty(
                    seed.get("angle"), f"{path}.seeds[{index}].angle"
                ),
                "intent_sha256": hashlib.sha256(intent.encode("utf-8")).hexdigest(),
            }
        )
        seen_ids.add(source_task_id)
        seen_sequences.add(sequence)
    rows.sort(key=lambda row: row["source_sort_key"])
    return rows


def _terminal_rejections(
    rejection_root: Path | Sequence[Path] | None,
) -> dict[str, list[dict[str, Any]]]:
    if rejection_root is None:
        return {}
    roots = [rejection_root] if isinstance(rejection_root, Path) else list(rejection_root)
    paths = sorted(
        {
            path
            for root in roots
            for path in root.rglob("rejection_audit.json")
        }
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        audit = _load_object(path, "formal rejection audit")
        decision = audit.get("decision")
        identity = audit.get("identity")
        if not isinstance(decision, Mapping) or not isinstance(identity, Mapping):
            raise QueueBuildError(
                f"{path}: rejection audit requires decision and identity objects"
            )
        status = _non_empty(decision.get("status"), f"{path}.decision.status")
        release_eligible = decision.get("formal_release_eligible")
        if not status.startswith("rejected_"):
            raise QueueBuildError(
                f"{path}: rejection audit status must start with 'rejected_'"
            )
        if release_eligible is not False:
            raise QueueBuildError(
                f"{path}: terminal rejection must set formal_release_eligible=false"
            )
        source_task_id = _non_empty(
            identity.get("source_task_id"), f"{path}.identity.source_task_id"
        )
        result.setdefault(source_task_id, []).append(
            {
                "candidate_id": _non_empty(
                    audit.get("candidate_id"), f"{path}.candidate_id"
                ),
                "target_task_id": _non_empty(
                    identity.get("target_task_id"), f"{path}.identity.target_task_id"
                ),
                "status": status,
                "code": _non_empty(decision.get("code"), f"{path}.decision.code"),
                "audit_path": path.as_posix(),
                "audit_sha256": _sha256(path),
            }
        )
    return result


def _public_task_ids(public_dir: Path) -> set[str]:
    task_ids: set[str] = set()
    for path in sorted(public_dir.rglob("*.json")):
        value = _load_object(path, "public task")
        task_id = _non_empty(value.get("task_id"), f"{path}.task_id")
        if task_id in task_ids:
            raise QueueBuildError(f"duplicate public task_id {task_id!r}")
        task_ids.add(task_id)
    return task_ids


def _candidate_to_source(capture_plan_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(capture_plan_dir.glob("*.json")):
        value = _load_object(path, "capture plan")
        candidate_id = _non_empty(value.get("candidate_id"), f"{path}.candidate_id")
        metadata = value.get("metadata")
        if not isinstance(metadata, Mapping):
            raise QueueBuildError(f"{path}: metadata must be an object")
        source_task_id = _non_empty(
            metadata.get("candidate_source_task_id"),
            f"{path}.metadata.candidate_source_task_id",
        )
        previous = result.get(candidate_id)
        if previous is not None and previous != source_task_id:
            raise QueueBuildError(
                f"candidate {candidate_id!r} maps to multiple source tasks: "
                f"{previous!r}, {source_task_id!r}"
            )
        result[candidate_id] = source_task_id
    return result


def _published_source_map(
    authoring_dir: Path | Sequence[Path],
    public_task_ids: set[str],
    candidate_sources: Mapping[str, str],
) -> dict[str, str]:
    task_to_source: dict[str, str] = {}
    roots = [authoring_dir] if isinstance(authoring_dir, Path) else list(authoring_dir)
    paths = sorted(
        {
            path
            for root in roots
            for path in root.rglob("*case_authoring_source.json")
        }
    )
    for path in paths:
        value = _load_object(path, "case authoring source")
        task_id = _non_empty(value.get("task_id"), f"{path}.task_id")
        if task_id not in public_task_ids:
            continue
        candidate_id = _non_empty(value.get("candidate_id"), f"{path}.candidate_id")
        source_task_id = candidate_sources.get(candidate_id)
        if source_task_id is None:
            raise QueueBuildError(
                f"published task {task_id!r} candidate {candidate_id!r} "
                "has no capture-plan source mapping"
            )
        previous = task_to_source.get(task_id)
        if previous is not None:
            if previous != source_task_id:
                raise QueueBuildError(
                    f"published task {task_id!r} has conflicting source mappings: "
                    f"{previous!r}, {source_task_id!r}"
                )
            continue
        task_to_source[task_id] = source_task_id
    missing = sorted(public_task_ids - set(task_to_source))
    if missing:
        raise QueueBuildError(
            f"public tasks missing case-authoring/source mapping: {missing}"
        )
    if len(set(task_to_source.values())) != len(task_to_source):
        raise QueueBuildError("multiple published tasks reuse the same source task")
    return task_to_source


def _audit_by_source(corpus_audit_path: Path) -> dict[str, dict[str, Any]]:
    audit = _load_object(corpus_audit_path, "corpus audit")
    candidates = audit.get("candidates")
    if not isinstance(candidates, list):
        raise QueueBuildError("corpus audit candidates must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(candidates):
        if not isinstance(raw, Mapping):
            raise QueueBuildError(f"corpus audit candidate[{index}] must be an object")
        source_task_id = _non_empty(
            raw.get("source_task_id"), f"corpus audit candidate[{index}].source_task_id"
        )
        if source_task_id in result:
            raise QueueBuildError(f"duplicate corpus-audit source {source_task_id!r}")
        result[source_task_id] = {
            "candidate_id": _non_empty(
                raw.get("candidate_id"), f"corpus audit candidate[{index}].candidate_id"
            ),
            "verdict": _non_empty(
                raw.get("verdict"), f"corpus audit candidate[{index}].verdict"
            ),
        }
    return result


def build_queue(
    *,
    source_dir: Path,
    public_dir: Path,
    authoring_dir: Path | Sequence[Path],
    capture_plan_dir: Path,
    corpus_audit_path: Path,
    target_total: int,
    supplemental_seed_path: Path | None = None,
    rejection_root: Path | Sequence[Path] | None = None,
) -> dict[str, Any]:
    if target_total < 1:
        raise QueueBuildError("target_total must be positive")
    development_target_count = min(DEVELOPMENT_PANEL_SIZE, target_total)
    formal_target_count = target_total - development_target_count
    legacy_specs = _source_specs(source_dir)
    supplemental_specs = _supplemental_specs(supplemental_seed_path)
    specs = legacy_specs + supplemental_specs
    source_ids = [row["source_task_id"] for row in specs]
    if len(set(source_ids)) != len(source_ids):
        raise QueueBuildError("legacy and supplemental seed pools contain duplicate IDs")
    specs.sort(key=lambda row: row["source_sort_key"])
    terminal_rejections = _terminal_rejections(rejection_root)
    rejected_source_ids = set(terminal_rejections)
    unknown_rejections = sorted(rejected_source_ids - set(source_ids))
    if unknown_rejections:
        raise QueueBuildError(
            f"terminal rejections reference unknown sources: {unknown_rejections}"
        )
    public_ids = _public_task_ids(public_dir)
    candidate_sources = _candidate_to_source(capture_plan_dir)
    published = _published_source_map(
        authoring_dir, public_ids, candidate_sources
    )
    published_source_ids = set(published.values())
    known_source_ids = {row["source_task_id"] for row in specs}
    unknown = sorted(published_source_ids - known_source_ids)
    if unknown:
        raise QueueBuildError(f"published tasks reference unknown sources: {unknown}")
    rejected_published = sorted(published_source_ids & rejected_source_ids)
    if rejected_published:
        raise QueueBuildError(
            f"terminally rejected sources are already published: {rejected_published}"
        )

    ordinals: list[int] = []
    for task_id in sorted(public_ids):
        match = TASK_ORDINAL_RE.search(task_id)
        if match is None:
            raise QueueBuildError(f"public task_id lacks four-digit ordinal: {task_id}")
        ordinals.append(int(match.group(1)))
    expected_existing = list(range(1, len(public_ids) + 1))
    if sorted(ordinals) != expected_existing:
        raise QueueBuildError(
            "published task ordinals must be contiguous from 0001; "
            f"found {sorted(ordinals)}"
        )

    audit = _audit_by_source(corpus_audit_path)
    eligible_specs = [
        row for row in specs if row["source_task_id"] not in rejected_source_ids
    ]
    unpublished = [
        row
        for row in eligible_specs
        if row["source_task_id"] not in published_source_ids
    ]
    needed = target_total - len(public_ids)
    if needed < 0:
        raise QueueBuildError(
            f"published task count {len(public_ids)} exceeds target_total {target_total}"
        )
    if len(unpublished) < needed:
        raise QueueBuildError(
            "not enough eligible scenario seeds after terminal rejections: "
            f"need {needed}, found {len(unpublished)}"
        )
    selected_unpublished = unpublished[:needed]
    reserve_sources = unpublished[needed:]

    queue: list[dict[str, Any]] = []
    next_ordinal = len(public_ids) + 1
    for offset, source in enumerate(selected_unpublished):
        ordinal = next_ordinal + offset
        prior = audit.get(source["source_task_id"])
        if source["source_kind"] == "legacy_v2_scenario_seed":
            candidate_source_suffix = f"{source['source_ordinal']:04d}"
        else:
            candidate_source_suffix = f"supplemental_{source['source_ordinal']:04d}"
        queue.append(
            {
                "ordinal": ordinal,
                "panel_partition": (
                    "development"
                    if ordinal <= development_target_count
                    else "formal_candidate"
                ),
                "target_task_id": (
                    f"dra_v3_formal_{_slug(source['domain'])}_{ordinal:04d}"
                ),
                "candidate_id": (
                    f"cand_formal_{ordinal:04d}_from_{candidate_source_suffix}"
                ),
                "source_kind": source["source_kind"],
                "source_task_id": source["source_task_id"],
                "source_task_path": source["source_task_path"],
                "source_task_sha256": source["source_task_sha256"],
                "source_entry_sha256": source["source_entry_sha256"],
                "source_container_sha256": source["source_container_sha256"],
                "source_hash_basis": source["source_hash_basis"],
                "intent_sha256": source["intent_sha256"],
                "domain": source["domain"],
                "cluster": source["cluster"],
                "archetype": source["archetype"],
                "angle": source["angle"],
                "prior_candidate_id": prior["candidate_id"] if prior else None,
                "prior_corpus_audit_verdict": prior["verdict"] if prior else "not_audited",
                "fresh_snapshot_required": True,
                "state": "queued_for_fresh_corpus_audit",
                "legacy_v2_mutated": False,
            }
        )

    spec_by_id = {row["source_task_id"]: row for row in specs}
    existing = [
        {
            "task_id": task_id,
            "source_task_id": source_task_id,
            "source_kind": spec_by_id[source_task_id]["source_kind"],
            "ordinal": int(TASK_ORDINAL_RE.search(task_id).group(1)),
            "panel_partition": (
                "development"
                if int(TASK_ORDINAL_RE.search(task_id).group(1))
                <= development_target_count
                else "formal_candidate"
            ),
        }
        for task_id, source_task_id in sorted(
            published.items(),
            key=lambda item: int(TASK_ORDINAL_RE.search(item[0]).group(1)),
        )
    ]
    development_existing_count = sum(
        row["panel_partition"] == "development" for row in existing
    )
    formal_existing_count = sum(
        row["panel_partition"] == "formal_candidate" for row in existing
    )
    development_queued_count = sum(
        row["panel_partition"] == "development" for row in queue
    )
    formal_queued_count = sum(
        row["panel_partition"] == "formal_candidate" for row in queue
    )
    if development_existing_count + development_queued_count != development_target_count:
        raise QueueBuildError("development partition does not reach its target size")
    if formal_existing_count + formal_queued_count != formal_target_count:
        raise QueueBuildError("formal partition does not reach its target size")

    return {
        "schema": QUEUE_SCHEMA,
        "target_total": target_total,
        "development_target_count": development_target_count,
        "formal_target_count": formal_target_count,
        "existing_count": len(existing),
        "queued_count": len(queue),
        "counted_total": len(existing) + len(queue),
        "development_existing_count": development_existing_count,
        "development_queued_count": development_queued_count,
        "formal_existing_count": formal_existing_count,
        "formal_queued_count": formal_queued_count,
        "terminal_rejected_count": len(rejected_source_ids),
        "terminal_rejections": [
            {
                "source_task_id": source_task_id,
                "audits": terminal_rejections[source_task_id],
            }
            for source_task_id in sorted(rejected_source_ids)
        ],
        "reserve_count": len(reserve_sources),
        "reserve_sources": [
            {
                "source_task_id": row["source_task_id"],
                "source_kind": row["source_kind"],
                "source_entry_sha256": row["source_entry_sha256"],
            }
            for row in reserve_sources
        ],
        "source_inventory": {
            "legacy_v2_scenario_seed_count": len(legacy_specs),
            "v3_supplemental_scenario_seed_count": len(supplemental_specs),
            "eligible_after_terminal_rejections": len(eligible_specs),
        },
        "selection_policy": (
            "eligible_unpublished_legacy_then_supplemental_seed_order_"
            "excluding_terminal_rejections"
        ),
        "source_task_usage": (
            "scenario_seed_only_no_v2_gold_checklist_url_verdict_or_score_inheritance"
        ),
        "existing_tasks": existing,
        "queue": queue,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument(
        "--authoring-dir",
        type=Path,
        action="append",
        required=True,
        help="authoring root; repeat for graph-local and pilot graph-input roots",
    )
    parser.add_argument("--capture-plan-dir", type=Path, required=True)
    parser.add_argument("--corpus-audit", type=Path, required=True)
    parser.add_argument(
        "--supplemental-seeds",
        type=Path,
        help="optional v3-only scenario seed pool used after legacy seeds",
    )
    parser.add_argument(
        "--rejection-root",
        type=Path,
        action="append",
        help="root containing terminal rejection_audit.json files; repeatable",
    )
    parser.add_argument("--target-total", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build_queue(
            source_dir=args.source_dir,
            public_dir=args.public_dir,
            authoring_dir=args.authoring_dir,
            capture_plan_dir=args.capture_plan_dir,
            corpus_audit_path=args.corpus_audit,
            target_total=args.target_total,
            supplemental_seed_path=args.supplemental_seeds,
            rejection_root=args.rejection_root,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError, QueueBuildError) as exc:
        print(f"queue build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "out": args.out.as_posix(),
                "existing_count": result["existing_count"],
                "queued_count": result["queued_count"],
                "counted_total": result["counted_total"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
