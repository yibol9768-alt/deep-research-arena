#!/usr/bin/env python3
"""Build the frozen Q35 console-generation value-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-gaming-0035-console-generation-value-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0035/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-gaming-0035-console-generation-value-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-gaming-0035-console-generation-value-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_gaming_0035"
TOPIC = "console_generation_value_and_ecosystem_boundary"


SEARCHES = [
    (
        "ps4_pro_bundle",
        "001-shopping-ps4-pro-rdr2-bundle-snapshot.json",
        "PS4 Pro Red Dead Redemption 2 bundle seller snapshot",
        "http://localhost:7770/playstation-4-pro-1tb-console-red-dead-redemption-2-bundle-discontinued.html",
    ),
    (
        "ps4_controller",
        "002-shopping-ps4-compatible-controller-snapshot.json",
        "seller-titled PS4 compatible controller snapshot",
        "http://localhost:7770/ps4-controller-dualshock-4-wireless-controller-for-gaming-controller-compatible-with-playstation-4-slim-pro-console-black-white.html",
    ),
    (
        "playstation_comparison",
        "003-wiki-playstation-console-comparison.json",
        "PlayStation console hardware comparison table",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Comparison_of_PlayStation_consoles",
    ),
    (
        "generation_history",
        "004-wiki-console-generation-history.json",
        "console-generation history and boundary concept",
        "http://localhost:8090/content/wikipedia_en_all_nopic/History_of_video_game_consoles",
    ),
    (
        "backward_compatibility",
        "005-wiki-backward-compatibility-boundary.json",
        "backward-compatibility definition benefits and costs",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Backward_compatibility",
    ),
    (
        "psn_service",
        "006-wiki-playstation-network-service-snapshot.json",
        "PlayStation Network and Plus historical service snapshot",
        "http://localhost:8090/content/wikipedia_en_all_nopic/PlayStation_Network",
    ),
    (
        "decade_ps4_owner",
        "007-forum-decade-ps4-owner-scope.json",
        "one decade-long PS4 owner report",
        "http://localhost:9999/f/consoles/81981/can-you-help-me-decide-on-a-console-my-ps4-is-dying-xbox",
    ),
    (
        "killer_app_opinion",
        "008-forum-next-gen-killer-app-opinion.json",
        "one next-generation killer-app opinion",
        "http://localhost:9999/f/gaming/40385/why-is-anyone-buying-next-gen-consoles",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_ps4_pro_bundle_listing_snapshot",
        "node_type": "proposition",
        "subject": "frozen PS4 Pro Red Dead Redemption 2 bundle listing",
        "predicate": "shows_internally_unresolved_offer_snapshot",
        "object": "a title marked discontinued while the body says in stock with SKU B07HHWJMGF, a 62-percent-of-100 aggregate over twelve reviews, and a 44.96-dollar price",
        "source_url": SEARCHES[0][3],
        "search_id": "ps4_pro_bundle",
        "role": "product",
        "scope": "anomalous_seller_snapshot_not_condition_contents_authenticity_return_terms_or_market_value",
        "quotes": [
            "PlayStation 4 Pro 1TB Console - Red Dead Redemption 2 Bundle [Discontinued]",
            "In stock SKU B07HHWJMGF Rating: 62 % of 100 12 Reviews Add Your Review $44.96 Qty Add to Cart Add to Wish List Add to Compare",
        ],
        "accepted": "The frozen PS4 Pro listing title identifies a 1 TB Red Dead Redemption 2 bundle and says Discontinued while its offer line says In stock, SKU B07HHWJMGF, Rating: 62 % of 100, 12 Reviews, and 44.96 dollars; this unresolved seller snapshot does not establish condition, contents, authenticity, warranty, return terms, or normal market value.",
    },
    {
        "evidence_id": "prop_ps4_controller_listing_snapshot",
        "node_type": "proposition",
        "subject": "frozen PS4-compatible controller listing",
        "predicate": "makes_seller_compatibility_and_offer_claim",
        "object": "a seller-titled wireless controller for PlayStation 4, Slim, and Pro in black and white at 29.99 dollars with an 80-percent-of-100 aggregate over three reviews",
        "source_url": SEARCHES[1][3],
        "search_id": "ps4_controller",
        "role": "product",
        "scope": "seller_claim_not_sony_oem_independent_compatibility_durability_or_ps5_support",
        "quotes": [
            "PS4 Controller Dualshock 4 Wireless Controller for Gaming Controller Compatible with PlayStation 4/Slim/Pro Console（Black+White）",
            "In stock SKU B09KLJ6ZLH Rating: 80 % of 100 3 Reviews Add Your Review $29.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Younux is a professional game controller manufacturer and provides all customers with products of high quality.",
        ],
        "accepted": "The frozen controller page has a seller title claiming wireless-controller compatibility with PlayStation 4, Slim, and Pro in black and white, names Younux in its description, and shows SKU B09KLJ6ZLH at 29.99 dollars with an 80-percent-of-100 aggregate over three reviews; it does not prove Sony OEM identity, independent compatibility, durability, or PlayStation 5 support.",
    },
    {
        "evidence_id": "prop_playstation_spec_table_scope",
        "node_type": "proposition",
        "subject": "frozen flattened PlayStation console comparison table",
        "predicate": "separates_models_and_hardware_fields",
        "object": "PlayStation 4 Pro and PlayStation 5 family columns with different storage bandwidth, CPU clock, GPU core and clock, ray-tracing, and memory fields",
        "source_url": SEARCHES[2][3],
        "search_id": "playstation_comparison",
        "role": "concept",
        "scope": "hardware_table_not_per_game_frame_rate_quality_loading_scalar_jump_or_current_offer",
        "quotes": [
            "Model PlayStation 4 PlayStation 4 Slim PlayStation 4 Pro PlayStation Classic PlayStation 5 PlayStation 5 Digital Edition",
            "Storage Capacity 500 GB or 1 TB 1 TB 1 TB or 2 TB 16 GB 825 GB Type HDD eMMC Flash SSD Bandwidth 50-100 MB /s 132 MB/s 5.5 GB/s Optical drive Yes No Yes No CPU Cores 8 4 8 Threads 8 4 16 Clock speed 1.6 GHz 2.1 GHz 1.5 GHz 3.5 GHz GPU Cores 18 36 2 36 Threads ? ? ? Clock speed 800 MHz 911 MHz 660 MHz 2.23 GHz Ray tracing No Yes Memory 8 GB GDDR5 1 GB DDR3 16 GB GDDR6",
        ],
        "accepted": "The frozen flattened comparison table names PlayStation 4 Pro, PlayStation 5, and PlayStation 5 Digital Edition and presents model-column hardware fields for storage type and bandwidth, CPU clock, GPU core and clock values, ray tracing, and memory; it is not a per-game frame-rate, image-quality, loading-time, scalar-generation-jump, or current-offer measurement.",
    },
    {
        "evidence_id": "prop_console_generation_history_scope",
        "node_type": "proposition",
        "subject": "video-game console generation labels",
        "predicate": "are_approximate_overlapping_long_tailed_cycles",
        "object": "technology-cycle labels commonly around five years but with viable long tails, overlap, and no consistently exact delineation",
        "source_url": SEARCHES[3][3],
        "search_id": "generation_history",
        "role": "concept",
        "scope": "generic_market_history_not_fixed_performance_multiplier_or_obsolescence_date",
        "quotes": [
            "Since then, home game consoles have progressed through technology cycles typically referred to as generations .",
            "Like consoles, these generations typically start five years after its prior one, though may have long tails as popular consoles remain viable well beyond five years.",
            "However, no exact definition and delineation of console generations was consistently developed in the industry or academic literature since that point.",
            "This can create years with overlaps between multiple generations, as shown.",
        ],
        "accepted": "The captured history page describes console generations as technology-cycle labels commonly separated by about five years while allowing viable long tails and overlapping generations, and says no exact delineation is consistently developed; this is not a fixed performance multiplier or an obsolescence date for an exact console.",
    },
    {
        "evidence_id": "prop_backward_compatibility_scope",
        "node_type": "proposition",
        "subject": "backward compatibility",
        "predicate": "is_a_general_interoperability_feature_with_benefits_and_costs",
        "object": "interoperability with older systems or inputs that can preserve software and fill launch libraries but costs money to support",
        "source_url": SEARCHES[4][3],
        "search_id": "backward_compatibility",
        "role": "concept",
        "scope": "general_feature_not_exact_game_save_dlc_account_disc_controller_or_revision_guarantee",
        "quotes": [
            "In telecommunications and computing , backward compatibility (or backwards compatibility ) is a property of an operating system , software, real-world product, or technology that allows for interoperability with an older legacy system , or with input designed for such a system.",
            "This can also help make up for the lack of titles at the launch of new systems, as users can pull from the previous console's library of games while developers transition to the new hardware.",
            "The current generation of consoles such as the PlayStation 5 (PS5) [ 16 ] and Xbox Series X/S also support this feature as well.",
            "The monetary costs of supporting old software is considered to be a large drawback to the usage of backward compatibility.",
        ],
        "accepted": "The captured concept page defines backward compatibility as interoperability with an older system or its input, describes software-preservation and launch-library benefits and support costs, and broadly says current consoles such as PlayStation 5 support the feature; it does not guarantee an exact game, version, save, DLC, account, disc, controller, accessory, or console revision.",
    },
    {
        "evidence_id": "prop_psn_service_snapshot_scope",
        "node_type": "proposition",
        "subject": "frozen PlayStation Network and PlayStation Plus page",
        "predicate": "records_a_historical_service_and_catalog_snapshot",
        "object": "store and subscription functions, tier catalog counts, and an example of a collection being removed",
        "source_url": SEARCHES[5][3],
        "search_id": "psn_service",
        "role": "concept",
        "scope": "frozen_history_not_current_official_pricing_catalog_online_access_or_child_account_policy",
        "quotes": [
            "PlayStation Network's services are dedicated to an online marketplace ( PlayStation Store ), a premium subscription service for enhanced gaming and social features ( PlayStation Plus ), music streaming (PlayStation Music, based on Spotify ), and formerly a cloud gaming service ( PlayStation Now ; folded into PlayStation Plus Premium in June 2022).",
            "PlayStation Plus Extra additionally gives the user access up to 400 PS4 and PS5 games as downloadable titles, and PlayStation Plus Premium further adds access to up to 340 games from the PlayStation, PS2, PS3, and PSP, streaming of all games mentioned above, and download of all but the PS3 games.",
            "In May 2023, the collection was removed.",
        ],
        "accepted": "The frozen PlayStation Network page records store and subscription functions, historical PlayStation Plus tier catalog counts, and an example of a collection being removed; it is not current authoritative evidence for price, catalog membership, online access, account-region rules, or child and family policy.",
    },
    {
        "evidence_id": "prop_decade_ps4_owner_scope",
        "node_type": "proposition",
        "subject": "one community author with an unspecified PS4",
        "predicate": "reports_a_decade_of_use_and_personal_library_concerns",
        "object": "an incredible decade-long run of games followed by a dying-console framing and personal backward-compatibility beliefs",
        "source_url": SEARCHES[6][3],
        "search_id": "decade_ps4_owner",
        "role": "community",
        "scope": "single_person_unnamed_revision_not_failure_rate_current_policy_or_teen_outcome",
        "quotes": [
            "Can you help me decide on a console? My PS4 is dying. Xbox Series X vs PS5",
            "Long story short, I have had my PS4 for a decade and it was an incredible run of phenomenal games.",
            "Xbox has backwards compatibility which is really important to me since I loved my 360 and still have a lot of older games.",
            "Which one do you suggest? If the PS5 had backwards compatibility it would be a no brainer but unfortunately it doesn’t have that.",
        ],
        "accepted": "One community author frames an unspecified PS4 as dying after a decade, calls the run of games incredible, and gives personal backward-compatibility beliefs; one unnamed revision and one person do not establish a failure rate, current compatibility policy, or an outcome for the frozen offer or a teenager.",
    },
    {
        "evidence_id": "prop_next_gen_killer_app_opinion_scope",
        "node_type": "proposition",
        "subject": "one next-generation console commenter",
        "predicate": "states_a_broad_cross_generation_game_opinion",
        "object": "that every killer app for PS5 was also still coming to PS4 and the same applied to Xbox",
        "source_url": SEARCHES[7][3],
        "search_id": "killer_app_opinion",
        "role": "community",
        "scope": "individual_broad_opinion_not_complete_dated_catalog_per_game_result_or_current_policy",
        "quotes": [
            "Honestly, no fanboy shit Every 'killer app' for ps5 is also still coming out on ps4 Same goes with xbox And yet people are still dying for the consoles 2",
        ],
        "accepted": "One author broadly says that every killer app for PS5 was also still coming to PS4 and makes the same claim about Xbox; this individual opinion is not a complete dated game catalog, per-game comparison, current ecosystem policy, or population result.",
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
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = (
            "http://localhost:8081/search?capture_run="
            f"{RUN_ID}&request_id={payload['request_id']}"
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
            "registry_id": "reg_case_spec_console_generation_0035",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans: list[dict[str, Any]] = []
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
                "node_type": item["node_type"],
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
        (
            "bridge_offer_total_cost_and_condition_boundary",
            "bridge",
            "cheap last-generation offer claim",
            "requires_exact_offer_and_total_cost_audit",
            "preserve the discontinued versus in-stock mismatch and leave condition, contents, authenticity, protection terms, controller status, service cost, and matched current value unresolved until exact verification",
            "exact_offer_total_cost_and_condition_boundary_v1",
        ),
        (
            "bridge_generation_specs_not_game_outcome",
            "bridge",
            "console generation jump claim",
            "separates_hardware_fields_from_observed_game_outcomes",
            "use exact-model hardware differences and approximate generation history without inventing per-game frame rate, image quality, loading, noticed value, a scalar jump, or an obsolescence date",
            "generational_hardware_not_game_outcome_v1",
        ),
        (
            "bridge_compatibility_and_service_policy_boundary",
            "bridge",
            "current PlayStation ecosystem fit",
            "requires_exact_current_policy_matrix",
            "verify exact revision, disc and digital games, versions, saves, DLC, accounts, region, online subscription, controller, accessories, and family policy instead of transferring generic compatibility or frozen service history",
            "current_ecosystem_compatibility_policy_v1",
        ),
        (
            "bridge_community_scope_and_transfer_limit",
            "bridge",
            "community evidence about longevity and cross-generation games",
            "retains_author_device_and_catalog_scope",
            "use two individual posts only to elicit questions and never as a failure rate, current policy, complete catalog, exact-listing outcome, or teen-use result",
            "scoped_community_transfer_limit_v1",
        ),
        (
            "bridge_conditional_teen_console_trial",
            "bridge",
            "reversible first-console decision",
            "requires_matched_verification_and_trial",
            "compare matched returnable exact offers under a predeclared total-cost, compatibility, account, controller, display, storage, game-performance, loading, noise, heat, comfort, and teen-use protocol or defer",
            "conditional_teen_console_trial_v1",
        ),
        (
            "decision_evidence_bounded_teen_console_choice",
            "decision",
            "last-generation versus current-generation console for a teenager",
            "selects_cheapest_admissible_exact_configuration",
            "choose only among exact configurations that clear current offer, ecosystem, total-cost, safety, and return-window trial gates, with no universal PS4 Pro or PS5 winner and deferral when a gate remains unresolved",
            "evidence_bounded_teen_console_choice_v1",
        ),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
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
        "bridge_offer_total_cost_and_condition_boundary": [
            "prop_ps4_pro_bundle_listing_snapshot",
            "prop_ps4_controller_listing_snapshot",
            "prop_psn_service_snapshot_scope",
        ],
        "bridge_generation_specs_not_game_outcome": [
            "prop_playstation_spec_table_scope",
            "prop_console_generation_history_scope",
            "prop_next_gen_killer_app_opinion_scope",
        ],
        "bridge_compatibility_and_service_policy_boundary": [
            "prop_ps4_pro_bundle_listing_snapshot",
            "prop_ps4_controller_listing_snapshot",
            "prop_backward_compatibility_scope",
            "prop_psn_service_snapshot_scope",
            "prop_decade_ps4_owner_scope",
        ],
        "bridge_community_scope_and_transfer_limit": [
            "prop_console_generation_history_scope",
            "prop_backward_compatibility_scope",
            "prop_decade_ps4_owner_scope",
            "prop_next_gen_killer_app_opinion_scope",
        ],
        "bridge_conditional_teen_console_trial": [
            "bridge_offer_total_cost_and_condition_boundary",
            "bridge_generation_specs_not_game_outcome",
            "bridge_compatibility_and_service_policy_boundary",
            "bridge_community_scope_and_transfer_limit",
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
                "source_id": "decision_evidence_bounded_teen_console_choice",
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
