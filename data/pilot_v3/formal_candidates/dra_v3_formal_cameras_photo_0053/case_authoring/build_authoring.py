#!/usr/bin/env python3
"""Build the audited Q53 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "choose_the_lowest_total_system_cost_exact_path_passing_declared_use_case_"
    "gates_or_keep_separate_paths_or_defer"
)
WHEN = (
    "the_packet_lacks_current_primary_mode_file_and_matched_trial_evidence_for_"
    "the_six_exact_offers"
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


EVIDENCE = [f"E{index}" for index in range(1, 20)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        rule_id: bridge(rules[rule_id])
        for rule_id in (
            "computation_reconstruction_ai_scope_boundary_v1",
            "exact_offer_spec_claim_matrix_v1",
            "optical_digital_zoom_physical_boundary_v1",
            "pixel_count_resolution_sampling_boundary_v1",
            "current_identity_file_metadata_gate_v1",
            "matched_scene_print_zoom_trial_v1",
        )
    }
    rule_definitions["evidence_bounded_camera_spec_choice_v1"] = {
        "type": "decision",
        "decision_matcher": matcher(
            rules["evidence_bounded_camera_spec_choice_v1"]
        ),
        "conclusion_matchers": {
            ANSWER: matcher(
                "Preserve the six exact seller assertions, resolve current identity, units, modes and files, separate pixel count from resolved detail and optical zoom from digital crop, and compare matched declared outputs. Choose only the lowest-total-system-cost exact path that passes every use-case gate; otherwise keep separately validated paths or defer.",
                "Do not select from megapixels, zoom multipliers or AI labels alone. Verify each current product and mode, run the matched chart, scene, zoom and print comparison, and choose the least costly passing exact path, separate paths by use, or defer.",
            )
        },
        "admissible_conditions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(
                    "The packet contains six frozen seller pages, ten general imaging-concept pages and three scoped community discussions, but it lacks current primary mode definitions and sample files for every exact offer and lacks a matched chart, scene, zoom and print trial under the buyer's declared daylight, dim-scene, distant-subject and output conditions."
                ),
                "tradeoff_matchers": {
                    "seller_pages_are_claims_not_quality_measurements": matcher(
                        "The six seller snapshots establish frozen SKU, price, review sample, selected configuration and claim wording, but none independently measures resolved detail, distant-subject quality, dim-scene quality or print quality under one matched protocol."
                    ),
                    "storage_sampling_output_and_print_units_differ": matcher(
                        "Storage capacity, sensor samples, effective or recorded pixels, reconstructed output dimensions and printer dots are different quantities, so the Nikon 64GB card cannot be compared as 64MP and the KUIDAMOS 200 DPI field cannot be ranked directly against camera megapixels."
                    ),
                    "pixel_count_is_only_an_upper_bound": matcher(
                        "A megapixel or output count is an upper bound on image detail rather than a measurement of resolved optical detail, which also depends on the lens, system, environment, contrast, reconstruction and output conditions."
                    ),
                    "panasonic_80mp_is_multishot_output": matcher(
                        "The Panasonic page describes one 80MP RAW output created by eight exposures of a 20.3MP sensor, not a native single-shot 80MP sensor, so motion and multi-exposure artifacts need their own test."
                    ),
                    "zoom_ratio_and_digital_crop_are_not_absolute_detail": matcher(
                        "The Nikon 40x claim is a longest-to-shortest focal-length ratio, its 80x mode is described as enhanced digital zoom, VJIANGER says 16x digital zoom and DJI's 8x text is unlabeled as optical; none of these multipliers alone supplies absolute reach or resolved detail."
                    ),
                    "optical_label_does_not_guarantee_sharpness": matcher(
                        "An optical-zoom label identifies a focal-length path but does not guarantee endpoint sharpness, aperture, autofocus, stabilization or dim-scene performance, and large zoom ranges can involve compromises."
                    ),
                    "ai_claims_name_different_operations": matcher(
                        "TCL's AI-powered camera wording, DJI's clip-combining AI Editor and KUIDAMOS's AI-labelled automatic functions describe unlike or unspecified operations and cannot be collapsed into one proven image-detail enhancement."
                    ),
                    "reconstruction_and_computation_require_separate_tests": matcher(
                        "Binning, Bayer sampling, demosaicing, multi-exposure processing and super-resolution use different inputs and operations and can trade detail, noise, false detail, color artifacts or motion robustness, so each exact mode needs a separate file-level comparison."
                    ),
                    "kuidamos_unit_remains_unresolved": matcher(
                        "The KUIDAMOS 2400W (720P) wording remains an unresolved seller unit and cannot be converted into a validated megapixel count or reconciled with exact output dimensions without current primary material and sample files."
                    ),
                    "community_reports_do_not_transfer": matcher(
                        "The colloquial megapixel explanation, phone-zoom opinions and iPhone complaint with a lens protector are commenter-, device-, accessory-, software-, scene- and viewing-specific and motivate controls rather than product-class conclusions."
                    ),
                    "current_identity_mode_and_file_gate_is_unresolved": matcher(
                        "Physical model, selected configuration, lens or module, firmware, app, manual, mode, zoom setting, stabilization, file type, output dimensions, metadata, RAW or JPEG path, storage and delivered system cost must be verified before a claim-level comparison."
                    ),
                    "matched_trial_separates_optical_digital_and_computational_paths": matcher(
                        "The comparison must match viewpoint, light, target distance, support, focus and declared field of view or framing, retain native files, disable digital zoom for the optical baseline and test crop, binning, multi-shot and other computational modes as separate factors."
                    ),
                    "outcome_thresholds_are_predeclared": matcher(
                        "Resolved chart detail, target detail, noise, false detail, halos, color artifacts, motion blur, ghosting, output size, print size, processing time and failure thresholds must be fixed before inspecting results."
                    ),
                    "results_are_local_to_tested_conditions": matcher(
                        "Any result applies only to the tested unit, firmware, lens or module, mode, scene, illumination, support, file path and output condition and cannot establish a universal brand, megapixel, zoom or AI winner."
                    ),
                    "lowest_cost_passing_path_or_separate_or_defer": matcher(
                        "Choose only the lowest delivered total system cost exact path that passes the declared daylight, dim-scene, distant-subject, detail, artifact, motion, output and workflow gates; if no single path passes, keep separately validated paths or defer."
                    ),
                },
            }
        ],
    }

    negative_rows = [
        ("wrong_largest_mp_wins", "B2", "The seller with the largest megapixel number necessarily resolves the most real detail."),
        ("wrong_64gb_is_64mp", "B2", "The included Nikon 64GB memory card means the camera captures 64-megapixel photographs."),
        ("wrong_panasonic_native_80mp", "B2", "The Panasonic G9 has a native single-shot 80MP image sensor."),
        ("wrong_2400w_is_validated_mp", "B2", "The KUIDAMOS 2400W field is a validated megapixel count that can be ranked directly against 48MP and 64MP."),
        ("wrong_price_proves_quality", "B2", "The Panasonic's higher frozen price proves better image quality than every cheaper offer."),
        ("wrong_rating_proves_detail", "B2", "The Nikon's 73-percent rating over twelve reviews proves more resolved detail than the VJIANGER's 72-percent rating over ten reviews."),
        ("wrong_pixel_count_equals_resolution", "B4", "Every nominal pixel count is itself a measured optical-resolution result."),
        ("wrong_sensor_sites_equal_full_rgb", "B4", "Every Bayer sensor site independently records complete red, green and blue detail for one final pixel."),
        ("wrong_recorded_equals_effective", "B4", "Total, effective, recorded and output pixels are interchangeable labels for exactly the same quantity."),
        ("wrong_dpi_equals_megapixels", "B4", "The KUIDAMOS 200 DPI print number can be compared directly with camera megapixel counts to select the sharpest camera."),
        ("wrong_binning_creates_native_detail", "B4", "Pixel binning creates more native optical detail while preserving the full unbinned output resolution."),
        ("wrong_40x_absolute_reach", "B3", "A 40x optical-zoom label gives an absolute target magnification and reach without knowing the wide and telephoto focal-length endpoints."),
        ("wrong_nikon_80x_optical", "B3", "The Nikon page identifies the entire 80x path as optical zoom."),
        ("wrong_digital_zoom_adds_optical_detail", "B3", "The VJIANGER 16x digital zoom and Nikon enhanced digital zoom add new optical resolution."),
        ("wrong_dji_8x_is_optical", "B3", "The captured DJI page explicitly labels its 8x zoom as optical."),
        ("wrong_optical_always_sharp", "B3", "Any optical-zoom endpoint is necessarily sharper and better in low light than every crop or fixed lens."),
        ("wrong_all_ai_same", "B1", "TCL AI camera, DJI AI Editor and KUIDAMOS AI photography are the same image-enhancement mechanism."),
        ("wrong_dji_editor_improves_stills", "B1", "DJI's clip-combining AI Editor proves improved still-photo resolved detail."),
        ("wrong_kuidamos_ai_validated", "B1", "The KUIDAMOS AI label proves that its automatic features improve measured image quality."),
        ("wrong_computation_always_improves", "B1", "Every computational-photography operation improves every image without a detail, noise, artifact or motion tradeoff."),
        ("wrong_demosaic_is_lossless", "B1", "Demosaicing reconstructs full color without possible lost detail, false color or edge artifacts."),
        ("wrong_super_resolution_breaks_limits", "B1", "Super-resolution creates unlimited physical information and needs no assumptions about multiple exposures or scene invariance."),
        ("wrong_multishot_handles_motion_by_definition", "B1", "An eight-exposure high-resolution mode is automatically valid for moving subjects because its output file is 80MP."),
        ("wrong_infer_manual_from_title", "B5", "Missing current manual, firmware, mode and output definitions may be safely inferred from the frozen seller title."),
        ("wrong_guess_untyped_zoom", "B5", "An unlabeled zoom multiplier may be called optical whenever the product also contains a physical lens."),
        ("wrong_files_not_needed", "B5", "Seller text alone is sufficient, so native sample files, dimensions and metadata need not be checked."),
        ("wrong_accessories_ignored", "B5", "Lens, module, protector, support, storage and selected configuration do not need to be recorded before comparison."),
        ("wrong_unmatched_trial", "B6", "Each camera may be tested from a different viewpoint and under different light, and the resulting detail ranking will still isolate product quality."),
        ("wrong_digital_in_optical_baseline", "B6", "Digital zoom may remain enabled in the optical baseline without affecting interpretation."),
        ("wrong_thresholds_after_results", "B6", "Detail and artifact thresholds should be selected after seeing which product looks best."),
        ("wrong_protector_anecdote_transfers", "B6", "The iPhone lens-protector discussion proves that every distant-detail complaint for every exact offer is caused by an accessory."),
        ("wrong_one_scene_universal", "B6", "One successful chart capture proves universal daylight, dim-scene, distant-subject and print performance across firmware and modes."),
        ("wrong_mix_modes_into_brand", "B6", "A multi-shot or AI mode may be enabled for only one product and the difference attributed solely to brand."),
        ("wrong_choose_before_gates", "D1", "The lowest sticker price or largest specification should be selected before resolving identity and matched performance gates."),
        ("wrong_force_one_camera", "D1", "The answer must name one universal winner even when different paths pass different uses or all paths have unresolved evidence."),
        ("wrong_universal_ai_winner", "D1", "A passing local trial proves that the selected brand and AI system are universally superior."),
    ]
    decidable_claims = [negative(*row) for row in negative_rows]

    g1 = ["E5", "E10", "E11", "E13", "E17", "E18", "B2"]
    g2 = ["E7", "E9", "E12", "E14", "E15", "B4"]
    g3 = ["E4", "E5", "E6", "E8", "E11", "E18", "E19", "B3"]
    g4 = ["E1", "E2", "E3", "E5", "E6", "E10", "E13", "E14", "E16", "E17", "B1"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5"]
    g6 = EVIDENCE + BRIDGES
    g7 = PROOF
    group_specs = [
        (
            "G1",
            "Audit all six exact offers and preserve identity, price, review sample, selected configuration, pixel or output wording, zoom label, AI operation, accessories and unresolved fields without converting seller copy into measured quality.",
            g1,
            "B2",
        ),
        (
            "G2",
            "Separate storage, sampling, total, effective, recorded and output pixels, print dots and measured resolved detail while explaining optical-system, binning and color-sampling limits.",
            g2,
            "B4",
        ),
        (
            "G3",
            "Separate optical focal-length ratio, digital crop enlargement and hybrid or unlabeled zoom claims, and require exact endpoints and matched crop baselines before judging reach or sharpness.",
            g3,
            "B3",
        ),
        (
            "G4",
            "Separate Bayer sampling, demosaicing, binning, multi-shot and super-resolution operations from AI marketing and editing automation, including their possible detail, noise, artifact and motion tradeoffs.",
            g4,
            "B1",
        ),
        (
            "G5",
            "Combine the evidence into a current physical-model, lens or module, firmware, manual, mode, output-dimension, metadata, file-path, storage and total-system-cost gate that blocks unresolved claim-level verdicts.",
            g5,
            "B5",
        ),
        (
            "G6",
            "Specify a small matched chart, daylight, dim-scene, distant-subject, zoom and print comparison with optical, crop and computational modes separated and predeclared detail, noise, artifact, motion and workflow thresholds.",
            g6,
            "B6",
        ),
        (
            "G7",
            "Choose only the lowest-total-system-cost exact path passing all declared use-case gates, otherwise keep separately validated paths or defer without universal brand, megapixel, zoom or AI claims.",
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
        "Audit all six exact offers and preserve frozen identity, price, review count, selected configuration, sensor or output wording, zoom type, AI operation, accessories and missing fields while keeping seller assertions separate from measured image quality.",
        "Distinguish storage, sensor sites, total, effective, recorded and output pixel counts, print dots and resolved optical detail, including binning, Bayer and demosaicing boundaries, without ranking nominal megapixels as measured detail.",
        "Distinguish optical focal-length ratios from digital crops and hybrid or unlabeled zoom, including the Nikon 40x and 80x split, VJIANGER 16x digital path and unlabeled DJI 8x claim, without inferring absolute reach or endpoint sharpness.",
        "Distinguish binning, Bayer reconstruction, demosaicing, multi-shot high-resolution output, super-resolution, camera enhancement and clip-editing automation by inputs, operation and output, and do not credit an unspecified AI label as proven quality.",
        "Verify current physical model, lens or module, firmware, app, manual, capture mode, zoom and stabilization settings, output dimensions, native file metadata, RAW or JPEG path, storage and delivered total system cost before comparison.",
        "Design a small matched chart, daylight, dim-scene, distant-subject, zoom and print trial with optical baselines, crops and computational modes separated and predeclared resolved-detail, noise, artifact, color, motion, ghosting, output and workflow criteria.",
        "Select only the lowest-total-system-cost exact path that passes the declared daylight, dim-scene, distant-subject, detail, artifact, motion, output and workflow gates; otherwise keep separately validated paths or defer without a universal winner.",
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
        "seller_pages_are_claims_not_quality_measurements",
        "storage_sampling_output_and_print_units_differ",
        "pixel_count_is_only_an_upper_bound",
        "panasonic_80mp_is_multishot_output",
        "zoom_ratio_and_digital_crop_are_not_absolute_detail",
        "optical_label_does_not_guarantee_sharpness",
        "ai_claims_name_different_operations",
        "reconstruction_and_computation_require_separate_tests",
        "kuidamos_unit_remains_unresolved",
        "community_reports_do_not_transfer",
        "current_identity_mode_and_file_gate_is_unresolved",
        "matched_trial_separates_optical_digital_and_computational_paths",
        "outcome_thresholds_are_predeclared",
        "results_are_local_to_tested_conditions",
        "lowest_cost_passing_path_or_separate_or_defer",
    ]
    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0053",
        "cluster_id": "camera_spec_claim_physical_boundary",
        "difficulty": {
            "proof_depth": 4,
            "branching_factor": 7,
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
            "human_solve_minutes": 75,
            "minimum_required_evidence_nodes": 19,
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
