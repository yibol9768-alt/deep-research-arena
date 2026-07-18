#!/usr/bin/env python3
"""Build the frozen Q45 sugar-free claim and individualized-fit inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-snacks-chocolate-0045-sugar-free-label-metabolic-tolerance-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_snacks_chocolate_0045/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-snacks-chocolate-0045-sugar-free-label-metabolic-tolerance-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-snacks-chocolate-0045-sugar-free-label-metabolic-tolerance-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_snacks_chocolate_0045"
TOPIC = "sugar_free_label_metabolic_tolerance_and_individualized_fit_boundary"


SEARCHES = [
    ("highkey", "001-shopping-highkey-caramel-filled-bar.json", "HighKey caramel-filled bar seller snapshot", "http://localhost:7770/highkey-sugar-free-chocolate-bar-3-17oz-3pack-keto-snacks-caramel-filled-milk-chocolate-bars-diabetic-dessert-low-carb-snack-healthy-candy-zero-carbs-diet-friendly-food-for-adults-no-sugar-added-cocoa.html"),
    ("lilys", "002-shopping-lilys-crispy-rice-stevia-bar.json", "Lily's crispy-rice dark bar seller snapshot", "http://localhost:7770/crispy-rice-dark-chocolate-bar-by-lily-s-made-with-stevia-no-added-sugar-low-carb-keto-friendly-55-cocoa-fair-trade-gluten-free-non-gmo-ingredients-3-ounce-4-pack.html"),
    ("choczero", "003-shopping-choczero-peanut-butter-cups.json", "ChocZero dark peanut-butter cups seller snapshot", "http://localhost:7770/choczero-s-dark-chocolate-peanut-butter-cups-sugar-free-keto-friendly-2bags.html"),
    ("hershey", "004-shopping-hershey-special-dark-zero-sugar.json", "HERSHEY'S SPECIAL DARK zero-sugar seller snapshot", "http://localhost:7770/hershey-s-special-dark-zero-sugar-chocolate-sugar-free-candy-individually-wrapped-5-1-oz-pouch.html"),
    ("russell_stover", "005-shopping-russell-stover-stevia-dark.json", "Russell Stover stevia dark seller snapshot", "http://localhost:7770/russell-stover-sugar-free-dark-chocolate-with-stevia-3-oz-bag.html"),
    ("sugar_substitute", "006-wiki-sugar-substitute-context.json", "sugar-substitute category and evidence boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Sugar_substitute"),
    ("sugar_alcohol", "007-wiki-sugar-alcohol-context.json", "sugar-alcohol absorption and tolerance boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Sugar_alcohol"),
    ("maltitol", "008-wiki-maltitol-context.json", "maltitol-specific metabolism and tolerance boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Maltitol"),
    ("stevia", "009-wiki-stevia-context.json", "stevia extract, taste, and regulatory boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Stevia"),
    ("glycemic_index", "010-wiki-glycemic-index-context.json", "glycemic-index population and individual-response boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Glycemic_index"),
    ("friends_diarrhea", "011-forum-tifu-friends-diarrhea.json", "confounded diet-ice-cream digestive anecdote", "http://localhost:9999/f/tifu/135445/tifu-by-accidentally-giving-my-friends-diharrhea"),
    ("werther_pack", "012-forum-tifu-werther-pack.json", "extreme-intake sugar-free candy anecdote", "http://localhost:9999/f/tifu/135460/tifu-by-eating-an-entire-pack-of-sugar-free-werther-candies"),
    ("sugar_free_drinks", "013-forum-eli5-sugar-free-drinks.json", "conflicting sugar-free drink discussion", "http://localhost:9999/f/explainlikeimfive/39322/eli5-sugar-free-drinks-contribute-to-obesity"),
    ("fruit_processed_sugar", "014-forum-eli5-fruit-processed-sugar.json", "conflicting fruit and processed-sugar discussion", "http://localhost:9999/f/explainlikeimfive/125175/eli5-why-sugar-in-fruits-is-good-for-you-but-processed-sugar"),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_highkey_offer_and_no_spike_claim",
        "node_type": "proposition",
        "subject": "frozen HighKey caramel-filled bar offer",
        "predicate": "shows_seller_price_aggregate_sweetener_and_no_spike_assertions",
        "object": "SKU B09QRTW2QH at 14.97 dollars with an 83-percent-of-100 aggregate over twelve reviews; seller copy names erythritol, allulose, and stevia and asserts zero added sugar, two net carbs, diabetic-friendly status, and no blood-sugar spike",
        "source_url": SEARCHES[0][3], "search_id": "highkey", "role": "product",
        "scope": "seller_copy_not_complete_current_label_independent_glucose_test_or_individual_clinical_fit",
        "quotes": [
            "In stock SKU B09QRTW2QH Rating: 83 % of 100 12 Reviews Add Your Review $14.97",
            "Our diabetic friendly Caramel Filled Bars contain 0g of added sugar and are made with natural sugar substitutes that won’t spike blood sugar levels.",
            "This healthy snack is made with wholesome alternative sweeteners like erythritol, allulose, and stevia with real cocoa butter and cream.",
            "These HighKey low carb snacks are made with only 2g of net carbs",
        ],
        "accepted": "The frozen HighKey seller page shows SKU B09QRTW2QH at 14.97 dollars with an 83-percent-of-100 aggregate over twelve reviews, names erythritol, allulose, and stevia, and makes zero-added-sugar, two-net-carb, diabetic-friendly, and no-blood-sugar-spike claims; it does not independently verify a complete current label, sweetener quantities, the exact food's glycemic response, digestive tolerance, or this recipient's clinical suitability.",
    },
    {
        "evidence_id": "prop_lilys_offer_stevia_no_added_sugar_claim",
        "node_type": "proposition",
        "subject": "frozen Lily's crispy-rice dark bar offer",
        "predicate": "shows_seller_price_format_stevia_and_net_carb_assertions",
        "object": "SKU B07J6V3XWP at 20 dollars for a nominal three-ounce four-pack whose title says 55-percent cocoa, stevia, no added sugar, low carb, and keto friendly; copy states five net carbs per serving",
        "source_url": SEARCHES[1][3], "search_id": "lilys", "role": "product",
        "scope": "seller_title_and_copy_not_complete_current_label_zero_glucose_result_or_individual_fit",
        "quotes": [
            "In stock SKU B07J6V3XWP Be the first to review this product $20.00",
            "Crispy Rice Dark Chocolate Bar by Lily's | Made with Stevia, No Added Sugar, Low-Carb, Keto Friendly | 55% Cocoa | Fair Trade, Gluten-Free & Non-GMO Ingredients | 3 ounce, 4-Pack",
            "Made with Stevia - Stevia is a zero calorie botanical sweetener.",
            "5 Net Carbs per Serving",
        ],
        "accepted": "The frozen Lily's seller page shows SKU B07J6V3XWP at 20 dollars for a nominal three-ounce four-pack, titles it as 55-percent cocoa, stevia-sweetened, no-added-sugar, low-carb and keto-friendly, and states five net carbs per serving; it supplies no independent exact-product glucose result, complete current label, sweetener quantity, digestive-tolerance result, or individualized clearance.",
    },
    {
        "evidence_id": "prop_choczero_offer_monk_fruit_no_polyol_claim",
        "node_type": "proposition",
        "subject": "frozen ChocZero dark peanut-butter cups offer",
        "predicate": "shows_seller_price_monk_fruit_no_sugar_alcohol_and_net_carb_assertions",
        "object": "SKU B08DHKKHR6 at 8.99 dollars for a two-bag option whose seller copy says one net carb per serving, no sugar alcohols or artificial sweeteners, and monk-fruit sweetening",
        "source_url": SEARCHES[2][3], "search_id": "choczero", "role": "product",
        "scope": "seller_assertions_not_complete_current_ingredient_quantities_taste_test_or_individual_outcome",
        "quotes": [
            "In stock SKU B08DHKKHR6 Be the first to review this product $8.99",
            "Our peanut butter cups contain NO SUGAR, NO SUGAR ALCOHOLS, and NO SUCRALOSE.",
            "That’s why all our products are sweetened by monk fruit.",
            "Low carb: only 1g net carb per serving!",
        ],
        "accepted": "The frozen ChocZero seller page shows SKU B08DHKKHR6 at 8.99 dollars for a two-bag option and asserts one net carb per serving, no sugar, sugar alcohols, sucralose, or artificial sweeteners, and monk-fruit sweetening; these are seller statements rather than a complete current ingredient-and-quantity audit, independent taste result, exact-product glucose test, or individualized tolerance finding.",
    },
    {
        "evidence_id": "prop_hershey_offer_zero_sugar_aspartame_free_claim",
        "node_type": "proposition",
        "subject": "frozen HERSHEY'S SPECIAL DARK zero-sugar offer",
        "predicate": "shows_seller_price_aggregate_package_and_zero_sugar_assertions",
        "object": "SKU B08MJLXH5N at 40.34 dollars for a 5.1-ounce pouch with an 88-percent-of-100 aggregate over twelve reviews and zero-sugar, aspartame-free, individually wrapped seller claims",
        "source_url": SEARCHES[3][3], "search_id": "hershey", "role": "product",
        "scope": "seller_copy_and_store_aggregate_not_current_ingredient_panel_replacement_sweetener_or_clinical_fit",
        "quotes": [
            "In stock SKU B08MJLXH5N Rating: 88 % of 100 12 Reviews Add Your Review $40.34",
            "Contains one (1) 5.1-ounce pouch of HERSHEY'S SPECIAL DARK Zero Sugar Chocolate Candy Bars",
            "Sugar-free, aspartame-free dark chocolate candy bars wrapped for lasting freshness and on-the-go snacking during any adventure",
        ],
        "accepted": "The frozen HERSHEY'S page shows SKU B08MJLXH5N at 40.34 dollars for a 5.1-ounce pouch with an 88-percent-of-100 aggregate over twelve reviews and seller wording that it is zero-sugar, aspartame-free, and individually wrapped; the frozen text does not identify a complete current ingredient panel or replacement-sweetener quantity and cannot establish taste, glucose impact, digestive tolerance, or clinical suitability.",
    },
    {
        "evidence_id": "prop_russell_stover_offer_stevia_sugar_free_claim",
        "node_type": "proposition",
        "subject": "frozen Russell Stover stevia dark offer",
        "predicate": "shows_seller_price_aggregate_package_and_stevia_assertions",
        "object": "SKU B01GD3DRXY at 25.68 dollars for a three-ounce bag with a 93-percent-of-100 aggregate over twelve reviews and sugar-free, dark-chocolate, stevia-extract, and individual-wrapper seller statements",
        "source_url": SEARCHES[4][3], "search_id": "russell_stover", "role": "product",
        "scope": "seller_copy_and_aggregate_not_complete_ingredient_panel_polyol_exclusion_taste_or_individual_fit",
        "quotes": [
            "In stock SKU B01GD3DRXY Rating: 93 % of 100 12 Reviews Add Your Review $25.68",
            "Each piece of Russell Stover Sugar Free dark chocolate medallion comes individually wrapped in a 3-ounce bag.",
            "This dark chocolate candy is made with stevia extract, delivering the taste and tradition you remember, without the sugar.",
        ],
        "accepted": "The frozen Russell Stover page shows SKU B01GD3DRXY at 25.68 dollars for a three-ounce bag with a 93-percent-of-100 aggregate over twelve reviews and says the individually wrapped sugar-free dark candy is made with stevia extract; the page does not provide a complete current ingredient panel, exclude unlisted bulking sweeteners, independently test taste, or establish individualized glucose or digestive suitability.",
    },
    {
        "evidence_id": "prop_sugar_substitute_category_and_outcome_uncertainty",
        "node_type": "proposition",
        "subject": "generic sugar-substitute classes and outcome evidence",
        "predicate": "distinguishes_compounds_and_reports_uncertain_long_term_outcomes",
        "object": "high-intensity sweeteners, monk fruit, stevia, allulose, and sugar alcohols are distinct categories or compounds; a cited review reports unclear HbA1c, body-weight, and adverse-event results with mainly very-low-certainty studies",
        "source_url": SEARCHES[5][3], "search_id": "sugar_substitute", "role": "concept",
        "scope": "generic_encyclopedia_summary_not_exact_product_composition_dose_outcome_or_patient_advice",
        "quotes": [
            "Common sugar substitutes include aspartame , monk fruit extract, saccharin , sucralose , stevia , acesulfame potassium (ace-K) and cyclamate .",
            "While it comes from the same family as other sugars, it does not substantially metabolize as sugar in the body.",
            "the results were unclear for effects on HbA1c, body weight and adverse events.",
            "The studies included were mainly of very low certainty",
        ],
        "accepted": "The generic sugar-substitute page distinguishes high-intensity sweeteners, monk fruit, stevia, allulose, and sugar alcohols and reports that one cited review found unclear HbA1c, body-weight, and adverse-event results in mainly very-low-certainty studies; it does not authenticate any captured product's current composition or dose or determine this recipient's outcome or care.",
    },
    {
        "evidence_id": "prop_sugar_alcohol_absorption_and_tolerance_scope",
        "node_type": "proposition",
        "subject": "generic sugar-alcohol absorption and gastrointestinal effects",
        "predicate": "describes_incomplete_absorption_compound_difference_and_amount_dependent_symptoms",
        "object": "many sugar alcohols are incompletely absorbed and generally change blood glucose less than sucrose, while erythritol is described as an exception and overconsumption may cause bloating, diarrhea, or flatulence with individual variability",
        "source_url": SEARCHES[6][3], "search_id": "sugar_alcohol", "role": "concept",
        "scope": "generic_class_summary_not_universal_threshold_exact_food_response_or_individual_clearance",
        "quotes": [
            "Sugar alcohols are usually incompletely absorbed into the blood stream from the small intestine which generally results in a smaller change in blood glucose than \"regular\" sugar (sucrose).",
            "As an exception, erythritol is actually absorbed in the small intestine and excreted unchanged through urine, so it contributes no calories even though it is rather sweet.",
            "overconsumption of sugar alcohols can lead to bloating , diarrhea and flatulence because they are not fully absorbed in the small intestine.",
            "Some individuals experience such symptoms even in a single-serving quantity.",
        ],
        "accepted": "The sugar-alcohol page says many polyols are incompletely absorbed and generally change blood glucose less than sucrose, describes erythritol as an absorption-and-excretion exception, and says overconsumption may produce bloating, diarrhea, or flatulence with some individual variability; it supplies no universal safe threshold, exact-product dose or response, or individualized clearance.",
    },
    {
        "evidence_id": "prop_maltitol_specific_metabolic_and_digestive_scope",
        "node_type": "proposition",
        "subject": "generic maltitol-specific properties",
        "predicate": "describes_nonzero_energy_lesser_glucose_effect_fermentation_and_laxative_effect",
        "object": "maltitol is a sugar alcohol with nonzero energy, a lesser rather than zero stated effect on blood glucose, gut-flora fermentation, and amount-dependent laxative effects reported on the page",
        "source_url": SEARCHES[7][3], "search_id": "maltitol", "role": "concept",
        "scope": "generic_compound_page_not_exact_product_ingredient_dose_universal_threshold_or_patient_advice",
        "quotes": [
            "Maltitol is a sugar alcohol (a polyol ) used as a sugar substitute and laxative .",
            "has a somewhat lesser effect on blood glucose .",
            "Maltitol provides between 2 and 3 kilocalories per gram [kcal/g]",
            "Maltitol is largely unaffected by human digestive enzymes and is fermented by gut flora",
            "Like other sugar alcohols (with the possible exception of erythritol ), maltitol has a laxative effect",
        ],
        "accepted": "The maltitol page identifies it as a sugar alcohol, says it has nonzero energy and a somewhat lesser rather than zero blood-glucose effect, is largely unaffected by digestive enzymes and fermented by gut flora, and can have amount-dependent laxative effects; it does not show that any exact captured product contains maltitol, establish its dose, set a universal patient threshold, or provide individualized advice.",
    },
    {
        "evidence_id": "prop_stevia_extract_taste_and_regulatory_scope",
        "node_type": "proposition",
        "subject": "generic stevia compound, taste, and extract distinction",
        "predicate": "describes_glycosides_zero_calories_aftertaste_and_high_purity_boundary",
        "object": "steviol glycosides are high-intensity compounds described as zero-calorie, some extracts can have bitter or licorice-like aftertaste, and high-purity glycosides are distinguished from leaves and crude extracts",
        "source_url": SEARCHES[8][3], "search_id": "stevia", "role": "concept",
        "scope": "generic_compound_and_regulatory_context_not_exact_product_mix_dose_taste_or_patient_outcome",
        "quotes": [
            "The active compounds in stevia are steviol glycosides (mainly stevioside and rebaudioside ).",
            "Humans cannot metabolize the glycosides in stevia, and it therefore has zero calories .",
            "at high concentrations some of its extracts may have an aftertaste described as licorice -like or bitter .",
            "extracts of certain high-purity steviol glycosides have been Generally Recognized As Safe (GRAS) and may be lawfully marketed and added to food products, but stevia leaf and crude extracts do not have GRAS or Food and Drug Administration (FDA) approval for use in food.",
        ],
        "accepted": "The stevia page identifies steviol glycosides, describes them as zero-calorie, notes possible bitter or licorice-like aftertaste at high concentrations, and distinguishes high-purity glycosides from leaves and crude extracts; it does not authenticate an exact chocolate's mixture or dose, predict its taste or glucose effect, or determine individualized suitability.",
    },
    {
        "evidence_id": "prop_glycemic_index_population_and_variability_boundary",
        "node_type": "proposition",
        "subject": "glycemic-index interpretation",
        "predicate": "is_population_average_not_individual_prediction_and_depends_on_amount_and_matrix",
        "object": "GI compares defined available-carbohydrate responses averaged across studied subjects, does not predict an individual's response, and must be interpreted with serving quantity, food composition, and substantial within- and between-person variability",
        "source_url": SEARCHES[9][3], "search_id": "glycemic_index", "role": "concept",
        "scope": "generic_measurement_boundary_not_exact_product_gi_or_recipient_prediction",
        "quotes": [
            "Glycemic index does not predict an individual's glycemic response to a food, but can be used as a tool to assess the insulin response burden of a food, averaged across a studied population.",
            "Individual responses vary greatly.",
            "More importantly, the glycemic response is different from one person to another, and also in the same person from day to day, depending on blood glucose levels, insulin resistance , and other factors.",
            "Depending on quantities, the number of grams of carbohydrate in a food can have a bigger impact on blood sugar levels than the glycemic index does.",
        ],
        "accepted": "The glycemic-index page says GI is a population-average tool rather than an individual prediction, actual responses vary between people and within a person from day to day, and carbohydrate quantity can matter more than GI; it gives no tested GI for the five exact foods and cannot predict this recipient's response.",
    },
    {
        "evidence_id": "prop_friends_diarrhea_confounded_anecdote_scope",
        "node_type": "proposition",
        "subject": "one diet-ice-cream digestive anecdote",
        "predicate": "reports_symptoms_after_a_multi_ingredient_drink_and_guesses_a_sweetener_role",
        "object": "an author reports two friends developed cramps, nausea, sweating, or diarrhea after drinks containing diet vanilla ice cream, coffee, chocolate syrup, and milk, then speculates about an unidentified sweetener",
        "source_url": SEARCHES[10][3], "search_id": "friends_diarrhea", "role": "community",
        "scope": "individual_confounded_recollection_not_identified_dose_causality_incidence_or_exact_product_evidence",
        "quotes": [
            "The way I make it is by mixing iced coffee with chocolate syrup and vanilla ice cream.",
            "My friends quickly drank their frapuccionos and a few minutes in, they started feeling, well... \"off\".",
            "Guys, I used diet vanilla ice cream. The type that has the sweetener found in sugar-free gummies- the kind that is borderline a laxative, which probably got worse combined with the coffee, chocolate, and milk.",
        ],
        "accepted": "One author reports two friends developed symptoms after drinks combining diet vanilla ice cream, coffee, chocolate syrup, and milk and speculates that an unidentified sweetener was involved; the account has multiple confounders and no verified ingredient, dose, diagnosis, comparator, incidence estimate, or link to any captured product.",
    },
    {
        "evidence_id": "prop_werther_extreme_intake_anecdote_scope",
        "node_type": "proposition",
        "subject": "one extreme sugar-free candy intake anecdote",
        "predicate": "reports_severe_symptoms_after_nearly_thirty_candies_and_self_reported_isomalt_amount",
        "object": "an author reports eating nearly thirty sugar-free Werther candies, later reading a laxative-effect warning, self-calculating about eighty grams of isomalt, and experiencing prolonged gastrointestinal symptoms",
        "source_url": SEARCHES[11][3], "search_id": "werther_pack", "role": "community",
        "scope": "individual_extreme_intake_self_report_not_normal_serving_trial_incidence_or_exact_product_evidence",
        "quotes": [
            "one candy turned into 5 which turned into 10 and before I knew it, I ate almost 30 of them.",
            "It read; \" Excessive consumption may produce laxative effects. \"",
            "I did some calculations and realized I ate almost 80 grams of the natural laxative present in the candy, ISOMALT.",
            "TLDR: I foolishly ate an entire bag of sugar-free candy and with it was around 80 grams of a natural laxative and now I'm paying the price.",
        ],
        "accepted": "One author reports eating nearly thirty sugar-free Werther candies, reading an excessive-consumption laxative warning, self-calculating about eighty grams of isomalt, and experiencing prolonged gastrointestinal symptoms; this extreme self-report is not a normal-serving trial, verified clinical record, incidence estimate, or evidence about any of the five captured products.",
    },
    {
        "evidence_id": "prop_sugar_free_drinks_conflicting_discussion_scope",
        "node_type": "proposition",
        "subject": "one sugar-free drink community discussion",
        "predicate": "contains_conflicting_speculation_and_calls_for_more_data",
        "object": "participants offer conflicting appetite, calorie, microbiome, migraine, weight, and no-harm claims and explicitly describe uncertainty and ongoing research",
        "source_url": SEARCHES[12][3], "search_id": "sugar_free_drinks", "role": "community",
        "scope": "uncontrolled_comments_about_drinks_not_authoritative_causal_evidence_or_exact_candy_result",
        "quotes": [
            "There are a lot of conflicting studies, many of which have their own flaws.",
            "It's possible that it's all bad data and that artificial sweeteners do nothing at all. We just don't know. We need more data on the subject.",
            "It depends on what specific sweetener you are referring to, and what you mean by \"bad for us\" or \"contribute to obesity\"",
        ],
        "accepted": "One ELI5 discussion contains conflicting claims and speculation about sugar-free drinks, appetite, calories, microbiome, migraine, and weight and says more data are needed; uncontrolled comments about drinks are not medical authority, causal evidence, or an exact-product result for any captured candy.",
    },
    {
        "evidence_id": "prop_fruit_processed_sugar_conflicting_discussion_scope",
        "node_type": "proposition",
        "subject": "one fruit versus processed-sugar community discussion",
        "predicate": "contains_conflicting_amount_fiber_matrix_and_sugar_claims",
        "object": "participants disagree about the premise, serving amounts, fruit varieties, fiber, food matrix, absorption, and whether different sugars are equivalent",
        "source_url": SEARCHES[13][3], "search_id": "fruit_processed_sugar", "role": "community",
        "scope": "uncontrolled_general_discussion_not_exact_chocolate_test_medical_guidance_or_individual_prediction",
        "quotes": [
            "The sugar in fruits isn't \"good for you\". It's just sugar.",
            "There are very different nutrition numbers between types of apples.",
            "Sugar is sugar, regardless of processing (for example, if you have diabetes, you might be able to eat a piece of chocolate but not an apple, depending on the sugar content of both).",
            "It’s all about quantity of sugar mostly",
        ],
        "accepted": "One ELI5 discussion contains conflicting statements about its premise, serving amounts, fruit variety, fiber, food matrix, absorption, and sugar equivalence; the uncontrolled comments are not an exact-chocolate comparison, medical guidance, or an individualized prediction.",
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
            "registry_id": "reg_case_spec_sugar_free_fit_0045",
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
            "bridge_exact_offer_claim_disclosure_matrix",
            "bridge",
            "five frozen sugar-free chocolate and candy offers",
            "binds_literal_claims_to_exact_offer_fields_and_unknowns",
            "record exact SKU, variant, price, aggregate, package, serving, literal sugar and health wording, named sweeteners and visible carbohydrate fields while preserving every missing current ingredient, quantity, label, and individualized outcome field",
            "exact_offer_claim_disclosure_matrix_v1",
        ),
        (
            "bridge_marketing_claim_non_equivalence",
            "bridge",
            "sugar-free zero-sugar no-added-sugar net-carb keto and diabetic-friendly language",
            "separates_non_equivalent_marketing_and_measurement_claims",
            "keep each literal claim at its exact source, variant, serving, and denominator and reject any inference that one front-label phrase proves another claim or a recipient-specific glucose result",
            "marketing_claims_are_not_synonyms_v1",
        ),
        (
            "bridge_sweetener_identity_and_dose_binding",
            "bridge",
            "high-intensity sweeteners allulose sugar alcohols maltitol stevia and monk fruit",
            "requires_exact_current_ingredient_and_amount_binding_before_comparison",
            "distinguish compounds and mixtures, resolve the complete current label and serving quantities, and do not infer unlisted bulking agents or rank an unknown blend as universally gentler",
            "sweetener_identity_and_dose_binding_v1",
        ),
        (
            "bridge_glycemic_and_individual_response_boundary",
            "bridge",
            "generic metabolic descriptions and glycemic index",
            "rejects_zero_impact_and_individual_prediction_shortcuts",
            "treat generic metabolism and population-average glycemic evidence as context only, preserve serving, matrix, medication and individual variability, and require individualized clinical compatibility rather than predicting zero impact",
            "glycemic_evidence_and_individual_response_boundary_v1",
        ),
        (
            "bridge_digestive_and_community_scope",
            "bridge",
            "generic digestive mechanisms and four community discussions",
            "retains_compound_amount_confounded_anecdote_and_question_scope",
            "use generic polyol mechanisms and individual stories only to identify label, portion, warning and stop-rule checks, never as incidence, universal thresholds, causality, exact-product outcomes, or medical authority",
            "digestive_tolerance_scope_v1",
        ),
        (
            "bridge_taste_evidence_and_small_trial_boundary",
            "bridge",
            "seller taste copy store aggregates and community comments",
            "requires_post_clearance_recipient_specific_reversible_tasting",
            "do not rank taste from seller copy, aggregates, or uncontrolled comments; after exact-label verification and clinical clearance use the smallest one-product-at-a-time trial with predeclared taste and stop rules",
            "taste_and_community_evidence_boundary_v1",
        ),
        (
            "bridge_clinician_first_new_diagnosis_gate",
            "bridge",
            "newly diagnosed intended recipient and exact edible gift",
            "requires_permission_and_individual_professional_compatibility_review_before_consumption",
            "obtain recipient permission and clinician, registered-dietitian, or pharmacist review of the exact current label, portion, medications, allergies, gastrointestinal history, and plan; avoid diagnosis, prescribing, medication changes, generic safe doses, and self-testing as a substitute",
            "clinician_first_new_diagnosis_gate_v1",
        ),
        (
            "decision_evidence_bounded_sugar_free_gift",
            "decision",
            "sugar-free or no-added-sugar gift decision",
            "selects_only_a_verified_individually_cleared_small_trial_or_nonfood_defer_path",
            "after exact-label verification and individualized professional clearance, choose the lowest-total-cost smallest eligible trial that passes ingredient, portion, allergy, delivery, taste, and stop-rule gates; otherwise send a nonfood gift or defer",
            "evidence_bounded_sugar_free_gift_decision_v1",
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
        "bridge_exact_offer_claim_disclosure_matrix": [
            "prop_highkey_offer_and_no_spike_claim",
            "prop_lilys_offer_stevia_no_added_sugar_claim",
            "prop_choczero_offer_monk_fruit_no_polyol_claim",
            "prop_hershey_offer_zero_sugar_aspartame_free_claim",
            "prop_russell_stover_offer_stevia_sugar_free_claim",
        ],
        "bridge_marketing_claim_non_equivalence": [
            "prop_highkey_offer_and_no_spike_claim",
            "prop_lilys_offer_stevia_no_added_sugar_claim",
            "prop_choczero_offer_monk_fruit_no_polyol_claim",
            "prop_hershey_offer_zero_sugar_aspartame_free_claim",
            "prop_russell_stover_offer_stevia_sugar_free_claim",
            "prop_sugar_substitute_category_and_outcome_uncertainty",
        ],
        "bridge_sweetener_identity_and_dose_binding": [
            "bridge_exact_offer_claim_disclosure_matrix",
            "prop_sugar_substitute_category_and_outcome_uncertainty",
            "prop_sugar_alcohol_absorption_and_tolerance_scope",
            "prop_maltitol_specific_metabolic_and_digestive_scope",
            "prop_stevia_extract_taste_and_regulatory_scope",
        ],
        "bridge_glycemic_and_individual_response_boundary": [
            "bridge_marketing_claim_non_equivalence",
            "bridge_sweetener_identity_and_dose_binding",
            "prop_sugar_alcohol_absorption_and_tolerance_scope",
            "prop_maltitol_specific_metabolic_and_digestive_scope",
            "prop_stevia_extract_taste_and_regulatory_scope",
            "prop_glycemic_index_population_and_variability_boundary",
        ],
        "bridge_digestive_and_community_scope": [
            "prop_sugar_alcohol_absorption_and_tolerance_scope",
            "prop_maltitol_specific_metabolic_and_digestive_scope",
            "prop_friends_diarrhea_confounded_anecdote_scope",
            "prop_werther_extreme_intake_anecdote_scope",
            "prop_sugar_free_drinks_conflicting_discussion_scope",
            "prop_fruit_processed_sugar_conflicting_discussion_scope",
        ],
        "bridge_taste_evidence_and_small_trial_boundary": [
            "bridge_exact_offer_claim_disclosure_matrix",
            "prop_stevia_extract_taste_and_regulatory_scope",
            "prop_friends_diarrhea_confounded_anecdote_scope",
            "prop_werther_extreme_intake_anecdote_scope",
            "prop_sugar_free_drinks_conflicting_discussion_scope",
            "prop_fruit_processed_sugar_conflicting_discussion_scope",
        ],
        "bridge_clinician_first_new_diagnosis_gate": [
            "bridge_exact_offer_claim_disclosure_matrix",
            "bridge_marketing_claim_non_equivalence",
            "bridge_sweetener_identity_and_dose_binding",
            "bridge_glycemic_and_individual_response_boundary",
            "bridge_digestive_and_community_scope",
            "bridge_taste_evidence_and_small_trial_boundary",
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
                "source_id": "decision_evidence_bounded_sugar_free_gift",
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
