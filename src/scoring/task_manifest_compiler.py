"""Compile existing frozen task assets into the four-axis TEC schema.

This is a report-blind transition compiler.  It uses the task query, the
pre-existing Task World Model, and the route-flexible Research Test Suite.  It
never receives a harness report, winner, or report citations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.scoring.audited_judge import AuditedJudge
from src.scoring.report_claim_pipeline import write_jsonl


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _flatten_checks(suite: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for facet in suite.get("facets", []):
        for unit in facet.get("units", []):
            for check in unit.get("checks", []):
                rows.append(
                    {
                        "check_id": check["check_id"],
                        "facet_id": facet["facet_id"],
                        "facet_label": facet.get("label", facet["facet_id"]),
                        "legacy_unit_id": unit.get("unit_id"),
                        "requirement": check["content_contract"],
                        "tier": check.get("tier", "core"),
                        "applicable": bool(check.get("applicable", True)),
                        "depends_on_checks": check.get("depends_on_checks", []),
                        "evidence_required": not bool(
                            check.get("evidence_exempt", False)
                        ),
                        "critical_error_on_contradiction": bool(
                            check.get("critical_error_on_contradiction", False)
                        ),
                    }
                )
    return rows


QUERY_RUBRIC_COMPILER_SYSTEM = """You are compiling query-compliance rubrics
before seeing any agent report, evidence graph, answer key, candidate pages, or
reference answer. You receive ONLY the literal user query.

Extract the explicit deliverables and constraints the report must obey:
requested comparisons, audits, procedures, recommendations, caveats, budget or
format constraints, and citation instructions. A rubric checks whether the
report followed the query; it must not encode which facts are true.

Rules:
1. Every item must be directly entailed by one exact contiguous query_span.
2. Do not add latent "good research" expectations.
3. Do not require a winner, value, conclusion, source, URL, or route unless the
   query literally specifies it.
4. Split independently satisfiable instructions, but do not atomize a natural
   list into dozens of stylistic fragments.
5. Keep requirements answer-independent.

Return JSON only:
{"items":[{"rubric_key":"Q1","query_span":"exact contiguous quote",
"requirement":"answer-independent compliance requirement",
"requirement_type":"comparison|audit|procedure|recommendation|caveat|budget|format|citation|other"}]}
"""

QUERY_RUBRIC_AUDIT_SYSTEM = """Audit proposed query-compliance rubrics using
ONLY the literal query. Accept an item only when its requirement is entailed by
its exact query_span and it contains no answer, preferred winner, hidden fact,
preselected URL, or invented research route. Return every item once:
{"items":[{"rubric_key":"Q1","verdict":"accept|reject",
"reason_code":"short_code"}]}
"""

RESEARCH_UNIT_COMPILER_SYSTEM = """You are compiling the content-coverage
denominator of a Deep Research task before seeing any agent report. You receive
the public query and report-blind candidate research checks.

For every candidate:
1. Keep it only when it is a content, comparison, mechanism, conflict,
   synthesis, community-pattern, procedure, budget-allocation, or decision
   unit that the frozen task is intended to make discoverable.
2. Rewrite route-bound wording into an outcome contract. Never require a
   preselected URL, unique witness, unique research route, or fixed winner.
3. Do not turn query-compliance instructions into rubric items here; this
   stage can output only completeness or drop.
4. Mark answer_leak or route_bound when safe rewriting is impossible.
5. Do not inspect or infer anything about an agent report.
6. Copy each check_id byte-for-byte from valid_check_ids. Return every
   candidate exactly once and in the input order. Never invent, abbreviate,
   or emit a placeholder identifier.

