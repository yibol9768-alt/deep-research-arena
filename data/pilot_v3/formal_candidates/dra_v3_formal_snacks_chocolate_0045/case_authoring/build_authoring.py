#!/usr/bin/env python3
"""Build the audited Q45 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "verify_each_current_exact_label_and_portion_obtain_individual_clinical_clearance_then_send_the_smallest_lowest_cost_taste_trial_that_passes_all_gates_or_choose_a_nonfood_gift_or_defer"
WHEN = "complete_current_labels_exact_serving_exposure_and_recipient_specific_compatibility_are_not_established_by_the_frozen_packet"


def matcher(*phrases: str) -> dict[str, object]:
    return {
        "matcher": "normalized_text",
        "accepted_phrases": list(phrases),
        "normalizers": NORMALIZERS,
    }


def bridge(phrase: str) -> dict[str, object]:
    return {"type": "bridge", **matcher(phrase)}


def negative(claim_id: str, slot_id: str, phrase: str) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "contradicts_slot_id": slot_id,
        "critical": True,
        "rejected_matcher": matcher(phrase),
    }


EVIDENCE = [f"E{index}" for index in range(1, 15)]
BRIDGES = [f"B{index}" for index in range(1, 8)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "digestive_tolerance_scope_v1": bridge(
            rules["digestive_tolerance_scope_v1"]
        ),
        "exact_offer_claim_disclosure_matrix_v1": bridge(
            rules["exact_offer_claim_disclosure_matrix_v1"]
        ),
        "marketing_claims_are_not_synonyms_v1": bridge(
            rules["marketing_claims_are_not_synonyms_v1"]
        ),
        "sweetener_identity_and_dose_binding_v1": bridge(
            rules["sweetener_identity_and_dose_binding_v1"]
        ),
        "taste_and_community_evidence_boundary_v1": bridge(
            rules["taste_and_community_evidence_boundary_v1"]
        ),
        "glycemic_evidence_and_individual_response_boundary_v1": bridge(
            rules["glycemic_evidence_and_individual_response_boundary_v1"]
        ),
        "clinician_first_new_diagnosis_gate_v1": bridge(
            rules["clinician_first_new_diagnosis_gate_v1"]
        ),
        "evidence_bounded_sugar_free_gift_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                rules["evidence_bounded_sugar_free_gift_decision_v1"]
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "No frozen source proves a universally gentlest sweetener, a zero-blood-sugar-impact chocolate, or an individually suitable winner. Verify each current exact label and proposed portion, obtain recipient permission and clinician, registered-dietitian, or pharmacist clearance, then choose the lowest-cost smallest eligible taste trial or a nonfood gift or defer.",
                    "Treat every sugar and health phrase as a scoped seller assertion, bind the complete current ingredient and nutrition panel to the exact serving, require individualized professional compatibility review before consumption, and buy only the smallest lowest-total-cost cleared option that passes the post-clearance trial; otherwise choose nonfood or defer.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The frozen packet contains five seller snapshots, generic sweetener and glycemic context, and four scoped community discussions, but lacks complete current labels and sweetener quantities for every offer, exact-product clinical outcomes, the recipient's medication and treatment context, and individualized professional clearance."
                    ),
                    "tradeoff_matchers": {
                        "seller_claims_are_scoped": matcher(
                            "Titles, prices, ratings, review counts, net-carb fields, sweetener names, taste copy, diabetic-friendly wording and no-spike language remain seller assertions rather than independent current-label tests, clinical outcomes or individualized suitability evidence."
                        ),
                        "marketing_terms_are_not_equivalent": matcher(
                            "Sugar-free, zero-sugar, no-added-sugar, zero-carb, net-carb, keto, diabetic-friendly and no-spike wording are not interchangeable and must remain bound to the exact SKU, variant, serving and literal claim."
                        ),
                        "complete_labels_are_missing": matcher(
                            "A current complete ingredient panel, Nutrition Facts, serving size, total carbohydrate, fiber, sugar alcohol, allulose and available per-sweetener quantities must be resolved before comparing exact products."
                        ),
                        "unlisted_sweeteners_cannot_be_inferred": matcher(
                            "A front-label stevia or monk-fruit statement does not prove that an exact product lacks unlisted bulking agents, and brand or product-family knowledge cannot fill a missing ingredient panel."
                        ),
                        "sweetener_classes_are_heterogeneous": matcher(
                            "High-intensity sweeteners, allulose and individual sugar alcohols have different properties, and neither a class label nor one compound page supports a universal gentlest ranking for an unknown product mixture."
                        ),
                        "generic_metabolism_is_not_exact_outcome": matcher(
                            "Generic statements about calories, absorption, fermentation or a lesser glucose change do not establish the exact chocolate's dose, food-matrix response, zero impact or clinical fit."
                        ),
                        "glycemic_index_is_not_individual_prediction": matcher(
                            "Glycemic index is a population-average measure that does not predict one individual's response, and actual serving carbohydrate, matrix, medication, insulin resistance and within-person variability remain relevant."
                        ),
                        "digestive_anecdotes_are_scoped": matcher(
                            "The diet-ice-cream story is confounded and the Werther story involves nearly thirty candies and a self-reported large isomalt amount, so neither supplies incidence, normal-serving tolerance or evidence about the five exact products."
                        ),
                        "eli5_comments_are_not_medical_authority": matcher(
                            "The ELI5 discussions contain conflicting and speculative comments about drinks, fruit, fiber, appetite and metabolism and cannot establish causal health effects or medical guidance."
                        ),
                        "ratings_do_not_prove_taste": matcher(
                            "Store aggregates, familiar brands, and seller words such as delicious, classic or premium do not independently establish the father's taste or aftertaste preference."
                        ),
                        "clinician_gate_precedes_consumption": matcher(
                            "Because the recipient is newly diagnosed, obtain his permission and have his clinician, registered dietitian or pharmacist review the exact current product, portion, medications, allergies, gastrointestinal history and plan before consumption."
                        ),
                        "no_diagnosis_prescription_or_generic_threshold": matcher(
                            "Do not diagnose, prescribe, adjust medication, invent a generic safe dose or use self-testing as a substitute for individualized clinical guidance."
                        ),
                        "small_trial_is_post_clearance_and_scoped": matcher(
                            "Only after exact-label verification and individual clearance, try the smallest returnable or shareable quantity one candidate and precleared portion at a time with declared taste, digestive, allergy and professional stop rules."
                        ),
                        "eligible_smallest_or_nonfood_defer": matcher(
                            "Choose the lowest-total-cost smallest exact offer that passes label, portion, allergy, delivery, clinical and taste gates; otherwise send a nonfood gift or defer."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_highkey_no_spike_is_proven", "B3", "The HighKey seller's no-blood-sugar-spike wording independently proves zero glucose impact for the recipient."),
        negative("wrong_highkey_zero_carbs_literal", "B3", "The HighKey title's zero-carbs wording proves the exact serving has no carbohydrate even though the page also states two net carbs."),
        negative("wrong_lilys_stevia_zero_impact", "B6", "Lily's use of stevia and no-added-sugar wording proves that the complete crispy-rice bar has zero glycemic impact."),
        negative("wrong_lilys_is_gentlest", "B4", "Stevia makes the Lily's bar universally gentler than every other sweetener and product."),
        negative("wrong_choczero_no_polyol_is_clinical_clearance", "B7", "ChocZero's no-sugar-alcohol claim is enough to clear the peanut-butter cups for a newly diagnosed recipient."),
        negative("wrong_monk_fruit_excludes_all_bulking_agents", "B4", "A monk-fruit front-label claim proves that an exact product contains no other sweetener or bulking ingredient."),
        negative("wrong_hershey_aspartame_free_reveals_formula", "B2", "HERSHEY'S aspartame-free wording identifies the full replacement-sweetener formula and its amounts."),
        negative("wrong_russell_stevia_excludes_polyols", "B4", "Russell Stover's made-with-stevia wording proves that the exact candy contains no sugar alcohol or other bulking sweetener."),
        negative("wrong_store_aggregate_proves_taste", "B5", "The highest store aggregate proves which exact candy will taste most like a regular treat to the father."),
        negative("wrong_familiar_brand_is_safer", "B7", "A familiar national brand is medically safer for this recipient without exact-label and professional review."),
        negative("wrong_all_sugar_free_terms_synonymous", "B3", "Sugar-free, zero-sugar, no-added-sugar, keto, net-carb and diabetic-friendly all make the same measurable claim."),
        negative("wrong_generic_page_authenticates_label", "B4", "A generic sweetener page authenticates the current ingredients and dose of all five exact products."),
        negative("wrong_all_polyols_same", "B4", "All sugar alcohols have identical absorption, glycemic and digestive properties and can be ranked as one compound."),
        negative("wrong_maltitol_page_proves_product_contains_it", "B4", "The presence of a maltitol concept page proves that one or more of the five exact captured products contains maltitol."),
        negative("wrong_maltitol_threshold_is_prescription", "B1", "The amounts reported on the generic maltitol page are a universal safe prescription for this father."),
        negative("wrong_stevia_zero_calories_means_zero_food_response", "B6", "Because steviol glycosides are described as zero-calorie, any stevia-labeled chocolate must have zero post-meal glucose effect."),
        negative("wrong_gi_predicts_father", "B6", "A population glycemic-index value predicts this father's exact post-consumption response."),
        negative("wrong_net_carbs_alone_predicts_response", "B6", "Net carbs alone determine the recipient's response regardless of serving, food matrix, medications or individual variability."),
        negative("wrong_friends_story_proves_sweetener_causality", "B1", "The diet-ice-cream story proves an identified sweetener caused both friends' symptoms and gives an incidence rate."),
        negative("wrong_werther_story_bans_all_products", "B1", "One report after nearly thirty Werther candies proves that every sugar-free chocolate is intolerable at a normal serving."),
        negative("wrong_eli5_drink_comments_are_causal", "B1", "The sugar-free drink comments establish a causal obesity or microbiome effect for the five captured candies."),
        negative("wrong_fruit_thread_is_medical_guidance", "B6", "The fruit-versus-processed-sugar comments provide authoritative individualized diabetes guidance."),
        negative("wrong_skip_recipient_permission", "B7", "The buyer can send and encourage consumption without the father's permission because the gift is labeled sugar-free."),
        negative("wrong_self_test_replaces_clinician", "B7", "The father should self-test each candy instead of asking his clinician, dietitian or pharmacist about compatibility."),
        negative("wrong_adjust_medication_for_candy", "B7", "The recipient should adjust diabetes medication to accommodate the selected candy."),
        negative("wrong_taste_trial_before_clearance", "B5", "A taste trial should happen before the exact label and individualized compatibility review are complete."),
        negative("wrong_one_trial_generalizes_class", "B5", "One acceptable taste or digestive result proves the whole sweetener class and every future product will work."),
        negative("wrong_universal_gentlest_winner", "D1", "The frozen corpus establishes one universally gentlest sweetener and one zero-impact candy winner for every person with type 2 diabetes."),
        negative("wrong_buy_despite_missing_label", "D1", "Buy the highest-rated exact product now even when its complete current label, serving exposure and individualized compatibility remain unresolved."),
        negative("wrong_nonfood_not_allowed", "D1", "An edible candy must be chosen even if no exact offer passes the label and clinical gates."),
    ]

    g1 = ["E1", "E5", "E6", "E7", "E9", "E13", "B2", "B3"]
    g2 = ["E1", "E6", "E7", "E8", "E9", "E10", "E11", "E13", "B4"]
    g3 = ["E4", "E6", "E7", "E8", "E10", "E11", "B3", "B4", "B6"]
    g4 = ["E2", "E3", "E8", "E11", "E12", "E14", "B1"]
    g5 = ["E1", "E2", "E3", "E5", "E6", "E7", "E9", "E10", "E12", "E14", "B2", "B5", "B7"]
    g6 = PROOF
    subgoals = [
        {
            "subgoal_id": "G1",
            "description": "Audit the five exact frozen offers and separate literal seller price, aggregate, package, serving, carbohydrate, sweetener, taste and health wording from missing current labels, independent tests and individualized outcomes.",
            "critical": True,
            "requires": g1,
            "local_conclusion_slot_id": "B3",
        },
        {
            "subgoal_id": "G2",
            "description": "Distinguish high-intensity sweeteners, allulose and individual sugar alcohols, then require exact current ingredients and quantities rather than inferring an unlisted mixture or universal gentlest ranking.",
            "critical": True,
            "requires": g2,
            "local_conclusion_slot_id": "B4",
        },
        {
            "subgoal_id": "G3",
            "description": "Explain what generic metabolism and glycemic-index evidence can and cannot establish, preserving serving, food matrix, medication, metabolic state and individual variability instead of predicting zero impact.",
            "critical": True,
            "requires": g3,
            "local_conclusion_slot_id": "B6",
        },
        {
            "subgoal_id": "G4",
            "description": "Scope the sugar-alcohol and maltitol mechanisms plus the two digestive stories and two ELI5 threads to compound, amount, confounder and question scale without deriving incidence, universal thresholds, causality or exact-product outcomes.",
            "critical": True,
            "requires": g4,
            "local_conclusion_slot_id": "B1",
        },
        {
            "subgoal_id": "G5",
            "description": "Reject seller copy and store aggregates as independent taste evidence, require recipient permission and individualized clinician, dietitian or pharmacist review before consumption, and design only a smallest post-clearance one-product trial with stop rules.",
            "critical": True,
            "requires": g5,
            "local_conclusion_slot_id": "B7",
        },
        {
            "subgoal_id": "G6",
            "description": "Choose only a current exact offer whose label and portion are verified and individually cleared, then select the lowest-total-cost smallest trial that passes every gate or send a nonfood gift or defer without diagnosis, prescribing or a universal winner.",
            "critical": True,
            "requires": g6,
            "local_conclusion_slot_id": "D1",
        },
    ]
    requirements = [
        {
            "requirement_id": "Q1",
            "text": "Build a matched five-offer table of exact SKU, variant, frozen price, store aggregate, package and serving fields, literal sugar and health wording, named sweeteners and every missing current ingredient or nutrition field; keep non-equivalent claims separate.",
            "slot_ids": g1,
            "subgoal_ids": ["G1"],
            "required": True,
        },
        {
            "requirement_id": "Q2",
            "text": "Compare sweetener identity and mixture only after binding exact current ingredients and quantities, and explain why generic class pages cannot prove an exact product or universally gentlest ranking.",
            "slot_ids": g2,
            "subgoal_ids": ["G2"],
            "required": True,
        },
        {
            "requirement_id": "Q3",
            "text": "Explain population-average glycemic and generic metabolic evidence while refusing an individual zero-impact prediction and preserving serving, matrix, medication, metabolic and response variability.",
            "slot_ids": g3,
            "subgoal_ids": ["G3"],
            "required": True,
        },
        {
            "requirement_id": "Q4",
            "text": "Keep digestive mechanisms and community stories at compound, amount, author, confounder and question scope rather than treating them as incidence, universal thresholds, causality or exact-product outcomes.",
            "slot_ids": g4,
            "subgoal_ids": ["G4"],
            "required": True,
        },
        {
            "requirement_id": "Q5",
            "text": "Obtain recipient permission and exact-product clinician, registered-dietitian or pharmacist compatibility review before consumption, then specify the smallest post-clearance one-product taste trial with declared stop rules.",
            "slot_ids": g5,
            "subgoal_ids": ["G5"],
            "required": True,
        },
        {
            "requirement_id": "Q6",
            "text": "Recommend only the lowest-total-cost smallest exact offer passing label, portion, allergy, delivery, individualized clinical and taste gates; otherwise choose a nonfood gift or defer without diagnosis, prescribing, medication adjustment, a generic safe dose or universal winner.",
            "slot_ids": g6,
            "subgoal_ids": ["G6"],
            "required": True,
        },
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0045",
        "cluster_id": "sugar_free_label_metabolic_tolerance_and_individualized_fit_boundary",
        "difficulty": {
            "proof_depth": 5,
            "branching_factor": 7,
            "distractor_density": 0.35,
            "contradiction_count": 0,
        },
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "required_tradeoffs": [
                    "seller_claims_are_scoped",
                    "marketing_terms_are_not_equivalent",
                    "complete_labels_are_missing",
                    "unlisted_sweeteners_cannot_be_inferred",
                    "sweetener_classes_are_heterogeneous",
                    "generic_metabolism_is_not_exact_outcome",
                    "glycemic_index_is_not_individual_prediction",
                    "digestive_anecdotes_are_scoped",
                    "eli5_comments_are_not_medical_authority",
                    "ratings_do_not_prove_taste",
                    "clinician_gate_precedes_consumption",
                    "no_diagnosis_prescription_or_generic_threshold",
                    "small_trial_is_post_clearance_and_scoped",
                    "eligible_smallest_or_nonfood_defer",
                ],
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {
                evidence_id: {"outcome": "decision_unresolved"}
                for evidence_id in EVIDENCE
            },
            "human_solve_minutes": 60,
            "minimum_required_evidence_nodes": 14,
            "minimum_reasoning_depth": 5,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(OUT),
                "rules": len(rule_definitions),
                "decidable_claims": len(decidable_claims),
                "subgoals": len(subgoals),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
