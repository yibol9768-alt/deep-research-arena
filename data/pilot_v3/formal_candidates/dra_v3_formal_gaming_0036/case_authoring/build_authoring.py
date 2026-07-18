#!/usr/bin/env python3
"""Build the audited Q36 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = "choose_the_cheapest_exact_configuration_that_passes_every_unit_controller_game_accessory_safety_protection_and_budget_gate_or_defer"
WHEN = "the_packet_lacks_an_inspected_matched_exact_unit_complete_two_controller_game_and_accessory_matrix_and_completed_two_child_trial"


def matcher(*phrases: str) -> dict[str, object]:
    return {"matcher": "normalized_text", "accepted_phrases": list(phrases), "normalizers": NORMALIZERS}


def bridge(phrase: str) -> dict[str, object]:
    return {"type": "bridge", **matcher(phrase)}


def negative(claim_id: str, slot_id: str, phrase: str) -> dict[str, object]:
    return {"claim_id": claim_id, "contradicts_slot_id": slot_id, "critical": True, "rejected_matcher": matcher(phrase)}


EVIDENCE = [f"E{index}" for index in range(1, 14)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    rule_definitions = {
        "controller_accessory_total_cost_boundary_v1": bridge(
            "Keep the three controller and one Wii accessory pages at seller-assertion scope. The Xbox 360 controller page is SKU B07FTWMTCK at 47.99 dollars and claims certified refurbishment, a minimum 90-day warranty, up to four controllers, and two AA batteries. The DualShock 3 page is SKU B00BWBTJOE at 57.31 dollars with a 60-percent-of-100 aggregate over twelve reviews and claims Bluetooth, USB charging, Sixaxis, vibration, and an included lithium-ion battery. The Wii Remote page is SKU B087412R9J at 43.99 dollars and claims renewed inspection, bulk packaging, and no batteries. The Wii bundle is SKU B07YJQWYB9 at 19.98 dollars with a 57-percent-of-100 aggregate over twelve reviews and claims an AC adapter, composite cable, and wired sensor bar. None independently proves exact-item authenticity, battery health, sticks, buttons, pairing, attachments, cable condition, game compatibility, or durability. Total cost requires two working title-appropriate input setups plus every power, video, sensing, battery, charging, safety, and replacement item."
        ),
        "exact_offer_revision_condition_boundary_v1": bridge(
            "Treat the Xbox 360 E and PlayStation 3 pages as exact frozen seller snapshots. The Xbox page is SKU B07S5YN1H9 at 249.99 dollars and claims renewed inspection, 250 GB, one controller, Wi-Fi, an AV cable, a power supply, and replacement-or-refund eligibility. The PlayStation 3 page is SKU B07D9VTVXM at 247.99 dollars and claims 160 GB, Wi-Fi, and a Blu-ray player but does not list a controller or exact refurbishment procedure. These claims do not substitute for observed serial, revision, drive, storage, port, controller, sustained-load, or authenticity checks and do not establish matched market value. The packet has no Wii console offer. Obtain matched current exact-unit offers with contents, protections, condition evidence, inspection, and total cost before comparing."
        ),
        "platform_interface_and_safety_scope_v1": bridge(
            "Use the seventh-generation page only for platform and revision context, not exact-unit survival or a complete local-multiplayer catalog. The PlayStation 3 accessories page establishes DualShock 3 wireless mini-USB charging, Sixaxis and vibration, and warns that generic USB controllers may lack required inputs. The Wii Remote page establishes motion sensing, Nunchuk and other attachment roles, counterfeit build-quality concerns, wrist-strap warnings, and revised straps. These define interface, attachment, charging, title-compatibility, and child-safety cells to verify; they do not establish exact controller condition, battery health, child fit, or years to failure."
        ),
        "revision_sensitive_failure_evidence_boundary_v1": bridge(
            "The Xbox 360 technical-problems page reports conflicting historical family failure estimates, early red-ring and disc problems, later design revisions, lower reported Jasper failure in one period, and improved S-model resilience. It also says disc scratching persisted in S and E models and warns against moving a powered console. This history makes exact revision and failure-mode inspection necessary, but it does not give the frozen Xbox 360 E unit's survival probability. Because the packet contains no comparable revision-matched population study for the exact PlayStation 3 and Wii paths, those historical figures cannot rank all three platforms or surviving used units."
        ),
        "scoped_family_and_replacement_questions_v1": bridge(
            "Keep each community page at author and scenario scope. One asks whether new controllers will continue to be made and what happens if retro controllers break; it is a replacement-supply question, not a breakage rate or inventory finding. One asks which console suits two five-to-six-year-old children and explicitly requires two-player games; it is not a tested catalog or platform result. One seeks a low-cost second-hand Just Dance setup for a six-year-old, mentions Wii Sports as a bonus, and does not need DVDs; it is not an exact offer, controller, safety, or durability result. Together the posts define questions to investigate but cannot select a platform or predict survival."
        ),
        "matched_family_couch_trial_v1": bridge(
            "For every current returnable exact unit, record seller, serial and hardware revision, region, storage, refurbishment evidence, included console and accessories, warranty, return deadline, and total cost after two known-good title-appropriate controllers or remotes, batteries or charging, Nunchuks or MotionPlus when required, straps and jackets, sensor bar, power and video adapters, target games, and replacement risk. Verify every disc's platform, region, edition, condition, required peripherals, local simultaneous-player count, save or account dependency, and offline or online mode. During the return window inspect the unit, cold and warm boot, sustained play, disc reading and ejection without moving the console, storage, ports, video, audio, power stability, both inputs' sticks, buttons, triggers, motion and pairing, child-safe strap and play-space use, and repeated two-child sessions. Reject or defer on any material unresolved field or failed critical task."
        ),
        "evidence_bounded_family_console_choice_v1": {
            "type": "decision",
            "decision_matcher": matcher(
                "No universal Xbox 360, PlayStation 3, or Wii longevity winner is supported. Keep seller snapshots separate from inspected condition and total cost, revision-sensitive Xbox 360 history separate from the exact E unit and unsupported cross-platform ranks, controller concepts separate from current controller condition, and community questions separate from outcomes. Choose only the cheapest matched exact setup whose unit, two complete controllers, required accessories, target two-player games, child-safety setup, seller protections, and repeated couch-play trial pass every predeclared gate; otherwise defer."
            ),
            "conclusion_matchers": {
                ANSWER: matcher(
                    "Choose the cheapest matched exact Xbox 360, PlayStation 3, or Wii configuration that passes verified unit condition, two complete controllers, required accessories, the children's exact two-player games, child-safety setup, seller protections, total budget, and a return-window couch-play trial; otherwise defer, with no universal longevity winner.",
                    "Defer while the exact unit, Wii offer, two-controller setup, game matrix, safety setup, total cost, or family trial remains unresolved, then select only the least costly exact configuration that clears every predeclared gate."
                )
            },
            "admissible_conditions": [
                {
                    "answer": ANSWER,
                    "when": WHEN,
                    "condition_matcher": matcher(
                        "The packet contains two console seller snapshots, controller and Wii accessory pages, platform and revision-sensitive history, and three scoped community questions, but no inspected matched exact unit, matched Wii console offer, complete two-controller and game matrix, or completed two-child return-window trial."
                    ),
                    "tradeoff_matchers": {
                        "seller_assertions_are_not_exact_unit_tests": matcher(
                            "Seller titles, renewed statements, descriptions, prices, and review aggregates are frozen assertions, not independent exact-unit condition, authenticity, refurbishment-quality, controller, drive, port, sustained-load, or market-value tests."
                        ),
                        "revision_history_is_not_cross_platform_rank": matcher(
                            "Revision-sensitive Xbox 360 failure history identifies inspection targets but cannot assign the frozen E unit a survival probability or rank it against unmatched PlayStation 3 and Wii evidence."
                        ),
                        "controller_descriptions_do_not_establish_longevity": matcher(
                            "Controller interface, charging, battery, attachment, price, warranty, and rating fields do not establish exact battery health, sticks, buttons, pairing, authenticity, child fit, game compatibility, or years to failure."
                        ),
                        "community_questions_are_scoped": matcher(
                            "The replacement, two-child, and second-hand Just Dance posts define user questions and constraints but are not rates, catalogs, inspections, exact offers, or platform outcomes."
                        ),
                        "total_cost_requires_two_complete_setups": matcher(
                            "Current total cost must include a matched exact console, two known-good game-appropriate input setups, required batteries or charging, attachments, straps, sensing, power and video items, target games, protections, and replacement risk."
                        ),
                        "exact_games_and_local_modes_must_be_verified": matcher(
                            "Every old disc must be checked for platform, region, edition, condition, required peripheral, local simultaneous-player count, and account or network dependency before it can support the family use case."
                        ),
                        "trial_reduces_uncertainty_without_guaranteeing_future_life": matcher(
                            "A repeated return-window exact-unit and two-child couch-play trial can verify current fit under tested conditions but cannot guarantee future hardware, controller, disc-drive, accessory-supply, or service survival."
                        ),
                        "cheapest_passing_or_defer": matcher(
                            "Choose only the cheapest exact configuration that passes every predeclared unit, controller, game, accessory, safety, protection, and budget gate, and defer whenever a material cell remains unresolved or fails."
                        )
                    }
                }
            ]
        }
    }

    decidable_claims = [
        negative("wrong_renewed_title_proves_durable_unit", "B2", "A Renewed title proves that the exact console is authentic, fully inspected, durable, and ready for years of child use."),
        negative("wrong_frozen_price_is_matched_market_value", "B2", "The frozen 249.99-dollar Xbox 360 E and 247.99-dollar PS3 prices are matched current market values and can be compared without checking contents or protections."),
        negative("wrong_xbox_listing_one_controller_is_two_child_setup", "B2", "The Xbox 360 E listing's one claimed controller is already a complete two-child couch setup."),
        negative("wrong_ps3_listing_includes_controller", "B2", "The PlayStation 3 seller page proves that a working DualShock 3 and charging cable are included with the console."),
        negative("wrong_invent_wii_console_offer", "B2", "The Wii Remote and accessory pages establish a complete Wii console offer and price even though no Wii console page is present."),
        negative("wrong_family_rate_applies_to_exact_e", "B4", "A historical Xbox 360 family failure estimate is the exact failure probability of the frozen Xbox 360 E unit."),
        negative("wrong_xbox_rate_ranks_all_three", "B4", "The Xbox 360 technical-problems page proves that PS3 or Wii has better surviving used hardware across every revision."),
        negative("wrong_e_revision_fixed_disc_scratching", "B4", "Because Xbox 360 E is a later revision, disc scratching and every other historical drive issue were eliminated."),
        negative("wrong_review_aggregate_ranks_controller_life", "B1", "The PlayStation 3 controller's 60-percent aggregate and Wii bundle's 57-percent aggregate rank controller and platform longevity."),
        negative("wrong_xbox_controller_page_proves_exact_condition", "B1", "The Xbox controller's renewed description and minimum warranty prove the exact stick, button, battery-contact, and pairing condition."),
        negative("wrong_dualshock_battery_is_healthy", "B1", "An included lithium-ion battery claim proves that the exact DualShock 3 battery still has healthy capacity."),
        negative("wrong_wii_remote_original_claim_proves_authenticity", "B1", "The seller phrase Original Standard Nintendo Wii Controller independently authenticates the exact remote."),
        negative("wrong_wii_bundle_claim_proves_safety", "B1", "The Wii accessory seller description proves electrical safety, signal quality, cable longevity, and complete exact-console fit."),
        negative("wrong_generic_usb_controller_all_games", "B3", "Any generic USB controller supplies every Sixaxis, analog, motion, and title-specific input required by every PS3 game."),
        negative("wrong_wii_remote_needs_no_strap_or_attachment", "B3", "Every Wii game for the children can be played safely with a bare remote and no strap, jacket, Nunchuk, MotionPlus, sensor, or play-space check."),
        negative("wrong_replacement_question_proves_shortage", "B5", "One author's question proves that all OEM retro controllers are unavailable and every used controller will soon break."),
        negative("wrong_two_child_question_selects_platform", "B5", "The two-child community question proves which platform has the best complete local-multiplayer catalog and safest hardware."),
        negative("wrong_just_dance_post_proves_wii_winner", "B5", "The second-hand Just Dance question proves that Wii is the cheapest, most durable, and complete choice for this family."),
        negative("wrong_short_trial_guarantees_future_longevity", "B6", "One short successful session guarantees years of console, disc-drive, controller, accessory, and service life."),
        negative("wrong_universal_platform_longevity_winner", "D1", "Xbox 360, PlayStation 3, or Wii is a universal hardware and controller longevity winner, so exact-unit inspection, game verification, and a return-window trial are unnecessary.")
    ]

    g1 = ["E1", "E8", "E12", "B2"]
    g2 = ["E6", "E12", "E13", "B4"]
    g3 = ["E3", "E8", "E10", "E11", "B1"]
    g4 = ["E2", "E3", "E6", "E9", "E10", "E11", "B3"]
    g5 = ["E4", "E5", "E6", "E7", "B5"]
    g6 = PROOF
    subgoals = [
        {"subgoal_id": "G1", "description": "Audit the two exact console seller snapshots, preserve their seller-assertion scope and missing fields, state that the packet has no Wii console offer, and define a matched exact-unit condition, contents, protection, and total-cost comparison.", "critical": True, "requires": g1, "local_conclusion_slot_id": "B2"},
        {"subgoal_id": "G2", "description": "Use the seventh-generation and Xbox 360 technical history to identify revision-specific failure modes while explaining why historical family estimates neither predict the exact E unit nor rank unmatched PS3 and Wii candidates.", "critical": True, "requires": g2, "local_conclusion_slot_id": "B4"},
        {"subgoal_id": "G3", "description": "Audit Xbox 360, DualShock 3, and Wii Remote seller claims plus the Wii accessory bundle, then construct the cost and verification requirements for two complete game-appropriate input setups.", "critical": True, "requires": g3, "local_conclusion_slot_id": "B1"},
        {"subgoal_id": "G4", "description": "Map platform, controller, charging, attachment, title-compatibility, motion, strap, counterfeit, and child-safety boundaries without inferring current condition or durability from concept pages.", "critical": True, "requires": g4, "local_conclusion_slot_id": "B3"},
        {"subgoal_id": "G5", "description": "Keep the replacement-controller, two-child, and second-hand Just Dance posts at individual question and scenario scope while extracting only the supply, local-play, budget, motion-game, and disc requirements to verify.", "critical": True, "requires": g5, "local_conclusion_slot_id": "B5"},
        {"subgoal_id": "G6", "description": "Combine all branches into a matched exact-unit, two-controller, game, accessory, safety, total-cost, and repeated two-child couch-play protocol, then choose the cheapest passing exact setup or defer without a universal longevity winner.", "critical": True, "requires": g6, "local_conclusion_slot_id": "D1"}
    ]
    requirements = [
        {"requirement_id": "Q1", "text": "Audit the exact Xbox 360 E and PlayStation 3 seller snapshots, identify the absent Wii console offer, and specify the matched exact-unit revision, condition, contents, protection, and total-cost evidence still needed.", "slot_ids": g1, "subgoal_ids": ["G1"], "required": True},
        {"requirement_id": "Q2", "text": "Explain the revision-sensitive Xbox 360 failure evidence and its limits, including why it cannot predict the exact E unit or support an unmatched Xbox 360, PS3, and Wii longevity ranking.", "slot_ids": g2, "subgoal_ids": ["G2"], "required": True},
        {"requirement_id": "Q3", "text": "Audit the three controller and Wii accessory seller pages, separate claimed features and prices from observed condition and durability, and calculate the requirements for two complete game-appropriate input setups.", "slot_ids": g3, "subgoal_ids": ["G3"], "required": True},
        {"requirement_id": "Q4", "text": "Map controller interfaces, charging, attachments, motion, straps, counterfeit risk, title-specific inputs, and child-safety checks without turning generic platform history into exact-item condition or lifespan.", "slot_ids": g4, "subgoal_ids": ["G4"], "required": True},
        {"requirement_id": "Q5", "text": "Use the three community pages only as scoped replacement-supply, two-child local-play, budget, Just Dance, and Wii Sports questions, not as rates, catalogs, inspections, or outcomes.", "slot_ids": g5, "subgoal_ids": ["G5"], "required": True},
        {"requirement_id": "Q6", "text": "Give a matched return-window inspection and repeated two-child couch-play protocol covering exact units, both inputs, discs, accessories, safety, protections, and total cost, then select only the cheapest exact setup that passes every gate or defer without naming a universal winner.", "slot_ids": g6, "subgoal_ids": ["G6"], "required": True}
    ]

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_gaming_0036",
        "cluster_id": "seventh_generation_family_couch_survivorship_boundary",
        "difficulty": {"proof_depth": 3, "branching_factor": 6, "distractor_density": 0.3, "contradiction_count": 0},
        "rule_definitions": rule_definitions,
        "decidable_claims": decidable_claims,
        "research_subgoals": subgoals,
        "query_requirements": requirements,
        "acceptable_conclusions": [{"answer": ANSWER, "when": WHEN, "required_tradeoffs": [
            "seller_assertions_are_not_exact_unit_tests",
            "revision_history_is_not_cross_platform_rank",
            "controller_descriptions_do_not_establish_longevity",
            "community_questions_are_scoped",
            "total_cost_requires_two_complete_setups",
            "exact_games_and_local_modes_must_be_verified",
            "trial_reduces_uncertainty_without_guaranteeing_future_life",
            "cheapest_passing_or_defer"
        ]}],
        "oracle": {
            "proof": PROOF,
            "single_page_sufficient": False,
            "critical_node_ablation": {evidence_id: {"outcome": "decision_unresolved"} for evidence_id in EVIDENCE},
            "human_solve_minutes": 45,
            "minimum_required_evidence_nodes": 13,
            "minimum_reasoning_depth": 3
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rules": len(rule_definitions), "decidable_claims": len(decidable_claims), "subgoals": len(subgoals)}, sort_keys=True))


if __name__ == "__main__":
    main()