Return every candidate exactly once as JSON:
{"items":[{"check_id":"EXACT_ID_FROM_VALID_CHECK_IDS","include":true,
"requirement":"answer-independent content requirement",
"axis":"completeness|drop","needs_split":false,
"unit_type":"atomic|comparison|mechanism|conflict|cross_source_synthesis|community_pattern|procedure|budget_allocation|decision",
"necessity":"necessary|useful_but_optional|not_justified",
"answer_leak":false,"route_bound":false,"reason_code":"short_code"}]}
"""

ATOMIC_COMPILER_SYSTEM = """You are organizing a frozen task evidence census.
Map every supplied atomic assertion to exactly one supplied facet. Do not
change its statement, truth value, qualifiers, or source-role policy. Do not
judge any report. Return JSON only:
{"items":[{"assertion_id":"F1","facet_id":"F_X",
"importance":"core|supporting","evidence_required":true}]}
"""


def compile_task_manifest(
    task: dict[str, Any],
    task_world_model: dict[str, Any],
    research_test_suite: dict[str, Any],
    judge: AuditedJudge,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    query = (
        task.get("prompt")
        or task.get("intent")
        or task.get("query")
        or ""
    )
    checks = _flatten_checks(research_test_suite)
    query_rubric_proposal = judge.call_json(
        "tec-query-only-rubric-compiler",
        QUERY_RUBRIC_COMPILER_SYSTEM,
        {
            "query": query,
        },
        expected_top_key="items",
    )
    proposed_query_rubrics: list[dict[str, Any]] = []
    seen_rubric_keys: set[str] = set()
    for row in query_rubric_proposal.get("items", []):
        key = str(row.get("rubric_key") or "")
        query_span = str(row.get("query_span") or "")
        requirement = str(row.get("requirement") or "")
        if (
            not key
            or key in seen_rubric_keys
            or not query_span
            or query_span not in query
            or not requirement
        ):
            continue
        seen_rubric_keys.add(key)
        proposed_query_rubrics.append(
            {
                "rubric_key": key,
                "query_span": query_span,
                "requirement": requirement,
                "requirement_type": str(
                    row.get("requirement_type") or "other"
                ),
            }
        )
    query_rubric_audit = judge.call_json(
        "tec-query-only-rubric-audit",
        QUERY_RUBRIC_AUDIT_SYSTEM,
        {
            "query": query,
            "items": proposed_query_rubrics,
        },
        expected_top_key="items",
    )
    query_rubric_audit_map = {
        str(row.get("rubric_key")): row
        for row in query_rubric_audit.get("items", [])
        if row.get("rubric_key")
    }
    accepted_query_rubrics = [
        row
        for row in proposed_query_rubrics
        if query_rubric_audit_map.get(row["rubric_key"], {}).get("verdict")
        == "accept"
    ]

    research_review = judge.call_json(
        "tec-report-blind-completeness-compiler",
        RESEARCH_UNIT_COMPILER_SYSTEM,
        {
            "query": query,
            "valid_check_ids": [row["check_id"] for row in checks],
            "candidate_requirements": checks,
        },
        expected_top_key="items",
    )
    reviews = {
        row.get("check_id"): row
        for row in research_review.get("items", [])
    }

    facets = [
        {
            "facet_id": row["facet_id"],
            "label": row.get("label", row["facet_id"]),
        }
        for row in research_test_suite.get("facets", [])
    ]
    assertions = task_world_model.get("assertions", [])
    atomic_review = judge.call_json(
        "tec-atomic-facet-compiler",
        ATOMIC_COMPILER_SYSTEM,
        {
            "facets": facets,
            "atomic_assertions": [
                {
                    "assertion_id": row["assertion_id"],
                    "statement": row["statement"],
                    "source_role": row.get("source_role"),
                    "modality": row.get("modality"),
                }
                for row in assertions
            ],
        },
        expected_top_key="items",
    )
    atomic_reviews = {
        row.get("assertion_id"): row for row in atomic_review.get("items", [])
    }
    fallback_facet = facets[0]["facet_id"] if facets else "task"
    atomic_units: list[dict[str, Any]] = []
    for assertion in assertions:
        classified = atomic_reviews.get(assertion["assertion_id"], {})
        facet_id = classified.get("facet_id")
        if facet_id not in {row["facet_id"] for row in facets}:
            facet_id = fallback_facet
        atomic_units.append(
            {
                "unit_id": f"atomic:{assertion['assertion_id']}",
                "legacy_assertion_id": assertion["assertion_id"],
                "facet_id": facet_id,
                "unit_type": "atomic",
                "statement": assertion["statement"],
                "importance": classified.get("importance", "core"),
                "applicable": True,
                "evidence_required": bool(
                    classified.get("evidence_required", True)
                ),
                "source_role_policy": [assertion.get("source_role")]
                if assertion.get("source_role")
                else [],
                "known_support_span_ids": assertion.get(
                    "known_support_span_ids", []
                ),
                "known_witness_urls": assertion.get(
                    "answerability_witness_urls", []
                ),
                "known_witnesses_are_allowlist": False,
                "limitations": assertion.get("limitations", []),
            }
        )

    rubric_items: list[dict[str, Any]] = [
        {
            "rubric_id": f"rubric:query:{index:03d}",
            "query_rubric_key": row["rubric_key"],
            "origin": "explicit_query",
            "query_span": row["query_span"],
            "requirement": row["requirement"],
            "requirement_type": row["requirement_type"],
            "importance": "core",
            "weight": 1.0,
            "applicable": True,
            "frozen_before_report_input": True,
            "compiler_review": {
                "source_visibility": "query_only",
                "audit": query_rubric_audit_map.get(
                    row["rubric_key"], {}
                ),
            },
        }
        for index, row in enumerate(accepted_query_rubrics, 1)
    ]
    research_units: list[dict[str, Any]] = []
    for check in checks:
        classified = reviews.get(check["check_id"])
        if not classified or not bool(classified.get("include")):
            continue
        requirement = str(classified.get("requirement") or check["requirement"])
        unit_type = str(classified.get("unit_type") or "cross_source_synthesis")
        axis = classified.get("axis")
        if axis != "completeness":
            continue
        compiler_review = {
            "necessity": classified.get("necessity"),
            "answer_leak": classified.get("answer_leak"),
            "route_bound": classified.get("route_bound"),
            "reason_code": classified.get("reason_code"),
            "axis": axis,
            "needs_split": bool(classified.get("needs_split", False)),
        }
        if (
            unit_type != "atomic"
            and not bool(classified.get("answer_leak"))
            and not bool(classified.get("route_bound"))
        ):
            research_units.append(
                {
                    "unit_id": f"research:{check['check_id']}",
                    "legacy_check_id": check["check_id"],
                    "facet_id": check["facet_id"],
                    "unit_type": unit_type,
                    "statement": requirement,
                    "importance": check["tier"],
                    "applicable": check["applicable"],
                    "evidence_required": check["evidence_required"],
                    "depends_on_checks": check["depends_on_checks"],
                    "critical_error_on_contradiction": check[
                        "critical_error_on_contradiction"
                    ],
                    "compiler_review": compiler_review,
                }
            )

    write_jsonl(output_dir / "atomic_facts.jsonl", atomic_units)
    write_jsonl(output_dir / "research_units.jsonl", research_units)
    write_jsonl(output_dir / "rubric_items.jsonl", rubric_items)
    (output_dir / "facets.json").write_text(
        json.dumps(facets, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rubric_legacy_ids: set[str] = set()
    research_legacy_ids = {
        row["legacy_check_id"] for row in research_units
    }
    overlap_ids = sorted(rubric_legacy_ids & research_legacy_ids)
    needs_split_ids = sorted(
        row["check_id"]
        for row in checks
        if bool((reviews.get(row["check_id"]) or {}).get("needs_split"))
    )
    manifest = {
        "schema": "dra_task_evidence_census_transition_v2",
        "task_id": task.get("task_id") or task_world_model.get("task_id"),
        "query": query,
        "compiled_without_report": True,
        "manual_semantic_decisions": 0,
        "compiler_model": judge.model,
        "source_hashes": {
            "task": _hash_json(task),
            "task_world_model": _hash_json(task_world_model),
            "research_test_suite": _hash_json(research_test_suite),
        },
        "counts": {
            "facets": len(facets),
            "atomic_units": len(atomic_units),
            "research_units": len(research_units),
            "rubric_items": len(rubric_items),
            "candidate_checks": len(checks),
        },
        "axis_disjointness_certificate": {
            "rubric_research_overlap_count": len(overlap_ids),
            "rubric_research_overlap_ids": overlap_ids,
            "needs_split_ids": needs_split_ids,
            "passed": not overlap_ids and not needs_split_ids,
            "verification_method": (
                "rubric compiler received query only; completeness compiler "
                "cannot emit rubric items"
            ),
        },
        "formal_eligible": False,
        "formal_eligibility_notes": [
            "transition compiler adapts an existing TWM/RTS rather than a protocol-complete TEC",
            "query-only rubrics have not completed frozen calibration review",
            "coverage and alternative-route certificates are not yet frozen",
            *(
                ["rubric and completeness axes are not disjoint"]
                if overlap_ids
                else []
            ),
            *(
                ["mixed requirements still require report-blind human splitting"]
                if needs_split_ids
                else []
            ),
        ],
    }
    (output_dir / "tec-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "manifest": manifest,
        "facets": facets,
        "atomic_units": atomic_units,
        "research_units": research_units,
        "rubric_items": rubric_items,
    }


__all__ = ["compile_task_manifest"]
