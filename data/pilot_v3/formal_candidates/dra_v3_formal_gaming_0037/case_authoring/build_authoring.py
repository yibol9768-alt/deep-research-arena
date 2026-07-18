#!/usr/bin/env python3
"""Build the audited Q37 retro-mini CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "buy_only_a_verified_returnable_configuration_that_passes_the_fathers_"
    "recipient_trial_or_choose_another_matched_route_or_defer"
)
WHEN = (
    "the_frozen_corpus_distinguishes_retail_objects_and_model_specific_"
    "evidence_but_lacks_a_current_exact_offer_and_the_fathers_trial_outcome"
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


EVIDENCE = [f"E{index}" for index in range(1, 15)]
BRIDGES = [f"B{index}" for index in range(1, 6)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    rule_definitions = {
        "latency_pipeline_and_emulation_scope_v1": bridge(
            "A console emulator makes a host behave like guest hardware and an incomplete implementation can produce defects, but that generic mechanism does not quantify any current product. Display lag is a separate delay between a sent signal and the display beginning to show it and is not pixel response time. A lag claim must therefore be localized to the exact emulator and game timing, output mode, display processing, controller path, and recipient tolerance under a repeatable test."
        ),
        "model_specific_mini_contrast_v1": bridge(
            "The PlayStation Classic facts are model-specific: twenty PCSX ReARMed games, two replica original controllers without analog sticks or vibration, nine PAL games at 50 Hz rather than 60 Hz that may respond slower for NTSC-expectant players, and negative criticism of frame rate, emulation, selection, and controls. The different NES Classic has a static thirty-game licensed library, US games and 720p output at 60 Hz, limited mapper support, and broadly positive emulation reception despite short-cord and minor sound-glitch criticism. This contrast supports neither universal emulation rejection nor universal mini-console quality."
        ),
        "recipient_preference_transfer_limit_v1": bridge(
            "One shopper wants a simple preloaded device but suspects a seller of dropshipping or overpricing, one casual player values short family sessions and a conventional controller shape, and a nostalgia thread names PS1, Xbox 360, Dreamcast, SNES, and other favorites. These scoped individual preferences identify questions to ask; they do not establish the father's target games, era, controller fit, setup tolerance, or delay sensitivity."
        ),
        "retail_object_and_rating_boundary_v1": bridge(
            "The retail pages are not matched consoles: the PlayStation Classic bundle is 86.22 dollars with no posted review; the generic AV-only 620-game box is 27.99 dollars with 40 percent of 100 over twelve reviews and discloses repeated games and lower picture quality; the 59.99-dollar RetroPie listing is a Raspberry Pi microSD card with 65 percent of 100 over twelve reviews and conflicting 7,749 versus 10,000-plus game language. None shows thousands of reviews or independently proves game uniqueness, emulation, controller feel, provenance, reliability, or recipient fit."
        ),
        "matched_father_trial_v1": bridge(
            "Record exact product identity, region, complete hardware or required host, controllers, included games and versions, video output and adapters, seller, condition, warranty, return window, game provenance, and total cost. Ask the father privately for his era, games, session style, controller shape, multiplayer, setup, and display needs. During a return window compare the target game or closest matched timing-sensitive scene on the same display, game mode, and connection path, and record repeatable response, controller comfort, audiovisual behavior, startup friction, library fit, and noticed delay against predeclared thresholds; defer when matching, provenance, returnability, or a realistic trial is unavailable."
        ),
        "evidence_bounded_retro_gift_decision_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                "No universal mini-console winner and no universal emulation rejection is supported. Buy only an exact returnable configuration whose identity, contents, games, output, controller, provenance, and total cost are verified and whose same-display recipient trial clears the father's predeclared game, comfort, latency, setup, and value thresholds. Otherwise choose a different matched legal route or defer."
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Buy only a verified exact returnable configuration that matches the father's expressed games and controller preferences and repeatedly passes the same-display latency, setup, and value trial; otherwise use another matched legal route or defer.",
                    "Do not buy from the three frozen pages alone: verify a complete returnable option and let the father's predeclared recipient trial decide, choosing an alternative matched route or deferring after any failed gate.",
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The frozen corpus distinguishes three non-comparable retail objects, separates emulator and display mechanisms, contrasts exact PlayStation Classic and NES Classic implementations, and preserves individual preference scope, but it does not contain a verified current complete offer or the father's controlled recipient-trial result."
                    ),
                    "tradeoff_matchers": {
                        "retail_pages_are_not_matched_and_reviews_are_sparse": matcher(
                            "The PlayStation bundle, generic AV console, and RetroPie microSD card are different retail objects, and their frozen review evidence is none or twelve rather than thousands, so price, rating, and game count cannot be compared as matched quality measures."
                        ),
                        "lag_must_be_localized_and_measured": matcher(
                            "Emulator behavior, game timing, video output, display processing, controller path, and player tolerance are separate contributors, so perceived delay must be tested on the exact game, display, and controller rather than assumed from the word emulation."
                        ),
                        "mini_model_results_do_not_transfer": matcher(
                            "PlayStation Classic's PAL timing and negative reception remain model-specific, while NES Classic's 60 Hz and broadly positive emulation reception remain bound to that different model; neither result defines every mini console."
                        ),
                        "community_preferences_do_not_define_the_father": matcher(
                            "The three community records illustrate simplicity, controller-shape, and nostalgia questions but cannot substitute for the father's own games, era, comfort, setup tolerance, or delay sensitivity."
                        ),
                        "complete_offer_and_provenance_are_gates": matcher(
                            "A purchase requires the exact model and region, complete hardware or host, controllers, game library and versions, video adapters, seller, condition, warranty, return window, legal provenance, and total cost to be recorded and verified."
                        ),
                        "recipient_trial_controls_the_conditional_choice": matcher(
                            "The father must try the target game or closest matched scene on the same display, game mode, and connection path under a return window, with predeclared pass conditions for response, controls, setup, library fit, and value."
                        ),
                        "alternative_or_defer_after_any_failed_gate": matcher(
                            "Choose a different matched legal route or defer whenever identity, compatibility, provenance, returnability, complete cost, or the recipient trial remains unresolved or fails."
                        ),
                    },
                }
            ],
        },
    }

    decidable_claims = [
        negative("wrong_thousands_of_reviews", "B4", "The frozen store pages show thousands of glowing reviews, so popularity independently proves quality."),
        negative("wrong_rating_proves_latency", "B4", "A seller aggregate rating directly proves that the console has low input lag and durable controllers."),
        negative("wrong_playstation_title_proves_contents", "B4", "The PlayStation Classic title alone proves the exact box contents, condition, returnability, and every included game version."),
        negative("wrong_620_count_is_unique", "B4", "The generic box contains 620 unique verified games because its title gives that number."),
        negative("wrong_generic_box_has_hdmi", "B4", "The generic 620-game box works over HDMI without an adapter even though its seller page says it is AV-only."),
        negative("wrong_retropie_is_complete_console", "B4", "The RetroPie listing is a complete ready-to-play console with host, power, video cable, and controllers rather than a microSD card."),
        negative("wrong_retropie_max_count_is_verified", "B4", "The larger 10,000-plus RetroPie game count overrides the conflicting 7,749 figure and proves a unique working licensed library."),
        negative("wrong_all_emulators_lag", "B1", "All emulators necessarily add the same perceptible lag regardless of game, implementation, display, controller, or output path."),
        negative("wrong_display_lag_is_pixel_response", "B1", "Display lag and pixel response time are the same measurement and either one alone equals total controller-to-photon delay."),
        negative("wrong_ps_pal_transfers_everywhere", "B2", "PlayStation Classic's PAL timing proves that every game, region, emulator, mini console, and television responds at 50 Hz."),
        negative("wrong_nes_reception_proves_every_mini", "B2", "Positive NES Classic emulation reception proves that every mini console and every included game has perfect emulation."),
        negative("wrong_ps_controller_called_mushy", "B2", "The frozen PlayStation Classic source directly measures its controllers as mushy and quantifies their input latency."),
        negative("wrong_community_is_prevalence", "B3", "Three community posts establish what casual fathers generally want and how sensitive they are to delay."),
        negative("wrong_ps1_nostalgia_defines_father", "B3", "One author's PS1 and Spyro nostalgia proves that this father wants the same games and console."),
        negative("wrong_game_count_replaces_recipient_trial", "B5", "A large advertised game count makes asking the father and running a recipient trial unnecessary."),
        negative("wrong_one_quick_trial_proves_reliability", "B5", "One uncontrolled quick play session proves long-term controller reliability, legal game provenance, and permanent display compatibility."),
        negative("wrong_universal_playstation_winner", "D1", "PlayStation Classic is the universal best retro gift, so exact offer verification and the father's trial can be skipped."),
        negative("wrong_universal_reject_all", "D1", "Every emulation-based mini console should be rejected without checking exact implementation, games, display, controller, or recipient tolerance."),
    ]

    g1 = ["E4", "E5", "E10", "E13", "E14", "B4"]
    g2 = ["E2", "E3", "E5", "E9", "B1"]
    g3 = ["E6", "E7", "E8", "E9", "E10", "B2"]
    g4 = ["E1", "E11", "E12", "B3"]
    g5 = EVIDENCE + ["B1", "B2", "B3", "B4", "B5"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit the three retail objects, their exact sparse rating evidence, disclosures, missing host or hardware, and internal game-count conflict without converting seller marketing into independent quality.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G2", "description": "Separate general emulator defects from display lag, pixel response, controller path, exact game timing, and player tolerance, then state what an actual lag test must localize.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G3", "description": "Contrast PlayStation Classic and NES Classic implementation and reception evidence while keeping timing, controllers, libraries, and criticisms bound to each exact model.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G4", "description": "Use community records only to elicit simplicity, controller, and nostalgia questions and never as a population result or substitute for the father's preferences.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G5", "description": "Combine retail, latency, exact-model, and preference branches into a complete-offer audit and controlled same-display recipient trial with predeclared pass conditions.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G6", "description": "Make a conditional gift decision: buy only a verified exact returnable threshold-passing configuration, otherwise choose a different matched legal route or defer, with no universal winner or rejection.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"},
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Audit the PlayStation Classic bundle, generic 620-game box, and RetroPie card as different retail objects; reconcile their frozen price, rating, review, disclosure, host, and game-count evidence without treating popularity or seller marketing as independent quality.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain what emulator behavior and display lag do and do not establish, distinguish pixel response and the rest of the input-to-display path, and define how perceived lag must be localized and tested.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Compare exact PlayStation Classic and NES Classic implementations and reception, keeping regional timing, libraries, controllers, and limitations attached to the correct model and rejecting universal claims.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Keep the three community records at individual scope and use them only to identify questions about simplicity, controller shape, nostalgia, and session style that must be asked of the father.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Specify a complete exact-offer and game-provenance audit plus a return-window same-game same-display recipient trial with predeclared controller, latency, setup, library-fit, and value thresholds.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a conditional buy, alternative matched legal route, or defer decision that depends on all verified branches and the father's trial, without naming a universal mini-console winner or rejecting all emulation.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True},
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_gaming_0037",
        "cluster_id": "retro_mini_emulation_and_recipient_fit_boundary",
        "difficulty": {
            "proof_depth": 3,
            "branching_factor": 6,
            "distractor_density": 0.2,
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
                    "retail_pages_are_not_matched_and_reviews_are_sparse",
                    "lag_must_be_localized_and_measured",
                    "mini_model_results_do_not_transfer",
                    "community_preferences_do_not_define_the_father",
                    "complete_offer_and_provenance_are_gates",
                    "recipient_trial_controls_the_conditional_choice",
                    "alternative_or_defer_after_any_failed_gate",
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
            "human_solve_minutes": 45,
            "minimum_required_evidence_nodes": 14,
            "minimum_reasoning_depth": 3,
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
                "proof_steps": len(PROOF),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
