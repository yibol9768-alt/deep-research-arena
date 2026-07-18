#!/usr/bin/env python3
"""Build the audited Q56 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "verify_exact_candidates_run_an_output_normalized_task_matched_trial_and_"
    "choose_the_lowest_total_cost_passing_lens_only_if_it_meaningfully_beats_"
    "the_kit_otherwise_keep_rent_save_rerun_or_defer"
)
WHEN = "the_packet_lacks_a_same_body_task_matched_output_normalized_comparison"


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
BRIDGES = [f"B{index}" for index in range(1, 8)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "community_image_workflow_scope_v1": bridge(
            rules["community_image_workflow_scope_v1"]
        ),
        "mount_focal_task_scope_v1": bridge(rules["mount_focal_task_scope_v1"]),
        "optical_design_mechanism_scope_v1": bridge(
            rules["optical_design_mechanism_scope_v1"]
        ),
        "seller_lens_offer_scope_v1": bridge(rules["seller_lens_offer_scope_v1"]),
        "output_artifact_measurement_scope_v1": bridge(
            rules["output_artifact_measurement_scope_v1"]
        ),
        "matched_lens_trial_v1": bridge(rules["matched_lens_trial_v1"]),
        "lens_value_decision_preparation_v1": bridge(
            rules["lens_value_decision_preparation_v1"]
        ),
        "evidence_bounded_lens_purchase_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                rules["evidence_bounded_lens_purchase_decision_v1"]
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "The packet proves no universal lens-value cutoff. Verify exact candidates, run a same-body task-matched and output-normalized trial, and choose only the lowest-total-cost exact lens that passes every gate and meaningfully improves the declared outputs over the actual kit; otherwise keep the kit, rent, save, rerun or defer.",
                    "Select the lowest-cost exact passing lens only after a controlled comparison shows a meaningful benefit over the kit baseline, or use a reversible fallback.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains frozen seller pages, bounded lens-family and optical-mechanism context, and three scoped community images, but lacks verified current samples and a same-body, same-scene, task-matched and output-normalized comparison of the exact lenses."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher(
                            "Keep every SKU, price, aggregate, review count, bundle, import, renewed, white-box, bulk, warranty, coating, sharpness, stabilization and sealing phrase bound to its exact frozen page."
                        ),
                        "bundle_and_lens_prices_differ": matcher(
                            "Treat the existing 4000D and EF-S 18-55mm III as the baseline and do not compare a whole camera bundle price with a lens-only price as equivalent contents or condition."
                        ),
                        "mount_format_and_field_are_required": matcher(
                            "Verify EF versus EF-S fit, APS-C field of view, focal length, autofocus, aperture, stabilization, filters, hoods and body compatibility for every exact candidate."
                        ),
                        "prime_zoom_labels_are_tendencies": matcher(
                            "Prime and zoom category tendencies do not establish that one exact prime is sharper, lighter or better for every declared task."
                        ),
                        "aperture_is_not_a_quality_guarantee": matcher(
                            "Maximum aperture affects exposure and depth of field but does not guarantee sharpness, autofocus success or preferred output."
                        ),
                        "coating_is_a_scoped_mechanism": matcher(
                            "Anti-reflective coating can affect reflection, transmission and contrast, with wavelength and angle dependence, but a premium label does not prove exact-lens performance."
                        ),
                        "aberrations_are_separate": matcher(
                            "Measure chromatic aberration, spherical aberration, vignetting and flare separately under relevant aperture, focus, frame-position and lighting conditions."
                        ),
                        "otf_mtf_is_scale_dependent": matcher(
                            "Treat OTF or MTF as scale-dependent contrast transfer tied to sensor, focus, processing, display and print output rather than one context-free sharpness score."
                        ),
                        "diffraction_has_an_aperture_tradeoff": matcher(
                            "Stopping down can reduce some aberrations but diffraction can eventually reduce detail, so the intended final output must govern aperture comparisons."
                        ),
                        "community_images_are_scoped": matcher(
                            "Keep the Andromeda, macro and moon images tied to their author, camera, lens, subject, distance, tracker, stack, processing, crop, output and missing metadata."
                        ),
                        "exact_sample_checks_are_required": matcher(
                            "Verify exact identity, serial, condition, optics, decentering, focus, aperture, contacts, mount, accessories, warranty, returns, shipping and delivered cost."
                        ),
                        "matched_trial_is_required": matcher(
                            "Use the same body and operator for task-matched trials of indoor family, moving children, portraits, travel, landscape and backlight with field of view, perspective, framing, focus, exposure and output controlled."
                        ),
                        "outcomes_are_separate": matcher(
                            "Record focus and keeper success, center and corner detail, contrast, color fringing, vignetting, flare, depth of field, stabilization, autofocus, carrying, editing and output preference separately."
                        ),
                        "gates_are_predeclared": matcher(
                            "Predeclare meaningful-improvement, compatibility, condition, workflow, output and total-cost gates and mark each pass, fail or unresolved before unblinding."
                        ),
                        "lowest_cost_or_reversible_fallback": matcher(
                            "Choose only the lowest-total-cost exact passing lens that meaningfully improves the declared outputs; otherwise keep the kit, rent, save, rerun or defer."
                        ),
                        "result_scope_is_local": matcher(
                            "Scope any result to the tested body, lens samples, tasks, settings, processing and web or small-print outputs rather than a universal price-to-quality rule."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_kit_bundle_lens_price", "B4", "The 4000D bundle price is the standalone market price of the EF-S 18-55mm III lens."),
        negative("wrong_frozen_stock_current", "B4", "An in-stock field in the frozen packet proves current availability and delivered condition."),
        negative("wrong_rating_optical_score", "B4", "A store aggregate is a standardized optical-quality score across the six exact offers."),
        negative("wrong_l_series_guarantee", "B4", "An L-series label and high frozen price guarantee visibly sharper small prints."),
        negative("wrong_art_guarantee", "B4", "The Art label and renewed testing guarantee that the exact Sigma sample is centered and superior."),
        negative("wrong_import_warranty", "B4", "Import-model wording and a seller warranty prove regional manufacturer coverage."),
        negative("wrong_white_box_support", "B4", "White-box bulk packaging proves normal retail contents, support and return rights."),
        negative("wrong_discontinued_no_issue", "B4", "Manufacturer-discontinued wording has no relevance to current support, return or sample verification."),
        negative("wrong_ef_efs_same", "B2", "EF and EF-S identify identical mount and sensor-format behavior on every Canon body."),
        negative("wrong_50mm_normal_aps_c", "B2", "A 50mm lens has the same normal field of view on Canon APS-C as on full frame."),
        negative("wrong_zoom_range_task_fit", "B2", "A broader zoom range automatically outweighs field of view, aperture, carry and task fit."),
        negative("wrong_any_lens_compatible", "B2", "Every captured lens can be mounted and fully operated on the 4000D without exact compatibility checks."),
        negative("wrong_prime_always_sharper", "B2", "Every prime lens is necessarily sharper than every zoom at every aperture and output size."),
        negative("wrong_wide_aperture_universal", "B2", "The widest maximum aperture makes one lens the universal best value for all tasks."),
        negative("wrong_stabilization_freezes_child", "B2", "Image stabilization by itself freezes a moving child and guarantees keeper success."),
        negative("wrong_coating_premium_winner", "B3", "An anti-reflective coating claim proves the premium lens has the best contrast in every scene."),
        negative("wrong_coating_angle_free", "B3", "Coating performance is independent of wavelength and incident angle."),
        negative("wrong_fast_lens_no_aberration", "B3", "A fast f/1.4 lens cannot exhibit spherical or chromatic aberration."),
        negative("wrong_price_corrects_aberrations", "B3", "Higher price proves that chromatic and spherical aberration are absent from the exact sample."),
        negative("wrong_design_only_resolution", "B3", "Photographic lens design optimizes only maximum resolution and ignores cost, weight and mechanical constraints."),
        negative("wrong_vignetting_always_failure", "B5", "Any peripheral brightness reduction proves a defective lens regardless of aperture, filter, hood or intended effect."),
        negative("wrong_flare_fixed_property", "B5", "One flare result is a context-free property independent of light position, hood and framing."),
        negative("wrong_mtf_single_number", "B5", "One MTF number is a universal sharpness score independent of spatial scale, sensor and final output."),
        negative("wrong_stop_down_always", "B5", "Stopping every lens down as far as possible always improves final detail."),
        negative("wrong_diffraction_irrelevant", "B5", "Diffraction never matters for web or small-print comparisons and may be ignored."),
        negative("wrong_one_center_crop", "B5", "One unmatched center crop is enough to rank center, corner, flare and output performance."),
        negative("wrong_andromeda_lens_only", "B1", "The Andromeda image proves that its lens alone caused the result regardless of tracker, stacking and processing."),
        negative("wrong_macro_upgrade_value", "B1", "One first picture with a new macro lens proves its upgrade value for a Canon APS-C beginner."),
        negative("wrong_moon_metadata_complete", "B1", "The moon post is a controlled lens test even though camera and composite details remain unresolved."),
        negative("wrong_community_cutoff", "B1", "Three attractive community images establish a universal price threshold above which lenses pay off."),
        negative("wrong_skip_decentering", "B6", "Brand reputation allows the buyer to skip sample identity, condition and decentering checks."),
        negative("wrong_unmatched_fov", "B6", "Lenses may be compared from different camera positions and fields of view without affecting the result."),
        negative("wrong_different_outputs", "B6", "An enlarged pixel crop and a small print can be ranked directly without matching final output size."),
        negative("wrong_one_task_all_tasks", "B6", "A portrait result is sufficient to establish value for moving children, travel, landscape and backlight."),
        negative("wrong_price_unmasked", "B6", "Knowing price and lens identity before preference scoring cannot influence the comparison."),
        negative("wrong_one_lucky_frame", "B6", "One sharp frame is enough to establish reliable autofocus and keeper performance."),
        negative("wrong_unresolved_pass", "B7", "An unresolved compatibility, condition, workflow or return field may be treated as a pass."),
        negative("wrong_rating_overrides_gate", "B7", "A high store aggregate may override failed compatibility or output gates."),
        negative("wrong_aperture_overrides_workflow", "B7", "A wider aperture may override failed carrying, editing or intended-output gates."),
        negative("wrong_posthoc_threshold", "B7", "Meaningful improvement may be defined after seeing which lens appears to win."),
        negative("wrong_immediate_kit_winner", "D1", "The packet proves that the kit lens is always sufficient for every small print and web post."),
        negative("wrong_immediate_50mm_winner", "D1", "The packet proves that the Canon 50mm f/1.8 is the unconditional universal-value winner."),
        negative("wrong_immediate_40mm_winner", "D1", "The packet proves that the Canon 40mm f/2.8 is the best normal-use lens because of its aggregate."),
        negative("wrong_immediate_sigma_winner", "D1", "The packet proves that the renewed Sigma 35mm Art is the unconditional best purchase."),
        negative("wrong_immediate_35l_winner", "D1", "The packet proves that the Canon 35mm L must deliver a visible advantage because it costs the most."),
        negative("wrong_immediate_zoom_winner", "D1", "The packet proves that the Canon 24-70mm f/4L is the unconditional best fit."),
        negative("wrong_must_buy", "D1", "The buyer must purchase one captured lens even when no candidate meaningfully beats the kit."),
        negative("wrong_universal_cutoff", "D1", "One local comparison establishes a universal price-to-optical-quality cutoff for all cameras and outputs."),
    ]

    g1 = ["E4", "E5", "E6", "E7", "E9", "E18", "B4"]
    g2 = ["E3", "E4", "E5", "E6", "E7", "E8", "E9", "E17", "E18", "B2"]
    g3 = ["E2", "E10", "E11", "E12", "E15", "E16", "E19", "E20", "B3", "B5"]
    g4 = ["E1", "E13", "E14", "B1"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5", "B6"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit the six exact frozen offers and separate page-bound price, aggregate, condition, bundle, warranty and label claims from current sample quality and output performance.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G2", "description": "Map EF or EF-S compatibility, APS-C field of view, focal length, aperture, autofocus and stabilization to the actual 4000D and each intended task without a prime-or-zoom shortcut.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G3", "description": "Explain coatings, design, chromatic and spherical aberration, vignetting, flare, scale-dependent OTF or MTF and diffraction, and translate each into declared output-specific measurements.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G4", "description": "Keep the Andromeda, macro and moon images at their actual capture, processing and missing-metadata scope rather than treating them as lens-only value evidence.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Verify exact samples and design a reversible same-body, same-operator, task-matched and output-normalized trial with separate optical, focus, workflow and preference outcomes.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B6"},
        {"subgoal_id": "G6", "description": "Mark every meaningful-improvement, compatibility, condition, workflow, output and total-cost gate pass, fail or unresolved and choose the lowest-cost exact passing lens or a reversible fallback.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build an exact-offer table separating frozen seller claims, whole-bundle versus lens-only prices, condition, warranty, labels and unresolved sample fields.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Map mount, sensor format, crop field of view, aperture, autofocus, stabilization and task fit to the actual 4000D baseline.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain and separately measure coating, aberration, vignetting, flare, contrast-transfer and diffraction effects for declared apertures and final outputs.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Audit each community image at its camera, lens, scene, capture, tracker, stack, processing, crop, output and missing-metadata scope.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify exact sample checks and the smallest reversible same-body task-matched trial with normalized framing and web or small-print outputs and separate outcome records.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a pass, fail or unresolved value matrix and a conditional lowest-cost purchase, keep-kit, rental, saving, corrected-rerun or deferral outcome scoped to the tested samples and tasks.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0056",
        "cluster_id": "kit_lens_premium_glass_task_output_value_boundary",
        "difficulty": {
            "proof_depth": 5,
            "branching_factor": 20,
            "distractor_density": 0.40,
            "contradiction_count": 2,
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
                    "bundle_and_lens_prices_differ",
                    "mount_format_and_field_are_required",
                    "prime_zoom_labels_are_tendencies",
                    "aperture_is_not_a_quality_guarantee",
                    "coating_is_a_scoped_mechanism",
                    "aberrations_are_separate",
                    "otf_mtf_is_scale_dependent",
                    "diffraction_has_an_aperture_tradeoff",
                    "community_images_are_scoped",
                    "exact_sample_checks_are_required",
                    "matched_trial_is_required",
                    "outcomes_are_separate",
                    "gates_are_predeclared",
                    "lowest_cost_or_reversible_fallback",
                    "result_scope_is_local",
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
            "human_solve_minutes": 65,
            "minimum_required_evidence_nodes": 20,
            "minimum_reasoning_depth": 5,
        },
    }
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
