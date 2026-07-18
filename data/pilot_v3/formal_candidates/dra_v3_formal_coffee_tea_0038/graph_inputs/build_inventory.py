#!/usr/bin/env python3
"""Build the frozen Q38 daily milk-espresso bean inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0038-milk-espresso-bean-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0038/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0038-milk-espresso-bean-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0038-milk-espresso-bean-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0038"
TOPIC = "daily_milk_espresso_species_origin_and_rebuy_boundary"


SEARCHES = [
    (
        "single_origin_arabica",
        "001-shopping-single-origin-arabica-1lb.json",
        "one-pound single-origin 100-percent-Arabica seller snapshot",
        "http://localhost:7770/the-french-press-coffee-roasters-whole-bean-1lb-colombian-santa-barbara-single-origin-coffee-medium-roast-100-arabica-fair-trade-kosher-1-pack.html",
    ),
    (
        "sumatra_blend",
        "002-shopping-sumatra-blend-2lb.json",
        "two-pound Sumatra blend seller snapshot",
        "http://localhost:7770/copper-moon-sumatra-blend-dark-roast-coffee-whole-bean-2-lb.html",
    ),
    (
        "arabica_robusta_herbal",
        "003-shopping-arabica-robusta-herbal-blend.json",
        "Arabica-Robusta instant herbal blend seller snapshot",
        "http://localhost:7770/burn-control-coffee-premium-100-south-american-arabica-robusta-blend-coffee-weight-management-herbs-garcinia-cambogia-and-yerba-mate-javita.html",
    ),
    (
        "arabica_species",
        "004-wiki-arabica-species-boundary.json",
        "Arabica species and comparison boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Coffea_arabica",
    ),
    (
        "robusta_species",
        "005-wiki-robusta-espresso-role.json",
        "Robusta species, production, and espresso-role boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Coffea_canephora",
    ),
    (
        "single_origin_label",
        "006-wiki-single-origin-label-boundary.json",
        "single-origin geographic-label scope",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Single-origin_coffee",
    ),
    (
        "espresso_extraction",
        "007-wiki-espresso-extraction-boundary.json",
        "espresso extraction-method scope",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Espresso",
    ),
    (
        "cappuccino_recipe",
        "008-wiki-cappuccino-milk-ratio.json",
        "cappuccino milk-recipe scope",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Cappuccino",
    ),
    (
        "community_long_rebuy",
        "009-forum-local-espresso-stockup-comparison.json",
        "individual long-term blend and go-to reports",
        "http://localhost:9999/f/massachusetts/62808/what-are-your-favorite-local-coffee-brands-for-espresso",
    ),
    (
        "community_roast_disagreement",
        "010-forum-dark-medium-roast-surprise.json",
        "individual roast preference and roaster disagreement",
        "http://localhost:9999/f/newhaven/64812/coffee-beans-ground-coffee-recommendations",
    ),
    (
        "community_espresso_sampling",
        "011-forum-espresso-gift-multiple-bags.json",
        "individual espresso sampling and freshness views",
        "http://localhost:9999/f/RhodeIsland/57434/coffee-help",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_single_origin_arabica_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Colombian Santa Barbara coffee offer",
        "predicate": "shows_seller_origin_species_size_and_price_labels",
        "object": "a one-pound whole-bean single-origin medium-roast product titled 100-percent Arabica at 16.98 dollars under SKU B09DR7Q1RF",
        "source_url": SEARCHES[0][3],
        "search_id": "single_origin_arabica",
        "role": "product",
        "scope": "seller_snapshot_not_origin_authentication_freshness_cup_quality_or_milk_espresso_result",
        "quotes": [
            "THE FRENCH PRESS COFFEE ROASTERS Whole Bean 1lb Colombian Santa Barbara, Single Origin Coffee, Medium Roast, 100% Arabica, Fair Trade, Kosher, - 1 Pack",
            "In stock SKU B09DR7Q1RF Be the first to review this product $16.98 Flavor Name Brazilian Datera Colombian, Santa Barbara Ethiopian Yirgacheffe Guatemalan Antigua Indonesian Sumatra Qty Add to Cart Add to Wish List Add to Compare",
            "Colombian Santa Barbara Single Origin Whole Bean Coffee: This coffee comes from the Santa Barbara Estate which is southwest of the Antioquia department in Colombia.",
        ],
        "accepted": "The frozen seller page titles SKU B09DR7Q1RF as a one-pound Colombian Santa Barbara single-origin, medium-roast, whole-bean, 100-percent-Arabica product and shows 16.98 dollars; those are seller labels and an offer snapshot, not independent origin, composition, freshness, cup-quality, or milk-espresso verification.",
    },
    {
        "evidence_id": "prop_sumatra_blend_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Copper Moon Sumatra Blend offer",
        "predicate": "shows_seller_blend_size_price_rating_and_arabica_labels",
        "object": "a two-pound whole-bean Sumatra dark-roast blend at 15.48 dollars with a 55-percent-of-100 aggregate over twelve reviews and a table marking the shown products 100-percent Arabica",
        "source_url": SEARCHES[1][3],
        "search_id": "sumatra_blend",
        "role": "product",
        "scope": "seller_snapshot_not_exact_selected_style_freshness_origin_authentication_or_milk_espresso_result",
        "quotes": [
            "Copper Moon Sumatra Blend, Dark Roast Coffee, Whole Bean, 2 Lb",
            "In stock SKU B01L9YE808 Rating: 55 % of 100 12 Reviews Add Your Review $15.48",
            "100% Arabica ✓ ✓ ✓ ✓ ✓ ✓",
            "PREMIUM COFFEE BLEND: Sumatra premium dark roast coffee is a bold blend sourced from the remote reaches of Indonesia.",
        ],
        "accepted": "The frozen seller page titles SKU B01L9YE808 as a two-pound Copper Moon Sumatra dark-roast whole-bean blend, shows 15.48 dollars and a 55-percent-of-100 aggregate over twelve reviews, and marks the displayed products 100-percent Arabica; these are seller snapshot fields, not independent exact-style, freshness, origin, or milk-drink verification.",
    },
    {
        "evidence_id": "prop_arabica_robusta_herbal_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Burn and Control coffee offer",
        "predicate": "shows_a_seller_arabica_robusta_instant_herbal_claim_without_package_amount",
        "object": "SKU B00A7IIOPI at 28 dollars, seller-described as a South American Arabica and Robusta instant blend infused with yerba mate and garcinia cambogia, with no captured comparable package amount",
        "source_url": SEARCHES[2][3],
        "search_id": "arabica_robusta_herbal",
        "role": "product",
        "scope": "seller_claim_not_species_ratio_health_efficacy_dose_count_or_comparable_unit_cost",
        "quotes": [
            "Burn + Control Coffee, Premium 100% South American Arabica, Robusta Blend Coffee, Weight Management Herbs, Garcinia Cambogia and Yerba Mate, Javita",
            "In stock SKU B00A7IIOPI Be the first to review this product $28.00",
            "PREMIUM, DELICIOUS COFFEE: 100% South American blend of Arabica and Robusta coffee beans, fully micronized to aid mixability, consumption and enjoyment.",
            "THE ORIGINAL: Burn + Control Coffee is the original, herb-infused, coffee formulated to help support benefits like healthy metabolism and weight management.*",
        ],
        "accepted": "The frozen seller page shows SKU B00A7IIOPI at 28 dollars and describes an instant South American Arabica and Robusta blend infused with yerba mate and garcinia cambogia, but the captured page does not establish a comparable package amount, species ratio, health efficacy, dose count, ordinary whole-bean format, or unit cost.",
    },
    {
        "evidence_id": "prop_arabica_general_species_scope",
        "node_type": "proposition",
        "subject": "Coffea arabica and general comparison with Robusta",
        "predicate": "supplies_species_level_context_not_exact_bag_identity",
        "object": "Arabica is a botanical species and the page characterizes Robusta as less acidic, more bitter, and more highly caffeinated while noting Arabica cultivation and labeling boundaries",
        "source_url": SEARCHES[3][3],
        "search_id": "arabica_species",
        "role": "concept",
        "scope": "general_species_page_not_exact_product_composition_ratio_roast_caffeine_or_cup_result",
        "quotes": [
            "Coffee produced from the less acidic, more bitter, and more highly caffeinated robusta bean ( C. canephora ) makes up most of the remaining coffee production.",
            "The trees are difficult to cultivate",
            "Blends consisting only of Arabica are often labelled \"100% Arabica\" as a sign of quality.",
        ],
        "accepted": "The frozen Arabica page treats Arabica as a botanical species, characterizes Robusta in general as less acidic, more bitter, and more highly caffeinated, and discusses cultivation and 100-percent-Arabica labeling; it does not authenticate an exact bag, ratio, roast, caffeine dose, or cup result.",
    },
    {
        "evidence_id": "prop_robusta_general_species_and_espresso_scope",
        "node_type": "proposition",
        "subject": "Coffea canephora or Robusta",
        "predicate": "has_general_yield_caffeine_cost_bitterness_body_and_crema_context",
        "object": "higher yield and caffeine, lower production cost, commonly stronger and more bitter cups, and a possible body and crema role in traditional Italian espresso blends",
        "source_url": SEARCHES[4][3],
        "search_id": "robusta_species",
        "role": "concept",
        "scope": "general_species_and_culture_context_not_exact_bag_ratio_quality_or_extraction_outcome",
        "quotes": [
            "The robusta plant has a greater crop yield than that of arabica, contains more caffeine (2.7% compared to arabica's 1.5%), [ 11 ] and contains less sugar (3â7% compared to arabica's 6â9%).",
            "Since Robusta is easier to care for and has a greater crop yield than C. arabica , it is cheaper to produce.",
            "Roasted robusta beans produce a strong, full-bodied coffee with a distinctive earthy flavour, but usually with more bitterness than arabica due to its pyrazine content.",
            "Good-quality robusta beans are used in traditional Italian espresso blends to provide a full-bodied taste and a better foam head (known as crema ).",
        ],
        "accepted": "The frozen Robusta page gives general yield, caffeine, production-cost, bitterness, body, and traditional Italian espresso-crema context; it does not establish the ratio, quality, freshness, caffeine dose, or extraction result of any exact seller product.",
    },
    {
        "evidence_id": "prop_single_origin_geographic_label_scope",
        "node_type": "proposition",
        "subject": "single-origin coffee",
        "predicate": "is_a_broad_geographic_label_with_no_universal_enforcement",
        "object": "coffee from one known geographic origin that may mean a farm, multiple farms, or a country and is contrasted with multiple-origin blends",
        "source_url": SEARCHES[5][3],
        "search_id": "single_origin_label",
        "role": "concept",
        "scope": "geographic_and_traceability_axis_not_species_purity_quality_or_label_authentication",
        "quotes": [
            "Single-origin coffee is coffee grown within a single known geographic origin.",
            "There are no universal rules, or governing bodies enforcing the labeling of coffee.",
            "Single-origin coffees may come from a single farm, multiple farms from the same country, or just a blend of the coffees grown from that country.",
        ],
        "accepted": "The frozen single-origin page defines a geographic-origin category, says it may range from one farm to multiple farms or a country, and notes no universal label enforcement; this is not the same axis as species purity and does not authenticate an exact product or guarantee quality.",
    },
    {
        "evidence_id": "prop_espresso_is_extraction_method_scope",
        "node_type": "proposition",
        "subject": "espresso",
        "predicate": "is_a_pressure_based_concentrated_extraction_method",
        "object": "hot water forced at high pressure through finely ground coffee, producing a concentrated drink with high suspended and dissolved solids",
        "source_url": SEARCHES[6][3],
        "search_id": "espresso_extraction",
        "role": "concept",
        "scope": "brewing_method_not_bean_species_exact_recipe_machine_compatibility_or_bag_quality",
        "quotes": [
            "Espresso ( / É Ë s p r É s oÊ / â , Italian: [eËsprÉsso] ) is a concentrated form of coffee produced by forcing hot water under high pressure through finely ground coffee beans.",
            "Espresso machines use pressure to extract a highly concentrated coffee with a complex flavor profile in a short time, usually 25â30 seconds.",
            "The result is a beverage with a higher concentration of suspended and dissolved solids than regular drip coffee , giving espresso its characteristic body and intensity.",
        ],
        "accepted": "The frozen espresso page defines a pressure-based concentrated extraction method and describes its short extraction and high suspended and dissolved solids; it does not define a bean species, exact household recipe, machine compatibility, or quality guarantee for a bag labeled espresso.",
    },
    {
        "evidence_id": "prop_cappuccino_fixed_milk_recipe_scope",
        "node_type": "proposition",
        "subject": "cappuccino",
        "predicate": "provides_a_milk_espresso_recipe_not_a_sensory_masking_result",
        "object": "an espresso-based drink with steamed milk and foam, traditionally described with equal thirds of espresso, steamed milk, and milk foam",
        "source_url": SEARCHES[7][3],
        "search_id": "cappuccino_recipe",
        "role": "concept",
        "scope": "recipe_definition_not_proof_that_milk_erases_species_roast_origin_or_blend_differences",
        "quotes": [
            "is an espresso -based coffee drink traditionally prepared with steamed milk , including a layer of milk foam .",
            "The espresso is poured into the bottom of the cup, followed by a similar amount of hot milk which is prepared by heating and texturing the milk using the espresso machine steam wand.",
            "the traditional way of preparing cappuccino is to add equal proportions of the ingredients: 1 â 3 espresso, 1 â 3 steamed milk and 1 â 3 milk foam.",
        ],
        "accepted": "The frozen cappuccino page supplies a milk-and-espresso recipe and a traditional equal-parts example; it can anchor a fixed comparison recipe but does not prove that milk erases species, roast, origin, blend, or exact-bag sensory differences.",
    },
    {
        "evidence_id": "prop_community_long_term_rebuy_scope",
        "node_type": "proposition",
        "subject": "individual Massachusetts coffee commenters",
        "predicate": "report_repeat_buying_and_long_term_custom_blend_use",
        "object": "a list of roasters bought and considered buy-again, an almost fifteen-year daily custom-blend report, and an exclusive go-to statement",
        "source_url": SEARCHES[8][3],
        "search_id": "community_long_rebuy",
        "role": "community",
        "scope": "individual_uncontrolled_reports_not_population_preference_or_exact_frozen_bag_evidence",
        "quotes": [
            "There are a ton of choices, so here's a Central/Western MA list of a few that I have bought from and would buy from again.",
            "A lot of these placesa will do custom blends, grinds if your order 5lbs or more. We have have had a custom blend made by indigo for almost 15 years and whenevert I sip it (daily) I look at it impressed.",
            "+1 for Armeno, it's become my exclusive go-to",
        ],
        "accepted": "Individual commenters in one Massachusetts thread describe buy-again roasters, an almost fifteen-year daily custom-blend habit, and an exclusive go-to; these motivate repeatability and rebuy checks but are uncontrolled personal reports, not population rates or evidence about the frozen bags.",
    },
    {
        "evidence_id": "prop_community_roast_preference_disagreement_scope",
        "node_type": "proposition",
        "subject": "individual New Haven coffee participants",
        "predicate": "show_preference_openness_and_direct_roaster_disagreement",
        "object": "a dark-roast-preferring author pleasantly surprised by some medium roasts and commenters who call one roaster both a favorite and dreadful",
        "source_url": SEARCHES[9][3],
        "search_id": "community_roast_disagreement",
        "role": "community",
        "scope": "individual_taste_disagreement_not_controlled_roast_test_population_rate_or_frozen_bag_result",
        "quotes": [
            "hi! does anyone have recommendations on a where to get coffee beans/coffee grounds in the area (i generally prefer dark roast but in the past i've tried some medium roast that has pleasantly surprised me)?",
            "Willoughby's is the goat.",
            "I personally think Willoughby’s is dreadful, but if you’re into dark/medium roasts, they’ll probably have more of that then the other places I mentioned.",
        ],
        "accepted": "One New Haven author reports a dark-roast preference with pleasant medium-roast surprises, while commenters directly disagree about the same roaster; this supports household-specific blinded testing, not a controlled roast comparison, population preference, or result for a frozen bag.",
    },
    {
        "evidence_id": "prop_community_espresso_sampling_freshness_scope",
        "node_type": "proposition",
        "subject": "individual Rhode Island coffee participants",
        "predicate": "report_sampling_and_personal_espresso_bean_selection_views",
        "object": "a plan to buy from multiple places, availability of blends and single origins, and one person's medium-dark, low-oil, and fresh-bean preferences for espresso",
        "source_url": SEARCHES[10][3],
        "search_id": "community_espresso_sampling",
        "role": "community",
        "scope": "individual_advice_not_universal_machine_rule_exact_bag_test_or_population_outcome",
        "quotes": [
            "Looks like I'll have to pick up some from multiple places.",
            "Definitely the place for a coffee gourmet. They have many many different blends and single origin coffees all roasted in house. they definitely know there stuff",
            "FYI for OP, any coffee bean can be used for espresso. Some coffee roasters will make an “espresso” blend, but you don’t need an espresso blend of coffee to make espresso. I typically use a medium dark roast. A less oily bean usually gives me a better pull, but it’s not necessarily required. A fresh roast also usually pulls better than one sitting on the shelf for months.",
        ],
        "accepted": "One Rhode Island thread includes a plan to sample multiple places, notes both blends and single origins, and records one person's medium-dark, lower-oil, and freshness preferences for espresso; this is scoped advice, not a universal machine rule, exact-bag test, or population outcome.",
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
            "registry_id": "reg_case_spec_daily_milk_espresso_0038",
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
            "bridge_offer_unit_cost_and_label_matrix",
            "bridge",
            "three frozen coffee offers",
            "normalizes_comparable_cost_and_preserves_missing_fields",
            "compare exact SKU, size, price, rating, format, and seller labels; compute 16.98 and 7.74 dollars per pound only for the one- and two-pound whole-bean offers and leave the 28-dollar herbal instant offer without a comparable unit cost",
            "coffee_offer_unit_cost_and_label_matrix_v1",
        ),
        (
            "bridge_species_mechanism_not_exact_bag",
            "bridge",
            "Arabica and Robusta mechanism comparison",
            "separates_general_species_context_from_exact_product_identity",
            "use general caffeine, yield, cost, bitterness, body, and crema context without authenticating an exact bag, species ratio, roast, caffeine dose, or cup outcome",
            "species_mechanism_not_exact_bag_identity_v1",
        ),
        (
            "bridge_origin_species_espresso_axis_separation",
            "bridge",
            "origin, species, blend, and espresso labels",
            "keeps_geography_botany_and_extraction_as_distinct_axes",
            "treat single origin as a broad geographic label, Arabica and Robusta as species, blend as a composition or origin label that requires details, and espresso as an extraction method",
            "origin_species_and_espresso_axis_separation_v1",
        ),
        (
            "bridge_milk_recipe_not_sensory_erasure",
            "bridge",
            "milk-based espresso comparison",
            "uses_recipe_control_without_inventing_masking_result",
            "hold the espresso and milk recipe constant but do not claim that milk erases bean differences until a blinded repeated household comparison observes it",
            "milk_recipe_not_sensory_erasure_v1",
        ),
        (
            "bridge_scoped_community_rebuy_and_disagreement",
            "bridge",
            "community coffee trajectories",
            "retains_author_preference_and_method_scope",
            "use repeat buying, long custom-blend use, sampling, freshness views, and direct taste disagreement as trial-design prompts rather than population evidence or exact-bag outcomes",
            "scoped_coffee_community_transfer_limit_v1",
        ),
        (
            "bridge_conditional_daily_milk_espresso_trial",
            "bridge",
            "reversible daily milk-espresso trial",
            "requires_verified_offers_and_fixed_recipe_repeats",
            "verify exact products, exclude incomparable formats or ingredients, then compare small quantities with fixed dose, grind, yield, time, milk, temperature, blinded order, repeated days, and predeclared taste, caffeine, workflow, waste, and cost thresholds",
            "conditional_daily_milk_espresso_trial_v1",
        ),
        (
            "decision_evidence_bounded_milk_espresso_rebuy",
            "decision",
            "daily milk-espresso bean rebuy",
            "selects_lowest_cost_repeatably_admissible_exact_option",
            "rebuy the lowest total-cost exact candidate that passes label, ingredient, format, freshness, fixed-recipe household taste, caffeine, workflow, and waste gates; use a smaller benchmark or defer when no candidate passes",
            "evidence_bounded_milk_espresso_rebuy_v1",
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
        "bridge_offer_unit_cost_and_label_matrix": [
            "prop_single_origin_arabica_offer_snapshot",
            "prop_sumatra_blend_offer_snapshot",
            "prop_arabica_robusta_herbal_offer_snapshot",
        ],
        "bridge_species_mechanism_not_exact_bag": [
            "prop_arabica_robusta_herbal_offer_snapshot",
            "prop_arabica_general_species_scope",
            "prop_robusta_general_species_and_espresso_scope",
        ],
        "bridge_origin_species_espresso_axis_separation": [
            "prop_single_origin_arabica_offer_snapshot",
            "prop_sumatra_blend_offer_snapshot",
            "prop_single_origin_geographic_label_scope",
            "prop_espresso_is_extraction_method_scope",
        ],
        "bridge_milk_recipe_not_sensory_erasure": [
            "prop_espresso_is_extraction_method_scope",
            "prop_cappuccino_fixed_milk_recipe_scope",
        ],
        "bridge_scoped_community_rebuy_and_disagreement": [
            "prop_community_long_term_rebuy_scope",
            "prop_community_roast_preference_disagreement_scope",
            "prop_community_espresso_sampling_freshness_scope",
        ],
        "bridge_conditional_daily_milk_espresso_trial": [
            "bridge_offer_unit_cost_and_label_matrix",
            "bridge_species_mechanism_not_exact_bag",
            "bridge_origin_species_espresso_axis_separation",
            "bridge_milk_recipe_not_sensory_erasure",
            "bridge_scoped_community_rebuy_and_disagreement",
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
                "source_id": "decision_evidence_bounded_milk_espresso_rebuy",
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
