#!/usr/bin/env python3
"""Build the frozen Q28 evidence inventory from the atomic capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-smartphones-0028-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0028/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-smartphones-0028-20260716-r1"
TOPIC = "phone_case_four_year_evidence_boundary"


SEARCHES = [
    (
        "casekoo",
        "001-shopping-clear-case-claim-snapshot.json",
        "current clear-case seller-claim snapshot",
        "http://localhost:7770/casekoo-magnetic-clear-for-iphone-13-pro-max-case-never-yellow-stronger-magnetic-power-military-level-drop-protection-with-magsafe-shockproof-slim-thin-cover-6-7-inch-2021-clear.html",
    ),
    (
        "clear_two_year",
        "002-forum-clear-two-year-observation.json",
        "unnamed clear-case two-year observation",
        "http://localhost:9999/f/iphone/40968/yellow-case-is-it-fr-getting-yellow-after-god-damn-2-months",
    ),
    (
        "leather_symmetry",
        "003-forum-leather-two-year-and-symmetry-three-year.json",
        "leather-corner and OtterBox Symmetry duration observations",
        "http://localhost:9999/f/iphone/41138/i-found-walmart-s-6-88-onn-iphone-14-pro-gel-case-pretty",
    ),
    (
        "bifl_reports",
        "004-forum-bifl-protection-and-failure-reports.json",
        "Spigen and OtterBox owner reports",
        "http://localhost:9999/f/BuyItForLife/75603/alternatives-to-otterbox-defender",
    ),
    (
        "casetify_year",
        "005-forum-casetify-one-year-aesthetic-protection.json",
        "Casetify one-year appearance and drop observation",
        "http://localhost:9999/f/iphone/62383/case-recs-for-iphone-14-pro-max-and-iphone-14",
    ),
    (
        "polycarbonate",
        "006-wiki-polycarbonate-uv-yellowing.json",
        "polycarbonate ultraviolet-yellowing mechanism",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Polycarbonate",
    ),
    (
        "tpu",
        "007-wiki-tpu-formulation-differences.json",
        "TPU formulation and non-yellowing distinctions",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Thermoplastic_polyurethane",
    ),
    (
        "polyurethane",
        "008-wiki-polyurethane-sticky-degradation.json",
        "polyurethane sticky-degradation mechanism",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Conservation_and_restoration_of_plastic_objects",
    ),
    (
        "leather",
        "009-wiki-leather-deterioration-boundary.json",
        "general leather-deterioration boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Conservation_and_restoration_of_leather_objects",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "ev_casekoo_seller_claims",
        "node_type": "attribute",
        "subject": "frozen CASEKOO clear-case listing",
        "predicate": "advertises_snapshot",
        "object": "25.99 dollars, PC and TPU construction, a 99.9 percent anti-yellow claim, military-level drop protection, and one-year replacement",
        "source_url": SEARCHES[0][3],
        "search_id": "casekoo",
        "role": "product",
        "scope": "seller_claim_snapshot_not_longevity_or_drop_test",
        "quotes": [
            "In stock SKU B09HKLWYJF Be the first to review this product $25.99 Qty Add to Cart Add to Wish List Add to Compare",
            "2. Free replacement without return within 1 year",
            "【Never Yellow & Showcases Clear】: Using high-grade Bayer's ultra-clear TPU and PC material, allowing you to admire the original sublime beauty of your phone while won't get oily when used. \"Never yellow\" thanks to the anti-yellow coating which can effectively resist 99.9% of yellowing caused by ultraviolet rays and sweat.",
            "【Military Level Drop Protection】: Equipped with Flex-impact Cushion Tech to disperse severe shocks, guaranteed with [MIL-STD-810G] standard. The backplane is made with rigid polycarbonate and flexible shockproof TPU bumpers around the edge to create tough protection.",
        ],
        "accepted": "The frozen listing advertises a 25.99 dollar PC-and-TPU case, anti-yellow and military-level drop claims, and one-year replacement; these are seller statements rather than four-year results.",
    },
    {
        "evidence_id": "prop_clear_two_year_scope",
        "node_type": "proposition",
        "subject": "unnamed clear-case owner",
        "predicate": "reports_scoped_outcome",
        "object": "the same unnamed clear case remained clear for two years, with no material, exposure, or protection outcome identified",
        "source_url": SEARCHES[1][3],
        "search_id": "clear_two_year",
        "role": "community",
        "scope": "two_year_clarity_only_unnamed_case",
        "quotes": [
            "Im about to change from android to ios,I got the same clear case in my phone for 2 years,and it's still clear as hell,im seeing a lot of people complaining about their clear cases being \"yellow\",is it a common thing in the iPhone case industry?"
        ],
        "accepted": "One author reports an unnamed clear case still clear after two years, but supplies no exact model, material, exposure history, or protection result.",
    },
    {
        "evidence_id": "prop_apple_leather_two_year_scope",
        "node_type": "proposition",
        "subject": "Apple Leather Cases used by one participant",
        "predicate": "reports_failure_time",
        "object": "about two years before that participant degrades the corners",
        "source_url": SEARCHES[2][3],
        "search_id": "leather_symmetry",
        "role": "community",
        "scope": "about_two_year_corner_failure_not_protection_test",
        "quotes": [
            "I dislike the feeling of plastic, so even though they only last about two years before I inevitably degrade the corners, it’s the Apple Leather Cases with metal buttons for me."
        ],
        "accepted": "A participant reports Apple Leather Cases lasting about two years before that participant degrades the corners; this is not an intact year-four or controlled protection result.",
    },
    {
        "evidence_id": "prop_symmetry_three_year_scope",
        "node_type": "proposition",
        "subject": "one OtterBox Symmetry case",
        "predicate": "reports_failure_time",
        "object": "the thin silicone strip near the charging port broke after about three years of being used to pull the phone from a pocket",
        "source_url": SEARCHES[2][3],
        "search_id": "leather_symmetry",
        "role": "community",
        "scope": "about_three_year_geometry_and_use_failure_not_year_four",
        "quotes": [
            "I used to pull my iPhone X out of my pocket using the tiny strip of silicone between the charging port and the screen of the Otterbox Symmetry case. After about 3 years, the case broke at that point. I think that was a good long run."
        ],
        "accepted": "One OtterBox Symmetry owner reports that a thin silicone strip used to pull the phone from a pocket broke after about three years.",
    },
    {
        "evidence_id": "prop_spigen_duration_scope",
        "node_type": "proposition",
        "subject": "brand-level Spigen owner reports",
        "predicate": "report_scoped_protection",
        "object": "one Pixel user reports many drops without a cracked screen while describing about four years as a Pixel user, and another Samsung user says a Spigen was used for years without problems; neither identifies an exact model and the first does not establish one-case continuity",
        "source_url": SEARCHES[3][3],
        "search_id": "bifl_reports",
        "role": "community",
        "scope": "brand_level_imprecise_duration_and_ambiguous_continuity",
        "quotes": [
            "Been a Pixel person for maybe 4 years now, currently have the 7 Pro. I use Spigen off Amazon, affordable and seems to work well. I've dropped my phone plenty, haven't ever had a cracked screen or anything",
            "I see... If you want the best value, it's Spigen for sure. It's not the best case, but it's really rugged and resilient. I had it for years on my Samsung without any problem. My model didn't have the plastic screen cover, I used a separate screen protector",
        ],
        "accepted": "The Spigen reports are brand-level and do not provide an exact model with a precise continuous four-year observation; one reports many drops without a cracked screen and another says only 'for years.'",
    },
    {
        "evidence_id": "prop_otterbox_failure_warranty_scope",
        "node_type": "proposition",
        "subject": "one OtterBox owner",
        "predicate": "reports_failure_and_service",
        "object": "a difficult warranty attempt, a torn charging-port cover, separating rubber shell, and one cracked plastic part",
        "source_url": SEARCHES[3][3],
        "search_id": "bifl_reports",
        "role": "community",
        "scope": "uncontrolled_owner_failure_and_warranty_report",
        "quotes": [
            "I've tried to use the warranty before and it's difficult to say the least. I fidget too much with the charging port cover and it inevitably rips off, same goes for the rubber covering around the base which causes the rubber shell to separate. The plastic has also gotten cracked on me once in a backpack."
        ],
        "accepted": "One OtterBox owner reports difficult warranty use, port-cover tearing, rubber-shell separation, and a cracked plastic part, without a precise model or duration.",
    },
    {
        "evidence_id": "prop_casetify_one_year_scope",
        "node_type": "proposition",
        "subject": "one Casetify case",
        "predicate": "reports_scoped_appearance_and_drop_outcomes",
        "object": "after more than one year and multiple uncontrolled drops, the case was undinged and its graphics remained bright and unscratched, but the exact model was not stated",
        "source_url": SEARCHES[4][3],
        "search_id": "casetify_year",
        "role": "community",
        "scope": "more_than_one_year_brand_level_uncontrolled_report",
        "quotes": [
            "Don’t know what the bad reviews are saying but I’ve had a Casetify case on my phone for over a year. No problems at all with it. I’ve dropped my phone multiple times and the case isn’t even dinged. The graphics on the case are still bright and are not scratched."
        ],
        "accepted": "A Casetify owner reports more than one year, multiple drops, an undinged case, and bright unscratched graphics, but gives no exact model or standardized drop conditions.",
    },
    {
        "evidence_id": "prop_polycarbonate_uv_scope",
        "node_type": "proposition",
        "subject": "polycarbonate",
        "predicate": "has_uv_degradation_boundary",
        "object": "it can yellow under ultraviolet exposure, while stabilizers or surface coatings can improve weathering resistance",
        "source_url": SEARCHES[5][3],
        "search_id": "polycarbonate",
        "role": "concept",
        "scope": "general_material_mechanism_not_case_lifetime",
        "quotes": [
            "However, automotive headlamps require outer surface coatings because of its low scratch resistance and susceptibility to ultraviolet degradation (yellowing).",
            "Standard polycarbonate resins are not suitable for long term exposure to UV radiation.",
            "To overcome this, the primary resin can have UV stabilisers added.",
        ],
        "accepted": "Polycarbonate is susceptible to ultraviolet degradation and yellowing, and stabilizers or coatings can improve resistance; this does not predict one phone case's lifetime.",
    },
    {
        "evidence_id": "prop_tpu_formulation_scope",
        "node_type": "proposition",
        "subject": "thermoplastic polyurethane formulations",
        "predicate": "differ_in_hydrolysis_and_colour_stability",
        "object": "polyether TPU is selected for additional hydrolysis resistance, while aliphatic TPU is used for stable light color and non-yellowing performance",
        "source_url": SEARCHES[6][3],
        "search_id": "tpu",
        "role": "concept",
        "scope": "formulation_distinction_not_product_identity_or_lifetime",
        "quotes": [
            "Polyether-based TPU in cases where additional excellent hydrolysis and microbial resistance is required, as well as in cases where extreme low-temperature flexibility is important.",
            "When stable light colour and non-yellowing performance are required, aliphatic TPU (ATPU) based on aliphatic isocyanates is used.",
        ],
        "accepted": "TPU formulation matters: polyether TPU offers additional hydrolysis resistance and aliphatic TPU is used for stable light color, so a generic TPU label is insufficient.",
    },
    {
        "evidence_id": "prop_polyurethane_sticky_scope",
        "node_type": "proposition",
        "subject": "polyurethane deterioration",
        "predicate": "can_produce_surface_and_strength_failures",
        "object": "polyurethane can become yellowed, brittle, sticky, and crumbly, and urethane-containing condensation plastics can weaken through hydrolysis",
        "source_url": SEARCHES[7][3],
        "search_id": "polyurethane",
        "role": "concept",
        "scope": "general_conservation_mechanism_not_phone_case_diagnosis",
        "quotes": [
            "Polyurethane yellowed, brittle, sticky, crumbles",
            "condensation plastics like esters , amides , and urethanes are subject to hydrolysis with subsequent weakening",
        ],
        "accepted": "A general conservation source lists polyurethane as yellowing, becoming brittle, sticky, and crumbly and notes hydrolysis weakening; it does not diagnose an exact phone-case coating.",
    },
    {
        "evidence_id": "prop_leather_deterioration_scope",
        "node_type": "proposition",
        "subject": "leather and leather finishes",
        "predicate": "have_environment_and_handling_boundaries",
        "object": "temperature and humidity variation can contribute to cracks, handling affects deterioration, and dressings can create tacky surfaces",
        "source_url": SEARCHES[8][3],
        "search_id": "leather",
        "role": "concept",
        "scope": "general_leather_conservation_not_phone_case_corner_causation",
        "quotes": [
            "If the humidity is at a level of about 40% with a fluctuation of temperature, cracks can occur along the surface.",
            "Handling The degree of handling and access will play a large role in the decisions of care and treatment, as well as display locations.",
            "Dressing or finishes may absorb dirt creating a tacky surface.",
        ],
        "accepted": "General leather-conservation evidence identifies environmental, handling, cracking, and finish risks, but cannot by itself explain a phone-case corner failure or its lifetime.",
    },
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
    extract_by_url = {row["source_url"]: row for row in capture_documents}
    search_by_id: dict[str, dict[str, Any]] = {}
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        request_id = payload["request_id"]
        source_url = (
            "http://localhost:8081/search?capture_run="
            f"v3-corpus-formal-smartphones-0028-20260716-r1&request_id={request_id}"
        )
        search_by_id[search_id] = {
            "source_url": source_url,
            "target_url": target_url,
        }
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

    documents.append(
        {
            "registry_id": "reg_case_spec_phone_case_0028",
            "source_url": "http://case-spec.local/dra_v3_formal_smartphones_0028",
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    assertion_targets: list[str] = []
    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            count = content.count(quote)
            if count < 1:
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
        node = {
            key: item[key]
            for key in (
                "evidence_id",
                "node_type",
                "subject",
                "predicate",
                "object",
                "source_url",
            )
        }
        node.update(
            {
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
        nodes.append(node)
        edges.append(
            {
                "edge_id": f"edge_discover_{item['evidence_id']}",
                "source_id": item["evidence_id"],
                "relation": "DISCOVERABLE_FROM",
                "target_id": f"search_{item['search_id']}",
                "discovery_method": "S",
                "discovery_order": 1,
            }
        )
        if item["node_type"] == "proposition":
            assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
            assertion_targets.append(item["evidence_id"])
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
            edges.append(
                {
                    "edge_id": f"edge_assert_{item['evidence_id']}",
                    "source_id": assertion_id,
                    "relation": "ASSERTS",
                    "target_id": item["evidence_id"],
                }
            )

    case_source = "http://case-spec.local/dra_v3_formal_smartphones_0028"
    deterministic_nodes = [
        (
            "mechanism_seller_material_claim_audit",
            "mechanism",
            "seller claims and material mechanisms",
            "separate",
            "current product claims from general material mechanisms and both from a demonstrated product lifetime",
            "seller_claim_snapshot_v1",
        ),
        (
            "mechanism_failure_mode_mapping",
            "mechanism",
            "clear, leather, soft-touch, and geometry failures",
            "map",
            "yellowing, tackiness, corner wear, and thin-strip breakage to distinct scoped evidence without transferring lifetime claims",
            "material_mechanism_boundaries_v1",
        ),
        (
            "mechanism_owner_report_scope",
            "mechanism",
            "owner observations",
            "preserve",
            "actual durations, model specificity, exposure gaps, appearance outcomes, and uncontrolled protection outcomes",
            "community_duration_and_outcome_scope_v1",
        ),
        (
            "bridge_four_year_evidence_boundary",
            "bridge",
            "year-four purchase claim",
            "requires",
            "one exact model observed for four years with both acceptable appearance and protection, which the frozen evidence lacks",
            "four_year_claim_audit_v1",
        ),
        (
            "bridge_conditional_monitoring_protocol",
            "bridge",
            "conditional purchase",
            "requires",
            "exact-model verification plus baseline photographs, periodic fit and surface checks, drop logging, and explicit replacement triggers",
            "conditional_purchase_and_monitoring_v1",
        ),
        (
            "decision_evidence_bounded_case_selection",
            "decision",
            "four-year phone-case decision",
            "selects_admissible_set",
            "no proven year-four winner; at most the listed clear case can be a conditional monitored trial rather than a four-year recommendation",
            "evidence_bounded_case_decision_v1",
        ),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    derives: dict[str, list[str]] = {
        "mechanism_seller_material_claim_audit": [
            "ev_casekoo_seller_claims",
            "prop_polycarbonate_uv_scope",
            "prop_tpu_formulation_scope",
        ],
        "mechanism_failure_mode_mapping": [
            "prop_clear_two_year_scope",
            "prop_apple_leather_two_year_scope",
            "prop_symmetry_three_year_scope",
            "prop_polyurethane_sticky_scope",
            "prop_leather_deterioration_scope",
        ],
        "mechanism_owner_report_scope": [
            "prop_clear_two_year_scope",
            "prop_apple_leather_two_year_scope",
            "prop_symmetry_three_year_scope",
            "prop_spigen_duration_scope",
            "prop_otterbox_failure_warranty_scope",
            "prop_casetify_one_year_scope",
        ],
        "bridge_four_year_evidence_boundary": [
            "mechanism_seller_material_claim_audit",
            "mechanism_failure_mode_mapping",
            "mechanism_owner_report_scope",
        ],
        "bridge_conditional_monitoring_protocol": [
            "mechanism_seller_material_claim_audit",
            "mechanism_failure_mode_mapping",
            "mechanism_owner_report_scope",
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
    for target_id in [
        "mechanism_seller_material_claim_audit",
        "mechanism_failure_mode_mapping",
        "mechanism_owner_report_scope",
        "bridge_four_year_evidence_boundary",
        "bridge_conditional_monitoring_protocol",
    ]:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id}",
                "source_id": "decision_evidence_bounded_case_selection",
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
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
