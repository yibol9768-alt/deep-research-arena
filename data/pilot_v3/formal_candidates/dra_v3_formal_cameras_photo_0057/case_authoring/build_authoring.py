#!/usr/bin/env python3
"""Build the audited Q57 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_verified_lowest_total_cost_passing_path_or_defer"
WHEN = (
    "the_packet_lacks_a_verified_coworker_unit_and_a_matched_repeatable_"
    "family_photo_trial"
)


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
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    bridge_rule_ids = (
        "frozen_offer_identity_condition_matrix_v1",
        "generation_feature_mechanism_boundary_v1",
        "used_unit_inspection_gate_v1",
        "complete_kit_cost_gate_v1",
        "task_matched_family_photo_trial_v1",
        "community_scope_boundary_v1",
    )
    rule_definitions = {
        rule_id: bridge(rules[rule_id]) for rule_id in bridge_rule_ids
    }
    rule_definitions["incremental_value_decision_v1"] = {
        "type": "decision",
        "decision_matcher": matcher(rules["incremental_value_decision_v1"]),
        "conclusion_matchers": {
            ANSWER: matcher(
                "Verify and inspect the actual used unit, normalize every candidate into a complete task-equivalent kit, run the matched and repeatable family-photo trial, and choose the lowest-total-cost path that passes all mandatory thresholds. Prefer the used path if it passes unless a newer path delivers a predeclared repeatable incremental gain; otherwise borrow, rent, keep the phone or defer.",
                "Do not choose from age, megapixels, feature counts or sticker prices. Buy only the verified lowest-cost complete path that clears every declared family use, and defer or use a temporary alternative when identity, condition, comparable-kit cost or repeatable task evidence remains unresolved.",
            )
        },
        "admissible_conditions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(
                    "The packet freezes six unlike seller listings, five matching model histories, six general mechanism pages and three scoped community discussions, but it does not identify or inspect the coworker's physical unit, does not price equivalent complete kits and does not contain a matched repeatable daylight, dim-indoor, moving-subject, close-subject and handheld-video trial."
                ),
                "tradeoff_matchers": {
                    "seller_pages_are_frozen_assertions_not_current_controlled_results": matcher(
                        "The six seller snapshots establish frozen SKU, price, review sample, condition or configuration wording, bundle contents and nominal claims, not current availability, physical-unit condition or a controlled family-photo result."
                    ),
                    "listing_date_is_not_model_release_or_unit_age": matcher(
                        "A seller Date First Available field belongs to the listing and cannot substitute for model release date, manufacture date, firmware age, usage age or the condition of the coworker's physical unit; model histories place the D7000 and 7D in 2010 and 2009 and the a7 III, Z6 and EOS R in 2018."
                    ),
                    "feature_counts_are_not_task_success_rates": matcher(
                        "Release year, megapixels, sensor class, ISO ceiling, AF-point count, coverage and burst rate describe capabilities but do not measure daylight portrait quality, dim-scene noise, moving-child keeper rate, close focus or video stability."
                    ),
                    "bsi_and_cmos_mechanisms_do_not_quantify_exact_gain": matcher(
                        "BSI can increase captured light and CMOS capability improved over time, but exact low-light gain still depends on sensor area, pixel design, lens aperture, exposure, processing, firmware and output conditions and must be measured on the compared paths."
                    ),
                    "af_architecture_needs_keeper_rate_testing": matcher(
                        "AF point count and coverage, phase or contrast detection, face or eye recognition, lens motor, firmware and subject tracking are separate factors, so the relevant result is a repeated task-matched acquisition and keeper rate rather than the largest AF number."
                    ),
                    "stabilization_does_not_freeze_subject_motion": matcher(
                        "Lens or body stabilization can reduce ordinary camera-shake blur at slower shutter speeds but does not stop a moving child or pet, so subject motion still requires suitable shutter speed, exposure and focus tracking."
                    ),
                    "evf_is_a_workflow_change_not_file_quality_proof": matcher(
                        "An EVF can preview exposure and white balance and show focus aids, but display dynamic range and processing lag remain possible tradeoffs and the viewfinder does not by itself improve the captured file."
                    ),
                    "silent_electronic_readout_can_have_motion_cost": matcher(
                        "Electronic silent modes can read a sensor line by line, so moving subjects, camera vibration or flashes can skew or wobble even when the feature removes shutter sound; exact readout speed needs a relevant motion test."
                    ),
                    "dynamic_range_requires_matched_files_and_outputs": matcher(
                        "Dynamic range concerns the luminance range captured and how far files can be pushed without a large noise increase, so it must be compared with matched exposure, native files and final display or print conditions rather than used as a universal image-quality score."
                    ),
                    "used_gear_opinions_do_not_replace_inspection": matcher(
                        "The community thread contains both an older-prosumer value claim and a warning about scams, overpayment and latent defects, so it motivates serial, condition, file-integrity, service and return checks rather than proving used gear is always the smarter buy."
                    ),
                    "practice_and_processing_are_generation_confounds": matcher(
                        "The Jupiter progress thread retains the core telescope but changes practice, weather, Barlow, tracking, frame count, stacking and editing, showing that workflow can change output and must be controlled rather than proving hardware is irrelevant."
                    ),
                    "close_focus_is_a_task_specific_lens_mode_check": matcher(
                        "The newer-phone close-focus complaint involves a five-inch distance and different telephoto, macro and minimum-focus-distance paths, so it motivates an exact close-subject test and does not establish a universal newer-is-worse result."
                    ),
                    "physical_used_unit_gate_is_unresolved": matcher(
                        "The actual body, regional variant, serial, ownership, firmware, actuations, sensor, mount, stabilization, AF, controls, ports, slots, display, battery, charger, errors, impact or weather signs, native RAW and JPEG integrity and service or return terms must pass before purchase."
                    ),
                    "complete_kits_replace_body_sticker_comparisons": matcher(
                        "Compare complete task-equivalent paths with an appropriate lens, healthy battery and charger, storage, adapter, delivery, immediate service and risk allowance; body-only, lens-included and accessory-heavy bundle prices cannot be ranked directly."
                    ),
                    "matched_blinded_trial_uses_predeclared_thresholds": matcher(
                        "Use matched field of view, effective aperture, viewpoint, distance, light, subject path, output size and operator practice for daylight, dim stationary, moving, close and handheld-video tasks, blind outputs when possible, and predeclare keeper-rate, blur, noise, highlight, skew, stability, battery, handling and workflow thresholds."
                    ),
                    "results_are_local_and_need_repeatability": matcher(
                        "Repeat enough trials to distinguish a stable gain from chance, preserve native files and attribute results only to the tested unit, lens, adapter, firmware, settings, subject, light and output rather than to an entire brand or generation."
                    ),
                    "incremental_value_selects_lowest_passing_or_defers": matcher(
                        "Choose the verified used path if it clears every mandatory gate unless a newer path supplies a repeatable predeclared threshold-crossing gain worth its incremental complete-kit cost; otherwise choose the lowest-cost passing path, borrow, rent, keep the phone or defer."
                    ),
                },
            }
        ],
    }

    negative_rows = [
        ("wrong_listing_date_is_release", "B1", "The seller Date First Available field proves the camera model's original release year and the age of the physical unit."),
        ("wrong_title_proves_exact_variant", "B1", "A similar product title is enough to merge every D7000, 7D, A300, a7 III, Z6 or EOS R variant into one exact identity."),
        ("wrong_rating_proves_keeper_rate", "B1", "The 7D's 100-percent rating over eight reviews proves a higher moving-subject keeper rate than every unrated camera."),
        ("wrong_price_proves_generation", "B1", "The highest frozen seller price necessarily identifies the newest model generation and best physical condition."),
        ("wrong_renewed_equals_coworker_condition", "B1", "The renewed D7000 seller wording proves that the coworker's separate unit was professionally inspected and looks like new."),
        ("wrong_bundle_accessory_is_primary_lens", "B1", "Every telephoto or wide-angle accessory in a bundle is automatically an equivalent primary interchangeable lens for the family-photo tasks."),
        ("wrong_largest_mp_wins", "B2", "The EOS R's 30.3MP claim proves better ordinary family photos than every lower-megapixel path."),
        ("wrong_newer_always_better_sensor", "B2", "Any 2018 camera sensor must outperform every 2009 or 2010 camera in every light, lens and output condition."),
        ("wrong_bsi_exact_stop_gain", "B2", "A BSI label alone proves a fixed multi-stop low-light advantage for the exact Z6 or a7 III bundle."),
        ("wrong_cmos_always_beats_ccd", "B2", "The general improvement of modern CMOS proves every CMOS camera beats every CCD camera regardless of sensor area, lens, exposure and output."),
        ("wrong_af_points_equal_accuracy", "B2", "The camera with the most selectable AF points necessarily produces the highest focus accuracy and keeper rate for every subject."),
        ("wrong_eye_af_needs_no_firmware", "B2", "Eye-detection performance is fixed at model launch and does not depend on installed firmware, subject, lens or settings."),
        ("wrong_ibis_freezes_child", "B2", "In-body image stabilization freezes a moving child or pet at a slow shutter speed."),
        ("wrong_ois_and_ibis_identical", "B2", "Lens stabilization, sensor-shift stabilization and combined stabilization are interchangeable labels with identical effects on every lens and mode."),
        ("wrong_evf_improves_raw", "B2", "An electronic viewfinder directly increases the dynamic range and detail stored in the RAW file."),
        ("wrong_evf_has_no_latency", "B2", "An EVF always has zero processing latency and unlimited display dynamic range."),
        ("wrong_silent_shutter_free", "B2", "A silent electronic shutter has no motion, flash, skew or mode tradeoff because it has no mechanical sound."),
        ("wrong_dynamic_range_universal_score", "B2", "A single dynamic-range number is a complete universal image-quality score independent of exposure, noise, processing and output."),
        ("wrong_skip_serial", "B3", "The coworker's verbal description is enough, so serial, ownership, exact variant and firmware do not need verification."),
        ("wrong_skip_shutter_count", "B3", "An old body needs no actuation, sensor, mount, control, port, card-slot or battery inspection if it powers on."),
        ("wrong_jpeg_only_inspection", "B3", "One resized social-media JPEG is sufficient to establish sensor, focus and native-file integrity."),
        ("wrong_no_return_risk", "B3", "Missing return rights and uncertain repairability have zero value and need not enter the used-unit gate."),
        ("wrong_body_price_complete", "B4", "A body-only sticker price can be compared directly with a lens kit or accessory bundle as a complete family-photo system."),
        ("wrong_storage_means_optical_path", "B4", "A 64GB or 128GB memory card makes a bundle optically complete and comparable without a task lens."),
        ("wrong_adapter_full_support_assumed", "B4", "Any mount adapter automatically preserves autofocus, stabilization and aperture control for every older lens."),
        ("wrong_ignore_battery_service", "B4", "Battery health, charger, storage, immediate service, delivery and expected repair costs may be omitted from incremental cost."),
        ("wrong_unmatched_lenses", "B5", "Bodies may be compared with arbitrary lenses, fields of view and apertures and the result still isolates camera generation."),
        ("wrong_different_light", "B5", "Each camera may be tested under different light and subject motion while retaining a valid low-light and AF ranking."),
        ("wrong_thresholds_after", "B5", "Keeper-rate, noise, blur and video-skew thresholds should be chosen after seeing which camera wins."),
        ("wrong_one_frame_enough", "B5", "One successful photograph is enough to prove a stable autofocus, noise and stabilization advantage."),
        ("wrong_stabilization_motion_test", "B5", "A stationary stabilized scene alone establishes performance for a moving child or pet."),
        ("wrong_close_focus_omit", "B5", "Minimum focus distance and available macro or telephoto paths do not need testing for close tabletop subjects."),
        ("wrong_forum_used_always_best", "B6", "The used-prosumer comment proves old professional bodies are always a better beginner purchase than new entry-level cameras."),
        ("wrong_forum_old_5d_universal", "B6", "One comment about an old 5D Mark II proves every decade-old body is sufficient for every still and video use."),
        ("wrong_same_telescope_hardware_irrelevant", "B6", "The Jupiter progress post proves camera hardware never affects image quality because the telescope stayed the same."),
        ("wrong_phone_newer_always_worse", "B6", "The iPhone close-focus complaint proves all newer cameras are worse than older cameras at all distances."),
        ("wrong_community_is_controlled", "B6", "Community comments are controlled product tests whose conclusions transfer across units, lenses, firmware, subjects and outputs."),
        ("wrong_always_buy_old", "D1", "A cheap decade-old body should always be purchased once it can produce one good daylight still."),
        ("wrong_always_buy_new", "D1", "A newer-generation body should always be purchased because autofocus and sensor technology advanced."),
        ("wrong_choose_before_inspection", "D1", "Select the lowest sticker price before the used-unit, complete-kit and matched-trial gates are resolved."),
        ("wrong_force_universal_winner", "D1", "The answer must name one universal generation winner even when different paths pass different tasks or evidence remains unresolved."),
        ("wrong_local_result_brand_verdict", "D1", "One passing local trial proves that the selected brand and generation are universally superior."),
    ]
    decidable_claims = [negative(*row) for row in negative_rows]

    g1 = ["E2", "E3", "E4", "E5", "E7", "E8", "E14", "E15", "E17", "E18", "E19", "B1"]
    g2 = ["E1", "E3", "E5", "E6", "E7", "E9", "E10", "E15", "E16", "E19", "E20", "B2"]
    g3 = ["E2", "E8", "E13", "E17", "B1", "B3"]
    g4 = ["E4", "E14", "E18", "B1", "B3", "B4"]
    g5 = ["E9", "E10", "E11", "E16", "E20", "B2", "B3", "B4", "B5"]
    g6 = ["E11", "E12", "E13", "B5", "B6"]
    g7 = PROOF
    group_specs = [
        (
            "G1",
            "Audit six frozen offers and five matching model histories, preserving exact identity, condition, price, review sample, lens or bundle completeness, feature wording and the boundary between listing date, model release and physical-unit age.",
            g1,
            "B1",
        ),
        (
            "G2",
            "Separate sensor layout and generation, AF architecture, stabilization, EVF preview, sensor readout and dynamic range into scoped mechanisms without converting nominal features into measured family-photo success.",
            g2,
            "B2",
        ),
        (
            "G3",
            "Specify a fail-closed inspection and native-file gate for the coworker's exact body, including identity, firmware, actuations, sensor, mount, controls, battery, storage, errors, service and return risk.",
            g3,
            "B3",
        ),
        (
            "G4",
            "Normalize every candidate into a complete task-equivalent optical path and calculate delivered incremental cost including lens, adapter, battery, charger, storage, service and risk allowance.",
            g4,
            "B4",
        ),
        (
            "G5",
            "Design a small matched and preferably blinded daylight, dim-stationary, moving-subject, close-subject and handheld-video trial with native files, repetitions and predeclared output and workflow thresholds.",
            g5,
            "B5",
        ),
        (
            "G6",
            "Use community reports only as hypotheses and confound warnings, separating used-value opinions, practice and processing changes, and lens or minimum-focus-distance regressions from generation verdicts.",
            g6,
            "B6",
        ),
        (
            "G7",
            "Choose the verified lowest-total-cost complete path passing every mandatory task, prefer the used path when it passes unless a repeatable newer-path gain clears the incremental-value threshold, or borrow, rent, keep the phone or defer.",
            g7,
            "D1",
        ),
    ]
    subgoals = [
        {
            "subgoal_id": goal_id,
            "description": description,
            "critical": True,
            "requires": slots,
            "local_conclusion_slot_id": conclusion,
        }
        for goal_id, description, slots, conclusion in group_specs
    ]

    requirement_texts = [
        "Audit all six exact frozen offers and the five matching model histories, preserving SKU, price, review count, condition, selected configuration, lens or bundle contents and nominal claims, and distinguish listing date, model release date and physical-unit age.",
        "Explain BSI and CMOS evolution, AF point count and coverage, face or eye tracking, lens and body stabilization, EVF preview, rolling readout and dynamic range as separate mechanisms, and do not use release year, megapixels or feature counts as measured task success.",
        "Require exact body and regional identity, serial and ownership, firmware, actuations, sensor and mount condition, controls, ports, card slots, stabilization, AF, battery, charger, error history, native RAW and JPEG integrity and service or return terms before purchase.",
        "Construct complete task-equivalent kits with appropriate lenses, verified adapter behavior, healthy battery and charger, storage, delivery, immediate service and risk allowance, and calculate incremental delivered cost only after the used unit passes inspection.",
        "Run matched daylight portrait, dim stationary, moving child or pet, close tabletop and short handheld-video trials with controlled lens, field of view, aperture, viewpoint, light, subject path, output and operator practice, blinded outputs where possible, repetitions and predeclared success thresholds.",
        "Keep the used-gear debate, same-telescope progress and newer-phone close-focus complaint at their exact author, unit, lens, distance, skill, accessory, processing and output scope, using them to identify confounds and tests rather than product-class verdicts.",
        "Choose the verified lowest-total-cost complete path that passes every mandatory family task, prefer the used path when it passes unless a repeatable newer-path gain clears a predeclared incremental-value threshold, or borrow, rent, keep the phone or defer without a universal old-versus-new winner.",
    ]
    groups = [g1, g2, g3, g4, g5, g6, g7]
    requirements = [
        {
            "requirement_id": f"Q{index}",
            "text": text,
            "slot_ids": slots,
            "subgoal_ids": [f"G{index}"],
            "required": True,
        }
        for index, (text, slots) in enumerate(zip(requirement_texts, groups), 1)
    ]

    required_tradeoffs = [
        "seller_pages_are_frozen_assertions_not_current_controlled_results",
        "listing_date_is_not_model_release_or_unit_age",
        "feature_counts_are_not_task_success_rates",
        "bsi_and_cmos_mechanisms_do_not_quantify_exact_gain",
        "af_architecture_needs_keeper_rate_testing",
        "stabilization_does_not_freeze_subject_motion",
        "evf_is_a_workflow_change_not_file_quality_proof",
        "silent_electronic_readout_can_have_motion_cost",
        "dynamic_range_requires_matched_files_and_outputs",
        "used_gear_opinions_do_not_replace_inspection",
        "practice_and_processing_are_generation_confounds",
        "close_focus_is_a_task_specific_lens_mode_check",
        "physical_used_unit_gate_is_unresolved",
        "complete_kits_replace_body_sticker_comparisons",
        "matched_blinded_trial_uses_predeclared_thresholds",
        "results_are_local_and_need_repeatability",
        "incremental_value_selects_lowest_passing_or_defers",
    ]
    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0057",
        "cluster_id": "old_body_generation_gain_boundary",
        "difficulty": {
            "proof_depth": 6,
            "branching_factor": 7,
            "distractor_density": 0.38,
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
                "required_tradeoffs": required_tradeoffs,
            }
        ],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {
                evidence_id: {"outcome": "decision_unresolved"}
                for evidence_id in EVIDENCE
            },
            "human_solve_minutes": 90,
            "minimum_required_evidence_nodes": 20,
            "minimum_reasoning_depth": 6,
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
                "requirements": len(requirements),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
