#!/usr/bin/env python3
"""Build the audited Q34 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "pay_the_verified_premium_only_if_a_matched_return_window_trial_"
    "repeatably_clears_the_buyers_display_threshold_without_failing_"
    "commute_constraints_otherwise_choose_the_cheaper_matched_"
    "configuration_or_defer"
)
WHEN = (
    "the_corpus_supports_price_model_mechanism_and_scope_boundaries_"
    "but_not_a_matched_current_offer_or_this_buyers_trial_outcome"
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


EVIDENCE = [f"E{index}" for index in range(1, 17)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    rule_definitions = {
        "battery_aging_evidence_boundary_v1": bridge(
            "The Nintendo Switch table gives one 4,310 mAh battery line and two duration ranges with footnote markers, but the frozen body does not bind those ranges to the exact local-shop revision or commute workload. The depth-of-discharge reference supplies two generic definitions and a generic cycle-life relationship across rechargeable technologies. These facts identify variables to verify; they do not predict exact Switch runtime, battery aging, usable years, or an OLED-versus-base advantage."
        ),
        "display_and_aging_mechanism_scope_v1": bridge(
            "AMOLED uses individually controlled light-generating pixels, its display power varies with shown color and brightness, and its generic organic-material degradation can involve color shift, image persistence, or burn-in. LCD instead requires illumination because it does not produce light, and the image-persistence reference says LCD or plasma retention is usually temporary unlike screen burn-in. These mechanisms do not rank complete Switch displays or establish Switch OLED preference, burn-in incidence, usage threshold, or years to failure."
        ),
        "exact_price_configuration_boundary_v1": bridge(
            "The 3.66 dollar OLED page and 35.67 dollar base-plus-Mario-Kart page are anomalous, non-matched frozen seller snapshots and cannot establish a screen-tier premium or value result. The model reference lists historical launch prices of 299.99 dollars for Original and 349.99 dollars for OLED, a 50-dollar launch gap rather than a current street-price quote. Verify current total price only after matching exact SKU, bundle, region, condition, storage, revision, accessories, warranty, and return terms."
        ),
        "model_tradeoff_scope_v1": bridge(
            "The captured model table lists Original or Lite at 32 GB and OLED at 64 GB, Original with a 6.2-inch 720p IPS display and OLED with a 7-inch 720p OLED display, and table weights of 297 g and 319 g. Its battery line gives two footnoted duration ranges without binding an unverified shop unit to one range. These model fields do not prove GPU performance, perceived improvement, full bag weight, real-route runtime, or a universal winner."
        ),
        "scoped_owner_experience_v1": bridge(
            "Use the direct Switch pages only as individual views: one normal-model owner values portability and does not care much about graphics, while one commenter says an unopened OLED deliberation does not justify the upgrade. Use the Steam Deck commute and battery comments only to define commute questions for a different handheld, and use OLED-TV picture-quality and conflicting burn-in histories only to show subjective and usage-specific uncertainty. None establishes prevalence or a transferable Switch result."
        ),
        "matched_commuter_trial_v1": bridge(
            "Obtain matched, returnable exact configurations and record total price, bundle, region, condition, revision, storage, accessories, warranty, and return terms. Predeclare a personal noticeability and commute threshold. Compare the same game and scene, brightness policy, color settings, session length, route lighting, seated and standing use, grip, carried setup, headphones, network mode, frame-rate policy if applicable, and starting charge. Record repeatable noticed benefit, readability, comfort, weight burden, and battery consumed. Select the cheapest exact configuration that passes without failing commute constraints, or defer if matching or trial is unavailable."
        ),
        "evidence_bounded_oled_commute_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                "No universal OLED or LCD winner is supported. Verify the claimed premium on matched exact configurations and use a reversible return-window commute trial. Pay the premium only if this buyer repeatably notices and values the screen benefit enough to clear a predeclared threshold while the full carried setup and battery behavior pass; otherwise choose the cheaper matched configuration, keep shopping, or defer when matching, terms, or trial evidence is unavailable."
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Pay the verified OLED premium only if a matched return-window commuter trial repeatably clears the buyer's predeclared display threshold without failing carried-weight, comfort, readability, or battery checks; otherwise choose the cheaper matched configuration or defer.",
                    "Verify matched exact offers, compare both units under the same commute-relevant conditions, and buy the least expensive configuration that repeatably passes the buyer's threshold; if the evidence, return terms, or trial is missing, defer."
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The frozen corpus supports anomalous seller snapshots, historical launch pricing, exact model-table fields, generic display and battery mechanisms, and scoped individual experiences, but it does not contain matched current offers or this buyer's controlled commute-trial outcome."
                    ),
                    "tradeoff_matchers": {
                        "current_premium_requires_matched_offers": matcher(
                            "The two seller pages cannot be compared as a tier premium because the prices are anomalous and the base page includes Mario Kart; current exact offers must be matched for SKU, bundle, region, condition, storage, revision, accessories, warranty, and return terms."
                        ),
                        "historical_msrp_is_not_current_price": matcher(
                            "The 299.99 and 349.99 dollar figures are historical launch prices and imply a 50-dollar launch gap, not proof of the current roughly 100-dollar shop quote."
                        ),
                        "model_fields_do_not_establish_preference_or_performance": matcher(
                            "The display, storage, table weight, and battery fields are model-bound facts but do not establish subjective value, GPU performance, a full carried load, or an exact route runtime."
                        ),
                        "generic_mechanisms_do_not_predict_product_life": matcher(
                            "AMOLED, LCD backlight, image-persistence, and depth-of-discharge references describe generic mechanisms and risks; they do not predict Switch-specific burn-in incidence, battery aging, usable years, or a winner."
                        ),
                        "community_experiences_are_scoped": matcher(
                            "Direct Switch comments remain individual opinions, while Steam Deck commute and OLED-TV picture or burn-in reports are different-device anecdotes that cannot be transferred to a Switch outcome."
                        ),
                        "trial_outcome_controls_conditional_choice": matcher(
                            "A matched return-window trial must hold game scene, brightness policy, settings, route lighting, session length, grip, carried setup, and starting charge sufficiently constant, then record repeatable noticeability, comfort, readability, weight, and battery use."
                        ),
                        "cheapest_threshold_passing_or_defer": matcher(
                            "Choose the cheapest exact configuration that repeatably clears the buyer's predeclared display and commute threshold; pay more only after that pass, and defer when matched offers, return terms, or a controlled trial are unavailable."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_compare_anomalous_seller_prices", "B3", "The 3.66 dollar OLED page and 35.67 dollar base bundle prove that the OLED tier is cheaper and therefore the better value."),
        negative("wrong_bundle_price_is_base_tier_price", "B3", "The Mario Kart bundle page is a clean base-console-only comparator, so its frozen price can be subtracted from the OLED page."),
        negative("wrong_historical_msrp_is_current_quote", "B3", "The 299.99 and 349.99 dollar historical launch prices are the current shop prices everywhere."),
        negative("wrong_user_hundred_dollar_gap_is_verified", "B3", "The source set independently verifies that the exact local OLED unit costs about 100 dollars more than the exact base unit."),
        negative("wrong_oled_label_proves_performance", "B4", "The OLED model must have faster game performance because its display technology and price tier are higher."),
        negative("wrong_table_weight_is_full_commute_load", "B4", "The table's 297 g and 319 g values are complete bag weights including controllers, case, charger, and accessories."),
        negative("wrong_duration_range_bound_to_shop_revision", "B1", "The 4.5 to 9 hour range is proven for the exact unverified shop OLED unit on this buyer's train route."),
        negative("wrong_amoled_always_uses_less_power", "B2", "AMOLED always consumes less power than LCD regardless of content, brightness, settings, or device design."),
        negative("wrong_generic_burnin_predicts_switch_failure", "B2", "The generic AMOLED degradation paragraph proves that this Switch OLED will burn in within a known number of years."),
        negative("wrong_image_persistence_is_always_permanent", "B2", "Every retained image is permanent OLED burn-in and temporary LCD image persistence does not exist."),
        negative("wrong_depth_of_discharge_predicts_years", "B1", "The generic depth-of-discharge page predicts the exact number of usable battery years for both Switch models."),
        negative("wrong_switch_comments_show_prevalence", "B5", "The two Switch comments establish what normal owners generally notice and which model most commuters prefer."),
        negative("wrong_steam_deck_commute_transfers_to_switch", "B5", "Steam Deck commute and battery comments directly establish Nintendo Switch commute runtime and superiority."),
        negative("wrong_oled_tv_experience_transfers_to_switch", "B5", "OLED television picture-quality and burn-in histories directly determine the Switch OLED's noticeability and lifespan."),
        negative("wrong_one_trial_proves_long_term", "B6", "One short comparison session proves years of screen reliability, battery aging, and permanent commute suitability."),
        negative("wrong_universal_oled_winner", "D1", "OLED is universally worth every premium for every commuter, so no exact offer verification or personal trial is needed."),
    ]

    g1 = ["E1", "E2", "E13", "B3"]
    g2 = ["E11", "E12", "E13", "E16", "B4"]
    g3 = ["E3", "E4", "E5", "E7", "E8", "B2"]
    g4 = ["E6", "E11", "B1"]
    g5 = ["E3", "E9", "E10", "E12", "E14", "E15", "B5"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Reconcile the user-reported shop premium with the two non-matched seller snapshots and historical launch pricing, then state what a valid current exact-offer comparison requires.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G2", "description": "Compare model-bound display, storage, weight, and battery fields while preserving revision and measurement boundaries and avoiding performance or commute-runtime inference.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G3", "description": "Explain the LCD and AMOLED light paths, content-dependent power, generic degradation, and temporary image-persistence distinction without predicting Switch preference or failure.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G4", "description": "Use the Switch battery table and generic depth-of-discharge material to define battery uncertainty without assigning an exact commute runtime or aging trajectory.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G5", "description": "Keep direct Switch opinions at individual scope and keep Steam Deck commute and OLED-TV preference or burn-in histories non-transferable while extracting only trial questions.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G6", "description": "Combine the price, model, mechanism, battery, and experience branches into a matched return-window commuter trial and a cheapest-threshold-passing conditional decision or defer.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Reconcile the local roughly 100-dollar quote with the two frozen seller pages and the historical launch prices, and specify how to match current exact configurations before calculating a premium.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Compare the exact display, storage, weight, and battery table fields while keeping model, revision, and measurement basis attached and avoiding unsupported performance, carried-weight, or route-runtime conclusions.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Explain the LCD and AMOLED mechanisms, content-dependent power, generic degradation, and image-persistence boundary, and state why those facts do not establish a Switch-specific preference or wear timeline.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Explain what the Switch battery table and generic depth-of-discharge material do and do not establish about commute runtime, battery aging, or usable years.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Use the two direct Switch views only as individual opinions and the Steam Deck and OLED-TV experiences only as non-transferable anecdotes, not prevalence or Switch outcomes.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a matched return-window commuter trial with a predeclared threshold and controlled conditions, then pay a verified premium only after a repeatable pass; otherwise choose the cheaper matched configuration or defer, without naming a universal winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_gaming_0034",
        "cluster_id": "gaming_oled_commute_evidence_boundary",
        "difficulty": {
            "proof_depth": 3,
            "branching_factor": 6,
            "distractor_density": 0.25,
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
                    "current_premium_requires_matched_offers",
                    "historical_msrp_is_not_current_price",
                    "model_fields_do_not_establish_preference_or_performance",
                    "generic_mechanisms_do_not_predict_product_life",
                    "community_experiences_are_scoped",
                    "trial_outcome_controls_conditional_choice",
                    "cheapest_threshold_passing_or_defer",
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
            "human_solve_minutes": 50,
            "minimum_required_evidence_nodes": 16,
            "minimum_reasoning_depth": 3,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
