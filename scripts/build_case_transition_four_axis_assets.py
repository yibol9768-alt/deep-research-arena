#!/usr/bin/env python3
"""Build report-blind transition assets for a compiled DRA v3 case.

This utility is intentionally a diagnostic bridge.  It converts the frozen
case evidence catalog into:

* a field-level Task World Model;
* a query-requirement Research Test Suite; and
* a small seed corpus for the on-demand frozen-world Fact resolver.

It never reads an agent report.  Witness URLs remain answerability witnesses,
not allowlists; the runtime Fact resolver may still retrieve any registered
sandbox page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source_role(source_type: str) -> str:
    return {
        "magento": "product_primary",
        "product": "product_primary",
        "postmill": "community_general",
        "forum": "community_general",
        "wikipedia": "technical_reference",
    }.get(source_type, "unknown")


def seed_source_type(source_type_value: str) -> str:
    return {
        "magento": "product",
        "postmill": "forum",
    }.get(source_type_value, source_type_value or "unknown")


def iter_leaves(value: Any, prefix: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from iter_leaves(value[key], (*prefix, str(key)))
        return
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            yield prefix, value
            return
        for index, item in enumerate(value):
            yield from iter_leaves(item, (*prefix, str(index)))
        return
    yield prefix, value


def display_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def build_assertions(case: dict[str, Any]) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    for source in case.get("evidence_sources", []):
        evidence_id = str(source.get("evidence_id") or "")
        if not evidence_id:
            continue
        subject = str(source.get("subject") or evidence_id)
        predicate = str(source.get("predicate") or "states")
        source_url = str(source.get("source_url") or "")
        span_ids = [
            str(row.get("support_span_id") or "")
            for row in source.get("support_spans", [])
            if row.get("support_span_id")
        ]
        leaves = list(iter_leaves(source.get("object")))
        if not leaves:
            phrases = (source.get("verifier") or {}).get("accepted_phrases") or []
            if phrases:
                leaves = [(("statement",), str(phrases[0]))]
        for index, (path, value) in enumerate(leaves, 1):
            field = ".".join(path) if path else "value"
            assertion_id = f"{evidence_id}__{index:03d}"
            statement = (
                f"Frozen {source.get('source_type', 'source')} evidence for "
                f"{subject}: {predicate}; {field} = {display_value(value)}."
            )
            assertions.append(
                {
                    "assertion_id": assertion_id,
                    "statement": statement,
                    "modality": str(source.get("node_type") or "frozen_evidence"),
                    "source_role": source_role(str(source.get("source_type") or "")),
                    "known_support_span_ids": span_ids,
                    "answerability_witness_urls": [source_url] if source_url else [],
                    "limitations": [],
                    "verification_status": "compiled_from_frozen_case_evidence_catalog",
                }
            )
    return assertions


def build_twm(case: dict[str, Any], assertions: list[dict[str, Any]]) -> dict[str, Any]:
    case_hash = digest(canonical_json(case))
    return {
        "schema": "dra_task_world_model_v1",
        "task_id": case["task_id"],
        "world_sha256": case_hash,
        "construction_policy": "report_blind_case_catalog_field_expansion_v1",
        "builder": {
            "name": "build_case_transition_four_axis_assets",
            "version": "v1",
            "status": "diagnostic_transition",
            "case_sha256": case_hash,
            "report_visible": False,
        },
        "assertions": assertions,
        "relations": [],
        "conflict_clusters": [],
        "bounded_unknowns": [],
        "extraction_trace": [
            {
                "assertion_id": row["assertion_id"],
                "source": "compiled_case.evidence_sources",
            }
            for row in assertions
        ],
    }


def build_rts(case: dict[str, Any], twm: dict[str, Any]) -> dict[str, Any]:
    facets: list[dict[str, Any]] = []
    for index, requirement in enumerate(case.get("query_requirements", []), 1):
        requirement_id = str(requirement.get("requirement_id") or f"Q{index}")
        text = str(requirement.get("text") or "").strip()
        if not text:
            continue
        facets.append(
            {
                "facet_id": f"F_{requirement_id}",
                "label": text,
                "units": [
                    {
                        "unit_id": f"U_{requirement_id}",
                        "checks": [
                            {
                                "check_id": f"K_{requirement_id}",
                                "content_contract": text,
                                "tier": "core",
                                "applicable": bool(requirement.get("required", True)),
                                "depends_on_checks": [],
                                "evidence_exempt": False,
                                "critical_error_on_contradiction": False,
                            }
                        ],
                    }
                ],
            }
        )
    if not facets:
        target = str((case.get("generator_view") or {}).get("target") or "Complete the requested research task.")
        facets = [
            {
                "facet_id": "F_TASK",
                "label": target,
                "units": [
                    {
                        "unit_id": "U_TASK",
                        "checks": [
                            {
                                "check_id": "K_TASK",
                                "content_contract": target,
                                "tier": "core",
                                "applicable": True,
                                "depends_on_checks": [],
                                "evidence_exempt": False,
                                "critical_error_on_contradiction": False,
                            }
                        ],
                    }
                ],
            }
        ]
    return {
        "schema": "dra_research_test_suite_v1",
        "task_id": case["task_id"],
        "aggregation": "facet_macro_unit_macro_check_mean",
        "compiler": {
            "name": "build_case_transition_four_axis_assets",
            "version": "v1",
            "status": "diagnostic_transition",
            "task_world_model_sha256": digest(canonical_json(twm)),
            "report_visible": False,
        },
        "facets": facets,
        "evidence_contracts": [],
        "search_certificates": [],
        "mock_evidence_matchers": {},
        "mock_semantic_contracts": {},
        "full_pass_contract": {},
    }


def build_graph(case: dict[str, Any], graph_dir: Path) -> dict[str, Any]:
    graph_dir.mkdir(parents=True, exist_ok=True)
    blobs_dir = graph_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for index, source in enumerate(case.get("evidence_sources", []), 1):
        source_url = str(source.get("source_url") or "")
        if not source_url:
            continue
        phrases = (source.get("verifier") or {}).get("accepted_phrases") or []
        blob_payload = {
            "title": str(source.get("evidence_id") or f"source-{index}"),
            "text": "\n".join(str(value) for value in phrases),
            "subject": source.get("subject"),
            "predicate": source.get("predicate"),
            "object": source.get("object"),
            "source_url": source_url,
        }
        body = canonical_json(blob_payload)
        content_sha256 = digest(body)
        (blobs_dir / content_sha256).write_bytes(body)
        entries.append(
            {
                "registry_id": f"case-source-{index:04d}",
                "source_url": source_url,
                "source_type": seed_source_type(str(source.get("source_type") or "")),
                "content_sha256": content_sha256,
            }
        )
    registry = {
        "schema": "dra_transition_fact_seed_registry_v1",
        "task_id": case["task_id"],
        "entries": entries,
    }
    write_json(graph_dir / "corpus_registry.json", registry)
    manifest = {
        "schema": "dra_transition_fact_seed_manifest_v1",
        "task_id": case["task_id"],
        "case_sha256": digest(canonical_json(case)),
        "corpus_registry_sha256": digest(canonical_json(registry)),
        "entry_count": len(entries),
        "world_boundary": False,
        "report_visible": False,
    }
    write_json(graph_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    case = json.loads(args.case.read_text(encoding="utf-8"))
    assertions = build_assertions(case)
    twm = build_twm(case, assertions)
    rts = build_rts(case, twm)
    output_dir = args.output_dir
    write_json(output_dir / "task-world-model.json", twm)
    write_json(output_dir / "research-test-suite.json", rts)
    graph_manifest = build_graph(case, output_dir / "graph")
    summary = {
        "task_id": case["task_id"],
        "case": str(args.case.resolve()),
        "output_dir": str(output_dir.resolve()),
        "assertion_count": len(assertions),
        "facet_count": len(rts["facets"]),
        "seed_entry_count": graph_manifest["entry_count"],
        "report_visible": False,
        "formal_eligible": False,
        "status": "diagnostic_transition",
    }
    write_json(output_dir / "build-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
