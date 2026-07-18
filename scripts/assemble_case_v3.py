#!/usr/bin/env python3
"""Assemble a canonical v3 Case Spec from a compiled motif and audited rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.case_schema_v3 import CaseValidationError, validate_case  # noqa: E402
from src.eval.evidence_graph import (  # noqa: E402
    EvidenceGraph,
    EvidenceGraphError,
    load_graph_structure,
    save_json,
)


AUTHORING_SCHEMA = "dra_v3_case_authoring_v1"


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaseValidationError(f"cannot load {label} from {source}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CaseValidationError(f"{label} must be a JSON object")
    return dict(payload)


def _evidence_source(graph: EvidenceGraph, evidence_id: str) -> dict[str, Any]:
    try:
        node = graph.node_by_id[evidence_id]
    except KeyError as exc:
        raise CaseValidationError(
            f"compiled proof source {evidence_id!r} is absent from the graph"
        ) from exc
    spans = [
        span
        for span in graph.support_spans
        if span.evidence_id == evidence_id
    ]
    if not spans:
        raise CaseValidationError(
            f"compiled proof source {evidence_id!r} has no frozen support span"
        )
    source = node.to_dict()
    source.pop("metadata", None)
    source["support_spans"] = []
    for span in sorted(spans, key=lambda item: item.support_span_id):
        record = span.to_dict()
        record.pop("metadata", None)
        source["support_spans"].append(record)
    source["frozen"] = True
    source["reachable"] = True
    return source


def assemble_case(
    *,
    graph_dir: str | Path,
    motif_compilation_path: str | Path,
    authoring_path: str | Path,
) -> dict[str, Any]:
    graph = load_graph_structure(graph_dir)
    motif_bundle = _load_object(motif_compilation_path, "motif compilation")
    authoring = _load_object(authoring_path, "case authoring")
    if authoring.get("schema") != AUTHORING_SCHEMA:
        raise CaseValidationError(
            f"case authoring schema must be {AUTHORING_SCHEMA!r}"
        )
    if motif_bundle.get("graph_stamp") != graph.graph_stamp:
        raise CaseValidationError("motif compilation is bound to a different graph")
    candidate = motif_bundle.get("candidate")
    compilation = motif_bundle.get("compilation")
    if not isinstance(candidate, Mapping) or not isinstance(compilation, Mapping):
        raise CaseValidationError("motif bundle lacks candidate or compilation")
    eligibility = candidate.get("eligibility")
    if not isinstance(eligibility, Mapping) or eligibility.get("eligible") is not True:
        raise CaseValidationError("only an eligible B-stage candidate can form a case")
    if compilation.get("candidate_id") != candidate.get("candidate_id"):
        raise CaseValidationError("motif compilation and candidate IDs disagree")
    generator_view = compilation.get("generator_view")
    evaluator_view = compilation.get("evaluator_view")
    if not isinstance(generator_view, Mapping) or not isinstance(evaluator_view, Mapping):
        raise CaseValidationError("motif compilation lacks dual views")
    steps = evaluator_view.get("required_proof_steps")
    if not isinstance(steps, list):
        raise CaseValidationError("compiled EvaluatorView lacks proof steps")
    support_ids: set[str] = set()
    for step in steps:
        if not isinstance(step, Mapping) or step.get("type") != "evidence":
            continue
        support = step.get("acceptable_support")
        if not isinstance(support, Mapping) or not isinstance(
            support.get("source_ids"), list
        ):
            raise CaseValidationError("evidence proof step lacks support source IDs")
        support_ids.update(str(value) for value in support["source_ids"])

    allowed_authoring = {
        "schema",
        "task_id",
        "cluster_id",
        "difficulty",
        "rule_definitions",
        "decidable_claims",
        "research_subgoals",
        "query_requirements",
        "acceptable_conclusions",
        "oracle",
    }
    missing = sorted((allowed_authoring - {"schema"}) - set(authoring))
    unknown = sorted(set(authoring) - allowed_authoring)
    if missing or unknown:
        raise CaseValidationError(
            f"case authoring fields disagree with the frozen schema; "
            f"missing={missing}, unknown={unknown}"
        )
    payload = {
        "task_id": authoring["task_id"],
        "task_version": 3,
        "case_schema": "evidence_graph_case_v1",
        "evidence_graph": "evidence_graph_v1",
        "observation_semantics": "observation_ledger_v1",
        "scoring_semantics": "proof_steps_v1",
        "headline_metrics": [
            "partial_completion_rate_v1",
            "full_pass_rate_v1",
        ],
        "diagnostic_metrics": [
            "route_coverage_v1",
            "acquisition_diagnostics_v1",
        ],
        "corpus_snapshot": graph.corpus_snapshot,
        "cluster_id": authoring["cluster_id"],
        "motif": compilation["graph_motif"],
        "difficulty": authoring["difficulty"],
        "generator_view": dict(generator_view),
        "evaluator_view": dict(evaluator_view),
        "evidence_sources": [
            _evidence_source(graph, evidence_id)
            for evidence_id in sorted(support_ids)
        ],
        "rule_definitions": authoring["rule_definitions"],
        "decidable_claims": authoring["decidable_claims"],
        "research_subgoals": authoring["research_subgoals"],
        "query_requirements": authoring["query_requirements"],
        "acceptable_conclusions": authoring["acceptable_conclusions"],
        "query_rendering": {
            "few_shot_subset": "manual_dev14_examples3_v1",
            "forbidden_leaks": [
                "step_id",
                "source_url",
                "gold_answer",
                "required_step_count",
            ],
            "validation": ["hard_rules", "blind_semantic_alignment"],
            "max_generation_attempts": 3,
        },
        "oracle": authoring["oracle"],
    }
    case = validate_case(payload)
    return case.protocol_dict()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", required=True)
    parser.add_argument("--motif-compilation", required=True)
    parser.add_argument("--authoring", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--print", dest="print_payload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = assemble_case(
            graph_dir=args.graph_dir,
            motif_compilation_path=args.motif_compilation,
            authoring_path=args.authoring,
        )
        save_json(args.out, payload)
        summary = {
            "ok": True,
            "out": str(Path(args.out)),
            "task_id": payload["task_id"],
            "evidence_sources": len(payload["evidence_sources"]),
            "required_proof_steps": len(
                payload["evaluator_view"]["required_proof_steps"]
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if args.print_payload:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (CaseValidationError, EvidenceGraphError, TypeError, ValueError) as exc:
        print(f"case assembly failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["AUTHORING_SCHEMA", "assemble_case", "main"]
