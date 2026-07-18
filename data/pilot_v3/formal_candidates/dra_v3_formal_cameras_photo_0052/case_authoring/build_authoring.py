#!/usr/bin/env python3
"""Build the audited Q52 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_lowest_total_cost_exact_passing_system_otherwise_rent_borrow_test_keep_the_phone_save_or_defer"
WHEN = "the_packet_lacks_verified_current_complete_systems_and_same_gym_results"


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
BRIDGES = [f"B{index}" for index in range(1, 9)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "autofocus_burst_sports_scope_v1": bridge(rules["autofocus_burst_sports_scope_v1"]),
        "community_phone_settings_scope_v1": bridge(rules["community_phone_settings_scope_v1"]),
        "exposure_motion_noise_tradeoff_v1": bridge(rules["exposure_motion_noise_tradeoff_v1"]),
        "frozen_offer_identity_budget_scope_v1": bridge(rules["frozen_offer_identity_budget_scope_v1"]),
        "model_release_sensor_mapping_v1": bridge(rules["model_release_sensor_mapping_v1"]),
        "lens_mount_total_system_cost_boundary_v1": bridge(rules["lens_mount_total_system_cost_boundary_v1"]),
        "same_gym_matched_trial_protocol_v1": bridge(rules["same_gym_matched_trial_protocol_v1"]),
        "first_camera_decision_preparation_v1": bridge(rules["first_camera_decision_preparation_v1"]),
        "first_camera_pass_fail_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(rules["first_camera_pass_fail_decision_v1"]),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no automatic camera winner. Choose only the lowest-total-cost exact complete system that passes identity, condition, compatibility, reach, aperture, autofocus, burst, same-gym output, handling and budget gates; otherwise rent, borrow, test, keep the phone, save or defer.",
                    "Verify current exact complete systems and compare them in the same gym. Select the lowest-total-cost passing option, or use a reversible fallback when no option passes or required fields remain unresolved.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains frozen camera and lens seller pages, bounded model and photography context, and three scoped community posts, but lacks verified current condition and delivered complete-system cost and lacks a controlled same-gym comparison of motion freeze, focus, noise, detail, keeper rate and handling."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher("All SKU, price, stock, rating, review, bundle, warranty, feature and performance wording remains a frozen seller assertion rather than a current delivered offer or independent result."),
                        "budget_anchor_is_unverified": matcher("The 700-dollar amount remains a buyer anchor until tax, shipping, lens, accessories and exact delivered cost are verified."),
                        "complete_system_cost_is_required": matcher("Do not compare a body-only price with a fixed-lens bundle as complete systems; add the exact compatible sport lens and required accessories."),
                        "model_mapping_is_not_ranking": matcher("Keep the E-M1, LX10, 80D and ZS70 release, sensor-format, mount and fixed-versus-interchangeable mappings exact without treating age or format as a winner."),
                        "sensor_age_metrics_are_not_winners": matcher("Sensor area, release year, megapixels, zoom ratio and store ratings cannot by themselves establish indoor-volleyball quality or keeper rate."),
                        "exposure_is_joint": matcher("Analyze shutter time, aperture, ISO or gain, noise, field of view, reach and output normalization jointly for motion in dim light."),
                        "stabilization_is_not_subject_freeze": matcher("Image stabilization may address camera shake but does not by itself freeze a moving volleyball player."),
                        "af_burst_need_field_validation": matcher("Generic autofocus, burst and sports-photography descriptions do not establish tracking, buffer, flicker or keeper rate for an exact unit and lens."),
                        "community_evidence_is_scoped": matcher("The three forum pages remain author-, device-, sample-, question- and time-scoped rather than controlled phone or dedicated-camera benchmarks."),
                        "exact_condition_and_compatibility_are_required": matcher("Verify exact model, condition, shutter count, battery, mount, lens, aperture, reach, autofocus mode, burst, buffer, card, warranty, return and delivered cost before purchase."),
                        "same_gym_matching_is_required": matcher("Compare candidates in the same gym, position, volleyball action and output size with declared setting strategies and repeated bursts."),
                        "outcomes_are_separate": matcher("Record motion-freeze rate, focus-hit rate, noise and retained detail, keeper rate, handling failures and total cost as separate outcomes."),
                        "gates_are_pass_fail_unresolved": matcher("Mark every identity, condition, compatibility, reach, aperture, autofocus, burst, output, handling and budget gate pass, fail or unresolved before deciding."),
                        "lowest_cost_or_reversible_fallback": matcher("Choose the lowest-total-cost exact passing system; if none passes, rent, borrow, run a corrected test, keep the phone, save or defer."),
                        "decision_scope_is_local": matcher("Report the result only for the tested gym, actions, position, output size, budget and exact units, not as a universal sensor-size or release-year rule."),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_olympus_price_current", "B4", "The frozen 668-dollar Olympus body page is necessarily a current delivered complete-system price."),
        negative("wrong_olympus_rating_quality", "B4", "The Olympus 93-percent store rating proves better image quality than the other cameras."),
        negative("wrong_zs70_rating_winner", "B4", "The ZS70 95-percent rating proves that it is the best indoor-volleyball camera."),
        negative("wrong_lx10_bundle_complete", "B4", "The LX10 bundle text proves every accessory, warranty and delivered term is current and suitable."),
        negative("wrong_canon_within_budget", "B4", "The 798-dollar Canon body page fits a 700-dollar complete-system budget before adding a lens."),
        negative("wrong_frozen_stock_current", "B4", "An in-stock field in the frozen packet proves current availability."),
        negative("wrong_older_always_better", "B5", "The 2013 E-M1 must win because it has a larger sensor than the newer compact."),
        negative("wrong_newer_always_better", "B5", "The newer small-sensor compact must win because release year dominates sensor and lens differences."),
        negative("wrong_megapixels_quality", "B5", "A higher megapixel count by itself proves higher indoor-sports image quality."),
        negative("wrong_zoom_quality", "B5", "A 30x zoom ratio by itself proves better action-photo quality or useful indoor aperture."),
        negative("wrong_sensor_format_complete_rank", "B5", "Sensor format alone determines the final ranking regardless of lens, exposure, autofocus, output size and technique."),
        negative("wrong_field_of_view_is_quality", "B5", "A field-of-view difference is itself proof of better light gathering, focus or image quality."),
        negative("wrong_body_price_complete", "B6", "A body-only camera at the budget ceiling is a complete volleyball system without a lens."),
        negative("wrong_any_lens_any_mount", "B6", "Either frozen fast telephoto can be attached to any captured camera without checking mount."),
        negative("wrong_lens_cost_ignored", "B6", "Lens and accessory costs may be omitted when testing the 700-dollar ceiling."),
        negative("wrong_panasonic_lens_required", "B6", "The 897.99-dollar Panasonic lens is proven to be the only valid lens for the Olympus body."),
        negative("wrong_sigma_lens_required", "B6", "The 999-dollar Sigma lens is proven to be the only valid lens for the Canon 80D."),
        negative("wrong_wide_aperture_guarantees", "B3", "A low f-number by itself guarantees a sharp low-noise volleyball result."),
        negative("wrong_fast_shutter_no_cost", "B3", "A faster shutter freezes motion without reducing the light admitted during exposure."),
        negative("wrong_noise_only_sensor", "B3", "Image noise is determined only by sensor size and not by captured light, exposure, gain, processing or output normalization."),
        negative("wrong_stabilization_freezes_player", "B3", "Image stabilization proves that a moving volleyball player will be frozen."),
        negative("wrong_one_iso_rule", "B3", "One ISO number is universally optimal across gyms, lenses, output sizes and cameras."),
        negative("wrong_generic_af_proves_tracking", "B1", "The general autofocus definition proves exact tracking accuracy for every candidate camera."),
        negative("wrong_burst_proves_keeper", "B1", "A seller burst-rate claim proves focus retention, buffer endurance and keeper rate."),
        negative("wrong_sports_page_mandate", "B1", "The sports-photography page mandates one exact body and lens for this buyer."),
        negative("wrong_reach_ignores_position", "B1", "A focal-length number proves adequate framing without the buyer's position and action distance."),
        negative("wrong_forum_phone_category", "B2", "One iPhone oversharpening report proves that every phone is worse than every dedicated camera."),
        negative("wrong_forum_android_benchmark", "B2", "One author's Android comparison is a controlled camera-category benchmark."),
        negative("wrong_forum_setting_authority", "B2", "A forum question establishes an authoritative low-light ISO, aperture and shutter prescription."),
        negative("wrong_file_size_quality", "B2", "A larger photo file size by itself proves better image quality."),
        negative("wrong_unmatched_gym_comparison", "B7", "Cameras can be compared across different gyms, positions, actions and output sizes without bias."),
        negative("wrong_one_lucky_frame", "B7", "One lucky sharp frame is sufficient evidence of a reliable camera system."),
        negative("wrong_keeper_hides_focus", "B7", "A single overall impression can replace separate motion-freeze, focus-hit, noise-detail and keeper-rate records."),
        negative("wrong_condition_not_needed", "B7", "Used condition, shutter count, battery health and return terms do not matter for the exact unit decision."),
        negative("wrong_posthoc_thresholds", "B7", "Pass thresholds may be invented after inspecting which camera looked best."),
        negative("wrong_rating_overrides_gate", "B8", "A high store rating can override failed compatibility, condition, field-test or budget gates."),
        negative("wrong_sensor_overrides_cost", "B8", "A larger sensor can override an unresolved or over-budget complete-system cost."),
        negative("wrong_handling_ignored", "B8", "Handling failures may be ignored if image quality looks good in a few frames."),
        negative("wrong_unresolved_treated_pass", "B8", "An unresolved identity, condition or compatibility field may be treated as a pass."),
        negative("wrong_immediate_olympus_winner", "D1", "The packet already proves that the Olympus E-M1 is the unconditional best purchase."),
        negative("wrong_immediate_zs70_winner", "D1", "The packet already proves that the Panasonic ZS70 is the unconditional best purchase."),
        negative("wrong_immediate_lx10_winner", "D1", "The packet already proves that the Panasonic LX10 is the unconditional best purchase."),
        negative("wrong_immediate_canon_winner", "D1", "The packet already proves that the Canon 80D is the unconditional best purchase."),
        negative("wrong_must_buy_now", "D1", "The buyer must purchase one captured listing immediately even if no complete system passes."),
        negative("wrong_universal_sensor_year_rule", "D1", "One result establishes a universal rule that sensor size or release year determines camera quality."),
    ]

    g1 = ["E3", "E4", "E9", "E10", "E12", "E13", "E19", "E20", "B4", "B5"]
    g2 = ["E4", "E13", "E14", "E17", "B4", "B5", "B6"]
    g3 = ["E5", "E6", "E11", "E15", "E16", "B3"]
    g4 = ["E1", "E3", "E4", "E9", "E12", "E18", "E19", "B1"]
    g5 = ["E2", "E7", "E8", "B1", "B2", "B3", "B5", "B6", "B7"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit the four frozen camera offers and independently map exact model, release, sensor format, mount and fixed-versus-interchangeable lens form without ranking by age or sensor alone.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G2", "description": "Separate body-only from fixed-lens bundle prices, verify mount and lens identity, and calculate the complete compatible system cost against the 700-dollar anchor.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B6"},
        {"subgoal_id": "G3", "description": "Explain the joint sensor-format, aperture, exposure-time, motion-blur, gain and noise tradeoff without treating stabilization or one variable as a guaranteed result.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G4", "description": "Bound autofocus, continuous shooting, lens reach and indoor-sports context and identify the tracking, buffer, flicker and keeper-rate questions requiring field validation.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Keep the three community pages scoped and design a repeated same-gym, same-position, same-action and normalized-output trial with separate motion, focus, noise-detail, keeper, handling and cost outcomes.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G6", "description": "Mark every complete-system gate pass, fail or unresolved and select the lowest-total-cost exact passing system or a reversible fallback without a universal sensor-size or release-year conclusion.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build an exact four-camera table separating frozen seller assertions from model facts, condition unknowns, release, sensor format, lens form, price and rating fields.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Compute complete-system cost only after exact body, mount, compatible lens, aperture, reach, accessories, tax and shipping are verified against the budget anchor.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain the linked field-of-view, aperture, shutter, motion-blur, ISO or gain, noise and output-size tradeoffs and why stabilization does not freeze subject motion.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Explain what autofocus, burst and sports-photography context can and cannot prove and specify the exact action-specific questions for testing.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Scope all community claims and specify the repeated same-gym trial, exact condition and compatibility checks, normalized outputs, separate metrics and predeclared stops.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a pass, fail or unresolved table and a conditional lowest-total-cost purchase or rent, borrow, corrected-test, keep-phone, save or deferral decision scoped to the tested units and gym.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0052",
        "cluster_id": "first_dedicated_camera_indoor_sports_sensor_age_system_boundary",
        "difficulty": {"proof_depth": 5, "branching_factor": 20, "distractor_density": 0.38, "contradiction_count": 2},
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
                    "budget_anchor_is_unverified",
                    "complete_system_cost_is_required",
                    "model_mapping_is_not_ranking",
                    "sensor_age_metrics_are_not_winners",
                    "exposure_is_joint",
                    "stabilization_is_not_subject_freeze",
                    "af_burst_need_field_validation",
                    "community_evidence_is_scoped",
                    "exact_condition_and_compatibility_are_required",
                    "same_gym_matching_is_required",
                    "outcomes_are_separate",
                    "gates_are_pass_fail_unresolved",
                    "lowest_cost_or_reversible_fallback",
                    "decision_scope_is_local"
                ]
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 60,
            "minimum_required_evidence_nodes": 20,
            "minimum_reasoning_depth": 5
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
