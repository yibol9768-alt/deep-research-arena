#!/usr/bin/env python3
"""Build the audited Q54 compact-camera CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "verify_one_exact_returnable_camera_run_a_recipient_matched_trial_against_her_actual_phone_and_buy_only_if_every_predeclared_gate_passes_with_a_meaningful_advantage_otherwise_improve_the_phone_workflow_choose_printing_support_rerun_or_defer"
WHEN = "seller_aggregates_and_scoped_feedback_do_not_establish_current_exact_unit_or_recipient_fit_without_a_matched_trial"


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


EVIDENCE = [f"E{index}" for index in range(1, 17)]
BRIDGES = [f"B{index}" for index in range(1, 9)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        "seller_rating_offer_scope_v1": bridge(
            rules["seller_rating_offer_scope_v1"]
        ),
        "rating_population_self_selection_boundary_v1": bridge(
            rules["rating_population_self_selection_boundary_v1"]
        ),
        "point_shoot_recipient_usability_boundary_v1": bridge(
            rules["point_shoot_recipient_usability_boundary_v1"]
        ),
        "image_quality_lens_lag_scope_v1": bridge(
            rules["image_quality_lens_lag_scope_v1"]
        ),
        "community_phone_claim_scope_v1": bridge(
            rules["community_phone_claim_scope_v1"]
        ),
        "feedback_reconciliation_matrix_v1": bridge(
            rules["feedback_reconciliation_matrix_v1"]
        ),
        "recipient_matched_trial_v1": bridge(
            rules["recipient_matched_trial_v1"]
        ),
        "camera_feedback_decision_preparation_v1": bridge(
            rules["camera_feedback_decision_preparation_v1"]
        ),
        "evidence_bounded_compact_gift_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                rules["evidence_bounded_compact_gift_decision_v1"]
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Buy only one verified exact returnable camera if the mother can operate it and repeated matched tests show acceptable keeper, intended-output, workflow, carry and cost results with a meaningful advantage over her actual phone; otherwise improve the phone workflow, choose printing support, rerun a corrected trial or defer.",
                    "There is no universal winner between retailer raters and enthusiasts. Verify one exact camera, compare it with the mother's actual phone in her real tasks, buy only if every predeclared gate passes with a meaningful advantage, and otherwise keep or improve the phone workflow, add printing support or defer.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains five frozen seller aggregates, bounded rating and camera concepts and three substantive scoped community reports, but lacks a verified current exact unit, representative reviewer sample, recipient usability result and matched comparison with the mother's actual phone."
                    ),
                    "tradeoff_matchers": {
                        "seller_fields_are_scoped": matcher(
                            "All SKU, stock, price, aggregate rating, review count, model, old-model, bundle and accessory wording remains bound to its exact frozen page rather than a current delivered offer, independent test or representative population."
                        ),
                        "star_distribution_is_unknown": matcher(
                            "A page aggregate is not converted into a known distribution of five-star reviews, probability of quality or standardized optical score."
                        ),
                        "review_population_is_not_representative": matcher(
                            "Self-selected participating reviewers may differ from nonreviewers and do not automatically represent all buyers, enthusiasts or this mother."
                        ),
                        "reviewer_roles_are_separated": matcher(
                            "Keep retailer user satisfaction separate from professional or enthusiast evaluation and map each claim to device, scene, output, metric and threshold."
                        ),
                        "simple_operation_is_design_intent": matcher(
                            "Point-and-shoot simple operation is a category design intent and not proof that an exact old or bundled unit is easy and reliable for the recipient."
                        ),
                        "image_quality_output_is_declared": matcher(
                            "Define the intended screen or print, size, crop and subjective versus objective image-quality criterion before comparing results."
                        ),
                        "lens_aberration_is_not_exact_diagnosis": matcher(
                            "Optical aberration explains possible blur, distortion or fringing but does not diagnose a captured unit or prove every inexpensive compact lens is soft."
                        ),
                        "shutter_lag_is_tested": matcher(
                            "Measure focus, metering and trigger delay during moving-child tasks rather than assuming one fixed lag or inferring action success from a static garden frame."
                        ),
                        "community_evidence_is_scoped": matcher(
                            "The positive phone report, processing complaint and older-phone product-photo request remain author-, device-, task-, skill-, output- and time-scoped."
                        ),
                        "actual_phone_is_the_baseline": matcher(
                            "Compare the exact candidate with the mother's actual current phone rather than a generic phone, another user's iPhone or an enthusiast's high-end camera."
                        ),
                        "exact_offer_condition_is_verified": matcher(
                            "Verify current model, variant, condition, lens, battery, charger, card, cables, transfer path, warranty, return terms, shipping and delivered cost before purchase."
                        ),
                        "trial_uses_the_intended_recipient": matcher(
                            "Observe the mother operating both devices and record time to first shot, focus and timing hits, errors, transfer, charging and willingness to carry."
                        ),
                        "scenes_and_outputs_are_matched": matcher(
                            "Repeat matched static garden, backlit, indoor-person, moving-grandchild and flash or no-flash scenes with normalized framing and final display or print size and masked labels where practical."
                        ),
                        "metrics_and_gates_are_separate": matcher(
                            "Predeclare and separately mark usability, condition, timing, keeper, intended-output preference, transfer, carry, returnability and total-cost gates pass, fail or unresolved."
                        ),
                        "meaningful_advantage_or_fallback": matcher(
                            "Buy only if the verified camera passes every hard gate and gives a meaningful advantage over the actual phone; otherwise improve the phone workflow, choose printing support, rerun a corrected smaller trial or defer."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_aggregate_is_five_star_count", "B5", "A 91-percent or 100-percent aggregate proves that every listed review awarded five stars."),
        negative("wrong_frozen_price_is_delivered", "B5", "Every frozen seller price is necessarily the current delivered price for a tested working camera."),
        negative("wrong_pool_review_counts", "B5", "Reviews from different camera models, variants, bundles and pages may be pooled into one representative sample."),
        negative("wrong_hp_rating_winner", "B5", "The HP M447 is the best camera because its frozen page shows 100 percent over four reviews."),
        negative("wrong_rating_probability", "B4", "A seller aggregate is a calibrated probability that the mother will like the camera."),
        negative("wrong_self_selection_disproves_reviews", "B4", "The possibility of self-selection proves that every positive retailer review is false."),
        negative("wrong_retailers_represent_all", "B4", "The participating retailer reviewers represent all casual buyers and the intended recipient."),
        negative("wrong_enthusiasts_are_universal_authority", "B4", "Enthusiast status makes every criticism universally applicable regardless of device, scene and output."),
        negative("wrong_point_shoot_guarantees_easy", "B3", "The point-and-shoot category definition guarantees that every exact old compact is easy for this mother."),
        negative("wrong_auto_guarantees_success", "B3", "Automatic focus, exposure and flash guarantee reliable garden and grandchildren photographs."),
        negative("wrong_opinion_is_usability_test", "B3", "Asking whether the mother likes the camera without observing tasks is a complete usability test."),
        negative("wrong_quality_single_metric", "B2", "Image quality has one universal metric independent of viewing size, task and human perception."),
        negative("wrong_aberration_diagnoses_listing", "B2", "The general optical-aberration page proves that one captured seller unit has a defective soft lens."),
        negative("wrong_every_compact_lens_soft", "B2", "All inexpensive compact camera lenses are necessarily soft in every part of every image."),
        negative("wrong_lag_fixed_by_category", "B2", "Every compact has the same shutter lag and therefore the same moving-child failure rate."),
        negative("wrong_static_proves_action", "B2", "One sharp static flower image proves reliable timing and focus for moving grandchildren."),
        negative("wrong_positive_phone_universal", "B1", "One switcher's positive iPhone report proves every phone is easier and better than every compact."),
        negative("wrong_negative_phone_universal", "B1", "One user's processing complaint proves every phone produces unacceptable photographs."),
        negative("wrong_etsy_request_transfers", "B1", "An older-phone request for Etsy product photos establishes the best device for garden and grandchildren snapshots."),
        negative("wrong_market_title_is_performance_test", "B1", "A forum search title about market displacement is a controlled image-quality test of the five captured cameras."),
        negative("wrong_choose_larger_crowd", "B6", "The correct crowd is whichever side has more ratings or louder comments."),
        negative("wrong_choose_more_technical_crowd", "B6", "Technical vocabulary alone makes enthusiast claims applicable to the mother's intended outputs."),
        negative("wrong_rating_invalidates_criticism", "B6", "A high retailer aggregate makes lens, lag, condition and workflow criticism irrelevant."),
        negative("wrong_criticism_invalidates_satisfaction", "B6", "Pixel-level or action criticism proves casual snapshot satisfaction could not be genuine."),
        negative("wrong_generic_phone_comparator", "B7", "The camera may be compared with a generic modern phone instead of the mother's actual phone."),
        negative("wrong_unmatched_scenes", "B7", "Different scenes, framings, operators and output sizes provide a fair camera-versus-phone comparison."),
        negative("wrong_pixel_crop_only", "B7", "A single 100-percent crop can replace intended display or print preference, timing, keeper and workflow measurements."),
        negative("wrong_one_lucky_frame", "B7", "One lucky sharp frame is sufficient evidence of a reliable camera for grandchildren."),
        negative("wrong_expert_operates_for_recipient", "B7", "An expert operating the camera proves that the mother can operate and transfer from it."),
        negative("wrong_transfer_ignored", "B7", "Transfer, charging, carry burden and errors may be ignored if one image looks sharper."),
        negative("wrong_posthoc_thresholds", "B7", "Pass thresholds may be invented after seeing which device looked best."),
        negative("wrong_return_not_needed", "B7", "Condition, warranty and returnability do not matter for an old or bundled exact offer."),
        negative("wrong_rating_compensates_gate", "B8", "A high store rating can compensate for failed condition, usability, transfer or keeper gates."),
        negative("wrong_sharpness_compensates_gate", "B8", "Pixel-level sharpness can compensate for a failed timing, carry, workflow or total-cost gate."),
        negative("wrong_unresolved_is_pass", "B8", "An unresolved exact identity, condition, battery, accessory or return field may be treated as a pass."),
        negative("wrong_immediate_sony_winner", "D1", "The packet already proves that the Sony DSC-W80 is the unconditional best gift."),
        negative("wrong_immediate_hp_winner", "D1", "The packet already proves that the HP M447 is the unconditional best gift."),
        negative("wrong_phone_always_wins", "D1", "The mother should always use a phone because low-end compact sales declined."),
        negative("wrong_must_buy_one", "D1", "The buyer must purchase one captured listing even if no exact unit passes the recipient-matched gates."),
    ]

    g1 = ["E1", "E2", "E4", "E10", "E11", "E13", "E14", "E15", "B4", "B5"]
    g2 = ["E9", "E16", "B3"]
    g3 = ["E3", "E5", "E12", "B2"]
    g4 = ["E6", "E7", "E8", "B1", "B2", "B4", "B5", "B6"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit all five exact frozen seller pages, separate aggregate scale from review count and star distribution, and bound reviewer authorship, self-selection and transfer to the intended recipient.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G2", "description": "Separate point-and-shoot simple-operation design intent from observed recipient usability and specify the mother's camera, transfer and output tasks.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G3", "description": "Explain subjective and objective image quality, optical aberration and shutter lag as task- and output-dependent test dimensions without diagnosing an exact listing.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G4", "description": "Keep the three substantive phone reports scoped and reconcile retailer satisfaction with enthusiast criticism by device, reviewer population, task, output, metric and threshold rather than choosing a crowd.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B6"},
        {"subgoal_id": "G5", "description": "Verify one exact returnable camera and run a smallest repeated mother-operated same-scene trial against her actual phone with normalized outputs, separate usability, timing, keeper, preference and workflow metrics, and predeclared gates.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B7"},
        {"subgoal_id": "G6", "description": "Buy only a verified exact camera that passes all recipient-matched gates and provides a meaningful advantage over the actual phone, or improve the phone workflow, choose printing support, rerun or defer without a universal crowd or category winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Build an exact five-page seller table and explain the limits of aggregate ratings, review counts, reviewer authorship and self-selection.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain why point-and-shoot simple-operation intent does not establish the mother's actual usability and define her intended tasks.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Translate image-quality, lens-aberration and shutter-lag criticism into declared scene, output and measurement conditions without diagnosing an exact unit.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Scope all community reports and reconcile retailer and enthusiast feedback by population, device, task, output, metric and threshold rather than choosing a crowd.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify exact-offer verification and a smallest repeated recipient-operated matched trial against her actual phone with normalized outputs, separate metrics and predeclared stops.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a conditional buy, improve-phone, printing-support, corrected-trial or deferral decision without a universal camera, phone, retailer or enthusiast winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_cameras_photo_0054",
        "cluster_id": "budget_compact_retailer_rating_enthusiast_scope_user_fit",
        "difficulty": {
            "proof_depth": 4,
            "branching_factor": 16,
            "distractor_density": 0.39,
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
                    "star_distribution_is_unknown",
                    "review_population_is_not_representative",
                    "reviewer_roles_are_separated",
                    "simple_operation_is_design_intent",
                    "image_quality_output_is_declared",
                    "lens_aberration_is_not_exact_diagnosis",
                    "shutter_lag_is_tested",
                    "community_evidence_is_scoped",
                    "actual_phone_is_the_baseline",
                    "exact_offer_condition_is_verified",
                    "trial_uses_the_intended_recipient",
                    "scenes_and_outputs_are_matched",
                    "metrics_and_gates_are_separate",
                    "meaningful_advantage_or_fallback",
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
            "human_solve_minutes": 55,
            "minimum_required_evidence_nodes": 16,
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
