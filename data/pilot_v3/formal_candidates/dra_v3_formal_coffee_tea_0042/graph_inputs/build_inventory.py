#!/usr/bin/env python3
"""Build the frozen Q42 tea taste-per-dollar evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0042-premium-loose-leaf-value-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0042/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0042-premium-loose-leaf-value-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0042-premium-loose-leaf-value-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0042"
TOPIC = "tea_loose_leaf_bag_taste_per_dollar_boundary"


SEARCHES = [
    (
        "ninas_premium_tin",
        "001-shopping-ninas-premium-loose-tin.json",
        "Nina's premium-priced loose-tea tin snapshot",
        "http://localhost:7770/nina-s-paris-fete-de-versailles-french-loose-tea-in-original-white-tin-2-8-ounces-imported.html",
    ),
    (
        "t2_mid_loose",
        "002-shopping-t2-midprice-loose-box.json",
        "T2 middle-price loose-leaf box snapshot",
        "http://localhost:7770/t2-tea-new-york-breakfast-black-tea-loose-leaf-in-a-box-100g-3-5oz.html",
    ),
    (
        "hyleys_low_loose_tin",
        "003-shopping-hyleys-lowprice-loose-tin.json",
        "Hyleys low-price flavored loose-tea tin snapshot",
        "http://localhost:7770/hyleys-traveller-s-collection-1001-mystery-loose-leaf-black-tea-with-strawberry-and-cranberry-in-tin-3-52-ounce-100g-100-natural-sugar-free-gluten-free-and-non-gmo.html",
    ),
    (
        "twinings_bags",
        "004-shopping-twinings-supermarket-bags.json",
        "Twinings 100-count supermarket-style bag snapshot",
        "http://localhost:7770/twinings-of-london-english-breakfast-black-tea-bags-100-count-pack-of-1.html",
    ),
    (
        "tea_processing",
        "005-wiki-tea-processing-flavor-variables.json",
        "tea processing, cultivar, leaf-quality, blending, and flavor context",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Tea_processing",
    ),
    (
        "tea_leaf_grading",
        "006-wiki-tea-leaf-grading.json",
        "tea leaf grading, size, and cross-price format boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Tea_leaf_grading",
    ),
    (
        "ctc",
        "007-wiki-ctc-tea-bag-process.json",
        "CTC manufacture and typical tea-bag context",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Crush%2C_tear%2C_curl",
    ),
    (
        "black_tea_brew",
        "008-wiki-black-tea-brew-comparison.json",
        "black-tea process, brewing, and sensory comparison context",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Black_tea",
    ),
    (
        "kettle_confound",
        "009-forum-kettle-confound-favorite-tea.json",
        "favorite-tea and kettle-contamination incident",
        "http://localhost:9999/f/tifu/114383/tifu-by-descaling-the-kettle-forgetting-about-it-and-having",
    ),
    (
        "chai_variability",
        "010-forum-chai-preparation-variability.json",
        "individual report of inconsistent chai preparation",
        "http://localhost:9999/f/CambridgeMA/75747/spill-the-tea-where-s-the-best-chai-in-cambridge-somerville",
    ),
    (
        "infuser_setup",
        "011-forum-loose-tea-infuser-setup.json",
        "individual tea-infuser shopping question",
        "http://localhost:9999/f/boston/59605/tea-ware-in-or-around-boston",
    ),
    (
        "loose_tea_availability",
        "012-forum-providence-loose-leaf-availability.json",
        "individual loose-leaf availability question",
        "http://localhost:9999/f/providence/90027/tea-shops",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_ninas_price_mass_conflict_scope",
        "subject": "frozen Nina's loose-tea seller page",
        "predicate": "shows_premium_price_rating_and_conflicting_mass_fields",
        "object": "SKU B082YCZMZ5 at 34 dollars and 87 percent over three reviews with 2.8 ounces in the title but 3.5 ounces or 100 grams in the body",
        "source_url": SEARCHES[0][3],
        "search_id": "ninas_premium_tin",
        "role": "product",
        "scope": "seller_offer_with_unresolved_net_content_conflict_not_independent_taste_or_value",
        "quotes": [
            "Nina's Paris, Fete de Versailles French Loose Tea in Original White Tin, 2.8 Ounces, Imported",
            "In stock SKU B082YCZMZ5 Rating: 87 % of 100 3 Reviews Add Your Review $34.00",
            "Each tin holds 100g (3.5 oz) of loose tea.",
        ],
        "accepted": "The frozen Nina's page lists SKU B082YCZMZ5 at 34 dollars with an 87-percent-of-100 aggregate over three reviews, while the title says 2.8 ounces and the body says 100 grams or 3.5 ounces; the exact selected net tea mass must be resolved before cost-per-cup calculation, and the seller fields do not prove independent taste or value.",
    },
    {
        "evidence_id": "prop_t2_midprice_variant_scope",
        "subject": "frozen T2 loose-leaf seller page",
        "predicate": "shows_midprice_loose_box_and_variant_selector",
        "object": "SKU B07GDT9HKY at 16.50 dollars titled as a 100-gram or 3.5-ounce loose-leaf box with no posted review aggregate and multiple sizes and styles",
        "source_url": SEARCHES[1][3],
        "search_id": "t2_mid_loose",
        "role": "product",
        "scope": "seller_offer_and_variant_selector_not_confirmed_checkout_variant_or_independent_quality",
        "quotes": [
            "T2 Tea - New York Breakfast Black Tea, Loose Leaf in a Box 100g (3.5oz)",
            "In stock SKU B07GDT9HKY Be the first to review this product $16.50",
            "Style Foil (Loose Leaf) Limited Edition Tin (Loose Leaf) Limited Edition Tin (Tea Bag) Loose Leaf in Cube Tea Bag in Cube Tin (Loose Leaf) Tin (Tea Bag)",
        ],
        "accepted": "The frozen T2 page lists SKU B07GDT9HKY at 16.50 dollars, titles it as a 100-gram or 3.5-ounce loose-leaf box, shows no posted review aggregate, and exposes multiple size and style choices; it does not by itself confirm the checkout variant, delivered price, dose, cup yield, or independent sensory quality.",
    },
    {
        "evidence_id": "prop_hyleys_lowprice_loose_scope",
        "subject": "frozen Hyleys flavored loose-tea seller page",
        "predicate": "shows_lowprice_loose_tin_and_aggregate",
        "object": "SKU B07DLR71Q6 at 7.70 dollars for a 100-gram or 3.52-ounce strawberry-cranberry black loose-tea tin rated 68 percent over twelve reviews",
        "source_url": SEARCHES[2][3],
        "search_id": "hyleys_low_loose_tin",
        "role": "product",
        "scope": "seller_offer_showing_loose_tin_is_not_inherently_premium_not_matched_taste_or_health_evidence",
        "quotes": [
            "Hyleys Traveller's Collection 1001 Mystery Loose Leaf Black Tea with Strawberry and Cranberry in Tin, 3.52 Ounce (100g)",
            "In stock SKU B07DLR71Q6 Rating: 68 % of 100 12 Reviews Add Your Review $7.70",
        ],
        "accepted": "The frozen Hyleys page lists SKU B07DLR71Q6 at 7.70 dollars for a flavored 100-gram or 3.52-ounce loose-leaf tin and shows a 68-percent-of-100 aggregate over twelve reviews; it demonstrates that loose tea in a tin is not inherently a high sticker-price category, but it does not prove taste, value, health effects, or comparability with plain English Breakfast bags.",
    },
    {
        "evidence_id": "prop_twinings_bag_offer_scope",
        "subject": "frozen Twinings bag seller page",
        "predicate": "shows_bag_count_price_rating_and_seller_brew_copy",
        "object": "SKU B001GM60LE at 9.26 dollars for 100 English Breakfast bags rated 48 percent over twelve reviews with a four-minute seller instruction",
        "source_url": SEARCHES[3][3],
        "search_id": "twinings_bags",
        "role": "product",
        "scope": "seller_count_offer_and_instruction_not_tea_mass_per_bag_accepted_yield_or_independent_taste",
        "quotes": [
            "Twinings of London English Breakfast Black Tea Bags, 100 Count (Pack of 1)",
            "In stock SKU B001GM60LE Rating: 48 % of 100 12 Reviews Add Your Review $9.26",
            "Steep for four minutes for the perfect cup of english breakfast tea.",
        ],
        "accepted": "The frozen Twinings page lists SKU B001GM60LE at 9.26 dollars for 100 English Breakfast bags with a 48-percent-of-100 aggregate over twelve reviews and seller advice to steep four minutes; it does not establish net tea mass per bag, accepted-cup yield, delivered cost, independent taste, or comparability with the flavored loose teas.",
    },
    {
        "evidence_id": "prop_processing_flavor_multi_axis_scope",
        "subject": "tea flavor determinants in processing",
        "predicate": "depends_on_cultivar_leaf_quality_processing_blending_and_flavorants",
        "object": "tea category and final flavor or aroma depend on more than loose or bag format",
        "source_url": SEARCHES[4][3],
        "search_id": "tea_processing",
        "role": "concept",
        "scope": "general_flavor_mechanisms_not_exact_offer_grade_quality_or_preference",
        "quotes": [
            "The categories of tea are distinguished by the processing they undergo.",
            "The innate flavor of the dried tea leaves is determined by the type of cultivar of the tea bush, the quality of the plucked tea leaves, and the manner and quality of the production processing they undergo.",
            "After processing, a tea may be blended with other teas or mixed with flavourants to alter the flavor of the final tea.",
        ],
        "accepted": "The tea-processing page says processing distinguishes tea categories and that cultivar, plucked-leaf quality, production processing, blending, and flavorants affect final flavor; these are general mechanisms and do not identify the grade, production quality, taste, or value of any exact captured offer.",
    },
    {
        "evidence_id": "prop_leaf_grade_format_ordering_scope",
        "subject": "tea leaf grading and format boundaries",
        "predicate": "uses_leaf_condition_and_size_without_universal_cross_product_order",
        "object": "leaf size affects preparation while expensive fannings may outperform cheaper whole leaf and bags may contain different grades",
        "source_url": SEARCHES[5][3],
        "search_id": "tea_leaf_grading",
        "role": "concept",
        "scope": "general_grading_and_cross_price_counterexample_not_exact_product_grade_or_taste_rank",
        "quotes": [
            "Tea leaf grading is the process of evaluating tea based on the quality and condition of the tea leaves themselves.",
            "In general, larger leaves or pieces require a longer steeping time.",
            "However, the fannings of expensive teas can still be more expensive and more flavourful than whole leaves of cheaper teas.",
        ],
        "accepted": "The tea-leaf-grading page defines grading by leaf quality and condition, says larger pieces generally require longer steeping, and explicitly allows expensive fannings to be more flavorful than cheaper whole leaf; it defeats a universal whole-leaf or bag ordering and does not grade or rank the exact four offers.",
    },
    {
        "evidence_id": "prop_ctc_typical_bag_scope",
        "subject": "CTC manufacture and typical bag use",
        "predicate": "produces_small_pellets_suited_to_quick_dark_brews",
        "object": "general convenience, price, liquor, flavor, and bitterness context for CTC-type tea",
        "source_url": SEARCHES[6][3],
        "search_id": "ctc",
        "role": "concept",
        "scope": "general_ctc_context_not_proof_of_exact_twinings_process_or_personal_preference",
        "quotes": [
            "Crush, tear, curl (sometimes cut, tear, curl ) is a method of processing tea leaves into black tea in which the leaves are passed through a series of cylindrical rollers with hundreds of sharp teeth that crush, tear, and curl the tea into small, hard pellets.",
            "CTC and Rotorvane orthodox have a finished product that is well suited for tea bags , as the product quickly gives a dark brew.",
            "The convenience, low price, strong liquor, generic flavor, and mild bitterness all have contributed to the near-monopoly that CTC-type teas now enjoy in South Asia.",
        ],
        "accepted": "The CTC page describes crushing, tearing, and curling leaves into small pellets, says CTC-type output is generally suited to tea bags and quick dark brews, and gives convenience, low price, strong liquor, generic flavor, and mild bitterness as general context; it does not prove the process used by the exact Twinings bags or the drinker's preference.",
    },
    {
        "evidence_id": "prop_black_tea_brew_sensory_scope",
        "subject": "black-tea brewing and sensory comparison",
        "predicate": "requires_controlled_dose_temperature_time_and_comparison_procedure",
        "object": "particle size and steeping alter extraction while ISO 3103 is a comparison method rather than an everyday recipe",
        "source_url": SEARCHES[7][3],
        "search_id": "black_tea_brew",
        "role": "concept",
        "scope": "general_brew_and_sensory_protocol_not_exact_best_recipe_or_preference_result",
        "quotes": [
            "Longer steeping times makes the tea bitter",
            "The ISO Standard 3103 defines how to brew tea for sensory testing.",
            "This standard is not meant to define the proper method for brewing tea intended for general consumption, but rather to document a tea brewing procedure where meaningful sensory comparisons can be made.",
        ],
        "accepted": "The black-tea page says longer steeping can make tea bitter and describes ISO 3103 as a documented method for meaningful sensory comparison rather than the proper everyday recipe; it supports controlled dose, water, temperature, time, vessel, and order without supplying an exact best recipe or a taste result for these offers.",
    },
    {
        "evidence_id": "prop_kettle_confound_anecdote_scope",
        "subject": "favorite-tea kettle incident",
        "predicate": "mistook_a_brew_setup_contaminant_for_recipe_change",
        "object": "one habitual drinker's perceived citrus change was traced to diluted vinegar left in a kettle",
        "source_url": SEARCHES[8][3],
        "search_id": "kettle_confound",
        "role": "community",
        "scope": "single_incident_and_personal_preference_not_prevalence_causal_rate_or_product_evidence",
        "quotes": [
            "Kroger brand ginger and turmeric tea. She will buy out the entire stock on a weekly basis. It's her fave tea, and as tea drinkers know, if they change the recipe it's hard to find something the same.",
            "I explain that her tea isn't \"Too lemony,\" it's that she's been sipping hot vinegar tea.",
        ],
        "accepted": "The descaling thread describes one habitual drinker's favorite tea and one incident where a perceived recipe change was traced to diluted vinegar left in the kettle; it identifies brew setup as a possible confound but is not a rate, controlled study, or evidence about any captured product.",
    },
    {
        "evidence_id": "prop_chai_variability_anecdote_scope",
        "subject": "afternoon chai preparation report",
        "predicate": "reports_same_shop_as_hit_or_miss",
        "object": "one drinker described cups ranging from plain milk tea to spicy chai",
        "source_url": SEARCHES[9][3],
        "search_id": "chai_variability",
        "role": "community",
        "scope": "single_author_shop_and_chai_context_not_exact_offer_or_general_variability_rate",
        "quotes": [
            "I'm an afternoon chai kind of guy.",
            "Darwin's was my go-to before their devastating demise, though too be fair their chai was sometimes hit or miss (sometimes just milk tea, sometimes nice and spicy).",
        ],
        "accepted": "The Cambridge thread contains one afternoon chai drinker's report that a former shop was sometimes plain milk tea and sometimes spicy; it makes preparation consistency a field to control but does not estimate a rate or test the exact loose teas and bags.",
    },
    {
        "evidence_id": "prop_infuser_setup_question_scope",
        "subject": "tea-infuser shopping question",
        "predicate": "asks_where_to_inspect_and_buy_equipment",
        "object": "one author wants an in-person tea-ware and infuser purchase experience",
        "source_url": SEARCHES[10][3],
        "search_id": "infuser_setup",
        "role": "community",
        "scope": "individual_equipment_question_not_required_equipment_price_or_universal_setup_burden",
        "quotes": [
            "Dear Bostonians, is there any store you know i can buy tea infusers?",
            "It’d be nice to have a specialized place to enjoy the in person experience of checking tea ware.",
        ],
        "accepted": "The Boston thread asks where to inspect and buy tea infusers in person; it supports checking whether the buyer needs equipment and its actual cost, but it provides no equipment price, performance result, or universal loose-tea setup burden.",
    },
    {
        "evidence_id": "prop_loose_tea_availability_question_scope",
        "subject": "loose-leaf retail availability question",
        "predicate": "asks_for_shops_selling_loose_leaf_tea",
        "object": "one author is willing to search statewide for a loose-leaf seller",
        "source_url": SEARCHES[11][3],
        "search_id": "loose_tea_availability",
        "role": "community",
        "scope": "individual_local_availability_question_not_current_stock_price_quality_or_general_access_rate",
        "quotes": [
            "does anyone know if there are any tea shops that sell loose leaf teas?",
            "doesn’t even have to be in providence it can be anywhere in the state",
        ],
        "accepted": "The Providence thread asks where loose-leaf tea is sold and is willing to search statewide; it makes current availability and sample access fields to verify, but it does not establish current stock, price, quality, or a general access rate.",
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
            "registry_id": "reg_case_spec_tea_value_0042",
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
            "bridge_seller_offer_scope",
            "bridge",
            "four unmatched frozen tea offers",
            "retain_offer_fields_and_resolve_measurement_conflicts",
            "record exact SKU variant price rating count mass style and flavor while resolving Nina's net-content conflict and refusing seller fields as independent taste or value proof",
            "seller_offer_and_measurement_scope_v1",
        ),
        (
            "bridge_quality_format_boundary",
            "bridge",
            "processing grading leaf size and format",
            "prevent_universal_loose_leaf_bag_or_price_ordering",
            "use cultivar leaf quality processing blending grading size and the fannings counterexample without assigning an exact offer a grade or universal quality rank",
            "tea_quality_format_boundary_v1",
        ),
        (
            "bridge_brew_sensory_control",
            "bridge",
            "CTC black-tea brewing and sensory comparison",
            "requires_matched_style_and_fixed_brew_variables",
            "treat CTC and extraction as general context and fix dose water temperature time vessel additions serving temperature coding and order for comparison",
            "brewing_and_sensory_control_v1",
        ),
        (
            "bridge_community_scope",
            "bridge",
            "four community preference preparation equipment and availability pages",
            "retain_author_incident_shop_and_question_scope",
            "use favorite tea kettle contamination chai inconsistency infuser shopping and loose-tea access only as individual fields to check rather than tests or rates",
            "community_preference_setup_scope_v1",
        ),
        (
            "bridge_matched_format_personal_trial",
            "bridge",
            "causal format question versus personal purchase question",
            "requires_two_labeled_small_blinded_trials",
            "use a closest-feasible plain matched pair to test format and separately compare the actual unmatched candidates across ten counterbalanced blinded pairs with predeclared preference score and defect gates",
            "matched_format_and_personal_trial_v1",
        ),
        (
            "bridge_accepted_cup_cost_threshold",
            "bridge",
            "effective cost per accepted cup",
            "requires_measured_yield_equipment_waste_and_incremental_cap",
            "divide delivered tea equipment allocation and discarded-brew cost by accepted cups and require no more than 0.20 dollars incremental cost per accepted cup after the taste gate",
            "accepted_cup_cost_and_threshold_v1",
        ),
        (
            "decision_evidence_bounded_tea_value_purchase",
            "decision",
            "daily tea value purchase",
            "selects_cheapest_exact_passing_option_or_bag_baseline_or_deferral",
            "resolve offer identity and measurements run matched and personal trials compute effective cost and choose the cheapest exact option clearing all gates otherwise keep bags or defer without a universal format claim",
            "evidence_bounded_tea_value_purchase_v1",
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
        "bridge_seller_offer_scope": [
            "prop_ninas_price_mass_conflict_scope",
            "prop_t2_midprice_variant_scope",
            "prop_hyleys_lowprice_loose_scope",
            "prop_twinings_bag_offer_scope",
        ],
        "bridge_quality_format_boundary": [
            "prop_processing_flavor_multi_axis_scope",
            "prop_leaf_grade_format_ordering_scope",
        ],
        "bridge_brew_sensory_control": [
            "prop_ctc_typical_bag_scope",
            "prop_black_tea_brew_sensory_scope",
        ],
        "bridge_community_scope": [
            "prop_kettle_confound_anecdote_scope",
            "prop_chai_variability_anecdote_scope",
            "prop_infuser_setup_question_scope",
            "prop_loose_tea_availability_question_scope",
        ],
        "bridge_matched_format_personal_trial": [
            "bridge_seller_offer_scope",
            "bridge_quality_format_boundary",
            "bridge_brew_sensory_control",
            "bridge_community_scope",
        ],
        "bridge_accepted_cup_cost_threshold": [
            "bridge_seller_offer_scope",
            "bridge_brew_sensory_control",
            "bridge_community_scope",
            "bridge_matched_format_personal_trial",
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
                "source_id": "decision_evidence_bounded_tea_value_purchase",
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
