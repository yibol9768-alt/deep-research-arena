#!/usr/bin/env python3
"""Build the frozen Q40 coffee-freshness rating-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0040-freshness-rating-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0040/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0040-freshness-rating-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0040-freshness-rating-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0040"
TOPIC = "coffee_freshness_rating_exact_lot_boundary"


SEARCHES = [
    (
        "onyx_whole_bean",
        "001-shopping-onyx-southern-weather-five-star.json",
        "Onyx near-perfect whole-bean seller snapshot",
        "http://localhost:7770/onyx-coffee-lab-southern-weather-blend-medium-roasted-whole-bean-coffee-2-pound-bag.html",
    ),
    (
        "dallmayr_ground_sixpack",
        "002-shopping-dallmayr-prodomo-high-rating.json",
        "Dallmayr high-rating ground-coffee multipack snapshot",
        "http://localhost:7770/dallmayr-prodomo-arabica-ground-coffee-17-6oz-6-pack.html",
    ),
    (
        "siroman_fresh_roast",
        "003-shopping-siroman-colombian-fresh-roast.json",
        "Siroman fresh-roast-marketed whole-bean snapshot",
        "http://localhost:7770/colombian-fresh-roast-organic-coffee-beans-4oz-12oz-1lb-2lb-4lb-by-siroman-coffee-colombian-cocktail-12oz.html",
    ),
    (
        "segafredo_pods",
        "004-shopping-segafredo-enzo-five-star-pods.json",
        "Segafredo near-perfect aroma-preservation pod snapshot",
        "http://localhost:7770/segafredo-enzo-rich-and-bold-dark-roast-coffee-single-serve-pods-10-count-box-pack-of-3.html",
    ),
    (
        "coffee_roasting",
        "005-wiki-coffee-roasting-chemistry.json",
        "coffee roasting chemistry and typical staling boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee_roasting",
    ),
    (
        "coffee_bag",
        "006-wiki-coffee-bag-valve.json",
        "coffee bag and pressure-relief-valve function",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee_bag",
    ),
    (
        "food_packaging",
        "007-wiki-food-packaging-barriers.json",
        "generic food-packaging barrier function",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Food_packaging",
    ),
    (
        "coffee_bean",
        "008-wiki-coffee-bean-composition.json",
        "coffee flavor-compound composition",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee_bean",
    ),
    (
        "coffee_quality_dimensions",
        "009-wiki-coffee-quality-dimensions.json",
        "coffee region varietal processing and sensory dimensions",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Economics_of_coffee",
    ),
    (
        "nh_fresh_beans",
        "010-forum-nh-fresh-light-roasted-source.json",
        "New Hampshire fresh light-roast sourcing discussion",
        "http://localhost:9999/f/newhampshire/108217/nh-source-for-fresh-light-roasted-coffee-beans",
    ),
    (
        "ri_fresh_beans",
        "011-forum-rhode-island-fresh-roasted-beans.json",
        "Rhode Island freshly roasted and bulk-subscription discussion",
        "http://localhost:9999/f/RhodeIsland/36340/coffee-beans",
    ),
    (
        "wa_five_pound",
        "012-forum-washington-five-pound-freshness-price.json",
        "Washington five-pound bag price and freshness discussion",
        "http://localhost:9999/f/Washington/122879/coffee-roasters-with-5-pound-bags",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_onyx_whole_bean_rating_scope",
        "subject": "frozen Onyx whole-bean seller page",
        "predicate": "shows_near_perfect_aggregate_and_flavor_copy",
        "object": "a 50.75-dollar two-pound whole-bean offer rated 100 percent over one review with seller flavor descriptions but no verified lot date or sensory test",
        "source_url": SEARCHES[0][3],
        "search_id": "onyx_whole_bean",
        "role": "product",
        "scope": "seller_offer_and_one_review_aggregate_not_exact_lot_freshness_or_independent_quality",
        "quotes": [
            "In stock SKU B08GFG99W8 Rating: 100 % of 100 1 Review Add Your Review $50.75 Qty Add to Cart Add to Wish List Add to Compare",
            "Southern Weather embodies everything we love about specialty coffee and has evolved into a foundational blend.",
        ],
        "accepted": "The frozen Onyx page shows SKU B08GFG99W8, a two-pound whole-bean offer at 50.75 dollars with a 100-percent-of-100 aggregate based on one review and seller flavor copy; it does not provide a verified roast or pack date, lot age, storage history, seal result, matched review evidence, or independent tasting of the exact bag.",
    },
    {
        "evidence_id": "prop_dallmayr_ground_rating_scope",
        "subject": "frozen Dallmayr ground-coffee seller page",
        "predicate": "shows_high_aggregate_and_large_ground_multipack",
        "object": "a 56.38-dollar six-pack of 17.6-ounce ground coffee rated 96 percent over 115 reviews without exact pack dates or opened-pack history",
        "source_url": SEARCHES[1][3],
        "search_id": "dallmayr_ground_sixpack",
        "role": "product",
        "scope": "seller_offer_and_aggregate_not_pack_date_storage_waste_or_sensory_measurement",
        "quotes": [
            "In stock SKU B00G3ECDJ8 Rating: 96 % of 100 115 Reviews Add Your Review $56.38 Qty Add to Cart Add to Wish List Add to Compare",
            "Dallmayr Prodomo Arabica Ground Coffee 17.6oz (6-pack) Famous German Coffee 100% Arabica 6 x 500g",
        ],
        "accepted": "The frozen Dallmayr page shows SKU B00G3ECDJ8 at 56.38 dollars for six 17.6-ounce ground-coffee packs with a 96-percent-of-100 aggregate over 115 reviews; it does not disclose a verified pack or roast date for each unit, warehouse or seal history, consumption and waste fit, or controlled sensory freshness.",
    },
    {
        "evidence_id": "prop_siroman_fresh_roast_claim_scope",
        "subject": "frozen Siroman whole-bean seller page",
        "predicate": "markets_fresh_roast_wording_with_high_aggregate",
        "object": "a selected 12-ounce whole-bean offer at 17.05 dollars rated 97 percent over seven reviews and described as fresh boarder roasted",
        "source_url": SEARCHES[2][3],
        "search_id": "siroman_fresh_roast",
        "role": "product",
        "scope": "seller_fresh_wording_not_verified_roast_date_lot_age_or_sensory_result",
        "quotes": [
            "In stock SKU B083TPKS3Q Rating: 97 % of 100 7 Reviews Add Your Review $17.05",
            "Fresh boarder roasted Colombian coffee beans.",
        ],
        "accepted": "The frozen Siroman page shows SKU B083TPKS3Q, the selected 12-ounce whole-bean variant at 17.05 dollars with a 97-percent-of-100 aggregate over seven reviews and seller wording that says fresh boarder roasted; the wording is not a verified roast date, exact lot age, storage record, seal test, gas measurement, or independent sensory result.",
    },
    {
        "evidence_id": "prop_segafredo_pod_preservation_scope",
        "subject": "frozen Segafredo single-serve pod seller page",
        "predicate": "markets_aroma_preservation_with_near_perfect_aggregate",
        "object": "a 32.99-dollar thirty-pod offer rated 100 percent over four reviews whose seller copy says filter-cup technology preserves aroma and flavor",
        "source_url": SEARCHES[3][3],
        "search_id": "segafredo_pods",
        "role": "product",
        "scope": "seller_package_claim_not_independent_barrier_test_date_or_sensory_result",
        "quotes": [
            "In stock SKU B084JHKDLC Rating: 100 % of 100 4 Reviews Add Your Review $32.99 Qty Add to Cart Add to Wish List Add to Compare",
            "FILTER CUP TECHNOLOGY - This eco-friendly pod design uses less plastic and preserves all of the aroma and rich flavor in every cup you brew",
        ],
        "accepted": "The frozen Segafredo page shows SKU B084JHKDLC at 32.99 dollars for thirty single-serve pods with a 100-percent-of-100 aggregate over four reviews and seller copy saying the filter-cup design preserves aroma and flavor; it supplies no independent barrier test, roast or pack date, seal history, oxygen measurement, or blind sensory result for the exact pods.",
    },
    {
        "evidence_id": "prop_roast_chemistry_staling_scope",
        "subject": "roasted-coffee chemistry and typical staling context",
        "predicate": "links_roasting_stability_exposure_form_and_preservation",
        "object": "Maillard and other roast reactions plus lower roasted-bean stability, heat oxygen and light exposure, form-specific typical windows, and preservation effects",
        "source_url": SEARCHES[4][3],
        "search_id": "coffee_roasting",
        "role": "concept",
        "scope": "general_mechanism_and_typical_windows_not_exact_lot_age_or_universal_discard_clock",
        "quotes": [
            "Roasting coffee transforms the chemical and physical properties of green coffee beans into roasted coffee products.",
            "Coffee tends to be roasted close to where it will be consumed, as green coffee is more stable than roasted beans.",
            "Extending the shelf life of roasted coffee relies on maintaining an optimum environment to protect it from exposure to heat, oxygen, and light.",
            "Roasted coffee has an optimal typical shelf life of two weeks, and ground coffee about 15 minutes.",
        ],
        "accepted": "The coffee-roasting page says roasting changes beans chemically and physically through Maillard and other reactions, green coffee is more stable than roasted beans, and roasted-coffee shelf life depends on protection from heat, oxygen, and light; its whole-bean and ground-coffee windows are general typical context, not a measurement of any exact lot or a universal sensory discard clock.",
    },
    {
        "evidence_id": "prop_coffee_bag_valve_scope",
        "subject": "coffee-bag and pressure-relief-valve function",
        "predicate": "describes_sealed_bags_and_one_way_pressure_relief",
        "object": "consumer bean or ground packaging plus carbon-dioxide pressure and valves that vent without admitting atmosphere",
        "source_url": SEARCHES[5][3],
        "search_id": "coffee_bag",
        "role": "concept",
        "scope": "generic_package_function_not_exact_seal_barrier_storage_or_age_verification",
        "quotes": [
            "Coffee beans are usually transported in large jute sacks, while coffee sold to consumers may be packaged as beans or ground coffee in a small, sealed plastic bag.",
            "There is a tendency for pressure from carbon dioxide to build up in these barrier bags.",
            "Special pressure relief valves have been developed to relieve the pressure without letting the atmosphere into the bags.",
        ],
        "accepted": "The coffee-bag page says consumer coffee may be packaged as beans or grounds in sealed plastic bags, carbon dioxide can build pressure, and pressure-relief valves can vent it without admitting atmosphere; this generic function does not prove an exact package's valve direction, seal integrity, barrier performance, gas composition, storage history, roast date, or current taste.",
    },
    {
        "evidence_id": "prop_food_packaging_barrier_scope",
        "subject": "generic food-packaging barrier function",
        "predicate": "protects_against_alteration_oxygen_and_water_vapor",
        "object": "chemical biological and physical protection plus oxygen and water-vapor barriers intended to help freshness over shelf life",
        "source_url": SEARCHES[6][3],
        "search_id": "food_packaging",
        "role": "concept",
        "scope": "generic_packaging_function_not_exact_coffee_package_performance_or_history",
        "quotes": [
            "Food packaging is a packaging system specifically designed for food and represents one of the most important aspects among the processes involved in the food industry, as it provides protection from chemical, biological and physical alterations.",
            "Barrier protection - A barrier from oxygen , water vapor , dust, etc.",
            "Keeping the contents clean, fresh, and safe for the intended shelf life is a primary function.",
        ],
        "accepted": "The food-packaging page describes protection from chemical, biological, and physical alteration, including barriers to oxygen and water vapor, with freshness over an intended shelf life as a function; it does not identify or test the material, seal, transmission rate, abuse history, or remaining shelf life of any exact coffee package.",
    },
    {
        "evidence_id": "prop_coffee_compound_aroma_scope",
        "subject": "coffee-bean flavor and aroma compounds",
        "predicate": "attributes_roasted_flavor_to_multiple_volatile_and_nonvolatile_compounds",
        "object": "volatile and nonvolatile compounds plus nitrogenous compounds and carbohydrates that contribute to roasted flavor and aroma",
        "source_url": SEARCHES[7][3],
        "search_id": "coffee_bean",
        "role": "concept",
        "scope": "general_composition_not_exact_bag_compound_loss_or_sensory_quality",
        "quotes": [
            "Further, both nonvolatile and volatile compounds contribute to the flavor of the coffee bean when it is roasted.",
            "Nonvolatile nitrogenous compounds (including alkaloids , trigonelline , proteins, and free amino acids ) and carbohydrates are of major importance in producing the full aroma of roasted coffee and for its biological action.",
        ],
        "accepted": "The coffee-bean page says volatile and nonvolatile compounds contribute to roasted flavor and that nitrogenous compounds and carbohydrates are important in producing roasted-coffee aroma; it does not measure compound loss, oxidation, aroma intensity, defect level, or preference for any exact captured offer.",
    },
    {
        "evidence_id": "prop_coffee_quality_multi_axis_scope",
        "subject": "coffee sensory quality dimensions",
        "predicate": "varies_with_region_varietal_and_processing",
        "object": "flavor aroma body acidity and texture differences that depend on region, genetic subspecies, and processing",
        "source_url": SEARCHES[8][3],
        "search_id": "coffee_quality_dimensions",
        "role": "concept",
        "scope": "general_quality_dimensions_not_brand_rank_or_exact_preference",
        "quotes": [
            "Beans from different countries or regions can usually be distinguished by differences in flavor, aroma, body , acidity and girth (texture)",
            "These taste characteristics are dependent not only on the coffee's growing region, but also on genetic subspecies ( varietals ) and processing.",
        ],
        "accepted": "The economics-of-coffee page says beans from different regions can differ in flavor, aroma, body, acidity, and texture, and that these characteristics also depend on varietal and processing; freshness is therefore not the only plausible quality axis, and the page does not rank the four exact products or determine this buyer's preference.",
    },
    {
        "evidence_id": "prop_nh_fresh_source_discussion_scope",
        "subject": "New Hampshire fresh-bean community discussion",
        "predicate": "asks_for_fresh_light_roasts_and_reports_one_high_turnover_shop",
        "object": "a sourcing question plus a commenter impression that near-daily roasting and selling out makes freshness easy to confirm while being pricey",
        "source_url": SEARCHES[9][3],
        "search_id": "nh_fresh_beans",
        "role": "community",
        "scope": "author_and_business_specific_question_and_comment_not_controlled_freshness_test_or_brand_rate",
        "quotes": [
            "New to the state and looking for a NH source for quality fresh light roasted coffee beans. Preferably Ethiopian. Any suggestions? 23",
            "Was going to say this place. They roast almost daily it seems and sell out so freshness is easily confirmed. Friendly bunch, but everything there is pricey.",
        ],
        "accepted": "The New Hampshire thread asks for fresh light-roasted beans and one commenter says a particular shop seems to roast almost daily and sell out, making freshness easy to confirm while being pricey; it is a business-specific question and impression, not a blind test, chemical measurement, prevalence estimate, or evidence about the four exact offers.",
    },
    {
        "evidence_id": "prop_ri_fresh_bulk_discussion_scope",
        "subject": "Rhode Island fresh and bulk coffee discussion",
        "predicate": "contains_conflicting_personal_freshness_and_consumption_statements",
        "object": "a freshly roasted sourcing question, a three-month five-pound subscription report, a never-on-grocery-shelf claim, and a possibly-less-fresh imported coffee statement",
        "source_url": SEARCHES[10][3],
        "search_id": "ri_fresh_beans",
        "role": "community",
        "scope": "individual_business_purchase_and_consumption_context_not_universal_storage_window_or_controlled_test",
        "quotes": [
            "I live in Warwick and am looking for the best place for freshly roasted beans. Thanks in advance! 4",
            "Dave’s roasters. They deliver. We order a 5 lb bag on subscription every 3 months. It’s good all the way through.",
            "North Koffee in NK on post Rd. Roasted on site in small batches. Freshest around. Never sits on a grocery store shelf.",
        ],
        "accepted": "The Rhode Island thread asks for freshly roasted beans; individual commenters say a five-pound subscription remains good over three months and call an on-site small-batch source freshest because it never sits on a grocery shelf. These are personal business, package-size, timing, and preference statements, not measurements, a universal storage window, a warehouse rate, or tests of the exact captured coffees.",
    },
    {
        "evidence_id": "prop_wa_bulk_price_freshness_scope",
        "subject": "Washington five-pound coffee discussion",
        "predicate": "trades_bulk_price_against_one_freshness_impression",
        "object": "a five-pound price question and one comment that a lower-cost Costco option is not as fresh while still being great coffee",
        "source_url": SEARCHES[11][3],
        "search_id": "wa_five_pound",
        "role": "community",
        "scope": "author_scoped_price_and_freshness_impression_not_controlled_sensory_or_exact_offer_evidence",
        "quotes": [
            "Any recommendations for PNW based coffee roasters that have decently priced 5 pound bags of coffee? Either one time purchase or subscription would work for me.",
            "You can get Portland roasting at Costco and it’s like $10/lb that way, but it’s not as fresh. It’s $85 for a 5lb bag from their inner SE roastery. Great coffee though.",
        ],
        "accepted": "The Washington thread asks for decently priced five-pound bags, and one commenter calls a roughly ten-dollar-per-pound Costco option not as fresh while still calling it great coffee and contrasting an 85-dollar roastery bag. This is an author-scoped price and freshness impression, not a blind comparison, measured lot age, prevalence estimate, or evidence for the four exact offers.",
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
            "registry_id": "reg_case_spec_freshness_rating_0040",
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
        (
            "bridge_seller_rating_fresh_scope",
            "bridge",
            "four high-rating coffee seller snapshots",
            "remain_seller_aggregates_and_copy_not_exact_lot_freshness",
            "record exact form, pack, price, aggregate, review count, and literal freshness or preservation copy without treating them as dates, history, measurements, or independent quality results",
            "seller_rating_and_fresh_copy_scope_v1",
        ),
        (
            "bridge_roast_chemistry_staling",
            "bridge",
            "roast chemistry, compounds, exposure, and staling",
            "supports_freshness_as_real_but_typical_not_exact",
            "use roast reactions, lower roasted-bean stability, flavor compounds, heat, oxygen, light, form, and preservation to establish a plausible freshness axis without assigning an exact lot age or universal deadline",
            "roast_chemistry_and_staling_boundary_v1",
        ),
        (
            "bridge_package_valve_history",
            "bridge",
            "sealed bags, pods, barriers, and pressure-relief valves",
            "define_functions_without_proving_exact_package_history",
            "verify exact dates, lot, seal, valve, barrier, gas, storage, transit, and opening history rather than treating package form or generic function as freshness proof",
            "package_valve_and_history_boundary_v1",
        ),
        (
            "bridge_community_freshness_scope",
            "bridge",
            "three community freshness and bulk-purchase discussions",
            "retain_author_business_price_size_and_timing_scope",
            "use local turnover, grocery shelf, subscription size, price, and consumption comments as variables to check without converting them to tests, rates, exact ages, or brand verdicts",
            "community_freshness_statement_scope_v1",
        ),
        (
            "bridge_multi_axis_matched_comparison",
            "bridge",
            "freshness versus other coffee quality axes",
            "requires_matched_form_and_brew_controls",
            "preserve region, varietal, processing, roast profile, grind, brew, format, and preference effects and compare sensory freshness only under matched dose, water, temperature, grind, extraction, cup, opening age, and order",
            "multi_axis_quality_and_matched_comparison_v1",
        ),
        (
            "bridge_exact_lot_matrix_trial",
            "bridge",
            "exact coffee offer audit and small controlled tasting",
            "requires_complete_date_package_consumption_brew_cost_and_taste_gates",
            "build an exact-lot matrix, calculate cost per acceptable consumed serving, and run a small blinded or randomized trial against a dated fresh reference while deferring unresolved or failed material cells",
            "exact_lot_matrix_and_controlled_trial_v1",
        ),
        (
            "decision_evidence_bounded_freshness_purchase",
            "decision",
            "coffee freshness and rating purchase choice",
            "selects_only_the_cheapest_exact_passing_coffee_or_fresh_reference_or_deferral",
            "treat freshness as real but non-exclusive, reject ratings copy packages and anecdotes as exact proof, and choose only the cheapest exact coffee clearing date package consumption brew cost and taste gates or buy a small dated fresh reference or defer",
            "evidence_bounded_freshness_purchase_v1",
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
        "bridge_seller_rating_fresh_scope": [
            "prop_onyx_whole_bean_rating_scope",
            "prop_dallmayr_ground_rating_scope",
            "prop_siroman_fresh_roast_claim_scope",
            "prop_segafredo_pod_preservation_scope",
        ],
        "bridge_roast_chemistry_staling": [
            "prop_roast_chemistry_staling_scope",
            "prop_coffee_compound_aroma_scope",
        ],
        "bridge_package_valve_history": [
            "prop_segafredo_pod_preservation_scope",
            "prop_coffee_bag_valve_scope",
            "prop_food_packaging_barrier_scope",
        ],
        "bridge_community_freshness_scope": [
            "prop_nh_fresh_source_discussion_scope",
            "prop_ri_fresh_bulk_discussion_scope",
            "prop_wa_bulk_price_freshness_scope",
        ],
        "bridge_multi_axis_matched_comparison": [
            "prop_roast_chemistry_staling_scope",
            "prop_coffee_compound_aroma_scope",
            "prop_coffee_quality_multi_axis_scope",
        ],
        "bridge_exact_lot_matrix_trial": [
            "bridge_seller_rating_fresh_scope",
            "bridge_roast_chemistry_staling",
            "bridge_package_valve_history",
            "bridge_community_freshness_scope",
            "bridge_multi_axis_matched_comparison",
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
                "source_id": "decision_evidence_bounded_freshness_purchase",
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
