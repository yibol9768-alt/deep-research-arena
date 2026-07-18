#!/usr/bin/env python3
"""Build the frozen Q41 remote-pantry storage-format inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0041-remote-pantry-storage-formats-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0041/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0041-remote-pantry-storage-formats-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0041-remote-pantry-storage-formats-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0041"
TOPIC = "remote_pantry_storage_format_and_rotation_boundary"


SEARCHES = [
    ("peruvian_whole_bean", "001-shopping-peruvian-whole-bean-three-bag.json", "whole-bean three-bag seller snapshot", "http://localhost:7770/organic-peruvian-coffee-beans-organic-peruvian-whole-beans-coffee-medium-roast-100-arabica-fair-trade-non-gmo-fair-trade-organic-coffee-beans-by-swan-life-essentials-36-ounce-3-bag.html"),
    ("don_francisco_ground", "002-shopping-don-francisco-ground-cans.json", "ground-coffee three-can seller snapshot", "http://localhost:7770/don-francisco-s-vanilla-nut-flavored-ground-coffee-3-x12-oz-cans.html"),
    ("mount_hagen_instant", "003-shopping-mount-hagen-freeze-dried-instant.json", "freeze-dried instant two-pouch seller snapshot", "http://localhost:7770/mount-hagen-7-05-oz-organic-fair-trade-freeze-dried-decaffeinated-2-pack-instant-coffee-resealable-doypack-bag-kosher-single-origin-100-arabica-freeze-dried-coffee-packets-instant-coffee-for-camping.html"),
    ("basilur_loose_leaf", "004-shopping-basilur-loose-leaf-metal-tins.json", "loose-leaf two-tin seller snapshot", "http://localhost:7770/basilur-ceylon-english-breakfast-tea-earl-grey-tea-pure-ceylon-black-tea-single-origin-and-low-elevation-100g-loose-leaf-per-metal-tin-pack-of-2.html"),
    ("imozai_wrapped_bags", "005-shopping-imozai-individually-wrapped-tea-bags.json", "individually wrapped tea-bag seller snapshot", "http://localhost:7770/imozai-organic-oolong-tea-bags-100-count-individually-wrapped.html"),
    ("shelf_life", "006-wiki-shelf-life.json", "shelf-life condition and endpoint boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Shelf_life"),
    ("vacuum_packing", "007-wiki-vacuum-packing.json", "vacuum-packing mechanism boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Vacuum_packing"),
    ("freeze_drying", "008-wiki-freeze-drying.json", "freeze-drying mechanism boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Freeze_drying"),
    ("water_activity", "009-wiki-water-activity.json", "water-activity measurement boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Water_activity"),
    ("rancidification", "010-wiki-rancidification.json", "rancidification mechanism boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Rancidification"),
    ("bifl_food_storage", "011-forum-bifl-food-storage-containers.json", "one general food-container discussion", "http://localhost:9999/f/BuyItForLife/53732/bifl-food-storage-containers"),
    ("stackable_glass", "012-forum-stackable-glass-storage-containers.json", "one stackable-glass-container discussion", "http://localhost:9999/f/BuyItForLife/32783/stackable-glass-storage-containers"),
    ("freezer_fridge", "013-forum-freezer-fridge-storage-containers.json", "one cold-storage-container discussion", "http://localhost:9999/f/BuyItForLife/32741/suggestions-for-food-storage-containers-that-will-spend-time"),
    ("bulk_dry_food", "014-forum-bulk-dry-food-container.json", "one bulk-dry-food-container discussion", "http://localhost:9999/f/BuyItForLife/75598/container-to-store-5-10lb-bulk-dry-food-such-as-beans-and"),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_peruvian_whole_bean_multibag_snapshot",
        "subject": "frozen Peruvian whole-bean seller page",
        "predicate": "asserts_three_bag_offer_and_coffee_attributes",
        "object": "SKU B096T2F4V9 at 39.95 dollars for a nominal 36-ounce three-bag whole-bean offer with medium-roast Arabica and certification language",
        "source_url": SEARCHES[0][3], "search_id": "peruvian_whole_bean", "role": "product",
        "scope": "seller_offer_not_exact_lot_date_barrier_seal_storage_or_one_year_quality",
        "quotes": [
            "In stock SKU B096T2F4V9 Be the first to review this product $39.95 Qty Add to Cart Add to Wish List Add to Compare",
            "Our Peruvian Fair Trade and Organic certified medium roast coffee (100% Pure Arabica Coffee) is great for novice coffee drinkers and coffee connoisseurs alike.",
        ],
        "accepted": "The frozen whole-bean page shows SKU B096T2F4V9 at 39.95 dollars for a nominal 36-ounce three-bag offer and describes medium-roast Arabica plus certification language; it supplies no exact lot's roast, pack, or best-before date, bag barrier, fill gas, seal test, storage history, opened duration, or twelve-month sensory result.",
    },
    {
        "evidence_id": "prop_don_francisco_ground_can_snapshot",
        "subject": "frozen Don Francisco ground-coffee seller page",
        "predicate": "asserts_three_can_offer_and_freshness_copy",
        "object": "SKU B076ZZ1FGP at 16.47 dollars for three 12-ounce cans with a 65-percent-of-100 aggregate over twelve reviews and seller freshness and aroma claims",
        "source_url": SEARCHES[1][3], "search_id": "don_francisco_ground", "role": "product",
        "scope": "seller_copy_and_store_aggregate_not_exact_can_or_one_year_test",
        "quotes": [
            "In stock SKU B076ZZ1FGP Rating: 65 % of 100 12 Reviews Add Your Review $16.47",
            "Our steel can locks in the unmistakable aroma from our freshly roasted 100% premium Arabica beans.",
            "Our steel cans protect the freshness and aroma of our coffee; they’re recyclable for the preservation of our planet",
        ],
        "accepted": "The frozen ground-coffee page shows SKU B076ZZ1FGP at 16.47 dollars for three 12-ounce cans with a 65-percent-of-100 aggregate over twelve reviews and seller claims that steel cans protect freshness and lock in aroma; neither the copy nor aggregate establishes the exact cans' dates, fill gas, residual oxygen, seal integrity, opened performance, storage history, or twelve-month outcome.",
    },
    {
        "evidence_id": "prop_mount_hagen_instant_pouch_snapshot",
        "subject": "frozen Mount Hagen instant-coffee seller page",
        "predicate": "asserts_freeze_dried_two_pouch_offer",
        "object": "SKU B08F9H762R at 40.98 dollars for two 7.05-ounce decaffeinated instant-coffee pouches with resealable Doypack and granule-protection language",
        "source_url": SEARCHES[2][3], "search_id": "mount_hagen_instant", "role": "product",
        "scope": "seller_format_and_package_claim_not_exact_barrier_reseal_or_storage_trial",
        "quotes": [
            "In stock SKU B08F9H762R Be the first to review this product $40.98 Qty Add to Cart Add to Wish List Add to Compare",
            "RESEALABLE DOYPACK: 2 resealable bags to keep your best instant coffee fresh, expertly packed to protect the granules",
            "BULK VALUE: 2 7.05oz decaffeinated bulk instant coffee packs, save on price without compromising on quality coffee, great for coffee jar refill",
        ],
        "accepted": "The frozen instant-coffee page shows SKU B08F9H762R at 40.98 dollars for two 7.05-ounce decaffeinated freeze-dried pouches and calls the Doypack bags resealable and protective of granules; the seller page supplies no exact lot date, measured water activity, film barrier, seal or repeated-reseal test, opened exposure, storage history, or twelve-month sensory result.",
    },
    {
        "evidence_id": "prop_basilur_loose_leaf_tin_snapshot",
        "subject": "frozen Basilur loose-leaf tea seller page",
        "predicate": "asserts_two_metal_tin_offer_and_freshness_copy",
        "object": "SKU B092DXH7S8 at 24.99 dollars for two 100-gram loose-leaf metal tins with an 80-percent-of-100 aggregate over eight reviews and packed-at-source and garden-fresh copy",
        "source_url": SEARCHES[3][3], "search_id": "basilur_loose_leaf", "role": "product",
        "scope": "seller_copy_and_aggregate_not_exact_tin_barrier_dates_or_one_year_result",
        "quotes": [
            "In stock SKU B092DXH7S8 Rating: 80 % of 100 8 Reviews Add Your Review $24.99",
            "Available in exquisitely crafted metal tins with Loose Leaf Tea (100g per tin)",
            "Pure Ceylon Tea, Packed at Source in Sri Lanka and Garden Fresh",
        ],
        "accepted": "The frozen loose-leaf page shows SKU B092DXH7S8 at 24.99 dollars for two 100-gram metal tins with an 80-percent-of-100 aggregate over eight reviews and seller copy saying packed at source and garden fresh; it gives no exact lot dates, tin lining or barrier, headspace, closure and seal test, opened duration, storage history, or twelve-month sensory outcome.",
    },
    {
        "evidence_id": "prop_imozai_wrapped_tea_bag_snapshot",
        "subject": "frozen Imozai oolong tea-bag seller page",
        "predicate": "asserts_individually_wrapped_hundred_count_offer",
        "object": "SKU B07TRYNP88 at 8.99 dollars for one hundred individually wrapped oolong tea bags with an 85-percent-of-100 aggregate over 118 reviews",
        "source_url": SEARCHES[4][3], "search_id": "imozai_wrapped_bags", "role": "product",
        "scope": "seller_unitization_and_aggregate_not_wrapper_barrier_date_or_storage_test",
        "quotes": [
            "In stock SKU B07TRYNP88 Rating: 85 % of 100 118 Reviews Add Your Review $8.99",
            "Individually wrapped.Total 100 tea bag",
        ],
        "accepted": "The frozen oolong page shows SKU B07TRYNP88 at 8.99 dollars for one hundred individually wrapped tea bags with an 85-percent-of-100 aggregate over 118 reviews; the page and aggregate do not specify wrapper material or barrier, seal integrity, exact lot dates, storage history, prepared sensory endpoint, or twelve-month performance.",
    },
    {
        "evidence_id": "prop_shelf_life_condition_boundary",
        "subject": "shelf-life duration and endpoint",
        "predicate": "depend_on_defined_quality_and_specified_conditions",
        "object": "a recommended maximum period for a defined quality under expected or specified conditions, distinct from several date, sale, use, safety, and quality concepts",
        "source_url": SEARCHES[5][3], "search_id": "shelf_life", "role": "concept",
        "scope": "generic_definition_not_exact_product_duration_or_safety_finding",
        "quotes": [
            "Shelf life is the recommended maximum time for which products or fresh (harvested) produce can be stored, during which the defined quality of a specified proportion of the goods remains acceptable under expected (or specified) conditions of distribution, storage and display.",
            "A product that has passed its shelf life might still be safe, but quality is no longer guaranteed.",
            "Shelf life depends on the degradation mechanism of the specific product.",
            "However, shelf life alone is not an accurate indicator of how long the food can safely be stored.",
        ],
        "accepted": "The shelf-life page defines a recommended maximum period for a specified quality under expected or specified distribution, storage, and display conditions, distinguishes quality from safety and several date concepts, and says degradation is product-specific; it gives no one-year duration for any exact captured product, lot, package, or opened state.",
    },
    {
        "evidence_id": "prop_vacuum_packing_boundary",
        "subject": "vacuum-packing preservation mechanism",
        "predicate": "removes_air_before_sealing_with_product_and_package_dependent_results",
        "object": "an oxygen-reduction method whose shelf-life effect depends on product, atmosphere, temperature, and package barrier",
        "source_url": SEARCHES[6][3], "search_id": "vacuum_packing", "role": "concept",
        "scope": "generic_mechanism_not_proof_any_exact_package_is_vacuumed_or_last_one_year",
        "quotes": [
            "Vacuum packing is a method of packaging that removes air from the package prior to sealing.",
            "The intent of vacuum packing is usually to remove oxygen from the container to extend the shelf life of foods and, with flexible package forms, to reduce the volume of the contents and package.",
            "Depending on the product, atmosphere, temperature, and the barrier properties of the package, vacuum packaging extends the shelf life of many foods.",
        ],
        "accepted": "The vacuum-packing page describes removing air before sealing to reduce oxygen and says shelf-life effects depend on product, atmosphere, temperature, and package barrier; it does not establish that any captured product is vacuum packed, authenticate its exact seal or barrier, or provide a product-specific one-year quality result.",
    },
    {
        "evidence_id": "prop_freeze_drying_mechanism_boundary",
        "subject": "freeze-drying preservation process",
        "predicate": "freezes_lowers_pressure_and_removes_ice_by_sublimation",
        "object": "a low-temperature dehydration process used for coffee and preservation that can retain many original qualities after rehydration",
        "source_url": SEARCHES[7][3], "search_id": "freeze_drying", "role": "concept",
        "scope": "generic_process_not_exact_product_water_activity_barrier_or_sensory_duration",
        "quotes": [
            "Freeze drying , also known as lyophilization or cryodesiccation , is a low temperature dehydration process [ 1 ] that involves freezing the product and lowering pressure, thereby removing the ice by sublimation .",
            "Because of the low temperature used in processing, [ 1 ] the rehydrated product retains many of its original qualities.",
            "Primary applications of freeze drying include biological (e.g., bacteria and yeasts), biomedical (e.g., surgical transplants), food processing (e.g., coffee), and preservation .",
        ],
        "accepted": "The freeze-drying page describes a low-temperature dehydration process that freezes a product, lowers pressure, and removes ice by sublimation, says rehydrated products can retain many original qualities, and lists coffee and preservation applications; it supplies no exact Mount Hagen process, water-activity, package, opened-pouch, or twelve-month sensory result.",
    },
    {
        "evidence_id": "prop_water_activity_boundary",
        "subject": "water activity in food",
        "predicate": "is_equilibrium_vapor_ratio_not_water_concentration",
        "object": "a product-specific variable used for shelf-stability, moisture migration, microbial control, quality, and safety",
        "source_url": SEARCHES[8][3], "search_id": "water_activity", "role": "concept",
        "scope": "generic_measurement_concept_not_exact_product_aw_or_safety_result",
        "quotes": [
            "In food science, water activity ( a w ) of a food is the ratio of its vapor pressure to the vapor pressure of water at the same temperature, both taken at equilibrium.",
            "Water activity is not simply a function of water concentration in food.",
            "Water activity is an important characteristic for food product design and food safety.",
            "They found that the values were not universal, but specific to each food product.",
        ],
        "accepted": "The water-activity page defines an equilibrium vapor-pressure ratio, says it is not simply water concentration, and describes product-specific uses in shelf stability, moisture migration, microbial control, quality, and safety; it contains no measured water activity or resulting duration for any exact captured lot or package.",
    },
    {
        "evidence_id": "prop_rancidification_boundary",
        "subject": "rancidification mechanism and sensory effects",
        "predicate": "can_follow_fat_oxidation_or_hydrolysis_under_environmental_exposure",
        "object": "air, light, moisture, or bacterial action can produce compounds associated with undesirable odors and flavors",
        "source_url": SEARCHES[9][3], "search_id": "rancidification", "role": "concept",
        "scope": "generic_degradation_mechanism_not_exact_product_rate_or_health_finding",
        "quotes": [
            "Rancidification is the process of complete or incomplete autoxidation or hydrolysis of fats and oils when exposed to air, light, moisture, or bacterial action, producing short-chain aldehydes , ketones and free fatty acids .",
            "When these processes occur in food, undesirable odors and flavors can result.",
            "In addition, rancidification can be decreased by storing fats and oils in a cool, dark place with little exposure to oxygen or free radicals, since heat and light accelerate the rate of reaction of fats with oxygen.",
        ],
        "accepted": "The rancidification page describes oxidation or hydrolysis of fats and oils under air, light, moisture, or bacterial action and says undesirable odors and flavors can result, with cool, dark, low-oxygen storage reducing some reactions; it gives no exact coffee or tea degradation rate, package result, health finding, or one-year sensory threshold.",
    },
    {
        "evidence_id": "prop_bifl_food_storage_question_scope",
        "subject": "one general food-container community discussion",
        "predicate": "reports_lid_warping_and_requests_longer_lived_small_containers",
        "object": "an individual author asks about small food and liquid containers after cheap lids bent, twisted, and stopped sealing properly",
        "source_url": SEARCHES[10][3], "search_id": "bifl_food_storage", "role": "community",
        "scope": "individual_question_and_replies_not_coffee_tea_storage_trial_or_prevalence",
        "quotes": [
            "Bifl Food Storage Containers?",
            "All of my food atarage tubs are cheap and the lids are all bent and twisted from microwaving, and don't seal properly I'm looking for a set of smaller tubs for storing food and liquids, and for taking my lunch to work Is tupperware still a good brand? I don't mind paying a little more for something that doesn't need replacing every 6 months because the lids don't go on UK based 6",
        ],
        "accepted": "One community author reports cheap food-container lids bent and twisted after microwaving, no longer seal properly, and asks for smaller durable food and liquid containers; the discussion may suggest closure and durability checks but is not a controlled coffee or tea package test, prevalence estimate, safety result, or twelve-month pantry trial.",
    },
    {
        "evidence_id": "prop_stackable_glass_container_scope",
        "subject": "one stackable-glass-container community discussion",
        "predicate": "asks_for_non_chipping_stackable_and_leak_proof_properties",
        "object": "an individual author states nesting, chipping, stacking, and leak-proof requirements while replies conflict about specific containers",
        "source_url": SEARCHES[11][3], "search_id": "stackable_glass", "role": "community",
        "scope": "individual_requirements_and_uncontrolled_replies_not_original_package_evidence",
        "quotes": [
            "Stackable Glass Storage Containers",
            "Is anyone aware of any glass storage containers that actually stack? Requirements Non-Chip Nestable/Stackable with the same size contain (i.e. 8\" will nest into an 8\") Leak-Proof Every container out there seems to not be stackable.",
            "The 1st link you have there. They leak.",
        ],
        "accepted": "One community author asks for non-chipping, same-size stackable, leak-proof glass containers, while replies include conflicting leak reports; this identifies inspection questions but does not test any captured coffee or tea's original package, pantry storage, sensory life, or safety.",
    },
    {
        "evidence_id": "prop_freezer_fridge_container_scope",
        "subject": "one freezer-and-fridge container community discussion",
        "predicate": "contains_varied_personal_reports_about_breakage_headspace_vacuum_and_odors",
        "object": "individual replies discuss glass durability, breakage, freezer headspace, vacuum sealing, stacking, and odor retention",
        "source_url": SEARCHES[12][3], "search_id": "freezer_fridge", "role": "community",
        "scope": "uncontrolled_cold_storage_experiences_not_remote_pantry_or_exact_product_trial",
        "quotes": [
            "suggestions for food storage containers that will spend time in freezer/fridge",
            "I've had one glass lock break (large crack) after doing direct transfer from fridge to microwave, but they otherwise hold up very well.",
            "I use canning jars! You just need to leave an inch of headspace (some even have a fill-to line).",
        ],
        "accepted": "One community discussion contains varied personal reports about glass durability and breakage, freezer headspace, vacuum sealing, stacking, and odor retention; these uncontrolled cold-storage experiences do not establish remote pantry conditions, exact coffee or tea package performance, a matched sensory result, or a universal container choice.",
    },
    {
        "evidence_id": "prop_bulk_dry_container_question_scope",
        "subject": "one bulk-dry-food-container community discussion",
        "predicate": "asks_about_five_to_ten_pound_storage_and_contains_disputed_airtightness",
        "object": "an individual author requests bulk bean and rice storage while replies mention buckets, gamma lids, jars, vacuum sealing, cost, and disputed airtightness",
        "source_url": SEARCHES[13][3], "search_id": "bulk_dry_food", "role": "community",
        "scope": "individual_question_and_anecdotes_not_exact_package_or_long_term_outcome",
        "quotes": [
            "container to store (5-10lb) bulk dry food, such as beans and rice?",
            "I tried a couple cheap sets from Amazon that snap seal. The plastic feels flimsy and the snap isn't easy to open and close. Oxo looks good but they are so expensive 12",
            "If you’re considering the OXO Pop containers, reconsider-they are trash. Not dishwasher safe (the ones I bought about five years ago, this may have changed) and definitely not air tight.",
        ],
        "accepted": "One community author asks about storing five to ten pounds of beans and rice, and replies mention buckets, gamma lids, jars, vacuum sealing, cost, and disputed airtightness; these anecdotes can suggest closure verification but do not test any exact captured package, coffee or tea quality, safety, or one-year outcome.",
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def typed_verifier(accepted: str) -> dict[str, Any]:
    return {"kind": "typed_claim", "matcher": "normalized_text", "accepted_phrases": [accepted], "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"]}


def build() -> dict[str, Any]:
    capture_documents = json.loads((CAPTURE / "documents.json").read_text(encoding="utf-8"))["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = f"http://localhost:8081/search?capture_run={RUN_ID}&request_id={payload['request_id']}"
        documents.append({"registry_id": f"reg_search_{search_id}", "source_url": source_url, "source_type": "search_result", "content_sha256": sha256_bytes(data), "blob_path": rel(path), "in_corpus": True})
        nodes.append({"evidence_id": f"search_{search_id}", "node_type": "search_result", "subject": subject, "predicate": "returned", "object": [target_url], "source_url": source_url, "body_support": False, "search_snippet_support": True, "verifier": {"kind": "search_observation"}, "metadata": {"discovery_root": True, "discovery_root_policy": "search_result", "topic_cluster": TOPIC}})

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append({"registry_id": row["registry_id"], "source_url": row["source_url"], "source_type": row["source_type"], "content_sha256": row["content_sha256"], "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(), "in_corpus": True})
        raw_content_by_url[row["source_url"]] = (CAPTURE / row["blob_path"]).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append({"registry_id": "reg_case_spec_remote_pantry_0041", "source_url": case_source, "source_type": "case_spec", "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()), "blob_path": CASE_SPEC_REL.as_posix(), "in_corpus": True})

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(f"quote missing from {item['evidence_id']}: {quote!r}")
            spans.append({"support_span_id": f"span_{item['evidence_id']}_{index}", "exact_quote": quote, "occurrence": 0, "support_type": "body"})
        nodes.append({"evidence_id": item["evidence_id"], "node_type": "proposition", "subject": item["subject"], "predicate": item["predicate"], "object": item["object"], "source_url": item["source_url"], "support_spans": spans, "verifier": typed_verifier(item["accepted"]), "metadata": {"acceptable_source_roles": [item["role"]], "critical": True, "scope": item["scope"], "topic_cluster": TOPIC}})
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append({"evidence_id": assertion_id, "node_type": "assertion", "subject": f"source for {item['subject']}", "predicate": "states", "object": item["object"], "source_url": item["source_url"], "support_spans": [{"support_span_id": f"span_{assertion_id}_1", "exact_quote": item["quotes"][0], "occurrence": 0, "support_type": "body"}], "verifier": {"kind": "quoted_assertion"}, "metadata": {"topic_cluster": TOPIC}})
        edges.extend([
            {"edge_id": f"edge_assert_{item['evidence_id']}", "source_id": assertion_id, "relation": "ASSERTS", "target_id": item["evidence_id"]},
            {"edge_id": f"edge_discover_{item['evidence_id']}", "source_id": item["evidence_id"], "relation": "DISCOVERABLE_FROM", "target_id": f"search_{item['search_id']}", "discovery_method": "S", "discovery_order": 1},
        ])

    deterministic_nodes = [
        ("bridge_seller_format_packaging_claim", "bridge", "five exact seller offers", "separates_format_and_packaging_copy_from_observed_storage_results", "record exact products, prices, quantities, package counts, and seller words without treating them as lot dates, verified barriers, seal tests, or one-year outcomes", "seller_format_packaging_claim_boundary_v1"),
        ("bridge_shelf_life_conditions_endpoint", "bridge", "one-year shelf-life claim", "requires_exact_endpoint_lot_state_and_conditions", "distinguish safety, quality, date, sale, and use endpoints and bind any duration to exact lot, package, unopened or opened state, and specified storage conditions", "shelf_life_condition_and_endpoint_specific_v1"),
        ("bridge_oxygen_moisture_heat_light_mechanisms", "bridge", "preservation and degradation mechanisms", "remain_measurement_variables_not_product_duration", "use vacuum, water activity, rancidification, oxygen, moisture, heat, and light to define exact measurements without assigning unobserved package performance or duration", "oxygen_moisture_heat_light_mechanism_boundary_v1"),
        ("bridge_freeze_dried_instant_scope", "bridge", "freeze-dried instant-coffee option", "requires_exact_process_package_and_opened_performance", "keep generic freeze-drying benefits and seller resealable-pouch claims separate from exact water activity, barrier, seal, rehydrated sensory, and twelve-month evidence", "freeze_dried_instant_not_universal_sensory_winner_v1"),
        ("bridge_format_opening_lot_comparison", "bridge", "whole-bean ground and instant comparison", "requires_matched_lot_package_opening_and_preparation_checks", "do not rank formats from names alone; verify dates, seals, servings, days open, conditions, preparation, and sensory endpoints for each exact option", "format_opening_and_lot_comparison_boundary_v1"),
        ("bridge_tea_unitization_scope", "bridge", "loose-leaf tins and wrapped tea bags", "treats_unitization_as_exposure_hypothesis_not_year_guarantee", "convert tins and wrappers into servings and time open while requiring exact barrier, seal, dates, and scheduled sensory checks", "tea_package_unitization_not_year_guarantee_v1"),
        ("bridge_community_container_scope", "bridge", "four community container discussions", "retains_question_and_individual_experience_scope", "use posts to suggest closure, leak, breakage, headspace, odor, stacking, and airtightness checks without treating them as coffee or tea evidence", "community_container_scope_v1"),
        ("bridge_staged_remote_pantry_trial", "bridge", "remote-pantry purchase and rotation protocol", "requires_small_calibration_verified_units_and_stop_rules", "verify exact lot and package fields, log conditions, compute opened duration, run a small controlled calibration, stock independent units, rotate earliest dates, replenish at a trigger, and defer failed or unresolved options", "staged_remote_pantry_trial_v1"),
        ("decision_evidence_bounded_remote_pantry_rotation", "decision", "twelve-month remote coffee-and-tea pantry", "selects_only_admissible_verified_and_rotatable_configuration", "choose the cheapest exact configuration that passes date, package, condition, serving, opened-duration, sensory, safety, and replenishment gates; otherwise shorten the horizon or defer, with no universal format winner", "evidence_bounded_remote_pantry_rotation_v1"),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append({"evidence_id": evidence_id, "node_type": node_type, "subject": subject, "predicate": predicate, "object": obj, "source_url": case_source, "verifier": {"kind": "deterministic_rule"}, "metadata": metadata})

    derives = {
        "bridge_seller_format_packaging_claim": ["prop_peruvian_whole_bean_multibag_snapshot", "prop_don_francisco_ground_can_snapshot", "prop_mount_hagen_instant_pouch_snapshot", "prop_basilur_loose_leaf_tin_snapshot", "prop_imozai_wrapped_tea_bag_snapshot"],
        "bridge_shelf_life_conditions_endpoint": ["prop_shelf_life_condition_boundary", "prop_peruvian_whole_bean_multibag_snapshot", "prop_don_francisco_ground_can_snapshot", "prop_mount_hagen_instant_pouch_snapshot", "prop_basilur_loose_leaf_tin_snapshot", "prop_imozai_wrapped_tea_bag_snapshot"],
        "bridge_oxygen_moisture_heat_light_mechanisms": ["prop_vacuum_packing_boundary", "prop_water_activity_boundary", "prop_rancidification_boundary", "prop_shelf_life_condition_boundary"],
        "bridge_freeze_dried_instant_scope": ["prop_mount_hagen_instant_pouch_snapshot", "prop_freeze_drying_mechanism_boundary", "prop_water_activity_boundary", "bridge_seller_format_packaging_claim", "bridge_oxygen_moisture_heat_light_mechanisms"],
        "bridge_format_opening_lot_comparison": ["prop_peruvian_whole_bean_multibag_snapshot", "prop_don_francisco_ground_can_snapshot", "prop_mount_hagen_instant_pouch_snapshot", "bridge_shelf_life_conditions_endpoint", "bridge_oxygen_moisture_heat_light_mechanisms"],
        "bridge_tea_unitization_scope": ["prop_basilur_loose_leaf_tin_snapshot", "prop_imozai_wrapped_tea_bag_snapshot", "bridge_shelf_life_conditions_endpoint", "bridge_oxygen_moisture_heat_light_mechanisms"],
        "bridge_community_container_scope": ["prop_bifl_food_storage_question_scope", "prop_stackable_glass_container_scope", "prop_freezer_fridge_container_scope", "prop_bulk_dry_container_question_scope"],
        "bridge_staged_remote_pantry_trial": ["bridge_seller_format_packaging_claim", "bridge_shelf_life_conditions_endpoint", "bridge_oxygen_moisture_heat_light_mechanisms", "bridge_freeze_dried_instant_scope", "bridge_format_opening_lot_comparison", "bridge_tea_unitization_scope", "bridge_community_container_scope"],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append({"edge_id": f"edge_{source_id}_from_{target_id}", "source_id": source_id, "relation": "DERIVES_FROM", "target_id": target_id})
    for target_id in derives:
        edges.append({"edge_id": f"edge_decision_requires_{target_id}", "source_id": "decision_evidence_bounded_remote_pantry_rotation", "relation": "REQUIRES", "target_id": target_id})

    return {"schema_version": "evidence_graph_inventory_v1", "corpus_snapshot": SNAPSHOT, "documents": documents, "nodes": nodes, "edges": edges, "support_spans": []}


def main() -> None:
    inventory = build()
    OUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": rel(OUT), "documents": len(inventory["documents"]), "nodes": len(inventory["nodes"]), "edges": len(inventory["edges"]), "critical_evidence": len(EVIDENCE), "sha256": sha256_bytes(OUT.read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
