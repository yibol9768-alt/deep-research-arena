#!/usr/bin/env python3
"""Build the frozen Q56 kit-versus-premium-lens evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-cameras-photo-0056-kit-lens-premium-glass-output-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-cameras-photo-0056-kit-lens-premium-glass-output-boundary-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_cameras_photo_0056"
TOPIC = "kit_lens_premium_glass_task_output_value_boundary"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0056/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
PLAN_REL = Path("data/pilot_v3/capture_plans/cand_formal_0056_from_0057.r1.json")
PLAN = json.loads((ROOT / PLAN_REL).read_text(encoding="utf-8"))
EVIDENCE_SPEC = Path(__file__).with_name("evidence_spec.json")
EVIDENCE = json.loads(EVIDENCE_SPEC.read_text(encoding="utf-8"))
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    (
        row["search_id"],
        f"{index:03d}-{row['search_id']}.json",
        row["query"],
        row["required_urls"][0],
    )
    for index, row in enumerate(PLAN["searches"], start=1)
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def typed_verifier(accepted: str) -> dict[str, Any]:
    return {
        "kind": "typed_claim",
        "matcher": "normalized_text",
        "accepted_phrases": [accepted],
        "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"],
    }


def build() -> dict[str, Any]:
    capture_documents = json.loads(
        (CAPTURE / "documents.json").read_text(encoding="utf-8")
    )["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = (
            f"http://localhost:8081/search?capture_run={RUN_ID}"
            f"&request_id={payload['request_id']}"
        )
        documents.append(
            {
                "registry_id": f"reg_search_{search_id}",
                "source_url": source_url,
                "source_type": "search_result",
                "content_sha256": sha256_bytes(data),
                "blob_path": rel(path),
                "in_corpus": True,
            }
        )
        nodes.append(
            {
                "evidence_id": f"search_{search_id}",
                "node_type": "search_result",
                "subject": subject,
                "predicate": "returned",
                "object": [target_url],
                "source_url": source_url,
                "body_support": False,
                "search_snippet_support": True,
                "verifier": {"kind": "search_observation"},
                "metadata": {
                    "discovery_root": True,
                    "discovery_root_policy": "search_result",
                    "topic_cluster": TOPIC,
                },
            }
        )

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append(
            {
                "registry_id": row["registry_id"],
                "source_url": row["source_url"],
                "source_type": row["source_type"],
                "content_sha256": row["content_sha256"],
                "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(),
                "in_corpus": True,
            }
        )
        raw_content_by_url[row["source_url"]] = (
            CAPTURE / row["blob_path"]
        ).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append(
        {
            "registry_id": "reg_case_spec_lens_value_0056",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        search_index = int(item["search_index"])
        source_url = SEARCHES[search_index][3]
        content = raw_content_by_url[source_url]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(
                    f"quote missing from {item['evidence_id']}: {quote!r}"
                )
            spans.append(
                {
                    "support_span_id": f"span_{item['evidence_id']}_{index}",
                    "exact_quote": quote,
                    "occurrence": 0,
                    "support_type": "body",
                }
            )
        nodes.append(
            {
                "evidence_id": item["evidence_id"],
                "node_type": "proposition",
                "subject": item["subject"],
                "predicate": item["predicate"],
                "object": item["object"],
                "source_url": source_url,
                "support_spans": spans,
                "verifier": typed_verifier(item["accepted"]),
                "metadata": {
                    "acceptable_source_roles": [item["role"]],
                    "critical": True,
                    "scope": item["scope"],
                    "topic_cluster": TOPIC,
                },
            }
        )
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append(
            {
                "evidence_id": assertion_id,
                "node_type": "assertion",
                "subject": f"source for {item['subject']}",
                "predicate": "states",
                "object": item["object"],
                "source_url": source_url,
                "support_spans": [
                    {
                        "support_span_id": f"span_{assertion_id}_1",
                        "exact_quote": item["quotes"][0],
                        "occurrence": 0,
                        "support_type": "body",
                    }
                ],
                "verifier": {"kind": "quoted_assertion"},
                "metadata": {"topic_cluster": TOPIC},
            }
        )
        edges.extend(
            [
                {
                    "edge_id": f"edge_assert_{item['evidence_id']}",
                    "source_id": assertion_id,
                    "relation": "ASSERTS",
                    "target_id": item["evidence_id"],
                },
                {
                    "edge_id": f"edge_discover_{item['evidence_id']}",
                    "source_id": item["evidence_id"],
                    "relation": "DISCOVERABLE_FROM",
                    "target_id": f"search_{SEARCHES[search_index][0]}",
                    "discovery_method": "S",
                    "discovery_order": 1,
                },
            ]
        )

    deterministic_nodes = [
        ("bridge_seller_lens_offer_scope", "bridge", "six frozen camera and lens pages", "separates_exact_page_fields_from_current_optical_results", "bind each SKU price rating condition bundle warranty label and claim to its page without converting price or category into a controlled output ranking", "seller_lens_offer_scope_v1"),
        ("bridge_mount_focal_task_scope", "bridge", "Canon APS-C body and exact lens forms", "requires_mount_format_field_of_view_and_task_matching", "map EF or EF-S fit crop field of view focal length aperture autofocus and stabilization to the 4000D and each declared task", "mount_focal_task_scope_v1"),
        ("bridge_optical_design_mechanism_scope", "bridge", "coating and lens aberration mechanisms", "separates_design_tradeoffs_from_premium_labels", "use coating photographic design chromatic aberration and spherical aberration to define tests rather than infer superiority from price aperture Art or L-series labels", "optical_design_mechanism_scope_v1"),
        ("bridge_output_artifact_measurement_scope", "bridge", "vignetting flare OTF and diffraction", "requires_aperture_position_light_scale_and_output_specific_measurement", "measure peripheral falloff flare contrast transfer and diffraction under declared focus aperture frame position processing and final web or print output", "output_artifact_measurement_scope_v1"),
        ("bridge_community_image_workflow_scope", "bridge", "three community images", "retains_author_capture_processing_and_missing_metadata_scope", "keep Andromeda macro and moon images tied to their complete or incomplete workflows rather than treating an attractive image as lens-only value evidence", "community_image_workflow_scope_v1"),
        ("bridge_matched_lens_trial", "bridge", "exact candidates and the actual kit baseline", "defines_a_reversible_same_body_task_and_output_matched_trial", "verify identity condition and compatibility then compare focus keeper artifacts workflow and preference across declared tasks with field of view and output controlled", "matched_lens_trial_v1"),
        ("bridge_lens_value_decision_preparation", "bridge", "lens value evidence matrix", "marks_meaningful_improvement_compatibility_condition_workflow_output_and_cost_gates", "prevent price rating aperture one crop or one community image from overriding a failed or unresolved hard gate", "lens_value_decision_preparation_v1"),
        ("decision_evidence_bounded_lens_purchase", "decision", "lens purchase for the Canon APS-C beginner", "selects_the_lowest_total_cost_exact_passing_lens_or_a_reversible_fallback", "choose only the lowest total cost exact lens that passes every gate and meaningfully improves declared outputs over the kit otherwise keep rent save rerun or defer", "evidence_bounded_lens_purchase_decision_v1"),
    ]
    for evidence_id, node_type, subject, predicate, object_, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    ids = [item["evidence_id"] for item in EVIDENCE]
    derives = {
        "bridge_seller_lens_offer_scope": ids[0:6],
        "bridge_mount_focal_task_scope": ids[0:6] + ids[7:11],
        "bridge_optical_design_mechanism_scope": [ids[6], ids[10], ids[11], ids[12]],
        "bridge_output_artifact_measurement_scope": ids[13:17] + ["bridge_optical_design_mechanism_scope"],
        "bridge_community_image_workflow_scope": ids[17:20],
        "bridge_matched_lens_trial": [
            "bridge_seller_lens_offer_scope",
            "bridge_mount_focal_task_scope",
            "bridge_optical_design_mechanism_scope",
            "bridge_output_artifact_measurement_scope",
            "bridge_community_image_workflow_scope",
        ],
        "bridge_lens_value_decision_preparation": [
            "bridge_seller_lens_offer_scope",
            "bridge_mount_focal_task_scope",
            "bridge_optical_design_mechanism_scope",
            "bridge_output_artifact_measurement_scope",
            "bridge_community_image_workflow_scope",
            "bridge_matched_lens_trial",
        ],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append(
                {
                    "edge_id": f"edge_{source_id}_from_{target_id}",
                    "source_id": source_id,
                    "relation": "DERIVES_FROM",
                    "target_id": target_id,
                }
            )
    for target_id in derives:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id}",
                "source_id": "decision_evidence_bounded_lens_purchase",
                "relation": "REQUIRES",
                "target_id": target_id,
            }
        )

    return {
        "schema_version": "evidence_graph_inventory_v1",
        "corpus_snapshot": SNAPSHOT,
        "documents": documents,
        "nodes": nodes,
        "edges": edges,
        "support_spans": [],
    }


def main() -> None:
    inventory = build()
    OUT.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": rel(OUT),
                "documents": len(inventory["documents"]),
                "nodes": len(inventory["nodes"]),
                "edges": len(inventory["edges"]),
                "critical_evidence": len(EVIDENCE),
                "sha256": sha256_bytes(OUT.read_bytes()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
