#!/usr/bin/env python3
"""Build the frozen Q53 camera-spec physical-boundary inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
CAPTURE_REL = Path(
    "data/evidence_graph/captures/"
    "v3-corpus-formal-cameras-photo-0053-spec-claim-physical-"
    "boundary-20260716-r1"
)
CAPTURE = ROOT / CAPTURE_REL
CASE_SPEC_REL = Path(
    "data/pilot_v3/formal_candidates/dra_v3_formal_cameras_photo_0053/"
    "graph_inputs/case_authoring_source.json"
)
CASE_SPEC = ROOT / CASE_SPEC_REL
OUT = Path(__file__).with_name("inventory.json")
SNAPSHOT = (
    "dra-v3-formal-cameras-photo-0053-spec-claim-physical-"
    "boundary-20260716-r1"
)
RUN_ID = (
    "v3-corpus-formal-cameras-photo-0053-spec-claim-physical-"
    "boundary-20260716-r1"
)
TASK_ID = "dra_v3_formal_cameras_photo_0053"
TOPIC = "camera_spec_claim_physical_boundary"


SEARCHES = [
    (
        "tcl_20s",
        "001-shopping-tcl-20s-64mp.json",
        "TCL 20S 64MP and AI-powered seller snapshot",
        "http://localhost:7770/tcl-20s-unlocked-android-smartphone-with-6-67-dotch-fhd-display-64mp-quad-rear-camera-system-128gb-4gb-ram-5000mah-battery-with-fast-charging-milky-way-black.html",
    ),
    (
        "dji_pocket2",
        "002-shopping-dji-pocket2-64mp.json",
        "DJI Pocket 2 64MP, 8x zoom and AI Editor seller snapshot",
        "http://localhost:7770/dji-pocket-2-creator-combo-3-axis-gimbal-stabilizer-with-4k-camera-1-1-7-cmos-64mp-photo-pocket-sized-activetrack-3-0-glamour-effects-youtube-tiktok-video-vlog-for-android-and-iphone-black.html",
    ),
    (
        "nikon_b500",
        "003-shopping-nikon-b500-40x-optical.json",
        "Nikon B500 optical, digital and storage seller snapshot",
        "http://localhost:7770/nikon-coolpix-b500-16mp-digital-camera-with-3-inch-tft-lcd-screen-nikkor-lens-with-40x-optical-zoom-wifi-64gb-memory-card-black.html",
    ),
    (
        "vjianger",
        "004-shopping-vjianger-48mp-16x-digital.json",
        "VJIANGER 48MP and 16x digital-zoom seller snapshot",
        "http://localhost:7770/digital-camera-for-photography-48mp-vlogging-camera-for-youtube-with-flip-screen-vjianger-4k-photography-camera-with-16x-digital-zoom-52mm-wide-angle-macro-lens-2-batteries-32gb-tf-card-black.html",
    ),
    (
        "panasonic_g9",
        "005-shopping-panasonic-g9-80mp-mode.json",
        "Panasonic G9 20.3MP sensor and 80MP mode seller snapshot",
        "http://localhost:7770/panasonic-lumix-g9-4k-digital-camera-20-3-megapixel-mirrorless-camera-plus-80-megapixel-high-resolution-mode-5-axis-dual-i-s-2-0-3-inch-lcd-dc-g9-black.html",
    ),
    (
        "kuidamos",
        "006-shopping-kuidamos-ai-intelligent-camera.json",
        "KUIDAMOS 2400W, 720P and AI seller snapshot",
        "http://localhost:7770/kuidamos-2-4-inch-hd-screen-mini-child-camera-2400w-pixel-dual-lens-ai-intelligent-photography-instant-printing-digital-children-camera-portable-instant-print-camera-for-kids-boy-girl-brown.html",
    ),
    (
        "pixel",
        "007-wiki-pixel-picture-element.json",
        "pixel sampling and sensor-element terminology",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Pixel",
    ),
    (
        "image_resolution",
        "008-wiki-image-resolution.json",
        "image-resolution and pixel-count boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Image_resolution",
    ),
    (
        "optical_resolution",
        "009-wiki-optical-resolution.json",
        "resolved optical detail and system boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Optical_resolution",
    ),
    (
        "digital_zoom",
        "010-wiki-digital-zoom.json",
        "digital crop and optical-resolution boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Digital_zoom",
    ),
    (
        "zoom_lens",
        "011-wiki-zoom-lens.json",
        "focal-length and zoom-ratio boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Zoom_lens",
    ),
    (
        "pixel_binning",
        "012-wiki-pixel-binning.json",
        "pixel-binning detail and low-light tradeoff",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Pixel_binning",
    ),
    (
        "bayer_filter",
        "013-wiki-bayer-filter.json",
        "Bayer single-color sampling boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Bayer_filter",
    ),
    (
        "demosaicing",
        "014-wiki-demosaicing.json",
        "demosaicing reconstruction and artifact boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Demosaicing",
    ),
    (
        "computational_photo",
        "015-wiki-computational-photography.json",
        "computational-photography operation boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Computational_photography",
    ),
    (
        "super_resolution",
        "016-wiki-super-resolution-imaging.json",
        "super-resolution information and invariance boundary",
        "http://localhost:8090/content/wikipedia_en_all_nopic/Super-resolution_imaging",
    ),
    (
        "forum_megapixel",
        "017-forum-megapixels-resolution-eli5.json",
        "community megapixel and resolution explanation",
        "http://localhost:9999/f/explainlikeimfive/39247/eli5-are-megapixels-just-resolution-but-for-still-images",
    ),
    (
        "forum_optical_zoom",
        "018-forum-true-optical-zoom-phone.json",
        "community phone optical-zoom and detail discussion",
        "http://localhost:9999/f/gadgets/61313/lg-innotek-is-ready-to-put-true-optical-zoom-lenses-in-the",
    ),
    (
        "forum_iphone_detail",
        "019-forum-iphone-distant-detail-confound.json",
        "community distant-detail complaint and accessory confound",
        "http://localhost:9999/f/iphone/20462/iphone-14-pro-max-camera",
    ),
    (
        "forum_dslr_phone_unused",
        "020-forum-dslr-versus-phone-eli5.json",
        "captured DSLR-versus-phone title-only page retained as unused corpus",
        "http://localhost:9999/f/explainlikeimfive/18682/eli5-what-is-the-difference-and-or-benefit-of-a-dlsr-camera",
    ),
]


EVIDENCE: list[dict[str, Any]] = [
    {
        "evidence_id": "prop_tcl_64mp_ai_offer_scope",
        "subject": "frozen TCL 20S seller page",
        "predicate": "shows_a_64mp_main_camera_with_ai_powered_quad_camera_copy",
        "object": "a 249.99-dollar SKU with no posted review whose seller describes a 64MP main camera inside an AI-powered four-camera system and claims precise detail across scenes and light",
        "source_url": SEARCHES[0][3],
        "search_id": "tcl_20s",
        "role": "product",
        "scope": "seller_offer_and_marketing_copy_not_measured_resolved_detail_ai_operation_or_low_light_result",
        "quotes": [
            "In stock SKU B095PGG2NB Be the first to review this product $249.99 Color Milky Way Black North Star Blue Qty Add to Cart Add to Wish List Add to Compare",
            "A Camera for Every Occasion Capture the beauty around you with the TCL 20S AI-powered quad camera that includes a 64MP super high-res main, 8MP 118° wide-angle, 2MP depth, and 2MP macro camera.",
            "The 64MP main camera redefines smartphone photography with precise details, regardless of the scene complexity and light conditions.",
        ],
        "accepted": "The frozen TCL page shows SKU B095PGG2NB at 249.99 dollars with no posted review and seller copy for an AI-powered quad-camera system with a 64MP main camera plus 8MP wide, 2MP depth and 2MP macro cameras; its precise-detail and all-scene or all-light wording is marketing, not a measured resolved-detail, low-light or identified AI-operation result.",
    },
    {
        "evidence_id": "prop_dji_64mp_zoom_ai_editor_scope",
        "subject": "frozen DJI Pocket 2 seller page",
        "predicate": "shows_a_64mp_sensor_claim_an_untyped_8x_zoom_and_clip_assembly_ai_editor",
        "object": "a 499-dollar SKU with no posted review whose seller describes a 1/1.7-inch sensor, 64MP photos, 8x zoom and an AI Editor that combines clips with transitions and music",
        "source_url": SEARCHES[1][3],
        "search_id": "dji_pocket2",
        "role": "product",
        "scope": "seller_offer_zoom_and_editing_copy_not_optical_zoom_label_or_validated_detail_enhancement",
        "quotes": [
            "In stock SKU B08HWCCS6S Be the first to review this product $499.00 Size DJI Pocket 2 DJI Pocket 2 Creator Combo DJI Pocket 2 Exclusive Combo (Sunset Whi... DJI Pocket 2 Exclusive Combo + Wide-Angl... Qty Add to Cart Add to Wish List Add to Compare",
            "8x ZoomLooking for crazy detail? When taking 64MP photos, the stabilized camera takes sharp 8x zoom shots.",
            "【HIGH IMAGE QUALITY】: An upgraded 1/1.7-inch sensor captures images with 64MP photo and 4K video.",
            "【AI EDITOR】: AI Editor automatically combines your clips with transitions and music to create share-worthy content.",
        ],
        "accepted": "The frozen DJI page shows SKU B08HWCCS6S at 499 dollars with no posted review and seller claims for a 1/1.7-inch sensor, 64MP photos and 8x zoom; the captured text does not label that 8x claim optical, and its explicitly described AI Editor combines clips with transitions and music rather than measuring or enhancing still-image resolved detail.",
    },
    {
        "evidence_id": "prop_nikon_optical_digital_storage_scope",
        "subject": "frozen Nikon B500 bundle seller page",
        "predicate": "separates_40x_optical_from_80x_enhanced_digital_zoom_and_64gb_storage",
        "object": "a 6.24-dollar rated bundle with a 16MP sensor, 40x optical zoom, 80x Dynamic Fine Zoom described as enhanced digital zoom and an included 64GB memory card",
        "source_url": SEARCHES[2][3],
        "search_id": "nikon_b500",
        "role": "product",
        "scope": "seller_offer_and_zoom_type_copy_not_focal_endpoints_endpoint_sharpness_or_storage_as_pixels",
        "quotes": [
            "In stock SKU B07J2V97WQ Rating: 73 % of 100 12 Reviews Add Your Review $6.24 Qty Add to Cart Add to Wish List Add to Compare",
            "40x optical zoom gives you super telephoto power, then Dynamic Fine Zoom, an enhanced digital zoom, effectively doubles that reach for a whopping 80x zoom.",
            "Lens-Shift Vibration Reduction (VR) keeps your shots steady - crucial at such long distances - and a 16-megapixel backside illuminated CMOS sensor captures every detail.",
            "INCLUDES: NIKON B500 and 64GB Memory Card",
        ],
        "accepted": "The frozen Nikon bundle page shows SKU B07J2V97WQ at 6.24 dollars, rated 73 percent over twelve reviews, and explicitly separates 40x optical zoom from 80x Dynamic Fine Zoom described as enhanced digital zoom; it also describes a 16MP sensor and an included 64GB memory card, where 64GB is storage rather than a capture-pixel count, and it supplies no focal endpoints or measured endpoint detail.",
    },
    {
        "evidence_id": "prop_vjianger_48mp_digital_zoom_scope",
        "subject": "frozen VJIANGER seller page",
        "predicate": "shows_48mp_and_16x_digital_zoom_marketing",
        "object": "a 119.99-dollar SKU rated 72 percent over ten reviews whose seller claims 48 megapixels and 16x digital zoom with clear-detail language",
        "source_url": SEARCHES[3][3],
        "search_id": "vjianger",
        "role": "product",
        "scope": "seller_offer_and_digital_zoom_copy_not_sensor_identity_optical_detail_or_independent_test",
        "quotes": [
            "In stock SKU B09JGPRCY5 Rating: 72 % of 100 10 Reviews Add Your Review $119.99 Color Black1 Pink1 Purple1 Qty Add to Cart Add to Wish List Add to Compare",
            "The 4k small digital camera with 30fps video resolution and 48 megapixel, provides a smooth shooting experience than 2.7K or 1080P video cameras, which can capture every excellent moment while vlog recording, the best camera for youtube.",
            "Equipped with wide angle & macro lenses and supports 16X Digital Zoom to get closer focus from far away and take close-up with clear details photos or recorder a wider range of scenery.",
        ],
        "accepted": "The frozen VJIANGER page shows SKU B09JGPRCY5 at 119.99 dollars, rated 72 percent over ten reviews, and seller copy for 48 megapixels, wide and macro accessories and 16x digital zoom with clear-detail wording; the page supplies no verified sensor sampling definition, focal endpoint or independent resolved-detail comparison.",
    },
    {
        "evidence_id": "prop_panasonic_multishot_80mp_scope",
        "subject": "frozen Panasonic G9 seller page",
        "predicate": "identifies_an_80mp_raw_special_mode_created_from_eight_20_3mp_sensor_shots",
        "object": "a 997.99-dollar body-only selected SKU with no posted review whose 80MP RAW output is described as one image made by shooting the 20.3MP sensor eight times",
        "source_url": SEARCHES[4][3],
        "search_id": "panasonic_g9",
        "role": "product",
        "scope": "seller_offer_and_multishot_mode_copy_not_native_single_shot_80mp_sensor_or_moving_scene_result",
        "quotes": [
            "In stock SKU B0774KTV1X Be the first to review this product $997.99 Style Body Only Premium Lens Kit Standard Lens Kit Qty Add to Cart Add to Wish List Add to Compare",
            "A High-Resolution special mode yields 80 megapixels in RAW recording by shooting the 20.3-megapixel sensor 8 times to create a single image.",
        ],
        "accepted": "The frozen Panasonic page shows SKU B0774KTV1X at 997.99 dollars with no posted review and Body Only selected; it explicitly describes a High-Resolution special mode that shoots the 20.3MP sensor eight times to create one 80MP RAW image, so the captured claim is a multi-exposure output mode rather than a native single-shot 80MP sensor or a validated moving-scene result.",
    },
    {
        "evidence_id": "prop_kuidamos_ambiguous_pixel_ai_scope",
        "subject": "frozen KUIDAMOS child-camera seller page",
        "predicate": "shows_ambiguous_2400w_720p_lens_and_ai_labelled_automatic_functions",
        "object": "a 73.69-dollar SKU with no posted review whose seller says each lens is 2400W (720P), printing is 200 DPI and AI-labelled functions include autofocus, color or discoloration and dimming",
        "source_url": SEARCHES[5][3],
        "search_id": "kuidamos",
        "role": "product",
        "scope": "seller_offer_ambiguous_unit_and_ai_copy_not_validated_megapixels_print_detail_or_computational_quality",
        "quotes": [
            "In stock SKU B093RDC7P7 Be the first to review this product $73.69 Color Blue Brown Pink Qty Add to Cart Add to Wish List Add to Compare",
            "Al Intelligent photography technology, auto focus / auto color / auto dimming.",
            "Lens: Front 2400W (720P) + Rear 2400W (720P)",
            "Paper Parameters: Thermal Paper Size: 57x30mm/2.2x1.2inch ,200 DPI Storage: 1GB Can Store 400 Photos or 6 Minutes of Video Language: Default Chinese, Support 28 Languages",
        ],
        "accepted": "The frozen KUIDAMOS page shows SKU B093RDC7P7 at 73.69 dollars with no posted review and seller fields for front and rear 2400W (720P) lenses, 200 DPI thermal paper and AI-labelled autofocus, color or discoloration and dimming; the page does not define 2400W as a validated megapixel count, reconcile it with 720P files, or demonstrate an image-detail improvement from the AI label.",
    },
    {
        "evidence_id": "prop_pixel_sampling_scope",
        "subject": "pixel and image-sample terminology",
        "predicate": "defines_pixels_as_addressable_elements_and_samples_with_context_dependent_sensor_terms",
        "object": "pixels are addressable elements arranged as samples, while camera-sensor contexts may use photosite or sensel terminology",
        "source_url": SEARCHES[6][3],
        "search_id": "pixel",
        "role": "concept",
        "scope": "general_sampling_definition_not_exact_product_pixel_type_output_or_resolved_detail",
        "quotes": [
            "In digital imaging , a pixel (abbreviated px ), pel , [ 1 ] or picture element [ 2 ] is the smallest addressable physical element of a raster image or the smallest controllable element of a display device or dot matrix printer.",
            "Pixels are arranged in a regular, two-dimensional grid, and each pixel serves as a sample of an original image, with a greater number of samples typically providing more accurate representations.",
        ],
        "accepted": "The frozen pixel page defines a pixel as an addressable physical image element, says pixels serve as samples and notes context-dependent camera-sensor terms such as photosite or sensel; it does not establish whether any seller number means total sensor sites, effective sites, recorded samples, reconstructed output or measured detail.",
    },
    {
        "evidence_id": "prop_image_resolution_upper_bound_scope",
        "subject": "image resolution and pixel-count conventions",
        "predicate": "distinguishes_detail_from_total_recorded_and_effective_pixel_counts",
        "object": "image resolution means detail, standards distinguish several pixel counts, and pixel-count resolutions are only upper bounds on image resolution",
        "source_url": SEARCHES[7][3],
        "search_id": "image_resolution",
        "role": "concept",
        "scope": "general_resolution_boundary_not_measurement_of_any_captured_camera",
        "quotes": [
            "Image resolution is the level of detail of an image .",
            "The term resolution is often considered equivalent to pixel count in digital imaging , though international standards in the digital camera field specify it should instead be called \"Number of Total Pixels\" in relation to image sensors, and as \"Number of Recorded Pixels\" for what is fully captured.",
            "None of these pixel resolutions are true resolutions, but they are widely referred to as such; they serve as upper bounds on image resolution.",
        ],
        "accepted": "The frozen image-resolution page defines image resolution as detail, says camera standards distinguish total and recorded pixel counts and separately discuss effective pixels, and says pixel-count resolutions are upper bounds rather than true resolution; it supplies no resolved-detail measurement for any exact SKU.",
    },
    {
        "evidence_id": "prop_optical_resolution_system_scope",
        "subject": "resolved optical detail",
        "predicate": "depends_on_the_full_imaging_system_environment_contrast_lens_quality_and_diffraction",
        "object": "optical resolution is resolved detail by scale and real system performance can differ with components, environment, contrast, lens quality and diffraction",
        "source_url": SEARCHES[8][3],
        "search_id": "optical_resolution",
        "role": "concept",
        "scope": "general_optical_system_boundary_not_chart_measurement_or_product_result",
        "quotes": [
            "Optical resolution is the resolved detail of an imaging system by scale.",
            "Each of these contributes (given suitable design, and adequate alignment) to the optical resolution of the system; the environment in which the imaging is done often is a further important factor.",
            "The ability of a lens to resolve detail is usually determined by the quality of the lens, but is ultimately limited by diffraction .",
        ],
        "accepted": "The frozen optical-resolution page defines optical resolution as resolved detail by scale and says the components, design, alignment, environment and contrast affect real results, while lens detail depends on lens quality and is ultimately diffraction-limited; it does not measure any captured offer or convert megapixels into resolved detail.",
    },
    {
        "evidence_id": "prop_digital_zoom_crop_scope",
        "subject": "digital zoom",
        "predicate": "crops_and_scales_without_adjusting_optics_or_gaining_optical_resolution",
        "object": "digital zoom narrows the field by cropping and scaling electronically, gains no optical resolution and may add computational or AI processing",
        "source_url": SEARCHES[9][3],
        "search_id": "digital_zoom",
        "role": "concept",
        "scope": "general_digital_zoom_mechanism_not_quality_result_for_any_exact_mode",
        "quotes": [
            "It is accomplished by cropping an image down to an area with the same aspect ratio as the original, and scaling the image up to the dimensions of the original.",
            "The camera's optics are not adjusted. It is accomplished electronically, so no optical resolution is gained.",
            "Digital zooming may be enhanced by computationally expensive algorithms which sometimes involves artificial intelligence.",
        ],
        "accepted": "The frozen digital-zoom page says digital zoom crops and scales an image without adjusting the optics, gains no optical resolution and may add computational or AI processing; those general statements classify a path but do not measure the Nikon, VJIANGER or DJI output quality.",
    },
    {
        "evidence_id": "prop_zoom_lens_ratio_scope",
        "subject": "optical zoom lens and zoom ratio",
        "predicate": "varies_focal_length_while_ratio_only_compares_longest_to_shortest_endpoints",
        "object": "optical zoom changes focal length and angle of view, while the x ratio is longest divided by shortest and larger ranges can involve image-quality and operational compromises",
        "source_url": SEARCHES[10][3],
        "search_id": "zoom_lens",
        "role": "concept",
        "scope": "general_zoom_definition_not_absolute_reach_endpoint_sharpness_or_exact_lens_result",
        "quotes": [
            "A zoom lens is a system of camera lens elements for which the focal length (and thus angle of view ) can be varied, as opposed to a fixed-focal-length (FFL) lens ( prime lens ).",
            "Zoom lenses are often described by the ratio of their longest to shortest focal lengths.",
            "The convenience of variable focal length comes at the cost of complexity â and some compromises on image quality, weight, dimensions, aperture, autofocus performance, and cost.",
            "This is commonly known as digital zoom and produces an image of lower optical resolution than optical zoom.",
        ],
        "accepted": "The frozen zoom-lens page says a zoom lens varies focal length and angle of view, defines the x ratio as longest divided by shortest focal length, notes quality and operational compromises and distinguishes lower-resolution crop enlargement; a 40x ratio alone therefore gives neither absolute reach nor measured endpoint sharpness.",
    },
    {
        "evidence_id": "prop_pixel_binning_tradeoff_scope",
        "subject": "pixel binning",
        "predicate": "combines_adjacent_samples_for_low_light_or_noise_benefit_with_lower_output_resolution",
        "object": "binning sums or averages neighboring samples and can improve low-light output or noise while reducing output resolution, sometimes with self-claimed AI processing",
        "source_url": SEARCHES[11][3],
        "search_id": "pixel_binning",
        "role": "concept",
        "scope": "general_binning_tradeoff_not_identification_of_any_exact_sku_mode_or_result",
        "quotes": [
            "Pixel binning , also known as binning , is a process image sensors of digital cameras use to combine adjacent pixels throughout an image, by summing or averaging their values, during or after readout.",
            "Therefore, with pixel binning activated, the 50-megapixel image sensor acts as a 12.5-megapixel image sensor, a quarter of its original resolution, with an accordingly larger surface area per pixel.",
            "Some systems use more advanced algorithms such as considering the values of nearby pixels, edge detection, self-claimed \"AI\", etc. to increase the perceived visual quality of the final downsized image.",
            "The binned image has lower resolution, but the relative noise level in each pixel is generally reduced.",
        ],
        "accepted": "The frozen pixel-binning page says binning combines adjacent samples, can trade output resolution for low-light or noise benefits and may include self-claimed AI processing; this is a general mechanism and does not identify whether, how or how well any exact seller camera bins pixels.",
    },
    {
        "evidence_id": "prop_bayer_single_color_scope",
        "subject": "Bayer-filter sampling",
        "predicate": "records_one_color_per_sensor_site_and_requires_interpolation_for_full_rgb",
        "object": "each Bayer-filtered site records one of three colors and algorithms estimate complete RGB values with computation-dependent output quality",
        "source_url": SEARCHES[12][3],
        "search_id": "bayer_filter",
        "role": "concept",
        "scope": "general_color_filter_and_interpolation_boundary_not_exact_sensor_architecture_or_output_quality",
        "quotes": [
            "Since each pixel is filtered to record only one of three colors, the data from each pixel cannot fully specify each of the red, green, and blue values on its own.",
            "To obtain a full-color image, various demosaicing algorithms can be used to interpolate a set of complete red, green, and blue values for each pixel.",
            "Different algorithms requiring various amounts of computing power result in varying-quality final images.",
        ],
        "accepted": "The frozen Bayer-filter page says each filtered sensor site records only one of three colors, full RGB values require demosaicing and algorithms can produce varying-quality final images; it neither identifies every exact SKU as Bayer nor converts a nominal site count into independently resolved full-color detail.",
    },
    {
        "evidence_id": "prop_demosaicing_artifact_scope",
        "subject": "demosaicing reconstruction",
        "predicate": "reconstructs_full_color_from_incomplete_samples_with_possible_detail_loss_and_artifacts",
        "object": "demosaicing estimates missing color components and can introduce false color, lost detail or sharpness and edge artifacts",
        "source_url": SEARCHES[13][3],
        "search_id": "demosaicing",
        "role": "concept",
        "scope": "general_reconstruction_mechanism_not_exact_firmware_algorithm_or_camera_result",
        "quotes": [
            "Demosaicing (or de-mosaicing , demosaicking ), also known as color reconstruction , is a digital image processing algorithm used to reconstruct a full color image from the incomplete color samples output from an image sensor overlaid with a color filter array (CFA) such as a Bayer filter .",
            "The reconstructed image is typically accurate in uniform-colored areas, but has a loss of resolution (detail and sharpness) and has edge artifacts (for example, the edges of letters have visible color fringes and some roughness).",
        ],
        "accepted": "The frozen demosaicing page defines reconstruction of full color from incomplete color-filter samples and notes possible loss of detail or sharpness and edge artifacts; it gives no exact firmware algorithm, RAW conversion or artifact measurement for the six offers.",
    },
    {
        "evidence_id": "prop_computational_photo_scope",
        "subject": "computational photography",
        "predicate": "uses_digital_computation_in_place_of_or_with_optical_processes",
        "object": "computational capture and processing can add capabilities or reduce hardware burden but covers many unlike operations",
        "source_url": SEARCHES[14][3],
        "search_id": "computational_photo",
        "role": "concept",
        "scope": "general_technique_class_not_validation_of_an_ai_label_or_exact_product_quality",
        "quotes": [
            "Computational photography refers to digital image capture and processing techniques that use digital computation instead of optical processes.",
            "Computational photography can improve the capabilities of a camera, or introduce features that were not possible at all with film-based photography, or reduce the cost or size of camera elements.",
        ],
        "accepted": "The frozen computational-photography page describes a broad class of digital capture and processing techniques that may add capabilities or reduce hardware burden; it does not identify the operation behind an exact AI label or validate a seller's claimed detail improvement.",
    },
    {
        "evidence_id": "prop_super_resolution_limit_scope",
        "subject": "super-resolution imaging",
        "predicate": "improves_output_under_physical_information_and_scene_invariance_constraints",
        "object": "super-resolution is a class of improvement techniques whose multiple-exposure or inference paths exchange assumptions and remain subject to physics and information limits",
        "source_url": SEARCHES[15][3],
        "search_id": "super_resolution",
        "role": "concept",
        "scope": "general_super_resolution_boundary_not_identification_or_validation_of_any_exact_camera_mode",
        "quotes": [
            "Super-resolution imaging ( SR ) is a class of techniques that improve the resolution of an imaging system.",
            "Information transfer can never be increased beyond this boundary, but packets outside the limits can be cleverly swapped for (or multiplexed with) some inside it.",
            "Nor are information-theoretical rules broken when superimposing several bands, [ 7 ] [ 8 ] [ 9 ] disentangling them in the received image needs assumptions of object invariance during multiple exposures, i.e., the substitution of one kind of uncertainty for another.",
        ],
        "accepted": "The frozen super-resolution page defines a class of resolution-improvement techniques while retaining physical and information limits, and says multiple-exposure disentangling can require object invariance; it does not establish that any exact seller mode is super-resolution or that it works on moving subjects.",
    },
    {
        "evidence_id": "prop_forum_megapixel_colloquial_scope",
        "subject": "community megapixel explanation",
        "predicate": "equates_megapixels_with_pixel_count_while_noting_color_sampling_complications",
        "object": "one forum explanation treats megapixels as millions of pixels while another comment says camera and display color-sample counting complicates direct comparison",
        "source_url": SEARCHES[16][3],
        "search_id": "forum_megapixel",
        "role": "community",
        "scope": "commenter_specific_educational_explanation_not_standard_definition_or_exact_product_measurement",
        "quotes": [
            "Yes, megapixels is just resolution. It's just the number of pixels, in millions (mega = million).",
            "Although cameras are different from TVs in the way pixels are counted: A 4K TV has 8 megapixels in one sense but in fact each pixel is made up of three sub-pixels (red, green and blue) so really there are 24 megapixels.",
            "A 24-megapixel camera is usually made up of 12 million green pixels, 6 million red pixels and 6 million blue pixels. This makes it hard compare resolutions.",
        ],
        "accepted": "The frozen ELI5 discussion includes one colloquial explanation that megapixels count millions of pixels and another comment warning that camera and display color sampling complicates comparison; these are commenter-specific educational statements, not a standards definition or a resolved-detail measurement for an exact camera.",
    },
    {
        "evidence_id": "prop_forum_optical_zoom_opinions_scope",
        "subject": "community phone optical-zoom discussion",
        "predicate": "contains_user_preferences_and_detail_complaints_about_phone_zoom_and_processing",
        "object": "individual commenters want more optical zoom for distant scenes and report artificial processing or missing detail when zooming",
        "source_url": SEARCHES[17][3],
        "search_id": "forum_optical_zoom",
        "role": "community",
        "scope": "author_device_scene_and_viewing_specific_opinions_not_matched_test_or_exact_offer_result",
        "quotes": [
            "Landscape photography for example requires much more optical zoom than the wide angles that are on cameras.",
            "I think we mostly need better sensors and optics. For landscape photography when you zoom in a bit you can see all the artificial processing and the lack of detail.",
        ],
        "accepted": "The frozen phone-zoom discussion contains individual preferences for more optical zoom on distant scenes and a commenter report of artificial processing and missing detail when zooming; these observations are author-, device-, scene- and viewing-specific and are not a matched result for any of the six exact offers.",
    },
    {
        "evidence_id": "prop_forum_iphone_accessory_confound_scope",
        "subject": "community iPhone distant-detail complaint",
        "predicate": "reports_blurry_far_detail_with_a_lens_protector_and_comments_identify_that_accessory_as_a_confound",
        "object": "one author reports missing distant detail while using a lens protector, and commenters propose removing the protector before attributing the result to the phone",
        "source_url": SEARCHES[18][3],
        "search_id": "forum_iphone_detail",
        "role": "community",
        "scope": "single_user_device_accessory_scene_and_software_anecdote_not_product_class_or_unconfounded_camera_result",
        "quotes": [
            "The main 1x camera on this phone is worse than my iPhone X. Seriously. I take full brightness shots outside and zoom in and there is no detail in the far objects, just a blurry mess.",
            "I also have a lens protector on the camera module.",
            "You just answered your own complaint. Take off the lens protector. They’re horrible and they affect camera quality.",
        ],
        "accepted": "The frozen iPhone discussion contains one author's distant-detail complaint while using a lens protector and comments that identify that protector as a possible image-quality confound; it motivates controlling accessories but remains a single user, device, scene and software anecdote rather than a clean product comparison.",
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
            "registry_id": "reg_case_spec_camera_claim_boundary_0053",
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
            "bridge_exact_offer_spec_claim_matrix",
            "bridge",
            "six exact frozen imaging offers",
            "retains_identity_price_reviews_claim_type_and_missing_validation",
            "record exact SKU price rating review count selected configuration sensor or output numbers zoom labels AI operations accessories and unresolved units without converting seller copy into measured quality",
            "exact_offer_spec_claim_matrix_v1",
        ),
        (
            "bridge_pixel_count_resolution_sampling_boundary",
            "bridge",
            "pixel counts sampling and resolved detail",
            "separates_sensor_sites_recorded_outputs_and_upper_bounds_from_measured_resolution",
            "distinguish storage sensor sites effective and recorded pixels reconstructed outputs print dots and resolved detail while retaining optics environment binning and color reconstruction limits",
            "pixel_count_resolution_sampling_boundary_v1",
        ),
        (
            "bridge_optical_digital_zoom_physical_boundary",
            "bridge",
            "optical focal length and digital crop evidence",
            "separates_zoom_ratio_endpoints_from_crop_enlargement_and_measured_detail",
            "classify each zoom path from exact wording and endpoints and compare optical files against matched crops without treating the largest x multiplier as absolute reach or sharpness",
            "optical_digital_zoom_physical_boundary_v1",
        ),
        (
            "bridge_computation_reconstruction_ai_scope_boundary",
            "bridge",
            "binning color reconstruction multishot computation and AI labels",
            "requires_named_inputs_operations_outputs_and_testable_effects",
            "separate binning Bayer demosaicing multishot super resolution image enhancement and editing automation and withhold quality credit from any unspecified AI label",
            "computation_reconstruction_ai_scope_boundary_v1",
        ),
        (
            "bridge_current_identity_file_metadata_gate",
            "bridge",
            "current physical products modes and files",
            "blocks_unresolved_units_modes_zoom_types_and_mismatched_outputs",
            "verify exact unit lens or module firmware manual mode output dimensions metadata raw or jpeg path storage and total system cost before claim-level comparison",
            "current_identity_file_metadata_gate_v1",
        ),
        (
            "bridge_matched_scene_print_zoom_trial",
            "bridge",
            "small matched chart scene zoom and print comparison",
            "measures_local_detail_noise_artifacts_motion_and_workflow_under_declared_conditions",
            "use matched viewpoint light target distance support field of view files and output conditions while separating optical crop binning multishot and computational factors under predeclared thresholds",
            "matched_scene_print_zoom_trial_v1",
        ),
        (
            "decision_evidence_bounded_camera_spec_choice",
            "decision",
            "daylight dim scene distant subject and print imaging choice",
            "selects_the_lowest_cost_exact_path_passing_declared_gates_or_separates_paths_or_defers",
            "reject largest number and AI winner shortcuts and choose only the lowest total system cost exact path passing identity detail artifact motion output and workflow gates otherwise keep separately validated paths or defer",
            "evidence_bounded_camera_spec_choice_v1",
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
        "bridge_exact_offer_spec_claim_matrix": [
            "prop_tcl_64mp_ai_offer_scope",
            "prop_dji_64mp_zoom_ai_editor_scope",
            "prop_nikon_optical_digital_storage_scope",
            "prop_vjianger_48mp_digital_zoom_scope",
            "prop_panasonic_multishot_80mp_scope",
            "prop_kuidamos_ambiguous_pixel_ai_scope",
        ],
        "bridge_pixel_count_resolution_sampling_boundary": [
            "prop_tcl_64mp_ai_offer_scope",
            "prop_dji_64mp_zoom_ai_editor_scope",
            "prop_nikon_optical_digital_storage_scope",
            "prop_vjianger_48mp_digital_zoom_scope",
            "prop_panasonic_multishot_80mp_scope",
            "prop_kuidamos_ambiguous_pixel_ai_scope",
            "prop_pixel_sampling_scope",
            "prop_image_resolution_upper_bound_scope",
            "prop_optical_resolution_system_scope",
            "prop_pixel_binning_tradeoff_scope",
            "prop_forum_megapixel_colloquial_scope",
        ],
        "bridge_optical_digital_zoom_physical_boundary": [
            "prop_dji_64mp_zoom_ai_editor_scope",
            "prop_nikon_optical_digital_storage_scope",
            "prop_vjianger_48mp_digital_zoom_scope",
            "prop_digital_zoom_crop_scope",
            "prop_zoom_lens_ratio_scope",
            "prop_forum_optical_zoom_opinions_scope",
            "prop_forum_iphone_accessory_confound_scope",
        ],
        "bridge_computation_reconstruction_ai_scope_boundary": [
            "prop_tcl_64mp_ai_offer_scope",
            "prop_dji_64mp_zoom_ai_editor_scope",
            "prop_panasonic_multishot_80mp_scope",
            "prop_kuidamos_ambiguous_pixel_ai_scope",
            "prop_pixel_binning_tradeoff_scope",
            "prop_bayer_single_color_scope",
            "prop_demosaicing_artifact_scope",
            "prop_computational_photo_scope",
            "prop_super_resolution_limit_scope",
            "prop_forum_iphone_accessory_confound_scope",
        ],
        "bridge_current_identity_file_metadata_gate": [
            "bridge_exact_offer_spec_claim_matrix",
            "bridge_pixel_count_resolution_sampling_boundary",
            "bridge_optical_digital_zoom_physical_boundary",
            "bridge_computation_reconstruction_ai_scope_boundary",
        ],
        "bridge_matched_scene_print_zoom_trial": [
            "bridge_exact_offer_spec_claim_matrix",
            "bridge_pixel_count_resolution_sampling_boundary",
            "bridge_optical_digital_zoom_physical_boundary",
            "bridge_computation_reconstruction_ai_scope_boundary",
            "bridge_current_identity_file_metadata_gate",
            "prop_optical_resolution_system_scope",
            "prop_forum_megapixel_colloquial_scope",
            "prop_forum_optical_zoom_opinions_scope",
            "prop_forum_iphone_accessory_confound_scope",
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
                "source_id": "decision_evidence_bounded_camera_spec_choice",
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
