#!/usr/bin/env python3
"""Build the audited Q47 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_only_the_least_commitment_exact_configuration_that_passes_identity_package_condition_week_ten_sensory_and_waste_adjusted_cost_gates_otherwise_shorten_the_stocking_horizon_or_defer"
WHEN = "the_packet_lacks_exact_lot_package_barrier_and_matched_ten_week_results"


def matcher(*phrases: str) -> dict[str, object]:
    return {"matcher": "normalized_text", "accepted_phrases": list(phrases), "normalizers": NORMALIZERS}


def bridge(phrase: str) -> dict[str, object]:
    return {"type": "bridge", **matcher(phrase)}


def negative(claim_id: str, slot_id: str, phrase: str) -> dict[str, object]:
    return {"claim_id": claim_id, "contradicts_slot_id": slot_id, "critical": True, "rejected_matcher": matcher(phrase)}


EVIDENCE = [f"E{index}" for index in range(1, 16)]
BRIDGES = [f"B{index}" for index in range(1, 8)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "bloom_temper_crystal_boundary_v1": bridge(rules["bloom_temper_crystal_boundary_v1"]),
        "community_operational_scope_v1": bridge(rules["community_operational_scope_v1"]),
        "oxidation_package_measurement_boundary_v1": bridge(rules["oxidation_package_measurement_boundary_v1"]),
        "seller_offer_identity_conflict_scope_v1": bridge(rules["seller_offer_identity_conflict_scope_v1"]),
        "independent_unit_rotation_cost_v1": bridge(rules["independent_unit_rotation_cost_v1"]),
        "staged_ten_week_sensory_protocol_v1": bridge(rules["staged_ten_week_sensory_protocol_v1"]),
        "stash_decision_preparation_v1": bridge(rules["stash_decision_preparation_v1"]),
        "evidence_bounded_stash_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["evidence_bounded_stash_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet does not prove an immediate ten-week winner. Choose only the least-commitment exact configuration that passes exact identity, package integrity, declared storage, week-ten sensory acceptability and waste-adjusted delivered-cost gates; otherwise shorten the stocking horizon or defer.",
                    "Start with independently sealed units, verify the exact delivered offer, run the predeclared week-zero through week-ten protocol, and select the lowest-commitment passing rotation or shorten the horizon or defer without a universal brand or package winner.",
                )
            },
            "admissible_conditions": [{
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(
                    "The packet contains five frozen seller snapshots, bounded bloom, tempering, autoxidation, MVTR, OTR and sensory-method context, and four scoped community discussions, but it lacks verified exact delivered lots and dates, complete package structures and barrier tests, declared ten-week environment histories and matched week-ten sensory outcomes."
                ),
                "tradeoff_matchers": {
                    "seller_fields_are_scoped": matcher("Seller prices, ratings, review counts, masses, counts, wrapper, resealability and freshness wording remain frozen offer assertions rather than measured ten-week results."),
                    "quantity_conflicts_remain_unresolved": matcher("The Hershey 3.6-ounce versus 1.41-ounce fields and the Oh Nuts selected 2-pound versus 1.2-pound fields remain unresolved until the exact delivered variants are checked."),
                    "bloom_is_classified_not_overdiagnosed": matcher("Fat bloom involves fat-crystal change and sugar bloom involves moisture acting on sugar; bloom can harm appearance and texture without by itself proving cheapness, spoilage, contamination or universal unsafety."),
                    "tempering_is_a_general_mechanism": matcher("Tempering and cocoa-butter polymorphism explain gloss, snap and bloom resistance but do not verify any exact offer's process history or future crystal state."),
                    "autoxidation_is_not_an_exact_rate": matcher("Autoxidation supplies a plausible oxygen-driven rancidity mechanism but not an exact lot rate, induction time, package result or ten-week prediction."),
                    "package_metrics_require_conditions": matcher("MVTR and OTR comparisons require exact package structure, opening state, temperature, humidity, thickness, method and whole-package seals, closures, creases and joints."),
                    "community_evidence_is_scoped": matcher("The pocket melt, bag clip, labeling and Boston sourcing discussions remain author-, product-, place- and time-scoped operational clues rather than controlled durability trials."),
                    "exact_identity_and_safety_fields_are_required": matcher("Verify SKU, variant, net quantity, unit count, lot, date, ingredients, allergens, storage instructions, seal condition, delivered cost and remedy terms before purchase or tasting."),
                    "independent_units_reduce_commitment": matcher("Preserve separately sealed units, label receipt and opening dates, and avoid exposing the full stash during sampling."),
                    "sensory_methods_have_distinct_jobs": matcher("Use discrimination testing only for matched current samples, use separate descriptive and acceptability measures, and do not treat failure to detect a difference as equality or preference."),
                    "causal_package_claims_need_matching": matcher("Do not infer a causal package winner across unlike recipes, products, lots, opening states, storage histories or test conditions."),
                    "cost_is_waste_adjusted": matcher("Compare delivered cost per serving that remains acceptable at week ten after waste and rotation risk rather than sticker price, total mass or rating alone."),
                    "least_commitment_or_shorter_horizon": matcher("Choose only the least-commitment exact configuration passing identity, package, condition, week-ten sensory and waste-cost gates; otherwise shorten the stocking horizon or defer."),
                },
            }],
        },
    }

    decidable_claims = [
        negative("wrong_bloom_proves_cheap", "B1", "A chalky white coating proves that the chocolate was made from cheap ingredients."),
        negative("wrong_bloom_is_spoilage", "B1", "Any visible bloom means the chocolate has spoiled and must be treated as the same failure mode as rancid nuts."),
        negative("wrong_bloom_universal_safety", "B1", "The general bloom article proves that every white-coated exact lot is safe regardless of mold, allergens, contamination or package damage."),
        negative("wrong_tempering_history_known", "B1", "The general tempering mechanism proves how each captured chocolate was manufactured and guarantees its week-ten crystal form."),
        negative("wrong_pocket_incident_ten_week_test", "B2", "One chocolate egg melting in a pocket is a controlled ten-week pantry test of all five exact offers."),
        negative("wrong_clip_restores_original_barrier", "B2", "Opening a snack bag, squeezing it and adding a clip restores the unopened package atmosphere and barrier."),
        negative("wrong_label_preserves_freshness", "B2", "Writing a date on a container prevents oxidation and guarantees freshness."),
        negative("wrong_boston_price_current", "B2", "A historical Boston comment proves the current rural price and availability of these exact offers."),
        negative("wrong_autoxidation_exact_rate", "B3", "The general autoxidation page establishes that the exact Oh Nuts or Blue Diamond lot will turn rancid at a known week."),
        negative("wrong_generic_mvtr_ranking", "B3", "A generic MVTR definition is enough to rank the five exact packages for ten-week moisture protection."),
        negative("wrong_generic_otr_ranking", "B3", "A generic OTR definition proves that resealable bags or individual wrappers have the best complete-package oxygen barrier."),
        negative("wrong_sheet_equals_package", "B3", "A packaging-film value automatically equals whole-package performance even when seals, creases, joints, closures and opening state differ."),
        negative("wrong_hershey_mass_resolved", "B4", "The Hershey page unambiguously establishes one net quantity despite its 3.6-ounce and 1.41-ounce fields."),
        negative("wrong_oh_nuts_mass_resolved", "B4", "The Oh Nuts page unambiguously establishes a two-pound delivered bag despite its 1.2-pound Package Dimensions field."),
        negative("wrong_hershey_wrapper_proof", "B4", "The Hershey seller's individually wrapped and lasting freshness wording proves good quality at week ten."),
        negative("wrong_ghirardelli_bulk_value", "B4", "Five pounds and 60-percent cacao automatically make the reseller bundle the best stash value."),
        negative("wrong_blue_rating_proof", "B4", "An 83-percent store rating over twelve reviews proves the Blue Diamond bag stays fresh for ten weeks."),
        negative("wrong_second_pouches_proof", "B4", "Twelve resealable Second Nature pouches alone prove the exact delivered case will retain quality for ten weeks."),
        negative("wrong_oh_nuts_copy_proof", "B4", "The zip-lock and no-more-rancid-nuts seller copy proves that the exact Oh Nuts lot cannot oxidize."),
        negative("wrong_sticker_cost_winner", "B5", "The lowest sticker price or largest total mass is the best value without accounting for delivered cost, accepted servings and waste."),
        negative("wrong_open_all_units", "B5", "Opening every unit at week zero has no effect on the validity or exposure risk of the ten-week trial."),
        negative("wrong_cross_product_package_causality", "B5", "Comparing unlike chocolate, flavored almonds and trail mix directly proves which package construction caused better retention."),
        negative("wrong_one_unit_all_timepoints", "B6", "Repeatedly opening and tasting the same package at weeks 0, 2, 6 and 10 is equivalent to sampling independent sealed timepoint units."),
        negative("wrong_discrimination_measures_preference", "B6", "A discrimination test by itself quantifies preference, defect size and acceptability."),
        negative("wrong_failure_to_reject_equality", "B6", "Failure to detect a difference proves that two products or timepoints are equal."),
        negative("wrong_ignore_environment", "B6", "A ten-week result remains interpretable without recording pantry temperature, humidity, heat excursions, moisture excursions or opening state."),
        negative("wrong_taste_after_safety_stop", "B6", "A sample with failed package integrity or a predeclared safety stop should still be tasted to complete the score sheet."),
        negative("wrong_one_gate_compensates", "B7", "A low price can compensate for unresolved exact identity, failed package integrity or a safety stop."),
        negative("wrong_immediate_product_winner", "D1", "The frozen packet already proves one unconditional brand, product or package winner for every ten-week rural pantry."),
        negative("wrong_buy_bulk_without_trial", "D1", "The buyer should commit to the largest bulk offer before verifying the delivered lot or running a reversible retention trial."),
    ]

    g1 = ["E4", "E15", "B1"]
    g2 = ["E1", "E10", "E12", "B3"]
    g3 = ["E5", "E7", "E8", "E11", "E14", "B4"]
    g4 = ["E2", "E3", "E9", "E13", "B2"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Classify fat and sugar bloom, explain tempering and cocoa-butter crystal forms, and separate appearance and texture effects from cheapness, rancidity, contamination and universal safety claims.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G2", "description": "Explain oxygen-driven autoxidation and the condition- and structure-specific meanings of MVTR and OTR without assigning exact rates or barrier rankings to the five offers.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G3", "description": "Audit all five frozen seller offers, retain both quantity conflicts, distinguish product forms, and list every exact identity, lot, label, package, storage and delivered-cost field still requiring verification.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G4", "description": "Keep the pocket melt, bag clip, storage-label and Boston sourcing discussions at their incident, author, product, place and time scopes while extracting only operational variables to test.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G5", "description": "Design a smallest-commitment independent-unit rotation and week 0, 2, 6 and 10 protocol with environment logs, defect classification, safety stops, bounded discrimination, acceptability scoring and waste-adjusted cost.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G6", "description": "Choose only a verified least-commitment configuration that passes every identity, package, condition, week-ten sensory and waste-cost gate, or shorten the horizon or defer without naming a universal winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Explain fat bloom, sugar bloom, tempering and cocoa-butter crystal behavior while refusing cheapness, spoilage and universal safety overclaims.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain autoxidation, MVTR and OTR and state the exact test conditions and whole-package features needed before making a ten-week package comparison.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Audit the five exact offers, preserve seller quantity conflicts, distinguish chocolate bars, cocoa-flavored almonds and trail mix, and identify unresolved exact-lot and package fields.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Use the four community discussions only as scoped operational clues about heat, opening, labeling and availability, not as exact-offer durability evidence.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify independent sealed timepoint units, environment and opening-state logs, week 0, 2, 6 and 10 checks, safety stops, sensory method limits and waste-adjusted cost per accepted serving.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a conditional least-commitment purchase, shorter-horizon or deferral decision without declaring an unconditional product, brand, package or safety winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0047",
        "cluster_id": "ten_week_chocolate_nut_stash_bloom_oxidation",
        "difficulty": {"proof_depth": 4, "branching_factor": 15, "distractor_density": 0.35, "contradiction_count": 2},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [{
            "answer": ANSWER,
            "when": WHEN,
            "required_tradeoffs": [
                "seller_fields_are_scoped", "quantity_conflicts_remain_unresolved",
                "bloom_is_classified_not_overdiagnosed", "tempering_is_a_general_mechanism",
                "autoxidation_is_not_an_exact_rate", "package_metrics_require_conditions",
                "community_evidence_is_scoped", "exact_identity_and_safety_fields_are_required",
                "independent_units_reduce_commitment", "sensory_methods_have_distinct_jobs",
                "causal_package_claims_need_matching", "cost_is_waste_adjusted",
                "least_commitment_or_shorter_horizon",
            ],
        }],
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
