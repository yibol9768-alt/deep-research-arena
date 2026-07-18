#!/usr/bin/env python3
"""Build the audited Q44 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_cheapest_exact_gift_path_that_passes_all_budget_recipient_delivery_and_taste_gates_or_buy_a_small_known_85_percent_reference_or_defer"
WHEN = "the_packet_lacks_current_delivered_totals_complete_dark_piece_recipe_and_safety_fields_and_a_matched_recipient_tasting"


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


EVIDENCE = [f"E{index}" for index in range(1, 14)]
BRIDGES = [f"B{index}" for index in range(1, 8)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "seller_bar_origin_percentage_scope_v1": bridge(
            rules["seller_bar_origin_percentage_scope_v1"]
        ),
        "seller_truffle_box_scope_v1": bridge(
            rules["seller_truffle_box_scope_v1"]
        ),
        "percentage_composition_boundary_v1": bridge(
            rules["percentage_composition_boundary_v1"]
        ),
        "origin_processing_flavor_boundary_v1": bridge(
            rules["origin_processing_flavor_boundary_v1"]
        ),
        "truffle_format_recipient_fit_boundary_v1": bridge(
            rules["truffle_format_recipient_fit_boundary_v1"]
        ),
        "community_gift_price_preference_scope_v1": bridge(
            rules["community_gift_price_preference_scope_v1"]
        ),
        "matched_gift_matrix_tasting_v1": bridge(
            rules["matched_gift_matrix_tasting_v1"]
        ),
        "evidence_bounded_dark_chocolate_gift_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                rules["evidence_bounded_dark_chocolate_gift_v1"]
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Treat origin and cacao percentage as meaningful but incomplete metadata, preserve product-form and seller-label conflicts, and choose only the cheapest exact gift path that passes budget, recipient darkness, format, ingredient, allergen, delivery and matched-taste gates; otherwise use a small known 85-percent reference or defer.",
                    "Reject ratings, awards, larger-box presentation, origin and percentage labels as automatic recipient-fit proof; select the least costly exact gift only after every predeclared gate passes, and otherwise buy a known 85-percent calibration reference or defer without a universal winner.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains five frozen seller snapshots, general percentage, origin, fermentation, variety and truffle context, and three scoped community discussions, but lacks current delivered totals and arrival verification, complete dark-piece, ingredient, allergen and alcohol fields for every offer, and a matched recipient tasting."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher(
                            "Seller titles, SKUs, prices, ratings, review counts, masses, counts, origin, percentage, flavor and gift descriptions remain frozen assertions rather than independent composition, traceability, taste or recipient-fit proof."
                        ),
                        "valrhona_conflict_is_unresolved": matcher(
                            "The Valrhona page's 65-percent title and quick-look wording conflict with its 64-percent Manjari option, so the exact percentage must remain unresolved until independently verified."
                        ),
                        "percentage_is_incomplete_metadata": matcher(
                            "Cacao percentage combines chocolate liquor and cocoa butter without disclosing their split, and identical percentages can have different compositions, so percentage cannot directly rank flavor or recipient fit."
                        ),
                        "origin_and_process_are_multi_axis": matcher(
                            "Origin can scope real variation while genetics, growing conditions, fermentation, drying, roasting, recipe and processing also affect possible flavor, and no single label predicts the recipient's ranking."
                        ),
                        "traditional_variety_terms_are_marketing": matcher(
                            "Traditional Criollo, Forastero and Trinitario terms remain marketing language rather than current botanical proof of an exact product's genotype or quality."
                        ),
                        "truffle_mass_is_not_acceptable_dark_share": matcher(
                            "A filled and coated truffle is not equivalent to a plain dark-bar portion, so box mass and piece count do not establish recipient-acceptable dark servings without shell, filling, percentage, ingredient, allergen and alcohol details."
                        ),
                        "community_statements_are_scoped": matcher(
                            "Gift success, flavor-variety, price-per-ounce and sweetness comments remain author-, business-, product-, time- and preference-scoped rather than controlled tests, current rates or exact-offer verdicts."
                        ),
                        "delivery_and_safety_fields_are_unresolved": matcher(
                            "Current delivered cost, stock, arrival, heat protection, storage, remedy terms, full ingredients, allergens and alcohol must be verified before purchase."
                        ),
                        "true_cost_uses_acceptable_servings": matcher(
                            "Compare cost per recipient-acceptable dark serving after shipping, unwanted assortment and waste rather than sticker price, total mass or box count alone."
                        ),
                        "small_tasting_is_recipient_specific": matcher(
                            "A small blinded or randomized equal-portion tasting against the recipient's known 85-percent reference reduces current preference uncertainty but does not prove a universal origin, percentage, brand or future-lot winner."
                        ),
                        "cheapest_passing_reference_or_defer": matcher(
                            "Choose only the cheapest exact gift path passing every budget, recipient, recipe, ingredient, allergen, delivery and taste gate; otherwise use a small known 85-percent reference or defer."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_valrhona_65_resolved", "B4", "The Valrhona listing conclusively proves that the exact Manjari bar is 65 percent despite the same page listing Manjari as 64 percent."),
        negative("wrong_rating_proves_recipient_fit", "B4", "A 100-percent store aggregate over one or two reviews independently proves that the exact bar will suit this 85-percent dark-chocolate recipient."),
        negative("wrong_box_rating_proves_fit", "B5", "The Cravings box's 92-percent aggregate proves that its mixed shells and fillings are the better gift for this recipient."),
        negative("wrong_percentage_is_quality_rank", "B3", "A higher cacao percentage always means higher chocolate quality and better flavor."),
        negative("wrong_70_closest_to_85_wins", "B3", "The 70-percent bar automatically wins because its number is closest among the candidates to the recipient's usual 85-percent bar."),
        negative("wrong_dark_milk_equals_plain_dark", "B3", "A 60-percent dark-milk bar is directly equivalent to a plain 60-percent or 85-percent dark bar for recipe and taste comparison."),
        negative("wrong_single_origin_guarantees_flavor", "B2", "A single-origin country label guarantees one bean genotype and a predetermined superior flavor."),
        negative("wrong_criollo_is_botanical_proof", "B2", "The Quma seller's Criollo wording botanically proves the exact bar's genotype and quality."),
        negative("wrong_origin_is_only_flavor_axis", "B2", "Origin alone determines chocolate flavor, so fermentation, drying, roasting, recipe and processing can be ignored."),
        negative("wrong_fermentation_history_known", "B2", "General fermentation mechanisms establish the exact fermentation duration and flavor result of all three captured bars."),
        negative("wrong_lindt_all_dark", "B5", "The Lindt box's approximately 36 pieces are all dark chocolate suitable for an 85-percent dark-chocolate recipient."),
        negative("wrong_cravings_fillings_irrelevant", "B6", "The Cravings box's Amaretto, Champagne, nut and other fillings require no ingredient, allergen or alcohol check."),
        negative("wrong_big_box_is_more_generous", "B6", "A larger or more luxurious box is necessarily more generous for this recipient regardless of its usable dark-chocolate share."),
        negative("wrong_truffle_equals_bar", "B6", "A filled truffle piece is nutritionally and sensorially interchangeable with an equal-mass plain dark-bar segment."),
        negative("wrong_jersey_comment_is_box_test", "B1", "One Jersey City comment that truffle gifts went over well is a controlled test of the two exact captured boxes for this sister."),
        negative("wrong_pennsylvania_identity_resolved", "B1", "The Pennsylvania thread conclusively identifies the remembered chocolate company and verifies its current products."),
        negative("wrong_lpt_price_is_current_rate", "B1", "One milk-chocolate-chip comparison establishes the current price-per-ounce ranking of the five exact offers."),
        negative("wrong_sticker_price_is_true_cost", "B7", "Sticker price alone establishes the cheapest useful gift even when shipping, unwanted pieces and waste differ."),
        negative("wrong_piece_count_is_dark_servings", "B7", "Total piece count directly equals recipient-acceptable dark servings without checking shell, filling and percentage."),
        negative("wrong_one_taste_is_universal", "B7", "One unblinded bite proves a universal origin and cacao-percentage ranking and guarantees every future lot."),
        negative("wrong_product_page_proves_delivery", "D1", "The frozen product pages prove current stock, delivered total, birthday arrival, heat protection and replacement terms."),
        negative("wrong_buy_despite_missing_safety", "D1", "The buyer should purchase the biggest box even if ingredient, allergen, alcohol and dark-share fields remain unresolved."),
        negative("wrong_universal_bar_or_box_winner", "D1", "Single-origin bars always beat assorted truffle boxes, or assorted truffle boxes always beat single-origin bars, for every dark-chocolate lover."),
    ]

    g1 = ["E5", "E11", "E12", "E13", "B3", "B4"]
    g2 = ["E1", "E4", "E8", "B5", "B6"]
    g3 = ["E2", "E3", "E5", "E6", "E11", "E12", "E13", "B2"]
    g4 = ["E7", "E9", "E10", "B1"]
    g5 = EVIDENCE + BRIDGES
    g6 = PROOF
    subgoals = [
        {
            "subgoal_id": "G1",
            "description": "Audit the three exact bar snapshots, retain the Manjari 64-versus-65-percent conflict, distinguish plain dark, dark-milk and added-ingredient forms, and explain why percentage and seller ratings do not directly rank quality or recipient fit.",
            "critical": True,
            "requires": g1,
            "local_conclusion_slot_id": "B4",
        },
        {
            "subgoal_id": "G2",
            "description": "Audit the two exact assorted-truffle boxes and truffle structure, then identify the dark-share, shell, filling, ingredient, allergen and alcohol fields required before box size or count can represent recipient-useful generosity.",
            "critical": True,
            "requires": g2,
            "local_conclusion_slot_id": "B6",
        },
        {
            "subgoal_id": "G3",
            "description": "Explain how origin, genetics, growing conditions, fermentation, drying, roasting, recipe and processing can produce real flavor variation while refusing deterministic origin, percentage or traditional-variety label claims.",
            "critical": True,
            "requires": g3,
            "local_conclusion_slot_id": "B2",
        },
        {
            "subgoal_id": "G4",
            "description": "Keep the three community discussions at their author, business, product, time, price and preference scopes while extracting only gift, assortment, cost, sweetness and format variables to verify.",
            "critical": True,
            "requires": g4,
            "local_conclusion_slot_id": "B1",
        },
        {
            "subgoal_id": "G5",
            "description": "Combine every evidence branch into an exact-offer matrix, current delivery and safety audit, cost-per-acceptable-dark-serving calculation, and small matched tasting against the recipient's known 85-percent reference.",
            "critical": True,
            "requires": g5,
            "local_conclusion_slot_id": "B7",
        },
        {
            "subgoal_id": "G6",
            "description": "Choose only the cheapest exact gift path passing all budget, recipient darkness, format, ingredient, allergen, delivery and taste gates, or use a small known 85-percent reference or defer without a universal bar, box, origin or percentage winner.",
            "critical": True,
            "requires": g6,
            "local_conclusion_slot_id": "D1",
        },
    ]
    requirements = [
        {
            "requirement_id": "Q1",
            "text": "Audit the three exact bars and separate seller price, rating, review, mass, origin, percentage and flavor statements from verified composition and recipient-fit evidence, retaining the Manjari 64-versus-65-percent inconsistency.",
            "slot_ids": g1,
            "subgoal_ids": ["G1"],
            "required": True,
        },
        {
            "requirement_id": "Q2",
            "text": "Audit both exact truffle boxes and explain why total mass and count do not establish useful dark servings without shell, filling, percentage, ingredient, allergen and alcohol details.",
            "slot_ids": g2,
            "subgoal_ids": ["G2"],
            "required": True,
        },
        {
            "requirement_id": "Q3",
            "text": "Explain the real but limited roles of cacao percentage, origin, genetics, fermentation, drying, roasting, recipe and processing, and keep traditional cocoa-variety terms at marketing rather than botanical-proof scope.",
            "slot_ids": g3,
            "subgoal_ids": ["G3"],
            "required": True,
        },
        {
            "requirement_id": "Q4",
            "text": "Use the three community discussions only as scoped gift, assortment, price, sweetness and format statements, not as tests, rates, exact-offer histories or recipient verdicts.",
            "slot_ids": g4,
            "subgoal_ids": ["G4"],
            "required": True,
        },
        {
            "requirement_id": "Q5",
            "text": "Build an exact-offer matrix, verify current delivered cost, stock, arrival, heat protection, storage and remedies, compute cost per acceptable dark serving, and specify a matched reversible tasting against the recipient's known 85-percent reference.",
            "slot_ids": g5,
            "subgoal_ids": ["G5"],
            "required": True,
        },
        {
            "requirement_id": "Q6",
            "text": "Recommend only the cheapest exact gift path passing every budget, recipient, recipe, ingredient, allergen, delivery and taste gate; otherwise use a known 85-percent reference or defer without naming a universal winner.",
            "slot_ids": g6,
            "subgoal_ids": ["G6"],
            "required": True,
        },
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0044",
        "cluster_id": "dark_chocolate_origin_percentage_gift_boundary",
        "difficulty": {
            "proof_depth": 3,
            "branching_factor": 7,
            "distractor_density": 0.3,
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
                    "seller_fields_are_scoped",
                    "valrhona_conflict_is_unresolved",
                    "percentage_is_incomplete_metadata",
                    "origin_and_process_are_multi_axis",
                    "traditional_variety_terms_are_marketing",
                    "truffle_mass_is_not_acceptable_dark_share",
                    "community_statements_are_scoped",
                    "delivery_and_safety_fields_are_unresolved",
                    "true_cost_uses_acceptable_servings",
                    "small_tasting_is_recipient_specific",
                    "cheapest_passing_reference_or_defer",
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
            "human_solve_minutes": 50,
            "minimum_required_evidence_nodes": 13,
            "minimum_reasoning_depth": 3,
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
