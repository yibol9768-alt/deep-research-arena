#!/usr/bin/env python3
"""Build the frozen Q30 evidence inventory from the atomic capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-smartphones-0030-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0030/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-smartphones-0030-20260716-r1"
RUN_ID = "v3-corpus-formal-smartphones-0030-20260716-r1"
TASK_ID = "dra_v3_formal_smartphones_0030"
TOPIC = "usbc_convergence_capability_boundary"


SEARCHES = [
    (
        "ultranet",
        "001-shopping-65w-two-port-pd-pps.json",
        "65 W two-port charger seller snapshot",
        "http://localhost:7770/fast-charger-with-led-by-ultranet-usb-c-charger-block-65w-2-port-gan-pps-pd-charger-foldable-and-compact-usb-wall-charger-for-macbook-pro-air-ipad-iphone-12-galaxy-and-all-usb-c-charger.html",
    ),
    (
        "alogic",
        "002-shopping-100w-four-port-allocation.json",
        "100 W four-port charger seller snapshot",
        "http://localhost:7770/alogic-100w-4-port-pd-usb-c-wall-charger-with-gan-fast-tech-2-usb-c-2-usb-a-dynamic-power-allocation-power-delivery-3-0-charger-for-macbook-m1-mac-xps-ipad-pro-iphone-galaxy-more.html",
    ),
    (
        "cable_100w",
        "003-shopping-100w-20gbps-emarker-cable.json",
        "100 W and 20 Gbit/s USB-C cable seller snapshot",
        "http://localhost:7770/usb-c-3-2-gen2x2-cable-100w-20gbps-updated-90-degree-right-angle-usb-c-to-c-3-2-cable-4kat60hz-video-cord-with-e-marker-for-thunderbolt-3-4-oculus-quest-imac-macbook-ipad-pro-dell-xps-6-6-ft.html",
    ),
    (
        "cable_60w",
        "004-shopping-60w-usb2-cable.json",
        "60 W USB 2.0 USB-C cable seller snapshot",
        "http://localhost:7770/usb-c-cable-60w-10ft-anker-powerline-iii-usb-c-to-usb-c-cable-2-0-usb-c-charger-cable-for-macbook-pro-2020-ipad-pro-2020-switch-samsung-galaxy-s20-plus-s9-s8-plus-pixel-and-more-white.html",
    ),
    (
        "iphone_charge_state",
        "005-forum-iphone-charge-rate-question.json",
        "iPhone 14 Pro Max state-dependent charging observation",
        "http://localhost:9999/f/iphone/62346/support-request-iphone-14pm-charging-speed-question",
    ),
    (
        "xsmax_debris",
        "006-forum-post-repair-cable-compatibility.json",
        "post-repair iPhone XS Max port-debris observation",
        "http://localhost:9999/f/iphone/106055/changed-my-back-glass-on-xs-max-now-only-my-20w-official",
    ),
    (
        "lightning_pins",
        "007-forum-lightning-pin-durability.json",
        "conflicting Lightning connector durability anecdotes",
        "http://localhost:9999/f/iphone/106050/cables-with-the-most-durable-lighting-pins",
    ),
    (
        "usb_history",
        "008-wiki-usb-standardization-history.json",
        "USB connector history and optional-function boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/USB",
    ),
    (
        "usb_hardware",
        "009-wiki-usb-hardware-cables-power.json",
        "USB cable and power capability boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/USB_hardware",
    ),
    (
        "usb_negotiation",
        "010-wiki-usb-communications-negotiation.json",
        "USB speed and power negotiation boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/USB_communications",
    ),
    (
        "s22_profiles",
        "011-wiki-s22-pps-charging-profiles.json",
        "Galaxy S22 family charging profiles",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Samsung_Galaxy_S22",
    ),
    (
        "gt_neo5_bundle",
        "012-wiki-oppo-proprietary-charge-bundle.json",
        "Realme GT Neo5 proprietary charging bundle",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Oppo",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "ev_ultranet_port_claims",
        "node_type": "attribute",
        "subject": "frozen ULTRANET charger listing",
        "predicate": "advertises_snapshot",
        "object": "one USB-C and one USB-A port, PD and PPS, up to 65 W on USB-C with one device, shared allocation with two devices, and an E-Mark cable condition for a MacBook claim",
        "source_url": SEARCHES[0][3],
        "search_id": "ultranet",
        "role": "product",
        "scope": "seller_claim_snapshot_single_and_dual_port_conditions",
        "quotes": [
            "ULTRANET 65W Charger Block with PPS & PD protocol, reaches a max power delivery of 65W, which can fast charge your USB C &A devices simultaneously.",
            "65W PD charger will power up your MacBook Pro 13.3” from 0% to 100% in only 2H via a USB-C to USB-C cable with E-Mark chip (Not Included, sold separately).",
            "ULTRANET PD GaN charger smartly distributes 65W of power between 2 devices when charging simultaneously to shorten charging time and minimize heat dissipation. Our USB wall charger supports high-speed charging up to 65W when a single device is connected via USB C port.",
        ],
        "accepted": "The frozen ULTRANET seller page claims PD and PPS, 65 W from its USB-C port with one device, shared allocation with two devices, and an E-Mark cable condition for one MacBook charging claim; it is not an independent test.",
    },
    {
        "evidence_id": "ev_alogic_port_claims",
        "node_type": "attribute",
        "subject": "frozen ALOGIC four-port charger listing",
        "predicate": "advertises_snapshot",
        "object": "USB-C port 1 up to 100 W alone, USB-C port 2 up to 18 W, two USB-A ports sharing 17 W, and 65 W plus 18 W plus 17 W when all outputs are active",
        "source_url": SEARCHES[1][3],
        "search_id": "alogic",
        "role": "product",
        "scope": "seller_claim_snapshot_port_specific_and_all_ports_active",
        "quotes": [
            "USB-C #1 single output: PD3.0 (5,9,15V/3A, 20V/5A) - 100W* | USB-C #2 single output: PD3.0 (5V/3A, 9V/2A) - 18W | USB-A #1 + #2 output: 5V/3.4A - 17W | *Derated when all ports active as follows: USB-C #1 65W + USB-C #2 18W, USB-A #1 + #2 17W",
            "2-meter Cable: Wall Charger comes with USB-C to USB-C 2-meter double braided cable.",
        ],
        "accepted": "The frozen ALOGIC seller page assigns different ceilings to its ports and says all-port use derates USB-C port 1 from 100 W to 65 W while USB-C port 2 remains 18 W and the USB-A pair shares 17 W.",
    },
    {
        "evidence_id": "ev_100w_cable_claims",
        "node_type": "attribute",
        "subject": "frozen ULT-WIIQ USB-C cable listing",
        "predicate": "advertises_snapshot",
        "object": "100 W power, 20 Gbit/s data, an E-Marker, and video only when the connected USB-C port supports DisplayPort Alternate Mode",
        "source_url": SEARCHES[2][3],
        "search_id": "cable_100w",
        "role": "product",
        "scope": "seller_claim_snapshot_power_data_emarker_and_video_condition",
        "quotes": [
            "supports 100W PD 20V5A, 4K@60Hz, 2K@144Hz, 2K@120Hz, 2K@60Hz, 1080P@60Hz video output and 20Gbps high speed data transfer.",
            "The video function only works for devices whose USB-C port supports DisplayPort Alternate Mode.",
            "E-Marker with Premium Material Designed with an advanced E-Marker chip in each connector for greater charging stability and clear signal transmission.",
        ],
        "accepted": "The frozen ULT-WIIQ seller page claims 100 W, 20 Gbit/s, an E-Marker, and video conditional on a USB-C port that supports DisplayPort Alternate Mode; these are not independently verified results.",
    },
    {
        "evidence_id": "ev_60w_usb2_cable_claims",
        "node_type": "attribute",
        "subject": "frozen Anker PowerLine III USB-C cable listing",
        "predicate": "advertises_snapshot",
        "object": "a 60 W charging ceiling and USB 2.0 or 480 Mbit/s data behavior despite USB-C connectors",
        "source_url": SEARCHES[3][3],
        "search_id": "cable_60w",
        "role": "product",
        "scope": "seller_claim_snapshot_60w_and_usb2_data",
        "quotes": [
            "A maximum output of 60W allows for high-speed charging to a wide range of devices including phones, tablets, and laptops.",
            "USB C to USB C 2.0 USB C to USB C 2.0 USB C to USB C 2.0 (Nylon) USB C to USB C 2.0 (Nylon) USB C 3.1 Gen 2 USB C Thunderbolt 3.0 Charging Technology 60W 100W 60W 60W 100W 100W Data Transfer 480Mbps 480Mbps 480Mbps 480Mbps 10Gbps 40Gbps",
            "PowerLine III USB-C to USB-C 2.0 Cable (10 ft)",
        ],
        "accepted": "The frozen Anker seller page claims a 60 W maximum for this USB-C cable and identifies it as USB-C to USB-C 2.0 with 480 Mbit/s data in its comparison table; connector shape alone does not supply the 20 Gbit/s claim made by the other cable page.",
    },
    {
        "evidence_id": "prop_iphone_charge_state_scope",
        "node_type": "proposition",
        "subject": "one iPhone 14 Pro Max charging thread",
        "predicate": "reports_scoped_rate_changes",
        "object": "slow progress near 75 percent with MagSafe and Lightning connected to a 30 W USB-C brick, followed by faster progress in a later trial starting at 49 percent",
        "source_url": SEARCHES[4][3],
        "search_id": "iphone_charge_state",
        "role": "community",
        "scope": "single_uncontrolled_report_magsafe_or_lightning_phone_side_not_usbc",
        "quotes": [
            "With this new iPhone 14PM, I put it on at 75% and it took a full 5 minutes to go up a single percentage. True on both MagSafe and lightning cable attached to a MacBook Air USB C 30w brick. All Apple cables and chargers. Also true regardless of optimization on or off.",
            "Did some messing around and as someone said below, it seems to throttle as it gets closer to 80. Plugged it in at 49 for 4 minutes and it jumped 7%.",
        ],
        "accepted": "One iPhone 14 Pro Max author reports one percentage point in five minutes near 75 percent with both MagSafe and a Lightning cable attached to a 30 W USB-C brick, then seven points in four minutes from 49 percent; this is an uncontrolled state-dependent observation and the phone-side cable is Lightning.",
    },
    {
        "evidence_id": "prop_xsmax_repair_debris_scope",
        "node_type": "proposition",
        "subject": "one post-repair iPhone XS Max thread",
        "predicate": "reports_confounded_compatibility_and_fix",
        "object": "several MFi cables stopped working after back-glass repair while an official 20 W combination and wireless charging worked, then small port debris removal was reported to fix the problem",
        "source_url": SEARCHES[5][3],
        "search_id": "xsmax_debris",
        "role": "community",
        "scope": "lightning_phone_post_repair_and_debris_confounding",
        "quotes": [
            "Changed my back-glass on XS Max, now only my 20w official apple charger and wireless chargers will work. Any ideas what may have caused this?",
            "I've got a bunch of MFi certified cables that just don't work now... and though it's not a massive problem, it seems quite strange to me.",
            "The triple check for debris was it! I gave it a good brushing and scraping… but I guess my pursed lips don’t do as good a job at dust and small debris eviction as a legit air compressor with an air pic just did! Thank you!!! There was barely anything in there… but it did the trick anyway.",
        ],
        "accepted": "One iPhone XS Max author reports post-repair failures with several MFi cables and continued operation with an official 20 W combination and wireless charging, then says compressed-air removal of small port debris fixed it; repair timing and debris prevent attribution to a protocol or charger.",
    },
    {
        "evidence_id": "prop_lightning_pin_anecdote_scope",
        "node_type": "proposition",
        "subject": "participants in one Lightning cable thread",
        "predicate": "report_conflicting_individual_experiences",
        "object": "one author reports Lightning pin failures as quickly as one week while another participant reports no official Apple cable failure and identifies unusually careful handling",
        "source_url": SEARCHES[6][3],
        "search_id": "lightning_pins",
        "role": "community",
        "scope": "conflicting_lightning_anecdotes_not_usb_c_lifetime_or_brand_ranking",
        "quotes": [
            "I have usb cables that are 20 years old that still work. I’ve had lighting connectors go bag in a week. The pins degrade and seem to run off or fall out or oxidize.",
            "I mean. I’ve never had an official Apple cable fail me. Get tatty? Sure. But fail me? I’ve not had that happen personally. But full disclosure I’m a very cautious user of all my tech soo I’m probably more gentle than most.",
        ],
        "accepted": "One author reports rapid Lightning connector-pin failures while another careful user reports no official Apple cable failure; these conflicting anecdotes do not establish USB-C contact life, population reliability, or a brand ranking.",
    },
    {
        "evidence_id": "prop_usb_convergence_optional_scope",
        "node_type": "proposition",
        "subject": "USB connector evolution and USB-C",
        "predicate": "standardizes_shape_without_fixing_all_capabilities",
        "object": "USB began by replacing several peripheral interfaces, Standard, Mini, and Micro forms preceded Type-C, and reversible Type-C supports many hardware-dependent optional functions",
        "source_url": SEARCHES[7][3],
        "search_id": "usb_history",
        "role": "concept",
        "scope": "general_history_and_optional_capabilities_not_one_product",
        "quotes": [
            "Introduced in 1996, USB was originally designed to standardize the connection of peripherals to computers, replacing various interfaces such as serial ports , parallel ports , game ports , and Apple Desktop Bus (ADB) ports.",
            "The Type-A and Type-B connectors came in Standard, Mini, and Micro sizes.",
            "The Type-C connector, also known as USB-C, is not exclusive to USB, is the only current standard for USB, is required for USB4, and is required by other standards, including modern DisplayPort and Thunderbolt.",
            "It is reversible and can support various functionalities and protocols, including USB; some are mandatory, and many are optional, depending on the type of hardware: host, peripheral device, or hub.",
            "USB specifications provide backward compatibility, usually resulting in decreased signaling rates, maximal power offered, and other capabilities.",
        ],
        "accepted": "USB was introduced to standardize peripheral connections; Standard, Mini, and Micro forms preceded Type-C, while reversible USB-C can carry several protocols and many hardware-dependent optional functions, so appearance does not determine capability.",
    },
    {
        "evidence_id": "prop_usb_hardware_cable_scope",
        "node_type": "proposition",
        "subject": "USB power and cable hardware",
        "predicate": "separates_power_data_and_role_capabilities",
        "object": "USB Power Delivery can reach 240 W, a standard USB-C cable is specified for 60 W and at least USB 2.0 data, Type-C peers negotiate roles, and broader USB cabling includes charge-only arrangements",
        "source_url": SEARCHES[8][3],
        "search_id": "usb_hardware",
        "role": "concept",
        "scope": "general_usb_hardware_boundaries_not_specific_combination_performance",
        "quotes": [
            "The modern specifications are called USB Power Delivery ( USB-PD ) and allow up to 240 watts .",
            "A standard USB-C cable is specified for 60 watts and at least of USB\u00a02.0 data capability.",
            "The modern standard is a cable with a Type-C plug on each end; these cables are non-directional, leaving it to the connected devices to negotiate their respective roles.",
            "Charging cables provide power connections but not data.",
        ],
        "accepted": "The USB hardware page distinguishes power, data, and role behavior: USB Power Delivery can reach 240 W, a standard USB-C cable is specified for 60 W and at least USB 2.0 data, Type-C peers negotiate roles, and USB also has charge-only cable arrangements.",
    },
    {
        "evidence_id": "prop_usb_negotiation_scope",
        "node_type": "proposition",
        "subject": "connected USB devices",
        "predicate": "identify_and_negotiate",
        "object": "parameters such as speed and power through standard protocols including USB Device Framework and USB Power Delivery",
        "source_url": SEARCHES[9][3],
        "search_id": "usb_negotiation",
        "role": "concept",
        "scope": "general_protocol_mechanism_not_fastest_mode_guarantee",
        "quotes": [
            "how they identify themselves and negotiate parameters such as speed and power with the host or other devices using standard protocols such as USB Device Framework and USB Power Delivery",
        ],
        "accepted": "The USB communications page says connected devices identify themselves and negotiate parameters such as speed and power through protocols including USB Device Framework and USB Power Delivery; negotiation does not guarantee the maximum printed on either device.",
    },
    {
        "evidence_id": "prop_s22_profile_scope",
        "node_type": "proposition",
        "subject": "Samsung Galaxy S22 family",
        "predicate": "lists_model_specific_charging_profiles",
        "object": "S22 at 25 W with PPS or 15 W without PPS, and S22+ or S22 Ultra at 45 W with PPS or 15 W without PPS",
        "source_url": SEARCHES[10][3],
        "search_id": "s22_profiles",
        "role": "concept",
        "scope": "exact_s22_family_profiles_not_other_galaxy_models",
        "quotes": [
            "Charging USB PD: S22 : 25 W (PPS), 15W (non-PPS) S22+ and S22 Ultra : 45W (PPS), 15W (non-PPS) All models: 15W wireless",
            "Connectivity USB-C 3.2",
        ],
        "accepted": "The Galaxy S22 page lists S22 at 25 W with PPS and 15 W without PPS, while S22+ and S22 Ultra are 45 W with PPS and 15 W without PPS; this is an exact family example, not a rule for other Galaxy phones.",
    },
    {
        "evidence_id": "prop_gt_neo5_bundle_scope",
        "node_type": "proposition",
        "subject": "Realme GT Neo5 240 W SuperVOOC implementation",
        "predicate": "requires_exact_proprietary_bundle",
        "object": "the bundled proprietary charger and proprietary USB-C cable to use the advertised charging rate",
        "source_url": SEARCHES[11][3],
        "search_id": "gt_neo5_bundle",
        "role": "concept",
        "scope": "exact_realme_gt_neo5_bundle_not_other_models_or_families",
        "quotes": [
            "It is implemented by Realme GT Neo5, which requires the use of bundled proprietary charger and proprietary USB-C cable to utilize the advertised charging rate.",
            "It is based on \"low voltage pulse\" charging that works in conjunction with a customized battery.",
        ],
        "accepted": "The Oppo page says the Realme GT Neo5 implementation requires its bundled proprietary charger and proprietary USB-C cable to use the advertised 240 W SuperVOOC rate; this cannot be generalized to unlisted Oppo, Realme, or OnePlus models.",
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
    search_by_id: dict[str, dict[str, str]] = {}
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for search_id, filename, subject, target_url in SEARCHES:
        path = CAPTURE / "searches" / filename
        data = path.read_bytes()
        payload = json.loads(data)
        request_id = payload["request_id"]
        source_url = (
            "http://localhost:8081/search?capture_run="
            f"{RUN_ID}&request_id={request_id}"
        )
        search_by_id[search_id] = {
            "source_url": source_url,
            "target_url": target_url,
        }
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
            "registry_id": "reg_case_spec_usbc_0030",
            "source_url": case_source,
            "source_type": "case_spec",
            "content_sha256": sha256_bytes(CASE_SPEC.read_bytes()),
            "blob_path": CASE_SPEC_REL.as_posix(),
            "in_corpus": True,
        }
    )

    for item in EVIDENCE:
        content = raw_content_by_url[item["source_url"]]
        spans = []
        for index, quote in enumerate(item["quotes"], start=1):
            count = content.count(quote)
            if count < 1:
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
        node = {
            key: item[key]
            for key in (
                "evidence_id",
                "node_type",
                "subject",
                "predicate",
                "object",
                "source_url",
            )
        }
        node.update(
            {
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
        nodes.append(node)
        edges.append(
            {
                "edge_id": f"edge_discover_{item['evidence_id']}",
                "source_id": item["evidence_id"],
                "relation": "DISCOVERABLE_FROM",
                "target_id": f"search_{item['search_id']}",
                "discovery_method": "S",
                "discovery_order": 1,
            }
        )
        if item["node_type"] == "proposition":
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
            edges.append(
                {
                    "edge_id": f"edge_assert_{item['evidence_id']}",
                    "source_id": assertion_id,
                    "relation": "ASSERTS",
                    "target_id": item["evidence_id"],
                }
            )

    deterministic_nodes = [
        (
            "mechanism_shape_capability_layers",
            "mechanism",
            "USB-C connector convergence",
            "leaves_separate",
            "protocol, charger-port profile, phone support, proprietary-bundle, cable power, cable data, alternate-mode, and device-state constraints",
            "connector_history_and_optional_functions_v1",
        ),
        (
            "mechanism_negotiated_power_path",
            "mechanism",
            "actual charging and data behavior",
            "depends_on_intersection",
            "the selected port and allocation state, negotiated protocol, exact phone profiles, cable capability, and test conditions rather than connector appearance or one printed wattage",
            "negotiated_path_v1",
        ),
        (
            "mechanism_scope_and_troubleshooting",
            "mechanism",
            "seller pages and community incidents",
            "preserve",
            "claim authority, exact phone-side connector, charge state, repair and debris confounders, model scope, and the absence of population reliability evidence",
            "community_observation_scope_v1",
        ),
        (
            "bridge_phone_combo_matrix",
            "bridge",
            "family charger consolidation",
            "requires",
            "a phone by brick by port by cable matrix with protocol, profile, allocation, current, power, data, e-marker, device-state, and measured-outcome fields",
            "compatibility_test_matrix_v1",
        ),
        (
            "bridge_conditional_trust_boundary",
            "bridge",
            "trusted charger or cable choice",
            "requires",
            "documented conditional capability plus exact-combination testing while declining a universal reliability or fastest-mode claim",
            "evidence_bounded_choice_v1",
        ),
        (
            "decision_layered_usbc_selection",
            "decision",
            "USB-C charger and cable decision",
            "selects_admissible_set",
            "explain convergence, reject appearance-based equivalence, create only a conditional per-phone matrix and test plan, and name no universally trusted product",
            "layered_usbc_decision_v1",
        ),
    ]
    for evidence_id, node_type, subject, predicate, obj, rule_id in deterministic_nodes:
        metadata = {"rule_id": rule_id, "topic_cluster": TOPIC}
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
        "mechanism_shape_capability_layers": [
            "prop_usb_convergence_optional_scope",
            "prop_usb_hardware_cable_scope",
            "ev_100w_cable_claims",
            "ev_60w_usb2_cable_claims",
        ],
        "mechanism_negotiated_power_path": [
            "prop_usb_negotiation_scope",
            "prop_usb_hardware_cable_scope",
            "ev_ultranet_port_claims",
            "ev_alogic_port_claims",
            "ev_100w_cable_claims",
            "ev_60w_usb2_cable_claims",
            "prop_s22_profile_scope",
            "prop_gt_neo5_bundle_scope",
        ],
        "mechanism_scope_and_troubleshooting": [
            "ev_ultranet_port_claims",
            "ev_alogic_port_claims",
            "ev_100w_cable_claims",
            "ev_60w_usb2_cable_claims",
            "prop_iphone_charge_state_scope",
            "prop_xsmax_repair_debris_scope",
            "prop_lightning_pin_anecdote_scope",
            "prop_s22_profile_scope",
            "prop_gt_neo5_bundle_scope",
        ],
        "bridge_phone_combo_matrix": [
            "mechanism_shape_capability_layers",
            "mechanism_negotiated_power_path",
            "ev_ultranet_port_claims",
            "ev_alogic_port_claims",
            "ev_100w_cable_claims",
            "ev_60w_usb2_cable_claims",
            "prop_usb_negotiation_scope",
            "prop_s22_profile_scope",
            "prop_gt_neo5_bundle_scope",
        ],
        "bridge_conditional_trust_boundary": [
            "mechanism_scope_and_troubleshooting",
            "ev_100w_cable_claims",
            "ev_60w_usb2_cable_claims",
            "prop_iphone_charge_state_scope",
            "prop_xsmax_repair_debris_scope",
            "prop_lightning_pin_anecdote_scope",
            "prop_usb_convergence_optional_scope",
            "prop_usb_hardware_cable_scope",
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

    for target_id in [
        "mechanism_shape_capability_layers",
        "mechanism_negotiated_power_path",
        "mechanism_scope_and_troubleshooting",
        "bridge_phone_combo_matrix",
        "bridge_conditional_trust_boundary",
    ]:
        edges.append(
            {
                "edge_id": f"edge_decision_requires_{target_id}",
                "source_id": "decision_layered_usbc_selection",
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
