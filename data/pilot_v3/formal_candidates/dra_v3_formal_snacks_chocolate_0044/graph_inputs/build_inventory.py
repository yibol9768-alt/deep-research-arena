#!/usr/bin/env python3
"""Build the frozen Q44 dark-chocolate gift-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-snacks-chocolate-0044-origin-percentage-gift-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0044/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-snacks-chocolate-0044-origin-percentage-gift-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-snacks-chocolate-0044-origin-percentage-gift-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_snacks_chocolate_0044"
TOPIC = "dark_chocolate_origin_percentage_gift_boundary"


SEARCHES = [
    (
        "valrhona_manjari",
        "001-shopping-valrhona-manjari-madagascar.json",
        "Valrhona Manjari percentage and origin seller snapshot",
        "http://localhost:7770/valrhona-dark-chocolate-manjari-65-cacao-baking-bars-gourmet-french-chocolate-tangy-and-fruity-notes-single-origin-madagascar-premium-couverture-the-perfect-baking-bar-70g-pack-of-1.html",
    ),
    (
        "quma_quinoa",
        "002-shopping-quma-quinoa-peru.json",
        "Quma Peru quinoa dark-bar seller snapshot",
        "http://localhost:7770/quma-quinoa-70-cacao-dark-chocolate-organic-bean-to-bar-born-and-made-in-peru-fair-trade.html",
    ),
    (
        "pump_street_dark_milk",
        "003-shopping-pump-street-ecuador-dark-milk.json",
        "Pump Street Ecuador dark-milk seller snapshot",
        "http://localhost:7770/pump-street-chocolate-ecuador-dark-milk-60.html",
    ),
    (
        "lindt_assorted_truffles",
        "004-shopping-lindt-holiday-assorted-truffles.json",
        "Lindt assorted truffle gift-box seller snapshot",
        "http://localhost:7770/lindt-lindor-holiday-deluxe-assorted-chocolate-truffles-gift-box-15-2-oz-2021.html",
    ),
    (
        "cravings_assorted_truffles",
        "005-shopping-cravings-zoe-sixteen-truffles.json",
        "Cravings by Zoe assorted truffle-box seller snapshot",
        "http://localhost:7770/cravings-by-zoe-valentine-s-day-chocolate-truffles-assorted-chocolate-gift-box-red-gourmet-chocolate-delicious-milk-chocolate-dark-chocolate-and-white-chocolate-flavors-with-16-assorted-toppings-7-5-oz-16-count.html",
    ),
    (
        "dark_chocolate",
        "006-wiki-dark-chocolate-percentage.json",
        "dark-chocolate percentage and composition boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Dark_chocolate",
    ),
    (
        "flavor_cocoa",
        "007-wiki-flavor-cocoa-origin.json",
        "flavor-cocoa origin and assessment boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Flavor_cocoa",
    ),
    (
        "cocoa_fermentation",
        "008-wiki-cocoa-fermentation-flavor.json",
        "cocoa-fermentation flavor mechanism",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Cocoa_bean_fermentation",
    ),
    (
        "cocoa_varieties",
        "009-wiki-cocoa-variety-marketing.json",
        "traditional cocoa-variety marketing boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Types_of_cocoa_beans",
    ),
    (
        "chocolate_truffle",
        "010-wiki-chocolate-truffle-definition.json",
        "chocolate-truffle structure and variety boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Chocolate_truffle",
    ),
    (
        "jersey_city_gifts",
        "011-forum-jersey-city-birthday-chocolate-gifts.json",
        "Jersey City birthday chocolate-gift discussion",
        "http://localhost:9999/f/jerseycity/20726/chocolate-gifts",
    ),
    (
        "pennsylvania_flavor_box",
        "012-forum-pennsylvania-custom-flavor-box.json",
        "Pennsylvania flavor-variety box discussion",
        "http://localhost:9999/f/Pennsylvania/79206/please-help-looking-for-a-chocolate-company-that-used-to-set",
    ),
    (
        "lpt_price_taste",
        "013-forum-lpt-price-taste-format.json",
        "LifeProTips chocolate price and taste discussion",
        "http://localhost:9999/f/LifeProTips/99418/lpt-chocolate-chips-are-candy",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_valrhona_manjari_label_scope",
        "subject": "frozen Valrhona Manjari seller page",
        "predicate": "shows_conflicting_percentage_labels_and_origin_flavor_copy",
        "object": "a 7.89-dollar 70-gram offer rated 100 percent over two reviews whose title and quick look say 65 percent and single-origin Madagascar while the same page also lists Manjari as 64 percent",
        "source_url": SEARCHES[0][3],
        "search_id": "valrhona_manjari",
        "role": "product",
        "scope": "seller_offer_and_internal_64_65_conflict_not_independent_composition_origin_or_taste_result",
        "quotes": [
            "Valrhona Dark Chocolate MANJARI, 65% Cacao Baking Bars - Gourmet French Chocolate, Tangy and Fruity Notes. Single Origin Madagascar. Premium Couverture, The Perfect Baking Bar 70g (Pack of 1)",
            "In stock SKU B09LMGQFTL Rating: 100 % of 100 2 Reviews Add Your Review $7.89 Flavor Name ABINAO DARK 85% ARAGUANI DARK 100% CARAIBE DARK 66% GUANAJA DARK 70% MANJARI DARK 64% ORIADO DARK 60% TULAKALUM DARK 75%",
            "MANJARI 65% IS THE MOST VERSATILE CHOCOLATE. INCREDIBLE TANGY AND FRUITY chocolate with a great 65% cacao content. Single Origin Bar with beans from Madagascar.",
        ],
        "accepted": "The frozen Valrhona page shows SKU B09LMGQFTL at 7.89 dollars, rated 100 percent over two reviews, with a title describing a 70-gram 65-percent single-origin Madagascar bar and tangy and fruity notes, while the same page also lists Manjari as 64 percent; the 64-versus-65-percent seller inconsistency remains unresolved and none of these fields independently proves exact composition, origin traceability, sensory preference, ingredients, allergens, or current delivered cost.",
    },
    {
        "evidence_id": "prop_quma_peru_quinoa_label_scope",
        "subject": "frozen Quma quinoa dark-chocolate seller page",
        "predicate": "shows_peru_percentage_recipe_and_criollo_marketing",
        "object": "a 9.99-dollar no-review offer marketed as 70-percent dark chocolate with puffed quinoa, made in Peru, minimally processed, and retaining fruity Criollo aromas",
        "source_url": SEARCHES[1][3],
        "search_id": "quma_quinoa",
        "role": "product",
        "scope": "seller_offer_origin_variety_process_and_flavor_copy_not_exact_mass_traceability_genotype_or_taste_result",
        "quotes": [
            "In stock SKU B09PMD2B73 Be the first to review this product $9.99 Qty Add to Cart Add to Wish List Add to Compare",
            "QUINOA 70% CACAO: We pair our 70% dark chocolate with puffed quinoa from the Peruvian Andes for a delicious crunchy taste.",
            "We believe that the best flavors come from maintaining the original taste of the beans, by minimal processing, we keep the fruity aromas of the Criollo varietal cacao beans in our chocolates.",
        ],
        "accepted": "The frozen Quma page shows SKU B09PMD2B73 at 9.99 dollars with no reviews shown and markets 70-percent dark chocolate with puffed quinoa, production in Peru, minimal processing, and fruity Criollo aromas; it does not establish an exact bar mass, independent origin traceability, botanical genotype, controlled flavor result, recipient preference, complete allergen status, or current delivered cost.",
    },
    {
        "evidence_id": "prop_pump_street_ecuador_dark_milk_scope",
        "subject": "frozen Pump Street Ecuador dark-milk seller page",
        "predicate": "shows_dark_milk_percentage_mass_and_flavor_copy",
        "object": "a 12.99-dollar 70-gram Ecuador dark-milk 60-percent bar rated 100 percent over one review and described with balanced cacao and creamy milk notes",
        "source_url": SEARCHES[2][3],
        "search_id": "pump_street_dark_milk",
        "role": "product",
        "scope": "seller_offer_and_dark_milk_copy_not_plain_85_percent_equivalence_or_independent_taste_result",
        "quotes": [
            "Pump Street Chocolate Ecuador Dark Milk 60%",
            "In stock SKU B00VAR0GHY Rating: 100 % of 100 1 Review Add Your Review $12.99 Qty Add to Cart Add to Wish List Add to Compare",
            "60% Dark milk chocolate 70 grams balanced cacao notes with the addition of creamy milk Handmade from bean to bar in Suffolk, UK",
        ],
        "accepted": "The frozen Pump Street page shows SKU B00VAR0GHY at 12.99 dollars, rated 100 percent over one review, and describes a 70-gram Ecuador dark-milk 60-percent bar with balanced cacao and creamy milk notes; a dark-milk bar is not equivalent to the recipient's usual plain 85-percent bar and the seller fields do not independently prove origin, sensory fit, ingredients, allergens, or current delivered cost.",
    },
    {
        "evidence_id": "prop_lindt_assorted_truffle_scope",
        "subject": "frozen Lindt assorted-truffle seller page",
        "predicate": "shows_large_mixed_truffle_box_and_gift_copy",
        "object": "a 19.99-dollar no-review 15.2-ounce box described as about 36 milk, dark, white, 60-percent extra-dark, fudge-swirl and sea-salt truffles",
        "source_url": SEARCHES[3][3],
        "search_id": "lindt_assorted_truffles",
        "role": "product",
        "scope": "seller_box_count_flavors_and_gift_copy_not_dark_share_recipe_allergen_or_recipient_fit",
        "quotes": [
            "In stock SKU B08H2TSBPX Be the first to review this product $19.99 Qty Add to Cart Add to Wish List Add to Compare",
            "15.2 oz. holiday gift box of approximately 36 individually wrapped Milk, Dark, White, 60% Extra Dark, Fudge Swirl, and Sea Salt Chocolate Truffles - perfect for Christmas gifting, sharing, or savoring one at a time",
            "Our seasonal limited-edition LINDOR Deluxe Gift Box features an assortment of six, individually-wrapped truffle flavors; assortment includes: Milk, Dark, White, 60% Extra Dark, Fudge Swirl, and Sea Salt Chocolate Truffles",
        ],
        "accepted": "The frozen Lindt page shows SKU B08H2TSBPX at 19.99 dollars with no reviews shown and describes a 15.2-ounce gift box of approximately 36 milk, dark, white, 60-percent extra-dark, fudge-swirl and sea-salt truffles; it does not establish the exact dark-piece allocation, percentage and recipe of every piece, complete ingredients and allergens, recipient preference, current stock and delivered cost, or a controlled comparison with the bars.",
    },
    {
        "evidence_id": "prop_cravings_assorted_flavor_scope",
        "subject": "frozen Cravings by Zoe assorted-truffle seller page",
        "predicate": "shows_sixteen_mixed_shells_and_flavored_fillings",
        "object": "a 24.95-dollar 7.5-ounce sixteen-piece box rated 92 percent over 12 reviews with milk, dark and white shells and multiple named fillings",
        "source_url": SEARCHES[4][3],
        "search_id": "cravings_assorted_truffles",
        "role": "product",
        "scope": "seller_box_flavors_rating_and_gift_copy_not_dark_share_percentage_allergen_alcohol_or_recipient_fit",
        "quotes": [
            "In stock SKU B09LM3H2F5 Rating: 92 % of 100 12 Reviews Add Your Review $24.95",
            "MOUTHWATERING ASSORTMENT - This irresistible chocolate gift box comes complete with a rich mixture of 16 savory gourmet chocolates in a lovely 7.5 ounce chocolate gift box. The assortment includes milk chocolate, dark chocolate and white chocolate shells with 16 delicious flavors.",
            "DELICIOUS FILLINGS: Every last gourmet chocolate in the bunch is a mouthwatering treat that is filled with premium ingredients and flavors you can only dream of; including including Amaretto, Caramel, Champagne, Coffee, Hazelnut, Irish Cream, Raspberry, Sea Salt Caramel, and Tiramisu.",
        ],
        "accepted": "The frozen Cravings by Zoe page shows SKU B09LM3H2F5 at 24.95 dollars, rated 92 percent over 12 reviews, and describes a 7.5-ounce box of 16 milk-, dark- and white-chocolate shells with fillings including Amaretto, Caramel, Champagne, Coffee, Hazelnut, Irish Cream, Raspberry, Sea Salt Caramel and Tiramisu; it does not give a dark-piece allocation, cacao percentage for each shell, complete per-piece allergen and alcohol status, recipient fit, current delivered cost, or an independent taste comparison.",
    },
    {
        "evidence_id": "prop_dark_chocolate_percentage_scope",
        "subject": "dark-chocolate percentage and composition",
        "predicate": "makes_percentage_meaningful_but_non_ranking_metadata",
        "object": "cocoa percentage combines chocolate liquor and cocoa butter while identical percentages can hide different compositions and lower percentages can have preferable flavor",
        "source_url": SEARCHES[5][3],
        "search_id": "dark_chocolate",
        "role": "concept",
        "scope": "general_composition_and_flavor_boundary_not_exact_product_recipe_quality_or_preference",
        "quotes": [
            "Many dark chocolate products sold label the cocoa percentage. This percentage refers to the percent of the chocolate that is chocolate liquor and cocoa butter, with almost all of the rest being sugar.",
            "As what part is chocolate liquor and what part is cocoa butter is not identified, chocolates with an identical cocoa percentage can have vastly different compositions and characteristics.",
            "Variability in the quality of cocoa beans mean chocolates with lower cocoa percentages can have more desirable flavors than those with higher percentages.",
        ],
        "accepted": "The dark-chocolate page says cocoa percentage combines chocolate liquor and cocoa butter, does not reveal their split, and therefore can mask very different compositions and characteristics at the same percentage; it also says bean-quality variation can make lower-percentage chocolate more desirable than higher-percentage chocolate, so percentage is useful composition metadata rather than a direct quality or recipient-preference rank.",
    },
    {
        "evidence_id": "prop_flavor_cocoa_origin_process_scope",
        "subject": "flavor-cocoa origin, process and assessment",
        "predicate": "links_flavor_to_multiple_geographic_genetic_and_processing_axes",
        "object": "premium cocoa may be scoped by region crop variety harvesting or fermentation and assessed through both objective and subjective criteria",
        "source_url": SEARCHES[6][3],
        "search_id": "flavor_cocoa",
        "role": "concept",
        "scope": "general_origin_process_and_assessment_boundary_not_exact_label_traceability_or_preference",
        "quotes": [
            "The beans are not traded as commodities , and may be from specific geographical regions, crops or varieties, or may be harvested or fermented using specific techniques.",
            "Flavor beans are assessed according to various criteria, including genetic material, acidity, fermentation and drying levels, color, harm from disease and pests, mold and flavor.",
            "Assessments are objective and subjective; while a bean can be assessed as having, for example, floral tasting notes, whether this is desirable is determined by the taster.",
        ],
        "accepted": "The flavor-cocoa page says premium beans may be associated with specific regions, crops, varieties, harvesting or fermentation techniques and are assessed using genetics, acidity, fermentation, drying, color, damage, mold and flavor; assessment has objective and subjective parts, so an origin label can identify a real scope but cannot by itself prove traceability, genotype, exact flavor or this recipient's preference.",
    },
    {
        "evidence_id": "prop_cocoa_fermentation_flavor_scope",
        "subject": "cocoa-bean fermentation mechanism",
        "predicate": "develops_flavor_precursors_and_reduces_bitterness",
        "object": "microbes break down pulp and develop precursors expressed during roasting while fermentation conditions can also create off-flavor",
        "source_url": SEARCHES[7][3],
        "search_id": "cocoa_fermentation",
        "role": "concept",
        "scope": "general_processing_mechanism_not_exact_bar_fermentation_history_or_taste_result",
        "quotes": [
            "Yeasts , lactic acid bacteria and acetic acid bacteria break down pulp surrounding the beans and develop flavor precursors within the bean that create chocolate flavors during roasting.",
            "The process also reduces bitterness and gives beans a more brown hue.",
            "In determining how long to ferment, producers try to avoid overfermention, which causes beans to take on a \"hammy\" off-flavor.",
        ],
        "accepted": "The cocoa-fermentation page says yeasts and bacteria break down pulp and develop flavor precursors that create chocolate flavors during roasting, fermentation reduces bitterness, and excessive fermentation can cause an off-flavor; this establishes processing as a plausible flavor axis but not the fermentation history, defect status or sensory outcome of any exact captured product.",
    },
    {
        "evidence_id": "prop_cocoa_variety_marketing_scope",
        "subject": "traditional cocoa-variety terminology",
        "predicate": "remains_marketing_language_without_current_botanical_basis",
        "object": "Forastero Criollo and Trinitario remain used in marketing but recent classification does not treat the traditional categories as botanically grounded",
        "source_url": SEARCHES[8][3],
        "search_id": "cocoa_varieties",
        "role": "concept",
        "scope": "general_taxonomy_marketing_boundary_not_exact_product_genotype_or_flavor",
        "quotes": [
            "The traditional varieties of Forastero, Criollo and Trinitario, while still used in marketing materials, are no longer considered to have a botanical basis.",
            "Use of these terms has changed across different contexts and times, and recent genetic research has found that the categories of Forastero and Triniario are better understood as geohistorical inventions rather than as having a botanical basis.",
            "They are still used frequently in marketing material.",
        ],
        "accepted": "The cocoa-types page says the traditional Forastero, Criollo and Trinitario categories remain used in marketing but are no longer considered to have a botanical basis and are better understood in geohistorical context; a seller's Criollo wording must therefore remain marketing evidence rather than proof of the exact bar's botanical genotype or flavor quality.",
    },
    {
        "evidence_id": "prop_chocolate_truffle_structure_scope",
        "subject": "chocolate-truffle structure and varieties",
        "predicate": "uses_fillings_coatings_and_multiple_recipe_styles",
        "object": "a traditional ganache-centered coated confection whose varieties may contain dairy butter dark or milk chocolate liqueur buttercream nuts or other fats",
        "source_url": SEARCHES[9][3],
        "search_id": "chocolate_truffle",
        "role": "concept",
        "scope": "general_truffle_structure_not_exact_box_piece_recipe_dark_share_allergen_or_fit",
        "quotes": [
            "A chocolate truffle is a French chocolate confectionery [ 1 ] traditionally made with a chocolate ganache center and coated in cocoa powder, coconut , or chopped nuts.",
            "The Spanish truffle, prepared with dark chocolate, condensed milk, rum (or any preferred liqueur), and chocolate sprinkles.",
            "The Belgian truffle or praline , made with dark or milk chocolate filled with ganache, buttercream, or nut pastes.",
        ],
        "accepted": "The chocolate-truffle page describes a traditional ganache center with a coating and varieties using cream, butter, dark or milk chocolate, condensed milk, liqueur, buttercream or nut paste; total box mass or count therefore cannot reveal the recipient-acceptable dark share, and the exact box still requires piece, recipe, ingredient, allergen and alcohol verification.",
    },
    {
        "evidence_id": "prop_jersey_city_gift_discussion_scope",
        "subject": "Jersey City handmade chocolate-gift discussion",
        "predicate": "asks_for_a_shipped_birthday_gift_and_reports_one_truffle_gift_impression",
        "object": "a local shipped-gift question plus one commenter saying boxes of a business's truffles went over pretty well",
        "source_url": SEARCHES[10][3],
        "search_id": "jersey_city_gifts",
        "role": "community",
        "scope": "author_business_and_recipient_specific_gift_impression_not_exact_offer_test_or_market_rate",
        "quotes": [
            "Looking for a local place that does handmade chocolates that can ship to VA for a friend’s birthday. Any recs? 10",
            "I've gotten boxes of their truffles as gifts before and they went over pretty well",
        ],
        "accepted": "The Jersey City thread asks for handmade chocolates shipped to Virginia for a friend's birthday and one commenter says boxes of one business's truffles went over pretty well; this is an author-, recipient- and business-scoped gift impression, not a controlled test, market rate, exact-offer comparison, or proof that either captured box fits an 85-percent dark-chocolate recipient.",
    },
    {
        "evidence_id": "prop_pennsylvania_flavor_box_discussion_scope",
        "subject": "Pennsylvania flavor-variety box discussion",
        "predicate": "recalls_custom_flavor_choice_but_leaves_company_unresolved",
        "object": "a memory of many interesting flavors selected into a clear rectangular box followed by guesses that do not identify the company",
        "source_url": SEARCHES[11][3],
        "search_id": "pennsylvania_flavor_box",
        "role": "community",
        "scope": "author_memory_and_unresolved_identity_not_exact_product_recipe_availability_or_preference_test",
        "quotes": [
            "I recall that they had a huge variety in flavors, and you could choose what flavors they’d put in a box for you.",
            "The box was clear and rectangular, and the chocolates were shaped like single kit-kat pieces. The flavors were all really interesting.",
            "I did, they weren’t able to give me an answer.",
        ],
        "accepted": "The Pennsylvania thread recalls a company with a large variety of interesting flavors chosen into a clear rectangular box, but the author and commenters do not resolve its identity; this is a memory and unresolved sourcing discussion, not evidence about either exact box's recipe, availability, dark share, quality or recipient fit.",
    },
    {
        "evidence_id": "prop_lpt_price_taste_discussion_scope",
        "subject": "LifeProTips chocolate price and taste discussion",
        "predicate": "contains_scoped_cost_substitution_and_conflicting_taste_statements",
        "object": "one price-per-ounce substitution claim plus replies about higher prices, semisweet preference and disputed mass-market quality",
        "source_url": SEARCHES[12][3],
        "search_id": "lpt_price_taste",
        "role": "community",
        "scope": "author_product_time_and_preference_specific_statements_not_current_market_rate_or_exact_offer_test",
        "quotes": [
            "Comparing a 10.5 oz bag of M&Ms and an 11 oz bag of milk chocolate chips, the store brand pure milk chocolate chips are about half the price of the M&Ms per ounce and taste great.",
            "All chocolate prices have risen, including baking chocolate.",
            "Semisweet is the perfect ratio; milk chocolate is to sweet, and dark chocolate is too sharp.",
        ],
        "accepted": "The LifeProTips thread contains one price-per-ounce comparison between milk-chocolate chips and M&Ms, a reply that all chocolate prices have risen, and one person's preference for semisweet over milk or dark; these are product-, time-, author- and preference-scoped statements rather than a current market rate, an exact-offer test, a universal sweetness ranking, or evidence about the sister's preference.",
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
            "registry_id": "reg_case_spec_dark_chocolate_gift_0044",
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
            "bridge_seller_bar_origin_percentage_scope",
            "bridge",
            "three exact bar seller snapshots",
            "retain_literal_offer_fields_and_label_conflicts",
            "record price rating review count mass recipe origin percentage and flavor copy while retaining the Valrhona 64-versus-65-percent conflict and not treating seller fields as independent taste or fit evidence",
            "seller_bar_origin_percentage_scope_v1",
        ),
        (
            "bridge_seller_truffle_box_scope",
            "bridge",
            "two exact assorted-truffle seller snapshots",
            "retain_box_count_mass_flavors_and_unknown_dark_share",
            "record price rating mass count shell and filling descriptions while requiring exact dark allocation recipe ingredient allergen alcohol and recipient-fit verification",
            "seller_truffle_box_scope_v1",
        ),
        (
            "bridge_percentage_composition_boundary",
            "bridge",
            "cacao percentages across unlike chocolate products",
            "treat_percentage_as_metadata_not_quality_rank",
            "preserve the liquor and cocoa-butter composition meaning plus undisclosed split and product-form differences without ranking taste or equating dark milk filled truffles plain bars and an 85-percent reference",
            "percentage_composition_boundary_v1",
        ),
        (
            "bridge_origin_processing_flavor_boundary",
            "bridge",
            "origin variety fermentation processing and flavor evidence",
            "supports_real_multi_axis_variation_without_label_determinism",
            "retain origin genetics growing conditions fermentation drying roasting recipe process and subjective preference as separate axes and keep traditional variety labels at marketing scope",
            "origin_processing_flavor_boundary_v1",
        ),
        (
            "bridge_truffle_format_recipient_fit",
            "bridge",
            "filled truffle structure and exact gift boxes",
            "requires_piece_recipe_and_recipient_fit_audit",
            "treat filled and coated truffles as unlike plain dark bars and verify dark share shell filling ingredients allergens alcohol storage and recipient constraints before comparing generosity",
            "truffle_format_recipient_fit_boundary_v1",
        ),
        (
            "bridge_community_gift_price_preference_scope",
            "bridge",
            "three community gift variety price and taste discussions",
            "retain_author_business_product_time_and_preference_scope",
            "use gifting assortment price sweetness and format comments as variables to check without converting them into controlled tests current rates exact-offer histories or recipient verdicts",
            "community_gift_price_preference_scope_v1",
        ),
        (
            "bridge_matched_gift_matrix_tasting",
            "bridge",
            "exact gift audit and reversible recipient tasting",
            "requires_complete_budget_recipe_delivery_and_taste_gates",
            "build an exact-offer matrix calculate cost per acceptable dark serving verify delivery and ingredient constraints and run a small matched tasting against the recipient's known 85-percent reference while deferring unresolved material cells",
            "matched_gift_matrix_tasting_v1",
        ),
        (
            "decision_evidence_bounded_dark_chocolate_gift",
            "decision",
            "fixed-budget dark-chocolate birthday gift",
            "selects_only_the_cheapest_exact_passing_gift_or_reference_or_deferral",
            "reject automatic single-origin percentage rating or bigger-box winners and choose only the cheapest exact gift clearing budget recipient darkness format ingredient allergen delivery and taste gates or use a small known 85-percent reference or defer",
            "evidence_bounded_dark_chocolate_gift_v1",
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
        "bridge_seller_bar_origin_percentage_scope": [
            "prop_valrhona_manjari_label_scope",
            "prop_quma_peru_quinoa_label_scope",
            "prop_pump_street_ecuador_dark_milk_scope",
        ],
        "bridge_seller_truffle_box_scope": [
            "prop_lindt_assorted_truffle_scope",
            "prop_cravings_assorted_flavor_scope",
        ],
        "bridge_percentage_composition_boundary": [
            "prop_dark_chocolate_percentage_scope",
            "prop_valrhona_manjari_label_scope",
            "prop_quma_peru_quinoa_label_scope",
            "prop_pump_street_ecuador_dark_milk_scope",
        ],
        "bridge_origin_processing_flavor_boundary": [
            "prop_dark_chocolate_percentage_scope",
            "prop_flavor_cocoa_origin_process_scope",
            "prop_cocoa_fermentation_flavor_scope",
            "prop_cocoa_variety_marketing_scope",
            "prop_valrhona_manjari_label_scope",
            "prop_quma_peru_quinoa_label_scope",
            "prop_pump_street_ecuador_dark_milk_scope",
        ],
        "bridge_truffle_format_recipient_fit": [
            "prop_chocolate_truffle_structure_scope",
            "prop_lindt_assorted_truffle_scope",
            "prop_cravings_assorted_flavor_scope",
        ],
        "bridge_community_gift_price_preference_scope": [
            "prop_jersey_city_gift_discussion_scope",
            "prop_pennsylvania_flavor_box_discussion_scope",
            "prop_lpt_price_taste_discussion_scope",
        ],
        "bridge_matched_gift_matrix_tasting": [
            "bridge_seller_bar_origin_percentage_scope",
            "bridge_seller_truffle_box_scope",
            "bridge_percentage_composition_boundary",
            "bridge_origin_processing_flavor_boundary",
            "bridge_truffle_format_recipient_fit",
            "bridge_community_gift_price_preference_scope",
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
                "source_id": "decision_evidence_bounded_dark_chocolate_gift",
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
