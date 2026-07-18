#!/usr/bin/env python3
"""Build the audited Q55 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_lowest_total_ownership_exact_passing_system_otherwise_keep_repair_rent_downscope_or_defer"
WHEN = "the_packet_lacks_exact_unit_survival_and_current_serviceability_evidence"


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


EVIDENCE = [f"E{index}" for index in range(1, 21)]
BRIDGES = [f"B{index}" for index in range(1, 10)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "community_lifetime_service_scope_v1": bridge(rules["community_lifetime_service_scope_v1"]),
        "exact_offer_condition_weather_claim_scope_v1": bridge(rules["exact_offer_condition_weather_claim_scope_v1"]),
        "model_release_mount_mapping_v1": bridge(rules["model_release_mount_mapping_v1"]),
        "seal_mechanism_maintenance_boundary_v1": bridge(rules["seal_mechanism_maintenance_boundary_v1"]),
        "shutter_mount_wear_boundary_v1": bridge(rules["shutter_mount_wear_boundary_v1"]),
        "reliability_metric_exact_unit_boundary_v1": bridge(rules["reliability_metric_exact_unit_boundary_v1"]),
        "spare_parts_field_replaceability_boundary_v1": bridge(rules["spare_parts_field_replaceability_boundary_v1"]),
        "decade_ownership_verification_trial_v1": bridge(rules["decade_ownership_verification_trial_v1"]),
        "ownership_cost_serviceability_matrix_v1": bridge(rules["ownership_cost_serviceability_matrix_v1"]),
        "evidence_bounded_decade_camera_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["evidence_bounded_decade_camera_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no universal buy-it-for-life camera. Choose only the lowest-total-ownership exact system that passes use, identity, condition, compatibility, maintenance, current regional serviceability, parts and budget gates after independent inspection and a reversible trial; otherwise keep, repair, rent, choose a smaller replaceable system or defer.",
                    "Verify the exact units and written regional serviceability, then choose the lowest-total-ownership passing system or a reversible fallback without promising decade survival.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains frozen seller pages, bounded camera-model and mechanism context, generic reliability and repair-parts definitions, and three scoped community posts, but lacks exact-unit condition and survival data, camera-specific failure distributions, current regional service commitments and a controlled decade comparison."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_frozen": matcher("All stock, SKU, price, rating, review, bundle, warranty, weather, durability and performance wording remains a frozen seller assertion rather than a current delivered offer, ingress test or lifetime result."),
                        "k30_conflict_is_preserved": matcher("Retain the K-30 conflict between the title saying discontinued and the later Is Discontinued By Manufacturer No field as unresolved."),
                        "exact_variant_region_is_required": matcher("Bind each offer to the exact model, variant, body or lens form, mount, bundle, region and page condition."),
                        "model_mapping_is_not_survival": matcher("Release date, sensor format, lens mount and shutter type are model context rather than exact-unit health or a decade-survival ranking."),
                        "weather_copy_is_not_ingress": matcher("Weather-sealed or weather-resistant copy does not establish a standardized ingress rating, current seal condition or future protection."),
                        "lens_seal_is_not_system_seal": matcher("A sealed lens-mount gap does not prove an entire body-lens system is sealed or that the lens is compatible with another mount."),
                        "mechanisms_need_unit_measurement": matcher("Focal-plane shutter and lens-mount definitions identify inspection targets but supply no actuation distribution, mount tolerance, repair quote or remaining life."),
                        "generic_seals_are_scoped": matcher("O-ring and gasket definitions do not identify a candidate camera's seal material, location, replacement interval or present condition."),
                        "reliability_needs_defined_conditions": matcher("Reliability must be tied to intended function, time and environment, and generic MTBF for a repairable population cannot predict one camera unit."),
                        "durability_and_repairability_are_separate": matcher("Keep physical durability, spare-part availability, field replaceability, authorized service and economic repairability as separate fields."),
                        "community_evidence_is_scoped": matcher("The old-camera, vintage-lens and laptop-parts posts remain author-, item-, place-, device- and time-scoped rather than survival data or future camera support promises."),
                        "exact_inspection_is_required": matcher("Verify exact serial, region, condition, shutter count, controls, sensor, mount, ports, card slots, battery, charger, firmware, lens optics, focus and aperture before purchase."),
                        "written_service_answers_are_required": matcher("Obtain current written regional service answers and quotes for shutter, seals, mount, boards, batteries, parts, authorization, downtime and likely repairs."),
                        "reversible_actual_use_trial_is_required": matcher("Use an independent inspection and return-compliant or rental trial in the buyer's actual use and environmental profile."),
                        "total_ownership_cost_is_required": matcher("Include compatible lenses, batteries, media, maintenance, repair scenarios, downtime and replacement fallback in total ownership cost."),
                        "gates_are_pass_fail_unresolved": matcher("Predeclare use, identity, condition, compatibility, maintenance, serviceability, parts, cost and stop gates and mark each pass, fail or unresolved."),
                        "fallback_avoids_false_winner": matcher("If no exact system passes, keep or repair current equipment, rent, choose a smaller more replaceable system or defer rather than naming a buy-it-for-life winner."),
                        "decision_scope_is_exact_and_dated": matcher("Scope the decision to the exact serials, lenses, environment, written service answers and decision date without promising ten-year survival."),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_k30_title_resolves_conflict", "B2", "The K-30 title proves the camera is discontinued despite the conflicting Is Discontinued By Manufacturer No field."),
        negative("wrong_k30_field_resolves_conflict", "B2", "The K-30 Is Discontinued By Manufacturer No field proves the discontinued title is false."),
        negative("wrong_frozen_stock_current", "B2", "An in-stock field in the frozen packet proves current availability."),
        negative("wrong_store_rating_survival", "B2", "A high store rating proves that a camera will survive for ten years."),
        negative("wrong_price_durability", "B2", "The highest frozen price proves the lowest lifetime failure risk."),
        negative("wrong_weather_ingress_rating", "B2", "Weather-sealed or weather-resistant seller wording proves a standardized ingress rating."),
        negative("wrong_magnesium_lifetime", "B2", "A magnesium-alloy body claim guarantees decade-long operation of the shutter, electronics and seals."),
        negative("wrong_import_support", "B2", "USA-compatible accessories and a seller warranty prove manufacturer service for the imported D7500."),
        negative("wrong_international_support", "B2", "International-version wording proves regional Canon warranty and service eligibility."),
        negative("wrong_bundle_condition", "B2", "A body bundle title proves exact delivered contents and used-unit condition."),
        negative("wrong_release_newer_wins", "B3", "The 2021 K-3 Mark III must outlast the 2016 and 2017 models because it is newer."),
        negative("wrong_full_frame_lasts", "B3", "The full-frame 5D Mark IV must last longer than smaller-sensor cameras because sensor size determines mechanical durability."),
        negative("wrong_mount_cross_compatible", "B3", "Pentax KAF2, Nikon F and Canon EF lenses are interchangeable without exact compatibility checks."),
        negative("wrong_shutter_type_rating", "B3", "A model page naming a focal-plane shutter supplies its remaining actuation life."),
        negative("wrong_model_page_unit_condition", "B3", "A model specification page proves the condition and identity of one seller unit."),
        negative("wrong_lens_gap_whole_system", "B4", "The Rokinon weather-sealed mount gap proves the complete camera and lens system is sealed."),
        negative("wrong_generic_oring_camera", "B4", "The generic O-ring definition proves every candidate camera uses the same seal material and replacement interval."),
        negative("wrong_generic_gasket_schedule", "B4", "The generic gasket definition supplies a maintenance schedule for all captured cameras."),
        negative("wrong_weather_never_degrades", "B4", "Weather sealing remains effective indefinitely without inspection, contamination control or service."),
        negative("wrong_focal_shutter_failure_rate", "B5", "The focal-plane-shutter mechanism page gives a failure rate for the captured camera models."),
        negative("wrong_burst_equals_life", "B5", "A higher burst rate proves a shutter has a longer service life."),
        negative("wrong_mount_interface_no_wear", "B5", "Because a lens mount is an interface it cannot loosen, wear or develop contact problems."),
        negative("wrong_no_shutter_count_needed", "B5", "Shutter count and exact-unit history do not matter when evaluating remaining life."),
        negative("wrong_generic_mtbf_camera", "B6", "A generic MTBF definition predicts the remaining lifetime of one used camera."),
        negative("wrong_mtbf_equals_mttf", "B6", "MTBF for repairable systems is identical to MTTF for non-repairable systems."),
        negative("wrong_reliability_context_free", "B6", "Reliability is a context-free property independent of intended function, time and environment."),
        negative("wrong_no_population_needed", "B6", "A camera reliability ranking needs no defined population, failure rule, operating profile or censoring."),
        negative("wrong_spare_definition_inventory", "B7", "The definition of a spare part proves that replacement shutters and seals are currently in stock for every candidate."),
        negative("wrong_fru_all_camera_parts", "B7", "The field-replaceable-unit definition proves camera shutters, sensors and boards are user replaceable."),
        negative("wrong_repairable_means_economic", "B7", "A technically replaceable part is necessarily authorized, affordable and faster than replacing the camera."),
        negative("wrong_parts_future_promise", "B7", "Current or anecdotal parts access guarantees supply throughout the next decade."),
        negative("wrong_old_camera_population", "B1", "One author's old cameras in good condition prove most cameras survive a decade."),
        negative("wrong_vintage_lens_inventory", "B1", "One local vintage-lens thread proves a stable verified inventory of compatible lenses."),
        negative("wrong_dell_camera_policy", "B1", "One Dell owner's laptop-parts experience proves camera manufacturers will sell internal parts."),
        negative("wrong_forum_anecdote_winner", "B1", "A community anecdote identifies the most durable captured body and lens."),
        negative("wrong_skip_serial_inspection", "B8", "Model reputation allows the buyer to skip serial, condition, shutter, mount, seal, battery and firmware checks."),
        negative("wrong_phone_service_answer", "B8", "An informal phone answer without exact serial, region and written quote is enough to establish serviceability."),
        negative("wrong_dry_room_trial", "B8", "A brief dry-room power-on test proves performance and sealing in the buyer's actual environments."),
        negative("wrong_no_return_window", "B8", "Inspection and trial may ignore seller return terms and irreversible risk."),
        negative("wrong_purchase_price_tco", "B9", "Frozen purchase price alone is total ownership cost."),
        negative("wrong_downtime_ignored", "B9", "Repair downtime and replacement fallback can be omitted from a long-ownership decision."),
        negative("wrong_unresolved_is_pass", "B9", "An unresolved service, parts, seal or condition field may be treated as a pass."),
        negative("wrong_marketing_overrides_gate", "B9", "Weather or workhorse marketing can override failed exact-unit condition and serviceability gates."),
        negative("wrong_immediate_k30_winner", "D1", "The packet already proves that the Pentax K-30 is the unconditional buy-it-for-life winner."),
        negative("wrong_immediate_k3iii_winner", "D1", "The packet already proves that the Pentax K-3 Mark III will last ten years."),
        negative("wrong_immediate_k1ii_winner", "D1", "The packet already proves that the Pentax K-1 Mark II will outlast every alternative."),
        negative("wrong_immediate_d7500_winner", "D1", "The packet already proves that the Nikon D7500 is the lowest-risk long-term system."),
        negative("wrong_immediate_5div_winner", "D1", "The packet already proves that the Canon 5D Mark IV is the unconditional long-haul choice."),
        negative("wrong_must_buy_captured", "D1", "The buyer must purchase one captured listing even when material condition or serviceability fields remain unresolved."),
        negative("wrong_decade_guarantee", "D1", "Passing one inspection and trial guarantees ten years without failure."),
    ]

    g1 = ["E1", "E2", "E9", "E10", "E13", "E14", "E15", "E16", "E18", "B2", "B3"]
    g2 = ["E3", "E5", "E7", "E11", "E18", "B4", "B5"]
    g3 = ["E4", "E8", "E17", "E19", "B6", "B7"]
    g4 = ["E6", "E12", "E20", "B1"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit the six frozen seller pages, preserve the K-30 discontinuation conflict, and map exact model, mount, region and body-versus-lens form without ranking durability by price, date or format.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G2", "description": "Explain focal-plane shutter, lens-mount, O-ring and gasket mechanisms and distinguish generic component context from exact-unit wear, seal condition, ingress protection and remaining life.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G3", "description": "Define reliability and MTBF with their required scope and separate physical durability, spare-part access, field replaceability, authorized service and economic repairability.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G4", "description": "Keep the old-camera, vintage-lens and laptop-parts community pages at their author, item, place, device and time scope without turning them into survival or support promises.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Design the exact serial and condition inspection, written regional service and parts inquiry, independent repair-cost check and reversible actual-use trial for every candidate system.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B8"},
        {"subgoal_id": "G6", "description": "Build a total-ownership and serviceability matrix, mark every gate pass, fail or unresolved, and choose the lowest-total-ownership exact passing system or a reversible fallback without promising decade survival.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build an exact seller and model table preserving the K-30 source conflict and separating frozen price, rating, bundle, region and weather wording from current condition and support.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain shutter, mount, O-ring and gasket mechanisms and list the exact-unit measurements and service facts missing from generic definitions.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain reliability, MTBF, spare parts and field replacement with their required population and repair scope, keeping durability and economic repairability separate.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Audit all three community posts at their actual scope and state why they cannot establish camera survival distributions, verified inventory or future parts policy.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify exact serial, condition, shutter, mount, seal, lens, battery, media, firmware, written regional service, parts, quote and reversible actual-use checks with predeclared stops.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a pass, fail or unresolved total-ownership matrix and a conditional lowest-cost passing choice or keep, repair, rent, smaller-system or deferral outcome scoped to exact units and the decision date.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0055",
        "cluster_id": "decade_camera_ownership_exact_unit_serviceability_boundary",
        "difficulty": {"proof_depth": 5, "branching_factor": 20, "distractor_density": 0.40, "contradiction_count": 2},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "required_tradeoffs": [
                    "seller_fields_are_frozen",
                    "k30_conflict_is_preserved",
                    "exact_variant_region_is_required",
                    "model_mapping_is_not_survival",
                    "weather_copy_is_not_ingress",
                    "lens_seal_is_not_system_seal",
                    "mechanisms_need_unit_measurement",
                    "generic_seals_are_scoped",
                    "reliability_needs_defined_conditions",
                    "durability_and_repairability_are_separate",
                    "community_evidence_is_scoped",
                    "exact_inspection_is_required",
                    "written_service_answers_are_required",
                    "reversible_actual_use_trial_is_required",
                    "total_ownership_cost_is_required",
                    "gates_are_pass_fail_unresolved",
                    "fallback_avoids_false_winner",
                    "decision_scope_is_exact_and_dated"
                ]
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 70,
            "minimum_required_evidence_nodes": 20,
            "minimum_reasoning_depth": 5
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
