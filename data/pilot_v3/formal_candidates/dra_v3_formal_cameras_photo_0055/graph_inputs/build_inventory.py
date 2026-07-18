#!/usr/bin/env python3
"""Build the frozen Q55 decade-ownership camera evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-cameras-photo-0055-decade-ownership-serviceability-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-cameras-photo-0055-decade-ownership-serviceability-boundary-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_cameras_photo_0055"
TOPIC = "decade_camera_ownership_exact_unit_serviceability_boundary"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0055/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    ("pentax_k30_offer", "001-shopping-pentax-k30-discontinued-weather.json", "Pentax K-30 frozen offer", "http://localhost:7770/pentax-k-30-weather-sealed-16-mp-cmos-digital-slr-white-body-only-discontinued-by-manufacturer.html"),
    ("pentax_k3iii_offer", "002-shopping-pentax-k3iii-weather-body.json", "Pentax K-3 Mark III frozen offer", "http://localhost:7770/pentax-k-3-mark-iii-flagship-aps-c-silver-camera-body-12fps-touch-screen-lcd-weather-resistant-magnesium-alloy-body-with-in-body-5-axis-shake-reduction-1-05x-optical-viewfinder-with-100-fov.html"),
    ("pentax_k1ii_offer", "003-shopping-pentax-k1ii-weather-body.json", "Pentax K-1 Mark II frozen offer", "http://localhost:7770/pentax-k-1-mark-ii-full-frame-weather-resistant-dslr-camera-body-only-with-32gb-card-deluxe-photo-cleaning-kit-bundle.html"),
    ("nikon_d7500_offer", "004-shopping-nikon-d7500-weather-body.json", "Nikon D7500 frozen offer", "http://localhost:7770/nikon-d7500-dslr-camera-body-only-20-9mp-dx-format-4k-uhd-video-weather-sealed-wi-fi-with-padded-shoulder-case-photo-video-edition-software-package-and-128gb-high-speed-memory.html"),
    ("canon_5div_offer", "005-shopping-canon-5div-international-body.json", "Canon 5D Mark IV frozen offer", "http://localhost:7770/canon-eos-5d-mark-iv-dslr-camera-body-only-pixibytes-exclusive-microfiber-cleaning-cloth-international-version.html"),
    ("rokinon_weather_offer", "006-shopping-rokinon-weather-lens.json", "Rokinon weather-sealed lens frozen offer", "http://localhost:7770/rokinon-series-ii-14mm-f2-8-weather-sealed-ultra-wide-angle-lens-for-canon-ef-se14-c.html"),
    ("pentax_k3iii_model", "007-wiki-pentax-k3iii-model.json", "Pentax K-3 Mark III model context", "http://localhost:8090/content/wikipedia_en_all_nopic/Pentax_K-3_Mark_III"),
    ("nikon_d7500_model", "008-wiki-nikon-d7500-model.json", "Nikon D7500 model context", "http://localhost:8090/content/wikipedia_en_all_nopic/Nikon_D7500"),
    ("canon_5div_model", "009-wiki-canon-5div-model.json", "Canon 5D Mark IV model context", "http://localhost:8090/content/wikipedia_en_all_nopic/Canon_EOS_5D_Mark_IV"),
    ("focal_plane_shutter", "010-wiki-focal-plane-shutter.json", "focal-plane shutter mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Focal-plane_shutter"),
    ("lens_mount", "011-wiki-lens-mount-interface.json", "lens-mount interface", "http://localhost:8090/content/wikipedia_en_all_nopic/Lens_mount"),
    ("o_ring", "012-wiki-o-ring-seal.json", "O-ring seal mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/O-ring"),
    ("gasket", "013-wiki-gasket-seal.json", "gasket seal mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Gasket"),
    ("reliability", "014-wiki-reliability-engineering.json", "reliability definition", "http://localhost:8090/content/wikipedia_en_all_nopic/Reliability_engineering"),
    ("mtbf", "015-wiki-mtbf-repairable-system.json", "MTBF boundary", "http://localhost:8090/content/wikipedia_en_all_nopic/Mean_time_between_failures"),
    ("spare_part", "016-wiki-spare-part.json", "spare-part definition", "http://localhost:8090/content/wikipedia_en_all_nopic/Spare_part"),
    ("fru", "017-wiki-field-replaceable-unit.json", "field-replaceable-unit definition", "http://localhost:8090/content/wikipedia_en_all_nopic/Field-replaceable_unit"),
    ("old_camera_post", "018-forum-old-cameras-good-condition.json", "one old-camera donation post", "http://localhost:9999/f/rva/133192/best-places-to-donate-old-cameras"),
    ("vintage_lens_post", "019-forum-vintage-lens-availability.json", "one local vintage-lens question", "http://localhost:9999/f/baltimore/81200/best-pawnshops-thrift-stores-for-vintage-camera-lenses"),
    ("replacement_parts_post", "020-forum-replacement-parts-scope.json", "one laptop-parts anecdote", "http://localhost:9999/f/BuyItForLife/32714/dell-will-sell-replacement-laptop-parts-if-you-just-ask"),
]


def ev(
    evidence_id: str,
    subject: str,
    predicate: str,
    object_: str,
    search_index: int,
    role: str,
    scope: str,
    quotes: list[str],
    accepted: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "source_url": SEARCHES[search_index][3],
        "search_id": SEARCHES[search_index][0],
        "role": role,
        "scope": scope,
        "quotes": quotes,
        "accepted": accepted,
    }


EVIDENCE = [
    ev(
        "prop_pentax_k30_seller_scope",
        "frozen Pentax K-30 seller page",
        "shows_a_body_offer_with_a_discontinuation_conflict",
        "SKU B0082OJ2YG at 359.49 dollars rated 73 percent over twelve reviews, with a discontinued title but an Is Discontinued By Manufacturer No field",
        0,
        "product",
        "frozen_seller_identity_price_weather_and_internal_conflict_not_current_condition_or_survival",
        [
            "Pentax K-30 Weather-Sealed 16 MP CMOS Digital SLR (White, Body Only) (Discontinued by Manufacturer)",
            "In stock SKU B0082OJ2YG Rating: 73 % of 100 12 Reviews Add Your Review $359.49",
            "Is Discontinued By Manufacturer No",
        ],
        "The frozen K-30 page shows SKU B0082OJ2YG at 359.49 dollars and a 73-percent rating over twelve reviews. Its title calls the white body-only camera discontinued, while a later field says Is Discontinued By Manufacturer No. Preserve that conflict; neither field verifies current availability, exact-unit condition, shutter count, seal health or decade survival.",
    ),
    ev(
        "prop_pentax_k3iii_seller_scope",
        "frozen Pentax K-3 Mark III seller page",
        "shows_a_weather_resistant_magnesium_body_offer",
        "SKU B091TTFCCH at 1,996.95 dollars rated 93 percent over eleven reviews with seller weather-resistant and magnesium wording",
        1,
        "product",
        "frozen_seller_identity_price_and_weather_copy_not_ingress_test_condition_or_lifetime",
        [
            "Pentax K-3 Mark III Flagship APS-C Silver Camera Body - 12fps, Touch Screen LCD, Weather Resistant Magnesium Alloy Body",
            "In stock SKU B091TTFCCH Rating: 93 % of 100 11 Reviews Add Your Review $1,996.95",
        ],
        "The frozen K-3 Mark III page shows SKU B091TTFCCH at 1,996.95 dollars, rated 93 percent over eleven reviews, and uses weather-resistant magnesium-alloy body wording. It does not supply a standardized ingress rating, exact-unit seal condition, shutter history, service commitment, current delivered offer or decade-long result.",
    ),
    ev(
        "prop_pentax_k1ii_seller_scope",
        "frozen Pentax K-1 Mark II seller page",
        "shows_a_weather_resistant_body_bundle",
        "SKU B07L2BQV81 at 1,602.05 dollars with no reviews shown and a body-only camera plus card and cleaning-kit title",
        2,
        "product",
        "frozen_seller_bundle_weather_and_price_copy_not_exact_unit_or_lifetime_test",
        [
            "Pentax K-1 Mark II Full Frame Weather Resistant DSLR Camera (Body Only) with 32GB Card & Deluxe Photo Cleaning Kit Bundle",
            "In stock SKU B07L2BQV81 Be the first to review this product $1,602.05",
        ],
        "The frozen K-1 Mark II page shows SKU B07L2BQV81 at 1,602.05 dollars with no reviews shown and titles a body-only camera bundled with a card and cleaning kit. Weather-resistant and extensive-sealing copy is seller material, not proof of current seal condition, exact-unit wear, current authorized service, future parts or ten-year survival.",
    ),
    ev(
        "prop_nikon_d7500_seller_scope",
        "frozen Nikon D7500 seller page",
        "shows_an_import_body_bundle_and_seller_warranty",
        "SKU B08N5G61P2 at 1,199 dollars with no reviews shown, an import-model description, USA-compatible accessories and a one-year limited seller warranty",
        3,
        "product",
        "frozen_import_bundle_and_seller_warranty_not_manufacturer_region_support_or_lifetime",
        [
            "Nikon D7500 DSLR Camera (Body Only) || 20.9MP DX-Format || 4K UHD Video || Weather-Sealed || Wi-Fi",
            "In stock SKU B08N5G61P2 Be the first to review this product $1,199.00",
            "This DSLR Camera Bundle comes complete with USA compatible accessories and a 1-Year Limited Seller Warranty Nikon D7500 DSLR Camera (Import Model)",
        ],
        "The frozen D7500 page shows SKU B08N5G61P2 at 1,199 dollars with no reviews shown, calls the camera weather-sealed, and describes an import-model bundle with USA-compatible accessories and a one-year limited seller warranty. It does not prove manufacturer warranty eligibility, exact delivered items, current condition, parts access or decade serviceability.",
    ),
    ev(
        "prop_canon_5div_seller_scope",
        "frozen Canon 5D Mark IV seller page",
        "shows_an_international_version_body_offer",
        "SKU B01LY3WID1 at 2,499 dollars with no reviews shown and international-version wording",
        4,
        "product",
        "frozen_international_version_price_and_workhorse_copy_not_region_service_or_survival",
        [
            "Canon EOS 5D Mark IV DSLR Camera (Body Only) + Pixibytes Exclusive Microfiber Cleaning Cloth (International Version)",
            "In stock SKU B01LY3WID1 Be the first to review this product $2,499.00",
        ],
        "The frozen 5D Mark IV page shows SKU B01LY3WID1 at 2,499 dollars with no reviews shown and calls the body an international version. Workhorse and performance copy does not verify the exact serial, current condition, regional Canon service eligibility, warranty, shutter history, future parts or lifetime cost.",
    ),
    ev(
        "prop_rokinon_weather_lens_scope",
        "frozen Rokinon Canon EF lens page",
        "shows_a_weather_sealed_lens_mount_offer",
        "SKU B0898Z5FVG at 349 dollars with no reviews shown and a claim that the sealed lens mount protects the mount gap",
        5,
        "product",
        "frozen_lens_mount_weather_claim_not_whole_system_seal_compatibility_or_lifetime",
        [
            "Rokinon Series II 14mm F2.8 Weather Sealed Ultra Wide Angle Lens for Canon EF (SE14-C)",
            "In stock SKU B0898Z5FVG Be the first to review this product $349.00",
            "The weather sealed lens mount protects the gap between the lens and camera mount.",
        ],
        "The frozen Rokinon page shows SKU B0898Z5FVG at 349 dollars with no reviews shown and says the weather-sealed lens mount protects the gap between lens and camera mount. That seller statement does not prove the whole body-lens system is sealed, compatible with a non-EF body, currently healthy, independently ingress-tested or durable for a decade.",
    ),
    ev(
        "prop_pentax_k3iii_model_scope",
        "Pentax K-3 Mark III model page",
        "maps_release_mount_and_interchangeable_form",
        "a Pentax KAF2 interchangeable-lens DSLR released by Ricoh Imaging in 2021",
        6,
        "concept",
        "frozen_model_mapping_not_exact_seller_unit_condition_support_or_survival",
        [
            "Lens mount Pentax KAF2 Lens Interchangeable lens",
            "The Pentax K-3 Mark III is a professional digital single-lens reflex camera released by Ricoh Imaging on 23 April 2021.",
        ],
        "The model page identifies the K-3 Mark III as a Pentax KAF2 interchangeable-lens DSLR released by Ricoh Imaging in 2021. These model facts do not verify the seller unit's identity, condition, shutter count, service eligibility, seal health, lens compatibility in a particular configuration or decade survival.",
    ),
    ev(
        "prop_nikon_d7500_model_scope",
        "Nikon D7500 model page",
        "maps_mount_shutter_and_release_context",
        "a Nikon F-mount interchangeable-lens DSLR announced in 2017 with a focal-plane shutter",
        7,
        "concept",
        "frozen_model_mapping_not_import_unit_condition_region_support_or_survival",
        [
            "Lens Lens Interchangeable, Nikon F-mount",
            "Shutter Shutter Electronically controlled vertical-travel focal plane shutter",
            "It was announced by Nikon Corporation on 12 April 2017, and started shipping on 2 June 2017.",
        ],
        "The D7500 model page identifies an interchangeable Nikon F-mount DSLR with an electronically controlled vertical-travel focal-plane shutter and says Nikon announced it in 2017. This does not verify the captured import unit, remaining shutter life, mount condition, manufacturer service eligibility or future parts.",
    ),
    ev(
        "prop_canon_5div_model_scope",
        "Canon 5D Mark IV model page",
        "maps_mount_sensor_shutter_and_release_context",
        "an interchangeable Canon EF full-frame DSLR announced in 2016 with an electronic focal-plane shutter",
        8,
        "concept",
        "frozen_model_mapping_not_international_unit_condition_region_support_or_survival",
        [
            "Lens mount Canon EF Lens Interchangeable",
            "Shutter Shutter Electronic focal-plane",
            "Announced on 25 August 2016 as the successor to the EOS 5D Mark III",
        ],
        "The 5D Mark IV model page maps an interchangeable Canon EF full-frame DSLR with an electronic focal-plane shutter and says it was announced in 2016. Those model facts do not verify the international seller unit, exact serial, shutter condition, regional support, current parts access or survival probability.",
    ),
    ev(
        "prop_focal_plane_shutter_mechanism_scope",
        "focal-plane-shutter concept",
        "locates_the_shutter_and_describes_moving_curtains",
        "a shutter immediately in front of film or sensor, with traditional two-curtain forms",
        9,
        "concept",
        "generic_mechanism_not_actuation_rating_failure_distribution_or_exact_unit_wear",
        [
            "a focal-plane shutter ( FPS ) is a type of photographic shutter that is positioned immediately in front of the focal plane of the camera",
            "uses two shutter curtains, made of opaque rubberised fabric, that run horizontally across the film plane",
        ],
        "The focal-plane-shutter page locates this shutter immediately in front of the film or image sensor and describes a traditional two-curtain mechanism. It provides no candidate-specific actuation rating, failure distribution, repair price, abuse history or exact-unit wear measurement.",
    ),
    ev(
        "prop_lens_mount_interface_scope",
        "lens-mount concept",
        "defines_a_mechanical_and_often_electrical_interface",
        "the interface between an interchangeable-lens camera body and lens",
        10,
        "concept",
        "generic_interface_not_mount_tolerance_wear_compatibility_or_repair_result",
        [
            "A lens mount is an interface",
            "mechanical and often also electrical",
            "between a photographic camera body and a lens.",
        ],
        "The lens-mount page defines a mechanical and often electrical interface between camera body and lens in interchangeable-lens systems. It does not measure mount play, flange condition, contact wear, exact lens compatibility, repairability or remaining service life for any candidate unit.",
    ),
    ev(
        "prop_o_ring_seal_scope",
        "O-ring concept",
        "defines_an_elastomer_loop_compressed_to_form_a_seal",
        "an elastomer loop seated in a groove and compressed between parts to seal an interface",
        11,
        "concept",
        "generic_seal_mechanism_not_camera_material_location_schedule_or_condition",
        [
            "it is a loop of elastomer with a round cross-section",
            "designed to be seated in a groove and compressed during assembly between two or more parts, forming a seal at the interface.",
        ],
        "The O-ring page describes an elastomer loop seated in a groove and compressed between parts to form a seal. It does not identify an exact camera's O-ring material, location, exposure, replacement interval, current elasticity, service method or remaining life.",
    ),
    ev(
        "prop_gasket_seal_scope",
        "gasket concept",
        "defines_a_compressed_mechanical_seal_between_surfaces",
        "a deformable seal filling space between mating surfaces, generally to prevent leakage",
        12,
        "concept",
        "generic_seal_mechanism_not_camera_seal_inventory_material_or_condition",
        [
            "A gasket is a mechanical seal which fills the space between two or more mating surfaces, generally to prevent leakage from or into the joined objects while under compression",
            "It is a deformable material that is used to create a static seal and maintain that seal under various operating conditions in a mechanical assembly.",
        ],
        "The gasket page defines a compressed mechanical seal that fills space between mating surfaces and notes a deformable material maintaining a static seal under operating conditions. It supplies no candidate-camera seal inventory, material specification, maintenance schedule, replacement stock or current condition.",
    ),
    ev(
        "prop_reliability_probability_scope",
        "reliability-engineering concept",
        "defines_reliability_for_function_time_and_environment",
        "the probability of adequate intended function for a specified time or defined environment without failure",
        13,
        "concept",
        "generic_probability_definition_not_model_distribution_or_exact_unit_prediction",
        [
            "Reliability is defined as the probability that a product, system, or service will perform its intended function adequately for a specified period of time; or will operate in a defined environment without failure.",
            "This probability is estimated from detailed (physics of failure) analysis, previous data sets, or through reliability testing and reliability modeling.",
        ],
        "The reliability page defines reliability relative to an intended function, specified time and environment, and says estimation can use failure analysis, data, testing or modeling. The packet supplies no camera-model population, use profile or estimate that predicts one unit or ranks the bodies.",
    ),
    ev(
        "prop_mtbf_repairable_average_scope",
        "MTBF concept",
        "defines_an_average_for_repairable_systems",
        "predicted elapsed or average time between inherent failures during normal operation, used for repairable systems and dependent on the failure definition",
        14,
        "concept",
        "generic_repairable_system_metric_not_camera_rating_distribution_or_remaining_life",
        [
            "Mean time between failures ( MTBF ) is the predicted elapsed time between inherent failures of a mechanical or electronic system during normal system operation.",
            "The term is used for repairable systems while mean time to failure ( MTTF ) denotes the expected time to failure for a non-repairable system.",
            "The definition of MTBF depends on the definition of what is considered a failure.",
        ],
        "The MTBF page defines a predicted or average time between inherent failures during normal operation, distinguishes repairable-system MTBF from non-repairable MTTF and says the failure definition matters. No captured source provides a camera-specific MTBF, population, censoring rule or exact-unit remaining life.",
    ),
    ev(
        "prop_spare_part_scope",
        "spare-part concept",
        "defines_an_interchangeable_inventory_part_for_repair",
        "an interchangeable part kept in inventory for repair or refurbishment",
        15,
        "concept",
        "generic_part_definition_not_camera_inventory_authorization_price_or_future_supply",
        [
            "A spare part , spare , service part , repair part , or replacement part , is an interchangeable part that is kept in an inventory and used for the repair or refurbishment of defective equipment/units.",
            "Spare parts are an important feature of logistics engineering and supply chain management",
        ],
        "The spare-part page defines an interchangeable part kept in inventory for repair or refurbishment and places spare parts in logistics and supply-chain management. It does not prove that any candidate camera part is stocked, authorized, affordable, regionally available or promised in the future.",
    ),
    ev(
        "prop_fru_scope",
        "field-replaceable-unit concept",
        "defines_a_quickly_removable_replaceable_part_or_assembly",
        "a part or assembly replaceable by a user or technician without sending the entire system to a repair facility, with granularity affecting ownership and support cost",
        16,
        "concept",
        "generic_fru_definition_not_camera_design_documentation_authorization_or_part_supply",
        [
            "A field-replaceable unit ( FRU )",
            "can be quickly and easily removed from a computer or other piece of electronic equipment, and replaced by the user or a technician without having to send the entire product or system to a repair facility.",
            "The granularity of FRUs in a system impacts total cost of ownership and support",
        ],
        "The FRU page describes a part or assembly replaceable without sending the entire system to a repair facility and says FRU granularity affects total ownership and support cost. It does not establish camera FRU design, documentation, authorization, diagnostic access or parts supply.",
    ),
    ev(
        "prop_old_camera_donation_anecdote_scope",
        "old-camera donation forum post",
        "reports_one_authors_old_items_as_good_condition",
        "one mover says several old point-and-shoot cameras and a GoPro are in good condition with accessories and asks where to donate them",
        17,
        "community",
        "single_author_unspecified_items_not_survival_distribution_or_model_comparison",
        [
            "Best places to donate old cameras?",
            "I am getting ready to move and am looking to get rid of things including some old cameras that I have, specifically a couple of point and shoot cameras and a go pro.",
            "All are in good condition and have accessories",
        ],
        "One Richmond author says several old point-and-shoot cameras and a GoPro are in good condition with accessories and asks where to donate them. The post gives no model, age, usage, inspection or failure denominator, so it is not a survival distribution or durability comparison.",
    ),
    ev(
        "prop_vintage_lens_availability_question_scope",
        "vintage-lens forum thread",
        "asks_about_local_secondary_market_availability",
        "one Baltimore newcomer asks where thrift or pawn shops sell antiques and old camera lenses, followed by mixed local suggestions",
        18,
        "community",
        "local_question_and_replies_not_verified_inventory_condition_compatibility_or_future_supply",
        [
            "Best pawnshops/thrift stores for vintage camera lenses?",
            "was wondering if anyone knew of any cool thrift/pawn shops that sold a wide variety of antiques and especially old camera lenses?",
            "Most camera stores in central Maryland have closed or been purchased by Ritz",
        ],
        "One Baltimore newcomer asks where thrift or pawn shops sell antiques and old camera lenses and receives mixed local suggestions. The thread is not a verified inventory, condition report, mount-compatibility check, service channel or promise of future lens and part availability.",
    ),
    ev(
        "prop_laptop_parts_anecdote_scope",
        "laptop replacement-parts forum post",
        "reports_one_owners_parts_request_and_self_repair_context",
        "one 2017 Dell XPS owner says support supplied a barrel-jack port and keyboard after part identification and discussion of self-repair",
        19,
        "community",
        "single_laptop_owner_and_time_scoped_parts_path_not_camera_policy_or_future_supply",
        [
            "Dell will sell replacement laptop parts if you just ask!",
            "My laptop is a Dell XPS 15 9560 from the spring of 2017, and it only had a 1 year warranty.",
            "Every part in my laptop has a unique ID sticker on it.",
        ],
        "One Dell XPS 15 9560 owner reports a 2017 laptop, a one-year warranty and obtaining parts after identifying the needed components and explaining self-repair. That device-, owner- and time-scoped anecdote is not a camera manufacturer policy, authorized camera repair procedure or future parts guarantee.",
    ),
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
            f"http://localhost:8081/search?capture_run={RUN_ID}"
            f"&request_id={payload['request_id']}"
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
            "registry_id": "reg_case_spec_decade_camera_0055",
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
                "node_type": "proposition",
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
        ("bridge_exact_offer_condition_weather_claim", "bridge", "six frozen seller pages", "separates_literal_page_fields_from_current_condition_and_lifetime", "bind exact SKU body lens bundle region price review and weather wording while retaining conflicts and leaving current unit condition ingress protection warranty service and lifetime unresolved", "exact_offer_condition_weather_claim_scope_v1"),
        ("bridge_model_release_mount_mapping", "bridge", "three camera model pages", "maps_release_mount_form_and_shutter_without_ranking", "join bounded K3III KAF2 D7500 F-mount and 5DIV EF model context without turning age format or shutter type into exact-unit remaining life", "model_release_mount_mapping_v1"),
        ("bridge_shutter_mount_wear_boundary", "bridge", "shutter and mount mechanisms", "identifies_components_without_inventing_failure_rates", "treat the focal-plane shutter and lens mount as inspection and service targets while withholding actuation survival mount tolerance and repair conclusions", "shutter_mount_wear_boundary_v1"),
        ("bridge_seal_mechanism_maintenance_boundary", "bridge", "weather claims O-rings and gaskets", "separates_generic_seal_mechanisms_from_camera_protection", "use generic compression material and operating-condition context to define seal checks without inferring exact camera seal inventory schedule condition or ingress rating", "seal_mechanism_maintenance_boundary_v1"),
        ("bridge_reliability_metric_exact_unit_boundary", "bridge", "reliability and MTBF concepts", "requires_defined_function_time_environment_population_and_failure", "keep reliability and MTBF tied to specified conditions and repairable populations rather than converting generic averages into one unit prediction", "reliability_metric_exact_unit_boundary_v1"),
        ("bridge_spare_parts_field_replaceability_boundary", "bridge", "spare-part and FRU concepts", "separates_part_existence_replaceability_authorization_and_cost", "verify current regional camera parts documentation service authorization downtime and economics instead of inferring them from generic part definitions", "spare_parts_field_replaceability_boundary_v1"),
        ("bridge_community_lifetime_service_scope", "bridge", "three community camera and parts threads", "retains_author_item_place_device_and_time_scope", "use the posts to motivate condition secondary-market and parts-channel questions while refusing survival distributions inventories camera policy or future supply conclusions", "community_lifetime_service_scope_v1"),
        ("bridge_decade_ownership_verification_trial", "bridge", "exact camera systems and the buyer's use profile", "defines_inspection_service_quote_and_reversible_trial", "verify identity condition shutter mount seals lens batteries media firmware regional service parts repair cost and actual-use function before purchase", "decade_ownership_verification_trial_v1"),
        ("bridge_ownership_cost_serviceability_matrix", "bridge", "decade ownership evidence table", "marks_each_use_condition_serviceability_and_cost_gate", "separate seller model inspection service trial and unresolved fields then include maintenance repair downtime and fallback in total ownership cost", "ownership_cost_serviceability_matrix_v1"),
        ("decision_evidence_bounded_decade_camera", "decision", "camera system for a decade ownership goal", "selects_the_lowest_total_ownership_exact_passing_system_or_reversible_fallback", "choose only an exact inspected and trialed system passing use condition compatibility maintenance regional serviceability parts and budget gates otherwise keep repair rent downscope or defer without promising decade survival", "evidence_bounded_decade_camera_decision_v1"),
    ]
    for evidence_id, node_type, subject, predicate, object_, rule_id in deterministic_nodes:
        metadata: dict[str, Any] = {"rule_id": rule_id, "topic_cluster": TOPIC}
        if node_type == "decision":
            metadata["oracle_unique_or_admissible"] = True
        nodes.append(
            {
                "evidence_id": evidence_id,
                "node_type": node_type,
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "source_url": case_source,
                "verifier": {"kind": "deterministic_rule"},
                "metadata": metadata,
            }
        )

    offer_props = [
        "prop_pentax_k30_seller_scope",
        "prop_pentax_k3iii_seller_scope",
        "prop_pentax_k1ii_seller_scope",
        "prop_nikon_d7500_seller_scope",
        "prop_canon_5div_seller_scope",
        "prop_rokinon_weather_lens_scope",
    ]
    model_props = [
        "prop_pentax_k3iii_model_scope",
        "prop_nikon_d7500_model_scope",
        "prop_canon_5div_model_scope",
    ]
    derives = {
        "bridge_exact_offer_condition_weather_claim": offer_props,
        "bridge_model_release_mount_mapping": model_props + offer_props,
        "bridge_shutter_mount_wear_boundary": [
            "prop_pentax_k3iii_model_scope",
            "prop_nikon_d7500_model_scope",
            "prop_canon_5div_model_scope",
            "prop_focal_plane_shutter_mechanism_scope",
            "prop_lens_mount_interface_scope",
        ],
        "bridge_seal_mechanism_maintenance_boundary": [
            "prop_pentax_k30_seller_scope",
            "prop_pentax_k3iii_seller_scope",
            "prop_pentax_k1ii_seller_scope",
            "prop_nikon_d7500_seller_scope",
            "prop_rokinon_weather_lens_scope",
            "prop_o_ring_seal_scope",
            "prop_gasket_seal_scope",
        ],
        "bridge_reliability_metric_exact_unit_boundary": [
            "prop_reliability_probability_scope",
            "prop_mtbf_repairable_average_scope",
            "bridge_shutter_mount_wear_boundary",
            "bridge_seal_mechanism_maintenance_boundary",
        ],
        "bridge_spare_parts_field_replaceability_boundary": [
            "prop_spare_part_scope",
            "prop_fru_scope",
            "bridge_shutter_mount_wear_boundary",
            "bridge_seal_mechanism_maintenance_boundary",
        ],
        "bridge_community_lifetime_service_scope": [
            "prop_old_camera_donation_anecdote_scope",
            "prop_vintage_lens_availability_question_scope",
            "prop_laptop_parts_anecdote_scope",
        ],
        "bridge_decade_ownership_verification_trial": [
            "bridge_exact_offer_condition_weather_claim",
            "bridge_model_release_mount_mapping",
            "bridge_shutter_mount_wear_boundary",
            "bridge_seal_mechanism_maintenance_boundary",
            "bridge_reliability_metric_exact_unit_boundary",
            "bridge_spare_parts_field_replaceability_boundary",
            "bridge_community_lifetime_service_scope",
        ],
        "bridge_ownership_cost_serviceability_matrix": [
            "bridge_exact_offer_condition_weather_claim",
            "bridge_model_release_mount_mapping",
            "bridge_shutter_mount_wear_boundary",
            "bridge_seal_mechanism_maintenance_boundary",
            "bridge_reliability_metric_exact_unit_boundary",
            "bridge_spare_parts_field_replaceability_boundary",
            "bridge_community_lifetime_service_scope",
            "bridge_decade_ownership_verification_trial",
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
                "source_id": "decision_evidence_bounded_decade_camera",
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
