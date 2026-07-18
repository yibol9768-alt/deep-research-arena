#!/usr/bin/env python3
"""Build the audited Q50 CaseSpec authoring payload."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "graph_inputs" / "case_authoring_source.json"
OUT = HERE / "authoring.json"
NORMALIZERS = ["casefold", "whitespace", "punctuation", "hyphen"]
ANSWER = (
    "choose_the_lowest_total_trip_cost_exact_snack_path_passing_current_label_"
    "safety_packaging_and_matched_route_exposure_gates_or_use_a_proven_control_"
    "or_defer"
)
WHEN = (
    "the_packet_lacks_complete_current_physical_labels_and_a_matched_"
    "instrumented_pannier_and_backpack_exposure_trial"
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


EVIDENCE = [f"E{index}" for index in range(1, 16)]
BRIDGES = [f"B{index}" for index in range(1, 7)]
PROOF = EVIDENCE + BRIDGES + ["D1"]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = source["rules"]
    rule_definitions = {
        rule_id: bridge(rules[rule_id])
        for rule_id in (
            "chocolate_phase_and_coating_boundary_v1",
            "exact_offer_heat_form_matrix_v1",
            "sugar_glass_humidity_boundary_v1",
            "transport_cooling_exposure_boundary_v1",
            "current_label_safety_route_gate_v1",
            "matched_hot_route_portability_trial_v1",
        )
    }
    rule_definitions["evidence_bounded_hot_weather_snack_choice_v1"] = {
        "type": "decision",
        "decision_matcher": matcher(
            rules["evidence_bounded_hot_weather_snack_choice_v1"]
        ),
        "conclusion_matchers": {
            ANSWER: matcher(
                "Preserve the exact seller fields and unknown labels, distinguish crystalline melting from sugar-glass and humidity failure, verify the current physical package, instrument the actual route, and choose only the lowest-total-trip-cost and carry-burden exact path that passes the matched contained trial; otherwise use a proven control or defer.",
                "Do not name a summer-proof brand from form or marketing alone. Verify identity, ingredients, allergens, storage and seals, measure the pannier and backpack exposure, test small matched contained samples with cooling separate, then select the least burdensome passing path or defer.",
            )
        },
        "admissible_conditions": [
            {
                "answer": ANSWER,
                "when": WHEN,
                "condition_matcher": matcher(
                    "The packet has four frozen seller pages, eight general concept pages and three scoped community discussions, but lacks complete current physical labels for all exact offers and a matched instrumented pannier and backpack exposure trial for the intended route, lot, weather, position, humidity, packaging and duration."
                ),
                "tradeoff_matchers": {
                    "seller_pages_do_not_measure_hot_route_survival": matcher(
                        "The four seller snapshots establish frozen price, rating, pack, mass, form and marketing fields but do not measure melting, softening, leakage, wrapper adhesion, texture or safety on the intended hot route."
                    ),
                    "ratings_do_not_measure_portability": matcher(
                        "Each displayed rating must stay paired with its review count, and neither a percentage nor the absence of reviews measures hot pannier or backpack portability."
                    ),
                    "shell_and_coating_words_do_not_set_thresholds": matcher(
                        "A colorful candy shell or chocolatey-coating phrase does not identify an exact fat system, crystal state, melting range or higher heat tolerance."
                    ),
                    "crystalline_phase_background_is_not_product_measurement": matcher(
                        "Generic melting, polymorphism and compound-chocolate pages explain possible crystalline and coating mechanisms but do not assign an exact SKU threshold, thermal history or route result."
                    ),
                    "sugar_glass_and_humidity_are_distinct_failure_paths": matcher(
                        "Hard candy can fail through material-specific glass softening, stickiness or environmental moisture uptake rather than classic crystalline melting, yet the background supplies no exact Skittles or Jolly Rancher threshold."
                    ),
                    "shelf_stable_is_not_ninety_degree_texture_or_safety": matcher(
                        "Shelf-stable describes sealed room-temperature storage achieved through product and packaging controls, not guaranteed texture, wrapper integrity or safety after uncontrolled heat or seal damage."
                    ),
                    "community_examples_do_not_transfer": matcher(
                        "The sweat-sogged candy, old large cooler and disputed salt-and-ice comments motivate controls but cannot establish performance for any captured snack, small bag or route."
                    ),
                    "current_label_and_seal_gate_is_unresolved": matcher(
                        "Physical identity, ingredients, allergens, filling, storage instructions, lot, net quantity, seal and wrapper integrity, delivered cost and intended serving must be verified before testing or recommending an exact item."
                    ),
                    "route_exposure_requires_instrumentation": matcher(
                        "A roughly 90-degree ambient statement is not an internal exposure measurement; pannier and backpack temperature, humidity, sun, shade, duration, position and handling must be logged."
                    ),
                    "cooling_is_a_separate_factor_and_burden": matcher(
                        "Insulation or an ice pack must be tested as a separate predeclared factor while recording start temperature, added mass, condensation and reusable-pack burden instead of attributing the effect to brand."
                    ),
                    "matched_contained_trial_is_local": matcher(
                        "Small identified-lot samples in identical leakproof secondary containment must be matched on start temperature, bag position, route, duration and handling with predeclared leak, wrapper, shape, texture, consumption, waste and clean-up criteria; results remain local to tested conditions."
                    ),
                    "lowest_trip_cost_passing_control_or_defer": matcher(
                        "Choose only the lowest-total-trip-cost and carry-burden exact path clearing label, safety, packaging, mess, texture, waste and matched-exposure gates; otherwise use an already proven route-and-lot control or defer without a universal brand verdict."
                    ),
                },
            }
        ],
    }

    negative_rows = [
        ("wrong_shell_is_heatproof", "B1", "The colorful shell proves that the captured M&M'S remains intact and safe in every 90-degree bag."),
        ("wrong_chocolatey_means_compound", "B1", "The word chocolatey proves that the exact Charleston Chew coating is compound chocolate with a known vegetable-fat formula."),
        ("wrong_compound_always_hotter", "B1", "Every compound coating has a higher melting point and better hot-route performance than every true chocolate."),
        ("wrong_generic_cocoa_butter_threshold", "B1", "A generic cocoa-butter table is the exact melting threshold of the captured M&M'S and Charleston Chew products."),
        ("wrong_polymorph_identified", "B1", "The general polymorphism article identifies the crystal form and tempering history of both captured coated candies."),
        ("wrong_rating_proves_portability", "B2", "The 85-percent Jolly Rancher rating proves better hot-weather portability than the 73-percent M&M'S rating."),
        ("wrong_no_review_means_failure", "B2", "The absence of a posted Skittles or Charleston Chew review proves those products fail in heat."),
        ("wrong_skittles_mass_resolved", "B2", "The Skittles one-ounce product-dimensions field proves the total edible mass of all ninety packets."),
        ("wrong_frozen_copy_is_route_result", "B2", "Charleston Chew's frequently-enjoyed-frozen copy is a controlled hot-pannier performance test."),
        ("wrong_hard_candy_cannot_soften", "B3", "Hard candy cannot soften, stick, take up water or adhere to a wrapper under any summer condition."),
        ("wrong_glass_transition_is_one_point", "B3", "Every amorphous candy has one universal glass-transition temperature that can be copied directly to both exact fruit candies."),
        ("wrong_hygroscopy_proves_exact_failure", "B3", "The hygroscopy definition proves that these exact Skittles and Jolly Rancher lots fail at a specific humidity."),
        ("wrong_crystalline_melting_only_failure", "B3", "If a candy does not undergo crystalline melting, it cannot become sticky or unusable in a hot humid pack."),
        ("wrong_sweat_anecdote_identifies_product", "B3", "The workout story identifies one of the captured candies and proves its wrapper always becomes soggy."),
        ("wrong_old_cooler_transfers", "B4", "A decades-old full-size Igloo cooler proves a small bicycle pannier with an ice pack will hold every snack cold for the intended trip."),
        ("wrong_salt_ice_field_proven", "B4", "The salt-and-ice thread contains a timed field experiment proving that salt makes a cooler stay cold longer on this route."),
        ("wrong_ice_pack_amount_universal", "B4", "One fixed ice-pack mass is sufficient regardless of contents, starting temperature, insulation, ambient temperature or direct sun."),
        ("wrong_ambient_equals_bag", "B4", "A 90-degree weather forecast is the exact internal temperature and humidity history of both bag positions."),
        ("wrong_shelf_stable_is_heatproof", "B5", "Shelf-stable means the exact product is texture-stable and safe after any uncontrolled 90-degree exposure or broken seal."),
        ("wrong_missing_label_can_be_inferred", "B5", "Missing ingredients, allergens, filling and storage instructions may be inferred from the brand name and candy form."),
        ("wrong_trial_before_label_gate", "B5", "The commuter may test an item before resolving its physical label, allergens, storage directions, filling and seal integrity."),
        ("wrong_uncontained_trial", "B6", "Loose samples may be placed directly in different bag locations and any resulting mess attributed only to product identity."),
        ("wrong_cooling_mixed_with_brand", "B6", "One brand may receive an ice pack while another stays uncooled and the difference may still be called a brand effect."),
        ("wrong_one_route_is_universal", "B6", "One successful lot on one route proves the brand is universally summer-proof across weather, bags, positions and durations."),
        ("wrong_choose_cheapest_before_gates", "D1", "The lowest sticker price should be selected before verifying the current label, seal, delivered total and matched exposure result."),
        ("wrong_brand_winner", "D1", "The selected path is therefore the universally safest and most heat-resistant sweet brand."),
        ("wrong_food_safety_from_texture", "D1", "Shape retention and acceptable texture alone establish universal food safety after hot exposure."),
        ("wrong_force_choice", "D1", "A recommendation must name one of the four products even when every exact path has unresolved safety or exposure cells."),
    ]
    decidable_claims = [negative(*row) for row in negative_rows]

    g1 = ["E1", "E8", "E10", "E14", "B2"]
    g2 = ["E1", "E2", "E3", "E9", "E10", "B1"]
    g3 = ["E4", "E5", "E6", "E8", "E14", "E15", "B3"]
    g4 = ["E7", "E9", "E11", "E12", "E15", "B4"]
    g5 = EVIDENCE + BRIDGES
    g6 = PROOF
    group_specs = [
        (
            "G1",
            "Audit the four exact seller snapshots, preserve price, rating denominator, pack, mass, form and packaging ambiguity, and state why none is a hot-route measurement.",
            g1,
            "B2",
        ),
        (
            "G2",
            "Explain crystalline melting, polymorphism and compound coating while refusing to assign an exact SKU fat identity, crystal form, threshold or heat advantage.",
            g2,
            "B1",
        ),
        (
            "G3",
            "Explain hard-candy formulation, glass transition and humidity uptake as distinct possible failure paths without turning them or the sweat anecdote into an exact-product threshold.",
            g3,
            "B3",
        ),
        (
            "G4",
            "Separate route exposure, passive containment and active cooling, and keep the sweat, old-cooler and salt-and-ice discussions at their exact anecdotal scope.",
            g4,
            "B4",
        ),
        (
            "G5",
            "Combine all branches into a current physical-label and seal gate, instrumented pannier and backpack profiles, and a small matched leakproof trial with cooling separate and predeclared outcomes.",
            g5,
            "B6",
        ),
        (
            "G6",
            "Choose only the lowest-total-trip-cost and carry-burden exact path that clears every gate, otherwise use a proven route-and-lot control or defer without universal heat, safety or brand claims.",
            g6,
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
        "Audit all four exact offers and preserve each frozen price, rating and review count, pack, mass, form, wrapper or coating claim and unresolved physical-label field while separating seller assertions from measured hot-route performance.",
        "Explain melting point, crystal polymorphism and compound coating only as general mechanisms and do not infer an exact product fat system, crystal history, melting range or heat superiority.",
        "Explain hard candy, glass transition and hygroscopy as separate material mechanisms and do not assign an exact fruit-candy threshold or treat non-melting as proof against softening, sticking or moisture damage.",
        "Keep the sweat-covered candy, old cooler and salt-and-ice discussions at their author, container, scale and condition scope, and use them only to motivate measurement, containment and cooling controls.",
        "Verify the current physical identity, ingredients, allergens, filling, storage directions, lot, net quantity and seals, measure actual pannier and backpack exposure, and specify a small matched leakproof route trial with cooling separate and predeclared mess, texture, consumption, waste and burden outcomes.",
        "Select only the lowest-total-trip-cost and carry-burden exact path passing every current-label, safety, packaging and matched-exposure gate; otherwise use a proven route-and-lot control or defer without a universal brand or food-safety verdict.",
    ]
    groups = [g1, g2, g3, g4, g5, g6]
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

    payload = {
        "schema": "dra_v3_case_authoring_v1",
        "task_id": "dra_v3_formal_snacks_chocolate_0050",
        "cluster_id": "hot_weather_sweet_snack_portability_boundary",
        "difficulty": {
            "proof_depth": 4,
            "branching_factor": 6,
            "distractor_density": 0.4,
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
                    "seller_pages_do_not_measure_hot_route_survival",
                    "ratings_do_not_measure_portability",
                    "shell_and_coating_words_do_not_set_thresholds",
                    "crystalline_phase_background_is_not_product_measurement",
                    "sugar_glass_and_humidity_are_distinct_failure_paths",
                    "shelf_stable_is_not_ninety_degree_texture_or_safety",
                    "community_examples_do_not_transfer",
                    "current_label_and_seal_gate_is_unresolved",
                    "route_exposure_requires_instrumentation",
                    "cooling_is_a_separate_factor_and_burden",
                    "matched_contained_trial_is_local",
                    "lowest_trip_cost_passing_control_or_defer",
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
            "minimum_required_evidence_nodes": 15,
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
