#!/usr/bin/env python3
"""Audit DRA v3 cases for reference-route overfitting.

The audit is deliberately read-only with respect to the case specs.  It turns
the current proof-DAG shape into a review queue for the route-flexible rubric
migration without pretending that alternative obligations can be inferred
mechanically from the hidden witness graph.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "route_flexibility_audit_v1"


class RouteFlexibilityAuditError(ValueError):
    """Raised when a case cannot be audited unambiguously."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteFlexibilityAuditError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise RouteFlexibilityAuditError(f"{path} must contain a JSON object")
    return dict(value)


def _partition(path: Path) -> str:
    parts = set(path.parts)
    if "development" in parts:
        return "development"
    if "formal_candidates" in parts:
        return "formal_candidate"
    return "formal_promoted"


def _conclusion_shape(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "missing"
    kinds = {"object" if isinstance(value, Mapping) else type(value).__name__ for value in values}
    return f"{'+'.join(sorted(kinds))}:{len(values)}"


def _source_url_by_id(case: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for source in case.get("evidence_sources") or []:
        if not isinstance(source, Mapping):
            continue
        evidence_id = str(source.get("evidence_id") or "").strip()
        source_url = str(source.get("source_url") or "").strip()
        if evidence_id:
            out[evidence_id] = source_url
    return out


def audit_case(path: Path) -> dict[str, Any]:
    case = _load(path)
    task_id = str(case.get("task_id") or "").strip()
    if not task_id:
        raise RouteFlexibilityAuditError(f"{path}: task_id is required")
    evaluator = case.get("evaluator_view")
    if not isinstance(evaluator, Mapping):
        raise RouteFlexibilityAuditError(f"{path}: evaluator_view is required")
    steps = evaluator.get("required_proof_steps")
    if not isinstance(steps, list) or not steps:
        raise RouteFlexibilityAuditError(
            f"{path}: evaluator_view.required_proof_steps is required"
        )

    evidence_steps = [step for step in steps if step.get("type") == "evidence"]
    derived_steps = [step for step in steps if step.get("type") in {"bridge", "decision"}]
    singleton = 0
    alternatives = 0
    evidence_review: list[dict[str, Any]] = []
    urls = _source_url_by_id(case)
    for step in evidence_steps:
        support = step.get("acceptable_support") or {}
        source_ids = list(support.get("source_ids") or [])
        singleton += int(len(source_ids) == 1)
        alternatives += int(len(source_ids) > 1)
        evidence_review.append(
            {
                "step_id": step.get("step_id"),
                "proposition": step.get("claim"),
                "source_roles": list(support.get("source_roles") or []),
                "witness_source_ids": source_ids,
                "witness_urls": [urls.get(str(source_id), "") for source_id in source_ids],
                "migration_action": (
                    "replace source whitelist with semantic proposition contract; "
                    "retain these sources only as answerability witnesses"
                ),
            }
        )

    conclusions = case.get("acceptable_conclusions") or []
    ablation = ((case.get("oracle") or {}).get("critical_node_ablation") or {})
    all_ablation_unresolved = bool(ablation) and all(
        isinstance(value, Mapping) and value.get("outcome") == "decision_unresolved"
        for value in ablation.values()
    )
    all_steps_required = all(
        step.get("required", True) is not False and step.get("optional") is not True
        for step in steps
    )
    all_singleton = bool(evidence_steps) and singleton == len(evidence_steps)
    fixed_dependencies = bool(derived_steps) and all(
        isinstance(step.get("requires"), list) and bool(step.get("requires"))
        for step in derived_steps
    )

    flags: list[str] = []
    if all_singleton:
        flags.append("all_evidence_steps_single_witness")
    if all_steps_required:
        flags.append("all_steps_unconditionally_required")
    if fixed_dependencies:
        flags.append("derived_steps_use_fixed_and_dependencies")
    if all_ablation_unresolved:
        flags.append("all_ablation_nodes_declared_decision_critical")
    if len(conclusions) == 1:
        flags.append("single_acceptable_conclusion")
    final_contract = evaluator.get("final_answer_contract") or {}
    if len(conclusions) == 1 and final_contract.get("unique_product_required") is False:
        flags.append("open_conclusion_contract_but_single_answer_whitelist")

    generator = case.get("generator_view") or {}
    return {
        "task_id": task_id,
        "case_path": path.as_posix(),
        "partition": _partition(path),
        "cluster_id": case.get("cluster_id"),
        "motif": case.get("motif"),
        "intent": case.get("intent"),
        "generator_view": {
            "constraints": list(generator.get("constraints") or []),
            "candidate_actions": list(generator.get("candidate_actions") or []),
            "target": generator.get("target"),
        },
        "counts": {
            "proof_steps": len(steps),
            "evidence_steps": len(evidence_steps),
            "derived_steps": len(derived_steps),
            "singleton_witness_steps": singleton,
            "multi_witness_steps": alternatives,
            "optional_steps": sum(
                step.get("required", True) is False or step.get("optional") is True
                for step in steps
            ),
            "acceptable_conclusions": len(conclusions),
        },
        "conclusion_shape": _conclusion_shape(conclusions),
        "acceptable_conclusions": conclusions,
        "risk_flags": flags,
        "evidence_review": evidence_review,
        "derived_review": [
            {
                "step_id": step.get("step_id"),
                "type": step.get("type"),
                "rule": step.get("rule"),
                "fixed_requires": list(step.get("requires") or []),
                "migration_action": (
                    "rewrite as a query-derived obligation with one or more "
                    "explicit alternative proof routes"
                ),
            }
            for step in derived_steps
        ],
        "review_required": {
            "query_obligations": True,
            "conditional_applicability": True,
            "alternative_proof_routes": True,
            "negative_search_routes": True,
            "constraint_consistent_decision_contract": True,
        },
    }


def build_audit(case_root: Path) -> dict[str, Any]:
    paths = sorted(case_root.rglob("*.json"))
    if not paths:
        raise RouteFlexibilityAuditError(f"no JSON cases found under {case_root}")
    cases = [audit_case(path) for path in paths]
    task_ids = [case["task_id"] for case in cases]
    duplicates = sorted(task_id for task_id, count in Counter(task_ids).items() if count > 1)
    if duplicates:
        raise RouteFlexibilityAuditError(f"duplicate task IDs: {duplicates}")

    motif_counts = Counter(str(case.get("motif")) for case in cases)
    partition_counts = Counter(str(case.get("partition")) for case in cases)
    total_evidence = sum(case["counts"]["evidence_steps"] for case in cases)
    total_singleton = sum(case["counts"]["singleton_witness_steps"] for case in cases)
    total_steps = sum(case["counts"]["proof_steps"] for case in cases)
    total_optional = sum(case["counts"]["optional_steps"] for case in cases)
    single_conclusion_cases = sum(
        case["counts"]["acceptable_conclusions"] == 1 for case in cases
    )
    all_ablation_critical = sum(
        "all_ablation_nodes_declared_decision_critical" in case["risk_flags"]
        for case in cases
    )
    return {
        "schema": AUDIT_SCHEMA,
        "case_root": case_root.as_posix(),
        "summary": {
            "case_count": len(cases),
            "partition_counts": dict(sorted(partition_counts.items())),
            "motif_counts": dict(sorted(motif_counts.items())),
            "proof_step_count": total_steps,
            "evidence_step_count": total_evidence,
            "singleton_witness_step_count": total_singleton,
            "multi_witness_step_count": total_evidence - total_singleton,
            "optional_step_count": total_optional,
            "single_conclusion_case_count": single_conclusion_cases,
            "all_ablation_critical_case_count": all_ablation_critical,
        },
        "migration_order": [
            "development",
            "formal_promoted",
            "formal_candidate",
        ],
        "cases": cases,
    }


def render_markdown(audit: Mapping[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# DRA v3 Route-Flexibility Audit",
        "",
        "This report is generated from the current case specs. It diagnoses "
        "reference-route overfitting; it does not modify or approve any rubric.",
        "",
        "## Summary",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Proof steps: {summary['proof_step_count']}",
        f"- Evidence steps: {summary['evidence_step_count']}",
        f"- Singleton witness bindings: {summary['singleton_witness_step_count']}",
        f"- Multi-witness bindings: {summary['multi_witness_step_count']}",
        f"- Optional steps: {summary['optional_step_count']}",
        f"- Cases with one accepted conclusion: {summary['single_conclusion_case_count']}",
        f"- Cases declaring every ablated evidence node decision-critical: "
        f"{summary['all_ablation_critical_case_count']}",
        "",
        "## Required migration",
        "",
        "1. Derive decision obligations from the public query, not the hidden witness graph.",
        "2. Replace source-ID whitelists with semantic proposition and source-role contracts.",
        "3. Retain current URLs only as known answerability witnesses.",
        "4. Represent conditional, alternative, and scoped-negative-search proof routes explicitly.",
        "5. Replace answer-name whitelists with evidence- and constraint-consistent decision contracts.",
        "6. Pass source-substitution, route-substitution, conclusion-substitution, and requirement-deletion tests.",
        "",
        "## Review queue",
        "",
        "| Task | Partition | Motif | Evidence | Conclusions | Flags |",
        "|---|---|---:|---:|---:|---|",
    ]
    for case in audit["cases"]:
        lines.append(
            "| {task_id} | {partition} | {motif} | {evidence} | {conclusions} | {flags} |".format(
                task_id=case["task_id"],
                partition=case["partition"],
                motif=case["motif"],
                evidence=case["counts"]["evidence_steps"],
                conclusions=case["counts"]["acceptable_conclusions"],
                flags=", ".join(case["risk_flags"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-root",
        type=Path,
        default=Path("data/golden/cases_v3"),
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    audit = build_audit(args.case_root)
    payload = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(audit), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
