#!/usr/bin/env python3
"""Build the frozen Q43 clinician-guided decaf and low-caffeine ritual inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0043-decaf-low-caffeine-ritual-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0043/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0043-decaf-low-caffeine-ritual-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0043-decaf-low-caffeine-ritual-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0043"
TOPIC = "doctor_guided_decaf_low_caffeine_ritual_boundary"


SEARCHES = [
    (
        "merry_swp_decaf",
        "001-shopping-merry-mocha-mint-swp-decaf.json",
        "Merry Mocha Mint whole-bean SWP Decaf seller snapshot",
        "http://localhost:7770/merry-mocha-mint-flavored-coffee-swp-decaf-specialty-arabica-coffee-medium-roast-12-ounce-whole-bean.html",
    ),
    (
        "seattles_best_decaf",
        "002-shopping-seattles-best-decaf-portside.json",
        "Seattle's Best Decaf Portside ground-coffee seller snapshot",
        "http://localhost:7770/seattle-s-best-coffee-decaf-portside-blend-previously-signature-blend-no-3-medium-roast-ground-coffee-12-ounce-pack-of-1.html",
    ),
    (
        "ocha_hojicha_powder",
        "003-shopping-ocha-co-hojicha-low-caffeine.json",
        "Ocha and Co. low-caffeine-labeled hojicha powder seller snapshot",
        "http://localhost:7770/ocha-co-hojicha-powder-japanese-organic-roasted-green-tea-latte-powder-houjicha-green-tea-blend-made-from-powdered-kukicha-and-sencha-low-caffeine-tea-with-a-sweet-smoky-taste-100g-3-5oz.html",
    ),
    (
        "good_earth_decaf_tea",
        "004-shopping-good-earth-decaf-lemongrass-green-tea.json",
        "Good Earth decaffeinated lemongrass green-tea seller snapshot",
        "http://localhost:7770/good-earth-tea-decaffeinated-lemongrass-green-tea-50th-anniversary-18-tea-bags-pack-of-6.html",
    ),
    (
        "decaffeination",
        "005-wiki-decaffeination-residual-and-methods.json",
        "decaffeination residual-caffeine and process boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Decaffeination",
    ),
    (
        "hojicha",
        "006-wiki-hojicha-roast-and-caffeine.json",
        "hojicha roast, flavor, and general caffeine boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/H%C5%8Djicha",
    ),
    (
        "white_tea",
        "007-wiki-white-tea-caffeine-variability.json",
        "white-tea brewing and caffeine variability boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/White_tea",
    ),
    (
        "herbal_tea",
        "008-wiki-herbal-tea-category-boundary.json",
        "herbal-infusion caffeine and ingredient boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Herbal_tea",
    ),
    (
        "community_brew_change",
        "009-forum-brew-ratio-strong-coffee-anecdote.json",
        "individual large brew-ratio change anecdote",
        "http://localhost:9999/f/tifu/49658/tifu-by-purchasing-an-expensive-coffee-machine-and-making-a",
    ),
    (
        "community_sensory_proxy",
        "010-forum-tea-color-bitterness-caffeine-question.json",
        "individual tea color, bitterness, and caffeine exchange",
        "http://localhost:9999/f/askscience/58717/does-lemon-acid-slows-down-or-stops-extraction-of-tannins",
    ),
    (
        "community_small_samples",
        "011-forum-small-amount-loose-tea-variety.json",
        "individual small-quantity loose-tea sampling discussion",
        "http://localhost:9999/f/boston/103493/good-store-to-buy-loose-leaf-tea",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_merry_swp_decaf_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Merry Mocha Mint SWP Decaf offer",
        "predicate": "shows_seller_sku_price_size_process_and_flavor_claims",
        "object": "SKU B07KC6D3HR at 17.49 dollars, titled as a 12-ounce whole-bean SWP Decaf coffee, with seller claims of Swiss Water processing, 99.9-percent caffeine-free status, and flavor protection",
        "source_url": SEARCHES[0][3],
        "search_id": "merry_swp_decaf",
        "role": "product",
        "scope": "seller_snapshot_not_independently_verified_serving_caffeine_process_certificate_flavor_result_or_clinical_suitability",
        "quotes": [
            "Merry Mocha Mint Flavored Coffee SWP Decaf, Specialty Arabica Coffee, Medium Roast, 12 ounce, Whole Bean",
            "In stock SKU B07KC6D3HR Be the first to review this product $17.49 Style Automatic Drip Coarse Fine Very Fine Whole Bean Qty Add to Cart Add to Wish List Add to Compare",
            "We care about giving you the best product, so all of our Decaf Coffee is decaffeinated using the Swiss Water Process.",
            "This process is the only chemical-free decaffeination process that delivers coffee that is 99.9% caffeine-free while protecting the unique origin characteristics and flavor.",
        ],
        "accepted": "The frozen seller page shows SKU B07KC6D3HR at 17.49 dollars and titles it as a 12-ounce whole-bean Merry Mocha Mint SWP Decaf product; the page also claims Swiss Water processing, 99.9-percent caffeine-free status, and flavor protection, but supplies no independently verified finished-serving caffeine milligrams, process certificate, sensory result, or individualized suitability determination.",
    },
    {
        "evidence_id": "prop_seattles_best_decaf_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Seattle's Best Decaf Portside offer",
        "predicate": "shows_seller_sku_price_rating_decaf_label_and_weight_discrepancy",
        "object": "SKU B01LTI9656 at 6.99 dollars with a 78-percent-of-100 aggregate over twelve reviews, titled and quick-looked as a 12-ounce decaffeinated ground coffee while a product-dimensions line says 10.4 ounces",
        "source_url": SEARCHES[1][3],
        "search_id": "seattles_best_decaf",
        "role": "product",
        "scope": "seller_snapshot_with_internal_weight_discrepancy_not_verified_net_weight_method_residual_caffeine_or_taste_result",
        "quotes": [
            "Seattle's Best Coffee Decaf Portside Blend (Previously Signature Blend No. 3) Medium Roast Ground Coffee, 12 Ounce (Pack of 1)",
            "In stock SKU B01LTI9656 Rating: 78 % of 100 12 Reviews Add Your Review $6.99 Flavor Name blend dark roast Decaf Portside Hazelnut House Blend Portside Size 1.25 Pound (Pack of 1) 12 Ounce (Pack of 1) 12 Ounce (Pack of 2) Qty Add to Cart Add to Wish List Add to Compare",
            "Decaf Portside Blend is a medium roasted, decaffeinated coffee with a well-rounded and smooth flavor",
            "Product Dimensions ‏ ‎ 2.5 x 3.4 x 6.5 inches; 10.4 Ounces",
        ],
        "accepted": "The frozen seller page shows Seattle's Best SKU B01LTI9656 at 6.99 dollars with a 78-percent-of-100 aggregate over twelve reviews and labels it Decaf Portside ground coffee; its title says 12 ounces while a product-dimensions line says 10.4 ounces, so the exact net weight, decaffeination method, residual caffeine per serving, and taste outcome remain unresolved.",
    },
    {
        "evidence_id": "prop_ocha_hojicha_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Ocha and Co. hojicha powder offer",
        "predicate": "shows_seller_sku_price_size_relative_caffeine_and_flavor_labels",
        "object": "SKU B0973D79W7 at 27 dollars, titled as a 100-gram or 3.5-ounce roasted sencha-and-kukicha powder and seller-labeled lower caffeine with a sweet smoky taste",
        "source_url": SEARCHES[2][3],
        "search_id": "ocha_hojicha_powder",
        "role": "product",
        "scope": "seller_relative_claim_not_exact_caffeine_milligrams_serving_preparation_taste_result_or_clinical_suitability",
        "quotes": [
            "Ocha & Co. Hojicha Powder - Japanese Organic Roasted Green Tea Latte Powder - Houjicha Green Tea Blend Made From Powdered Kukicha and Sencha - Low Caffeine Tea with a Sweet, Smoky Taste, 100g/3.5oz.",
            "In stock SKU B0973D79W7 Be the first to review this product $27.00 Qty Add to Cart Add to Wish List Add to Compare",
            "Low caffeine content compared to other green teas. Aromatic, naturally sweet, and smooth.",
            "HOJICHA GREEN TEA POWDER: Our high-grade organic Hojicha powder is a blend of roasted Sencha and Kukicha green teas; the organic powdered green tea is naturally lower in caffeine than regular green teas",
        ],
        "accepted": "The frozen seller page shows Ocha and Co. SKU B0973D79W7 at 27 dollars, titles it as 100 grams or 3.5 ounces of powdered roasted sencha and kukicha, and claims relatively lower caffeine plus sweet, smoky, or smooth flavor; it gives no exact caffeine milligrams per prepared serving, verified preparation, taste result, or individualized suitability.",
    },
    {
        "evidence_id": "prop_good_earth_decaf_tea_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen Good Earth decaffeinated lemongrass green-tea offer",
        "predicate": "shows_seller_sku_price_rating_pack_and_decaf_flavor_labels",
        "object": "SKU B09JKZHQ6V at 22.96 dollars with a 92-percent-of-100 aggregate over twelve reviews, titled as six packs of eighteen decaffeinated lemongrass green-tea bags with fruit, lemongrass, and peppermint flavor language",
        "source_url": SEARCHES[3][3],
        "search_id": "good_earth_decaf_tea",
        "role": "product",
        "scope": "seller_snapshot_not_verified_caffeine_milligrams_ingredient_interaction_taste_result_or_clinical_suitability",
        "quotes": [
            "Good Earth Tea, Decaffeinated Lemongrass Green Tea, 50th Anniversary, 18 Tea Bags (Pack of 6)",
            "In stock SKU B09JKZHQ6V Rating: 92 % of 100 12 Reviews Add Your Review $22.96 Flavor Name Chai Black Tea Decaffeinated Lemongrass Green Tea Qty Add to Cart Add to Wish List Add to Compare",
            "This flavored green tea is bold, decaffeinated, and packs a fruity punch!",
            "Premium decaffeinated green tea blended with citrus lemongrass, sweet mango, juicy peach and refreshing peppermint for a delicate tropical brew",
        ],
        "accepted": "The frozen seller page shows Good Earth SKU B09JKZHQ6V at 22.96 dollars with a 92-percent-of-100 aggregate over twelve reviews and titles it as six packs of eighteen decaffeinated lemongrass green-tea bags; its flavor and ingredient language does not supply verified caffeine milligrams per serving, interaction screening, a taste result, or individualized suitability.",
    },
    {
        "evidence_id": "prop_decaffeination_residual_process_scope",
        "node_type": "proposition",
        "subject": "decaffeination and finished-product residual caffeine",
        "predicate": "defines_reduction_standards_residual_variability_and_process_goals",
        "object": "caffeine removal rather than guaranteed zero, with a United States reduction threshold, reported residual variability, and solvent, carbon-dioxide, or water processes that try to retain flavor precursors",
        "source_url": SEARCHES[4][3],
        "search_id": "decaffeination",
        "role": "concept",
        "scope": "general_process_and_measurement_context_not_exact_product_caffeine_flavor_or_clinician_limit",
        "quotes": [
            "Decaffeination is the removal of caffeine from coffee beans , cocoa , tea leaves, and other caffeine-containing materials.",
            "A caffeine content reduction of at least 97% is required under United States FDA standards.",
            "A 2006 study found decaffeinated drinks to contain typically 1â2% of the original caffeine content, but sometimes as much as 20%.",
            "These methods take place prior to roasting and may use organic solvents such as dichloromethane or ethyl acetate , supercritical CO 2 , or water to extract caffeine from the beans, while leaving flavour precursors in as close to their original state as possible.",
            "This process uses no organic solvents, and instead only water is used to decaffeinate beans.",
        ],
        "accepted": "The frozen decaffeination page defines caffeine removal, gives a United States reduction threshold of at least 97 percent, reports that residual caffeine can vary, and describes solvent, supercritical-carbon-dioxide, and water approaches that try to retain flavor precursors; these general facts do not establish zero milligrams, exact-product flavor, or fit with an individual's clinician instruction.",
    },
    {
        "evidence_id": "prop_hojicha_general_roast_flavor_caffeine_scope",
        "node_type": "proposition",
        "subject": "hojicha as a roasted green-tea category",
        "predicate": "has_general_roast_flavor_and_lower_caffeine_context",
        "object": "a roasted Japanese green tea that can be powdered for milk drinks, with nutty, toasty, sweet, low-bitterness flavor and generally lowered caffeine after roasting",
        "source_url": SEARCHES[5][3],
        "search_id": "hojicha",
        "role": "concept",
        "scope": "general_category_context_not_exact_powder_caffeine_serving_taste_or_clinical_suitability",
        "quotes": [
            "Hojicha is sometimes sold in a powdered form and used to make steamed milk drinks.",
            "Once infused, hÅjicha has a nutty, toasty, sweet flavor. The tea has little to no bitterness.",
            "The roasting process used to make hÅjicha also lowers the amount of caffeine in the tea.",
        ],
        "accepted": "The frozen hojicha page describes a roasted Japanese green-tea category that may be powdered for milk drinks, gives general nutty, toasty, sweet, low-bitterness flavor context, and says roasting lowers caffeine; it provides no exact amount, preparation, taste result, or individualized suitability for the frozen Ocha powder.",
    },
    {
        "evidence_id": "prop_white_tea_caffeine_variability_scope",
        "node_type": "proposition",
        "subject": "white-tea caffeine content",
        "predicate": "varies_with_tea_and_brewing_and_cannot_be_read_from_a_light_label",
        "object": "caffeine depends on tea type and brewing method, with wide cup estimates and no simple proven variety relationship because brewed-tea values vary",
        "source_url": SEARCHES[6][3],
        "search_id": "white_tea",
        "role": "concept",
        "scope": "general_category_variability_not_exact_product_serving_or_clinician_limit",
        "quotes": [
            "The caffeine content of tea depends on many factors, including the type of tea and the brewing method.",
            "Estimates for the caffeine content of a cup of brewed white tea range widely, from less than 10 mg to over 50 mg, with some studies concluding that white tea tends to have less caffeine than green tea.",
            "Due to the wide variability of the caffeine content in brewed tea, some studies have failed to prove a relationship between the variety of tea and the caffeine content.",
        ],
        "accepted": "The frozen white-tea page says caffeine depends on tea type and brewing method, gives a wide less-than-10-to-over-50-milligram estimate range per brewed cup, and notes that variability has prevented a simple proven variety relationship; a white, pale, light, or mild label therefore cannot supply an exact serving value or clinician-limit determination.",
    },
    {
        "evidence_id": "prop_herbal_tea_caffeine_ingredient_scope",
        "node_type": "proposition",
        "subject": "herbal infusions and their ingredients",
        "predicate": "are_not_true_tea_and_are_not_universally_caffeine_or_interaction_free",
        "object": "most tisanes do not naturally contain caffeine, but some plants contain caffeine or other stimulants and some plant compounds can interact with medications",
        "source_url": SEARCHES[7][3],
        "search_id": "herbal_tea",
        "role": "concept",
        "scope": "general_category_and_interaction_context_not_exact_blend_safety_diagnosis_or_treatment",
        "quotes": [
            "Herbal teas are not technically teas because they are not brewed from the tea plant.",
            "Unlike true teas, most tisanes do not naturally contain caffeine (though tea can be decaffeinated , i.e., processed to remove caffeine).",
            "A number of plants, however, do contain psychoactive compounds, such as caffeine or another stimulant , like theobromine , cocaine or ephedrine .",
            "Some phytochemicals found in herbs and fruits can adversely interact with others and over the counter or prescription medications, among other ways by affecting their metabolism by the body.",
        ],
        "accepted": "The frozen herbal-tea page distinguishes tisanes from true tea and says most do not naturally contain caffeine, while also noting that some plant infusions contain caffeine or other stimulants and that some plant compounds can interact with medications; this supports exact-ingredient verification and clinician or pharmacist review, not a blanket safety claim, diagnosis, or treatment.",
    },
    {
        "evidence_id": "prop_community_brew_change_anecdote_scope",
        "node_type": "proposition",
        "subject": "one TIFU author's coffee preparation change",
        "predicate": "reports_a_large_ratio_change_and_personal_symptoms",
        "object": "a two-300-millilitre-mug habit, a move from about 20 to 60 grams of grounds per litre, and an exaggerated personal symptom report after the stronger preparation",
        "source_url": SEARCHES[8][3],
        "search_id": "community_brew_change",
        "role": "community",
        "scope": "uncontrolled_personal_anecdote_not_measured_caffeine_medical_causality_threshold_or_advice",
        "quotes": [
            "My mornings consist of two 300ml mugs of coffee, and I sometimes have a third after dinner later in the day.",
            "Now, coffee science says the ideal water-to-beans ratio for this brew method is about 60g of grounds per litre of water.",
            "It turns out, since I got the old machine just over a year ago, I've been brewing at about 20g/litre, resulting in what I now realise is pathetically weak brew.",
            "And I had just drunk over half a litre of coffee that was theoretically three times as strong as usual.",
        ],
        "accepted": "One TIFU author describes a two-300-millilitre-mug habit and changing a brew ratio from about 20 to 60 grams per litre before reporting exaggerated symptoms; this uncontrolled anecdote motivates fixed preparation and symptom stop rules but supplies neither measured caffeine exposure, medical causality, a safe threshold, nor advice for the user.",
    },
    {
        "evidence_id": "prop_community_sensory_proxy_question_scope",
        "node_type": "proposition",
        "subject": "one AskScience tea-color and caffeine exchange",
        "predicate": "contrasts_lighter_less_bitter_tea_with_a_commenters_same_quantity_claim",
        "object": "a question about whether lemon-reduced color and bitterness imply less caffeine and one commenter's response that perceived weakening can occur despite the same quantities of food chemistry",
        "source_url": SEARCHES[9][3],
        "search_id": "community_sensory_proxy",
        "role": "community",
        "scope": "individual_question_and_comment_not_laboratory_measurement_medical_evidence_or_exact_product_result",
        "quotes": [
            "I know that adding lemon changing colour of tea, making it lighter. And taste of tea has less bitterness. But does it mean that lemon acid neutralises or break down tannins and caffeine (which responsible for bitterness)? Or they are still there?Especially caffeine",
            "No change. Lemon juice does nothing for tannins or caffeine. It won't affect the amount extracted, it won't change the extraction time.",
            "Overall: it makes the tea/coffee taste a little bit weaker, despite containing all the same quantities of food chemistry.",
        ],
        "accepted": "One AskScience exchange asks whether lighter color and lower bitterness after lemon mean less caffeine, and a commenter says perceived weakening can occur without changing the quantities; this is useful only as a prompt not to use sensory appearance as an exposure proxy, because it is not a laboratory measurement, medical source, or exact-product result.",
    },
    {
        "evidence_id": "prop_community_small_sample_tea_scope",
        "node_type": "proposition",
        "subject": "individual Boston loose-tea shoppers",
        "predicate": "discuss_small_quantities_samples_and_varied_tea_categories",
        "object": "a request for small amounts of varied loose teas and a comment describing 10-to-20-gram sample packs plus blends, flavored, decaf, and herbal categories",
        "source_url": SEARCHES[10][3],
        "search_id": "community_small_samples",
        "role": "community",
        "scope": "individual_shopping_discussion_not_exact_product_safety_efficacy_freshness_or_population_preference",
        "quotes": [
            "Hiya, I’m looking to get a little variety of loose-leaf teas as a gift for a friend. I’d prefer a place where I can get a nice variety of small amounts so they can make their own blends with it.",
            "They have most teas available in sample packs of between 10 to 20 grams.",
            "Many of their teas are single estate teas, but they also have blends, flavored teas, decaf teas, and herbal teas (tisanes).",
        ],
        "accepted": "One Boston thread asks for varied loose teas in small amounts and a commenter describes 10-to-20-gram samples across several categories; this supports low-commitment sampling only, not exact-product safety, efficacy, freshness, or population preference.",
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
            "registry_id": "reg_case_spec_decaf_low_caffeine_ritual_0043",
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
            "bridge_decaf_low_caffeine_offer_disclosure_matrix",
            "bridge",
            "four frozen coffee and tea offers",
            "audits_exact_fields_and_preserves_unknown_exposure",
            "compare exact SKU, price, package fields, ratings, format, process and flavor labels, surface the Seattle weight discrepancy, and preserve that none supplies independently verified caffeine milligrams per prepared serving",
            "decaf_low_caffeine_offer_disclosure_matrix_v1",
        ),
        (
            "bridge_decaffeination_residual_and_flavor_boundary",
            "bridge",
            "decaffeination residual caffeine and flavor",
            "separates_reduction_method_and_sensory_outcome",
            "treat decaf as caffeine reduction rather than zero, describe process and flavor-preservation goals, and do not turn a seller process or percentage claim into exact serving exposure or a universally best-tasting method",
            "decaffeination_residual_and_flavor_boundary_v1",
        ),
        (
            "bridge_tea_category_caffeine_uncertainty",
            "bridge",
            "hojicha white tea and herbal-infusion categories",
            "rejects_category_and_sensory_shortcuts_to_exposure",
            "use general category facts while requiring exact preparation and ingredients; never infer exact caffeine or individualized suitability from low, light, mild, pale, less bitter, white, or herbal labels",
            "tea_category_caffeine_uncertainty_v1",
        ),
        (
            "bridge_scoped_ritual_and_preparation_transfer",
            "bridge",
            "three community ritual and preparation discussions",
            "retains_anecdote_question_and_shopping_scope",
            "use the pages only to motivate fixed preparation, sensory-proxy skepticism, small samples, repeats, and stop conditions rather than medical causality, a safe threshold, exact-product outcomes, or population preference",
            "scoped_ritual_and_preparation_transfer_v1",
        ),
        (
            "bridge_clinician_limit_first_safety_gate",
            "bridge",
            "individual clinician instruction and exact serving exposure",
            "gates_consumption_before_any_taste_trial",
            "follow the clinician's individualized instruction, avoid diagnosis, generic safe doses, tapering, and treatment, require verified product-specific serving caffeine and ingredient review before consumption, and defer or contact the clinician when exposure, instruction, interactions, or symptoms are unclear",
            "clinician_limit_first_safety_gate_v1",
        ),
        (
            "bridge_reversible_ritual_preserving_trial",
            "bridge",
            "eligible morning-coffee and afternoon-tea candidates",
            "tests_taste_and_ritual_only_after_safety_eligibility",
            "use smallest quantities, fixed recipes, blinded order where practical, repeated days, a verified caffeine ledger, and predeclared taste, wateriness, ritual, effort, cost, and waste thresholds without exceeding the clinician-compatible exposure",
            "reversible_ritual_preserving_trial_v1",
        ),
        (
            "decision_evidence_bounded_decaf_low_caffeine_order",
            "decision",
            "clinician-guided decaf and low-caffeine ritual purchase",
            "orders_and_rebuys_only_a_verified_eligible_trial_winner_or_defers",
            "resolve exact product data, order only a candidate whose verified finished-serving caffeine and ingredients fit the clinician's instruction, then rebuy the lowest-total-cost exact option that repeatedly passes the fixed ritual trial, or defer and ask the clinician or manufacturer",
            "evidence_bounded_decaf_low_caffeine_order_v1",
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
        "bridge_decaf_low_caffeine_offer_disclosure_matrix": [
            "prop_merry_swp_decaf_offer_snapshot",
            "prop_seattles_best_decaf_offer_snapshot",
            "prop_ocha_hojicha_offer_snapshot",
            "prop_good_earth_decaf_tea_offer_snapshot",
        ],
        "bridge_decaffeination_residual_and_flavor_boundary": [
            "prop_merry_swp_decaf_offer_snapshot",
            "prop_seattles_best_decaf_offer_snapshot",
            "prop_good_earth_decaf_tea_offer_snapshot",
            "prop_decaffeination_residual_process_scope",
        ],
        "bridge_tea_category_caffeine_uncertainty": [
            "prop_ocha_hojicha_offer_snapshot",
            "prop_good_earth_decaf_tea_offer_snapshot",
            "prop_hojicha_general_roast_flavor_caffeine_scope",
            "prop_white_tea_caffeine_variability_scope",
            "prop_herbal_tea_caffeine_ingredient_scope",
        ],
        "bridge_scoped_ritual_and_preparation_transfer": [
            "prop_community_brew_change_anecdote_scope",
            "prop_community_sensory_proxy_question_scope",
            "prop_community_small_sample_tea_scope",
        ],
        "bridge_clinician_limit_first_safety_gate": [
            "bridge_decaf_low_caffeine_offer_disclosure_matrix",
            "bridge_decaffeination_residual_and_flavor_boundary",
            "bridge_tea_category_caffeine_uncertainty",
            "bridge_scoped_ritual_and_preparation_transfer",
        ],
        "bridge_reversible_ritual_preserving_trial": [
            "bridge_decaf_low_caffeine_offer_disclosure_matrix",
            "bridge_decaffeination_residual_and_flavor_boundary",
            "bridge_tea_category_caffeine_uncertainty",
            "bridge_scoped_ritual_and_preparation_transfer",
            "bridge_clinician_limit_first_safety_gate",
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
                "source_id": "decision_evidence_bounded_decaf_low_caffeine_order",
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
