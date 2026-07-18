#!/usr/bin/env python3
"""Build the audited Q49 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "verify_exact_current_packages_and_guest_constraints_then_run_a_small_category_aware_blinded_tasting_and_choose_the_lowest_commitment_passing_lineup_or_control_reduce_or_defer"
WHEN = "the_packet_lacks_current_verified_packages_guest_constraints_and_matched_local_tasting_results"


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
BRIDGES = [f"B{index}" for index in range(1, 10)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "bean_to_liquor_process_boundary_v1": bridge(rules["bean_to_liquor_process_boundary_v1"]),
        "community_tasting_variable_scope_v1": bridge(rules["community_tasting_variable_scope_v1"]),
        "conching_texture_flavor_boundary_v1": bridge(rules["conching_texture_flavor_boundary_v1"]),
        "pack_mass_cost_normalization_boundary_v1": bridge(rules["pack_mass_cost_normalization_boundary_v1"]),
        "percentage_component_quality_boundary_v1": bridge(rules["percentage_component_quality_boundary_v1"]),
        "seller_sampler_offer_scope_v1": bridge(rules["seller_sampler_offer_scope_v1"]),
        "white_ruby_category_boundary_v1": bridge(rules["white_ruby_category_boundary_v1"]),
        "category_aware_tasting_protocol_v1": bridge(rules["category_aware_tasting_protocol_v1"]),
        "sampler_decision_preparation_v1": bridge(rules["sampler_decision_preparation_v1"]),
        "evidence_bounded_sampler_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["evidence_bounded_sampler_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no universal percentage ladder, automatic process premium or fake-versus-real verdict. Verify exact packages and guest constraints, run a small category-aware tasting and choose the lowest-commitment exact lineup passing identity, allergen, budget, category-coverage and local-acceptance gates; otherwise use a verified known control, reduce the lineup or defer.",
                    "Choose only the least-commitment verified lineup that clears identity, allergen, budget, educational category and local sensory gates, or use a verified control, shrink the lineup or defer without naming a universal product, percentage or category winner.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet freezes five seller listings, general bean-to-chocolate, conching, component and category context, and three scoped community pages, but lacks current delivered packages, complete labels and allergens for every offer, guest constraints, matched tasting results and a universal percentage-to-quality rule."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher("Treat every captured title, SKU, price, pack, mass, percentage, rating, review count, flavor and quality phrase as a frozen seller assertion rather than a current delivered label or independent taste result."),
                        "quantity_conflicts_remain_visible": matcher("Preserve the Green and Black eight-times-3.17-ounce versus 3.17-ounce conflict and the unresolved Lindt milk and Chocolove total-mass ambiguities."),
                        "arithmetic_is_conditional": matcher("Show price-per-bar and price-per-mass arithmetic only conditionally with every pack and mass assumption visible."),
                        "unlike_categories_are_separate": matcher("Do not turn white, milk, milk with almonds, dark and ruby products into one homogeneous percentage, price or quality ladder."),
                        "process_chain_is_general": matcher("Explain fermentation, drying, roasting, nibs, nonalcoholic chocolate liquor, cocoa solids and cocoa butter without assigning an unreported process history to an exact offer."),
                        "conching_is_not_monotonic_quality": matcher("Use conching as mixing, particle-coating, volatile-acid, moisture, texture and flavor context rather than a longer-is-always-better rule."),
                        "percentage_is_incomplete": matcher("A cocoa percentage or category name does not reveal the complete component balance, recipe, quality, bitterness, sweetness or preference."),
                        "white_is_definition_bounded": matcher("White chocolate contains cocoa butter without nonfat cocoa solids, while real-versus-fake claims remain bounded by market definitions and preferences."),
                        "ruby_is_disputed": matcher("Ruby remains a disputed category and marketing boundary; a seller title does not independently verify the exact formula or a fourth natural type."),
                        "community_evidence_is_scoped": matcher("Keep the blind-caramel plan, hot-cocoa recommendations and flavor-cue discussion at their author, product, place, time and preference scopes."),
                        "identity_allergen_checks_precede_serving": matcher("Verify current exact identity, pack, mass, price, ingredients, allergens, cocoa components, market, lot, storage and cross-contact before selection or serving."),
                        "exploration_and_comparison_are_separate": matcher("Use a category exploration for unlike forms and reserve any causal price or quality comparison for matched products."),
                        "tasting_controls_cues": matcher("For comparable samples, mask brand, package, price and marketing, randomize or counterbalance coded equal portions and standardize temperature and serving size."),
                        "difference_and_liking_are_separate": matcher("Record aroma, sweetness, bitterness, acidity, texture, melt, aftertaste, detected difference and overall liking separately."),
                        "predeclared_gates_control_choice": matcher("Predeclare guest count, budget, maximum lineup cost, minimum category coverage, acceptance threshold and identity, allergen, package and sensory stops."),
                        "lowest_commitment_or_control_reduce_defer": matcher("Choose the lowest-commitment verified passing lineup; otherwise use a verified known control, reduce the lineup or defer."),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_green_black_current", "B6", "The frozen Green and Black listing necessarily describes the current delivered package."),
        negative("wrong_green_black_mass_resolved", "B6", "The Green and Black page unambiguously proves that exactly 25.36 ounces will be delivered."),
        negative("wrong_green_black_selected_flavor", "B6", "The selected 70-percent flavor field proves that all eight Green and Black bars are 70-percent dark chocolate."),
        negative("wrong_lindt_white_mass", "B6", "The Lindt white listing establishes an exact delivered net mass even though no mass is shown."),
        negative("wrong_lindt_milk_total", "B6", "The Lindt milk page proves that each of two pieces weighs 4.4 ounces."),
        negative("wrong_chocolove_total", "B6", "The Chocolove page proves that each of two ruby bars weighs 3.1 ounces."),
        negative("wrong_ritter_rating_taste", "B6", "Ritter's 55-percent store rating over four reviews proves its objective taste quality."),
        negative("wrong_chocolove_rating_taste", "B6", "Chocolove's 78-percent store rating over twelve reviews proves guest preference."),
        negative("wrong_green_black_cheapest", "B4", "The Green and Black title automatically proves the cheapest complete tasting without package verification."),
        negative("wrong_lindt_piece_arithmetic", "B4", "The Lindt milk listing supports unconditional price-per-ounce arithmetic despite the two-piece mass ambiguity."),
        negative("wrong_chocolove_bar_arithmetic", "B4", "The Chocolove listing supports unconditional price per delivered bar and ounce."),
        negative("wrong_white_unit_price", "B4", "A price per ounce can be calculated for Lindt white even though the frozen page supplies no mass."),
        negative("wrong_unit_price_quality", "B4", "The lowest conditional price per ounce proves the best quality or guest value."),
        negative("wrong_bean_exact_history", "B1", "The general cocoa pages establish the exact fermentation, roast and bean history of every captured bar."),
        negative("wrong_liquor_alcohol", "B1", "Chocolate liquor is an alcoholic ingredient."),
        negative("wrong_nib_finished", "B1", "A cocoa nib is already finished sweetened chocolate with a verified exact recipe."),
        negative("wrong_conching_longer", "B3", "Longer conching always produces better chocolate and justifies a higher price."),
        negative("wrong_conching_exact_brand", "B3", "The generic conching page proves the duration, equipment and sensory outcome used for each exact offer."),
        negative("wrong_percentage_formula", "B5", "A cocoa percentage alone reveals the full amounts of cocoa solids, cocoa butter, sugar, milk and every other ingredient."),
        negative("wrong_percentage_bitterness", "B5", "An 85-percent label necessarily means more bitterness and better quality than every 70- or 61-percent product."),
        negative("wrong_mixed_ladder", "B5", "White, milk, almond, dark and ruby products form one comparable monotonic percentage-quality ladder."),
        negative("wrong_white_fake", "B7", "White chocolate is universally fake because it lacks nonfat cocoa solids."),
        negative("wrong_white_exact_formula", "B7", "The generic white-chocolate page independently verifies the exact Lindt ingredients and market compliance."),
        negative("wrong_ruby_fourth_type", "B7", "Ruby chocolate is an undisputed fourth natural cocoa type."),
        negative("wrong_ruby_exact_formula", "B7", "The Chocolove title proves its exact ruby formula and natural color mechanism."),
        negative("wrong_caramel_results", "B2", "The New Jersey blind caramel post contains completed results ranking the five captured chocolate bars."),
        negative("wrong_hot_cocoa_population", "B2", "The New Haven hot-cocoa recommendations establish a universal product preference."),
        negative("wrong_weather_causal", "B2", "One poster's cold-weather remark proves the causal effect of temperature on every guest's liking."),
        negative("wrong_eli5_authority", "B2", "The ELI5 flavor discussion is an authoritative controlled trial of the five exact products."),
        negative("wrong_unverified_serving", "B8", "The host may serve the frozen offers without checking ingredients, allergens, dietary rules or cross-contact."),
        negative("wrong_unmatched_blind_comparison", "B8", "A blinded comparison of unlike white, milk, almond, dark and ruby forms proves a causal price-quality ranking."),
        negative("wrong_difference_equals_liking", "B8", "Detecting a sensory difference proves which sample guests like more."),
        negative("wrong_brand_visible", "B8", "Showing brands, packages, prices and marketing cannot influence a tasting result."),
        negative("wrong_posthoc_gates", "B9", "The host may inspect the results first and then invent budget, coverage and liking gates that select a preferred winner."),
        negative("wrong_unresolved_allergen_compensated", "B9", "Strong liking can compensate for unresolved identity, allergens or cross-contact."),
        negative("wrong_immediate_winner", "D1", "The frozen packet already proves one unconditional brand, category and percentage winner."),
        negative("wrong_buy_all", "D1", "The host should buy every listing now even if package identity, allergens, budget or comparison validity remains unresolved."),
        negative("wrong_universal_fake_verdict", "D1", "The final decision should impose one universal real-versus-fake verdict on white and ruby chocolate."),
    ]

    g1 = ["E3", "E8", "E9", "E10", "E13", "B4", "B6"]
    g2 = ["E1", "E2", "E4", "E5", "E6", "B1", "B3"]
    g3 = ["E1", "E3", "E5", "E10", "E14", "E15", "B5", "B7"]
    g4 = ["E7", "E11", "E12", "B2"]
    g5 = ["E3", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E14", "E15", "B4", "B5", "B7", "B8"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit all five frozen offers, preserve every pack and mass conflict and show only conditional cost arithmetic without turning seller ratings into taste evidence.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B6"},
        {"subgoal_id": "G2", "description": "Explain the general bean-to-liquor chain and conching mechanisms while withholding unreported exact-product process histories and monotonic longer-is-better claims.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G3", "description": "Bound percentage, cocoa components, white-chocolate definitions and the disputed ruby category without inventing formulas or a cross-category quality ladder.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G4", "description": "Keep the blind-caramel plan, hot-cocoa recommendations and flavor-cue discussion at their author, product, place, time and preference scopes.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G5", "description": "Design a small category-aware tasting with exact identity and allergen checks, reversible quantities, cue masking, randomized comparable portions and separate sensory-difference and liking records.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B8"},
        {"subgoal_id": "G6", "description": "Apply predeclared identity, allergen, budget, category-coverage and local-acceptance gates and choose the lowest-commitment passing lineup, verified control, reduced lineup or deferral.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build the five-offer matrix, retain frozen and conflicting pack and mass fields and show conditional price-per-bar or mass arithmetic.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain beans, nibs, nonalcoholic chocolate liquor, cocoa solids, cocoa butter and conching, including what generic process pages cannot prove for exact products.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain the limits of percentage labels and the definition-bounded white and disputed ruby categories without a homogeneous quality ladder.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Use the three community pages only as scoped anecdotes and tasting-design prompts, not as results or population evidence.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify exact package, ingredient, allergen and guest checks plus a category-aware blinded tasting separating exploration, matched comparison, detected difference and liking.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a predeclared lowest-commitment lineup, control, reduction or deferral decision without naming a universal product, percentage, category or fake-versus-real winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0049",
        "cluster_id": "chocolate_process_category_sampler_boundary",
        "difficulty": {"proof_depth": 4, "branching_factor": 15, "distractor_density": 0.38, "contradiction_count": 4},
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
                    "quantity_conflicts_remain_visible",
                    "arithmetic_is_conditional",
                    "unlike_categories_are_separate",
                    "process_chain_is_general",
                    "conching_is_not_monotonic_quality",
                    "percentage_is_incomplete",
                    "white_is_definition_bounded",
                    "ruby_is_disputed",
                    "community_evidence_is_scoped",
                    "identity_allergen_checks_precede_serving",
                    "exploration_and_comparison_are_separate",
                    "tasting_controls_cues",
                    "difference_and_liking_are_separate",
                    "predeclared_gates_control_choice",
                    "lowest_commitment_or_control_reduce_defer",
                ],
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": 15,
            "minimum_reasoning_depth": 4,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
