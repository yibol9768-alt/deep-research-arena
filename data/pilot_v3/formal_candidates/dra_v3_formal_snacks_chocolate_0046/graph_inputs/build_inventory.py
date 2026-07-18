#!/usr/bin/env python3
"""Build the frozen Q46 rating, recipe, and shrinkflation-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-snacks-chocolate-0046-rating-recipe-shrinkflation-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0046/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = (
    "dra-v3-formal-snacks-chocolate-0046-rating-recipe-"
    "shrinkflation-boundary-20260716-r1"
)
RUN_ID = (
    "v3-corpus-formal-snacks-chocolate-0046-rating-recipe-"
    "shrinkflation-boundary-20260716-r1"
)
TASK_ID = "dra_v3_formal_snacks_chocolate_0046"
TOPIC = "office_candy_rating_recipe_and_shrinkflation_boundary"


SEARCHES = [
    (
        "kinder_bueno",
        "001-shopping-kinder-bueno-five-pack.json",
        "Kinder Bueno five-pack seller snapshot",
        "http://localhost:7770/pack-of-5-kinder-bueno-crispy-creamy-chocolate-bar-crispy-wafer-with-creamy-nut-filling-in-milk-chocolate-2-bars-per-pack-1-5oz-totoal-5-packs-7-5oz.html",
    ),
    (
        "hershey_personalized",
        "002-shopping-hershey-personalized-twelve-bars.json",
        "Hershey personalized twelve-bar seller snapshot",
        "http://localhost:7770/hershey-s-personalized-milk-chocolate-bars-classic-hershey-bars-pastel-spring-colors-prime-idea-for-mothers-day-gift-1-55-ounce-pack-of-12.html",
    ),
    (
        "godiva_mini_bars",
        "003-shopping-godiva-signature-mini-bars.json",
        "Godiva-branded Candy Cabin mini-bar set seller snapshot",
        "http://localhost:7770/godiva-chocolatier-signature-mini-bars-set-of-6-8pc-each-variety-pack-roasted-almond-dark-chocolate-72-cacao-dark-salted-caramel-milk-chocolate-by-candy-cabin.html",
    ),
    (
        "goldenberg_peanut_chews",
        "004-shopping-goldenberg-dark-peanut-chews.json",
        "Goldenberg peanut-chew bulk seller snapshot",
        "http://localhost:7770/goldenberg-s-dark-chocolate-peanut-chews-2-lbs-of-fresh-delicious-assorted-bulk-mini-bars-of-candy-with-refrigerator-magnet.html",
    ),
    (
        "types_chocolate",
        "005-wiki-types-of-chocolate-standards.json",
        "chocolate type and jurisdiction boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Types_of_chocolate",
    ),
    (
        "couverture",
        "006-wiki-couverture-definition.json",
        "couverture definition and jurisdiction boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Couverture_chocolate",
    ),
    (
        "unit_price",
        "007-wiki-unit-price-comparable-units.json",
        "comparable-unit price boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Unit_price",
    ),
    (
        "food_labeling",
        "008-wiki-food-labeling-regulations.json",
        "food-label regulation and field boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/List_of_food_labeling_regulations",
    ),
    (
        "bifl_quality_decline",
        "009-forum-bifl-quality-decline.json",
        "BuyItForLife manufacturing-change anecdote",
        "http://localhost:9999/f/BuyItForLife/118455/bifl-products-that-are-at-their-peak-right-now",
    ),
    (
        "rating_disagreement",
        "010-forum-high-rating-personal-disagreement.json",
        "popular-rating disagreement anecdote",
        "http://localhost:9999/f/books/103302/what-popular-books-have-you-rated-one-or-two-stars",
    ),
    (
        "snack_temperature",
        "011-forum-snack-temperature-confound.json",
        "snack serving-temperature anecdote",
        "http://localhost:9999/f/LifeProTips/120115/lpt-fridge-your-chips-snacks-for-a-more-satisfying",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_kinder_offer_rating_scope",
        "subject": "frozen Kinder Bueno seller page",
        "predicate": "shows_a_high_displayed_rating_and_five_pack_offer",
        "object": "a 9.99-dollar SKU rated 98 percent over eight reviews and described as five 1.5-ounce packs with two wrapped bars per pack",
        "source_url": SEARCHES[0][3],
        "search_id": "kinder_bueno",
        "role": "product",
        "scope": "current_seller_offer_copy_not_ingredient_formula_history_shrinkflation_or_office_preference",
        "quotes": [
            "In stock SKU B08ZHJY8NY Rating: 98 % of 100 8 Reviews Add Your Review $9.99 Qty Add to Cart Add to Wish List Add to Compare",
            "✔️ Great Value Pack: Total 5 (1.5oz) packs.",
            "✔️Each pack contains TWO individually wrapped Kinder bars.",
        ],
        "accepted": "The frozen Kinder Bueno page shows SKU B08ZHJY8NY at 9.99 dollars, rated 98 percent over eight reviews, and describes five 1.5-ounce packs with two individually wrapped bars per pack; it does not provide a complete current ingredient panel, manufacturer-confirmed formula version, dated historical package pair, shrinkflation comparison, current delivered cost, or office preference result.",
    },
    {
        "evidence_id": "prop_hershey_offer_rating_scope",
        "subject": "frozen personalized Hershey seller page",
        "predicate": "shows_a_perfect_displayed_rating_over_two_reviews_and_twelve_bars",
        "object": "a 22-dollar SKU rated 100 percent over two reviews and described as twelve individually wrapped 1.55-ounce milk-chocolate bars",
        "source_url": SEARCHES[1][3],
        "search_id": "hershey_personalized",
        "role": "product",
        "scope": "current_seller_offer_copy_not_ingredient_formula_history_shrinkflation_or_office_preference",
        "quotes": [
            "In stock SKU B084Q44G26 Rating: 100 % of 100 2 Reviews Add Your Review $22.00 Qty Add to Cart Add to Wish List Add to Compare",
            "Each chocolate bar is individually wrapped and ideal for sharing.",
            "Each bar is 1.55 ounces. 12 Bars in total",
        ],
        "accepted": "The frozen Hershey page shows SKU B084Q44G26 at 22.00 dollars, rated 100 percent over two reviews, and describes twelve individually wrapped 1.55-ounce milk-chocolate bars; the page does not establish a complete current ingredient panel, a manufacturer-confirmed recipe history, a dated old-versus-new net-weight pair, current delivered cost, or office acceptance.",
    },
    {
        "evidence_id": "prop_godiva_candy_cabin_offer_scope",
        "subject": "frozen Godiva-branded Candy Cabin seller page",
        "predicate": "shows_a_perfect_one_review_rating_and_ambiguous_mini_bar_set",
        "object": "a 36.95-dollar SKU rated 100 percent over one review with six cartons of eight minis across three flavors and a Candy Cabin manufacturer field",
        "source_url": SEARCHES[2][3],
        "search_id": "godiva_mini_bars",
        "role": "product",
        "scope": "current_seller_offer_and_packer_copy_with_mass_ambiguity_not_official_formula_history_or_office_preference",
        "quotes": [
            "In stock SKU B08SFJWJK2 Rating: 100 % of 100 1 Review Add Your Review $36.95 Qty Add to Cart Add to Wish List Add to Compare",
            "Contains 2 Bars of Each Flavor: Roasted Almond Dark, 72% Cacao Dark, Salted Caramel Milk",
            "Manufacturer ‏ ‎ CANDY CABIN",
        ],
        "accepted": "The frozen Godiva-branded Candy Cabin page shows SKU B08SFJWJK2 at 36.95 dollars, rated 100 percent over one review, and describes a six-carton, eight-mini-per-carton variety across roasted-almond dark, 72-percent cacao dark and salted-caramel milk flavors while listing Candy Cabin as manufacturer; its 3.1-ounce wording and exact brand-packer relationship remain ambiguous and it does not prove current ingredients, formula history, shrinkage or office preference.",
    },
    {
        "evidence_id": "prop_goldenberg_offer_reputation_scope",
        "subject": "frozen Goldenberg peanut-chew seller page",
        "predicate": "shows_the_largest_review_count_and_an_unverified_continuity_claim",
        "object": "a 14.99-dollar two-pound SKU rated 95 percent over twelve reviews whose seller repeats same-quality-and-taste wording and an Emporium Candy repacking warning",
        "source_url": SEARCHES[3][3],
        "search_id": "goldenberg_peanut_chews",
        "role": "product",
        "scope": "current_seller_offer_repacker_and_reputation_copy_not_dated_formula_or_taste_continuity",
        "quotes": [
            "In stock SKU B07YST76HH Rating: 95 % of 100 12 Reviews Add Your Review $14.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Buy in bulk to get more bang for your buck! - The same quality and taste you have always known.",
            "Items are repackaged in a facility that may contain milk, soy, peanuts, tree nuts, eggs, wheat and all other allergens.",
        ],
        "accepted": "The frozen Goldenberg page shows SKU B07YST76HH at 14.99 dollars, rated 95 percent over twelve reviews, and describes two pounds of mini peanut chews repackaged in a broad-allergen facility; its claim of the same quality and taste always known is seller copy without a dated ingredient, weight or sensory baseline and cannot prove recipe continuity, lack of shrinkflation, office safety or preference.",
    },
    {
        "evidence_id": "prop_chocolate_type_jurisdiction_scope",
        "subject": "chocolate types and fat-substitution rules",
        "predicate": "distinguishes_compound_chocolate_and_market_specific_rules",
        "object": "compound chocolate replaces cocoa butter with other vegetable fats while Canada and the EU are described with different naming and permitted-fat rules",
        "source_url": SEARCHES[4][3],
        "search_id": "types_chocolate",
        "role": "concept",
        "scope": "general_frozen_jurisdiction_summary_not_current_legal_advice_or_exact_sku_classification",
        "quotes": [
            "Compound chocolate is the name for a confection combining cocoa with other vegetable fats , usually tropical fats or hydrogenated fats, as a replacement for cocoa butter.",
            "The use of cocoa butter substitutes in Canada is not permitted.",
            "In 1999, however, the EU resolved the fat issue by allowing up to 5% of chocolate's content to be one of six alternatives to cocoa butter: illipe oil, palm oil , sal, shea butter , kokum gurgi , or mango kernel oil.",
        ],
        "accepted": "The frozen types page describes compound chocolate as cocoa combined with other vegetable fats in place of cocoa butter, says Canada does not permit cocoa-butter substitutes in products sold as chocolate, and describes the EU as allowing up to five percent of six named alternative fats; these are jurisdiction-scoped general statements, not current legal advice, an exact SKU classification, or proof that any captured product changed its fat source.",
    },
    {
        "evidence_id": "prop_couverture_jurisdiction_scope",
        "subject": "couverture composition and terminology",
        "predicate": "is_a_distinct_cocoa_butter_rich_term_with_different_regulatory_scope",
        "object": "couverture is described as cocoa-butter-rich, distinct from compound chocolate, EU-regulated and not US-regulated as a term",
        "source_url": SEARCHES[5][3],
        "search_id": "couverture",
        "role": "concept",
        "scope": "general_frozen_term_boundary_not_exact_product_recipe_quality_or_current_legal_advice",
        "quotes": [
            "This additional cocoa butter, combined with proper tempering , gives the chocolate more sheen, a firmer \"snap\" when broken, and a creamy mellow flavor.",
            "It is legally regulated in the EU.",
            "It is not a regulated term in the US.",
            "The term \"couverture chocolate\" is distinct from compound chocolate .",
        ],
        "accepted": "The frozen couverture page describes additional cocoa butter, states that the term is legally regulated in the EU but not in the US, and distinguishes couverture from compound chocolate; it does not prove that any captured offer is couverture or compound, identify its current fat source, establish a recipe change, or rank office taste.",
    },
    {
        "evidence_id": "prop_unit_price_comparable_scope",
        "subject": "unit-price comparison across packages",
        "predicate": "requires_comparable_units_across_sizes_forms_and_configurations",
        "object": "price per common weight or volume supports package comparison only after variants and product forms are normalized",
        "source_url": SEARCHES[6][3],
        "search_id": "unit_price",
        "role": "concept",
        "scope": "general_comparison_method_not_historical_price_or_shrinkflation_proof",
        "quotes": [
            "When one product is sold in variants, such as bottle sizes, managers must define \"comparable\" units.",
            "Average price per unit and prices per statistical unit are needed by marketers who sell the same product in different packages, sizes, forms, or configurations at a variety of different prices.",
            "The \"unit price\" tells the buyer the cost per pound, quart, or other unit of weight or volume of a food package.",
        ],
        "accepted": "The unit-price page says variants need comparable units, that package size, form and configuration differences must be reflected, and that food unit price can be expressed per common weight or volume; it supplies a comparison method but no historical price, matched old package, exact current delivered total or shrinkflation proof for the four offers.",
    },
    {
        "evidence_id": "prop_food_labeling_field_scope",
        "subject": "food-label regulation and identity fields",
        "predicate": "varies_by_jurisdiction_and_includes_identity_ingredient_and_quantity_context",
        "object": "food labels are generally regulated by jurisdiction and may require clear product names, ingredient listings, manufacturer identity and net quantity",
        "source_url": SEARCHES[7][3],
        "search_id": "food_labeling",
        "role": "concept",
        "scope": "general_regulatory_and_field_context_not_exact_current_label_or_recipe_history",
        "quotes": [
            "The packaging and labeling of food is subject to regulation in most regions/jurisdictions, to prevent false advertising and to promote food safety , and increasingly to provide greater information to consumers relating to quality or lifestyle concerns.",
            "In many countries, early food laws focused on preventing adulteration and fraud , often by mandating clear product names and ingredient listings.",
            "Fair Packaging and Labeling Act (US) â enacted in 1966, requiring product identity, manufacturer, and net quantity labeling.",
        ],
        "accepted": "The labeling page says food packaging and labeling are regulated in most jurisdictions, describes clear product names and ingredient listings as recurring controls, and lists product identity, manufacturer and net quantity for a US packaging law; this is general field context, not the physical current label, applicable law, formula version or historical change record for any exact offer.",
    },
    {
        "evidence_id": "prop_bifl_quality_decline_anecdote_scope",
        "subject": "BuyItForLife quality-decline discussion",
        "predicate": "reports_unrelated_products_and_manufacturing_change_concerns",
        "object": "one author describes non-chocolate examples of ownership or manufacturing changes followed by lower perceived quality",
        "source_url": SEARCHES[8][3],
        "search_id": "bifl_quality_decline",
        "role": "community",
        "scope": "author_category_product_and_time_specific_anecdote_not_chocolate_formula_history",
        "quotes": [
            "Company has been bought out and manufacturing methods have changed for the worse Quality is lowered, cost has increased",
            "A brand/pillow that sounded perfect for me (Dunlopilo) went into administration, has been bought out by Relyon and old customers of Dunlopilo are reporting that the quality and comfort is no longer the same.",
        ],
        "accepted": "The BuyItForLife author reports non-chocolate examples in which ownership or manufacturing allegedly changed and users perceived lower quality; this motivates version and date checks but cannot transfer to Kinder, Hershey, Godiva or Goldenberg, establish a formula change, prove shrinkflation, or measure office preference.",
    },
    {
        "evidence_id": "prop_rating_disagreement_anecdote_scope",
        "subject": "popular-rating disagreement discussion",
        "predicate": "shows_one_person_disagreeing_with_high_averages_in_another_domain",
        "object": "a books author reports rating popular high-average works one or two stars",
        "source_url": SEARCHES[9][3],
        "search_id": "rating_disagreement",
        "role": "community",
        "scope": "single_author_cross_domain_preference_not_product_rating_validity_or_office_taste",
        "quotes": [
            "i always feel like i’m reading a completely different book when i give a normally highly rated book two stars… or maybe some people are too nice.",
            "what book with an average rating of 4 or more have you rated one or two stars?",
        ],
        "accepted": "One books author reports personally rating popular works with high averages much lower; this illustrates possible individual-versus-aggregate disagreement in another domain but says nothing about the provenance, representativeness or validity of the four seller ratings and does not predict office chocolate preference.",
    },
    {
        "evidence_id": "prop_snack_temperature_anecdote_scope",
        "subject": "snack serving-temperature discussion",
        "predicate": "reports_a_temperature_linked_taste_difference",
        "object": "one construction worker prefers chilled chips and invites readers to test a favorite brand after refrigeration",
        "source_url": SEARCHES[10][3],
        "search_id": "snack_temperature",
        "role": "community",
        "scope": "author_snack_brand_temperature_and_time_specific_anecdote_not_chocolate_trial_result",
        "quotes": [
            "Anytime I eat it after it's freshly cold it just hits different.",
            "Test it for yourself! Pick your favorite brand chips, (Mine is Doritos) and fridge a zip lock bag full of em.",
            "8/10 - would recommend",
        ],
        "accepted": "The snack thread contains one author's preference for freshly chilled chips, an invitation to test a favorite brand after refrigeration, and one 8-out-of-10 reply; it motivates matching serving temperature but does not establish a universal temperature effect, a chocolate result, recipe continuity, shrinkflation or office preference.",
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
            "registry_id": "reg_case_spec_rating_recipe_shrinkflation_0046",
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
            "bridge_exact_offer_rating_sample_matrix",
            "bridge",
            "four exact seller snapshots",
            "retains_offer_fields_rating_denominators_and_identity_ambiguities",
            "record each SKU price displayed rating review count pack count stated mass product form manufacturer or repacker field and missing ingredients history and delivered cost without treating small-sample percentages as equal confidence",
            "exact_offer_rating_sample_matrix_v1",
        ),
        (
            "bridge_chocolate_label_fat_jurisdiction",
            "bridge",
            "chocolate naming fat and label evidence",
            "separates_general_jurisdiction_rules_from_exact_sku_classification",
            "retain compound couverture cocoa-butter alternative product-identity ingredient and net-quantity concepts by applicable market while requiring a current physical exact label and current primary rule before classification",
            "chocolate_label_and_fat_substitution_boundary_v1",
        ),
        (
            "bridge_recipe_weight_change_pairing",
            "bridge",
            "recipe and package-change allegation",
            "requires_dated_matched_before_after_evidence",
            "require the same SKU or documented version mapping in the same market with dated complete ingredients net quantity pack count total paid and comparable-unit calculations before any formula-change quality-downgrade or shrinkflation conclusion",
            "recipe_weight_change_pairing_requirement_v1",
        ),
        (
            "bridge_scoped_rating_reputation_temperature",
            "bridge",
            "ratings reputation and taste anecdotes",
            "retains_author_category_product_time_and_condition_scope",
            "use non-chocolate quality-decline and rating-disagreement reports plus a snack-temperature report only to motivate checks and controls without transferring them to any exact chocolate offer",
            "scoped_rating_reputation_temperature_transfer_v1",
        ),
        (
            "bridge_current_historical_verification_gate",
            "bridge",
            "current exact package and any historical counterpart",
            "blocks_unresolved_identity_ingredient_weight_history_and_market_cells",
            "verify physical identity manufacturer or repacker current ingredients allergens category wording market lot net quantity pack count delivered cost and dated mapped historical records while calculating comparable units only after ambiguity resolution",
            "current_and_historical_verification_gate_v1",
        ),
        (
            "bridge_reversible_office_candy_trial",
            "bridge",
            "small office candy comparison",
            "measures_local_fit_under_matched_conditions",
            "after safety and current-label gates pass use small quantities equal coded portions matched temperature randomized or counterbalanced order an accepted control and predeclared acceptance consumption repeat-choice and waste thresholds",
            "reversible_office_candy_trial_v1",
        ),
        (
            "decision_evidence_bounded_office_candy_stocking",
            "decision",
            "office candy drawer restocking",
            "selects_only_the_lowest_cost_exact_offer_clearing_all_gates_or_deferral",
            "reject automatic highest-rating and folklore verdicts and choose only the lowest total-cost exact offer passing current identity ingredient allergen dietary budget and local-trial gates otherwise use an accepted control or defer",
            "evidence_bounded_office_candy_stocking_v1",
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
        "bridge_exact_offer_rating_sample_matrix": [
            "prop_kinder_offer_rating_scope",
            "prop_hershey_offer_rating_scope",
            "prop_godiva_candy_cabin_offer_scope",
            "prop_goldenberg_offer_reputation_scope",
        ],
        "bridge_chocolate_label_fat_jurisdiction": [
            "prop_chocolate_type_jurisdiction_scope",
            "prop_couverture_jurisdiction_scope",
            "prop_food_labeling_field_scope",
            "prop_kinder_offer_rating_scope",
            "prop_hershey_offer_rating_scope",
            "prop_godiva_candy_cabin_offer_scope",
            "prop_goldenberg_offer_reputation_scope",
        ],
        "bridge_recipe_weight_change_pairing": [
            "prop_kinder_offer_rating_scope",
            "prop_hershey_offer_rating_scope",
            "prop_godiva_candy_cabin_offer_scope",
            "prop_goldenberg_offer_reputation_scope",
            "prop_unit_price_comparable_scope",
            "prop_bifl_quality_decline_anecdote_scope",
        ],
        "bridge_scoped_rating_reputation_temperature": [
            "prop_kinder_offer_rating_scope",
            "prop_hershey_offer_rating_scope",
            "prop_godiva_candy_cabin_offer_scope",
            "prop_goldenberg_offer_reputation_scope",
            "prop_bifl_quality_decline_anecdote_scope",
            "prop_rating_disagreement_anecdote_scope",
            "prop_snack_temperature_anecdote_scope",
        ],
        "bridge_current_historical_verification_gate": [
            "bridge_exact_offer_rating_sample_matrix",
            "bridge_chocolate_label_fat_jurisdiction",
            "bridge_recipe_weight_change_pairing",
            "prop_food_labeling_field_scope",
            "prop_unit_price_comparable_scope",
        ],
        "bridge_reversible_office_candy_trial": [
            "bridge_exact_offer_rating_sample_matrix",
            "bridge_scoped_rating_reputation_temperature",
            "bridge_current_historical_verification_gate",
            "prop_snack_temperature_anecdote_scope",
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
                "source_id": "decision_evidence_bounded_office_candy_stocking",
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
