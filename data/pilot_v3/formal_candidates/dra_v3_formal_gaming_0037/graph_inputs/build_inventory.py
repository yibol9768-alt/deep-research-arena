#!/usr/bin/env python3
"""Build the frozen Q37 retro-mini evidence-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "dra-v3-formal-gaming-0037-retro-mini-evidence-boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_gaming_0037/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-gaming-0037-retro-mini-evidence-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-gaming-0037-retro-mini-evidence-boundary-20260716-r1"
TASK_ID = "dra_v3_formal_gaming_0037"
TOPIC = "retro_mini_emulation_and_recipient_fit_boundary"


SEARCHES = [
    (
        "playstation_listing",
        "001-shopping-playstation-classic-snapshot.json",
        "PlayStation Classic bundle seller snapshot",
        "http://localhost:7770/playstation-classic-console-with-20-classic-playstation-games-pre-installed-holiday-bundle-includes-final-fantasy-vii-grand-theft-auto-resident-evil-director-s-cut-and-more.html",
    ),
    (
        "generic_620_listing",
        "002-shopping-generic-620-console-snapshot.json",
        "generic 620-game plug-and-play seller snapshot",
        "http://localhost:7770/classic-retro-game-console-plug-and-play-8-bit-video-game-entertainment-system-built-in-620-games-with-2-classic-controllers.html",
    ),
    (
        "retropie_card_listing",
        "003-shopping-retropie-card-snapshot.json",
        "preloaded RetroPie microSD-card seller snapshot",
        "http://localhost:7770/retropie-gaming-console-roms-v4-7-128gb-microsd-card-preloaded-games-for-raspberry-pi-4-400-retropie-emulation-console-plug-play-fully-loaded-game-system-compatible-with-xbox-ps1-controller.html",
    ),
    (
        "console_emulator",
        "004-wiki-console-emulator-boundary.json",
        "video-game console emulator mechanism and scope",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Video_game_console_emulator",
    ),
    (
        "display_lag",
        "005-wiki-display-lag-boundary.json",
        "display-lag mechanism and pixel-response distinction",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Display_lag",
    ),
    (
        "playstation_classic",
        "006-wiki-playstation-classic-specifics.json",
        "PlayStation Classic exact implementation and reception",
        "http://localhost:8090/content/wikipedia_en_all_nopic/PlayStation_Classic",
    ),
    (
        "nes_classic",
        "007-wiki-nes-classic-specifics.json",
        "NES Classic exact implementation and reception",
        "http://localhost:8090/content/wikipedia_en_all_nopic/NES_Classic_Edition",
    ),
    (
        "preloaded_question",
        "008-forum-preloaded-retro-handheld-scope.json",
        "one preloaded-retro-device shopping question",
        "http://localhost:9999/f/gaming/83725/good-handheld-console",
    ),
    (
        "casual_controller",
        "009-forum-casual-family-controller-preference.json",
        "one casual family player's game and controller preferences",
        "http://localhost:9999/f/consoles/124582",
    ),
    (
        "ps1_nostalgia",
        "010-forum-ps1-nostalgia-scope.json",
        "one PS1 nostalgia statement and heterogeneous replies",
        "http://localhost:9999/f/gaming/83708/what-was-you-re-favourite-console",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_playstation_listing_snapshot",
        "node_type": "proposition",
        "subject": "frozen PlayStation Classic bundle seller page",
        "predicate": "shows_sparse_offer_snapshot",
        "object": "an in-stock SKU B07L7W915H listing at 86.22 dollars whose title claims twenty pre-installed games and whose body says there is no posted review",
        "source_url": SEARCHES[0][3],
        "search_id": "playstation_listing",
        "role": "product",
        "scope": "seller_snapshot_not_current_market_value_contents_emulation_quality_controller_fit_or_recipient_outcome",
        "quotes": [
            "Playstation Classic Console with 20 Classic Playstation Games Pre-Installed Holiday Bundle, Includes Final Fantasy VII, Grand Theft Auto, Resident Evil Director's Cut and More",
            "In stock SKU B07L7W915H Be the first to review this product $86.22 Qty Add to Cart Add to Wish List Add to Compare",
        ],
        "accepted": "The frozen seller page titles an in-stock PlayStation Classic holiday bundle with twenty pre-installed games and shows SKU B07L7W915H at 86.22 dollars with no posted review; this sparse seller snapshot does not prove current market value, exact contents, emulation quality, controller fit, returnability, or the father's outcome.",
    },
    {
        "evidence_id": "prop_generic_620_offer_snapshot",
        "node_type": "proposition",
        "subject": "frozen generic 620-game plug-and-play seller page",
        "predicate": "shows_offer_and_compatibility_disclosures",
        "object": "SKU B08FBWB96P at 27.99 dollars with a 40-percent-of-100 aggregate over twelve reviews, AV-only output, repeated games, lower picture quality, and two controllers",
        "source_url": SEARCHES[1][3],
        "search_id": "generic_620_listing",
        "role": "product",
        "scope": "seller_snapshot_and_disclosures_not_independent_game_quality_latency_legality_or_reliability_test",
        "quotes": [
            "In stock SKU B08FBWB96P Rating: 40 % of 100 12 Reviews Add Your Review $27.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Console Does not support HDMI. Please make sure your TV has AV ports before purchasing, otherwise, you could not play the Classic Mini Retro Game.2. Video Game Picture Quality is not as clear as today's games.3. Some Game repetitions in this System Console4. There is not Mario 2 & 3 games",
            "Package Included:1* Entertainment system console,2* Classic controllers, 1* AV cable, 1*charger, 1* game list,1* user manual.",
        ],
        "accepted": "The generic seller page shows SKU B08FBWB96P at 27.99 dollars with a 40-percent-of-100 aggregate over twelve reviews, says the box is AV-only rather than HDMI, warns that picture quality is lower and some games repeat, and lists two controllers; these are seller snapshot and disclosure facts, not an independent latency, legality, reliability, or recipient-fit test.",
    },
    {
        "evidence_id": "prop_generic_620_marketing_scope",
        "node_type": "proposition",
        "subject": "generic 620-game seller description",
        "predicate": "makes_unverified_nostalgia_and_quality_claims",
        "object": "a built-in 620-game childhood-memory pitch, third-party Infityle identity, and seller replacement or refund language within forty-five days",
        "source_url": SEARCHES[1][3],
        "search_id": "generic_620_listing",
        "role": "product",
        "scope": "seller_assertion_not_independent_quality_game_uniqueness_controller_feel_or_policy_verification",
        "quotes": [
            "【Childhood Memory】This is a Retro Tv Classic Game Console Popular in the 1980s and 1990s, Built-in 620 Video Games, No need to insert cards or download games. (Some game repetitions in this console)",
            "【Third Party Product】It is Infityle brand product, but the quality will meet your requirements. We will ALWAYS replace a faulty product or refund your purchase within 45 days, Please do not hesitate to contact us via Amazon.",
        ],
        "accepted": "The generic page markets childhood memory and 620 built-in games while admitting repetitions, identifies the item as a third-party Infityle product, and states a forty-five-day replacement or refund promise; those seller assertions do not independently establish unique games, controller feel, quality, or currently enforceable return terms.",
    },
    {
        "evidence_id": "prop_retropie_card_identity_snapshot",
        "node_type": "proposition",
        "subject": "frozen RetroPie preloaded product page",
        "predicate": "identifies_a_card_not_complete_console",
        "object": "a 128 GB microSD-card configuration for Raspberry Pi 4 or 400 at 59.99 dollars with a 65-percent-of-100 aggregate over twelve reviews",
        "source_url": SEARCHES[2][3],
        "search_id": "retropie_card_listing",
        "role": "product",
        "scope": "card_snapshot_not_complete_host_console_controllers_power_video_or_legal_game_provenance",
        "quotes": [
            "In stock SKU B08TBB1TZ8 Rating: 65 % of 100 12 Reviews Add Your Review $59.99 Size RetroPie SD Card 128GB RetroPie SD Card 64GB Qty Add to Cart Add to Wish List Add to Compare",
            "Fastoe 128GB RetroPie Preloaded Games MicroSD Card Fastoe 128GB RetroPie Preloaded Games MicroSD Card.",
            "★【Compatibility】: Compatible with all Raspberry Pi 4 models.",
        ],
        "accepted": "The RetroPie seller page identifies a Fastoe 128 GB preloaded microSD card for Raspberry Pi 4 models at 59.99 dollars with a 65-percent-of-100 aggregate over twelve reviews; it is not a complete host console and does not establish controllers, power, video output, setup, or legal game provenance.",
    },
    {
        "evidence_id": "prop_retropie_game_count_conflict",
        "node_type": "proposition",
        "subject": "RetroPie card game-count language",
        "predicate": "contains_an_unresolved_count_inconsistency",
        "object": "one description says more than fifty-five systems and 7,749 games while another says more than 10,000 games",
        "source_url": SEARCHES[2][3],
        "search_id": "retropie_card_listing",
        "role": "product",
        "scope": "seller_count_conflict_not_verified_unique_compatible_working_or_licensed_library",
        "quotes": [
            "Over 55 systems, 7749 games.",
            "★【Classic Games】: RetroPie SD card preloaded 10000+ games with preview for Raspberry Pi 4.",
        ],
        "accepted": "The same RetroPie card page says both over fifty-five systems with 7,749 games and more than 10,000 games; preserve the unresolved seller count inconsistency rather than treating either number as a verified unique, compatible, working, or licensed library.",
    },
    {
        "evidence_id": "prop_console_emulator_mechanism_scope",
        "node_type": "proposition",
        "subject": "video-game console emulation",
        "predicate": "replicates_guest_hardware_behavior_with_implementation_specific_limits",
        "object": "a host behaves like a console so its games can run, while incomplete implementations can produce defects",
        "source_url": SEARCHES[3][3],
        "search_id": "console_emulator",
        "role": "concept",
        "scope": "general_mechanism_not_latency_amount_or_quality_of_any_current_product",
        "quotes": [
            "A video game console emulator is a type of emulator that allows a computing device [ fn 1 ] to emulate a video game console 's hardware and play its games on the emulating platform.",
            "These early programs were often incomplete, only partially emulating a given system, resulting in defects .",
        ],
        "accepted": "A video-game console emulator makes a host emulate a console's hardware so its games can run, and the historical reference notes that incomplete implementations can produce defects; this general mechanism does not quantify latency or establish the quality of any current mini console.",
    },
    {
        "evidence_id": "prop_display_lag_boundary",
        "node_type": "proposition",
        "subject": "display lag",
        "predicate": "is_signal_to_visible_start_latency_distinct_from_pixel_response",
        "object": "delay from a signal being sent to a display beginning to show it, separate from the time a pixel changes brightness",
        "source_url": SEARCHES[4][3],
        "search_id": "display_lag",
        "role": "concept",
        "scope": "display_pipeline_definition_not_total_controller_to_photon_measurement_or_exact_tv_result",
        "quotes": [
            "It refers to latency , or lag between when the signal is sent to the display and when the display starts to show that signal.",
            "Display lag is not to be confused with pixel response time , which is the amount of time it takes for a pixel to change from one brightness value to another.",
        ],
        "accepted": "The display reference defines display lag as delay between a sent signal and the display beginning to show it, and distinguishes it from pixel response time; this identifies one separate pipeline contribution, not a total controller-to-photon measurement or a result for the father's television.",
    },
    {
        "evidence_id": "prop_playstation_classic_hardware_scope",
        "node_type": "proposition",
        "subject": "PlayStation Classic exact product",
        "predicate": "uses_twenty_emulated_games_and_two_original_style_controllers",
        "object": "a dedicated console with twenty games and two replica original controllers lacking analog sticks and vibration",
        "source_url": SEARCHES[5][3],
        "search_id": "playstation_classic",
        "role": "concept",
        "scope": "exact_historical_model_not_the_frozen_seller_box_contents_condition_or_father_preference",
        "quotes": [
            "The PlayStation Classic is a dedicated video game console by Sony Interactive Entertainment that emulates games originally released on its 1994 PlayStation console.",
            "Specifications The PlayStation Classic ships with two replica PlayStation controllers (the original model without the analog sticks and vibration), an HDMI cable, and a USB Micro-A to standard USB-A cable.",
            "Games The PlayStation Classic comes preloaded with 20 games, running off the open source emulator , PCSX ReARMed.",
        ],
        "accepted": "The historical PlayStation Classic reference describes a dedicated console with twenty games running through PCSX ReARMed and two replica original controllers without analog sticks or vibration; those model facts do not inspect the frozen seller unit or determine the father's controller and game preference.",
    },
    {
        "evidence_id": "prop_playstation_classic_pal_and_reception",
        "node_type": "proposition",
        "subject": "PlayStation Classic regional timing and critical reception",
        "predicate": "binds_slower_pal_versions_and_negative_reviews_to_this_model",
        "object": "nine PAL releases at 50 Hz rather than 60 Hz that may respond slower than NTSC players expect, plus criticism of lower frame rates, emulation quality, game selection, and controller limitations",
        "source_url": SEARCHES[5][3],
        "search_id": "playstation_classic",
        "role": "concept",
        "scope": "historical_model_specific_evidence_not_all_games_regions_displays_emulators_or_users",
        "quotes": [
            "Nine games use the PAL release (favored in most European countries) regardless of the console's release platform, which means they run at a slower frame rate of 50 Hz as opposed to the NTSC standard of 60 Hz (favored in North America , parts of Japan , as well as some other Asian countries ), and may respond slower than players from NTSC regions would expect.",
            "The lower frame rates during gameplay, poor emulation quality, and the user interface were also criticized.",
            "Joe Juba of Game Informer lamented on the lack of analog sticks on the controller, along with the lacking selection of titles and a barebones menu, which makes the system a good fit only for an \"extremely specific audience\".",
        ],
        "accepted": "The PlayStation Classic reference says nine games use 50 Hz PAL releases rather than 60 Hz and may respond slower than NTSC-region players expect, and records criticism of lower frame rates, emulation quality, game selection, and the non-analog controller; this evidence remains bound to that historical model, games, and region context.",
    },
    {
        "evidence_id": "prop_nes_classic_implementation_scope",
        "node_type": "proposition",
        "subject": "NES Classic exact product",
        "predicate": "uses_a_static_thirty_game_60_hz_emulated_library",
        "object": "a dedicated console with thirty built-in games, US releases at 60 Hz, 720p 60 Hz output, and an emulator with limited support for some cartridge mappers",
        "source_url": SEARCHES[6][3],
        "search_id": "nes_classic",
        "role": "concept",
        "scope": "exact_historical_model_not_current_offer_or_playstation_generic_box_or_retropie_result",
        "quotes": [
            "Originally launched on November 10, 2016, the console aesthetically is a miniature replica of the NES, and it includes a static library of 30 built-in games from the licensed NES library, supporting save states for all of them.",
            "For the NES version, all of the games are based on their US release, running at 60 Hz and using the names by which they were released in the United States.",
            "For video output, the system features an HDMI connection, which puts out 720p at 60 Hz video for all games.",
            "The emulation included limited support for some of the memory management controllers , aka mappers, used in NES cartridges to extend the ability of the console, such as for Super Mario Bros.",
        ],
        "accepted": "The NES Classic reference describes a dedicated console with a static thirty-game licensed library, US releases at 60 Hz, 720p 60 Hz output, and limited support for some cartridge mappers; these historical exact-model facts do not transfer to the PlayStation Classic, generic box, RetroPie card, or a current offer.",
    },
    {
        "evidence_id": "prop_nes_classic_reception_scope",
        "node_type": "proposition",
        "subject": "NES Classic emulation reception",
        "predicate": "records_positive_overall_reception_with_specific_limitations",
        "object": "well-received emulation quality despite short controller-cord criticism and minor sound-related emulation glitches",
        "source_url": SEARCHES[6][3],
        "search_id": "nes_classic",
        "role": "concept",
        "scope": "historical_critical_summary_not_every_unit_game_controller_or_recipient_outcome",
        "quotes": [
            "It was well-received for its emulation quality.",
            "Aside from criticism regarding the controller cord being too short as well as minor emulation glitches, especially with sound, the NES Classic Edition has been well received.",
        ],
        "accepted": "The NES Classic reference says its emulation quality was well received while preserving criticism of a short controller cord and minor sound-related emulation glitches; this historical summary is not proof about every unit, game, controller, display, or recipient.",
    },
    {
        "evidence_id": "prop_preloaded_shopper_scope",
        "node_type": "proposition",
        "subject": "one preloaded-retro-device shopper",
        "predicate": "expresses_simplicity_goal_and_seller_suspicion",
        "object": "interest in old pre-installed games without complicated setup together with a personal suspicion of dropshipping or overpricing",
        "source_url": SEARCHES[7][3],
        "search_id": "preloaded_question",
        "role": "community",
        "scope": "single_author_question_not_verified_seller_behavior_product_quality_or_father_preference",
        "quotes": [
            "After reviewing their site they are either doing dropshipping or just overpriced stuff (they have a section on thei online shop called \"tiktok best seller\").",
            "Looking for something with pre-installed games if possible (or something that's not complicated to to do) maybe something with dual screens/touchscreen for the DS games ?",
        ],
        "accepted": "One shopper wants pre-installed old games without complicated setup and suspects a different seller may be dropshipping or overpriced; this is one author's question, not verified seller behavior, product quality, or evidence of the father's preferences.",
    },
    {
        "evidence_id": "prop_casual_family_controller_scope",
        "node_type": "proposition",
        "subject": "one casual family player's preferences",
        "predicate": "values_short_social_sessions_and_conventional_controller_shape",
        "object": "short Mario Kart, Guitar Hero, and Tetris-like sessions with family or friends and a preference for a typical controller shape over Joy-Con",
        "source_url": SEARCHES[8][3],
        "search_id": "casual_controller",
        "role": "community",
        "scope": "single_author_preference_not_father_or_population_controller_fit_or_game_demand",
        "quotes": [
            "I'm really more of a Nintendo person — I like short games, things like Mario Kart, Guitar Hero, Tetris, etc. Things I can play with family and friends for a half hour here or there.",
            "However, I don't love the Switch controller; I'm partial to a more typical controller shape.",
        ],
        "accepted": "One casual player values short Mario Kart, Guitar Hero, and Tetris-like sessions with family or friends and prefers a conventional controller shape over the Joy-Con they tried; this individual preference is not evidence of the father's controller fit or game demand.",
    },
    {
        "evidence_id": "prop_ps1_nostalgia_heterogeneity_scope",
        "node_type": "proposition",
        "subject": "one favorite-console discussion",
        "predicate": "contains_personal_ps1_nostalgia_and_diverse_favorites",
        "object": "one author misses a childhood PS1 and Spyro experience while replies name Xbox 360, PS2, Dreamcast, SNES, Game Boy, Saturn, and other favorites",
        "source_url": SEARCHES[9][3],
        "search_id": "ps1_nostalgia",
        "role": "community",
        "scope": "individual_memories_and_thread_heterogeneity_not_prevalence_or_father_nostalgia_target",
        "quotes": [
            "As a child I had a Sega Megadrive (which is also an amazing console) but when I got a PS1 for Christmas and played Spyro I was hooked! This was the future lol! God I wish I could experience those days again.",
            "Xbox 360 is my personal favorite. It had all the right games and hardware",
            "Dreamcast - I've loved a lot of consoles in my days, but the Dreamcast still holds a special place.",
            "My favourite console would have to be the super Nintendo, it had so many great games...but if we include computers too id probably choose the amiga, that had some really good games too.",
        ],
        "accepted": "One author expresses childhood PS1 and Spyro nostalgia while replies name Xbox 360, PS2, Dreamcast, SNES, Game Boy, Saturn, and other favorites; the thread illustrates heterogeneous individual memories, not prevalence or the father's nostalgia target.",
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def typed_verifier(accepted: str) -> dict[str, Any]:
    return {
        "kind": "typed_claim",
        "matcher": "normalized_text",
        "accepted_phrases": [accepted],
        "normalizers": ["casefold", "whitespace", "punctuation", "hyphen"],
    }


def build() -> dict[str, Any]:
    capture_documents = json.loads(
        (CAPTURE / "documents.json").read_text(encoding="utf-8")
    )["documents"]
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        source_url = (
            "http://localhost:8081/search?capture_run="
            f"{RUN_ID}&request_id={payload['request_id']}"
        )
        documents.append(
            {
                "registry_id": f"reg_search_{search_id}",
                "source_url": source_url,
                "source_type": "search_result",
                "content_sha256": sha256_bytes(data),
                "blob_path": rel(path),
                "in_corpus": True,
            }
        )
        nodes.append(
            {
                "evidence_id": f"search_{search_id}",
                "node_type": "search_result",
                "subject": subject,
                "predicate": "returned",
                "object": [target_url],
                "source_url": source_url,
                "body_support": False,
                "search_snippet_support": True,
                "verifier": {"kind": "search_observation"},
                "metadata": {
                    "discovery_root": True,
                    "discovery_root_policy": "search_result",
                    "topic_cluster": TOPIC,
                },
            }
        )

    raw_content_by_url: dict[str, str] = {}
    for row in capture_documents:
        documents.append(
            {
                "registry_id": row["registry_id"],
                "source_url": row["source_url"],
                "source_type": row["source_type"],
                "content_sha256": row["content_sha256"],
                "blob_path": (CAPTURE_REL / row["blob_path"]).as_posix(),
                "in_corpus": True,
            }
        )
        raw_content_by_url[row["source_url"]] = (
            CAPTURE / row["blob_path"]
        ).read_text(encoding="utf-8")

    case_source = f"http://case-spec.local/{TASK_ID}"
    documents.append(
        {
            "registry_id": "reg_case_spec_retro_mini_0037",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans: list[dict[str, Any]] = []
        for index, quote in enumerate(item["quotes"], start=1):
            if quote not in content:
                raise ValueError(
                    f"quote missing from {item['evidence_id']}: {quote!r}"
                )
            spans.append(
                {
                    "support_span_id": f"span_{item['evidence_id']}_{index}",
                    "exact_quote": quote,
                    "occurrence": 0,
                    "support_type": "body",
                }
            )
        nodes.append(
            {
                "evidence_id": item["evidence_id"],
                "node_type": item["node_type"],
                "subject": item["subject"],
                "predicate": item["predicate"],
                "object": item["object"],
                "source_url": item["source_url"],
                "support_spans": spans,
                "verifier": typed_verifier(item["accepted"]),
                "metadata": {
                    "acceptable_source_roles": [item["role"]],
                    "critical": True,
                    "scope": item["scope"],
                    "topic_cluster": TOPIC,
                },
            }
        )
        assertion_id = f"assert_{item['evidence_id'].removeprefix('prop_')}"
        nodes.append(
            {
                "evidence_id": assertion_id,
                "node_type": "assertion",
                "subject": f"source for {item['subject']}",
                "predicate": "states",
                "object": item["object"],
                "source_url": item["source_url"],
                "support_spans": [
                    {
                        "support_span_id": f"span_{assertion_id}_1",
                        "exact_quote": item["quotes"][0],
                        "occurrence": 0,
                        "support_type": "body",
                    }
                ],
                "verifier": {"kind": "quoted_assertion"},
                "metadata": {"topic_cluster": TOPIC},
            }
        )
        edges.extend(
            [
                {
                    "edge_id": f"edge_assert_{item['evidence_id']}",
                    "source_id": assertion_id,
                    "relation": "ASSERTS",
                    "target_id": item["evidence_id"],
                },
                {
                    "edge_id": f"edge_discover_{item['evidence_id']}",
                    "source_id": item["evidence_id"],
                    "relation": "DISCOVERABLE_FROM",
                    "target_id": f"search_{item['search_id']}",
                    "discovery_method": "S",
                    "discovery_order": 1,
                },
            ]
        )

    deterministic_nodes = [
        (
            "bridge_retail_object_and_rating_boundary",
            "bridge",
            "three frozen retro retail pages",
            "separates_product_identity_and_evidence_scope",
            "the pages are a PlayStation Classic bundle, a generic AV console, and a Raspberry Pi microSD card with sparse rather than thousand-scale frozen review evidence",
            "retail_object_and_rating_boundary_v1",
        ),
        (
            "bridge_latency_pipeline_and_emulation_scope",
            "bridge",
            "claims of emulation lag",
            "requires_pipeline_localization_and_measurement",
            "general emulator defects and display lag identify separate possible causes but do not quantify a product without exact game, output, display, controller, and recipient testing",
            "latency_pipeline_and_emulation_scope_v1",
        ),
        (
            "bridge_model_specific_mini_contrast",
            "bridge",
            "PlayStation Classic and NES Classic evidence",
            "rejects_universal_mini_console_quality_claims",
            "model-specific 50 Hz and negative PlayStation Classic evidence contrasts with 60 Hz and broadly positive NES Classic evidence while preserving each model's limitations",
            "model_specific_mini_contrast_v1",
        ),
        (
            "bridge_recipient_preference_transfer_limit",
            "bridge",
            "community retro preferences",
            "retains_author_scope_and_requires_recipient_elicitation",
            "individual simplicity, controller-shape, and nostalgia preferences generate questions but cannot stand in for the father's priorities or sensitivity",
            "recipient_preference_transfer_limit_v1",
        ),
        (
            "bridge_matched_father_trial",
            "bridge",
            "reversible retro gift protocol",
            "requires_exact_offer_audit_and_recipient_trial",
            "verify identity, contents, library, output path, controller, provenance, total cost, and return terms before a same-game same-display father trial with predeclared pass conditions",
            "matched_father_trial_v1",
        ),
        (
            "decision_evidence_bounded_retro_gift",
            "decision",
            "retro-game gift for the father",
            "selects_only_a_verified_threshold_passing_configuration_or_defer",
            "buy only an exact returnable configuration that matches the father's games and controller preferences and clears the controlled latency, setup, and value trial; otherwise use another matched route or defer",
            "evidence_bounded_retro_gift_decision_v1",
        ),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    derives: dict[str, list[str]] = {
        "bridge_retail_object_and_rating_boundary": [
            "prop_playstation_listing_snapshot",
            "prop_generic_620_offer_snapshot",
            "prop_generic_620_marketing_scope",
            "prop_retropie_card_identity_snapshot",
            "prop_retropie_game_count_conflict",
        ],
        "bridge_latency_pipeline_and_emulation_scope": [
            "prop_console_emulator_mechanism_scope",
            "prop_display_lag_boundary",
            "prop_generic_620_offer_snapshot",
            "prop_playstation_classic_pal_and_reception",
        ],
        "bridge_model_specific_mini_contrast": [
            "prop_playstation_classic_hardware_scope",
            "prop_playstation_classic_pal_and_reception",
            "prop_playstation_listing_snapshot",
            "prop_nes_classic_implementation_scope",
            "prop_nes_classic_reception_scope",
        ],
        "bridge_recipient_preference_transfer_limit": [
            "prop_preloaded_shopper_scope",
            "prop_casual_family_controller_scope",
            "prop_ps1_nostalgia_heterogeneity_scope",
        ],
        "bridge_matched_father_trial": [
            "bridge_retail_object_and_rating_boundary",
            "bridge_latency_pipeline_and_emulation_scope",
            "bridge_model_specific_mini_contrast",
            "bridge_recipient_preference_transfer_limit",
        ],
    }
    for source_id, targets in derives.items():
        for target_id in targets:
            edges.append(
                {
                    "edge_id": f"edge_{source_id}_from_{target_id}",
                    "source_id": source_id,
                    "relation": "DERIVES_FROM",
                    "target_id": target_id,
                }
            )

    for target_id in derives:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id}",
                "source_id": "decision_evidence_bounded_retro_gift",
                "relation": "REQUIRES",
                "target_id": target_id,
            }
        )

    return {
        "schema_version": "evidence_graph_inventory_v1",
        "corpus_snapshot": SNAPSHOT,
        "documents": documents,
        "nodes": nodes,
        "edges": edges,
        "support_spans": [],
    }


def main() -> None:
    inventory = build()
    OUT.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": rel(OUT),
                "documents": len(inventory["documents"]),
                "nodes": len(inventory["nodes"]),
                "edges": len(inventory["edges"]),
                "critical_evidence": len(EVIDENCE),
                "sha256": sha256_bytes(OUT.read_bytes()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
