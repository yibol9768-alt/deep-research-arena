#!/usr/bin/env python3
"""Build the frozen Q54 compact-camera feedback evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-cameras-photo-0054-retailer-rating-user-fit-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-cameras-photo-0054-retailer-rating-user-fit-boundary-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_cameras_photo_0054"
TOPIC = "budget_compact_retailer_rating_enthusiast_scope_user_fit"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0054/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    ("sony_dscw80", "001-shopping-sony-dscw80-high-rating-old-model.json", "Sony DSC-W80 frozen offer", "http://localhost:7770/sony-cybershot-dscw80-7-2mp-digital-camera-with-3x-optical-zoom-and-super-steady-shot-silver-old-model.html"),
    ("hp_m447", "002-shopping-hp-m447-rating-printer-bundle.json", "HP M447 frozen offer", "http://localhost:7770/hp-m447-photosmart-compact-photo-studio-digital-camera-with-printer.html"),
    ("canon_elph300", "003-shopping-canon-elph-300-rating.json", "Canon ELPH 300 HS frozen offer", "http://localhost:7770/canon-powershot-elph-300-hs-12-1-mp-digital-camera-black.html"),
    ("kodak_dx4530", "004-shopping-kodak-dx4530-rating.json", "Kodak DX4530 frozen offer", "http://localhost:7770/kodak-easyshare-dx4530-5mp-digital-camera-w-3x-optical-zoom.html"),
    ("sony_w800", "005-shopping-sony-w800-rating-bundle.json", "Sony W800 frozen bundle offer", "http://localhost:7770/sony-cyber-shot-dsc-w800-digital-camera-black-deal-expo-essential-accessories-bundle.html"),
    ("point_shoot", "006-wiki-point-and-shoot-simple-operation.json", "point-and-shoot simple-operation intent", "http://localhost:8090/content/wikipedia_en_all_nopic/Point-and-shoot_camera"),
    ("star_rating", "007-wiki-star-rating-scale.json", "star rating scale", "http://localhost:8090/content/wikipedia_en_all_nopic/Star_(classification)"),
    ("self_selection", "008-wiki-self-selection-bias.json", "self-selection bias", "http://localhost:8090/content/wikipedia_en_all_nopic/Self-selection_bias"),
    ("usability", "009-wiki-usability-testing-real-user-task.json", "real-user usability testing", "http://localhost:8090/content/wikipedia_en_all_nopic/Usability_testing"),
    ("image_quality", "010-wiki-image-quality-subjective-objective.json", "subjective and objective image quality", "http://localhost:8090/content/wikipedia_en_all_nopic/Image_quality"),
    ("optical_aberration", "011-wiki-optical-aberration-blur.json", "optical aberration", "http://localhost:8090/content/wikipedia_en_all_nopic/Optical_aberration"),
    ("shutter_lag", "012-wiki-shutter-lag-action-timing.json", "shutter lag", "http://localhost:8090/content/wikipedia_en_all_nopic/Shutter_lag"),
    ("review_site", "013-wiki-review-site-user-professional-scope.json", "user and professional review authorship", "http://localhost:8090/content/wikipedia_en_all_nopic/Review_site"),
    ("compact_market", "014-forum-low-end-compact-market-smartphones.json", "low-end compact market search result", "http://localhost:9999/f/gadgets/61325/panasonic-nikon-quit-developing-low-end-compact-digital"),
    ("phone_positive", "015-forum-phone-camera-positive-user-opinion.json", "one positive phone-camera report", "http://localhost:9999/f/iphone/41144/an-android-users-opinions-of-the-iphone-14-pro-max"),
    ("phone_processing", "016-forum-phone-camera-processing-complaint.json", "one phone-processing complaint", "http://localhost:9999/f/iphone/106073/iphone-14-pro-camera-driving-me-insane"),
    ("phone_use_case", "017-forum-use-case-older-phone-product-photos.json", "one use-case-specific phone request", "http://localhost:9999/f/iphone/40999/which-older-model-has-the-best-camera"),
]


def ev(
    evidence_id: str,
    subject: str,
    predicate: str,
    object_: str,
    search_index: int,
    role: str,
    scope: str,
    quotes: list[str],
    accepted: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "source_url": SEARCHES[search_index][3],
        "search_id": SEARCHES[search_index][0],
        "role": role,
        "scope": scope,
        "quotes": quotes,
        "accepted": accepted,
    }


# Keeping the reviewed evidence table separate makes every authored phrase
# and exact support quote independently inspectable as JSON.
EVIDENCE_SPEC = Path(__file__).with_name("evidence_spec.json")
EVIDENCE = [
    ev(
        item["evidence_id"],
        item["subject"],
        item["predicate"],
        item["object"],
        item["search_index"],
        item["role"],
        item["scope"],
        item["quotes"],
        item["accepted"],
    )
    for item in json.loads(EVIDENCE_SPEC.read_text(encoding="utf-8"))
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
            "registry_id": "reg_case_spec_clean_label_snacks_0051",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
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
                "source_url": item["source_url"],
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
                "source_url": item["source_url"],
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
                    "target_id": f"search_{item['search_id']}",
                    "discovery_method": "S",
                    "discovery_order": 1,
                },
            ]
        )

    deterministic_nodes = [
        ("bridge_seller_rating_offer_scope", "bridge", "five frozen compact-camera seller pages", "audits_page_bound_rating_review_count_and_price_fields", "bind every aggregate review count price model and bundle phrase to its exact frozen page without inferring current condition recipient usability or performance", "seller_rating_offer_scope_v1"),
        ("bridge_rating_population_boundary", "bridge", "retailer ratings and reviewer populations", "separates_scale_authorship_and_self_selection_from_universal_fit", "treat star aggregates as page-bound rating scales from an unknown participating population rather than representative optical usability or recipient-fit probabilities", "rating_population_self_selection_boundary_v1"),
        ("bridge_point_shoot_usability_boundary", "bridge", "point-and-shoot simplicity and recipient usability", "separates_category_design_intent_from_observed_user_task_success", "retain simple-operation category intent but require observation of the intended recipient performing intended camera transfer and output tasks", "point_shoot_recipient_usability_boundary_v1"),
        ("bridge_image_quality_lens_lag_boundary", "bridge", "image quality optical aberration and shutter lag", "maps_technical_criticisms_to_declared_tasks_outputs_and_measurements", "use perceptual and objective image quality lens aberration and trigger delay as test dimensions without diagnosing an exact unit or declaring a category winner", "image_quality_lens_lag_scope_v1"),
        ("bridge_community_phone_scope", "bridge", "three substantive phone-camera community pages", "retains_author_device_task_and_time_scope", "keep positive negative and use-case-specific phone reports scoped and compare only the mother's actual phone with the exact candidate", "community_phone_claim_scope_v1"),
        ("bridge_feedback_reconciliation", "bridge", "retailer satisfaction and enthusiast criticism", "reconciles_feedback_by_population_task_output_metric_and_threshold", "map each claim to device reviewer task output metric and threshold so both crowds may be locally valid while neither transfers automatically to the gift decision", "feedback_reconciliation_matrix_v1"),
        ("bridge_recipient_matched_trial", "bridge", "same-recipient compact-versus-phone trial", "requires_exact_offer_verification_and_repeated_matched_tasks", "verify identity condition accessories workflow returns and cost then observe the mother using both devices on matched garden indoor moving-child transfer and intended-output tasks with predeclared gates", "recipient_matched_trial_v1"),
        ("bridge_camera_decision_preparation", "bridge", "evidence-bounded compact-camera gift", "combines_claim_scope_exact_offer_and_recipient_trial_gates", "build claim-to-task and pass fail unresolved tables where no aggregate price technical term anecdote or isolated crop compensates for a failed hard gate", "camera_feedback_decision_preparation_v1"),
        ("decision_evidence_bounded_compact_gift", "decision", "budget compact-camera gift", "selects_a_verified_camera_only_if_it_beats_the_actual_phone_on_recipient_matched_gates", "buy only one verified exact returnable camera if it passes recipient usability keeper intended-output workflow carry and cost gates with a meaningful advantage over her actual phone otherwise improve the phone workflow choose printing support rerun or defer", "evidence_bounded_compact_gift_decision_v1"),
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

    products = [
        "prop_sony_dscw80_offer_scope",
        "prop_hp_m447_offer_scope",
        "prop_canon_elph300_offer_scope",
        "prop_kodak_dx4530_offer_scope",
        "prop_sony_w800_offer_scope",
    ]
    derives = {
        "bridge_seller_rating_offer_scope": products,
        "bridge_rating_population_boundary": [
            "prop_star_rating_scale_scope",
            "prop_self_selection_bias_scope",
            "prop_review_site_authorship_scope",
        ],
        "bridge_point_shoot_usability_boundary": [
            "prop_point_shoot_simple_operation_scope",
            "prop_usability_testing_scope",
        ],
        "bridge_image_quality_lens_lag_boundary": [
            "prop_image_quality_assessment_scope",
            "prop_optical_aberration_scope",
            "prop_shutter_lag_scope",
        ],
        "bridge_community_phone_scope": [
            "prop_phone_positive_experience_scope",
            "prop_phone_processing_complaint_scope",
            "prop_phone_use_case_request_scope",
        ],
        "bridge_feedback_reconciliation": [
            "bridge_seller_rating_offer_scope",
            "bridge_rating_population_boundary",
            "bridge_point_shoot_usability_boundary",
            "bridge_image_quality_lens_lag_boundary",
            "bridge_community_phone_scope",
        ],
        "bridge_recipient_matched_trial": [
            "bridge_seller_rating_offer_scope",
            "bridge_rating_population_boundary",
            "bridge_point_shoot_usability_boundary",
            "bridge_image_quality_lens_lag_boundary",
            "bridge_community_phone_scope",
        ],
        "bridge_camera_decision_preparation": [
            "bridge_seller_rating_offer_scope",
            "bridge_rating_population_boundary",
            "bridge_point_shoot_usability_boundary",
            "bridge_image_quality_lens_lag_boundary",
            "bridge_community_phone_scope",
            "bridge_feedback_reconciliation",
            "bridge_recipient_matched_trial",
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
                "source_id": "decision_evidence_bounded_compact_gift",
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
