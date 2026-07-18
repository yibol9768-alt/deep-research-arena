#!/usr/bin/env python3
"""Build the frozen Q52 first-camera evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = "dra-v3-formal-cameras-photo-0052-first-camera-sensor-age-boundary-20260716-r1"
RUN_ID = "v3-corpus-formal-cameras-photo-0052-first-camera-sensor-age-boundary-20260716-r1"
CAPTURE_REL = Path("data/evidence_graph/captures") / RUN_ID
CAPTURE = ROOT / CAPTURE_REL
TASK_ID = "dra_v3_formal_cameras_photo_0052"
TOPIC = "first_dedicated_camera_indoor_sports_sensor_age_system_boundary"
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0052/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")


SEARCHES = [
    ("olympus_offer", "001-shopping-olympus-em1-body.json", "Olympus E-M1 body offer", "http://localhost:7770/olympus-om-d-e-m1-16mp-mirrorless-digital-camera-with-3-inch-lcd-body-only-silver-w-black-trim.html"),
    ("zs70_offer", "002-shopping-panasonic-zs70-fixed-zoom.json", "Panasonic ZS70 bundle offer", "http://localhost:7770/panasonic-lumix-dc-zs70s-20-3-megapixel-4k-digital-camera-touch-enabled-3-inch-180-degree-flip-front-display-30x-zoom-silver-bag-extra-battery-charger-32gb-sd-card-pc-software-kit-tripod.html"),
    ("lx10_offer", "003-shopping-panasonic-lx10-one-inch.json", "Panasonic LX10 bundle offer", "http://localhost:7770/panasonic-lumix-dmc-lx10-4k-digital-point-and-shoot-camera-20-1-megapixel-1-inch-sensor-bundle-with-camera-bag-32gb-sd-card-sd-card-case-pc-software-kit-cleaning-kit.html"),
    ("canon_offer", "004-shopping-canon-80d-aps-c-body.json", "Canon 80D body offer", "http://localhost:7770/canon-digital-slr-camera-body-eos-80d-with-24-2-megapixel-aps-c-cmos-sensor-and-dual-pixel-cmos-af-black.html"),
    ("mft_lens_offer", "005-shopping-panasonic-fast-mft-telephoto.json", "Panasonic fast Micro Four Thirds lens offer", "http://localhost:7770/panasonic-h-hsa35100-f2-8-ii-asph-35-100mm-mirrorless-micro-four-thirds-mount-power-optical-i-s-lumix-g-x-vario-professional-lens.html"),
    ("canon_lens_offer", "006-shopping-sigma-fast-canon-telephoto.json", "Sigma fast Canon lens offer", "http://localhost:7770/sigma-50-100mm-f1-8-art-dc-hsm-lens-for-canon-dslr-cameras-sigma-usb-dock-with-altura-photo-essential-accessory-and-travel-bundle.html"),
    ("olympus_model", "007-wiki-olympus-em1-model.json", "Olympus E-M1 model facts", "http://localhost:8090/content/wikipedia_en_all_nopic/Olympus_OM-D_E-M1"),
    ("lx10_model", "008-wiki-panasonic-lx10-model.json", "Panasonic LX10 model facts", "http://localhost:8090/content/wikipedia_en_all_nopic/Panasonic_Lumix_DMC-LX10"),
    ("canon_model", "009-wiki-canon-80d-model.json", "Canon 80D model facts", "http://localhost:8090/content/wikipedia_en_all_nopic/Canon_EOS_80D"),
    ("zs70_model", "010-wiki-superzoom-compact-list.json", "Panasonic ZS70 superzoom row", "http://localhost:8090/content/wikipedia_en_all_nopic/List_of_superzoom_compact_cameras"),
    ("sensor_format", "011-wiki-image-sensor-format.json", "image-sensor-format concept", "http://localhost:8090/content/wikipedia_en_all_nopic/Image_sensor_format"),
    ("f_number", "012-wiki-f-number-light-gathering.json", "f-number light-gathering concept", "http://localhost:8090/content/wikipedia_en_all_nopic/F-number"),
    ("shutter_speed", "013-wiki-shutter-speed-exposure.json", "shutter-speed exposure concept", "http://localhost:8090/content/wikipedia_en_all_nopic/Shutter_speed"),
    ("motion_blur", "014-wiki-motion-blur-exposure.json", "motion-blur mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Motion_blur_(media)"),
    ("image_noise", "015-wiki-image-noise.json", "image-noise mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Image_noise"),
    ("autofocus", "016-wiki-autofocus.json", "autofocus mechanism", "http://localhost:8090/content/wikipedia_en_all_nopic/Autofocus"),
    ("sports_photo", "017-wiki-sports-photography-equipment.json", "sports-photography equipment context", "http://localhost:8090/content/wikipedia_en_all_nopic/Sports_photography"),
    ("settings_post", "018-forum-camera-settings-dataset.json", "one camera-settings question", "http://localhost:9999/f/MachineLearning/34807/d-camera-settings-for-dataset-collection"),
    ("iphone_compare", "019-forum-iphone-dedicated-camera-comparison.json", "one phone-versus-camera report", "http://localhost:9999/f/iphone/62271/defective-iphone-14-camera"),
    ("iphone_noise", "020-forum-iphone-noise-focus-complaint.json", "one phone noise-and-focus report", "http://localhost:9999/f/iphone/20396/iphone-14-pro-camera-quality"),
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
        "prop_olympus_seller_body_scope",
        "frozen Olympus E-M1 seller page",
        "shows_a_body_only_titled_offer",
        "SKU B00NGSLTBC at 668 dollars with a 93-percent rating over twelve reviews and body-only wording",
        0,
        "product",
        "frozen_seller_identity_price_and_style_not_current_complete_system_or_test",
        [
            "Olympus OM-D E-M1 16MP Mirrorless Digital Camera with 3-Inch LCD (Body Only) (Silver w/ Black Trim)",
            "In stock SKU B00NGSLTBC Rating: 93 % of 100 12 Reviews Add Your Review $668.00 Color Black Silver (Black Trim) Style Body Only w/ 12-40mm PRO Lens Qty Add to Cart Add to Wish List Add to Compare",
        ],
        "The frozen Olympus page titles the E-M1 offer as body only and shows SKU B00NGSLTBC at 668 dollars with a 93-percent rating over twelve reviews while also displaying style options. It does not verify a current delivered offer, selected lens, used condition, shutter count, battery health, warranty, return terms, or indoor-volleyball performance.",
    ),
    ev(
        "prop_zs70_seller_bundle_scope",
        "frozen Panasonic ZS70 seller page",
        "shows_a_fixed_zoom_bundle_offer",
        "SKU B07VNKKKSB at 379.08 dollars rated 95 percent over four reviews with 20.3-megapixel and 30x lens claims",
        1,
        "product",
        "frozen_seller_bundle_and_marketing_not_current_offer_or_independent_sports_test",
        [
            "Panasonic LUMIX DC-ZS70S, 20.3 Megapixel, 4K Digital Camera, Touch Enabled 3-inch 180 Degree Flip-Front Display, 30X Zoom (Silver), Bag, Extra Battery-Charger, 32GB SD Card, PC Software Kit, Tripod",
            "In stock SKU B07VNKKKSB Rating: 95 % of 100 4 Reviews Add Your Review $379.08",
            "20.3 Megapixel MOS sensor plus 30X LEICA DC VARIO-ELMAR Lens (24-720mm), plus 5-axis HYBRID O.I.S. (Optical Image Stabilizer)",
        ],
        "The frozen ZS70 page shows SKU B07VNKKKSB at 379.08 dollars, rated 95 percent over four reviews, and describes a bundle plus a 20.3-megapixel sensor, 30x 24-720mm lens and stabilization. Those are seller assertions, not a current delivered offer, independent indoor-sports test, proof of subject-motion freezing, or proof that every named accessory is suitable.",
    ),
    ev(
        "prop_lx10_seller_bundle_scope",
        "frozen Panasonic LX10 seller page",
        "shows_a_one_inch_fixed_lens_bundle_offer",
        "SKU B01NGYHJOQ at 514.87 dollars rated 80 percent over four reviews with a one-inch 20.1-megapixel title and 24-72mm f/1.4-f/2.8 lens claim",
        2,
        "product",
        "frozen_seller_bundle_and_low_light_copy_not_reach_tracking_or_keeper_rate_proof",
        [
            "Panasonic Lumix DMC-LX10 4K Digital Point and Shoot Camera, 20.1 Megapixel 1-inch Sensor Bundle with Camera Bag, 32GB SD Card, SD Card Case, PC Software Kit, Cleaning Kit",
            "In stock SKU B01NGYHJOQ Rating: 80 % of 100 4 Reviews Add Your Review $514.87",
            "3x (24-72mm) F/1.4-2.8 LEICA DC VARIO-SUMMILUX Optical Zoom Lens",
        ],
        "The frozen LX10 page shows SKU B01NGYHJOQ at 514.87 dollars, rated 80 percent over four reviews, and titles a one-inch 20.1-megapixel bundle while claiming a fixed 24-72mm-equivalent f/1.4-f/2.8 lens. It does not prove adequate reach, autofocus tracking, burst endurance, current delivered contents, or keeper rate from the buyer's volleyball position.",
    ),
    ev(
        "prop_canon_80d_seller_body_scope",
        "frozen Canon 80D seller page",
        "shows_an_aps_c_body_offer_and_feature_claims",
        "SKU B01BUYK04A at 798 dollars with no reviews shown, body-only style, APS-C title and a seller claim of up to 7 fps",
        3,
        "product",
        "frozen_seller_body_and_feature_claims_not_complete_budget_or_field_test",
        [
            "Canon Digital SLR Camera Body [EOS 80D] with 24.2 Megapixel (APS-C) CMOS Sensor and Dual Pixel CMOS AF - Black",
            "In stock SKU B01BUYK04A Be the first to review this product $798.00 Style Body Only Storage Bundle Qty Add to Cart Add to Wish List Add to Compare",
            "The EOS 80D shoots up to 7.0 fps during continuous shooting, making it great for quick action shots.",
        ],
        "The frozen Canon page titles a 24.2-megapixel APS-C EOS 80D body and shows SKU B01BUYK04A at 798 dollars with no reviews shown and body-only style, while the seller says it shoots up to 7 fps. The page price already exceeds the 700-dollar anchor before a lens, and none of these fields independently verifies current cost, compatibility, buffer behavior or gym performance.",
    ),
    ev(
        "prop_panasonic_mft_lens_scope",
        "frozen Panasonic 35-100mm lens page",
        "shows_a_fast_micro_four_thirds_lens_offer",
        "SKU B01MU3WOVP at 897.99 dollars with no reviews shown for a 35-100mm f/2.8 Micro Four Thirds lens",
        4,
        "product",
        "frozen_mount_focal_aperture_and_price_claims_not_required_lens_or_test",
        [
            "Panasonic H-HSA35100 F2.8 II ASPH 35-100mm Mirrorless Micro Four Thirds Mount POWER Optical I.S. LUMIX G X VARIO Professional Lens",
            "In stock SKU B01MU3WOVP Be the first to review this product $897.99",
            "35-100mm / F2.8 Telephoto Brilliance",
        ],
        "The frozen Panasonic lens page shows SKU B01MU3WOVP at 897.99 dollars with no reviews shown and explicitly identifies a 35-100mm f/2.8 Micro Four Thirds lens. It demonstrates that a compatible fast telephoto can dominate total system cost, but it does not prove this exact lens is required, currently offered, condition-matched, or successful in the buyer's gym.",
    ),
    ev(
        "prop_sigma_canon_lens_scope",
        "frozen Sigma 50-100mm lens page",
        "shows_a_fast_canon_aps_c_lens_offer",
        "SKU B076H8BGTB at 999 dollars rated 87 percent over twelve reviews with f/1.8 and explicit Canon 80D compatibility copy",
        5,
        "product",
        "frozen_mount_compatibility_price_and_feature_copy_not_required_lens_or_performance_test",
        [
            "Sigma 50-100mm F1.8 Art DC HSM Lens for Canon DSLR Cameras + Sigma USB Dock with Altura Photo Essential Accessory and Travel Bundle",
            "In stock SKU B076H8BGTB Rating: 87 % of 100 12 Reviews Add Your Review $999.00",
            "COMPATIBLE with APS-C DSLR Canon Cameras, including EOS 7D Mark II, 70D, 77D, 80D, 90D and Rebel T3, T3i, T4i, T5, T5i, T6, T6i, T6s, T7, T7i, T8i, SL1, SL2 and SL3.",
        ],
        "The frozen Sigma page shows SKU B076H8BGTB at 999 dollars, rated 87 percent over twelve reviews, for a 50-100mm f/1.8 Canon DSLR bundle and explicitly lists the 80D as compatible. This is seller compatibility and price copy, not proof that the lens is necessary, currently available, within budget, easy to handle, or independently superior in the gym.",
    ),
    ev(
        "prop_olympus_model_scope",
        "Olympus E-M1 model page",
        "maps_release_sensor_mount_and_burst_fields",
        "a 2013 Micro Four Thirds interchangeable-lens model with a Four Thirds sensor and listed continuous-autofocus burst behavior",
        6,
        "concept",
        "frozen_model_mapping_not_exact_unit_condition_or_same_gym_result",
        [
            "The Olympus OM-D E-M1 Micro Four Thirds is a compact mirrorless interchangeable-lens camera introduced on September 10, 2013.",
            "Buffer for 40 raw images at 10 frames per second with focus locked or 45 raw images at 6 frame per second with continuous autofocus.",
        ],
        "The Olympus model page identifies the E-M1 as a compact Micro Four Thirds interchangeable-lens camera introduced in 2013 and lists distinct burst behavior with focus locked and continuous autofocus. It does not identify the seller unit's condition, firmware, compatible lens, battery, buffer under the buyer's settings, or same-gym keeper rate.",
    ),
    ev(
        "prop_lx10_model_scope",
        "Panasonic LX10 model page",
        "maps_release_sensor_and_fixed_lens_fields",
        "a 2016 fixed-lens model with a 13.2 by 8.8mm sensor and 24-72mm-equivalent f/1.4-f/2.8 lens",
        7,
        "concept",
        "frozen_model_mapping_not_exact_offer_or_indoor_sports_result",
        [
            "Panasonic Lumix DMC-LX10 Overview Maker Panasonic Type Large sensor fixed-lens camera Released September 19, 2016 Intro price 699$ Lens Lens 24-72mm equivalent F-numbers f/1.4-f/2.8 at the widest Sensor/medium Sensor type BSI-CMOS Sensor size 13.2 x 8.8mm",
            "The LX10 is more compact than the Panasonic LX100 or GX8 series by not having an electronic viewfinder, interchangeable lenses, or hot shoe.",
        ],
        "The LX10 model page places the camera in 2016 and identifies a fixed 24-72mm-equivalent f/1.4-f/2.8 lens, 13.2 by 8.8mm sensor, and no interchangeable lens, electronic viewfinder or hot shoe. These model fields do not prove adequate volleyball reach, tracking, buffer, exact bundle identity or same-gym output quality.",
    ),
    ev(
        "prop_canon_80d_model_scope",
        "Canon 80D model page",
        "maps_release_and_interchangeable_lens_forms",
        "a 2016 DSLR sold in body-only and multiple kit forms",
        8,
        "concept",
        "frozen_model_mapping_not_exact_offer_unit_condition_or_keeper_rate",
        [
            "The Canon EOS 80D is a digital single-lens reflex camera announced by Canon on February 18, 2016.",
            "The camera can be purchased as a body-only, as kit with the 18-55mm IS STM lens, with the new 18-135mm IS USM lens or with the EF-S 18-200mm IS .",
        ],
        "The Canon model page identifies the EOS 80D as a DSLR announced in 2016 and distinguishes body-only from several lens-kit forms. This supports keeping exact bundle and lens identity explicit, but it does not verify the seller page's current offer, unit condition, exact compatible sports lens, total cost or gym result.",
    ),
    ev(
        "prop_zs70_model_scope",
        "superzoom compact model table",
        "maps_zs70_sensor_zoom_aperture_and_release_fields",
        "the ZS70 row is a 2017 1/2.3-type 30x compact with 24-720mm-equivalent f/3.3-f/6.4 optics",
        9,
        "concept",
        "frozen_table_mapping_not_current_status_exact_offer_or_sports_performance",
        [
            "Each of the following models contains a 1/2.3-type (\"1/2.3-inch\") image sensor with a crop factor of 5.6.",
            "Panasonic ZS70 [ f ] 1/2.3-type",
            "720mm f / 3.3 f / 6.4 20 MP 322g Yes 2017 Discontinued [ 20 ]",
        ],
        "The superzoom table places the Panasonic ZS70 among 1/2.3-type small-sensor compacts and lists 30x, 24-720mm-equivalent f/3.3-f/6.4 optics and a 2017 release row. This is model-table context, not proof of current discontinuation status, exact seller bundle identity, usable indoor aperture at the needed framing, tracking or keeper rate.",
    ),
    ev(
        "prop_sensor_format_scope",
        "image-sensor-format concept",
        "relates_sensor_shape_and_size_to_angle_of_view",
        "sensor format is the sensor's shape and size and affects a lens's angle of view",
        10,
        "concept",
        "general_optical_context_not_universal_quality_rank_or_model_test",
        [
            "In digital photography, the image sensor format is the shape and size of the image sensor .",
            "The image sensor format of a digital camera determines the angle of view of a particular lens when used with a particular sensor.",
        ],
        "The sensor-format page defines image sensor format as sensor shape and size and says it determines the angle of view of a particular lens with a particular sensor. It does not reduce sensor comparisons to a universal quality ranking or establish reach, exposure, autofocus, noise or keeper rate for the captured cameras.",
    ),
    ev(
        "prop_f_number_scope",
        "f-number concept",
        "relates_relative_aperture_to_entering_light",
        "a lower f-number means a larger relative aperture and more entering light",
        11,
        "concept",
        "general_aperture_mechanism_not_exact_lens_transmission_focus_or_field_result",
        [
            "An f-number is a measure of the light-gathering ability of an optical system such as a camera lens .",
            "A lower f-number means a larger relative aperture and more light entering the system, while a higher f-number means a smaller relative aperture and less light entering the system.",
        ],
        "The f-number page describes f-number as a light-gathering measure and states that a lower f-number means a larger relative aperture and more entering light. This general relation does not verify exact transmission, depth-of-field acceptability, focusing behavior, tele-end aperture or volleyball results for any seller page.",
    ),
    ev(
        "prop_shutter_speed_scope",
        "shutter-speed concept",
        "defines_exposure_time_and_light_proportionality",
        "shutter speed is exposure time and reaching light is proportional to that time",
        12,
        "concept",
        "general_exposure_relation_not_exact_motion_freeze_threshold_or_camera_result",
        [
            "In photography , shutter speed or exposure time is the length of time that the film or digital sensor inside the camera is exposed to light (that is, when the camera 's shutter is open) when taking a photograph.",
            "The amount of light that reaches the film or image sensor is proportional to the exposure time.",
        ],
        "The shutter-speed page defines shutter speed as exposure time and says the amount of reaching light is proportional to that time. Shortening exposure can help control motion blur but admits less light; the page does not supply one universal volleyball shutter threshold or a result for any captured camera.",
    ),
    ev(
        "prop_motion_blur_scope",
        "motion-blur concept",
        "links_streaking_to_scene_change_during_exposure",
        "moving objects can streak when the recorded image changes during one exposure because of rapid movement or long exposure",
        13,
        "concept",
        "general_motion_mechanism_not_exact_subject_speed_setting_or_model_test",
        [
            "Motion blur is the apparent streaking of moving objects in a photograph or a sequence of frames, such as a film or animation .",
            "It results when the image being recorded changes during the recording of a single exposure, due to rapid movement or long exposure .",
        ],
        "The motion-blur page explains that apparent streaking occurs when the recorded image changes during a single exposure because of rapid movement or long exposure. It supports testing exposure time against the actual volleyball action, but supplies no exact player speed, camera setting, lens, stabilization effect or model winner.",
    ),
    ev(
        "prop_image_noise_scope",
        "image-noise concept",
        "defines_noise_and_low_light_exposure_tradeoffs",
        "noise is random brightness or color variation and low-light capture trades shutter time aperture and gain",
        14,
        "concept",
        "general_noise_mechanism_not_same_output_model_ranking",
        [
            "Image noise is random variation of brightness or color information in images .",
            "In digital cameras In low light, correct exposure requires the use of slow shutter speed (i.e. long exposure time) or an opened aperture (lower f-number ), or both, to increase the amount of light (photons) captured which in turn reduces the impact of shot noise.",
        ],
        "The image-noise page defines random brightness or color variation and describes low-light tradeoffs among longer exposure, wider aperture and gain after practical limits. It does not prove a universal ISO ranking, equal processing, same output size, or an exact noise and detail result for any candidate camera.",
    ),
    ev(
        "prop_autofocus_scope",
        "autofocus concept",
        "defines_focus_control_and_moving_subject_tracking",
        "autofocus uses sensing control and a motor, and some systems keep focus as a subject moves",
        15,
        "concept",
        "general_af_mechanism_not_tracking_accuracy_or_model_comparison",
        [
            "An autofocus ( AF ) optical system uses a sensor , a control system and a motor to focus on an automatically or manually selected point or area.",
            "Some AF cameras are able to detect whether the subject is moving towards or away from the camera, including speed and acceleration, and keep focus",
        ],
        "The autofocus page says an AF optical system uses a sensor, control system and motor to focus a selected point or area and that some systems can keep focus as a subject moves. This general mechanism does not establish tracking acquisition, retention, lens-drive behavior, low-light accuracy or keeper rate for any captured model.",
    ),
    ev(
        "prop_sports_photography_scope",
        "sports-photography equipment page",
        "lists_joint_camera_lens_focus_burst_and_exposure_demands",
        "sports work commonly uses high continuous speeds, suitable focal lengths, fast autofocus, wide apertures and motion-aware shutter choices",
        16,
        "concept",
        "general_genre_context_not_mandatory_gear_or_exact_volleyball_result",
        [
            "Equipment typically used for sports photography includes a digital single-lens reflex (DSLR) camera or Mirrorless Camera with high continuous shooting speeds and interchangeable lenses ranging from 14mm to 400mm or longer in focal length , depending on the type of sport.",
            "indoor sports tend to have shorter lenses with faster apertures.",
            "Shutter speed is critical to catching motion",
        ],
        "The sports-photography page describes joint demands involving continuous shooting, lenses, autofocus, aperture and shutter choice and notes that indoor sports tend toward shorter faster lenses. It is general genre context, not a mandatory equipment list or a controlled test of the four candidate cameras in this volleyball gym.",
    ),
    ev(
        "prop_camera_settings_anecdote_scope",
        "camera-settings forum question",
        "asks_about_iso_aperture_exposure_and_dark_condition_noise",
        "one author asks how settings affect a dataset and mentions high ISO and noise in dark capture",
        17,
        "community",
        "single_author_question_not_authoritative_setting_or_camera_result",
        [
            "How much does it matter what settings (iso, f, exposure time) are used in datasets?",
            "Of course there are some specific cases, like imaging in dark conditions where the iso obviously needs to be large and the noise has to be handled.",
        ],
        "One forum author asks how ISO, f-number and exposure time affect datasets and mentions high ISO and noise in dark conditions. This can motivate recording settings and noise but is a question, not an authoritative exposure rule, controlled test, or result for the buyer's phone, gym or camera candidates.",
    ),
    ev(
        "prop_iphone_dedicated_anecdote_scope",
        "phone-versus-dedicated-camera forum report",
        "reports_one_oversharpened_phone_sample",
        "one author compares an iPhone 14 Pro sample with a Sony A7III and 24-105 f/4 and reports oversharpening",
        18,
        "community",
        "single_author_unmatched_sample_not_phone_or_dedicated_camera_benchmark",
        [
            "The photo taken by my iPhone 14 Pro looks over-sharpened mess and compared to the one taken with Sony A7III with 24-105 F4 lens.",
            "I have have been hearing how smartphone cameras can now rival dedicated camera in good lighting conditions. It doesn't look the case to me.",
        ],
        "One iPhone author reports an oversharpened iPhone 14 Pro sample compared with a Sony A7III and 24-105 f/4 and rejects a broad good-light parity claim for that experience. The post is not a matched exposure, lens, framing, processing or output-size test and cannot rank phones or dedicated cameras generally.",
    ),
    ev(
        "prop_iphone_noise_focus_anecdote_scope",
        "phone noise-and-focus forum report",
        "reports_one_devices_noise_focus_and_file_size_complaints",
        "one author reports noise, intermittent focus and smaller files relative to an Android phone",
        19,
        "community",
        "single_author_device_report_not_controlled_quality_or_camera_category_result",
        [
            "Makes noise while in use, lacks focus at times",
            "my android takes 8-9 mb on standard and they are much better",
        ],
        "One iPhone author reports noise, intermittent focus and smaller standard-photo files relative to an Android phone. The post identifies no controlled settings, action, output normalization or verified defect, so it motivates separate focus and noise checks but cannot establish phone-category performance or a dedicated-camera winner.",
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
            "registry_id": "reg_case_spec_first_camera_0052",
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
        ("bridge_frozen_offer_identity_budget", "bridge", "four frozen camera offers", "separates_literal_offer_fields_from_current_complete_systems", "bind exact SKU model body or fixed-lens form bundle and frozen price while leaving current condition delivered contents warranty return and total cost unresolved", "frozen_offer_identity_budget_scope_v1"),
        ("bridge_model_release_sensor_mapping", "bridge", "camera model and sensor records", "maps_release_format_and_lens_form_without_ranking", "join the 2013 E-M1 Four Thirds interchangeable system the 2016 LX10 fixed one-inch-class system the 2016 Canon 80D DSLR and the 2017 ZS70 small-sensor fixed superzoom without turning age or format into a winner", "model_release_sensor_mapping_v1"),
        ("bridge_lens_mount_total_system_cost", "bridge", "body lens mount reach aperture and budget", "requires_a_compatible_complete_system_cost", "keep body-only and fixed-lens offers separate and add exact compatible lens and accessory costs before testing the 700-dollar ceiling", "lens_mount_total_system_cost_boundary_v1"),
        ("bridge_exposure_motion_noise_tradeoff", "bridge", "sensor aperture shutter motion and noise evidence", "requires_a_joint_low_light_motion_analysis", "treat motion freezing light gathering gain noise field of view and output normalization as linked variables rather than a one-variable sensor-size or stabilization conclusion", "exposure_motion_noise_tradeoff_v1"),
        ("bridge_autofocus_burst_sports_scope", "bridge", "autofocus burst lens and sports context", "requires_matched_action_specific_validation", "use generic sports requirements and model claims to choose tests while withholding tracking buffer flicker and keeper-rate conclusions until same-gym observation", "autofocus_burst_sports_scope_v1"),
        ("bridge_community_phone_settings_scope", "bridge", "three community camera posts", "retains_author_device_sample_and_question_scope", "use the posts to motivate separate settings noise focus and processing checks while refusing phone-category dedicated-camera or universal quality conclusions", "community_phone_settings_scope_v1"),
        ("bridge_same_gym_matched_trial_protocol", "bridge", "exact candidate systems and the buyer's volleyball use", "defines_a_repeated_field_side_comparison", "verify identity condition compatibility and total cost then compare same gym position action and output size with separate motion focus noise detail keeper handling and cost outcomes", "same_gym_matched_trial_protocol_v1"),
        ("bridge_first_camera_decision_preparation", "bridge", "first dedicated camera evidence table", "marks_every_complete_system_gate_pass_fail_or_unresolved", "separate seller claims model facts condition compatibility field outcomes and cost while preventing release sensor megapixels zoom ratings or anecdotes from overriding failed gates", "first_camera_decision_preparation_v1"),
        ("decision_first_camera_pass_fail", "decision", "first dedicated camera for indoor volleyball", "selects_the_lowest_total_cost_exact_passing_system_or_a_reversible_fallback", "choose only the lowest total-cost exact system passing identity condition compatibility reach aperture autofocus burst same-gym output handling and budget gates otherwise rent borrow test keep the phone save or defer", "first_camera_pass_fail_decision_v1"),
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
        "prop_olympus_seller_body_scope",
        "prop_zs70_seller_bundle_scope",
        "prop_lx10_seller_bundle_scope",
        "prop_canon_80d_seller_body_scope",
    ]
    model_props = [
        "prop_olympus_model_scope",
        "prop_lx10_model_scope",
        "prop_canon_80d_model_scope",
        "prop_zs70_model_scope",
        "prop_sensor_format_scope",
    ]
    derives = {
        "bridge_frozen_offer_identity_budget": offer_props,
        "bridge_model_release_sensor_mapping": offer_props + model_props,
        "bridge_lens_mount_total_system_cost": [
            "prop_olympus_seller_body_scope",
            "prop_canon_80d_seller_body_scope",
            "prop_panasonic_mft_lens_scope",
            "prop_sigma_canon_lens_scope",
            "bridge_model_release_sensor_mapping",
        ],
        "bridge_exposure_motion_noise_tradeoff": [
            "prop_sensor_format_scope",
            "prop_f_number_scope",
            "prop_shutter_speed_scope",
            "prop_motion_blur_scope",
            "prop_image_noise_scope",
        ],
        "bridge_autofocus_burst_sports_scope": [
            "prop_canon_80d_seller_body_scope",
            "prop_olympus_model_scope",
            "prop_lx10_model_scope",
            "prop_canon_80d_model_scope",
            "prop_zs70_model_scope",
            "prop_autofocus_scope",
            "prop_sports_photography_scope",
        ],
        "bridge_community_phone_settings_scope": [
            "prop_camera_settings_anecdote_scope",
            "prop_iphone_dedicated_anecdote_scope",
            "prop_iphone_noise_focus_anecdote_scope",
        ],
        "bridge_same_gym_matched_trial_protocol": [
            "bridge_model_release_sensor_mapping",
            "bridge_lens_mount_total_system_cost",
            "bridge_exposure_motion_noise_tradeoff",
            "bridge_autofocus_burst_sports_scope",
            "bridge_community_phone_settings_scope",
        ],
        "bridge_first_camera_decision_preparation": [
            "bridge_frozen_offer_identity_budget",
            "bridge_model_release_sensor_mapping",
            "bridge_lens_mount_total_system_cost",
            "bridge_exposure_motion_noise_tradeoff",
            "bridge_autofocus_burst_sports_scope",
            "bridge_community_phone_settings_scope",
            "bridge_same_gym_matched_trial_protocol",
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
                "source_id": "decision_first_camera_pass_fail",
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
