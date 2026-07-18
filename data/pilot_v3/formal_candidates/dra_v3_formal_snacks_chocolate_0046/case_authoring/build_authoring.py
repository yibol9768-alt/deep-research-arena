#!/usr/bin/env python3
"""Build the audited Q46 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_lowest_total_cost_exact_offer_passing_all_current_label_safety_budget_and_local_trial_gates_or_use_an_accepted_control_or_defer"
WHEN = "the_packet_lacks_complete_current_physical_labels_dated_matched_formula_and_weight_histories_and_a_controlled_office_trial"


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


EVIDENCE = [f"E{index}" for index in range(1, 12)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        rule_id: bridge(rules[rule_id])
        for rule_id in (
            "chocolate_label_and_fat_substitution_boundary_v1",
            "exact_offer_rating_sample_matrix_v1",
            "recipe_weight_change_pairing_requirement_v1",
            "scoped_rating_reputation_temperature_transfer_v1",
            "current_and_historical_verification_gate_v1",
            "reversible_office_candy_trial_v1",
        )
    }
    rule_definitions["evidence_bounded_office_candy_stocking_v1"] = {
        "type": "decision",
        "decision_matcher": matcher(
            rules["evidence_bounded_office_candy_stocking_v1"]
        ),
        "conclusion_matchers": {
            ANSWER: matcher(
                "Retain every displayed rating with its review count, refuse recipe-change or shrinkflation claims without dated matched exact-version evidence, verify current physical labels and office safety, and choose only the lowest-total-cost exact offer that passes the matched local trial; otherwise use an accepted control or defer.",
                "Do not bulk-buy from a percentage rating or brand reputation alone; verify identity, ingredients, allergens, market, net quantity and history, run a small controlled office trial, and select the least costly passing offer or defer.",
            )
        },
        "admissible_conditions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(
                    "The packet contains four frozen seller pages, four general concept pages and three scoped community discussions, but lacks complete current physical ingredient and allergen labels for all exact offers, dated matched old-versus-new formula, weight and receipt pairs, resolved package identities and a controlled office acceptance trial."
                ),
                "tradeoff_matchers": {
                    "rating_percentage_needs_denominator": matcher(
                        "A displayed percentage must remain paired with its review count, so 100 percent over one or two reviews is not equal evidence to another percentage over a larger count and none directly measures this office."
                    ),
                    "seller_snapshot_is_not_history": matcher(
                        "A current seller page, rating, product title or nostalgic continuity phrase cannot prove an old recipe, current recipe stability, a downgrade or shrinkflation without a dated matched historical counterpart."
                    ),
                    "jurisdiction_rules_do_not_classify_sku": matcher(
                        "General compound, couverture and cocoa-fat rules differ by jurisdiction and cannot classify an exact SKU or establish its current fat source without the applicable market rule and physical label."
                    ),
                    "unit_cost_requires_comparable_units": matcher(
                        "Price comparison requires common weight or accepted-serving units after pack count, product form, delivered total and ambiguous mass fields are resolved."
                    ),
                    "godiva_identity_and_mass_are_ambiguous": matcher(
                        "The Godiva-branded page lists Candy Cabin as manufacturer and uses ambiguous 3.1-ounce, carton and mini-bar wording, so its exact identity and comparable mass require physical-package verification."
                    ),
                    "goldenberg_continuity_copy_is_unverified": matcher(
                        "The Goldenberg page's same-quality-and-taste wording is seller copy rather than a dated ingredient, net-weight or sensory continuity record."
                    ),
                    "community_anecdotes_do_not_transfer": matcher(
                        "Reports about unrelated product decline, book-rating disagreement and chilled-chip preference motivate checks and temperature control but cannot transfer to any captured chocolate offer."
                    ),
                    "current_label_and_office_safety_are_unresolved": matcher(
                        "Current physical identity, complete ingredients, allergens, dietary fit, market, lot, net quantity, delivered cost and office food-handling requirements must be verified before purchase or tasting."
                    ),
                    "historical_pair_must_match_version": matcher(
                        "A recipe or size-change claim requires dated before-and-after records for the same SKU or a documented version mapping in the same market, including complete ingredients, net quantity, pack count, price and receipts as applicable."
                    ),
                    "small_trial_is_local_not_universal": matcher(
                        "A small brand-masked trial with equal portions, matched temperature, controlled order and predeclared acceptance, consumption, repeat-choice and waste thresholds measures only local office fit under tested conditions."
                    ),
                    "lowest_cost_passing_or_defer": matcher(
                        "Choose only the lowest-total-cost exact offer clearing identity, ingredient, allergen, dietary, budget and local-trial gates; otherwise use an already accepted control or defer without a universal brand verdict."
                    ),
                },
            }
        ],
    }

    decidable_claims = [
        negative("wrong_one_review_equals_confidence", "B2", "A 100-percent rating over one review is conclusive and more reliable than a 95-percent rating over twelve reviews."),
        negative("wrong_rating_is_office_preference", "B2", "The four store aggregates directly measure preference in this office."),
        negative("wrong_kinder_history_known", "B3", "The current Kinder page proves that its ingredients and pack size have never changed."),
        negative("wrong_hershey_history_known", "B3", "The current Hershey page proves a stable historical recipe and excludes shrinkflation."),
        negative("wrong_godiva_mass_resolved", "B2", "The Godiva page unambiguously proves the total edible mass and official manufacturer identity of the entire set."),
        negative("wrong_goldenberg_copy_is_history", "B3", "The same quality and taste always known phrase proves Goldenberg recipe continuity through time."),
        negative("wrong_95_means_downgrade", "B4", "Goldenberg's 95-percent rating proves a quiet recipe downgrade compared with the 100-percent listings."),
        negative("wrong_compound_is_all_substitute_fat", "B1", "Every product containing any non-cocoa fat is universally and legally compound chocolate in every jurisdiction."),
        negative("wrong_canada_rule_is_global", "B1", "The frozen Canadian chocolate rule applies unchanged to every market represented by the four listings."),
        negative("wrong_eu_rule_is_global", "B1", "The frozen EU alternative-fat rule classifies all four exact offers regardless of sale market or current label."),
        negative("wrong_couverture_term_global", "B1", "Couverture has the same legally regulated meaning in the EU and the United States."),
        negative("wrong_brand_proves_cocoa_butter", "B1", "A famous brand name proves that cocoa butter is the only current fat source in the exact captured SKU."),
        negative("wrong_current_page_proves_change", "B3", "A single current package snapshot is enough to prove shrinkflation or recipe reformulation."),
        negative("wrong_package_dimensions_are_net", "B3", "Package dimensions and shipping weight can substitute for dated edible net-quantity records."),
        negative("wrong_sticker_price_is_unit_value", "B5", "Sticker price alone identifies the cheapest comparable chocolate despite different packs, forms and delivered totals."),
        negative("wrong_bifl_transfers_to_chocolate", "B4", "A pillow and boot quality complaint proves that these chocolate brands changed manufacturing for the worse."),
        negative("wrong_books_rating_invalidates_food", "B4", "One books author's disagreement invalidates all product ratings and proves the chocolate listings are wrong."),
        negative("wrong_chilled_chips_proves_chocolate", "B4", "A chilled-chip anecdote proves the preferred serving temperature for every chocolate eater."),
        negative("wrong_trial_without_temperature_control", "B6", "An office taste test may serve products at different temperatures and still attribute every difference to brand or recipe."),
        negative("wrong_unmasked_vote_proves_history", "B6", "One unmasked popularity vote proves both office preference and historical recipe continuity."),
        negative("wrong_bulk_buy_before_allergy_check", "D1", "The manager should bulk-buy the highest-rated listing before checking current ingredients and office allergies."),
        negative("wrong_missing_history_can_be_filled", "D1", "Missing old labels and receipts may be replaced by brand folklore when declaring shrinkflation."),
        negative("wrong_universal_brand_winner", "D1", "The selected office offer is therefore the universally best chocolate brand and deserves the same rating in every market."),
    ]

    g1 = ["E5", "E6", "E7", "E8", "B2"]
    g2 = ["E2", "E3", "E4", "B1"]
    g3 = ["E1", "E4", "E5", "E6", "E7", "E8", "E11", "B3", "B5"]
    g4 = ["E1", "E9", "E10", "B4"]
    g5 = EVIDENCE + BRIDGES
    g6 = PROOF
    subgoals = [
        {
            "subgoal_id": "G1",
            "description": "Audit all four exact seller snapshots, preserve rating denominators, product-form, pack, mass and manufacturer-or-repacker ambiguities, and state what the aggregates do and do not justify.",
            "critical": True,
            "requires": g1,
            "local_conclusion_slot_id": "B2",
        },
        {
            "subgoal_id": "G2",
            "description": "Explain compound chocolate, couverture and food-label fields by jurisdiction while refusing to classify any exact SKU from a title or general page.",
            "critical": True,
            "requires": g2,
            "local_conclusion_slot_id": "B1",
        },
        {
            "subgoal_id": "G3",
            "description": "Specify the dated same-SKU or documented-version before-and-after ingredients, net quantity, pack count, price and receipt evidence required for recipe-change, downgrade or shrinkflation claims.",
            "critical": True,
            "requires": g3,
            "local_conclusion_slot_id": "B5",
        },
        {
            "subgoal_id": "G4",
            "description": "Keep the quality-decline, rating-disagreement and temperature discussions at their author, category, product, time and condition scope while extracting only checks and trial controls.",
            "critical": True,
            "requires": g4,
            "local_conclusion_slot_id": "B4",
        },
        {
            "subgoal_id": "G5",
            "description": "Combine every branch into a current physical-label and office-safety verification gate, comparable-unit and accepted-serving costs, and a small brand-masked matched trial with predeclared local outcomes.",
            "critical": True,
            "requires": g5,
            "local_conclusion_slot_id": "B6",
        },
        {
            "subgoal_id": "G6",
            "description": "Choose only the lowest-total-cost exact offer clearing every identity, ingredient, allergen, dietary, budget and local-trial gate, or use an accepted control or defer without a universal rating, recipe or brand verdict.",
            "critical": True,
            "requires": g6,
            "local_conclusion_slot_id": "D1",
        },
    ]
    requirements = [
        {
            "requirement_id": "Q1",
            "text": "Audit all four exact offers and carry each rating with its review count, pack and mass wording, product form and manufacturer-or-repacker field while separating page assertions from verified quality and office fit.",
            "slot_ids": g1,
            "subgoal_ids": ["G1"],
            "required": True,
        },
        {
            "requirement_id": "Q2",
            "text": "Explain jurisdiction-specific chocolate, compound, couverture, fat and label concepts without classifying an exact SKU or offering universal legal advice from the frozen background.",
            "slot_ids": g2,
            "subgoal_ids": ["G2"],
            "required": True,
        },
        {
            "requirement_id": "Q3",
            "text": "State the dated matched identity, ingredient, net-quantity, pack, price and receipt evidence needed to decide recipe change, quality downgrade or shrinkflation and calculate comparable units only after normalization.",
            "slot_ids": g3,
            "subgoal_ids": ["G3"],
            "required": True,
        },
        {
            "requirement_id": "Q4",
            "text": "Use community reports only to motivate version checks, aggregate-versus-individual caution and matched serving temperature, not as proof about an exact chocolate offer.",
            "slot_ids": g4,
            "subgoal_ids": ["G4"],
            "required": True,
        },
        {
            "requirement_id": "Q5",
            "text": "Verify current physical identity, ingredients, allergens, dietary fit, market, lot, net quantity and delivered cost, then specify a small reversible brand-masked office trial with equal portions, matched temperature, controlled order and predeclared acceptance, consumption, repeat-choice and waste outcomes.",
            "slot_ids": g5,
            "subgoal_ids": ["G5"],
            "required": True,
        },
        {
            "requirement_id": "Q6",
            "text": "Select only the lowest-total-cost exact offer passing every current-label, safety, budget and local-trial gate; otherwise use an accepted control or defer without naming a universal winner or unsupported historical change.",
            "slot_ids": g6,
            "subgoal_ids": ["G6"],
            "required": True,
        },
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0046",
        "cluster_id": "office_candy_rating_recipe_and_shrinkflation_boundary",
        "difficulty": {
            "proof_depth": 4,
            "branching_factor": 6,
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
                    "rating_percentage_needs_denominator",
                    "seller_snapshot_is_not_history",
                    "jurisdiction_rules_do_not_classify_sku",
                    "unit_cost_requires_comparable_units",
                    "godiva_identity_and_mass_are_ambiguous",
                    "goldenberg_continuity_copy_is_unverified",
                    "community_anecdotes_do_not_transfer",
                    "current_label_and_office_safety_are_unresolved",
                    "historical_pair_must_match_version",
                    "small_trial_is_local_not_universal",
                    "lowest_cost_passing_or_defer",
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
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": 11,
            "minimum_reasoning_depth": 4,
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
