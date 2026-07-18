#!/usr/bin/env python3
"""Build the audited Q51 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_only_the_lowest_cost_exact_offer_that_passes_formula_label_budget_allergen_package_and_family_acceptability_gates_otherwise_keep_the_baseline_run_a_smaller_matched_trial_or_defer"
WHEN = "the_packet_lacks_current_exact_formulas_matched_clean_label_controls_and_repeated_family_acceptability_results"


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


EVIDENCE = [f"E{index}" for index in range(1, 17)]
BRIDGES = [f"B{index}" for index in range(1, 8)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "clean_label_natural_ambiguity_v1": bridge(rules["clean_label_natural_ambiguity_v1"]),
        "msg_glutamate_mechanism_boundary_v1": bridge(rules["msg_glutamate_mechanism_boundary_v1"]),
        "additive_color_flavor_function_boundary_v1": bridge(rules["additive_color_flavor_function_boundary_v1"]),
        "seller_claim_quantity_price_scope_v1": bridge(rules["seller_claim_quantity_price_scope_v1"]),
        "community_claim_method_scope_v1": bridge(rules["community_claim_method_scope_v1"]),
        "exact_formula_matched_cost_trial_v1": bridge(rules["exact_formula_matched_cost_trial_v1"]),
        "clean_label_decision_preparation_v1": bridge(rules["clean_label_decision_preparation_v1"]),
        "evidence_bounded_snack_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["evidence_bounded_snack_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no universal clean-label premium, automatic health or safety advantage, or immediate winner. Choose only the lowest-cost exact offer passing formula, label, budget, allergen, package and family-acceptability gates; otherwise keep the baseline, run a smaller matched trial or defer.",
                    "Verify exact current offers and formulas, define the household criterion narrowly, compare only comparable products and choose the lowest-cost passing offer, or keep the baseline, run a smaller matched trial or defer without a universal clean-label winner.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains five frozen seller snapshots, bounded clean-label, natural, MSG, glutamate, additive, color and flavor context, and four scoped community discussions, but lacks verified current exact formulas, ingredient amounts, allergens, delivered prices, matched clean-label controls and repeated blinded family acceptability and waste results."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher("All SKU, price, pack, mass, rating, no-MSG, natural, no-artificial, nutrition, health and quality wording remains frozen seller assertion rather than a current offer, exact formula audit or child outcome."),
                        "quantity_ambiguities_are_preserved": matcher("Retain the title quantities alongside every Item Weight, Package Dimensions or Product Dimensions value and do not silently relabel a generic or shipping weight as net food quantity."),
                        "unit_arithmetic_is_conditional": matcher("Show the title-based arithmetic of about 9.43, 0.63, 0.94, 1.66 and 1.75 dollars per declared ounce with assumptions visible and without calling it a current delivered-price comparison."),
                        "offers_are_not_a_matched_premium_test": matcher("The five offers differ in category, flavor, formula, unit size and pack count, and Natural Cheetos versus regular Jumbo Puffs is not a matched clean-label control."),
                        "clean_label_and_natural_are_ambiguous": matcher("Clean-label and natural terminology has multiple meanings and does not automatically mean additive-free, organic, whole, healthy or safe."),
                        "msg_and_glutamate_are_distinguished": matcher("Keep monosodium glutamate distinct from glutamic acid, free glutamate, other glutamate salts and yeast extract, and interpret a no-MSG claim only from its exact wording and formula."),
                        "additive_functions_are_not_outcomes": matcher("Additive, color and flavor classes describe functions and origins rather than an automatic whole-product health, safety or quality ranking."),
                        "community_evidence_is_scoped": matcher("The MSG, front-label and child-survey discussions remain author-, thread-, product-, time- and method-scoped rather than chemistry, law, medicine, exact-product or population evidence."),
                        "survey_limitations_are_retained": matcher("The 1,135-parent online survey with about twenty or more per state remains vulnerable to sampling, self-report, outlier and uncertainty problems and is not a validated child-consumption estimate."),
                        "exact_formula_and_allergens_are_required": matcher("Verify current SKU, variant, unit count, net quantity, delivered price, ingredients, subingredients, nutrition, serving size, allergens, claim wording, lot, date, storage and return terms before purchase or tasting."),
                        "household_criterion_is_narrow": matcher("Define no intentionally added monosodium glutamate or no artificial color and flavor operationally without expanding the criterion to no glutamate, no additives, healthy or safe."),
                        "trial_is_small_matched_and_repeated": matcher("Use the smallest reversible comparable rotation or matched variant, mask marketing and price, randomize equal portions, repeat sessions and record acceptability and waste with identity, allergen and package stops."),
                        "no_medical_safety_or_exposure_inference": matcher("Do not issue health, safety, medical, intake, exposure or child-specific conclusions from seller copy, frozen concept pages, community debate or this family preference trial."),
                        "lowest_cost_or_baseline_trial_defer": matcher("Choose only the lowest-cost exact offer passing formula, label, budget, allergen, package and family-acceptability gates; otherwise keep the baseline, run a smaller matched trial or defer."),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_additive_exclusion_means_none", "B1", "A no-artificial-color-or-flavor claim proves the exact product contains no additives of any kind."),
        negative("wrong_natural_color_always_better", "B1", "A natural colorant is automatically healthier and safer than every synthesized colorant."),
        negative("wrong_natural_flavor_always_better", "B1", "A natural flavor is automatically higher quality and safer than an artificial or nature-identical flavor."),
        negative("wrong_source_class_is_formula", "B1", "A generic flavoring source class reveals every flavor compound and amount in an exact snack."),
        negative("wrong_clean_label_additive_free", "B2", "Clean label has one universal definition and always means completely additive-free."),
        negative("wrong_natural_means_organic", "B2", "Natural is synonymous with certified organic and whole food."),
        negative("wrong_natural_means_healthy_safe", "B2", "A natural claim by itself proves that the exact snack is healthy and safe for every child."),
        negative("wrong_frozen_label_current_law", "B2", "The frozen natural-food background page is sufficient current legal advice for every product and jurisdiction."),
        negative("wrong_forum_natural_proof", "B3", "The naturally occurring MSG thread proves that natural occurrence makes a substance nutritious or safe."),
        negative("wrong_forum_natural_danger", "B3", "One reply saying natural occurrence signifies nothing proves that every natural ingredient is dangerous."),
        negative("wrong_msg_forum_medical", "B3", "The MSG ELI5 comments provide authoritative medical conclusions about exact child exposure."),
        negative("wrong_front_label_forum_law", "B3", "The whole-wheat discussion establishes the binding legal meaning of every clean-label phrase."),
        negative("wrong_survey_state_ranking", "B3", "The 1,135-parent online survey validates a precise ranking of child snack consumption in every state."),
        negative("wrong_survey_household", "B3", "The online state survey establishes how much this exact household's child eats."),
        negative("wrong_no_msg_means_no_glutamate", "B4", "A no-MSG statement necessarily means the product contains no glutamic acid, free glutamate, other glutamate salts or yeast extract."),
        negative("wrong_glutamate_disproves_no_msg", "B4", "Any naturally occurring glutamate automatically proves that a no-MSG seller statement is false."),
        negative("wrong_msg_mechanism_health", "B4", "The general MSG identity and umami mechanism establishes a child-specific health or safety outcome."),
        negative("wrong_glutamate_amount_known", "B4", "The glutamate-flavoring page reveals the exact glutamate compounds and amounts in all five snacks."),
        negative("wrong_muya_claim_proves_formula", "B5", "Muya's no-MSG and natural wording proves its complete current formula and the best child outcome."),
        negative("wrong_fisher_claim_additive_free", "B5", "Fisher's no-artificial-colors-or-flavors wording proves that its flavored almonds contain no additives."),
        negative("wrong_orchard_claim_health", "B5", "Orchard's no-artificial-ingredients wording proves a health advantage over every other snack."),
        negative("wrong_natural_cheetos_matched", "B5", "Natural Cheetos and regular Jumbo Puffs are a matched formula pair differing only in clean-label wording."),
        negative("wrong_generic_weights_are_net", "B5", "Every Item Weight or Package Dimensions weight is the verified total net food quantity."),
        negative("wrong_sticker_price_is_delivered", "B5", "Every frozen seller price is necessarily the family's current delivered price."),
        negative("wrong_muya_price_health", "B6", "Muya's much higher conditional title price per ounce proves greater health or quality."),
        negative("wrong_cheetos_no_premium", "B6", "Natural Cheetos' lower frozen title price per ounce than Jumbo Puffs proves there is no clean-label premium in the market."),
        negative("wrong_cross_product_causality", "B6", "Cross-product price or liking differences can be attributed to a no-MSG or no-artificial phrase despite different recipes and formats."),
        negative("wrong_unblinded_one_taste", "B6", "One taste after seeing brand, price and marketing proves a stable family preference caused by clean labeling."),
        negative("wrong_cost_before_verification", "B6", "Cost per accepted serving can be calculated without verified current price, net quantity, serving size and waste."),
        negative("wrong_one_gate_compensates", "B7", "A low price or high liking score can compensate for unresolved exact identity, allergens, formula or package integrity."),
        negative("wrong_health_decision", "D1", "The frozen packet proves one snack is the healthiest or safest choice for every child."),
        negative("wrong_immediate_winner", "D1", "The frozen packet already proves one unconditional clean-label product winner."),
        negative("wrong_buy_before_checks", "D1", "The caregiver should buy the largest promoted offer before verifying the formula, allergens, delivered quantity and family acceptability."),
    ]

    g1 = ["E1", "E3", "E4", "E5", "E13", "B1", "B2"]
    g2 = ["E7", "E10", "B4"]
    g3 = ["E2", "E11", "E12", "E14", "E15", "B5"]
    g4 = ["E6", "E8", "E9", "E16", "B3"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5", "B6"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Explain clean-label and natural ambiguity plus additive, color and flavor functions and source classes without promoting any category into an exact formula, health, safety or quality result.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G2", "description": "Distinguish monosodium glutamate from broader glutamic acid and glutamate flavoring and keep the evidence at identity and umami-mechanism scope rather than medical, exposure or child-outcome scope.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G3", "description": "Audit all five exact frozen offers, preserve every title-versus-generic-weight ambiguity, show conditional price-per-declared-ounce arithmetic and reject a matched clean-label premium interpretation.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G4", "description": "Keep the two MSG threads, front-label thread and child-snack survey discussion at author, thread, product, time and method scope and retain the online survey's sampling and uncertainty limitations.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G5", "description": "Define the household criterion narrowly, verify exact current formula, allergens, quantity and delivered cost, and design the smallest comparable masked randomized repeated acceptability-and-waste trial with predeclared stops.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B6"},
        {"subgoal_id": "G6", "description": "Choose only the lowest-cost exact offer passing formula, label, budget, allergen, package and family-acceptability gates, or keep the baseline, run a smaller matched trial or defer without naming a universal clean-label, health or safety winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Explain clean-label, natural, additive, coloring and flavoring terminology and its exact formula, health, safety and quality limits.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Distinguish MSG identity from broader glutamate flavoring without medical, exposure, safety or child-specific conclusions.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Build the five-offer table, retain all frozen and ambiguous quantity fields, show conditional unit arithmetic and explain why the offers are not a matched premium test.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Use the community pages only as scoped belief, label-question and survey-method evidence, not as chemistry, law, medicine, exact-product or population evidence.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify exact current formula, allergen, quantity and delivered-cost checks plus a smallest reversible comparable masked randomized repeated family trial with acceptability, waste and stops.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a conditional lowest-cost purchase, keep-baseline, smaller-matched-trial or deferral decision without a universal clean-label, health or safety winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0051",
        "cluster_id": "clean_label_snack_premium_formula_and_claim_boundary",
        "difficulty": {"proof_depth": 4, "branching_factor": 16, "distractor_density": 0.37, "contradiction_count": 2},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "required_tradeoffs": [
                    "seller_fields_are_scoped",
                    "quantity_ambiguities_are_preserved",
                    "unit_arithmetic_is_conditional",
                    "offers_are_not_a_matched_premium_test",
                    "clean_label_and_natural_are_ambiguous",
                    "msg_and_glutamate_are_distinguished",
                    "additive_functions_are_not_outcomes",
                    "community_evidence_is_scoped",
                    "survey_limitations_are_retained",
                    "exact_formula_and_allergens_are_required",
                    "household_criterion_is_narrow",
                    "trial_is_small_matched_and_repeated",
                    "no_medical_safety_or_exposure_inference",
                    "lowest_cost_or_baseline_trial_defer"
                ]
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": 16,
            "minimum_reasoning_depth": 4
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
