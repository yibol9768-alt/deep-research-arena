#!/usr/bin/env python3
"""Build the frozen Q33 long-life-phone evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-smartphones-0033-long-life-2031-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_smartphones_0033/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = "dra-v3-formal-smartphones-0033-long-life-2031-20260716-r1"
RUN_ID = "v3-corpus-formal-smartphones-0033-long-life-2031-20260716-r1"
TASK_ID = "dra_v3_formal_smartphones_0033"
TOPIC = "smartphone_2031_service_repair_policy_boundary"


SEARCHES = [
    (
        "pixel_4a",
        "001-shopping-pixel-4a-5g-renewed.json",
        "renewed Pixel 4a with 5G seller snapshot",
        "http://localhost:7770/google-pixel-4a-with-5g-6-2-128gb-6gb-ram-unlocked-cellular-just-black-renewed.html",
    ),
    (
        "nord_n10",
        "002-shopping-oneplus-nord-n10-renewed.json",
        "renewed OnePlus Nord N10 seller snapshot",
        "http://localhost:7770/oneplus-nord-n10-5g-6gb-ram-128gb-90hz-display-t-mobile-sprint-unlocked-be2028-64mp-quad-camera-smartphone-black-renewed.html",
    ),
    (
        "blackview_bl5000",
        "003-shopping-blackview-bl5000-rugged.json",
        "Blackview BL5000 rugged-phone seller snapshot",
        "http://localhost:7770/rugged-smartphone-blackview-bl5000-5g-phones-unlocked-dual-sim-smartphone-with-6-5-fhd-display-8gb-128gb-big-storage-4980-mah-massive-battery-30w-fast-charging-face-detection-smartphone-tmobile.html",
    ),
    (
        "iphone_x_battery",
        "004-shopping-iphone-x-battery-kit.json",
        "iPhone X aftermarket battery-kit seller snapshot",
        "http://localhost:7770/battery-for-iphone-x-deji-3060-high-capacity-upgraded-replacement-battery-compatible-with-iphone-x-with-professional-repair-tools-kit-and-instructions.html",
    ),
    (
        "a13_case",
        "005-shopping-a13-case-port-cover.json",
        "Galaxy A13 5G case and port-cover seller snapshot",
        "http://localhost:7770/dahkoiz-for-samsung-galaxy-a13-5g-case-with-glass-screen-protector-and-dust-proof-port-cover-work-with-magnetic-car-mount-full-body-protection-silicone-rubber-phone-case-teal.html",
    ),
    (
        "iphone_6s_long_use",
        "006-forum-iphone-6s-since-2016.json",
        "iPhone 6s kept since 2016 anecdote",
        "http://localhost:9999/f/iphone/41094/do-i-really-need-a-new-iphone-when-still-i-love-my-6s",
    ),
    (
        "iphone_7_five_years",
        "007-forum-iphone-7-five-years-microphone.json",
        "five-year iPhone 7 microphone-failure anecdote",
        "http://localhost:9999/f/iphone/62384/time-to-change",
    ),
    (
        "iphone_6_apps",
        "008-forum-iphone-6-eight-years-app-support.json",
        "eight-year iPhone 6 app-compatibility anecdote",
        "http://localhost:9999/f/iphone/62290/ios-12-5",
    ),
    (
        "screen_burn_in",
        "009-wiki-screen-burn-in.json",
        "screen burn-in mechanism",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Screen_burn-in",
    ),
    (
        "planned_obsolescence",
        "010-wiki-planned-obsolescence.json",
        "planned-obsolescence and software-end-of-life concept",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Planned_obsolescence",
    ),
    (
        "repairability",
        "011-wiki-repairability.json",
        "repairability framework",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Repairability",
    ),
    (
        "modular_smartphone",
        "012-wiki-modular-smartphone.json",
        "modular-smartphone repair and tradeoff framework",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Modular_smartphone",
    ),
    (
        "service_life",
        "013-wiki-service-life.json",
        "service-life and technical-life distinction",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Service_life",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "ev_pixel_4a_listing_snapshot",
        "node_type": "attribute",
        "subject": "frozen renewed Pixel 4a with 5G listing",
        "predicate": "advertises_snapshot",
        "object": "a renewed 6.2-inch 128 GB and 6 GB RAM unlocked phone at 273.50 dollars with a 60 percent aggregate rating from 12 posted reviews",
        "source_url": SEARCHES[0][3],
        "search_id": "pixel_4a",
        "role": "product",
        "scope": "seller_snapshot_not_condition_support_failure_rate_or_2031_outcome",
        "quotes": [
            "Google Pixel 4a with 5G, 6.2\", 128GB, 6GB RAM, Unlocked Cellular - Just Black (Renewed)",
            "In stock SKU B08R61G69Q Rating: 60 % of 100 12 Reviews Add Your Review $273.50 Qty Add to Cart Add to Wish List Add to Compare",
            "Pixel 4a with 5G also takes amazing ultrawide photos in any light, keeps your data safe, blocks robocalls,[8] and has an all-day battery that can last up to 48 hours with Extreme Battery Saver.[6]",
        ],
        "accepted": "The frozen Pixel 4a with 5G seller page labels a renewed 6.2-inch, 128 GB, 6 GB RAM unlocked phone at 273.50 dollars with a 60 percent aggregate rating from twelve posted reviews and makes an Extreme Battery Saver claim; it gives no verified current-unit condition, current support end date, failure rate, or 2031 outcome.",
    },
    {
        "evidence_id": "ev_nord_n10_listing_snapshot",
        "node_type": "attribute",
        "subject": "frozen renewed OnePlus Nord N10 listing",
        "predicate": "advertises_snapshot",
        "object": "a renewed 6 GB and 128 GB 90 Hz phone at 44.91 dollars with a 69 percent aggregate rating, an internally inconsistent 11-review top summary and 12-review footer, plus generic condition, warranty, accessory, and carrier caveats",
        "source_url": SEARCHES[1][3],
        "search_id": "nord_n10",
        "role": "product",
        "scope": "seller_snapshot_generic_renewed_caveats_not_exact_unit_grade_or_longevity",
        "quotes": [
            "OnePlus Nord N10 (5G) 6GB(RAM)+128GB 90Hz Display (T-Mobile/Sprint Unlocked) BE2028 64MP Quad Camera Smartphone - Black (Renewed)",
            "In stock SKU B097BYW2NK Rating: 69 % of 100 11 Reviews Add Your Review $44.91 Qty Add to Cart Add to Wish List Add to Compare",
            "Reviews 12 Write Your Own Review",
            "90 days store limited warranty. Ships in non-retail box; Premium aftermarket charger and USB Cable only.",
            "Amazon Renewed condition : May have few minor scuffs or scratches; This device is Factory Unlocked and will work with all major GSM carriers.",
        ],
        "accepted": "The frozen Nord N10 seller page labels a renewed 6 GB, 128 GB, 90 Hz phone at 44.91 dollars with a 69 percent aggregate rating, but its top summary shows eleven reviews while its footer shows twelve; its minor-scuff, 90-day store-warranty, aftermarket-accessory, and carrier statements remain generic seller caveats, not an inspection grade, current support promise, or longevity test.",
    },
    {
        "evidence_id": "ev_blackview_listing_snapshot",
        "node_type": "attribute",
        "subject": "frozen Blackview BL5000 listing",
        "predicate": "advertises_snapshot",
        "object": "a 339.99 dollar phone with a 53 percent aggregate rating from four posted reviews and seller claims for ruggedness, IP68, 4980 mAh, 30 W charging, 8 GB plus 128 GB, and one-year warranty service",
        "source_url": SEARCHES[2][3],
        "search_id": "blackview_bl5000",
        "role": "product",
        "scope": "seller_ruggedness_and_battery_claims_not_independent_test_or_survival_rate",
        "quotes": [
            "Rugged Smartphone, Blackview BL5000 5G Phones Unlocked Dual SIM Smartphone with 6.5\" FHD Display, 8GB +128GB Big Storage,4980 mAh Massive Battery, 30W Fast Charging, Face Detection Smartphone Tmobile",
            "In stock SKU B09GFWWG8B Rating: 53 % of 100 4 Reviews Add Your Review $339.99 Color Black Green Qty Add to Cart Add to Wish List Add to Compare",
            "【Massive Battery Cell Phone】Blackview BL5000 built-in 4980 mAh battery, also comes with a 30W supercharge, theoretically, after a full charge, you can use it for 6 hours of gaming,22 hours of calling, or 48 hours of music listening.",
            "【Concern on Security】The screen and body of BL5000 rugged phone was made of Gorilla Glass, IP68 level protects your phone and makes it water-proof, dust-proof, and drop-proof.",
            "【Caring Service】We apply some Extra Gi-ft for BL5000 series, all the product enjoy a one-year warranty service after the purchase(not including Gi-ft), welcome to share your excellent experience,if you have any problem, please contact us intime",
        ],
        "accepted": "The frozen Blackview BL5000 seller page shows 339.99 dollars and a 53 percent aggregate rating from four posted reviews and claims 4980 mAh, 30 W charging, IP68 rugged protection, and one-year warranty service; none is an independent durability test, current support promise, population failure rate, or 2031 guarantee.",
    },
    {
        "evidence_id": "ev_iphone_x_battery_kit_snapshot",
        "node_type": "attribute",
        "subject": "frozen DEJI iPhone X battery-kit listing",
        "predicate": "advertises_exact_model_aftermarket_availability",
        "object": "a 19.99 dollar 3060 mAh kit for iPhone X A1865, A1901, and A1902, explicitly not XR or XS, with tools and instructions and a 100 percent aggregate rating from two posted reviews",
        "source_url": SEARCHES[3][3],
        "search_id": "iphone_x_battery",
        "role": "product",
        "scope": "seller_availability_claim_exact_iphone_x_models_not_quality_safety_or_other_phone_repairability",
        "quotes": [
            "Battery for iPhone X, DEJI 3060 High Capacity Upgraded Replacement Battery Compatible with iPhone X, with Professional Repair Tools Kit and Instructions",
            "In stock SKU B09FT1PXJH Rating: 100 % of 100 2 Reviews Add Your Review $19.99 Qty Add to Cart Add to Wish List Add to Compare",
            "Compatibility: This high capacity replacement battery compatible with iPhone X only (Model A1865, A1901, A1902). Not for XR or XS",
            "【What You Get】Comprehensive repair tools kit, adhesives and step-by-step instruction manual are provided with the battery.",
        ],
        "accepted": "The frozen DEJI seller page advertises a 19.99 dollar 3060 mAh battery kit with tools and instructions only for iPhone X A1865, A1901, and A1902, explicitly not XR or XS, and shows two posted reviews; it does not verify cell quality, safety, repair success, or parts availability for Pixel, Nord, or Blackview.",
    },
    {
        "evidence_id": "ev_a13_case_snapshot",
        "node_type": "attribute",
        "subject": "frozen Dahkoiz Galaxy A13 5G case listing",
        "predicate": "advertises_exact_model_accessory_availability",
        "object": "an 11.99 dollar Galaxy A13 5G case with one tempered-glass protector and port covers, no posted review, and a condition that the case be removed for wireless charging",
        "source_url": SEARCHES[4][3],
        "search_id": "a13_case",
        "role": "product",
        "scope": "seller_accessory_claim_exact_galaxy_a13_5g_not_verified_protection_or_transfer",
        "quotes": [
            "Dahkoiz for Samsung Galaxy A13 5G Case with Glass Screen Protector and Dust-Proof Port Cover, Work with Magnetic Car Mount, Full Body Protection Silicone Rubber Phone Case, Teal",
            "In stock SKU B09MTFD4KQ Be the first to review this product $11.99",
            "Question 2: Will the case support wireless charging? Answer: No, the case does not allow for wireless charging. Please remove it before placing it on a wireless charger.",
            "【Full Body Covered & Dust-proof】Raised bezels lift screen and camera off flat surfaces. Port covers keep out dust, lint and debris",
        ],
        "accepted": "The frozen Dahkoiz seller page advertises an 11.99 dollar Galaxy A13 5G case with one tempered-glass protector and port covers, shows no posted review, and says to remove the case for wireless charging; it does not prove protection effectiveness or apply to Pixel, Nord, Blackview, or iPhone X.",
    },
    {
        "evidence_id": "prop_iphone_6s_long_use_scope",
        "node_type": "proposition",
        "subject": "one iPhone 6s author",
        "predicate": "reports_scoped_long_use_sequence",
        "object": "use since 2016 with a battery needing replacement, working screen and camera, rare freezes, modest slowing, quiet call audio, occasional app crashes, and slow Spotify opening",
        "source_url": SEARCHES[5][3],
        "search_id": "iphone_6s_long_use",
        "role": "community",
        "scope": "single_dated_apple_anecdote_not_prevalence_causation_or_candidate_evidence",
        "quotes": [
            "I got my first Iphone in 2016 - the 6s. And still have it with me today.",
            "The battery desperately needs replacing, screen + camera still work, the phone rarely freezes, obviously got a little slower over the years but not massively.",
            "The speakers (where you would usually put your ear in a call) are way too silent which is why I either need to call via headphones or speaker, although that never really bothered me much. Sometimes applications crash when there is too much going on and Spotify takes quite a while to open which is a tad annoying.",
        ],
        "accepted": "One author says an iPhone 6s kept since 2016 has a battery needing replacement, a working screen and camera, rare freezes, some slowing, quiet call audio, occasional app crashes, and slow Spotify opening; this single report gives no prevalence, causal ranking, or evidence for the captured candidate phones.",
    },
    {
        "evidence_id": "prop_iphone_7_five_year_scope",
        "node_type": "proposition",
        "subject": "one five-year iPhone 7 author",
        "predicate": "reports_unresolved_post_repair_failure",
        "object": "microphone and call-audio failure after a legitimate battery replacement while explicitly asking whether the problem is hardware or software",
        "source_url": SEARCHES[6][3],
        "search_id": "iphone_7_five_years",
        "role": "community",
        "scope": "temporal_anecdote_with_unresolved_attribution_not_repair_causation",
        "quotes": [
            "Hello, I'm currently an iPhone 7 user. I have owned this phone for 5 years now.",
            "Currently, in 2022 the problems start rolling in after I got a legit battery replacement. Now, my microphone won't work, every time someone calls me, they can't hear me nor can I hear them.",
            "After fiddling with other apps like voice memos it still won't work. Is it a hardware or software problem?",
        ],
        "accepted": "One author says a five-year iPhone 7 developed microphone and call-audio failure after a legitimate battery replacement and explicitly asks whether the cause is hardware or software; temporal order does not prove the repair caused the failure.",
    },
    {
        "evidence_id": "prop_iphone_6_app_scope",
        "node_type": "proposition",
        "subject": "one eight-year iPhone 6 author",
        "predicate": "reports_physical_function_with_app_incompatibility",
        "object": "a still functional phone while Twitter, Medium, Notion, Pocket, and other apps were becoming incompatible with iOS 12.5",
        "source_url": SEARCHES[7][3],
        "search_id": "iphone_6_apps",
        "role": "community",
        "scope": "single_dated_app_compatibility_report_not_universal_support_policy",
        "quotes": [
            "Yes, I am one of these guys that still use an iPhone 6, don't get me wrong the device is pretty functionable...But I am planning on buying a new iPhone at start of 2023.",
            "But for now, as time passes a lot of apps are becoming incompatible with iOS 12.5 and its kind of frustrating how apps like Twitter, Medium, Notion, Pocket...etc. don't support iOS 12.5.",
            "While I appreciate the fact that the iPhone 6 is an 8 year old phone and the fact that it doesn't have the power to meet the standards of certain apps we have today, yet can't I just download older versions of these apps?",
        ],
        "accepted": "One author describes an eight-year iPhone 6 as still functional while naming several apps becoming incompatible with iOS 12.5; this is a dated individual report, not a universal app rule, current support policy, or candidate-model outcome.",
    },
    {
        "evidence_id": "prop_screen_burn_in_scope",
        "node_type": "proposition",
        "subject": "screen burn-in",
        "predicate": "is_generic_permanent_display_mechanism",
        "object": "permanent discoloration caused by cumulative non-uniform screen use, distinct from non-permanent LCD image persistence",
        "source_url": SEARCHES[8][3],
        "search_id": "screen_burn_in",
        "role": "concept",
        "scope": "generic_mechanism_not_phone_model_incidence_or_time_to_failure",
        "quotes": [
            "Screen burn-in , image burn-in , ghost image , or shadow image , is a permanent discoloration of areas on an electronic visual display such as a cathode-ray tube (CRT) or organic light-emitting diode (OLED) in a computer monitor or television set . It is caused by cumulative non-uniform use of the screen.",
            "Newer liquid-crystal displays (LCDs) may suffer from a phenomenon called image persistence instead, which is not permanent.",
        ],
        "accepted": "The captured concept page defines screen burn-in as permanent display discoloration caused by cumulative non-uniform use and distinguishes it from non-permanent LCD image persistence; it supplies no smartphone-model incidence or time-to-failure estimate.",
    },
    {
        "evidence_id": "prop_planned_obsolescence_scope",
        "node_type": "proposition",
        "subject": "planned obsolescence and software end of life",
        "predicate": "provides_generic_concepts_without_vendor_finding",
        "object": "an artificially limited useful-life concept, a general maintenance-economics reason for proprietary software end of life, and a distinction between perceived and premeditated obsolescence",
        "source_url": SEARCHES[9][3],
        "search_id": "planned_obsolescence",
        "role": "concept",
        "scope": "generic_policy_framework_never_vendor_intent_or_misconduct_evidence",
        "quotes": [
            "In economics and industrial design , planned obsolescence (also called built-in obsolescence or premature obsolescence ) is the concept of policies planning or designing a product with an artificially limited useful life or a purposely frail design, so that it becomes obsolete after a certain predetermined period of time upon which it decrementally functions or suddenly ceases to function, or might be perceived as unfashionable .",
            "Most proprietary software will ultimately reach an end-of-life point at which the supplier will cease updates and support, usually when and because the cost of code maintenance, testing and support exceed the revenue generated from the old version.",
            "Although similar, it is a result of consumer perception rather than premeditated (planned) by the designer.",
        ],
        "accepted": "The captured page supplies a general planned-obsolescence concept, notes that proprietary software can reach end of life when maintenance, testing, and support costs exceed revenue, and distinguishes perceived from premeditated obsolescence; it does not establish intent or misconduct by any captured vendor.",
    },
    {
        "evidence_id": "prop_repairability_framework_scope",
        "node_type": "proposition",
        "subject": "product repairability",
        "predicate": "uses_multi_field_framework",
        "object": "ease of repair and maintenance assessed through documentation, disassembly, spare-parts availability, spare-part pricing, and product-specific factors",
        "source_url": SEARCHES[10][3],
        "search_id": "repairability",
        "role": "concept",
        "scope": "generic_framework_not_current_score_for_any_captured_phone",
        "quotes": [
            "Repairability is a measure of the degree to and ease with which a product can be repaired and maintained, usually by end consumers.",
            "Products are evaluated on 5 key areas: documentation, disassembly, spare parts availability, spare part pricing, and product specifics.",
        ],
        "accepted": "The captured repairability page defines ease of repair and maintenance and lists documentation, disassembly, spare-parts availability, spare-part pricing, and product-specific factors; it is a framework, not a current exact-model score for any captured phone.",
    },
    {
        "evidence_id": "prop_modular_smartphone_scope",
        "node_type": "proposition",
        "subject": "modular smartphone design",
        "predicate": "trades_replaceability_for_other_costs",
        "object": "replaceable components intended to reduce waste, extend life, and lower repair costs, with bulk and performance tradeoffs and no guaranteed outcome",
        "source_url": SEARCHES[11][3],
        "search_id": "modular_smartphone",
        "role": "concept",
        "scope": "generic_design_framework_not_current_product_or_2031_guarantee",
        "quotes": [
            "A modular smartphone is a smartphone designed for users to upgrade or replace components and modules without the need for resoldering or repair services.",
            "This design aims to reduce electronic waste , increase the phone's lifespan, and lower repair costs.",
            "However, modular smartphones are generally bulkier and slower than their non-modular counterparts which may make them less attractive for most consumers.",
        ],
        "accepted": "The captured modular-smartphone page says replaceable components aim to reduce waste, increase lifespan, and lower repair costs while noting bulk and performance tradeoffs; this generic design framework is not a current product finding or 2031 guarantee.",
    },
    {
        "evidence_id": "prop_service_life_scope",
        "node_type": "proposition",
        "subject": "product service life",
        "predicate": "differs_from_technical_predicted_and_replacement_life",
        "object": "total time in use and manufacturer serviceability or support, distinct from physical technical life, predicted life, and purchaser replacement timing",
        "source_url": SEARCHES[12][3],
        "search_id": "service_life",
        "role": "concept",
        "scope": "generic_lifecycle_vocabulary_not_numeric_smartphone_estimate",
        "quotes": [
            "A product's service life is its period of use in service.",
            "Service life has been defined as \"a product's total life in use from the point of sale to the point of discard\" and distinguished from replacement life , \"the period after which the initial purchaser returns to the shop for a replacement\".",
            "It is the time that any manufactured item can be expected to be \"serviceable\" or supported by its manufacturer . Service life is not to be confused with shelf life , which deals with storage time, or with technical life, which is the maximum period during which it can physically function.",
        ],
        "accepted": "The captured service-life page distinguishes total time in use and manufacturer serviceability or support from physical technical life, predicted life, and purchaser replacement timing; it gives lifecycle vocabulary, not a numeric smartphone lifetime estimate.",
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
            "registry_id": "reg_case_spec_phone_2031_0033",
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
            "mechanism_seller_snapshot_boundary",
            "mechanism",
            "three frozen phone listings",
            "support_only",
            "seller-level catalog attributes and caveats, not exact-unit condition, current support, failure rates, or 2031 outcomes",
            "seller_snapshot_boundary_v1",
        ),
        (
            "mechanism_exact_aftermarket_boundary",
            "mechanism",
            "battery-kit and case listings",
            "remain_exact_model",
            "iPhone X battery-kit and Galaxy A13 5G case availability claims with no transfer to other phones or proof of effectiveness",
            "exact_aftermarket_scope_v1",
        ),
        (
            "mechanism_long_use_anecdote_boundary",
            "mechanism",
            "three Apple long-use reports",
            "enumerate_without_generalizing",
            "individual physical, performance, repair, and app-compatibility sequences without prevalence, causation, or candidate-model inference",
            "long_use_anecdote_scope_v1",
        ),
        (
            "mechanism_physical_policy_layers",
            "mechanism",
            "phone end-of-use analysis",
            "separates",
            "physical function, component wear, repair access, manufacturer serviceability, security support, app compatibility, and user task satisfaction while making no vendor-intent finding",
            "physical_and_policy_layering_v1",
        ),
        (
            "bridge_repairability_audit",
            "bridge",
            "long-life purchase claim",
            "requires_exact_model_repair_evidence",
            "documentation, disassembly, parts availability and price, service channels, repair cost, data effects, and post-repair checks rather than another model's aftermarket listing",
            "repairability_and_modularity_framework_v1",
        ),
        (
            "bridge_current_2031_matrix",
            "bridge",
            "conditional 2031 procurement decision",
            "requires",
            "current exact-model support, app, region, condition, parts, manuals, repair, warranty, return-window, accessory, daily-task trial, maintenance, backup, and exit-trigger fields or deferral",
            "current_evidence_matrix_v1",
        ),
        (
            "decision_conditional_2031_selection",
            "decision",
            "phone intended for use through 2031",
            "selects_admissible_set",
            "defer a universal winner from the frozen pool and choose only after a current exact candidate clears the policy, condition, repair, parts, return-window, and task-trial matrix, without promising survival",
            "conditional_2031_decision_v1",
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
        "mechanism_seller_snapshot_boundary": [
            "ev_pixel_4a_listing_snapshot",
            "ev_nord_n10_listing_snapshot",
            "ev_blackview_listing_snapshot",
        ],
        "mechanism_exact_aftermarket_boundary": [
            "ev_iphone_x_battery_kit_snapshot",
            "ev_a13_case_snapshot",
        ],
        "mechanism_long_use_anecdote_boundary": [
            "prop_iphone_6s_long_use_scope",
            "prop_iphone_7_five_year_scope",
            "prop_iphone_6_app_scope",
        ],
        "mechanism_physical_policy_layers": [
            "prop_iphone_6s_long_use_scope",
            "prop_iphone_7_five_year_scope",
            "prop_iphone_6_app_scope",
            "prop_screen_burn_in_scope",
            "prop_planned_obsolescence_scope",
            "prop_service_life_scope",
        ],
        "bridge_repairability_audit": [
            "prop_repairability_framework_scope",
            "prop_modular_smartphone_scope",
            "ev_iphone_x_battery_kit_snapshot",
            "ev_a13_case_snapshot",
            "prop_iphone_6s_long_use_scope",
            "prop_iphone_7_five_year_scope",
        ],
        "bridge_current_2031_matrix": [
            "mechanism_seller_snapshot_boundary",
            "mechanism_exact_aftermarket_boundary",
            "mechanism_long_use_anecdote_boundary",
            "mechanism_physical_policy_layers",
            "bridge_repairability_audit",
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
                "source_id": "decision_conditional_2031_selection",
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
