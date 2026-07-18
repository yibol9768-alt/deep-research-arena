#!/usr/bin/env python3
"""Build the audited Q48 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_lowest_cost_exact_comparable_bar_that_passes_identity_allergen_repeatable_sensory_and_budget_gates_otherwise_keep_the_current_bar_run_a_smaller_corrected_trial_or_defer"
WHEN = "the_packet_lacks_current_exact_delivered_offers_and_blinded_matched_repeat_results"


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


EVIDENCE = [f"E{index}" for index in range(1, 16)]
BRIDGES = [f"B{index}" for index in range(1, 9)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "seller_price_pack_normalization_scope_v1": bridge(rules["seller_price_pack_normalization_scope_v1"]),
        "comparable_form_price_ladder_boundary_v1": bridge(rules["comparable_form_price_ladder_boundary_v1"]),
        "process_ethics_label_boundary_v1": bridge(rules["process_ethics_label_boundary_v1"]),
        "cocoa_composition_quality_boundary_v1": bridge(rules["cocoa_composition_quality_boundary_v1"]),
        "community_habit_value_scope_v1": bridge(rules["community_habit_value_scope_v1"]),
        "blinded_difference_liking_protocol_v1": bridge(rules["blinded_difference_liking_protocol_v1"]),
        "person_specific_price_stop_rule_v1": bridge(rules["person_specific_price_stop_rule_v1"]),
        "price_ladder_decision_preparation_v1": bridge(rules["price_ladder_decision_preparation_v1"]),
        "evidence_bounded_price_ladder_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["evidence_bounded_price_ladder_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no universal price cutoff or immediate winner. Choose the lowest-cost exact comparable bar that passes verified identity, allergens, repeatable blinded sensory and budget gates; otherwise keep the current bar, run a smaller corrected trial or defer.",
                    "Verify current exact offers and comparable forms, then select only the lowest-cost bar clearing the predeclared difference, liking and incremental-cost rule, or keep the current bar, correct the trial or defer without a universal breakpoint.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains five frozen seller snapshots, bounded process, ethics, composition, sensory, hedonic and blinding context, and three scoped community anecdotes, but lacks verified current delivered labels and prices, matched comparable portions and repeated blinded difference, liking and willingness-to-pay results."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher("All SKU, price, pack, mass, percentage, rating, process, origin, certification, flavor and quality wording remains frozen seller assertion rather than current offer or independent result."),
                        "unit_arithmetic_is_conditional": matcher("Show conditional price per nominal bar and mass with visible arithmetic while retaining pack assumptions and the Raaka 5.4-ounce versus 1.8-ounce conflict."),
                        "comparable_forms_are_required": matcher("Compare price tiers causally only among matched plain bars and keep the 60-percent coconut-milk recipe in a separate stratum or exclude it."),
                        "budget_anchors_are_unverified": matcher("The buyer's two-dollar and ten-to-twelve-dollar figures remain unverified anchors until current exact delivered offers match them."),
                        "process_and_ethics_are_not_taste": matcher("Bean-to-bar is process-control context and Fairtrade is price-support context, not guarantees of blind taste, health, exact payments, traceability or total ethics."),
                        "percentage_is_not_complete_composition": matcher("Cocoa percentage and cocoa-solids terminology do not reveal the complete balance of non-fat solids, cocoa butter, sugar and other ingredients."),
                        "bean_class_is_not_an_exact_grade": matcher("Bulk-versus-flavor cocoa is partly subjective and processing-sensitive and does not grade an exact captured bar or define a price-quality curve."),
                        "community_evidence_is_scoped": matcher("The daily-habit, varied-gift and Aldi posts remain author-, incident-, product-, place- and time-scoped rather than population, safety, brand or value evidence."),
                        "difference_liking_and_value_are_separate": matcher("Record detectable difference separately from nine-point liking and willingness to pay; none of those outcomes substitutes for the others."),
                        "blinding_and_repeatability_are_required": matcher("Mask brand, package, price and marketing, randomize equal coded portions, repeat sessions and report guesses or other unblinding before interpreting a preference."),
                        "exact_identity_and_allergens_are_required": matcher("Verify current SKU, variant, pack, net mass, price, shipping, ingredients, allergens, cocoa components, origin, certification, lot, date, storage and return terms before tasting."),
                        "no_health_or_intake_inference": matcher("Do not claim health benefit, a safe daily intake or medical effect from percentages, generic cocoa context, seller copy or anecdotes."),
                        "stop_rule_is_person_specific": matcher("Apply the predeclared minimum liking gain, repeatability and maximum incremental evening-cost rule only to this buyer, these bars, portions, prices and test conditions."),
                        "lowest_cost_or_keep_correct_defer": matcher("Choose the lowest-cost exact comparable passing bar; if no premium clears every gate, keep the current bar, run a smaller corrected trial or defer."),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_dove_current_price", "B6", "The frozen DOVE price is necessarily the buyer's current delivered price."),
        negative("wrong_dove_low_price_best", "B6", "DOVE must be the best daily value because its conditional price per ounce is lowest."),
        negative("wrong_lindt_rating_taste", "B6", "The Lindt 67-percent store rating proves superior taste or quality."),
        negative("wrong_ritter_price_quality", "B6", "The 8.99-dollar Ritter bar is higher quality because it costs more per bar."),
        negative("wrong_green_black_price_quality", "B6", "The Green and Black three-pack price proves that each bar is better than the twelve-pack bars."),
        negative("wrong_raaka_mass_resolved", "B6", "The Raaka page unambiguously establishes 5.4 delivered ounces despite its 1.8-ounce Product Dimensions field."),
        negative("wrong_budget_anchors_verified", "B6", "The packet verifies one exact two-dollar supermarket bar and one exact ten-to-twelve-dollar craft bar."),
        negative("wrong_homogeneous_ladder", "B4", "All five offers form one homogeneous price ladder despite percentage, recipe, coconut content, mass and pack differences."),
        negative("wrong_raaka_plain_control", "B4", "The Raaka coconut-milk 60-percent bar is a matched plain control for every 70- or 74-percent bar."),
        negative("wrong_unit_price_causes_quality", "B4", "A higher normalized price by itself causes or proves a better sensory result."),
        negative("wrong_bean_to_bar_taste", "B5", "Bean-to-bar universally guarantees superior blind taste."),
        negative("wrong_fairtrade_taste", "B5", "Fairtrade certification proves that a chocolate tastes better."),
        negative("wrong_exact_payments_known", "B5", "The generic Fairtrade definition and seller page establish every exact payment and farmer outcome in the captured supply chain."),
        negative("wrong_raaka_total_ethics", "B5", "Raaka's direct-source and beyond-fair-trade copy proves complete ethical superiority over every other bar."),
        negative("wrong_percentage_formula", "B2", "A cocoa percentage alone reveals the full balance of cocoa solids, cocoa butter, sugar and every ingredient."),
        negative("wrong_percentage_quality", "B2", "The 74-percent bar must be higher quality than every 70- or 60-percent bar."),
        negative("wrong_bulk_class_grade", "B2", "The generic bulk-cocoa page grades each exact seller product and establishes its taste quality."),
        negative("wrong_origin_quality", "B2", "Single-origin or Trinitario wording alone proves a monotonic flavor-quality advantage."),
        negative("wrong_daily_post_population", "B3", "One daily-habit post establishes how much chocolate the buyer or population should eat."),
        negative("wrong_gift_post_taste_trial", "B3", "Sending six varied dark bars is a controlled blind price-ladder experiment."),
        negative("wrong_aldi_dark_bar_curve", "B3", "One Aldi favorites list containing chocolate-flavored ice cream establishes the dark-bar price-quality curve."),
        negative("wrong_forum_health", "B3", "The three community pages provide medical or safe-intake evidence for a nightly dark-chocolate habit."),
        negative("wrong_difference_equals_liking", "B1", "Detecting that two bars differ proves that the expensive bar is liked more."),
        negative("wrong_hedonic_equals_detection", "B1", "A nine-point liking score by itself proves that two products are analytically distinguishable."),
        negative("wrong_one_unblinded_taste", "B1", "One taste after seeing brand and price is sufficient evidence of a measurable premium improvement."),
        negative("wrong_blind_automatically_succeeds", "B1", "Calling a test blind proves that all recipe and identity cues were successfully masked."),
        negative("wrong_unmatched_portions", "B1", "Different portion sizes, temperatures and serving orders do not affect the interpretation of the taste comparison."),
        negative("wrong_willingness_is_preference", "B1", "Willingness to pay and sensory liking are the same outcome and need only one measure."),
        negative("wrong_posthoc_cutoff", "B7", "The buyer may inspect all results and then invent a price and liking threshold that selects the preferred winner."),
        negative("wrong_universal_breakpoint", "B7", "A stopping tier from one person's trial is a universal market point where price stops improving quality."),
        negative("wrong_ethics_as_taste_gain", "B8", "An ethics preference can be reported as a measured blind taste improvement."),
        negative("wrong_health_from_cocoa", "B8", "Generic cocoa information proves a health benefit or safe nightly amount for an exact bar."),
        negative("wrong_one_gate_compensates", "B8", "A strong liking score can compensate for unresolved identity or allergens."),
        negative("wrong_immediate_winner", "D1", "The frozen packet already proves one unconditional product and universal price cutoff."),
        negative("wrong_buy_craft_without_trial", "D1", "The buyer should adopt the craft habit before verifying exact offers and running the predeclared trial."),
    ]

    g1 = ["E7", "E9", "E11", "E12", "E13", "B4", "B6"]
    g2 = ["E2", "E4", "E5", "E8", "E9", "E12", "E13", "B2", "B5"]
    g3 = ["E1", "E6", "E15", "B3"]
    g4 = ["E3", "E7", "E9", "E10", "E11", "E12", "E13", "E14", "B1", "B4"]
    g5 = EVIDENCE + ["B1", "B3", "B4", "B6", "B7", "B8"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit all five frozen offers, show conditional price-per-bar and price-per-mass arithmetic, preserve the Raaka mass conflict and separate comparable plain bars from unlike recipes.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G2", "description": "Bound bean-to-bar, Fairtrade, cocoa-solids, bean-class, origin and percentage evidence without promoting process, ethics or composition context into exact taste, health or quality guarantees.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G3", "description": "Keep the daily-habit, varied-gift and Aldi price-and-quality pages at their author, incident, product, place and time scopes and extract only trial-design variables.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G4", "description": "Design a matched repeated within-person protocol with verified labels and allergens, equal coded portions, randomized order, brand-price masking, unblinding records and separate difference, nine-point liking and willingness-to-pay outcomes.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Apply a predeclared person-specific next-tier stop rule using repeatability, minimum liking gain and maximum incremental evening cost without a post-hoc or universal cutoff.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G6", "description": "Choose the lowest-cost exact comparable bar passing identity, allergen, repeatable sensory and budget gates, or keep the current bar, correct the trial or defer without naming an unconditional winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build the exact five-offer table, preserve frozen and conflicting fields, show conditional unit-price arithmetic and state which forms are actually comparable.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain what bean-to-bar, Fairtrade, cocoa-solids, bulk-versus-flavor cocoa, origin and percentage can and cannot establish.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Use the three community pages only as scoped anecdotes and not as population, safety, preference or price-quality evidence.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Specify exact-offer, label and allergen checks plus a randomized blinded repeated trial that separates detectable difference, nine-point liking and willingness to pay.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Predeclare and apply a person-specific minimum liking gain, repeatability and maximum incremental cost stop rule, including unblinding and safety stops.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a conditional lowest-cost purchase, keep-current-bar, corrected-trial or deferral decision without health claims or a universal product or price cutoff.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0048",
        "cluster_id": "dark_chocolate_price_ladder_personal_sensory_cutoff",
        "difficulty": {"proof_depth": 4, "branching_factor": 15, "distractor_density": 0.36, "contradiction_count": 2},
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
                    "unit_arithmetic_is_conditional",
                    "comparable_forms_are_required",
                    "budget_anchors_are_unverified",
                    "process_and_ethics_are_not_taste",
                    "percentage_is_not_complete_composition",
                    "bean_class_is_not_an_exact_grade",
                    "community_evidence_is_scoped",
                    "difference_liking_and_value_are_separate",
                    "blinding_and_repeatability_are_required",
                    "exact_identity_and_allergens_are_required",
                    "no_health_or_intake_inference",
                    "stop_rule_is_person_specific",
                    "lowest_cost_or_keep_correct_defer"
                ]
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": 15,
            "minimum_reasoning_depth": 4
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
