#!/usr/bin/env python3
"""Build the frozen Q57 old-body generation-gain inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-cameras-photo-0057-old-body-generation-gain-"
    "boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0057/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = (
    "dra-v3-formal-cameras-photo-0057-old-body-generation-gain-"
    "boundary-20260716-r1"
)
RUN_ID = (
    "v3-corpus-formal-cameras-photo-0057-old-body-generation-gain-"
    "boundary-20260716-r1"
)
TASK_ID = "dra_v3_formal_cameras_photo_0057"
TOPIC = "old_body_generation_gain_boundary"


SEARCHES = [
    (
        "nikon_d7000_offer",
        "001-shopping-nikon-d7000-renewed.json",
        "Nikon D7000 renewed kit seller snapshot",
        "http://localhost:7770/nikon-d7000-16-2-megapixel-digital-slr-camera-with-18-105mm-lens-black-renewed.html",
    ),
    (
        "canon_7d_offer",
        "002-shopping-canon-eos-7d-kit.json",
        "Canon EOS 7D 18-135mm kit seller snapshot",
        "http://localhost:7770/canon-eos-7d-digital-camera-with-18-135mm-f-3-5-5-6-is-lens-kit.html",
    ),
    (
        "sony_a300_offer",
        "003-shopping-sony-a300-body.json",
        "Sony A300 stabilized body seller snapshot",
        "http://localhost:7770/sony-alpha-dslr-a300-10-2mp-digital-slr-camera-with-super-steadyshot-image-stabilization-body.html",
    ),
    (
        "sony_a7iii_offer",
        "004-shopping-sony-a7iii-body-bundle.json",
        "Sony a7 III body and accessory bundle seller snapshot",
        "http://localhost:7770/sony-alpha-a7-iii-mirrorless-digital-camera-body-only-ilce7m3-b-bundle-with-telephoto-and-wide-angle-lens-set-128gb-memory-card-microphone-ttl-flash-camera-bag-and-accessories.html",
    ),
    (
        "nikon_z6_offer",
        "005-shopping-nikon-z6-body-bundle.json",
        "Nikon Z6 body, FTZ and storage bundle seller snapshot",
        "http://localhost:7770/nikon-z6-mirrorless-digital-camera-24-5mp-body-only-ftz-mount-adapter-64gb-g-series-xqd-memory-card-accessory-bundle-20-pieces.html",
    ),
    (
        "canon_eos_r_offer",
        "006-shopping-canon-eos-r-body-bundle.json",
        "Canon EOS R body, adapter and storage bundle seller snapshot",
        "http://localhost:7770/canon-eos-r-mirrorless-digital-camera-body-only-mount-adapter-128gb-memory-card.html",
    ),
    (
        "nikon_d7000_model",
        "007-wiki-nikon-d7000.json",
        "Nikon D7000 release generation and feature page",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Nikon_D7000",
    ),
    (
        "canon_7d_model",
        "008-wiki-canon-eos-7d.json",
        "Canon EOS 7D release generation and feature page",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Canon_EOS_7D",
    ),
    (
        "sony_a7iii_model",
        "009-wiki-sony-a7iii.json",
        "Sony a7 III release generation and feature page",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Sony_%CE%B17_III",
    ),
    (
        "nikon_z6_model",
        "010-wiki-nikon-z6.json",
        "Nikon Z6 release generation and feature page",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Nikon_Z6",
    ),
    (
        "canon_eos_r_model",
        "011-wiki-canon-eos-r.json",
        "Canon EOS R release generation and feature page",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Canon_EOS_R",
    ),
    (
        "bsi_mechanism",
        "012-wiki-back-illuminated-sensor.json",
        "back-illuminated sensor mechanism and chronology",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Back-illuminated_sensor",
    ),
    (
        "active_pixel_mechanism",
        "013-wiki-active-pixel-sensor.json",
        "active-pixel CMOS development and readout boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Active-pixel_sensor",
    ),
    (
        "stabilization_mechanism",
        "014-wiki-image-stabilization.json",
        "camera-shake stabilization and subject-motion boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Image_stabilization",
    ),
    (
        "evf_mechanism",
        "015-wiki-electronic-viewfinder.json",
        "electronic viewfinder preview and latency boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Electronic_viewfinder",
    ),
    (
        "rolling_shutter_mechanism",
        "016-wiki-rolling-shutter.json",
        "rolling readout and motion-distortion boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Rolling_shutter",
    ),
    (
        "dynamic_range_mechanism",
        "017-wiki-dynamic-range.json",
        "photographic dynamic-range and noise boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Dynamic_range",
    ),
    (
        "forum_used_body_debate",
        "018-forum-used-old-body-debate.json",
        "community used-prosumer value and defect-risk debate",
        "http://localhost:9999/f/gadgets/61300/canon-develops-new-19mp-full-frame-global-shutter-sensor",
    ),
    (
        "forum_same_gear_progress",
        "019-forum-same-telescope-progress.json",
        "community progress with retained core gear and changed workflow",
        "http://localhost:9999/f/space/112972/my-two-year-progress-shooting-jupiter-using-the-same-300",
    ),
    (
        "forum_close_focus_regression",
        "020-forum-new-camera-close-focus-regression.json",
        "community newer-device close-focus regression report",
        "http://localhost:9999/f/iphone/84591/14-plus-cannot-take-photos-close-up-expected-similar-quality",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_d7000_renewed_offer_scope",
        "subject": "frozen Nikon D7000 renewed-kit seller page",
        "predicate": "shows_a_renewed_older_dslr_kit_with_seller_specs",
        "object": "SKU B08QJQF76H at 799 dollars with no posted review, renewed condition wording, an 18-105mm lens, a 16.2MP DX CMOS claim, six-frame-per-second claim and ISO 100 to 6400 claim",
        "source_url": SEARCHES[0][3],
        "search_id": "nikon_d7000_offer",
        "role": "product",
        "scope": "frozen_seller_offer_condition_and_spec_copy_not_current_price_physical_unit_condition_or_measured_family_photo_result",
        "quotes": [
            "In stock SKU B08QJQF76H Be the first to review this product $799.00 Qty Add to Cart Add to Wish List Add to Compare",
            "This pre-owned or refurbished product has been professionally inspected and tested to work and look like new.",
            "High Resolution 16.2 MP DX-format CMOS sensor High Speed 6 frames per second continuous shooting up to 100 shots Breathtaking Full 1080p HD Movies with Full Time Autofocus Dynamic ISO range from 100 to 6400",
        ],
        "accepted": "The frozen D7000 page shows SKU B08QJQF76H at 799 dollars with no posted review, renewed inspection wording, an 18-105mm kit title and seller claims for a 16.2MP DX CMOS sensor, six frames per second and ISO 100 to 6400; it does not establish the coworker unit's identity, wear, current value or family-photo performance.",
    },
    {
        "evidence_id": "prop_canon_7d_offer_scope",
        "subject": "frozen Canon EOS 7D kit seller page",
        "predicate": "shows_an_older_dslr_kit_with_af_burst_and_durability_claims",
        "object": "SKU B002LSI1LY at 899.55 dollars, rated 100 percent over eight reviews, with an 18-135mm IS kit title, an 18MP APS-C claim, nineteen-point AF, eight frames per second and shutter durability up to 150,000 cycles",
        "source_url": SEARCHES[1][3],
        "search_id": "canon_7d_offer",
        "role": "product",
        "scope": "frozen_seller_offer_rating_and_feature_copy_not_current_offer_used_condition_or_measured_keeper_rate",
        "quotes": [
            "In stock SKU B002LSI1LY Rating: 100 % of 100 8 Reviews Add Your Review $899.55 Qty Add to Cart Add to Wish List Add to Compare",
            "The EOS 7D has a cross-type 19-point AF system with improved AI Servo AF subject tracking and user-selectable AF area selection modes for sharp focus no matter the situation.",
            "The EOS 7D features a magnesium alloy body that is dust- and weather-resistant and shutter durability of up to 150,000 cycles.",
        ],
        "accepted": "The frozen 7D page shows SKU B002LSI1LY at 899.55 dollars, rated 100 percent over eight reviews, with an 18-135mm IS kit title and seller claims for 18MP APS-C, nineteen-point AF, eight frames per second and shutter durability up to 150,000 cycles; ratings and durability copy do not reveal the tested unit's remaining life or keeper rate.",
    },
    {
        "evidence_id": "prop_sony_a300_offer_scope",
        "subject": "frozen Sony A300 body seller page",
        "predicate": "shows_an_older_body_with_sensor_shift_stabilization_and_live_view_claims",
        "object": "SKU B003J9DC72 at 337.99 dollars with no posted review, a body title, a 10.2MP APS-C CCD claim, Quick AF Live View and body-based Super SteadyShot rated by the seller at 2.5 to 3.5 shutter-speed steps",
        "source_url": SEARCHES[2][3],
        "search_id": "sony_a300_offer",
        "role": "product",
        "scope": "frozen_seller_body_and_stabilization_copy_not_complete_lens_path_current_condition_or_subject_motion_result",
        "quotes": [
            "In stock SKU B003J9DC72 Be the first to review this product $337.99 Qty Add to Cart Add to Wish List Add to Compare",
            "To aid shooting in low light, the camera incorporates Sony's Super SteadyShot image stabilization enables shutter speeds 2.5 to 3.5 steps slower than otherwise possible, and since the image stabilization system is built into the camera body, you'll be able to take advantage of the image stabilization with every compatible Minolta Maxxum and Sony ? (alpha) lens ever available.",
            "10.2 MP for high-resolution image detail APS-C CCD Image Sensor",
        ],
        "accepted": "The frozen A300 page shows SKU B003J9DC72 at 337.99 dollars with no posted review, a body configuration, a 10.2MP APS-C CCD claim, Quick AF Live View and a seller claim of 2.5 to 3.5 slower shutter-speed steps from body-based Super SteadyShot; it does not include a task lens or show that stabilization freezes subject motion.",
    },
    {
        "evidence_id": "prop_sony_a7iii_offer_scope",
        "subject": "frozen Sony a7 III accessory-bundle seller page",
        "predicate": "shows_a_2018_generation_mirrorless_body_bundle_with_full_frame_burst_and_video_claims",
        "object": "SKU B07XDCPVSL at 1,999 dollars, rated 100 percent over two reviews, with a body-only-labeled bundle, 24.2MP full-frame claim, up to ten frames per second with AF or AE tracking and 4K HDR wording",
        "source_url": SEARCHES[3][3],
        "search_id": "sony_a7iii_offer",
        "role": "product",
        "scope": "frozen_seller_offer_and_accessory_copy_not_equivalent_primary_lens_complete_kit_or_measured_family_photo_gain",
        "quotes": [
            "In stock SKU B07XDCPVSL Rating: 100 % of 100 2 Reviews Add Your Review $1,999.00 Qty Add to Cart Add to Wish List Add to Compare",
            "The camera features a 24.2MP Full frame sensor, 4K UHD Videos with an ISO upto 204800.",
            "The α7 III can shoot in a continuous burst at up to 10fps with AF/AE tracking and up to 8fps burst shooting when shooting with live-view mode.",
        ],
        "accepted": "The frozen a7 III page shows SKU B07XDCPVSL at 1,999 dollars, rated 100 percent over two reviews, and a body-only-labeled accessory bundle with seller claims for a 24.2MP full-frame sensor, high ISO, 4K and up to ten frames per second with AF or AE tracking; bundle accessories and feature counts are not an equivalent family-photo kit or measured gain.",
    },
    {
        "evidence_id": "prop_nikon_z6_offer_scope",
        "subject": "frozen Nikon Z6 body and FTZ bundle seller page",
        "predicate": "shows_a_mirrorless_bundle_with_bsi_on_sensor_af_ibis_and_adapter_claims",
        "object": "SKU B0934RQLD4 at 1,728 dollars with no posted review, an international-model body, FTZ adapter and 64GB XQD bundle, plus 24.5MP BSI, 273-point phase-detect AF and five-axis sensor-shift stabilization claims",
        "source_url": SEARCHES[4][3],
        "search_id": "nikon_z6_offer",
        "role": "product",
        "scope": "frozen_seller_bundle_and_mechanism_copy_not_current_warranty_lens_compatibility_or_measured_low_light_af_stabilization_gain",
        "quotes": [
            "In stock SKU B0934RQLD4 Be the first to review this product $1,728.00 Qty Add to Cart Add to Wish List Add to Compare",
            "Nikon Z6 FX-Format Mirrorless Camera(International Model)-24.5MP FX-Format BSI CMOS Sensor, EXPEED 6 Image Processing Engine, UHD 4K30 Video; N-Log & 10-Bit HDMI Out, 273-Point Phase-Detect AF System, Built-in to the body is a 5-axis sensor-shift Vibration Reduction mechanism",
            "Nikon Mount Adapter FTZ- Nikon F Lens to Nikon Z-Mount Camera, Maintains AF/AE with E, G, D Lenses, Retains Infinity Focus",
        ],
        "accepted": "The frozen Z6 page shows SKU B0934RQLD4 at 1,728 dollars with no posted review and international-model, FTZ and 64GB XQD bundle wording, plus seller claims for 24.5MP BSI, 273-point phase-detect AF and five-axis sensor-shift stabilization; exact lens compatibility, warranty and task gains still require verification.",
    },
    {
        "evidence_id": "prop_canon_eos_r_offer_scope",
        "subject": "frozen Canon EOS R body and adapter bundle seller page",
        "predicate": "shows_a_mirrorless_bundle_with_dual_pixel_af_evf_and_adapter_claims",
        "object": "SKU B09RTQ2VXP at 1,869 dollars with no posted review, a body, EF-EOS R adapter and 128GB card bundle, plus 30.3MP full-frame, Dual Pixel AF, 5,655 AF-point, EVF, eight-frame-per-second and 4K claims",
        "source_url": SEARCHES[5][3],
        "search_id": "canon_eos_r_offer",
        "role": "product",
        "scope": "frozen_seller_bundle_and_feature_copy_not_complete_task_lens_current_offer_or_measured_af_video_gain",
        "quotes": [
            "In stock SKU B09RTQ2VXP Be the first to review this product $1,869.00 Qty Add to Cart Add to Wish List Add to Compare",
            "Canon EOS R Mirrorless Digital Camera |Body Only Features : 30.3MP Full-Frame CMOS Sensor DIGIC 8 Image Processor UHD 4K30 Video; C-Log & 10-Bit HDMI Out Dual Pixel CMOS AF, 5655 AF Points 3.69m-Dot OLED Electronic Viewfinder",
            "This Bundle Also Includes: Mount Adapter + 128GB Memory Card",
        ],
        "accepted": "The frozen EOS R page shows SKU B09RTQ2VXP at 1,869 dollars with no posted review and a body, mount-adapter and 128GB-card bundle, plus seller claims for 30.3MP full frame, Dual Pixel AF, 5,655 AF points, EVF, eight frames per second and 4K; it lacks an equivalent task lens and measured family-photo result.",
    },
    {
        "evidence_id": "prop_d7000_release_feature_scope",
        "subject": "Nikon D7000 model history",
        "predicate": "places_the_model_in_2010_with_39_point_af_and_six_frame_per_second_capability",
        "object": "a 16.2MP DSLR announced in September 2010 with a 39-area AF system, 3D tracking modes and six-frame-per-second capability",
        "source_url": SEARCHES[6][3],
        "search_id": "nikon_d7000_model",
        "role": "concept",
        "scope": "model_generation_and_nominal_features_not_seller_listing_date_physical_unit_age_condition_or_current_performance",
        "quotes": [
            "Released 15 September 2010",
            "Focus areas 39-area AF system, Multi-CAM 4800DX AF Sensor Module Area modes: 3D-tracking, Auto-area, Dynamic-area, Single-point",
            "The Nikon D7000 [ 2 ] is a 16.2- megapixel digital single-lens reflex camera (DSLR) model announced by Nikon on September 15, 2010.",
        ],
        "accepted": "The D7000 model page places announcement and release in September 2010 and lists 16.2MP, a 39-area AF system with 3D tracking and six-frame-per-second capability; those model facts do not establish the later seller listing date, manufacture date or condition of a particular unit.",
    },
    {
        "evidence_id": "prop_canon_7d_release_feature_scope",
        "subject": "Canon EOS 7D model history",
        "predicate": "places_the_model_in_2009_with_19_cross_type_points_and_eight_frame_per_second_capability",
        "object": "a high-end APS-C DSLR announced in September 2009 with an 18MP sensor, nineteen cross-type AF points and eight-frame-per-second capability",
        "source_url": SEARCHES[7][3],
        "search_id": "canon_7d_model",
        "role": "concept",
        "scope": "model_generation_and_nominal_features_not_current_listing_condition_remaining_shutter_life_or_keeper_rate",
        "quotes": [
            "Focus areas 19 cross-type AF points",
            "Continuous shooting up to 8.0 frame/s",
            "The Canon EOS 7D is a high-end APS-C digital single-lens reflex camera made by Canon . [ 2 ] It was announced on 1 September 2009 with a suggested retail price of US$1,699, and was marketed as a semi-professional DSLR camera.",
        ],
        "accepted": "The EOS 7D model page identifies a high-end APS-C DSLR announced in September 2009 and lists 18MP, nineteen cross-type AF points and up to eight frames per second; these nominal model facts do not reveal current condition, remaining shutter life or family-photo keeper rate.",
    },
    {
        "evidence_id": "prop_sony_a7iii_release_feature_scope",
        "subject": "Sony a7 III model history",
        "predicate": "places_the_model_in_2018_with_bsi_dense_af_eye_tracking_ibis_and_ten_fps",
        "object": "a full-frame mirrorless model announced in February 2018 with a 24MP BSI sensor, 693 phase and 425 contrast AF points, eye AF, five-axis in-body stabilization and ten-frame-per-second capability",
        "source_url": SEARCHES[8][3],
        "search_id": "sony_a7iii_model",
        "role": "concept",
        "scope": "model_generation_and_capability_descriptors_not_exact_bundle_identity_firmware_lens_or_measured_task_gain",
        "quotes": [
            "It was announced [ 4 ] on 26 February 2018 as the successor to the Sony Î±7 II and available April 10, 2018.",
            "24 MP full-frame BSI CMOS sensor 693 Phase Detection AF Points with 93% coverage, inherited from Î±9 and 425 contrast AF points Continuous eye autofocus mode called Eye AF with High Tracking ability",
            "5-axis optical in-body image stabilization with a 5.0 step shutter speed advantage 10 fps continuous shooting (mechanical or silent)",
        ],
        "accepted": "The a7 III model page places the model in 2018 and lists a 24MP BSI sensor, 693 phase and 425 contrast AF points, eye AF, five-axis in-body stabilization and ten frames per second; these are capability descriptors rather than proof of the exact bundle, firmware, lens or task gain.",
    },
    {
        "evidence_id": "prop_nikon_z6_release_feature_scope",
        "subject": "Nikon Z6 model history",
        "predicate": "places_the_model_in_2018_with_bsi_273_point_coverage_and_firmware_evolution",
        "object": "a full-frame mirrorless model announced in August 2018 with a 24.5MP back-illuminated sensor, 273 single-point AF positions covering ninety percent and later firmware additions to eye and animal detection",
        "source_url": SEARCHES[9][3],
        "search_id": "nikon_z6_model",
        "role": "concept",
        "scope": "model_generation_hardware_and_firmware_history_not_exact_bundle_firmware_state_or_measured_af_success",
        "quotes": [
            "The camera was officially announced on August 23, 2018, to be released in November. Nikon began shipping the Z6 to retailers on November 16, 2018.",
            "Sensor type Back-illuminated CMOS sensor Sensor size Full frame (35.9 x 23.9 mm) Sensor maker Sony Maximum resolution 6048 x 4024 (24.5 effective megapixels )",
            "Focus areas 273 points (single-point AF) with 90% coverage",
        ],
        "accepted": "The Z6 model page places announcement and shipping in 2018 and lists a 24.5MP back-illuminated full-frame sensor and 273 single-point AF positions with ninety-percent coverage; its update history also makes installed firmware a separate inspection field rather than a fixed launch capability.",
    },
    {
        "evidence_id": "prop_canon_eos_r_release_feature_scope",
        "subject": "Canon EOS R model history",
        "predicate": "places_the_model_in_2018_with_dual_pixel_eye_af_dense_selection_and_known_mode_limits",
        "object": "Canon's first full-frame mirrorless model released in October 2018 with 30.3MP, Dual Pixel eye AF and up to 5,655 selectable points, while silent electronic readout can produce rolling-shutter skew and the body lacks IBIS",
        "source_url": SEARCHES[10][3],
        "search_id": "canon_eos_r_model",
        "role": "concept",
        "scope": "model_generation_capabilities_and_limits_not_exact_seller_bundle_firmware_lens_or_controlled_comparison",
        "quotes": [
            "It was announced days after Nikon's first full-frame MILC, the Nikon Z7 , and five years after Sony's first, and was released in October 2018.",
            "The camera supports up to 5,655 manually selectable autofocus points, within a focus area which covers approximately 100% of the height and 88% of the width of the image area when shooting still images.",
            "However, this uses an electronic shutter mode which works by reading the sensor one line at a time, and this means that fast movement during the read will cause a rolling shutter effect, leading to an image with skewed elements.",
        ],
        "accepted": "The EOS R model page places release in October 2018, lists up to 5,655 selectable AF points and eye-detection behavior, and says its silent electronic mode reads line by line so fast movement can skew; generation and feature presence still do not establish a measured gain for the exact seller bundle.",
    },
    {
        "evidence_id": "prop_bsi_low_light_mechanism_scope",
        "subject": "back-illuminated sensor architecture",
        "predicate": "rearranges_imaging_elements_to_increase_captured_light_with_cost_and_implementation_history",
        "object": "a sensor layout intended to increase captured light and improve low-light performance, with consumer-price introduction in 2009 but without a quantified gain for every exact camera",
        "source_url": SEARCHES[11][3],
        "search_id": "bsi_mechanism",
        "role": "concept",
        "scope": "general_sensor_architecture_mechanism_not_exact_camera_low_light_noise_dynamic_range_or_family_photo_result",
        "quotes": [
            "A back-illuminated (BI) sensor , also known as back-side illumination ( BSI ) sensor, is a type of digital image sensor that uses a novel arrangement of the imaging elements to increase the amount of light captured and thereby improve low-light performance.",
            "Sony was the first to reduce these problems and their costs sufficiently to introduce a 5-megapixel",
        ],
        "accepted": "The BSI page describes a rearranged sensor architecture intended to capture more light and improve low-light performance and notes consumer-price introduction in 2009; it does not quantify the gain of any exact camera after sensor size, lens, pixel pitch, exposure and processing differ.",
    },
    {
        "evidence_id": "prop_cmos_evolution_readout_scope",
        "subject": "active-pixel CMOS sensor development",
        "predicate": "shows_noise_capability_improvement_and_a_row_readout_tradeoff",
        "object": "modern CMOS sensors can outperform earlier CCD noise capability, BSI can mitigate inactive area, and row-wise capture can produce rolling-shutter effects",
        "source_url": SEARCHES[12][3],
        "search_id": "active_pixel_mechanism",
        "role": "concept",
        "scope": "general_cmos_development_and_readout_boundary_not_exact_sensor_generation_brand_or_measured_task_result",
        "quotes": [
            "With improvements in CMOS technology, this advantage has closed as of 2020, with modern CMOS sensors available capable of outperforming CCD sensors.",
            "The active circuitry in CMOS pixels takes some area on the surface which is not light-sensitive, reducing the photon-detection efficiency of the device ( microlenses and back-illuminated sensors can mitigate this problem).",
            "Since a CMOS sensor typically captures a row at a time within approximately 1/60 or 1/50 of a second (depending on refresh rate) it may result in a rolling shutter effect",
        ],
        "accepted": "The active-pixel page says modern CMOS capability can outperform the former CCD noise advantage, that microlenses and BSI can mitigate inactive light-sensitive area, and that row-wise capture can create rolling-shutter effects; these general mechanisms do not identify an exact unit's measured output.",
    },
    {
        "evidence_id": "prop_stabilization_subject_motion_boundary",
        "subject": "image stabilization",
        "predicate": "reduces_camera_motion_blur_but_does_not_freeze_subject_motion",
        "object": "lens, body or combined stabilization can allow slower handheld shutter speeds by reducing ordinary camera shake, but it does not prevent blur from a moving subject",
        "source_url": SEARCHES[13][3],
        "search_id": "stabilization_mechanism",
        "role": "concept",
        "scope": "general_camera_shake_mechanism_not_exact_stop_rating_subject_motion_keeper_rate_or_video_result",
        "quotes": [
            "Image stabilization ( IS ) is a family of techniques that reduce blurring associated with the motion of a camera or other imaging device during exposure .",
            "However, image stabilization does not prevent motion blur caused by the movement of the subject or by extreme movements of the camera.",
            "Stabilization can be applied in the lens, the camera body or both. Each method has distinctive advantages and disadvantages.",
        ],
        "accepted": "The stabilization page defines IS as reducing blur from camera motion, says it can be implemented in the lens, body or both, and explicitly says it does not prevent blur caused by subject movement; a moving-child task therefore requires shutter speed and AF testing rather than an IBIS label alone.",
    },
    {
        "evidence_id": "prop_evf_preview_latency_scope",
        "subject": "electronic viewfinder",
        "predicate": "adds_processed_setting_aware_preview_and_focus_aids_with_display_limits",
        "object": "an EVF displays the sensor view on a small processed screen, can preview exposure and white balance and show focus aids, but can have display dynamic-range and processing-latency limits",
        "source_url": SEARCHES[14][3],
        "search_id": "evf_mechanism",
        "role": "concept",
        "scope": "general_viewfinder_workflow_capability_not_final_file_quality_operator_preference_or_exact_model_latency",
        "quotes": [
            "An electronic viewfinder ( EVF ) is a camera viewfinder where the image captured by the lens is displayed on a small screen (usually LCD or OLED ) which the photographer can look through when composing their shot.",
            "The digital preview shown in an EVF incorporates the camera's settings (including exposure, white balance, etc.) and so the image seen can be an exact preview of what the taken photograph will look like, which is not possible with an OVF.",
            "There is also no time lag with an OVF, whereas an EVF might take a bit of time to process the image and update the display (particularly when using longer exposure times).",
        ],
        "accepted": "The EVF page describes a processed sensor view that can preview settings and support focus or exposure aids, while noting display dynamic-range and processing-latency limits relative to an optical finder; this is a workflow difference, not a final-file quality verdict.",
    },
    {
        "evidence_id": "prop_rolling_shutter_motion_scope",
        "subject": "rolling shutter readout",
        "predicate": "records_scene_regions_at_different_times_and_can_distort_motion_or_flashes",
        "object": "row or region scanning means the whole scene is not captured at one instant, so fast motion, vibration or flashes can produce skew or wobble unlike a global shutter",
        "source_url": SEARCHES[15][3],
        "search_id": "rolling_shutter_mechanism",
        "role": "concept",
        "scope": "general_readout_and_motion_artifact_mechanism_not_exact_camera_mode_readout_speed_or_video_failure_rate",
        "quotes": [
            "Rolling shutter is a process of image capture in which a still picture (in a still camera) or each frame of a video (in a video camera) is captured not by taking a snapshot of the entire scene at a single instant in time but rather by scanning across the scene rapidly, vertically, horizontally or rotationally.",
            "This produces predictable distortions of fast-moving objects or rapid flashes of light, referred to as rolling shutter effect .",
            "This process contrasts with global shutter, in which the entire frame is captured at the same instant.",
        ],
        "accepted": "The rolling-shutter page explains that different scene regions are captured at different times, which can distort fast motion, vibration or flashes, whereas a global shutter captures the frame at one instant; an exact mode's readout speed and task failure rate still require testing.",
    },
    {
        "evidence_id": "prop_dynamic_range_noise_scope",
        "subject": "photographic dynamic range",
        "predicate": "describes_a_luminance_range_and_shadow_recovery_noise_boundary",
        "object": "dynamic range is a ratio of measurable extremes and in photography concerns the luminance range a scene or camera can capture and how far exposure can be pushed without significantly increasing noise",
        "source_url": SEARCHES[16][3],
        "search_id": "dynamic_range_mechanism",
        "role": "concept",
        "scope": "general_definition_and_editing_boundary_not_exact_sensor_score_family_photo_quality_or_uncontrolled_composite",
        "quotes": [
            "Dynamic range (abbreviated DR , DNR , [ 1 ] or DYR [ 2 ] ) is the ratio between the largest and smallest measurable values of a specific quantity.",
            "The better the dynamic range of the camera, the more an exposure can be pushed without significantly increasing noise .",
            "Photographers use dynamic range to describe the luminance range of a scene being photographed, or the limits of luminance range that a given digital camera or film can capture",
        ],
        "accepted": "The dynamic-range page defines a ratio between measurable extremes and, for photography, the luminance range a scene or camera can capture and the degree to which exposure can be pushed without a large noise increase; it is not a universal image-quality score and needs matched files and output conditions.",
    },
    {
        "evidence_id": "prop_forum_used_value_defect_risk_scope",
        "subject": "community used-camera value discussion",
        "predicate": "contains_both_an_older_prosumer_value_claim_and_a_beginner_defect_risk_warning",
        "object": "one commenter recommends older prosumer gear over new entry level and another warns that beginners can be scammed, overpay or miss latent problems, while a third says an old 5D Mark II remains capable for stills",
        "source_url": SEARCHES[17][3],
        "search_id": "forum_used_body_debate",
        "role": "community",
        "scope": "opposing_user_opinions_and_personal_gear_experience_not_verified_market_value_unit_condition_or_universal_old_body_result",
        "quotes": [
            "Why would you ever buy new entry level when there is a robust used market and you can get an older prosumer level instead.",
            "Buying used camera gear isn't really a beginner's game. It's very easy to get scammed, overpay, or buy something with problems that won't be found until later.",
            "And honestly if you can’t create good stills work with even an old 5dm2, the problem isn’t the camera.",
        ],
        "accepted": "The frozen discussion contains opposing community claims about older prosumer value and hidden used-gear risk, plus one user's view that an old 5D Mark II remains capable for stills; these are scoped opinions that motivate inspection and task testing, not a market or generation verdict.",
    },
    {
        "evidence_id": "prop_forum_same_gear_workflow_confound_scope",
        "subject": "community two-year Jupiter progress post",
        "predicate": "shows_visible_progress_with_retained_core_gear_and_changed_practice_accessories_capture_and_processing",
        "object": "the author reports four images over two years with the same core telescope while practice, weather, Barlow choice, tracking, frame count, stacking and editing changed",
        "source_url": SEARCHES[18][3],
        "search_id": "forum_same_gear_progress",
        "role": "community",
        "scope": "single_astrophotography_workflow_history_not_family_photo_body_generation_test_or_hardware_irrelevance_proof",
        "quotes": [
            "My two year progress shooting Jupiter, using the same $300 telescope!",
            "I got the telescope last summer and was finally able to capture some nice images after a lot of practice (and bad weather)!",
            "My post history has the full equipment and processing details for the four pictures, taken in October 2020, July 2021, August 2022, and October 2022.",
        ],
        "accepted": "The frozen Jupiter thread reports progress across four dates with the same core telescope but also documents practice, weather, Barlow, tracking, capture-count, stacking and processing changes; it demonstrates workflow confounding rather than proving that camera generation never matters.",
    },
    {
        "evidence_id": "prop_forum_close_focus_task_regression_scope",
        "subject": "community newer-phone close-focus complaint",
        "predicate": "reports_a_newer_device_failing_an_older_device_close_focus_task_with_lens_and_mode_differences",
        "object": "one author says a newer 14 Plus is blurry at the older XS Max's five-inch distance, while comments identify missing telephoto or macro paths and a different minimum focus distance",
        "source_url": SEARCHES[19][3],
        "search_id": "forum_close_focus_regression",
        "role": "community",
        "scope": "single_user_phone_lens_mode_distance_and_subject_report_not_interchangeable_camera_or_universal_newer_is_worse_result",
        "quotes": [
            "14 plus cannot take photos close up? Expected similar quality to XS max but at same distance (5”) photos insanely blurry… super frustrated, should/can I exchange from att for the pro max? :/",
            "Xs max has telephoto lens, 14 plus doesnt",
            "I take hundreds of photos of these animals lol that didn’t work. I was messing with it all day trying to get it to focus and just ended up with a dozen blurry photos unless I move 10+ inches away and then zoom in on the screen lol",
        ],
        "accepted": "The frozen phone discussion reports a newer device failing an older device's five-inch close-focus expectation and identifies lens, macro-path and minimum-focus-distance differences; it motivates an exact close-subject task but remains one phone-user report rather than a universal newer-is-worse result.",
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

    critical_search_ids = {item["search_id"] for item in EVIDENCE}
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
                    "critical_path_root": search_id in critical_search_ids,
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
            "registry_id": "reg_case_spec_old_body_generation_0057",
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
        (
            "bridge_exact_offer_generation_matrix",
            "bridge",
            "six frozen offers and five model histories",
            "separates_listing_identity_condition_and_date_from_model_generation",
            "retain exact seller fields and match each model to release history without using listing dates or nominal feature counts as physical-unit performance",
            "frozen_offer_identity_condition_matrix_v1",
        ),
        (
            "bridge_generation_feature_mechanism_boundary",
            "bridge",
            "sensor AF stabilization EVF shutter and dynamic-range evidence",
            "maps_generation_features_to_scoped_testable_mechanisms",
            "separate BSI and CMOS layout AF method and coverage stabilization EVF preview rolling readout and dynamic range before claiming any task gain",
            "generation_feature_mechanism_boundary_v1",
        ),
        (
            "bridge_used_unit_inspection_gate",
            "bridge",
            "coworker physical used camera",
            "blocks_purchase_until_identity_condition_and_file_integrity_pass",
            "inspect serial firmware actuations sensor mount controls battery ports storage errors sample files and service or return terms before price comparison",
            "used_unit_inspection_gate_v1",
        ),
        (
            "bridge_complete_kit_cost_gate",
            "bridge",
            "complete working older and newer paths",
            "normalizes_lens_adapter_battery_storage_service_and_return_costs",
            "price equivalent task lenses and all required accessories and risk allowances rather than comparing body-only and kit sticker prices",
            "complete_kit_cost_gate_v1",
        ),
        (
            "bridge_task_matched_family_trial",
            "bridge",
            "daylight dim moving close and video family tasks",
            "measures_repeatable_threshold_crossing_gains_under_matched_outputs",
            "run matched and preferably blinded trials for AF keeper rate motion and shake blur noise highlights close focus rolling skew stability battery handling and transfer time",
            "task_matched_family_photo_trial_v1",
        ),
        (
            "bridge_attribution_repeatability_gate",
            "bridge",
            "observed old versus newer path differences",
            "withholds_generation_credit_when_lens_firmware_skill_processing_or_scene_is_confounded",
            "repeat stable effects and attribute only the tested path while using community reports as hypotheses and confound warnings rather than verdicts",
            "community_scope_boundary_v1",
        ),
        (
            "decision_incremental_value_used_or_new",
            "decision",
            "first camera purchase for mandatory family uses",
            "chooses_the_lowest_total_cost_complete_path_passing_every_required_gate_or_defers",
            "buy the verified used path when it passes all thresholds unless a newer path produces a repeatable predeclared incremental value gain otherwise choose the lowest passing complete path or borrow rent keep the phone or defer",
            "incremental_value_decision_v1",
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
        "bridge_exact_offer_generation_matrix": [
            "prop_d7000_renewed_offer_scope",
            "prop_canon_7d_offer_scope",
            "prop_sony_a300_offer_scope",
            "prop_sony_a7iii_offer_scope",
            "prop_nikon_z6_offer_scope",
            "prop_canon_eos_r_offer_scope",
            "prop_d7000_release_feature_scope",
            "prop_canon_7d_release_feature_scope",
            "prop_sony_a7iii_release_feature_scope",
            "prop_nikon_z6_release_feature_scope",
            "prop_canon_eos_r_release_feature_scope",
        ],
        "bridge_generation_feature_mechanism_boundary": [
            "prop_d7000_release_feature_scope",
            "prop_canon_7d_release_feature_scope",
            "prop_sony_a7iii_release_feature_scope",
            "prop_nikon_z6_release_feature_scope",
            "prop_canon_eos_r_release_feature_scope",
            "prop_bsi_low_light_mechanism_scope",
            "prop_cmos_evolution_readout_scope",
            "prop_stabilization_subject_motion_boundary",
            "prop_evf_preview_latency_scope",
            "prop_rolling_shutter_motion_scope",
            "prop_dynamic_range_noise_scope",
        ],
        "bridge_used_unit_inspection_gate": [
            "bridge_exact_offer_generation_matrix",
            "prop_d7000_renewed_offer_scope",
            "prop_canon_7d_offer_scope",
            "prop_sony_a300_offer_scope",
            "prop_forum_used_value_defect_risk_scope",
        ],
        "bridge_complete_kit_cost_gate": [
            "bridge_exact_offer_generation_matrix",
            "bridge_used_unit_inspection_gate",
            "prop_sony_a7iii_offer_scope",
            "prop_nikon_z6_offer_scope",
            "prop_canon_eos_r_offer_scope",
        ],
        "bridge_task_matched_family_trial": [
            "bridge_generation_feature_mechanism_boundary",
            "bridge_used_unit_inspection_gate",
            "bridge_complete_kit_cost_gate",
            "prop_stabilization_subject_motion_boundary",
            "prop_evf_preview_latency_scope",
            "prop_rolling_shutter_motion_scope",
            "prop_dynamic_range_noise_scope",
            "prop_forum_close_focus_task_regression_scope",
        ],
        "bridge_attribution_repeatability_gate": [
            "bridge_task_matched_family_trial",
            "prop_forum_used_value_defect_risk_scope",
            "prop_forum_same_gear_workflow_confound_scope",
            "prop_forum_close_focus_task_regression_scope",
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
                "source_id": "decision_incremental_value_used_or_new",
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
