#!/usr/bin/env python3
"""Build the audited Q40 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_cheapest_exact_coffee_that_passes_date_package_consumption_brew_cost_and_taste_gates_or_buy_a_small_fresh_reference_or_defer"
WHEN = "the_packet_lacks_verified_exact_lot_dates_package_and_storage_history_and_a_matched_controlled_tasting"


def matcher(*phrases: str) -> dict[str, object]:
    return {"matcher": "normalized_text", "accepted_phrases": list(phrases), "normalizers": NORMALIZERS}


def bridge(phrase: str) -> dict[str, object]:
    return {"type": "bridge", **matcher(phrase)}


def negative(claim_id: str, slot_id: str, phrase: str) -> dict[str, object]:
    return {"claim_id": claim_id, "contradicts_slot_id": slot_id, "critical": True, "rejected_matcher": matcher(phrase)}


EVIDENCE = [f"E{index}" for index in range(1, 13)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    rule_definitions = {
        "seller_rating_and_fresh_copy_scope_v1": bridge(
            "The four shopping pages are exact frozen seller snapshots. Onyx SKU B08GFG99W8 is 50.75 dollars, whole bean, and rated 100 percent over one review; Dallmayr SKU B00G3ECDJ8 is 56.38 dollars for six 17.6-ounce ground-coffee packs and rated 96 percent over 115 reviews; Siroman SKU B083TPKS3Q is 17.05 dollars for the selected 12-ounce whole-bean variant, rated 97 percent over seven reviews, and described as fresh boarder roasted; Segafredo SKU B084JHKDLC is 32.99 dollars for thirty single-serve pods, rated 100 percent over four reviews, and claims its filter-cup design preserves aroma and flavor. Those fields establish seller assertions and aggregates only. They do not supply verified roast or pack dates, lot age, individual review recency or matching, seal integrity, warehouse and transit history, oxygen exposure, time since opening, controlled sensory results, or a universal brand ranking."
        ),
        "roast_chemistry_and_staling_boundary_v1": bridge(
            "The roasting page says roasting changes green beans chemically and physically, creates characteristic flavor through Maillard and other reactions, and that green coffee is more stable than roasted beans. Its packaging section says protecting roasted coffee from heat, oxygen, and light extends shelf life, gives typical rather than exact freshness windows, distinguishes whole bean from ground coffee, and says preservation methods retard staling. The coffee-bean page says volatile and nonvolatile compounds contribute to flavor and that nitrogenous compounds and carbohydrates help create roasted-coffee aroma. Together these make freshness and exposure a chemically plausible sensory axis, but they do not reveal the age, storage history, remaining aroma, acceptable taste, or discard date of any exact offer."
        ),
        "package_valve_and_history_boundary_v1": bridge(
            "The coffee-bag page says consumer coffee may be sold as beans or grounds in sealed plastic bags, carbon dioxide can build in barrier bags, and pressure-relief valves can release pressure without admitting atmosphere. The food-packaging page describes protection from chemical, biological, and physical alteration, oxygen and water-vapor barriers, and keeping contents fresh for an intended shelf life. These are packaging functions, not observations of an exact package. A bag or pod format and a valve or aroma-preservation claim do not prove roast date, seal integrity, gas composition, barrier performance, storage temperature, light exposure, transit time, opening history, or current sensory quality; those fields require exact-lot verification."
        ),
        "community_freshness_statement_scope_v1": bridge(
            "The New Hampshire thread asks for fresh light-roasted beans and includes a commenter saying one shop seems to roast almost daily and sell out, making freshness easy to confirm, while noting the price. The Rhode Island thread asks for freshly roasted beans and contains different personal statements: a five-pound subscription is said to remain good over three months, one small-batch source is called freshest because it never sits on a grocery shelf, and imported grower-roasted beans are acknowledged as possibly less fresh. The Washington thread asks for lower-priced five-pound bags and one commenter calls a Costco option not as fresh while still calling it great coffee. These author-scoped recommendations and impressions identify date, turnover, package size, price, and consumption variables; they are not blind tests, chemical measurements, prevalence estimates, warehouse-age evidence, or verdicts on the four exact offers."
        ),
        "multi_axis_quality_and_matched_comparison_v1": bridge(
            "Freshness cannot be isolated by comparing unmatched products and brew formats. The economics page says flavor, aroma, body, acidity, and texture differ by region and depend on varietal and processing; the roasting page also describes origin, roast-profile, and roast-degree effects. Therefore whole bean, preground multipacks, and pods must be recorded separately, and any sensory comparison must control coffee dose, water, temperature, grind, brewer, extraction, cup, time since grinding and opening, and tasting order. Freshness can matter while origin, varietal, processing, roast profile, grind, brew execution, package format, and preference also change perceived quality."
        ),
        "exact_lot_matrix_and_controlled_trial_v1": bridge(
            "For every current exact offer, record seller and SKU, coffee form, origin and varietal if supported, processing and roast profile if supported, package count and mass, price and shipping, rating and review count as seller fields, roast date, pack date, best-by date, lot identifier, seal and valve design, opening date, storage path and temperature, seller protection, planned consumption rate, waste risk, compatible grind and brewer, and cost per acceptable consumed serving. Buy only a small reversible quantity when possible. Compare it against a dated fresh reference with the same dose, water, temperature, grind, brewer, extraction, cup, resting time, and randomized or blinded order; repeat enough cups to apply predeclared aroma, flavor, defect, preference, waste, and budget thresholds. A short trial establishes current preference under tested conditions, not a universal freshness window or future-lot guarantee."
        ),
        "evidence_bounded_freshness_purchase_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                "The packet supports neither a near-perfect-rating winner nor the claim that all large brands are warehouse-stale. Treat freshness as a real but non-exclusive quality axis. Reject star aggregates, fresh wording, pod or valve presence, and community impressions as exact-lot proof. Verify dates, lot, package and storage history, compare cost per acceptable consumed serving, and run a controlled small-quantity tasting against a dated fresh reference while holding brew variables constant. Choose only the cheapest exact coffee that clears every date, package, consumption, brew, cost, and taste gate; otherwise buy a small dated fresh reference for calibration or defer. Do not name a universal brand, format, roast-age cutoff, or freshness-only winner."
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Treat freshness as a real but non-exclusive coffee-quality axis, then choose only the cheapest exact coffee that passes verified date, lot, package, storage, consumption, brew, true-cost, and controlled-taste gates; otherwise buy a small dated fresh reference for calibration or defer.",
                    "Reject ratings, fresh wording, package format, valves, and community impressions as exact-lot proof; select the least costly exact coffee only after every predeclared gate passes, and otherwise use a dated fresh reference or defer without a universal winner."
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains four frozen seller snapshots, general roast, compound, bag and packaging context, and three scoped community discussions, but no verified exact-lot date, package and storage history, matched review sample, or controlled tasting for any exact offer."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_not_exact_lot_proof": matcher(
                            "Seller titles, prices, ratings, review counts, flavor descriptions, fresh-roast wording, and aroma-preservation statements are frozen assertions and aggregates, not verified dates, lot age, seal tests, warehouse history, or independent sensory measurements."
                        ),
                        "typical_staling_context_is_not_an_exact_clock": matcher(
                            "Roast chemistry and typical whole-bean or ground-coffee staling windows make freshness plausible but cannot assign an exact offer an age, remaining aroma, acceptable taste, or universal discard time."
                        ),
                        "generic_package_functions_are_not_package_history": matcher(
                            "Generic barrier, sealing, valve, and food-packaging functions do not establish an exact bag or pod's seal integrity, gas composition, barrier performance, storage path, opening history, or current quality."
                        ),
                        "community_impressions_are_scoped": matcher(
                            "Local-roaster, grocery-shelf, bulk-subscription, price, and freshness comments remain author- and scenario-scoped impressions rather than tests, rates, exact-offer histories, or brand verdicts."
                        ),
                        "freshness_is_one_quality_axis": matcher(
                            "Freshness may affect aroma and flavor while origin, varietal, processing, roast profile, grind, brew execution, package format, and personal preference also affect perceived quality."
                        ),
                        "formats_and_brews_require_matched_controls": matcher(
                            "Whole bean, preground multipacks, and pods cannot isolate freshness unless dose, water, temperature, grind, brewer, extraction, cup, age, opening time, and tasting order are matched."
                        ),
                        "true_cost_includes_consumption_and_waste": matcher(
                            "Compare cost per acceptable consumed serving after package size, shipping, equipment, consumption rate, and waste rather than choosing by sticker price alone."
                        ),
                        "small_trial_is_current_not_universal": matcher(
                            "A small blinded or randomized tasting against a dated fresh reference reduces current uncertainty under tested conditions but does not prove a universal freshness window or future-lot result."
                        ),
                        "cheapest_passing_reference_or_defer": matcher(
                            "Choose only the cheapest exact coffee passing every date, package, consumption, brew, cost, and taste gate; otherwise buy a small dated fresh reference for calibration or defer."
                        )
                    }
                }
            ]
        }
    }

    decidable_claims = [
        negative("wrong_rating_proves_freshness", "B5", "A near-perfect store rating proves that the exact coffee is freshly roasted and sensorially superior."),
        negative("wrong_review_count_proves_recency", "B5", "A large review count establishes the roast date, review recency, lot identity, and warehouse history of the current exact offer."),
        negative("wrong_fresh_wording_is_date", "B5", "Fresh roasted, medium roasted, dark roast, or preserves aroma wording is a verified roast date and exact-lot freshness test."),
        negative("wrong_onyx_one_review_is_universal", "B5", "Onyx's 100-percent aggregate over one review proves universal coffee quality and freshness."),
        negative("wrong_dallmayr_multipack_low_waste", "B5", "The Dallmayr six-pack's 96-percent aggregate proves every pack is fresh and that the buyer will incur no staling waste."),
        negative("wrong_segafredo_pod_claim_independent", "B3", "The Segafredo filter-cup statement independently proves exact-pod seal integrity, oxygen protection, storage history, and preserved aroma."),
        negative("wrong_siroman_exact_date", "B5", "Siroman's fresh boarder roasted description supplies a verified roast date and exact-lot age."),
        negative("wrong_typical_window_exact_clock", "B4", "A general roasted- or ground-coffee freshness window is the exact age, remaining quality, and mandatory discard clock for every offer."),
        negative("wrong_valve_proves_age_and_seal", "B3", "The existence of a pressure-relief valve proves an exact bag's roast age, intact seal, storage conditions, and current freshness."),
        negative("wrong_generic_packaging_proves_exact", "B3", "Generic food-packaging barrier functions prove that the four exact packages achieved their intended shelf life and remain fresh."),
        negative("wrong_nh_comment_is_brand_rate", "B1", "One New Hampshire comment about frequent roasting and sell-through is a measured freshness rate for that business and the four exact offers."),
        negative("wrong_ri_bulk_duration_is_universal", "B1", "One Rhode Island user's five-pound subscription remaining good for three months proves all coffee stays good for that duration."),
        negative("wrong_grocery_shelf_always_stale", "B1", "A community statement that one source avoids grocery shelves proves every grocery-shelf or large-brand coffee is stale."),
        negative("wrong_wa_costco_comment_is_trial", "B1", "One Washington comment calling Costco less fresh but still great is a blinded comparison and a universal Costco quality result."),
        negative("wrong_freshness_is_only_axis", "B2", "Freshness alone determines coffee quality, so origin, varietal, processing, roast profile, grind, brew, and preference can be ignored."),
        negative("wrong_unmatched_formats_rank_freshness", "B2", "Whole beans, preground multipacks, and pods can be ranked directly for freshness without matching coffee, age, dose, grind, brewer, or extraction."),
        negative("wrong_sticker_price_is_true_cost", "B6", "Sticker price alone establishes the cheapest choice even when package size, shipping, equipment, consumption rate, and waste differ."),
        negative("wrong_one_cup_guarantees_future", "B6", "One preferred cup proves a universal freshness cutoff and guarantees the quality of every future lot."),
        negative("wrong_all_big_brands_warehouse_stale", "D1", "All large coffee brands are warehouse-stale, so exact dates, package history, and controlled tasting are unnecessary."),
        negative("wrong_universal_rating_freshness_winner", "D1", "The highest-rated brand or the offer with the strongest fresh wording is a universal winner regardless of exact-lot evidence and taste gates.")
    ]

    g1 = ["E4", "E7", "E10", "E11", "B5"]
    g2 = ["E2", "E9", "B4"]
    g3 = ["E1", "E5", "E10", "B3"]
    g4 = ["E6", "E8", "E12", "B1"]
    g5 = ["E2", "E3", "E9", "B2"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit all four frozen seller snapshots, preserve rating, review-count, product-form, price, fresh-wording, and aroma-preservation fields at seller-assertion scope, and identify the exact date, lot, package, storage, and sensory fields they do not establish.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G2", "description": "Use roast chemistry, coffee-compound, and typical staling evidence to explain why freshness is chemically plausible while refusing an exact lot age, remaining-aroma result, universal cutoff, or discard clock.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G3", "description": "Separate generic bag, valve, oxygen-barrier, and packaging functions from exact-package observations, then define the seal, barrier, gas, transit, storage, and opening-history checks required for each offer.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G4", "description": "Keep the New Hampshire, Rhode Island, and Washington local-roaster, bulk, grocery-shelf, price, and freshness statements at individual author and scenario scope while extracting only variables to verify.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Treat freshness as one quality axis among origin, varietal, processing, roast, grind, brew, package, and preference, and specify matched controls needed to compare whole bean, ground coffee, and pods.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G6", "description": "Combine all branches into an exact-offer matrix, cost-per-consumed-serving calculation, and small blinded or randomized tasting against a dated fresh reference, then choose the cheapest exact coffee passing every gate, buy a calibration reference, or defer without a universal winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"}
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Audit the four exact seller snapshots and separate each title, price, rating, review count, form, flavor description, fresh-roast phrase, and aroma-preservation statement from the verified date, lot, package, storage, and sensory evidence still needed.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain what roast chemistry, aroma compounds, and typical staling context establish and why they cannot determine an exact offer's age, remaining quality, or universal discard time.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain generic bag, valve, sealing, oxygen-barrier, and food-packaging functions while identifying every exact-package and storage-history fact that remains unverified.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Use the three community threads only as scoped local-roaster, bulk-subscription, grocery-shelf, price, consumption, and freshness statements, not as tests, rates, exact-offer histories, or universal verdicts.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Compare freshness with origin, varietal, processing, roast, grind, brew, package, and preference axes, and specify matched controls for a fair sensory comparison across product forms.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give an exact-lot, package, storage, consumption, true-cost, and controlled-tasting protocol against a dated fresh reference, then choose only the cheapest exact coffee passing every gate, buy a calibration reference, or defer without naming a universal brand or freshness-only winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True}
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_coffee_tea_0040",
        "cluster_id": "coffee_exact_lot_freshness_rating_boundary",
        "difficulty": {"proof_depth": 3, "branching_factor": 6, "distractor_density": 0.3, "contradiction_count": 0},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [{"answer": ANSWER, "when": WHEN, "required_tradeoffs": [
            "seller_fields_are_not_exact_lot_proof",
            "typical_staling_context_is_not_an_exact_clock",
            "generic_package_functions_are_not_package_history",
            "community_impressions_are_scoped",
            "freshness_is_one_quality_axis",
            "formats_and_brews_require_matched_controls",
            "true_cost_includes_consumption_and_waste",
            "small_trial_is_current_not_universal",
            "cheapest_passing_reference_or_defer"
        ]}],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 45,
            "minimum_required_evidence_nodes": 12,
            "minimum_reasoning_depth": 3
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
