#!/usr/bin/env python3
"""Build the frozen Q39 wellness-packaging claim-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-coffee-tea-0039-wellness-packaging-claims-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0039/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-coffee-tea-0039-wellness-packaging-claims-20260716-r1"
RUN_ID = "v3-corpus-formal-coffee-tea-0039-wellness-packaging-claims-20260716-r1"
TASK_ID = "dra_v3_formal_coffee_tea_0039"
TOPIC = "coffee_tea_wellness_packaging_claim_boundary"


SEARCHES = [
    (
        "lakanto_matcha",
        "001-shopping-lakanto-detox-antioxidant-matcha.json",
        "Lakanto detox, destress, and antioxidant matcha seller claim",
        "http://localhost:7770/lakanto-sugar-free-matcha-latte-green-tea-powder-shelf-stable-probiotics-and-fiber-sugar-free-monkfruit-sweetener-keto-diet-friendly-vegan-detox-and-destress-antioxidants-authentic-10-oz.html",
    ),
    (
        "tealyra_blood_cleanser",
        "002-shopping-tealyra-blood-cleanser-detox-tea.json",
        "Tealyra blood-cleanser detox-tea seller claim",
        "http://localhost:7770/tealyra-blood-cleanser-tea-wellness-detox-health-tonic-dandelion-ginger-loose-leaf-herbal-tea-natural-cleanse-diuretic-tea-caffeine-free-112g-4-ounce.html",
    ),
    (
        "lifeboost_low_acid",
        "003-shopping-lifeboost-low-acid-coffee.json",
        "Lifeboost low-acid coffee seller claim",
        "http://localhost:7770/lifeboost-coffee-ground-medium-roast-coffee-low-acid-single-origin-usda-organic-coffee-non-gmo-ground-coffee-third-party-tested-for-mycotoxins-pesticides-12-ounces.html",
    ),
    (
        "la_republica_mushroom",
        "004-shopping-la-republica-mushroom-coffee-focus-jitters.json",
        "La Republica mushroom coffee focus and no-jitters seller claims",
        "http://localhost:7770/la-republica-organic-mushroom-coffee-30-servings-with-7-superfood-mushrooms-great-tasting-arabica-instant-coffee-includes-lion-s-mane-reishi-chaga-cordyceps-shiitake-maitake-and-turkey-tail.html",
    ),
    (
        "detox_concept",
        "005-wiki-detoxification-alternative-medicine.json",
        "alternative-medicine detoxification evidence boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Detoxification_(alternative_medicine)",
    ),
    (
        "antioxidant_concept",
        "006-wiki-antioxidant-evidence-boundary.json",
        "antioxidant in-vitro and health-outcome boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Antioxidant",
    ),
    (
        "caffeine_concept",
        "007-wiki-caffeine-effects-boundary.json",
        "caffeine dose, alertness, sleep, and anxiety boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Caffeine",
    ),
    (
        "low_acid_concept",
        "008-wiki-low-acid-coffee-definition.json",
        "low-acid coffee definition and label-measurement boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Low-acid_coffee",
    ),
    (
        "medicinal_fungi_concept",
        "009-wiki-medicinal-fungi-boundary.json",
        "fungal drug-development and supplement-evidence boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Medicinal_uses_of_fungi",
    ),
    (
        "black_tea_anxiety",
        "010-forum-black-tea-anxiety-anecdote.json",
        "one black-tea anxiety experience",
        "http://localhost:9999/f/tifu/135314/tifu-by-drinking-black-tea",
    ),
    (
        "starbucks_sleep",
        "011-forum-starbucks-coffee-sleep-anecdote.json",
        "one late-coffee sleep experience",
        "http://localhost:9999/f/tifu/93355/tifu-by-drinking-one-starbucks-coffee-and-now-i-have-an-exam",
    ),
    (
        "energy_kick_question",
        "012-forum-energy-drink-kick-question.json",
        "one energy-drink versus coffee and tea question",
        "http://localhost:9999/f/explainlikeimfive/125265/eli5-what-s-in-energy-drinks-that-provides-the-kick-that-one",
    ),
    (
        "tea_caffeine_question",
        "013-forum-black-green-tea-caffeine-question.json",
        "one black-versus-green-tea caffeine question",
        "http://localhost:9999/f/askscience/37578/how-does-black-tea-have-more-caffeine-than-green-tea-when",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_lakanto_matcha_claim_snapshot",
        "subject": "frozen Lakanto matcha seller page",
        "predicate": "markets_detox_antioxidant_and_performance_language",
        "object": "detox and destress, antioxidants, probiotics, L-theanine, metabolism, and endurance language on a 9.95-dollar unreviewed offer",
        "source_url": SEARCHES[0][3],
        "search_id": "lakanto_matcha",
        "role": "product",
        "scope": "seller_copy_not_ingredient_assay_detox_measurement_or_health_outcome",
        "quotes": [
            "In stock SKU B01G4I8VUM Be the first to review this product $9.95 Qty Add to Cart Add to Wish List Add to Compare",
            "Detox and Destress Naturally: Lakanto’s Japanese green tea powder is high in antioxidants, probiotics, and L-Thanine to help increase your metabolism and endurance.",
        ],
        "accepted": "The frozen Lakanto page shows an in-stock SKU B01G4I8VUM offer at 9.95 dollars with no posted review and seller copy saying detox and destress, antioxidants, probiotics, L-theanine, metabolism, and endurance; it supplies no independent ingredient assay, named-toxin measurement, clinical comparator, or verified health outcome.",
    },
    {
        "evidence_id": "prop_tealyra_blood_cleanser_claim_snapshot",
        "subject": "frozen Tealyra blood-cleanser tea seller page",
        "predicate": "markets_blood_cleaning_detox_and_elimination_language",
        "object": "blood cleansing, kidney filtering, liver toxin elimination, and diuretic claims on a 13.97-dollar offer rated 98 percent over ten reviews",
        "source_url": SEARCHES[1][3],
        "search_id": "tealyra_blood_cleanser",
        "role": "product",
        "scope": "seller_copy_and_store_aggregate_not_toxin_identity_clearance_or_clinical_efficacy",
        "quotes": [
            "In stock SKU B075H4G4T6 Rating: 98 % of 100 10 Reviews Add Your Review $13.97 Size 4 Ounce (Pack of 1) 8 Ounce / 224g Qty Add to Cart Add to Wish List Add to Compare",
            "It cleanses the blood by increasing the effectiveness of each of the body's natural elimination systems.",
            "Its diuretic properties effectively help the kidneys filter impurities from the blood.",
            "Dandelion is included for its diuretic properties, helping the body to naturally pass unhealthy toxins built up in the liver.",
        ],
        "accepted": "The frozen Tealyra page shows SKU B075H4G4T6 at 13.97 dollars with a 98-percent-of-100 aggregate over ten reviews and seller claims about blood cleansing, kidney filtering, diuresis, and liver toxins; neither the store aggregate nor the copy identifies and measures a toxin, clearance change, validated endpoint, comparator, or clinical benefit.",
    },
    {
        "evidence_id": "prop_lifeboost_low_acid_claim_snapshot",
        "subject": "frozen Lifeboost low-acid coffee seller page",
        "predicate": "markets_ph_and_stomach_or_teeth_tolerance_language",
        "object": "pH 6 or higher, third-party testing, and gentle-on-stomach-and-teeth claims on a 27.95-dollar unreviewed offer",
        "source_url": SEARCHES[2][3],
        "search_id": "lifeboost_low_acid",
        "role": "product",
        "scope": "seller_measurement_statement_not_independent_lot_assay_or_symptom_guarantee",
        "quotes": [
            "In stock SKU B0899ZYXXN Be the first to review this product $27.95 Flavor Name Dark Roast Half Caff Light Roast Medium Decaf Medium Roast Size Ground Coffee Whole Bean Qty Add to Cart Add to Wish List Add to Compare",
            "When you make the switch to Lifeboost Coffee, you'll enjoy a fresh, flavorful cup that's very gentle on your stomach and teeth.",
            "Most popular coffee has a pH level of 4.85 or lower (very acidic). Lifeboost's pH level is 6 or higher, which is why customers who thought they could never drink coffee again love our brand.",
        ],
        "accepted": "The frozen Lifeboost seller page shows SKU B0899ZYXXN at 27.95 dollars with no posted review and claims that its pH is 6 or higher and that the drink is gentle on stomach and teeth; it does not provide an independent lot-and-brew assay, test protocol, clinical comparator, or a guarantee for reflux, gastritis, ulcers, nausea, or dental outcomes.",
    },
    {
        "evidence_id": "prop_la_republica_mushroom_claim_snapshot",
        "subject": "frozen La Republica mushroom-coffee seller page",
        "predicate": "markets_focus_clean_energy_no_jitters_and_multi_system_benefits",
        "object": "seven named mushrooms plus focus, clean energy, no-jitters, antioxidant, immune, liver, stomach, and inflammation language on a 24-dollar unreviewed offer",
        "source_url": SEARCHES[3][3],
        "search_id": "la_republica_mushroom",
        "role": "product",
        "scope": "seller_ingredient_and_outcome_copy_not_dose_quality_or_product_specific_efficacy",
        "quotes": [
            "In stock SKU B078XR2R6B Be the first to review this product $24.00 Flavor Name Caffeinated Decaffeinated Size 2.12 Ounce (Pack of 1) 8.48 Ounce (Pack of 1) Qty Add to Cart Add to Wish List Add to Compare",
            "Your energy levels will be raised to new heights without jitters or shakes.",
            "After one cup, you will have the focus of a meditating Buddhist monk. We’re talking about clean and calm energy that will power you throughout the day.",
            "Enjoy all of the upsides of coffee without the downside of jitters, courtesy of cordyceps.",
        ],
        "accepted": "The frozen La Republica page shows SKU B078XR2R6B at 24 dollars with no posted review, names seven mushrooms, and uses focus, clean-energy, and no-jitters language; the page does not independently establish extract identity, per-serving active dose, quality, interactions, comparator, or product-specific cognitive, immune, liver, stomach, inflammation, antioxidant, crash, or jitter outcomes.",
    },
    {
        "evidence_id": "prop_detox_concept_boundary",
        "subject": "alternative-medicine detoxification claims",
        "predicate": "lack_named_toxins_and_supporting_evidence",
        "object": "a distinction from ordinary liver and kidney detoxification plus criticism of undefined toxins and unsupported commercial claims",
        "source_url": SEARCHES[4][3],
        "search_id": "detox_concept",
        "role": "concept",
        "scope": "generic_evidence_boundary_not_medical_diagnosis_or_product_trial",
        "quotes": [
            "It is not to be confused with detoxification carried out by the liver and kidneys , which filter the blood and remove harmful substances to be processed and eliminated from the body.",
            "Scientists and health organizations have criticized the concept of detoxification for its unsound scientific basis and for the lack of evidence for claims made.",
            "The \"toxins\" usually remain undefined, with little to no evidence of toxic accumulation in the patient.",
        ],
        "accepted": "The detoxification concept page distinguishes alternative body-cleansing claims from ordinary liver and kidney filtering, says scientists and health organizations criticize the lack of evidence, and notes that toxins usually remain undefined with little to no evidence of accumulation; it does not diagnose this drinker or independently test either exact tea.",
    },
    {
        "evidence_id": "prop_antioxidant_outcome_boundary",
        "subject": "antioxidant activity and dietary health claims",
        "predicate": "separates_in_vitro_properties_from_in_vivo_outcomes",
        "object": "little evidence for some in-vivo properties and no demonstrated human health maintenance or disease prevention from antioxidant supplements",
        "source_url": SEARCHES[5][3],
        "search_id": "antioxidant_concept",
        "role": "concept",
        "scope": "general_activity_to_outcome_boundary_not_exact_product_assay",
        "quotes": [
            "Dietary antioxidants are vitamins A , C , and E , but the term has also been applied to various compounds that exhibit antioxidant properties in vitro , having little evidence for antioxidant properties in vivo .",
            "Dietary supplements marketed as antioxidants have not been shown to maintain health or prevent disease in humans.",
        ],
        "accepted": "The antioxidant concept page says compounds may exhibit antioxidant properties in vitro while having little evidence for in-vivo properties, and that supplements marketed as antioxidants have not been shown to maintain health or prevent disease in humans; this supplies no assay, dose, bioavailability, or outcome evidence for the exact matcha or mushroom coffee.",
    },
    {
        "evidence_id": "prop_caffeine_response_boundary",
        "subject": "caffeine alertness and adverse effects",
        "predicate": "vary_with_dose_timing_tolerance_and_person",
        "object": "dose-dependent alertness alongside variable sleep disruption, anxiety, jitteriness, insomnia, and sleep latency",
        "source_url": SEARCHES[6][3],
        "search_id": "caffeine_concept",
        "role": "concept",
        "scope": "general_caffeine_effects_not_exact_serving_or_person_specific_prediction",
        "quotes": [
            "Caffeine in a dose dependent manner increases alertness in both fatigued and normal individuals.",
            "Some people experience sleep disruption or anxiety if they consume caffeine, [ 28 ] [ 29 ] [ 30 ] but others show little disturbance.",
            "Minor undesired symptoms from caffeine ingestion not sufficiently severe to warrant a psychiatric diagnosis are common and include mild anxiety, jitteriness, insomnia, increased sleep latency, and reduced coordination.",
        ],
        "accepted": "The caffeine concept page describes dose-dependent alertness and says some people experience sleep disruption or anxiety while others show little disturbance, with anxiety, jitteriness, insomnia, and increased sleep latency among common minor undesired effects; it does not measure an exact prepared serving or predict this drinker's response.",
    },
    {
        "evidence_id": "prop_low_acid_measurement_boundary",
        "subject": "low-acid coffee labels",
        "predicate": "require_recipe_specific_measurement",
        "object": "a pH or relative-acid definition, brew-factor sensitivity, and evidence that most tested labeled products remained in the regular-coffee range",
        "source_url": SEARCHES[7][3],
        "search_id": "low_acid_concept",
        "role": "concept",
        "scope": "definition_and_label_audit_not_symptom_treatment_guarantee",
        "quotes": [
            "Low acid coffee is any coffee above the critical pH level of 5.5 or has at least 50% less acid than regular coffee without any additives or treatments.",
            "The researchers found that the pH values ranged from 4.97 to 5.72, with only one sample having a significantly higher pH (5.72) compared to the others and exceeding the critical pH threshold of 5.5 for beverages.",
            "The study found that nearly all tested coffees had high acidity despite labeling claims.",
        ],
        "accepted": "The low-acid concept page gives a pH-above-5.5 or relative-acid definition and reports that only one of eleven tested labeled products exceeded pH 5.5 while nearly all remained highly acidic despite label claims; it does not assay the exact Lifeboost lot and recipe or guarantee a stomach, reflux, nausea, or dental outcome.",
    },
    {
        "evidence_id": "prop_medicinal_fungi_supplement_boundary",
        "subject": "fungal metabolites and mushroom supplements",
        "predicate": "distinguishes_drug_development_from_supplement_claims",
        "object": "successful fungal drug development alongside insufficient safety and effectiveness evidence and variable processing for mushroom supplements",
        "source_url": SEARCHES[8][3],
        "search_id": "medicinal_fungi_concept",
        "role": "concept",
        "scope": "general_fungi_boundary_not_exact_mushroom_coffee_efficacy",
        "quotes": [
            "Some species are included in traditional medicine , but lack evidence as to any health benefit .",
            "Similarly, mushroom dietary supplements , commonly made from powdered or extracted fruit bodies or mycelium , are marketed for various health benefits but lack sufficient scientific evidence for their safety or effectiveness, and their quality can vary due to inconsistent processing and labeling.",
        ],
        "accepted": "The medicinal-fungi page distinguishes fungal compounds developed into drugs from traditional species and dietary supplements, and says mushroom supplements lack sufficient safety or effectiveness evidence while quality can vary with processing and labeling; it does not validate the exact seven-mushroom coffee, doses, or claimed outcomes.",
    },
    {
        "evidence_id": "prop_black_tea_anxiety_anecdote_scope",
        "subject": "one black-tea community author",
        "predicate": "reports_anxiety_after_a_long_steep",
        "object": "self-described slow caffeine metabolism and anxiety after leaving a black-tea bag in the drink",
        "source_url": SEARCHES[9][3],
        "search_id": "black_tea_anxiety",
        "role": "community",
        "scope": "single_self_report_not_diagnosis_dose_prevalence_or_product_validation",
        "quotes": [
            "In a college molecular biology class I learned I was a “slow caffeine metabolizer”.",
            "I am now one giant ball of anxiety thanks to my poor ability to metabolize caffeine.",
            "TL;DR drank black tea that I steeped too long as a slow caffeine metabolizer, now am an anxious mess for the last hour of the work day.",
        ],
        "accepted": "One community author self-identifies as a slow caffeine metabolizer and reports anxiety after leaving a black-tea bag in the drink; the page is an individual uncontrolled report without measured caffeine dose, diagnostic confirmation, prevalence, or evidence about any of the four exact products.",
    },
    {
        "evidence_id": "prop_starbucks_sleep_anecdote_scope",
        "subject": "one infrequent coffee drinker",
        "predicate": "reports_overnight_wakefulness_after_a_late_americano",
        "object": "a venti Americano around 3 PM followed by an inability to fall asleep before an exam",
        "source_url": SEARCHES[10][3],
        "search_id": "starbucks_sleep",
        "role": "community",
        "scope": "single_self_report_with_timing_and_stress_confounds_not_product_comparison",
        "quotes": [
            "So I don’t normally drink a lot of coffee. But today I decided to just get a venti americano from Starbucks at only around 3pm.",
            "And I am not exaggerating when I say that I was simply awake the whole night.",
            "Tl;DR I drank one venti Starbucks coffee and that prevented me from sleeping at all in the night prior to having an exam.",
        ],
        "accepted": "One infrequent coffee drinker reports a venti Americano around 3 PM and overnight wakefulness before an exam; this uncontrolled account includes timing, serving-size, exercise, and stress confounds and does not establish dose, prevalence, or the energy and jitter outcome of an exact captured product.",
    },
    {
        "evidence_id": "prop_energy_kick_question_scope",
        "subject": "one energy-drink community question",
        "predicate": "asks_what_differs_from_coffee_or_tea",
        "object": "a no-sugar-drink question mentioning no more than 200 mg caffeine per can",
        "source_url": SEARCHES[11][3],
        "search_id": "energy_kick_question",
        "role": "community",
        "scope": "question_not_composition_assay_mechanism_or_outcome_evidence",
        "quotes": [
            "ELI5: What's in energy drinks that provides the \"kick\" that one otherwise doesn't get from coffee, tea, etc?",
            "Should mention that I drink only no sugar drinks, so it can't be that, and a single can of what I have is usually no more than 200MG of caffeine",
        ],
        "accepted": "One community author asks what produces an energy-drink kick beyond coffee or tea and mentions no-sugar drinks with no more than 200 mg caffeine per can; a question is not a composition assay, causal comparison, product-specific mechanism, or evidence for clean energy, focus, crash, or no jitters.",
    },
    {
        "evidence_id": "prop_tea_caffeine_question_scope",
        "subject": "one black-versus-green-tea community question",
        "predicate": "asks_whether_processing_changes_caffeine",
        "object": "a question about oxidation, taste, color, and caffeine in teas from the same plant",
        "source_url": SEARCHES[12][3],
        "search_id": "tea_caffeine_question",
        "role": "community",
        "scope": "question_not_serving_assay_or_general_tea_caffeine_ranking",
        "quotes": [
            "How does black tea have more caffeine than green tea, when they come from the same plant?",
            "I know that oxidation plays a role to make it taste and look different. But does that play into the caffeine content too?",
        ],
        "accepted": "One community author asks whether oxidation explains an assumed black-versus-green-tea caffeine difference; the question does not measure leaf mass, preparation, serving caffeine, or establish a general ranking, much less validate the captured matcha's energy or wellness claims.",
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
            "registry_id": "reg_case_spec_wellness_claims_0039",
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
            "bridge_seller_claim_status",
            "bridge",
            "wellness language on four seller pages",
            "remains_marketing_until_independently_substantiated",
            "record exact copy and offers without treating ingredients, testing language, ratings, or reviews as independent product-specific outcome proof",
            "seller_claim_not_independent_outcome_v1",
        ),
        (
            "bridge_named_detox_endpoint",
            "bridge",
            "detox and blood-cleanser claims",
            "require_named_exposure_measurement_and_endpoint",
            "distinguish ordinary liver and kidney physiology from undefined toxins and require a named substance, exposure, before-and-after measurement, comparator, endpoint, and safety evidence",
            "named_detox_endpoint_boundary_v1",
        ),
        (
            "bridge_antioxidant_activity_outcome",
            "bridge",
            "antioxidant language",
            "separates_activity_from_human_outcomes",
            "do not convert ingredient presence or in-vitro antioxidant activity into health maintenance or disease-prevention claims without dose, bioavailability, comparator, and applicable outcomes",
            "antioxidant_activity_not_health_outcome_v1",
        ),
        (
            "bridge_caffeine_dose_person",
            "bridge",
            "energy focus crash and jitter claims",
            "require_serving_dose_timing_and_person_specific_trial",
            "measure prepared-serving caffeine and other actives and bind response to timing, frequency, tolerance, sleep window, co-exposures, and repeatable individual observations",
            "caffeine_dose_timing_and_person_boundary_v1",
        ),
        (
            "bridge_low_acid_measurement_symptom",
            "bridge",
            "low-acid and gentle-on-stomach claims",
            "requires_independent_recipe_specific_ph_and_separate_symptom_evidence",
            "verify the exact lot and brew pH under disclosed conditions while keeping reflux, gastritis, nausea, and dental tolerance as separate person-specific outcomes",
            "low_acid_measurement_not_symptom_guarantee_v1",
        ),
        (
            "bridge_fungal_drug_product_scope",
            "bridge",
            "seven-mushroom coffee claims",
            "separates_fungal_drug_history_from_supplement_efficacy",
            "require exact extract identity, dose, purity, quality, interactions, comparator, and product-specific outcomes rather than transferring drug development or ingredient names to the beverage",
            "fungal_drug_history_not_mushroom_coffee_efficacy_v1",
        ),
        (
            "bridge_community_scope",
            "bridge",
            "four community pages about caffeine",
            "retain_individual_question_and_experience_scope",
            "use the pages to identify preparation, dose, timing, tolerance, sleep, and person variables without treating them as prevalence, diagnosis, composition, causality, or product validation",
            "community_anecdote_and_question_scope_v1",
        ),
        (
            "decision_evidence_bounded_wellness_claim_choice",
            "decision",
            "wellness-claim premium for daily tea or coffee",
            "selects_only_substantiated_or_claim_neutral_options",
            "classify label-only, mechanism-only, independently measured, and applicable outcome evidence; do not pay for unresolved claims, use a reversible nonmedical trial after safety checks, choose the cheapest acceptable claim-neutral beverage or defer, and seek qualified care for persistent or severe symptoms",
            "evidence_bounded_wellness_claim_decision_v1",
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
        "bridge_seller_claim_status": [
            "prop_lakanto_matcha_claim_snapshot",
            "prop_tealyra_blood_cleanser_claim_snapshot",
            "prop_lifeboost_low_acid_claim_snapshot",
            "prop_la_republica_mushroom_claim_snapshot",
        ],
        "bridge_named_detox_endpoint": [
            "prop_lakanto_matcha_claim_snapshot",
            "prop_tealyra_blood_cleanser_claim_snapshot",
            "prop_detox_concept_boundary",
        ],
        "bridge_antioxidant_activity_outcome": [
            "prop_lakanto_matcha_claim_snapshot",
            "prop_la_republica_mushroom_claim_snapshot",
            "prop_antioxidant_outcome_boundary",
        ],
        "bridge_caffeine_dose_person": [
            "prop_la_republica_mushroom_claim_snapshot",
            "prop_caffeine_response_boundary",
            "prop_black_tea_anxiety_anecdote_scope",
            "prop_starbucks_sleep_anecdote_scope",
            "prop_energy_kick_question_scope",
            "prop_tea_caffeine_question_scope",
        ],
        "bridge_low_acid_measurement_symptom": [
            "prop_lifeboost_low_acid_claim_snapshot",
            "prop_low_acid_measurement_boundary",
        ],
        "bridge_fungal_drug_product_scope": [
            "prop_la_republica_mushroom_claim_snapshot",
            "prop_medicinal_fungi_supplement_boundary",
        ],
        "bridge_community_scope": [
            "prop_caffeine_response_boundary",
            "prop_black_tea_anxiety_anecdote_scope",
            "prop_starbucks_sleep_anecdote_scope",
            "prop_energy_kick_question_scope",
            "prop_tea_caffeine_question_scope",
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
                "source_id": "decision_evidence_bounded_wellness_claim_choice",
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
