#!/usr/bin/env python3
"""Discover graph candidates or validate pre-existing DRA v3 case candidates.

Discovery mode performs B-stage anchor expansion, hard eligibility, Pareto
filtering and strata selection.  It does not create proof steps or gold.
Validation mode preserves the original behavior: supplied case objects are
checked against the external evidence catalog and emitted unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compile_case_v3 import (
    _catalog_container,
    _load_graph_edges,
    _load_json_or_jsonl,
    _load_support_spans,
    compile_case,
    load_reachability_manifest,
)
from src.eval.case_discovery_v3 import discover_candidates
from src.eval.case_schema_v3 import (
    CaseSpecV3,
    CaseValidationError,
    proof_subgraph_fingerprint,
    validate_case,
)
from src.eval.evidence_graph import load_graph_structure


ENUMERATION_SCHEMA = "validated_case_enumeration_v1"


def _canonical_hash(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class CandidateInput:
    payload: Mapping[str, Any]
    source: str
    index: int


@dataclass(frozen=True)
class CandidateRejection:
    source: str
    index: int
    task_id: str | None
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "index": self.index,
            "task_id": self.task_id,
            "error": self.error,
        }


@dataclass(frozen=True)
class EnumerationResult:
    cases: tuple[CaseSpecV3, ...]
    sources: tuple[str, ...]
    proof_fingerprints: tuple[str, ...]
    rejections: tuple[CandidateRejection, ...]

    def to_dict(self) -> dict[str, Any]:
        rows = []
        for case, source, fingerprint in zip(
            self.cases, self.sources, self.proof_fingerprints
        ):
            payload = case.to_dict()
            rows.append(
                {
                    "task_id": case.task_id,
                    "source": source,
                    "case_sha256": case.sha256(),
                    "proof_subgraph_sha256": fingerprint,
                    "case": payload,
                }
            )
        return {
            "enumeration_schema": ENUMERATION_SCHEMA,
            "formal_validation_only": True,
            "directly_scorable_gold": False,
            "validated_count": len(rows),
            "rejected_count": len(self.rejections),
            "task_set_sha256": _canonical_hash(
                {
                    row["task_id"]: row["case_sha256"]
                    for row in sorted(rows, key=lambda item: item["task_id"])
                }
            ),
            "formally_validated_candidates": rows,
            "rejections": [rejection.to_dict() for rejection in self.rejections],
        }


def _objects_from_payload(payload: Any, source: str) -> list[CandidateInput]:
    if isinstance(payload, Mapping):
        if isinstance(payload.get("candidates"), list):
            raw_cases = payload["candidates"]
        elif isinstance(payload.get("cases"), list):
            raw_cases = payload["cases"]
        else:
            raw_cases = [payload]
    elif isinstance(payload, list):
        raw_cases = payload
    else:
        raise CaseValidationError(f"candidate input {source} must contain JSON objects")
    candidates: list[CandidateInput] = []
    for index, raw in enumerate(raw_cases):
        if isinstance(raw, Mapping) and isinstance(raw.get("case"), Mapping):
            raw = raw["case"]
        if not isinstance(raw, Mapping):
            raise CaseValidationError(f"candidate {source}[{index}] is not a JSON object")
        candidates.append(CandidateInput(dict(raw), source, index))
    return candidates


def load_candidate_inputs(paths: Sequence[str | Path]) -> list[CandidateInput]:
    """Load supplied candidates without generating or completing any fields."""

    inputs: list[CandidateInput] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files = sorted(
                child for child in path.iterdir() if child.suffix.lower() in {".json", ".jsonl"}
            )
            if not files:
                raise CaseValidationError(f"candidate directory contains no JSON files: {path}")
            inputs.extend(load_candidate_inputs(files))
            continue
        if not path.is_file():
            raise CaseValidationError(f"candidate input does not exist: {path}")
        payload = _load_json_or_jsonl(path)
        inputs.extend(_objects_from_payload(payload, str(path)))
    return inputs


def enumerate_validated_candidates(
    candidates: Iterable[CandidateInput | Mapping[str, Any]],
    *,
    catalog_records: Iterable[Mapping[str, Any]],
    corpus_registry: Mapping[str, Any],
    support_span_records: Iterable[Mapping[str, Any]],
    graph_edges: Iterable[Mapping[str, Any]],
    reachability_manifest: Mapping[str, Any],
) -> EnumerationResult:
    """Validate supplied candidates and return only those that already pass."""

    records = [dict(record) for record in catalog_records]
    spans = [dict(record) for record in support_span_records]
    edges = [dict(record) for record in graph_edges]
    provisional: list[tuple[CaseSpecV3, CandidateInput, str]] = []
    rejected: list[CandidateRejection] = []
    seen_task_ids: set[str] = set()

    for position, raw_candidate in enumerate(candidates):
        if isinstance(raw_candidate, CandidateInput):
            candidate = raw_candidate
        elif isinstance(raw_candidate, Mapping):
            candidate = CandidateInput(dict(raw_candidate), "<memory>", position)
        else:
            rejected.append(
                CandidateRejection(
                    source="<memory>",
                    index=position,
                    task_id=None,
                    error="candidate is not a mapping",
                )
            )
            continue
        task_id_value = candidate.payload.get("task_id")
        task_id = task_id_value if isinstance(task_id_value, str) else None
        try:
            case = validate_case(candidate.payload)
            if case.task_id in seen_task_ids:
                raise CaseValidationError(f"duplicate task_id {case.task_id}")
            # Formal validation only.  Discard the compiled projection so the
            # enumerator cannot silently add registry URLs or rewrite the input.
            compile_case(
                case,
                catalog_records=records,
                corpus_registry=corpus_registry,
                support_span_records=spans,
                graph_edges=edges,
                reachability_manifest=reachability_manifest,
            )
            seen_task_ids.add(case.task_id)
            provisional.append((case, candidate, proof_subgraph_fingerprint(case)))
        except Exception as exc:
            rejected.append(
                CandidateRejection(
                    source=candidate.source,
                    index=candidate.index,
                    task_id=task_id,
                    error=str(exc),
                )
            )

    clusters_by_fingerprint: dict[str, set[str]] = {}
    for case, _, fingerprint in provisional:
        clusters_by_fingerprint.setdefault(fingerprint, set()).add(case.cluster_id)
    conflicting = {
        fingerprint: clusters
        for fingerprint, clusters in clusters_by_fingerprint.items()
        if len(clusters) > 1
    }
    valid: list[CaseSpecV3] = []
    sources: list[str] = []
    fingerprints: list[str] = []
    for case, candidate, fingerprint in provisional:
        if fingerprint in conflicting:
            rejected.append(
                CandidateRejection(
                    source=candidate.source,
                    index=candidate.index,
                    task_id=case.task_id,
                    error=(
                        "shared critical proof subgraph declares inconsistent cluster_id "
                        f"values: {sorted(conflicting[fingerprint])}"
                    ),
                )
            )
            continue
        valid.append(case)
        sources.append(candidate.source)
        fingerprints.append(fingerprint)

    # Stable input order is intentional.  It lets reviewers compare enumeration
    # output to the hand-curated candidate list without a hidden reranking step.
    return EnumerationResult(
        tuple(valid), tuple(sources), tuple(fingerprints), tuple(rejected)
    )


# Concise compatibility alias.
enumerate_cases = enumerate_validated_candidates


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="*", help="candidate JSON/JSONL files or directories")
    parser.add_argument(
        "--discover-graph-dir",
        help="run B-stage discovery on a canonical evidence-graph artifact directory",
    )
    parser.add_argument("--max-expansion-depth", type=int, default=3)
    parser.add_argument("--per-stratum", type=int, default=1)
    parser.add_argument("--selection-seed", default="dra-v3-strata-v1")
    parser.add_argument("--evidence-catalog")
    parser.add_argument("--support-spans")
    parser.add_argument("--graph-edges")
    parser.add_argument("--reachability-manifest")
    parser.add_argument(
        "--corpus-registry",
        help="complete registry; optional only when catalog container includes one",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--allow-rejections",
        action="store_true",
        help="exit zero while still recording rejected candidates",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.discover_graph_dir:
            if args.candidates:
                raise CaseValidationError(
                    "discovery mode does not accept pre-authored candidate files"
                )
            graph = load_graph_structure(args.discover_graph_dir)
            result = discover_candidates(
                graph,
                max_depth=args.max_expansion_depth,
                per_stratum=args.per_stratum,
                seed=args.selection_seed,
            )
            payload = result.to_dict()
            _write_json(args.out, payload)
            print(
                json.dumps(
                    {
                        "out": str(Path(args.out)),
                        **payload["counts"],
                        "directly_scorable_gold": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if not args.candidates:
            raise CaseValidationError(
                "validation mode requires candidate files, or use --discover-graph-dir"
            )
        if not args.evidence_catalog or not args.reachability_manifest:
            raise CaseValidationError(
                "validation mode requires --evidence-catalog and --reachability-manifest"
            )
        candidates = load_candidate_inputs(args.candidates)
        records, catalog_container = _catalog_container(args.evidence_catalog)
        spans = _load_support_spans(args.evidence_catalog, args.support_spans)
        if spans is None:
            raise CaseValidationError("formal enumeration requires support spans")
        edges = _load_graph_edges(args.evidence_catalog, args.graph_edges)
        reachability_manifest = load_reachability_manifest(args.reachability_manifest)
        if args.corpus_registry:
            # Candidate snapshots are also checked individually by compile_case.
            raw_registry = _load_json_or_jsonl(Path(args.corpus_registry))
            if not isinstance(raw_registry, Mapping):
                raise CaseValidationError("corpus registry must be a JSON object")
            registry_payload = raw_registry
        elif isinstance(catalog_container, Mapping):
            registry_payload = catalog_container
        else:
            raise CaseValidationError(
                "enumeration requires --corpus-registry or complete registry in catalog"
            )
        result = enumerate_validated_candidates(
            candidates,
            catalog_records=records,
            corpus_registry=registry_payload,
            support_span_records=spans,
            graph_edges=edges,
            reachability_manifest=reachability_manifest,
        )
        payload = result.to_dict()
        _write_json(args.out, payload)
        print(
            json.dumps(
                {
                    "out": str(Path(args.out)),
                    "validated_count": payload["validated_count"],
                    "rejected_count": payload["rejected_count"],
                    "formal_validation_only": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if result.rejections and not args.allow_rejections:
            return 2
        return 0
    except (CaseValidationError, ValueError, TypeError) as exc:
        print(f"case enumeration failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CandidateInput",
    "CandidateRejection",
    "ENUMERATION_SCHEMA",
    "EnumerationResult",
    "enumerate_cases",
    "enumerate_validated_candidates",
    "discover_candidates",
    "load_candidate_inputs",
    "main",
    "proof_subgraph_fingerprint",
]
