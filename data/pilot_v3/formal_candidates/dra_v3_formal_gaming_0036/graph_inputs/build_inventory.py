#!/usr/bin/env python3
"""Build the frozen Q36 seventh-generation family-console inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "dra-v3-formal-gaming-0036-used-console-survivorship-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0036/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-gaming-0036-used-console-survivorship-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-gaming-0036-used-console-survivorship-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_gaming_0036"
TOPIC = "seventh_generation_family_couch_survivorship_boundary"


SEARCHES = [
    ("xbox_360_e", "001-shopping-xbox-360-e-renewed.json", "exact Xbox 360 E renewed seller snapshot", "http://localhost:7770/microsoft-xbox-360-e-250gb-console-renewed.html"),
    ("ps3_160gb", "002-shopping-ps3-160gb-renewed.json", "exact PlayStation 3 renewed seller snapshot", "http://localhost:7770/sony-playstation-3-160gb-system-renewed.html"),
    ("xbox_controller", "003-shopping-xbox-360-controller-renewed.json", "Xbox 360 controller renewed seller snapshot", "http://localhost:7770/xbox-360-wireless-controller-black-by-microsoft-renewed.html"),
    ("ps3_controller", "004-shopping-ps3-dualshock3-metallic-grey.json", "PlayStation 3 DualShock 3 seller snapshot", "http://localhost:7770/playstation-3-dualshock-3-wireless-controller-metallic-grey.html"),
    ("wii_remote", "005-shopping-wii-remote-renewed.json", "Wii Remote renewed seller snapshot", "http://localhost:7770/nintendo-wii-remote-controller-black-renewed.html"),
    ("wii_bundle", "006-shopping-wii-power-av-sensor-bundle.json", "Wii power video and sensor-bar seller snapshot", "http://localhost:7770/3-in-1-wii-ac-power-adapter-composite-audio-video-cable-and-wired-motion-sensor-bar-compatible-with-nintendo-wii.html"),
    ("seventh_generation", "007-wiki-seventh-generation-console-comparison.json", "seventh-generation platform comparison", "http://localhost:8090/content/wikipedia_en_all_nopic/Seventh_generation_of_video_game_consoles"),
    ("xbox_failures", "008-wiki-xbox-360-technical-problems.json", "revision-sensitive Xbox 360 failure history", "http://localhost:8090/content/wikipedia_en_all_nopic/Xbox_360_technical_problems"),
    ("wii_remote_concept", "009-wiki-wii-remote-safety-and-attachments.json", "Wii Remote interface attachment and safety history", "http://localhost:8090/content/wikipedia_en_all_nopic/Wii_Remote"),
    ("ps3_accessories", "010-wiki-playstation-3-accessories.json", "PlayStation 3 controller and accessory boundaries", "http://localhost:8090/content/wikipedia_en_all_nopic/PlayStation_3_accessories"),
    ("retro_replacement", "011-forum-retro-controller-replacement-concern.json", "one retro-controller replacement-supply question", "http://localhost:9999/f/consoles/59836/are-there-any-brand-new-ps1-controllers-out-there-oem-or"),
    ("two_children", "012-forum-console-for-two-five-year-olds.json", "one two-child two-player console question", "http://localhost:9999/f/consoles/59842/which-console-for-5-year-olds"),
    ("just_dance", "013-forum-cheap-second-hand-just-dance.json", "one second-hand Just Dance family question", "http://localhost:9999/f/consoles/17998/cheap-console-for-just-dance"),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_xbox_360_e_offer_scope",
        "subject": "frozen Xbox 360 E renewed seller page",
        "predicate": "asserts_exact_offer_and_inclusions",
        "object": "SKU B07S5YN1H9 at 249.99 dollars with seller claims about renewed inspection, 250 GB, one controller, Wi-Fi, AV cable, power supply, and a replacement-or-refund guarantee",
        "source_url": SEARCHES[0][3], "search_id": "xbox_360_e", "role": "product",
        "scope": "seller_assertions_not_observed_exact_unit_condition_or_market_value",
        "quotes": [
            "Microsoft XBOX 360 E 250GB Console (Renewed)",
            "In stock SKU B07S5YN1H9 Be the first to review this product $249.99 Qty Add to Cart Add to Wish List Add to Compare",
            "250 GB hard drive 1 Black Wireless Controller Built in Wi-Fi AV cable and power supply",
        ],
        "accepted": "The frozen Xbox 360 E seller page is SKU B07S5YN1H9 at 249.99 dollars and claims renewed inspection, a 250 GB drive, one black wireless controller, built-in Wi-Fi, an AV cable, a power supply, and replacement-or-refund eligibility; these are seller-page assertions, not an observed test of the exact unit, serial, drive, ports, controller, sustained load, authenticity, or matched market value.",
    },
    {
        "evidence_id": "prop_ps3_160gb_offer_scope",
        "subject": "frozen PlayStation 3 160 GB renewed seller page",
        "predicate": "asserts_exact_offer_and_platform_features",
        "object": "SKU B07D9VTVXM at 247.99 dollars with seller claims for 160 GB, Wi-Fi, and a Blu-ray player but no listed controller or exact refurbishment test",
        "source_url": SEARCHES[1][3], "search_id": "ps3_160gb", "role": "product",
        "scope": "seller_assertions_not_controller_inclusion_or_observed_exact_unit_condition",
        "quotes": [
            "Sony Playstation 3 160GB System (Renewed)",
            "In stock SKU B07D9VTVXM Be the first to review this product $247.99 Qty Add to Cart Add to Wish List Add to Compare",
            "With the PlayStation 3 160GB system, you get free PlayStation Network membership, built-in Wi-Fi and 160GB of hard disk drive storage for games, music, videos and photos.",
        ],
        "accepted": "The frozen PlayStation 3 page is SKU B07D9VTVXM at 247.99 dollars and its seller copy describes 160 GB storage, Wi-Fi, and a Blu-ray player; the page does not list a controller, define an exact-unit refurbishment test, supply observed drive or port results, authenticate the exact unit, or establish matched market value.",
    },
    {
        "evidence_id": "prop_xbox_360_controller_offer_scope",
        "subject": "frozen Xbox 360 wireless-controller renewed seller page",
        "predicate": "asserts_controller_offer_refurbishment_and_power_fields",
        "object": "SKU B07FTWMTCK at 47.99 dollars with seller claims for certified refurbishment, a minimum 90-day warranty, four-controller support, and two AA batteries required",
        "source_url": SEARCHES[2][3], "search_id": "xbox_controller", "role": "product",
        "scope": "seller_claims_not_observed_authenticity_condition_or_durability",
        "quotes": [
            "Xbox 360 Wireless Controller Black by Microsoft (Renewed)",
            "In stock SKU B07FTWMTCK Be the first to review this product $47.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Use up to four controllers simultaneously on one console,Requires 2 AA Batteries",
        ],
        "accepted": "The frozen Xbox 360 controller page is SKU B07FTWMTCK at 47.99 dollars and seller copy claims certified refurbishment, a minimum 90-day warranty, up to four simultaneous controllers, and two required AA batteries; it does not independently establish authenticity, exact stick, button, pairing, battery-contact, or sustained-use condition, title-specific compatibility, or durability.",
    },
    {
        "evidence_id": "prop_ps3_controller_offer_scope",
        "subject": "frozen PlayStation 3 DualShock 3 seller page",
        "predicate": "asserts_controller_offer_features_and_aggregate",
        "object": "SKU B00BWBTJOE at 57.31 dollars with a 60-percent-of-100 aggregate over twelve reviews and seller claims for Bluetooth, USB charging, Sixaxis, vibration, and an included lithium-ion battery",
        "source_url": SEARCHES[3][3], "search_id": "ps3_controller", "role": "product",
        "scope": "seller_claims_and_aggregate_not_exact_battery_health_or_durability",
        "quotes": [
            "PlayStation 3 DualShock 3 wireless controller - Metallic Grey",
            "In stock SKU B00BWBTJOE Rating: 60 % of 100 12 Reviews Add Your Review $57.31 Qty Add to Cart Add to Wish List Add to Compare",
            "DUALSHOCK 3 utilizes Bluetooth technology for wireless game play and the controller's USB cable to seamlessly and automatically charge the controller through the PlayStation 3 at anytime.",
        ],
        "accepted": "The frozen DualShock 3 page is SKU B00BWBTJOE at 57.31 dollars with a 60-percent-of-100 aggregate over twelve reviews and seller claims for Bluetooth, USB charging, Sixaxis, vibration, and an included lithium-ion battery; the page and aggregate do not prove exact battery health, stick and button condition, pairing, authenticity, title-specific compatibility, or durability.",
    },
    {
        "evidence_id": "prop_wii_remote_offer_scope",
        "subject": "frozen black Wii Remote renewed seller page",
        "predicate": "asserts_remote_offer_and_packaging_fields",
        "object": "SKU B087412R9J at 43.99 dollars with seller claims about renewed inspection, an original standard remote, bulk packaging, no batteries, and a replacement-or-refund guarantee",
        "source_url": SEARCHES[4][3], "search_id": "wii_remote", "role": "product",
        "scope": "seller_claims_not_observed_authenticity_strap_motionplus_or_condition",
        "quotes": [
            "Nintendo Wii Remote Controller - Black (Renewed)",
            "In stock SKU B087412R9J Be the first to review this product $43.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Original Standard Nintendo Wii Controller - Black Bulk Packaging - Does Not Include Retail Packaging Does not include batteries",
        ],
        "accepted": "The frozen Wii Remote page is SKU B087412R9J at 43.99 dollars and seller copy claims renewed inspection, an original standard black remote in bulk packaging, no included batteries, and replacement-or-refund eligibility; it does not independently verify authenticity, exact button, motion, speaker, pairing, battery-contact, strap, jacket, MotionPlus, Nunchuk, or durability condition.",
    },
    {
        "evidence_id": "prop_wii_accessory_bundle_offer_scope",
        "subject": "frozen Wii power video and sensor-bar bundle seller page",
        "predicate": "asserts_accessory_bundle_offer",
        "object": "SKU B07YJQWYB9 at 19.98 dollars with a 57-percent-of-100 aggregate over twelve reviews and seller claims for an AC adapter, composite AV cable, and wired sensor bar",
        "source_url": SEARCHES[5][3], "search_id": "wii_bundle", "role": "product",
        "scope": "seller_claims_not_observed_safety_signal_quality_or_exact_console_fit",
        "quotes": [
            "3 in 1 Wii AC Power Adapter + Composite Audio Video Cable and Wired Motion Sensor Bar Compatible with Nintendo Wii",
            "In stock SKU B07YJQWYB9 Rating: 57 % of 100 12 Reviews Add Your Review $19.98 Qty Add to Cart Add to Wish List Add to Compare",
            "What You Wii Get - 1 x AC Power Adapter for Wii; 1 x AV Cord for for Wii; 1 x Wired Sensor Bar for Wii.",
        ],
        "accepted": "The frozen Wii accessory bundle is SKU B07YJQWYB9 at 19.98 dollars with a 57-percent-of-100 aggregate over twelve reviews and seller claims for an AC adapter, composite AV cable, and wired sensor bar; this does not independently verify electrical safety, signal quality, exact-console fit, cable condition, longevity, or a complete Wii setup.",
    },
    {
        "evidence_id": "prop_seventh_generation_platform_scope",
        "subject": "seventh-generation Xbox 360 PlayStation 3 and Wii platform history",
        "predicate": "distinguishes_platform_emphases_and_revision_boundaries",
        "object": "contemporaneous platforms with HD, Blu-ray, and motion-control emphases plus model-dependent compatibility and production histories",
        "source_url": SEARCHES[6][3], "search_id": "seventh_generation", "role": "concept",
        "scope": "platform_history_not_exact_unit_survival_or_complete_local_multiplayer_catalog",
        "quotes": [
            "The seventh generation of home video game consoles began on November 22, 2005, with the release of Microsoft 's Xbox 360 home console.",
            "This was followed by the release of Sony 's PlayStation 3 on November 17, 2006, and Nintendo 's Wii on November 19, 2006.",
            "Each new console introduced new technologies.",
        ],
        "accepted": "The captured seventh-generation page places Xbox 360, PlayStation 3, and Wii in the same generation and describes different HD, Blu-ray, and motion-control emphases plus revision-dependent platform histories; those platform facts do not test a surviving exact unit, compare current used-unit condition, or enumerate every target game's local-player and peripheral requirements.",
    },
    {
        "evidence_id": "prop_xbox_360_revision_failure_scope",
        "subject": "historical Xbox 360 family failures",
        "predicate": "vary_by_failure_mode_and_hardware_revision",
        "object": "conflicting family estimates, early red-ring and disc problems, later design improvements, and disc scratching that persisted in S and E models",
        "source_url": SEARCHES[7][3], "search_id": "xbox_failures", "role": "concept",
        "scope": "historical_family_evidence_not_exact_e_unit_probability_or_cross_platform_rank",
        "quotes": [
            "There were many conflicting estimates of the console's unusually high failure rate .",
            "The crisis was ultimately abated from 2009 by design revisions to the later-produced Xbox models; the S model in particular was far more resilient.",
            "Unlike the Red Ring issues, the disc scratching was not resolved by hardware revisions and was present in the S and E models.",
        ],
        "accepted": "The Xbox 360 technical-problems page reports conflicting historical family failure estimates, says later design revisions and the S model improved resilience, and says disc scratching persisted in S and E models; this makes exact revision and failure-mode inspection necessary but does not give the exact frozen E unit's survival probability or a comparable Xbox 360-versus-PS3-versus-Wii ranking.",
    },
    {
        "evidence_id": "prop_wii_remote_interface_safety_scope",
        "subject": "Wii Remote interface attachment and safety history",
        "predicate": "requires_motion_attachments_and_scoped_safety_checks",
        "object": "motion sensing, Nunchuk and other attachments, counterfeit build-quality concerns, wrist-strap warnings, and revised straps",
        "source_url": SEARCHES[8][3], "search_id": "wii_remote_concept", "role": "concept",
        "scope": "interface_and_safety_history_not_exact_remote_condition_or_child_fit",
        "quotes": [
            "An essential capability of the Wii Remote is its motion sensing capability, which allows the user to interact with and manipulate items on screen via motion sensing, gesture recognition , and pointing using an accelerometer and optical sensor technology.",
            "The attachment bundled with the Wii console is the Nunchuk , which complements the Wii Remote by providing functions similar to those in gamepad controllers.",
            "The Wii Remote has a wrist strap attached to the bottom to prevent it from flying away during game action if not held securely.",
        ],
        "accepted": "The Wii Remote page describes motion sensing, the Nunchuk and other attachments, counterfeit build-quality concerns, wrist-strap warnings, and revised straps; it defines attachment and safety checks but does not verify the frozen remote's authenticity, exact condition, MotionPlus or Nunchuk inclusion, strap state, child fit, or durability.",
    },
    {
        "evidence_id": "prop_ps3_controller_interface_scope",
        "subject": "PlayStation 3 controller and accessory interfaces",
        "predicate": "have_feature_and_input_compatibility_boundaries",
        "object": "DualShock 3 wireless mini-USB charging, Sixaxis and vibration plus generic USB controllers that may lack required inputs",
        "source_url": SEARCHES[9][3], "search_id": "ps3_accessories", "role": "concept",
        "scope": "interface_history_not_exact_controller_battery_condition_or_title_compatibility",
        "quotes": [
            "Like the Sixaxis, it is a wireless controller with a mini-USB port on the rear that is used for charging, as well as playing while charging.",
            "A limitation of this is that not all such controllers provide the same range of inputs as a Sixaxis/DualShock 3 controller (fewer buttons or joysticks for example), so may not be practical in all games.",
        ],
        "accepted": "The PlayStation 3 accessories page describes DualShock 3 wireless operation, rear mini-USB charging while playing, Sixaxis and vibration, and warns that generic USB controllers may lack required inputs; it does not verify the frozen controller's battery, pairing, sticks, buttons, authenticity, exact-game compatibility, or durability.",
    },
    {
        "evidence_id": "prop_retro_controller_replacement_question_scope",
        "subject": "one retro-controller replacement-supply question",
        "predicate": "asks_about_future_new_oem_supply",
        "object": "what happens if retro console controllers break and whether new controllers will always be made",
        "source_url": SEARCHES[10][3], "search_id": "retro_replacement", "role": "community",
        "scope": "individual_question_not_breakage_rate_supply_finding_or_platform_outcome",
        "quotes": ["I’m a console and PC player. But I prefer using a controller too a keyboard and mouse too play my games and was wondering would they’re always be new video game controllers made ? For each new Console generation? And what happens if all the retro console controllers break ? 4"],
        "accepted": "One community author asks whether new controllers will continue to be made and what happens if retro controllers break; the post identifies a replacement-supply concern but supplies no breakage rate, inventory finding, exact controller result, or Xbox 360, PlayStation 3, or Wii durability comparison.",
    },
    {
        "evidence_id": "prop_two_child_local_play_question_scope",
        "subject": "one two-child console question",
        "predicate": "states_age_and_two_player_constraint",
        "object": "two five-to-six-year-old children require two-player games",
        "source_url": SEARCHES[11][3], "search_id": "two_children", "role": "community",
        "scope": "individual_requirements_not_tested_catalog_safety_or_platform_result",
        "quotes": ["I have not owned a console since Super Nintendo was the big thing which is quite a few years ago. Which of the consoles is the most suitable for young 5-6-year-old kids (2x girls)? So it would require 2 player games. View Poll 33"],
        "accepted": "One community author asks which console suits two five-to-six-year-old children and explicitly requires two-player games; this supplies a family scenario and local-play requirement, not a tested game catalog, child-safety result, hardware failure rate, or platform recommendation.",
    },
    {
        "evidence_id": "prop_second_hand_just_dance_question_scope",
        "subject": "one second-hand Just Dance family question",
        "predicate": "states_budget_motion_game_and_child_constraints",
        "object": "a low-cost second-hand setup for a six-year-old to play Just Dance with Wii Sports as a bonus and no DVD need",
        "source_url": SEARCHES[12][3], "search_id": "just_dance", "role": "community",
        "scope": "individual_requirements_not_offer_game_version_accessory_or_durability_result",
        "quotes": ["Hi everone Im looking for advice on a budget solution as I would like to buy my 6y daughter a console to play Just Dance for xmas. It doesnt have to be the 2022 edition and I would like to buy a second-hand console to keep cost low (and realistic for us). I'm not a console guy but it would be a bonus if you suggestion could support a game like Wii sports, which was the hottest thing last time I touched a console :-) We dont own any DVDs so thats it not a requirement. Thanks for any advice you may have. 14"],
        "accepted": "One community author seeks a low-cost second-hand console for a six-year-old to play Just Dance, mentions Wii Sports as a bonus, and says DVD playback is unnecessary; the post supplies scenario constraints but no exact offer, game edition, controller set, safety test, hardware inspection, or durability outcome.",
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def typed_verifier(accepted: str) -> dict[str, Any]:
    return {"kind": "typed_claim", "matcher": "normalized_text", "accepted_phrases": [accepted], "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"]}


def build() -> dict[str, Any]:
    capture_documents = json.loads((CAPTURE / "documents.json").read_text(encoding="utf-8"))["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = f"http://localhost:8081/search?capture_run={RUN_ID}&request_id={payload['request_id']}"
        documents.append({"registry_id": f"reg_search_{search_id}", "source_url": source_url, "source_type": "search_result", "content_sha256": sha256_bytes(data), "blob_path": rel(path), "in_corpus": True})
        nodes.append({"evidence_id": f"search_{search_id}", "node_type": "search_result", "subject": subject, "predicate": "returned", "object": [target_url], "source_url": source_url, "body_support": False, "search_snippet_support": True, "verifier": {"kind": "search_observation"}, "metadata": {"discovery_root": True, "discovery_root_policy": "search_result", "topic_cluster": TOPIC}})

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append({"registry_id": row["registry_id"], "source_url": row["source_url"], "source_type": row["source_type"], "content_sha256": row["content_sha256"], "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(), "in_corpus": True})
        raw_content_by_url[row["source_url"]] = (CAPTURE / row["blob_path"]).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append({"registry_id": "reg_case_spec_family_console_0036", "source_url": case_source, "source_type": "case_spec", "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()), "blob_path": CASE_SPEC_REL.as_posix(), "in_corpus": True})

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(f"quote missing from {item['evidence_id']}: {quote!r}")
            spans.append({"support_span_id": f"span_{item['evidence_id']}_{index}", "exact_quote": quote, "occurrence": 0, "support_type": "body"})
        nodes.append({"evidence_id": item["evidence_id"], "node_type": "proposition", "subject": item["subject"], "predicate": item["predicate"], "object": item["object"], "source_url": item["source_url"], "support_spans": spans, "verifier": typed_verifier(item["accepted"]), "metadata": {"acceptable_source_roles": [item["role"]], "critical": True, "scope": item["scope"], "topic_cluster": TOPIC}})
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append({"evidence_id": assertion_id, "node_type": "assertion", "subject": f"source for {item['subject']}", "predicate": "states", "object": item["object"], "source_url": item["source_url"], "support_spans": [{"support_span_id": f"span_{assertion_id}_1", "exact_quote": item["quotes"][0], "occurrence": 0, "support_type": "body"}], "verifier": {"kind": "quoted_assertion"}, "metadata": {"topic_cluster": TOPIC}})
        edges.extend([
            {"edge_id": f"edge_assert_{item['evidence_id']}", "source_id": assertion_id, "relation": "ASSERTS", "target_id": item["evidence_id"]},
            {"edge_id": f"edge_discover_{item['evidence_id']}", "source_id": item["evidence_id"], "relation": "DISCOVERABLE_FROM", "target_id": f"search_{item['search_id']}", "discovery_method": "S", "discovery_order": 1},
        ])

    deterministic_nodes = [
        ("bridge_exact_offer_revision_condition", "bridge", "used-console exact offers", "requires_exact_offer_revision_and_condition_audit", "keep seller claims separate from observed exact-unit condition, complete contents, protections, and matched market value, including the absence of a Wii console offer", "exact_offer_revision_condition_boundary_v1"),
        ("bridge_revision_sensitive_failure_evidence", "bridge", "platform longevity comparison", "requires_revision_and_failure_mode_scope", "use historical Xbox 360 failures to define exact revision and failure-mode checks without assigning an exact E-unit probability or unsupported cross-platform rank", "revision_sensitive_failure_evidence_boundary_v1"),
        ("bridge_controller_accessory_total_cost", "bridge", "two-child input and accessory setup", "requires_complete_controller_and_accessory_cost", "treat controller and bundle pages as seller assertions and total two working title-appropriate input setups plus power video sensing battery charging and safety items", "controller_accessory_total_cost_boundary_v1"),
        ("bridge_platform_interface_and_safety", "bridge", "platform controller and couch-play fit", "requires_interface_attachment_game_and_safety_verification", "map exact-game input requirements, controller interfaces, charging, attachments, straps, counterfeit risk, and child-safe use without inferring durability", "platform_interface_and_safety_scope_v1"),
        ("bridge_scoped_family_and_replacement_questions", "bridge", "community family and replacement evidence", "retains_author_question_and_scenario_scope", "use three posts only to define replacement supply, two-child local play, budget and motion-game questions, never as rates, catalogs, inspections, or platform outcomes", "scoped_family_and_replacement_questions_v1"),
        ("bridge_matched_family_couch_trial", "bridge", "reversible used-console selection protocol", "requires_matched_exact_unit_and_two_child_trial", "inspect matched returnable exact units, complete game and accessory matrices, and run repeated two-child couch-play and safety tests or defer", "matched_family_couch_trial_v1"),
        ("decision_evidence_bounded_family_console_choice", "decision", "used Xbox 360 PlayStation 3 or Wii for two children", "selects_cheapest_admissible_exact_configuration", "choose only the cheapest exact setup that passes unit controller accessory game safety protection and couch-play gates, with no universal longevity winner and deferral for unresolved or failed gates", "evidence_bounded_family_console_choice_v1"),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append({"evidence_id": evidence_id, "node_type": node_type, "subject": subject, "predicate": predicate, "object": obj, "source_url": case_source, "verifier": {"kind": "deterministic_rule"}, "metadata": metadata})

    derives = {
        "bridge_exact_offer_revision_condition": ["prop_xbox_360_e_offer_scope", "prop_ps3_160gb_offer_scope", "prop_wii_accessory_bundle_offer_scope"],
        "bridge_revision_sensitive_failure_evidence": ["prop_seventh_generation_platform_scope", "prop_xbox_360_revision_failure_scope", "prop_xbox_360_e_offer_scope"],
        "bridge_controller_accessory_total_cost": ["prop_xbox_360_controller_offer_scope", "prop_ps3_controller_offer_scope", "prop_wii_remote_offer_scope", "prop_wii_accessory_bundle_offer_scope"],
        "bridge_platform_interface_and_safety": ["prop_seventh_generation_platform_scope", "prop_wii_remote_interface_safety_scope", "prop_ps3_controller_interface_scope", "prop_xbox_360_controller_offer_scope", "prop_ps3_controller_offer_scope", "prop_wii_remote_offer_scope"],
        "bridge_scoped_family_and_replacement_questions": ["prop_retro_controller_replacement_question_scope", "prop_two_child_local_play_question_scope", "prop_second_hand_just_dance_question_scope", "prop_seventh_generation_platform_scope"],
        "bridge_matched_family_couch_trial": ["bridge_exact_offer_revision_condition", "bridge_revision_sensitive_failure_evidence", "bridge_controller_accessory_total_cost", "bridge_platform_interface_and_safety", "bridge_scoped_family_and_replacement_questions"],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append({"edge_id": f"edge_{source_id}_from_{target_id}", "source_id": source_id, "relation": "DERIVES_FROM", "target_id": target_id})
    for target_id in derives:
        edges.append({"edge_id": f"edge_decision_requires_{target_id}", "source_id": "decision_evidence_bounded_family_console_choice", "relation": "REQUIRES", "target_id": target_id})

    return {"schema_version": "evidence_graph_inventory_v1", "corpus_snapshot": SNAPSHOT, "documents": documents, "nodes": nodes, "edges": edges, "support_spans": []}


def main() -> None:
    inventory = build()
    OUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": rel(OUT), "documents": len(inventory["documents"]), "nodes": len(inventory["nodes"]), "edges": len(inventory["edges"]), "critical_evidence": len(EVIDENCE), "sha256": sha256_bytes(OUT.read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
