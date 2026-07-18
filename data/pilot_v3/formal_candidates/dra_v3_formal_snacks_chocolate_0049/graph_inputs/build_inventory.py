#!/usr/bin/env python3
"""Build the frozen Q49 chocolate-process and sampler evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = (
    "dra-v3-formal-snacks-chocolate-0049-process-category-sampler-"
    "boundary-20260716-r1"
)
RUN_ID = (
    "v3-corpus-formal-snacks-chocolate-0049-process-category-sampler-"
    "boundary-20260716-r1"
)
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_snacks_chocolate_0049"
TOPIC = "chocolate_process_category_affordable_sampler_boundary"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0049/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    (
        "green_black_variety",
        "001-shopping-green-black-mixed-eight-bar-pack.json",
        "Green and Black mixed eight-bar seller offer",
        "http://localhost:7770/green-black-s-organic-chocolate-variety-pack-85-dark-chocolate-70-dark-chocolate-milk-chocolate-milk-chocolate-with-almonds-white-chocolate-easter-chocolate-gift-8-3-17-oz-bars.html",
    ),
    (
        "lindt_white",
        "002-shopping-lindt-white-single.json",
        "Lindt white single-bar seller offer",
        "http://localhost:7770/product-of-lindt-white-chocolate-bar-count-1-chocolate-candy-grab-varieties-flavors.html",
    ),
    (
        "lindt_milk",
        "003-shopping-lindt-classic-milk-two.json",
        "Lindt Classic milk two-piece seller offer",
        "http://localhost:7770/lindt-classic-recipe-milk-chocolate-bar-4-4-oz-2-pc.html",
    ),
    (
        "ritter_sixty_one",
        "004-shopping-ritter-sixty-one-single.json",
        "Ritter Sport 61-percent seller offer",
        "http://localhost:7770/ritter-sport-61-fine-dark-chocolate-bar-candy-original-german-chocolate-100g-3-52oz.html",
    ),
    (
        "chocolove_ruby",
        "005-shopping-chocolove-ruby-two-bars.json",
        "Chocolove ruby two-bar seller offer",
        "http://localhost:7770/chocolove-ruby-cacao-bar-2-bars.html",
    ),
    (
        "chocolate",
        "006-wiki-chocolate-processing-overview.json",
        "broad chocolate processing overview",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Chocolate",
    ),
    (
        "cocoa_bean",
        "007-wiki-cocoa-bean-processing.json",
        "cocoa bean and nib context",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Cocoa_bean",
    ),
    (
        "chocolate_liquor",
        "008-wiki-chocolate-liquor-composition.json",
        "chocolate-liquor composition boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Chocolate_liquor",
    ),
    (
        "cocoa_butter",
        "009-wiki-cocoa-butter-composition.json",
        "cocoa-butter composition and melting context",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Cocoa_butter",
    ),
    (
        "conching",
        "010-wiki-conching-process.json",
        "conching process and duration boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Conching",
    ),
    (
        "white_chocolate",
        "011-wiki-white-chocolate-category.json",
        "white-chocolate composition and category boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/White_chocolate",
    ),
    (
        "ruby_chocolate",
        "012-wiki-ruby-chocolate-category.json",
        "ruby-chocolate category dispute",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Ruby_chocolate",
    ),
    (
        "nj_blind_test",
        "013-forum-new-jersey-blind-chocolate-test.json",
        "one planned local blind caramel comparison",
        "http://localhost:9999/f/newjersey/43404/favorite-local-chocolate-candy-shop",
    ),
    (
        "new_haven_cocoa",
        "014-forum-new-haven-hot-cocoa-preferences.json",
        "place-specific hot-cocoa preferences",
        "http://localhost:9999/f/newhaven/86919/small-businesses-with-the-best-hot-cocoa",
    ),
    (
        "eli5_flavor",
        "015-forum-eli5-flavor-smell-texture-temperature.json",
        "lay flavor-cue discussion",
        "http://localhost:9999/f/explainlikeimfive/104197/eli5-if-the-tongue-can-only-taste-five-basic-flavors-sweet",
    ),
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


EVIDENCE = [
    ev(
        "prop_green_black_variety_offer_scope",
        "frozen Green and Black seller page",
        "shows_a_mixed_eight_bar_offer_and_mass_conflict",
        "SKU B08M4XT3XM at 22.98 dollars with no reviews shown describes eight 3.17-ounce bars across five category or recipe positions while Product Dimensions reports 3.17 ounces",
        0,
        "product",
        "frozen_mixed_offer_not_verified_total_mass_formula_or_guest_preference",
        [
            "Green & Black’s Organic Chocolate Variety Pack, 85% Dark Chocolate, 70% Dark Chocolate, Milk Chocolate, Milk Chocolate with Almonds & White Chocolate, Easter Chocolate Gift, 8 - 3.17 oz Bars",
            "In stock SKU B08M4XT3XM Be the first to review this product $22.98",
            "This bulk variety package contains 8 GREEN & BLACK’S Organic Chocolate Bars (2 - 85% Dark Chocolate, 2 - 70% Dark Chocolate, 2 Milk Chocolate with Almonds, 1 Milk Chocolate and 1 White Chocolate)",
            "Package Dimensions ‏ ‎ 9.13 x 4.53 x 4.09 inches; 3.17 Ounces",
        ],
        "The frozen Green and Black page shows SKU B08M4XT3XM at 22.98 dollars with no reviews shown and describes eight 3.17-ounce bars allocated across 85-percent dark, 70-percent dark, milk with almonds, milk and white, while Product Dimensions reports only 3.17 ounces. The selected flavor field also says 70-percent cacao. These are seller assertions with an unresolved total-mass conflict, not a verified current sampler, ingredient audit or guest preference result.",
    ),
    ev(
        "prop_lindt_white_offer_scope",
        "frozen Lindt white seller page",
        "shows_one_white_bar_without_mass_or_reviews",
        "SKU B07938SPXM at 5.39 dollars with no reviews shown and no captured mass ingredient or cocoa-component detail",
        1,
        "product",
        "frozen_minimal_seller_offer_not_formula_category_or_taste_proof",
        [
            "Product Of Lindt , White Chocolate Bar, Count 1 - Chocolate Candy / Grab Varieties & Flavors",
            "In stock SKU B07938SPXM Be the first to review this product $5.39",
        ],
        "The frozen Lindt white page shows SKU B07938SPXM at 5.39 dollars with no reviews shown and a count of one, but it provides no captured mass, ingredient panel, cocoa-butter percentage, market identity or taste result. Its title alone cannot verify that the delivered item meets a particular white-chocolate definition or calculate price per mass.",
    ),
    ev(
        "prop_lindt_milk_offer_scope",
        "frozen Lindt milk seller page",
        "shows_a_two_piece_mass_ambiguity",
        "SKU B01N3OYUMS at 9.58 dollars with no reviews shown is titled 4.4 ounces and two pieces while Product Dimensions reports 4.4 ounces",
        2,
        "product",
        "frozen_offer_with_ambiguous_total_mass_not_verified_formula_or_taste",
        [
            "Lindt Classic Recipe Milk Chocolate Bar -- 4.4 oz - 2 pc",
            "In stock SKU B01N3OYUMS Be the first to review this product $9.58",
            "Package Dimensions ‏ ‎ 9.49 x 3.62 x 1.14 inches; 4.4 Ounces",
        ],
        "The frozen Lindt milk page shows SKU B01N3OYUMS at 9.58 dollars with no reviews shown, titled 4.4 ounces and two pieces, while Product Dimensions reports 4.4 ounces. Conditional count arithmetic is 4.79 dollars per nominal piece, but total delivered mass, ingredients, cocoa components and tasting performance remain unresolved.",
    ),
    ev(
        "prop_ritter_sixty_one_offer_scope",
        "frozen Ritter Sport seller page",
        "shows_one_sixty_one_percent_bar_and_marketing",
        "SKU B07PRJC1KW at 7.99 dollars rated 55 percent over four reviews for one 100-gram or 3.52-ounce 61-percent bar with seller sustainability origin and flavor claims",
        3,
        "product",
        "frozen_offer_and_marketing_not_verified_process_quality_or_preference",
        [
            "Ritter Sport 61% Fine Dark Chocolate Bar Candy Original German Chocolate 100g/3.52oz",
            "In stock SKU B07PRJC1KW Rating: 55 % of 100 4 Reviews Add Your Review $7.99",
            "Experience the new dark with our tasty 61% Cocoa Selection bar.",
        ],
        "The frozen Ritter Sport page shows SKU B07PRJC1KW at 7.99 dollars, rated 55 percent over four reviews, for one 61-percent 100-gram or 3.52-ounce bar and makes seller origin, sustainability, freshness and flavor claims. The literal mass gives about 2.27 dollars per declared ounce, but neither percentage, aggregate rating nor copy proves exact composition, processing quality or guest preference.",
    ),
    ev(
        "prop_chocolove_ruby_offer_scope",
        "frozen Chocolove ruby seller page",
        "shows_a_two_bar_mass_ambiguity_and_ruby_claim",
        "SKU B07SQ4JSKK at 8.99 dollars rated 78 percent over twelve reviews is titled two bars and selected as a 3.1-ounce two-pack while Product Dimensions reports 3.1 ounces",
        4,
        "product",
        "frozen_offer_with_unresolved_total_mass_not_verified_ruby_formula_or_taste",
        [
            "Chocolove Ruby Cacao bar (2 BARS)",
            "In stock SKU B07SQ4JSKK Rating: 78 % of 100 12 Reviews Add Your Review $8.99 Size 3.1 Ounce (Pack of 12) 3.1 Ounce (Pack of 2) 4 BARS 6 BARS",
            "Chocolove Ruby Cacao bar 3.1 OZ From Ruby cacao beans",
            "Package Dimensions ‏ ‎ 5.94 x 4.33 x 1.1 inches; 3.1 Ounces",
        ],
        "The frozen Chocolove page shows SKU B07SQ4JSKK at 8.99 dollars, rated 78 percent over twelve reviews, titled two bars and selected as a 3.1-ounce two-pack while Product Dimensions reports 3.1 ounces. Conditional count arithmetic is about 4.50 dollars per nominal bar, but total mass, current formula and the seller's ruby-cacao assertion require independent verification.",
    ),
    ev(
        "prop_chocolate_process_chain_scope",
        "general chocolate overview",
        "describes_ferment_dry_roast_nib_and_liquor_stages",
        "beans are fermented dried cleaned roasted and shelled before nibs are ground into chocolate liquor that can be separated into solids and butter",
        5,
        "concept",
        "general_process_chain_not_exact_offer_history_or_quality_rank",
        [
            "Cocoa beans are the processed seeds of the cacao tree ( Theobroma cacao ). They are usually fermented to develop the flavor, then dried, cleaned, and roasted.",
            "The shell is removed to reveal nibs, which are ground to chocolate liquor (unadulterated chocolate in rough form.)",
            "The liquor can be processed to separate its two components, cocoa solids and cocoa butter , or shaped and sold as unsweetened baking chocolate .",
        ],
        "The chocolate overview says cocoa beans are usually fermented for flavor development, then dried, cleaned and roasted; shells are removed, nibs are ground into chocolate liquor, and liquor can be separated into cocoa solids and cocoa butter. This is a general pathway, not the verified fermentation, roast, ingredient split or quality history of any exact seller offer.",
    ),
    ev(
        "prop_cocoa_bean_nib_scope",
        "cocoa-bean page",
        "distinguishes_fermented_seed_nib_solids_and_butter",
        "the bean is a dried fully fermented seed yielding nonfat cocoa solids and cocoa butter and roasted nibs may be ground into liquor",
        6,
        "concept",
        "general_bean_material_context_not_exact_origin_process_or_flavor_proof",
        [
            "Roasted nibs (pieces of kernels) are generally powdered and melted into chocolate liquor , but also inserted into chocolate bars to give additional texture or \"crunch\".",
            "which cocoa solids (a mixture of nonfat substances) and cocoa butter (the fat) can be extracted.",
        ],
        "The cocoa-bean page describes roasted nibs being ground or melted into chocolate liquor and distinguishes extractable nonfat cocoa solids from cocoa butter fat. It supplies material context but does not verify an exact bean origin, fermentation, roast, solids-to-butter ratio or sensory result for the five offers.",
    ),
    ev(
        "prop_chocolate_liquor_composition_scope",
        "chocolate liquor",
        "defines_nonalcoholic_cocoa_mass_and_component_split",
        "fermented dried roasted skinned nibs are ground until butter release creates cocoa mass containing both solids and butter",
        7,
        "concept",
        "general_liquor_definition_not_exact_percentage_or_formula_proof",
        [
            "Chocolate liquor , also called cocoa liquor , paste or mass , is pure cocoa in liquid or semi-solid form.",
            "It is produced from cocoa bean nibs that have been fermented, dried, roasted, and separated from their skins.",
            "Like the nibs from which it is produced, it contains both cocoa solids and cocoa butter in roughly equal proportion.",
            "The name liquor is used not in the sense of a distilled, alcoholic substance, but rather the older meaning of the word, meaning 'liquid' or 'fluid'.",
        ],
        "The chocolate-liquor page defines cocoa liquor, paste or mass as nonalcoholic pure cocoa made from fermented, dried, roasted and skinned nibs and says it contains both cocoa solids and cocoa butter. This prevents confusing liquor with alcohol but does not disclose the exact component balance or percentage basis of any captured bar.",
    ),
    ev(
        "prop_cocoa_butter_material_scope",
        "cocoa butter",
        "defines_an_edible_cocoa_fat_with_near_body_temperature_melting",
        "a pale edible fat extracted from cocoa beans is essential to chocolate and melts slightly below body temperature",
        8,
        "concept",
        "general_material_property_not_exact_bar_formula_melt_or_quality_guarantee",
        [
            "Cocoa butter , also called theobroma oil , is a pale-yellow, edible fat extracted from the cocoa bean ( Theobroma  cacao ).",
            "Its melting point is slightly below human body temperature.",
            "It is an essential ingredient of chocolate and related confectionary products.",
        ],
        "The cocoa-butter page defines a pale edible fat extracted from cocoa beans, essential to chocolate, whose melting point is slightly below body temperature. These general properties help explain melt and mouthfeel but do not establish an exact bar's cocoa-butter share, substitutes, temper, storage history or quality.",
    ),
    ev(
        "prop_conching_process_scope",
        "conching",
        "mixes_coats_and_changes_texture_and_flavor_under_equipment_dependent_conditions",
        "agitation distributes cocoa butter and promotes flavor changes while duration depends on batch and equipment",
        9,
        "concept",
        "general_process_mechanism_not_longer_is_better_or_exact_brand_history",
        [
            "Conching is a process used in the manufacture of chocolate whereby a surface scraping mixer and agitator, known as a conche , evenly distributes cocoa butter within chocolate and may act as a \"polisher\" of the particles .",
            "It also promotes flavor development through frictional heat, release of volatiles and acids, and oxidation.",
            "The duration of conching is highly dependent on batch size and the type of equipment used; modern industrial conching of multi-tonne batches can be completed in under 12 hours, whereas traditional methods for large batches may take several days.",
        ],
        "The conching page says mixing distributes cocoa butter, can polish particles and promotes flavor development through heat, volatile and acid release and oxidation. Duration depends on batch size and equipment, so longer is not automatically better, and no seller page verifies an exact conching time or causal taste effect.",
    ),
    ev(
        "prop_white_chocolate_category_scope",
        "white chocolate",
        "uses_cocoa_butter_sugar_and_milk_without_nonfat_cocoa_solids",
        "an ivory traditional chocolate type lacks nonfat cocoa solids while consumer opinions and market standards differ",
        10,
        "concept",
        "general_category_and_market_boundary_not_exact_lindt_classification_or_preference",
        [
            "White chocolate is chocolate made from cocoa butter , sugar and milk solids .",
            "It is ivory in color and lacks the dark appearance of most other types of chocolate because it does not contain the non-fat components of cocoa ( cocoa solids ).",
            "Due to this omission, as well as its sweetness and the occasional use of additives, some consumers do not consider white chocolate to be real chocolate.",
        ],
        "The white-chocolate page describes cocoa butter, sugar and milk solids without nonfat cocoa solids and notes that some consumers dispute whether it is real chocolate. It is still treated as a traditional chocolate type, while composition rules vary by market. The page cannot independently classify the exact Lindt offer without its current label and market.",
    ),
    ev(
        "prop_ruby_chocolate_category_scope",
        "ruby chocolate",
        "presents_a_distinct_style_with_a_disputed_fourth_type_claim",
        "a pink or purple product was introduced as distinct while experts debate whether the fourth natural type claim is technical or marketing",
        11,
        "concept",
        "general_disputed_category_not_exact_chocolove_formula_or_naturalness_proof",
        [
            "Ruby chocolate is a style or distinct variety of chocolate that is pink or purple in color.",
            "While Barry Callebaut says it is a fourth natural type of chocolate (in addition to dark , milk , and white chocolate varieties), [ 5 ] [ 6 ] industry experts have debated whether this is true or a marketing claim.",
        ],
        "The ruby-chocolate page describes a pink or purple style introduced as distinct and says experts debate whether the fourth natural type claim is true or marketing. This supports a disputed-category explanation, not verification of the Chocolove bar's formula, processing, color source, legal identity or sensory quality.",
    ),
    ev(
        "prop_nj_blind_test_anecdote_scope",
        "New Jersey chocolate-shop post",
        "reports_a_planned_local_blind_caramel_comparison",
        "one author planned a blind taste test of milk-chocolate-covered caramels from eight local shops but reported no result in the frozen page",
        12,
        "community",
        "planned_local_test_not_result_or_method_validation_for_exact_bars",
        [
            "My husband, our friend, and I are doing a blind taste test for milk chocolate covered caramels this weekend to see which one is the best.",
            "We’re getting chocolate from 8 different shops in Monmouth/Ocean County.",
        ],
        "One New Jersey author planned a blind test of milk-chocolate-covered caramels from eight local shops, but the frozen page reports recommendations rather than the test result. It motivates masking and local comparison while providing no result, protocol validation or evidence about the five exact bar offers.",
    ),
    ev(
        "prop_new_haven_cocoa_preference_scope",
        "New Haven hot-cocoa post",
        "contains_place_specific_preferences_and_a_condition_caveat",
        "authors recommend local drinks and one explicitly cannot separate cold-weather satisfaction from product quality",
        13,
        "community",
        "local_drink_preferences_not_bar_category_or_quality_evidence",
        [
            "Are there any coffee shops, bakeries, etc, that have some slammin’ hot cocoa that is better than the corporate sludge I currently pump?",
            "Not sure if it was crazy satisfying because it was cold or because it was just that good.",
        ],
        "The New Haven discussion contains place- and time-specific hot-cocoa preferences, and one commenter explicitly cannot separate cold-weather satisfaction from drink quality. It motivates controlling serving conditions but is not evidence about bar composition, the exact five offers or a universal quality ranking.",
    ),
    ev(
        "prop_eli5_flavor_cue_scope",
        "ELI5 flavor discussion",
        "identifies_smell_texture_temperature_and_expectation_as_possible_cues",
        "lay commenters distinguish basic taste from aroma mouthfeel temperature and visual or expectation effects",
        14,
        "community",
        "lay_mechanism_discussion_not_authoritative_protocol_or_exact_product_result",
        [
            "That's because our sense of taste is really closely tied to our sense of smell as well.",
            "Except then there are also things like temperature and texture/mouth feel that affect it too.",
            "Add to this that the brain changes the \"flavor\" of food based on what it thinks the food is.",
        ],
        "An ELI5 discussion says smell, texture, mouthfeel, temperature and expectation can contribute to perceived flavor. As a lay forum discussion it can suggest variables to standardize and cues to mask, but it is not an authoritative sensory protocol and contains no observation of the five exact offers.",
    ),
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
            "registry_id": "reg_case_spec_chocolate_sampler_0049",
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
        (
            "bridge_seller_sampler_offer_scope",
            "bridge",
            "five frozen seller offers",
            "retains_exact_offer_and_conflict_scope",
            "audit literal seller fields while preserving all pack and mass conflicts and the lack of current labels ingredients allergens or taste results",
            "seller_sampler_offer_scope_v1",
        ),
        (
            "bridge_pack_mass_cost_normalization",
            "bridge",
            "pack count mass and sticker price fields",
            "permits_only_conditional_transparent_arithmetic",
            "show price per nominal bar or declared mass only with explicit assumptions and without ranking unlike categories",
            "pack_mass_cost_normalization_boundary_v1",
        ),
        (
            "bridge_bean_to_liquor_process",
            "bridge",
            "bean nib liquor solids and butter evidence",
            "explains_a_general_processing_chain",
            "connect ferment dry roast shell nib grind liquor solids and butter without assigning an exact process history or quality rank",
            "bean_to_liquor_process_boundary_v1",
        ),
        (
            "bridge_conching_texture_flavor",
            "bridge",
            "conching evidence",
            "separates_process_mechanism_from_longer_is_better_claims",
            "explain particle coating volatile acid moisture texture and flavor changes while preserving equipment batch time and exact-offer unknowns",
            "conching_texture_flavor_boundary_v1",
        ),
        (
            "bridge_white_ruby_category",
            "bridge",
            "white and ruby category evidence",
            "rejects_universal_fake_or_verified_fourth_type_shortcuts",
            "retain cocoa-component market definition consumer-dispute and exact-label boundaries for white and ruby products",
            "white_ruby_category_boundary_v1",
        ),
        (
            "bridge_percentage_component_quality",
            "bridge",
            "percentage component and recipe evidence",
            "prevents_a_homogeneous_quality_ladder",
            "record percentage literally while refusing direct bitterness sweetness processing value or preference rankings across unlike forms",
            "percentage_component_quality_boundary_v1",
        ),
        (
            "bridge_community_tasting_variable_scope",
            "bridge",
            "three community discussions",
            "extracts_only_scoped_tasting_variables",
            "use masking serving-condition aroma texture and local-preference clues without converting anecdotes into exact-offer results",
            "community_tasting_variable_scope_v1",
        ),
        (
            "bridge_category_aware_tasting_protocol",
            "bridge",
            "small host tasting",
            "separates_category_exploration_from_like_for_like_comparison",
            "verify labels and guests then mask randomize balance and standardize comparable portions while recording distinct sensory and liking outcomes",
            "category_aware_tasting_protocol_v1",
        ),
        (
            "bridge_sampler_decision_preparation",
            "bridge",
            "verified sampler matrix and local outcomes",
            "combines_identity_safety_budget_category_and_acceptance_gates",
            "prefer the least expensive verified configuration meeting declared educational coverage without redundant bulk or unresolved risk",
            "sampler_decision_preparation_v1",
        ),
        (
            "decision_evidence_bounded_sampler",
            "decision",
            "affordable chocolate tasting lineup",
            "selects_the_lowest_commitment_passing_lineup_or_control_reduce_or_defer",
            "choose the lowest-commitment exact lineup passing identity allergen budget category coverage and local acceptance gates otherwise use a verified control reduce the lineup or defer without a universal winner",
            "evidence_bounded_sampler_decision_v1",
        ),
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
        "prop_green_black_variety_offer_scope",
        "prop_lindt_white_offer_scope",
        "prop_lindt_milk_offer_scope",
        "prop_ritter_sixty_one_offer_scope",
        "prop_chocolove_ruby_offer_scope",
    ]
    derives = {
        "bridge_seller_sampler_offer_scope": products,
        "bridge_pack_mass_cost_normalization": products,
        "bridge_bean_to_liquor_process": [
            "prop_chocolate_process_chain_scope",
            "prop_cocoa_bean_nib_scope",
            "prop_chocolate_liquor_composition_scope",
        ],
        "bridge_conching_texture_flavor": [
            "prop_chocolate_process_chain_scope",
            "prop_conching_process_scope",
        ],
        "bridge_white_ruby_category": [
            "prop_lindt_white_offer_scope",
            "prop_chocolove_ruby_offer_scope",
            "prop_chocolate_liquor_composition_scope",
            "prop_cocoa_butter_material_scope",
            "prop_white_chocolate_category_scope",
            "prop_ruby_chocolate_category_scope",
        ],
        "bridge_percentage_component_quality": products
        + [
            "prop_chocolate_liquor_composition_scope",
            "prop_cocoa_butter_material_scope",
            "prop_white_chocolate_category_scope",
            "prop_ruby_chocolate_category_scope",
        ],
        "bridge_community_tasting_variable_scope": [
            "prop_nj_blind_test_anecdote_scope",
            "prop_new_haven_cocoa_preference_scope",
            "prop_eli5_flavor_cue_scope",
        ],
        "bridge_category_aware_tasting_protocol": products
        + [
            "prop_nj_blind_test_anecdote_scope",
            "prop_new_haven_cocoa_preference_scope",
            "prop_eli5_flavor_cue_scope",
            "bridge_white_ruby_category",
            "bridge_percentage_component_quality",
        ],
        "bridge_sampler_decision_preparation": [
            "bridge_seller_sampler_offer_scope",
            "bridge_pack_mass_cost_normalization",
            "bridge_bean_to_liquor_process",
            "bridge_conching_texture_flavor",
            "bridge_white_ruby_category",
            "bridge_percentage_component_quality",
            "bridge_community_tasting_variable_scope",
            "bridge_category_aware_tasting_protocol",
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
                "source_id": "decision_evidence_bounded_sampler",
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
