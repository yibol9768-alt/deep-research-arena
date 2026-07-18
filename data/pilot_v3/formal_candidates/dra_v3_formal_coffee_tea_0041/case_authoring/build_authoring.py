#!/usr/bin/env python3
"""Build Q41 case authoring from its compiled motif and audited rule text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "data/pilot_v3/formal_candidates/dra_v3_formal_coffee_tea_0041"
SOURCE = BASE / "graph_inputs/case_authoring_source.json"
MOTIF = BASE / "motif_compilations/motif.json"
OUT = Path(__file__).with_name("authoring.json")
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "verify_exact_lots_and_package_fields_run_a_small_sealed_and_opened_"
    "calibration_then_stage_the_cheapest_configuration_that_passes_"
    "predeclared_rotation_and_stop_rules_or_defer"
)
WHEN = (
    "the_packet_lacks_exact_lot_dates_verified_package_barriers_seal_tests_"
    "recorded_pantry_conditions_opened_duration_and_a_completed_calibration"
)


def matcher(*phrases: str) -> dict[str, Any]:
    return {
        "matcher": "normalized_text",
        "accepted_phrases": list(phrases),
        "normalizers": NORMALIZERS,
    }


def rejected(claim_id: str, slot_id: str, phrase: str) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "contradicts_slot_id": slot_id,
        "critical": True,
        "rejected_matcher": matcher(phrase),
    }


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    motif = json.loads(MOTIF.read_text(encoding="utf-8"))
    rules = source["rules"]

    bridge_rules = [
        "community_container_scope_v1",
        "oxygen_moisture_heat_light_mechanism_boundary_v1",
        "seller_format_packaging_claim_boundary_v1",
        "shelf_life_condition_and_endpoint_specific_v1",
        "format_opening_and_lot_comparison_boundary_v1",
        "freeze_dried_instant_not_universal_sensory_winner_v1",
        "tea_package_unitization_not_year_guarantee_v1",
        "staged_remote_pantry_trial_v1",
    ]
    rule_definitions: dict[str, Any] = {
        rule_id: {"type": "bridge", **matcher(rules[rule_id])}
        for rule_id in bridge_rules
    }

    decision_phrase = (
        "No universal one-year storage winner is established among the five exact offers. "
        "Keep product pages at seller-assertion scope; distinguish unopened reserve from "
        "opened units and quality from safety; do not turn generic shelf-life, vacuum, "
        "freeze-drying, water-activity, rancidification, package-format, rating, or community "
        "evidence into exact-lot duration. Verify exact roast or manufacture, pack, and "
        "best-before dates, independent-unit count, package barrier, closure and seal, pantry "
        "conditions, servings, and days open. Run the smallest controlled sealed and opened "
        "calibration with predeclared sensory and safety stop rules. Then stage only the "
        "cheapest exact configuration that passes every date, package, condition, consumption, "
        "rotation, and replenishment gate; shorten the horizon or defer while a material field "
        "is unresolved."
    )
    conclusion_phrases = [
        (
            "Verify each shippable lot and package, run a small sealed and opened calibration, "
            "then choose the cheapest configuration whose independent units, consumption rate, "
            "pantry conditions, sensory and safety checks, rotation, and replenishment trigger "
            "all pass; shorten the purchase horizon or defer when any material gate remains unresolved."
        ),
        (
            "Do not buy a universal one-year winner from this packet. Start with the smallest "
            "verified lot, open one independently sealed unit at a time, rotate earliest dates "
            "first, and expand only after the declared quality and safety checkpoints pass, "
            "otherwise replenish sooner or defer."
        ),
    ]
    condition_phrase = (
        "The packet contains five frozen seller pages, five generic mechanism or shelf-life "
        "pages, and four scoped community discussions, but it lacks exact shippable-lot dates, "
        "verified package-barrier and seal results, measured water activity, logged remote-pantry "
        "conditions, actual opened-unit duration, and a completed controlled sensory calibration."
    )
    tradeoffs = {
        "seller_pages_are_not_lot_tests": (
            "Titles, descriptions, prices, ratings, review counts, format names, package words, "
            "and freshness copy are frozen seller assertions rather than observed exact-lot, "
            "seal, barrier, storage, or sensory tests."
        ),
        "shelf_life_requires_endpoint_and_conditions": (
            "Shelf life requires a defined quality endpoint, exact lot and package state, and "
            "specified storage conditions; best-before, sale, use, sensory quality, and safety "
            "cannot be treated as interchangeable."
        ),
        "generic_mechanisms_do_not_set_exact_duration": (
            "Vacuum packing, freeze drying, water activity, and rancidification identify oxygen, "
            "moisture, heat, light, product, and barrier variables but do not authenticate an "
            "exact package or assign it a one-year duration."
        ),
        "coffee_formats_need_matched_comparison": (
            "Whole bean, ground, and instant offers differ in product, lot, package, quantity, "
            "preparation, and other fields, so format alone cannot establish a freshness ranking."
        ),
        "tea_unitization_is_not_barrier_proof": (
            "Two metal tins and one hundred individual wrappers indicate unitization, not a "
            "verified barrier, seal, date, opened duration, or twelve-month tea-quality result."
        ),
        "community_pages_remain_individual_scope": (
            "Community container questions and personal replies may suggest closure, leak, "
            "breakage, headspace, odor, stacking, and airtightness checks but are not controlled "
            "coffee or tea storage evidence."
        ),
        "opened_duration_follows_consumption": (
            "Package quantity must be converted into actual servings and days each unit remains "
            "open; a pack size that exceeds the predeclared opened-quality window is inadmissible."
        ),
        "calibration_is_small_and_reversible": (
            "A small controlled purchase using one preparation protocol and scheduled sensory, "
            "seal, moisture, odor, and safety stop rules reduces uncertainty before a larger commitment."
        ),
        "rotation_and_replenishment_are_explicit": (
            "Admissible reserves stay in independent sealed units, open one unit at a time, use "
            "earliest verified dates first, and replenish at a declared trigger."
        ),
        "cheapest_passing_or_defer": (
            "Choose price only among exact configurations that pass every material gate; shorten "
            "the horizon, replenish sooner, or defer rather than guessing a missing date, package, "
            "condition, consumption, sensory, or safety field."
        ),
    }
    rule_definitions["evidence_bounded_remote_pantry_rotation_v1"] = {
        "type": "decision",
        "decision_matcher": matcher(decision_phrase),
        "conclusion_matchers": {ANSWER: matcher(*conclusion_phrases)},
        "admissible_conditions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(condition_phrase),
                "tradeoff_matchers": {
                    key: matcher(value) for key, value in tradeoffs.items()
                },
            }
        ],
    }

    decidable_claims = [
        rejected("wrong_rating_proves_storage_quality", "B3", "A high store rating and many reviews prove that the exact lot will retain freshness for one year."),
        rejected("wrong_seller_freshness_copy_is_test", "B3", "Seller phrases such as locks in aroma, garden fresh, or protects granules are independent package and storage tests."),
        rejected("wrong_whole_bean_always_wins", "B5", "Whole-bean coffee is always the freshest one-year choice regardless of lot age, package, opening rate, storage, and preparation."),
        rejected("wrong_steel_can_guarantees_year", "B5", "The ground coffee's steel can guarantees peak quality for a full year because the seller says it locks in aroma."),
        rejected("wrong_freeze_drying_guarantees_year", "B6", "Freeze drying alone guarantees that the exact instant coffee will taste unchanged after twelve months."),
        rejected("wrong_resealable_means_verified_barrier", "B6", "A resealable Doypack label proves high oxygen and moisture barrier performance through repeated opening."),
        rejected("wrong_metal_tin_guarantees_freshness", "B7", "A metal tin plus packed-at-source and garden-fresh wording proves twelve-month loose-leaf tea quality."),
        rejected("wrong_individual_wrapper_is_high_barrier", "B7", "Every individually wrapped tea bag is necessarily in a verified high-barrier package with one-year quality."),
        rejected("wrong_generic_shelf_life_sets_year", "B4", "A generic shelf-life definition establishes a twelve-month duration for every captured coffee and tea product."),
        rejected("wrong_best_before_equals_safety", "B4", "Best-before, shelf life, sensory quality, and food-safety limits are the same endpoint."),
        rejected("wrong_vacuum_page_proves_exact_pack", "B2", "Because vacuum packing can extend shelf life, each exact bag, can, pouch, tin, and wrapper is proven vacuum sealed."),
        rejected("wrong_moisture_content_substitutes_aw", "B2", "A general description of dryness or low moisture substitutes for an exact water-activity measurement."),
        rejected("wrong_rancidification_sets_exact_rate", "B2", "The generic rancidification mechanism supplies the exact degradation rate of all five offers."),
        rejected("wrong_community_replies_are_trials", "B1", "Community container replies are controlled long-term coffee and tea package trials that establish comparative durability and airtightness."),
        rejected("wrong_ignore_unopened_opened_state", "B8", "Unopened reserve packages and the currently open package can use the same storage duration without tracking openings or consumption."),
        rejected("wrong_full_year_without_dates", "B8", "It is safe to commit to a full-year quantity before obtaining exact roast or manufacture, pack, and best-before dates."),
        rejected("wrong_no_calibration_needed", "B8", "A small exact-lot calibration and predeclared sensory and safety stop rules are unnecessary when package marketing sounds plausible."),
        rejected("wrong_sticker_price_only", "D1", "Choose the lowest sticker price without converting package quantity into acceptable consumed servings, waste, and replenishment cost."),
        rejected("wrong_reject_every_bulk_option", "D1", "All multi-unit or bulk purchases must be rejected even when exact dates, independent seals, conditions, opened duration, and calibration pass."),
        rejected("wrong_universal_format_winner", "D1", "One universal package or coffee format is the best twelve-month choice for every remote pantry."),
    ]

    query_requirements = [
        {"requirement_id": "Q1", "text": "Audit all five frozen product pages at exact seller-assertion scope, preserving offer, quantity, unitization, price, aggregate, format, and packaging copy while identifying missing lot dates, barrier, seal, storage, opened-duration, and outcome fields.", "slot_ids": ["E1", "E4", "E7", "E8", "E9", "B3"], "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Distinguish shelf-life quality, safety, best-before, sell-by, use-by, unopened, and opened endpoints and bind every proposed duration to the exact lot, package, state, and specified remote-pantry conditions.", "slot_ids": ["E11", "E1", "E4", "E7", "E8", "E9", "B4"], "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Use vacuum packing, water activity, rancidification, oxygen, moisture, heat, and light only to define measurements and failure modes; do not infer exact package authentication or one-year duration from generic mechanisms.", "slot_ids": ["E10", "E11", "E13", "E14", "B2"], "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Compare whole-bean, ground, and freeze-dried instant coffee only after matching exact lot dates, packages, independent units, openings, consumption, pantry conditions, preparation, cost per acceptable serving, and sensory endpoints; keep freeze drying and reseal claims at their proper scope.", "slot_ids": ["E4", "E5", "E8", "E9", "B5", "B6"], "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Treat two loose-leaf metal tins and one hundred individually wrapped tea bags as unitization clues, convert them into servings and days open, and require exact dates, barrier, seal, conditions, and scheduled sensory evidence before any one-year conclusion.", "slot_ids": ["E1", "E7", "E11", "E13", "E14", "B7"], "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Keep the four community pages at individual author, container, use, and reply scope, using them only to identify closure, leak, breakage, headspace, odor, stacking, and physically verified airtightness questions.", "slot_ids": ["E2", "E3", "E6", "E12", "B1"], "subgoal_ids": ["G6"], "required": True},
        {"requirement_id": "Q7", "text": "Specify a small reversible exact-lot calibration that verifies dates, seals, package fields, pantry temperature, humidity and light, servings and days open, one preparation protocol, scheduled sensory and safety checkpoints, independent-unit rotation, and a replenishment trigger.", "slot_ids": ["E1", "E4", "E7", "E8", "E9", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"], "subgoal_ids": ["G7"], "required": True},
        {"requirement_id": "Q8", "text": "Choose only the cheapest exact configuration that passes all date, package, condition, consumption, calibration, sensory, safety, rotation, and replenishment gates; shorten the horizon, replenish sooner, or defer when material fields remain unresolved, and do not name a universal winner.", "slot_ids": ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E14", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "D1"], "subgoal_ids": ["G8"], "required": True},
    ]
    research_subgoals = [
        {"subgoal_id": "G1", "description": "Audit the five exact seller snapshots, preserve their offer and packaging statements, and identify why format, price, aggregates, and copy do not establish exact-lot storage performance.", "critical": True, "requires": ["E1", "E4", "E7", "E8", "E9", "B3"], "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G2", "description": "Define the exact shelf-life endpoint, lot, package, unopened or opened state, and remote storage conditions instead of merging quality, safety, and date concepts.", "critical": True, "requires": ["E11", "E1", "E4", "E7", "E8", "E9", "B4"], "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G3", "description": "Translate generic vacuum, water-activity, rancidification, oxygen, moisture, heat, and light mechanisms into exact measurements and failure checks without assigning an unsupported duration.", "critical": True, "requires": ["E10", "E11", "E13", "E14", "B2"], "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G4", "description": "Build a matched whole-bean, ground, and instant comparison while separating generic freeze-drying and seller reseal copy from exact lot, package, preparation, and sensory evidence.", "critical": True, "requires": ["E4", "E5", "E8", "E9", "B5", "B6"], "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G5", "description": "Convert loose-leaf tins and individually wrapped tea bags into unit counts, servings, and time open while requiring verified dates, barriers, seals, conditions, and sensory checkpoints.", "critical": True, "requires": ["E1", "E7", "E11", "E13", "E14", "B7"], "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G6", "description": "Keep four community discussions at individual question and experience scope while extracting only container inspection questions relevant to a later exact test.", "critical": True, "requires": ["E2", "E3", "E6", "E12", "B1"], "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G7", "description": "Design a small exact-lot sealed and opened calibration, condition log, stop rules, independent-unit rotation, and replenishment trigger before any larger commitment.", "critical": True, "requires": ["E1", "E4", "E7", "E8", "E9", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"], "local_conclusion_slot_id": "B8"},
        {"subgoal_id": "G8", "description": "Synthesize all product, concept, and community branches into the cheapest exact configuration that passes every declared gate, or shorten the horizon, replenish sooner, or defer without naming a universal format winner.", "critical": True, "requires": ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E14", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "D1"], "local_conclusion_slot_id": "D1"},
    ]

    steps = motif["compilation"]["evaluator_view"]["required_proof_steps"]
    proof = [step["step_id"] for step in steps]
    evidence_steps = [step_id for step_id in proof if step_id.startswith("E")]
    authoring = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_coffee_tea_0041",
        "cluster_id": "remote_pantry_storage_format_and_rotation_boundary",
        "difficulty": {"proof_depth": 4, "branching_factor": 8, "distractor_density": 0.32, "contradiction_count": 0},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": research_subgoals,
        "query_requirements": query_requirements,
        "acceptable_conclusions": [{"answer": ANSWER, "when": WHEN, "required_tradeoffs": list(tradeoffs)}],
        "oracle": {
            "proof": proof,
            "single_page_sufficient": False,
            "critical_node_ablation": {step_id: {"outcome": "decision_unresolved"} for step_id in evidence_steps},
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": len(evidence_steps),
            "minimum_reasoning_depth": 4,
        },
    }
    OUT.write_text(json.dumps(authoring, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": OUT.relative_to(ROOT).as_posix(), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "proof_steps": len(proof)}, sort_keys=True))


if __name__ == "__main__":
    main()
