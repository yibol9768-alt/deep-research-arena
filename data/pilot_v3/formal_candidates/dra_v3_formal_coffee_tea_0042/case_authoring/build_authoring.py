#!/usr/bin/env python3
"""Build the audited Q42 tea taste-per-dollar CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "authoring.json"
CASE_SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "resolve_exact_variants_run_separate_matched_format_and_personal_preference_trials_then_choose_the_cheapest_option_that_passes_the_taste_and_effective_cost_gates_keep_bags_or_defer"
WHEN = "the_packet_lacks_resolved_exact_variants_comparable_dose_yield_and_controlled_taste_results"


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


EVIDENCE = [f"E{index}" for index in range(1, 13)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(CASE_SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "seller_offer_and_measurement_scope_v1": bridge(
            rules["seller_offer_and_measurement_scope_v1"]
        ),
        "tea_quality_format_boundary_v1": bridge(
            rules["tea_quality_format_boundary_v1"]
        ),
        "brewing_and_sensory_control_v1": bridge(
            rules["brewing_and_sensory_control_v1"]
        ),
        "community_preference_setup_scope_v1": bridge(
            rules["community_preference_setup_scope_v1"]
        ),
        "matched_format_and_personal_trial_v1": bridge(
            rules["matched_format_and_personal_trial_v1"]
        ),
        "accepted_cup_cost_and_threshold_v1": bridge(
            rules["accepted_cup_cost_and_threshold_v1"]
        ),
        "evidence_bounded_tea_value_purchase_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                rules["evidence_bounded_tea_value_purchase_v1"]
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Resolve exact tea variants, net mass, delivered cost, availability, dose, equipment, and accepted-cup yield; run a matched plain format trial and a separately labeled personal-preference trial; then choose the cheapest exact tea clearing the taste and 0.20-dollar incremental accepted-cup cap, otherwise keep the bag baseline or defer.",
                    "Buy only the least costly exact option that clears identity, availability, fixed-brew, seven-of-ten blind preference, one-point median score, no-defect, and effective-cost gates; if none clears, stay with bags, and defer when a material field is unresolved.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains four frozen unmatched seller offers, general processing, grading, CTC, and black-tea brewing context, and four scoped community pages, but no resolved Nina's net mass, confirmed checkout variants, matched tea pair, measured dose and accepted-cup yield, or controlled blind preference result for any exact option."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_require_exact_measurement": matcher(
                            "Seller titles, SKUs, prices, ratings, review counts, counts, masses, styles, flavor copy, and brew wording are frozen offer fields; Nina's 2.8-ounce title conflicts with the 3.5-ounce or 100-gram body, and every exact variant, net tea mass, delivered cost, dose, and yield must be verified."
                        ),
                        "format_is_not_a_quality_order": matcher(
                            "Cultivar, plucked-leaf quality, processing, blending, flavorants, grade, and particle size can affect tea, while expensive fannings may be more flavorful than cheaper whole leaf, so loose leaf, bags, tins, price, and grade have no universal taste ordering."
                        ),
                        "ctc_context_is_not_exact_product_proof": matcher(
                            "CTC is generally suited to quick dark tea-bag brews, but that context does not prove the exact Twinings process or preference, and dose, water, temperature, time, vessel, additions, serving temperature, cup code, and order must be controlled."
                        ),
                        "community_pages_are_scoped_inputs": matcher(
                            "The favorite-tea kettle incident, inconsistent chai report, infuser-shopping question, and loose-tea availability question remain individual examples that suggest confound, consistency, equipment, and access checks rather than rates, tests, or product verdicts."
                        ),
                        "causal_and_personal_questions_need_separate_trials": matcher(
                            "Use a closest-feasible plain matched bag and loose pair to test format itself, and separately compare the actual differently flavored candidates only as a personal purchase preference without generalizing the result to format."
                        ),
                        "taste_gate_is_predeclared": matcher(
                            "Across ten randomized or counterbalanced blinded pairs, require at least seven preferences, a median overall-score gain of at least one point on a five-point scale, and no recurring material defect before calling a candidate taste-superior for this drinker."
                        ),
                        "effective_cost_uses_accepted_cups": matcher(
                            "Effective cost per accepted cup includes delivered tea, allocated required equipment, measured grams per brew, successful resteeps, and failed or discarded brews, divided by accepted cups actually produced rather than advertised counts or sticker price."
                        ),
                        "incremental_cost_cap_controls_upgrade": matcher(
                            "The candidate's effective cost may exceed the Twinings baseline by no more than 0.20 dollars per accepted cup, with weekly and monthly cost projected at four or five cups per day from measured yield."
                        ),
                        "cheapest_passing_bags_or_defer": matcher(
                            "Choose the cheapest exact available option clearing every identity, brew, taste, defect, and cost gate; do not pay for Nina's if a middle-price option passes, keep bags if none passes, and defer wherever a material cell remains unresolved."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative(
            "wrong_ninas_title_resolves_mass",
            "B4",
            "Nina's 2.8-ounce title is the verified net tea mass, so the 3.5-ounce and 100-gram body fields can be ignored.",
        ),
        negative(
            "wrong_ninas_rating_proves_premium_taste",
            "B4",
            "Nina's 87-percent store aggregate over three reviews independently proves premium taste and value.",
        ),
        negative(
            "wrong_t2_selector_confirms_variant",
            "B4",
            "The T2 variant selector proves that the 16.50-dollar checkout choice is the exact 100-gram loose-leaf box and that no variant confirmation is needed.",
        ),
        negative(
            "wrong_hyleys_tin_proves_quality",
            "B4",
            "The Hyleys loose-leaf tin format proves either premium quality or poor quality without tasting it.",
        ),
        negative(
            "wrong_twinings_rating_proves_bad_taste",
            "B4",
            "Twinings' 48-percent store aggregate proves every current bag tastes bad to this drinker.",
        ),
        negative(
            "wrong_sticker_price_comparison",
            "B6",
            "A 100-count bag price can be directly compared with a 100-gram loose-tea price without measuring tea mass per cup, resteeps, rejected brews, or accepted yield.",
        ),
        negative(
            "wrong_loose_leaf_always_better",
            "B3",
            "Loose-leaf tea is always more flavorful and higher quality than tea bags.",
        ),
        negative(
            "wrong_tin_is_taste_mechanism",
            "B3",
            "A metal or reusable tin itself proves that the tea tastes better than a boxed or bagged offer.",
        ),
        negative(
            "wrong_whole_leaf_always_beats_fannings",
            "B3",
            "Whole leaf is always more flavorful and more valuable than fannings regardless of the underlying tea and price tier.",
        ),
        negative(
            "wrong_ctc_proves_twinings_process",
            "B1",
            "Because CTC tea is often used in bags, the exact Twinings bags are proven to use CTC and to have generic flavor and mild bitterness.",
        ),
        negative(
            "wrong_iso_is_everyday_recipe",
            "B1",
            "ISO 3103 is the universally proper everyday brewing recipe and therefore the only acceptable way to drink these teas.",
        ),
        negative(
            "wrong_longer_steep_is_better",
            "B1",
            "A longer steep always produces a fairer and better cup regardless of particle size or bitterness.",
        ),
        negative(
            "wrong_kettle_story_is_rate",
            "B2",
            "The vinegar-kettle incident proves that perceived tea changes are generally caused by dirty kettles.",
        ),
        negative(
            "wrong_chai_story_tests_offers",
            "B2",
            "One author's hit-or-miss chai report is a controlled consistency test of the four exact offers.",
        ),
        negative(
            "wrong_infuser_thread_gives_cost",
            "B2",
            "The Boston infuser question establishes the exact equipment required and its price for this buyer.",
        ),
        negative(
            "wrong_providence_thread_proves_stock",
            "B2",
            "The Providence shop suggestions prove current loose-tea stock, sample sizes, prices, and quality.",
        ),
        negative(
            "wrong_unmatched_offers_isolate_format",
            "B5",
            "Comparing apple-and-rose, pancake-like or cinnamon, strawberry-and-cranberry, and plain English Breakfast cups directly isolates the causal effect of loose leaf versus bags.",
        ),
        negative(
            "wrong_personal_trial_proves_format",
            "B5",
            "A preference for one unmatched candidate proves that loose leaf is universally better than bags.",
        ),
        negative(
            "wrong_one_pair_guarantees_future",
            "B5",
            "One preferred cup establishes stable personal preference and guarantees every future lot.",
        ),
        negative(
            "wrong_advertised_cups_are_accepted_yield",
            "B6",
            "Advertised bag count or package mass is the number of accepted cups without measuring dose, successful resteeps, waste, or rejected brews.",
        ),
        negative(
            "wrong_premium_tin_winner",
            "D1",
            "Buy Nina's because the premium price and tin make it the universal taste-per-dollar winner.",
        ),
        negative(
            "wrong_no_trial_middle_tier",
            "D1",
            "Select the middle-price T2 offer from sticker price alone without resolving the exact variant or applying the taste and effective-cost gates.",
        ),
    ]

    g1 = ["E4", "E9", "E11", "E12", "B4"]
    g2 = ["E7", "E10", "B3"]
    g3 = ["E1", "E3", "B1"]
    g4 = ["E2", "E5", "E6", "E8", "B2"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5"]
    g6 = PROOF
    subgoals = [
        {
            "subgoal_id": "G1",
            "description": "Audit all four frozen seller pages, retain exact offer fields, resolve Nina's net-content conflict and every selected variant, and refuse ratings, tins, loose-leaf wording, counts, or sticker prices as independent taste or accepted-cup value proof.",
            "critical": True,
            "requires": g1,
            "local_conclusion_slot_id": "B4",
        },
        {
            "subgoal_id": "G2",
            "description": "Use processing and grading evidence to identify real flavor axes while explaining why leaf form, grade, bag, tin, and price do not create a universal quality ordering or rank the exact offers.",
            "critical": True,
            "requires": g2,
            "local_conclusion_slot_id": "B3",
        },
        {
            "subgoal_id": "G3",
            "description": "Keep CTC statements at general mechanism scope and define the measured dose, water, temperature, time, vessel, additions, serving, coding, and order controls needed for meaningful black-tea sensory comparison.",
            "critical": True,
            "requires": g3,
            "local_conclusion_slot_id": "B1",
        },
        {
            "subgoal_id": "G4",
            "description": "Keep the favorite-tea kettle incident, chai variability report, infuser question, and availability question at individual scope while extracting only preparation, consistency, equipment, and access fields to verify.",
            "critical": True,
            "requires": g4,
            "local_conclusion_slot_id": "B2",
        },
        {
            "subgoal_id": "G5",
            "description": "Separate the causal format question from the personal purchase question and design a closest-feasible plain matched trial plus a separately labeled ten-pair blind test of the actual unmatched candidates with predeclared taste and defect gates.",
            "critical": True,
            "requires": g5,
            "local_conclusion_slot_id": "B5",
        },
        {
            "subgoal_id": "G6",
            "description": "Measure dose, resteeps, accepted cups, waste, equipment, and delivered cost, apply the 0.20-dollar incremental accepted-cup cap at four or five cups daily, and choose the cheapest exact passing tea, keep bags, or defer without a universal format winner.",
            "critical": True,
            "requires": g6,
            "local_conclusion_slot_id": "D1",
        },
    ]
    requirements = [
        {
            "requirement_id": "Q1",
            "text": "Audit the four exact seller offers and separate every supported SKU, variant, price, aggregate, review count, count, mass, style, flavor, and brew statement from unresolved net content, delivered cost, dose, accepted yield, and independent taste evidence.",
            "slot_ids": g1,
            "subgoal_ids": ["G1"],
            "required": True,
        },
        {
            "requirement_id": "Q2",
            "text": "Explain how cultivar, leaf quality, processing, blending, flavorants, grading, and particle size may affect tea while rejecting a universal loose-leaf, bag, tin, price, grade, or whole-leaf ordering.",
            "slot_ids": g2,
            "subgoal_ids": ["G2"],
            "required": True,
        },
        {
            "requirement_id": "Q3",
            "text": "Explain what CTC and black-tea brewing evidence establishes and specify fixed measured brew and sensory-comparison controls without treating ISO 3103 as the proper everyday recipe or assigning CTC to an exact product without evidence.",
            "slot_ids": g3,
            "subgoal_ids": ["G3"],
            "required": True,
        },
        {
            "requirement_id": "Q4",
            "text": "Use all four community pages only as scoped preference, preparation-confound, consistency, equipment, and availability inputs, not as prevalence, controlled trials, exact prices, current inventory, or product verdicts.",
            "slot_ids": g4,
            "subgoal_ids": ["G4"],
            "required": True,
        },
        {
            "requirement_id": "Q5",
            "text": "Design two explicitly different reversible trials: a closest-feasible plain matched bag-versus-loose trial for format causality and a separately labeled ten-pair blinded personal-preference trial for the actual unmatched drinks with seven-of-ten, one-point, and no-defect gates.",
            "slot_ids": g5,
            "subgoal_ids": ["G5"],
            "required": True,
        },
        {
            "requirement_id": "Q6",
            "text": "Calculate effective and incremental cost per accepted cup from delivered tea, required equipment, measured dose, successful resteeps, and discarded brews; project four or five daily cups; and choose the cheapest exact option clearing every gate, keep bags, or defer under the 0.20-dollar cap.",
            "slot_ids": g6,
            "subgoal_ids": ["G6"],
            "required": True,
        },
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_coffee_tea_0042",
        "cluster_id": "tea_loose_leaf_bag_taste_per_dollar_boundary",
        "difficulty": {
            "proof_depth": 4,
            "branching_factor": 6,
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
                    "seller_fields_require_exact_measurement",
                    "format_is_not_a_quality_order",
                    "ctc_context_is_not_exact_product_proof",
                    "community_pages_are_scoped_inputs",
                    "causal_and_personal_questions_need_separate_trials",
                    "taste_gate_is_predeclared",
                    "effective_cost_uses_accepted_cups",
                    "incremental_cost_cap_controls_upgrade",
                    "cheapest_passing_bags_or_defer",
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
            "human_solve_minutes": 45,
            "minimum_required_evidence_nodes": 12,
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
